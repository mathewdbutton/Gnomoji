"""Put an emoji on the clipboard for one paste, then hand back the old text.

GNOME only accepts a clipboard claim straight after user input in our window, so we
claim once (on pick) and afterwards only change what our provider serves.
"""

import logging

import gi

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, GObject

log = logging.getLogger(__name__)


class SwitchingText(Gdk.ContentProvider):
    """A text clipboard provider whose text can change after it's been claimed."""

    def __init__(self, text: str):
        super().__init__()
        self.text = text

    def do_ref_formats(self) -> Gdk.ContentFormats:
        builder = Gdk.ContentFormatsBuilder.new()
        builder.add_gtype(GObject.TYPE_STRING)
        return builder.to_formats()

    def do_get_value(self):
        # PyGObject 3.48 returns the caller-allocated GValue: (success, value).
        # GTK serialises the string to text/plain for other apps.
        return True, self.text


class ClipboardKeeper:
    def __init__(self, clipboard):
        self._cb = clipboard
        self._generation = 0
        self.saved_text: str | None = None
        self._ours: SwitchingText | None = None

    def save(self) -> None:
        """Snapshot the clipboard text. Call while our window has keyboard focus."""
        self._generation += 1
        self.saved_text = None
        if self._cb.get_formats().contain_gtype(GObject.TYPE_STRING):
            self._cb.read_text_async(None, self._on_text, self._generation)

    def _on_text(self, clipboard, result, generation) -> None:
        try:
            text = clipboard.read_text_finish(result)
        except GLib.Error as e:
            log.info("Couldn't read clipboard text: %s", e)
            return
        if generation == self._generation:
            self.saved_text = text

    def set_text(self, text: str) -> None:
        """Claim the clipboard. Must run inside an input handler of our window."""
        self._ours = SwitchingText(text)
        self._cb.set_content(self._ours)

    def restore(self) -> bool:
        """Serve the saved text again, only if the clipboard is still ours."""
        if self.saved_text is None or self._ours is None:
            return False
        if self._cb.get_content() is not self._ours:
            return False
        self._ours.text = self.saved_text
        self._ours = None
        return True
