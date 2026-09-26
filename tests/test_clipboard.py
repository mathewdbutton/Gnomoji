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
        self._local = False
        self._changed_handlers = []

    def connect(self, signal, handler):
        assert signal == "changed"
        self._changed_handlers.append(handler)
        return len(self._changed_handlers)

    def is_local(self):
        return self._local

    def emit_changed(self, local):
        """Simulate GTK's 'changed' signal, as if the clipboard's offer changed.

        `local` mirrors what `is_local()` should report during the emission.
        The formats a handler sees during the callback come from whatever
        `self.text`/`self.image` are set to at that point, same as a real
        `get_formats()` call.
        """
        self._local = local
        for handler in self._changed_handlers:
            handler(self)

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
        # A real Gdk.Clipboard accepts None here too (that's how ownership is
        # given up); this fake just stores whatever it's handed.
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


def test_claim_with_decoy_serves_the_saved_text():
    # Mutter reads text/plain the instant we claim, so the decoy makes its
    # instant copy the old text rather than the emoji.
    cb = FakeClipboard(text="ORIGINAL")
    keeper = ClipboardKeeper(cb)
    keeper.save()
    assert keeper.saved_text == "ORIGINAL"
    keeper.claim("🎉", decoy=True)
    assert served_by_gtk(cb.content) == "ORIGINAL"


def test_arm_switches_the_decoy_to_the_emoji():
    cb = FakeClipboard(text="ORIGINAL")
    keeper = ClipboardKeeper(cb)
    keeper.save()
    keeper.claim("🎉", decoy=True)
    ours = cb.content
    keeper.arm()
    assert cb.content is ours  # arm doesn't re-claim
    assert served_by_gtk(ours) == "🎉"


def test_arm_callback_fires_once_when_the_emoji_is_read():
    cb = FakeClipboard(text="ORIGINAL")
    keeper = ClipboardKeeper(cb)
    keeper.save()
    keeper.claim("🎉", decoy=True)
    reads = []
    served_by_gtk(cb.content)  # Mutter's decoy read before arming doesn't count
    keeper.arm(on_read=lambda: reads.append(1))
    assert reads == []
    assert served_by_gtk(cb.content) == "🎉"
    assert served_by_gtk(cb.content) == "🎉"
    assert reads == [1]


def test_claim_without_decoy_serves_the_emoji_immediately():
    cb = FakeClipboard(text="ORIGINAL")
    keeper = ClipboardKeeper(cb)
    keeper.save()
    keeper.claim("🎉", decoy=False)
    assert served_by_gtk(cb.content) == "🎉"


def test_release_gives_up_ownership_and_returns_true_when_still_ours():
    cb = FakeClipboard(text="ORIGINAL")
    keeper = ClipboardKeeper(cb)
    keeper.save()
    keeper.claim("🎉", decoy=True)
    keeper.arm()
    assert keeper.release() is True
    assert cb.content is None  # Mutter now serves its own cached copy


def test_image_only_clipboard_serves_the_emoji_from_claim():
    cb = FakeClipboard(image=True)
    keeper = ClipboardKeeper(cb)
    keeper.save()
    keeper.claim("🎉", decoy=True)
    assert served_by_gtk(cb.content) == "🎉"


def test_empty_clipboard_serves_the_emoji_from_claim():
    cb = FakeClipboard()
    keeper = ClipboardKeeper(cb)
    keeper.save()
    keeper.claim("🎉", decoy=True)
    assert served_by_gtk(cb.content) == "🎉"


def test_does_not_release_the_clipboard_the_user_changed_meanwhile():
    cb = FakeClipboard(text="ORIGINAL")
    keeper = ClipboardKeeper(cb)
    keeper.save()
    keeper.claim("🎉", decoy=True)
    users_copy = Gdk.ContentProvider.new_for_value("user copied this")
    cb.content = users_copy
    assert keeper.release() is False
    assert cb.content is users_copy


def test_keeper_keeps_a_reference_to_the_served_provider_after_release():
    # The keeper is the only Python-level reference keeping the provider (and its
    # .text) alive for as long as GTK's C side might still hold it.
    cb = FakeClipboard(text="ORIGINAL")
    keeper = ClipboardKeeper(cb)
    keeper.save()
    keeper.claim("🎉", decoy=True)
    served = cb.content
    assert keeper.release() is True
    assert keeper._served is served


def test_release_only_once():
    cb = FakeClipboard(text="ORIGINAL")
    keeper = ClipboardKeeper(cb)
    keeper.save()
    keeper.claim("🎉", decoy=True)
    assert keeper.release() is True
    assert keeper.release() is False


def test_stale_read_from_previous_save_is_ignored():
    cb = FakeClipboard(text="OLD", defer=True)
    keeper = ClipboardKeeper(cb)
    keeper.save()
    cb.text = "NEW"
    keeper.save()
    for run in cb.pending:
        run()
    assert keeper.saved_text == "NEW"


def test_read_failure_saves_nothing_and_serves_emoji_from_claim():
    cb = FakeClipboard(text="ORIGINAL", fail=True)
    keeper = ClipboardKeeper(cb)
    keeper.save()
    assert keeper.saved_text is None
    keeper.claim("🎉", decoy=True)
    assert served_by_gtk(cb.content) == "🎉"


# --- 'changed' signal backstop (bug I2: re-show doesn't always re-fire notify::is-active,
# but GTK reliably emits the clipboard's own 'changed' with the current offer on focus) ---


def test_non_local_change_with_text_triggers_a_fresh_save():
    cb = FakeClipboard(text="APPLE")
    keeper = ClipboardKeeper(cb)
    keeper.save()
    assert keeper.saved_text == "APPLE"
    cb.text = "BANANA"
    cb.emit_changed(local=False)
    assert keeper.saved_text == "BANANA"


def test_local_change_does_not_trigger_a_resave():
    cb = FakeClipboard(text="APPLE")
    keeper = ClipboardKeeper(cb)
    keeper.save()
    cb.text = "BANANA"  # e.g. our own claim's decoy provider, never actually read
    cb.emit_changed(local=True)
    assert keeper.saved_text == "APPLE"


def test_non_local_change_with_no_text_formats_does_not_resave_or_clear():
    cb = FakeClipboard(text="APPLE")
    keeper = ClipboardKeeper(cb)
    keeper.save()
    cb.text = None  # e.g. the transient empty-format 'changed' right after release
    cb.emit_changed(local=False)
    assert keeper.saved_text == "APPLE"


def test_i2_scenario_second_open_resaves_from_changed_signal():
    # copy APPLE -> pick emoji -> claim (decoy APPLE) -> arm -> release -> copy
    # BANANA elsewhere (non-local 'changed' with text, simulating GTK receiving
    # the offer when our window regains focus) -> pick again -> decoy is BANANA.
    cb = FakeClipboard(text="APPLE")
    keeper = ClipboardKeeper(cb)

    keeper.save()
    assert keeper.saved_text == "APPLE"

    keeper.claim("🎉", decoy=True)
    keeper.arm()
    assert keeper.release() is True

    # The user copies BANANA while our window isn't focused; GTK only tells us
    # about it once we regain focus, as a non-local 'changed' carrying text.
    cb.text = "BANANA"
    cb.emit_changed(local=False)

    keeper.claim("🎉", decoy=True)
    assert served_by_gtk(cb.content) == "BANANA"
