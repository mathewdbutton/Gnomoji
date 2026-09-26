import ctypes

import gi

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, GObject

from emoji_picker.clipboard import ClipboardKeeper, SwitchingText


class FakeClipboard:
    """Mimics the parts of Gdk.Clipboard we use. Reads snapshot at request time."""

    def __init__(self, text=None, image=False, defer=False, fail=False):
        self.text, self.image = text, image
        self.defer, self.fail = defer, fail
        self.pending = []
        self.content = None

    def get_formats(self):
        builder = Gdk.ContentFormatsBuilder.new()
        if self.text is not None:
            builder.add_gtype(GObject.TYPE_STRING)
        if self.image:
            builder.add_gtype(Gdk.Texture)
        return builder.to_formats()

    def read_text_async(self, cancellable, callback, user_data):
        result = self.text
        if self.defer:
            self.pending.append(lambda: callback(self, result, user_data))
        else:
            callback(self, result, user_data)

    def read_text_finish(self, result):
        if self.fail:
            raise GLib.Error("read failed")
        return result

    def set_content(self, provider):
        self.content = provider

    def get_content(self):
        return self.content


def served_by_gtk(provider):
    """Ask GTK's C API for the provider's string, the way a real paste request does."""
    gtk = ctypes.CDLL("libgtk-4.so.1")
    gobject = ctypes.CDLL("libgobject-2.0.so.0")
    gtk.gdk_content_provider_get_value.argtypes = [ctypes.c_void_p] * 3
    gtk.gdk_content_provider_get_value.restype = ctypes.c_int
    gobject.g_value_init.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    gobject.g_value_get_string.argtypes = [ctypes.c_void_p]
    gobject.g_value_get_string.restype = ctypes.c_char_p
    ctypes.pythonapi.PyCapsule_GetPointer.restype = ctypes.c_void_p
    ctypes.pythonapi.PyCapsule_GetPointer.argtypes = [ctypes.py_object, ctypes.c_char_p]
    pointer = ctypes.pythonapi.PyCapsule_GetPointer(provider.__gpointer__, None)
    value = (ctypes.c_byte * 64)()
    gobject.g_value_init(value, 64)  # G_TYPE_STRING
    assert gtk.gdk_content_provider_get_value(pointer, value, None) == 1
    return gobject.g_value_get_string(value).decode("utf-8")


def test_switching_text_serves_current_text_through_gtk():
    provider = SwitchingText("🎉")
    assert provider.ref_formats().contain_gtype(GObject.TYPE_STRING)
    assert served_by_gtk(provider) == "🎉"
    provider.text = "ORIGINAL"
    assert served_by_gtk(provider) == "ORIGINAL"


def test_restore_swaps_served_text_without_reclaiming():
    cb = FakeClipboard(text="ORIGINAL")
    keeper = ClipboardKeeper(cb)
    keeper.save()
    assert keeper.saved_text == "ORIGINAL"
    keeper.set_text("🎉")
    ours = cb.content
    assert served_by_gtk(ours) == "🎉"
    assert keeper.restore() is True
    assert cb.content is ours  # no second claim
    assert served_by_gtk(ours) == "ORIGINAL"


def test_image_only_clipboard_leaves_emoji_in_place():
    cb = FakeClipboard(image=True)
    keeper = ClipboardKeeper(cb)
    keeper.save()
    keeper.set_text("🎉")
    assert keeper.restore() is False
    assert served_by_gtk(cb.content) == "🎉"


def test_empty_clipboard_leaves_emoji_in_place():
    cb = FakeClipboard()
    keeper = ClipboardKeeper(cb)
    keeper.save()
    keeper.set_text("🎉")
    assert keeper.restore() is False
    assert served_by_gtk(cb.content) == "🎉"


def test_does_not_touch_clipboard_the_user_changed_meanwhile():
    cb = FakeClipboard(text="ORIGINAL")
    keeper = ClipboardKeeper(cb)
    keeper.save()
    keeper.set_text("🎉")
    users_copy = Gdk.ContentProvider.new_for_value("user copied this")
    cb.content = users_copy
    assert keeper.restore() is False
    assert cb.content is users_copy


def test_restore_only_once():
    cb = FakeClipboard(text="ORIGINAL")
    keeper = ClipboardKeeper(cb)
    keeper.save()
    keeper.set_text("🎉")
    assert keeper.restore() is True
    assert keeper.restore() is False


def test_stale_read_from_previous_save_is_ignored():
    cb = FakeClipboard(text="OLD", defer=True)
    keeper = ClipboardKeeper(cb)
    keeper.save()
    cb.text = "NEW"
    keeper.save()
    for run in cb.pending:
        run()
    assert keeper.saved_text == "NEW"


def test_read_failure_saves_nothing_and_does_not_raise():
    cb = FakeClipboard(text="ORIGINAL", fail=True)
    keeper = ClipboardKeeper(cb)
    keeper.save()
    assert keeper.saved_text is None
    keeper.set_text("🎉")
    assert keeper.restore() is False
