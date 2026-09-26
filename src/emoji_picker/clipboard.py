"""Put an emoji on the clipboard for one paste, then let it go: decoy, arm, release.

Mutter (GNOME's Wayland compositor) keeps its own copy of the clipboard: the instant
any client claims it, Mutter reads that client's best text/plain value into memory.
When the claiming client's ownership ends (its content set to `None`, or the client
exiting), Mutter takes over and serves whatever it cached.

That means claiming with the emoji and later swapping our own provider's text back to
the old text (the previous design) doesn't actually restore anything for GNOME's
purposes: Mutter already cached the emoji at claim time, so if our process is ever not
there to keep serving the swapped-back text, the clipboard reverts to the emoji, not
the old text.

So instead we never let Mutter see the emoji until the moment we're about to send the
paste chord, and we hand ownership back afterwards rather than holding it forever:

1. **claim** (`claim`): serve a *decoy* -- the saved old text -- so Mutter's instant
   copy is the old text, not the emoji. (If there's no saved text, e.g. an empty or
   image clipboard, serve the emoji from the start; nothing better is possible.)
2. **arm** (`arm`): right before sending the paste chord, switch the provider to
   serve the emoji, so the target app's paste request gets it.
3. **release** (`release`): once the paste has gone through (`arm(on_read=...)`
   reports the target app's read), if the clipboard is
   still ours, call `set_content(None)` to give up ownership. Mutter then serves its
   cached copy -- the decoy, i.e. the old text -- with no further help from us, even
   if our process exits right after.

Verified by hand with `.superpowers/sdd/2026-09-25-emoji-picker/probe_release.py`
(2026-09-26): Mutter asked for the value 10ms after the claim and got the decoy;
`set_content(None)` released ownership without our window having focus; Ctrl+V then
gave the old text, and still did after the probing process exited.

GNOME only accepts a clipboard claim straight after user input in our window, so we
claim once (on pick) and afterwards only change what our provider serves (arm) or
give it up (release); we never claim a second time.
"""

import logging
from collections.abc import Callable

import gi

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, GObject

log = logging.getLogger(__name__)


class SwitchingText(Gdk.ContentProvider):
    """A text clipboard provider whose text can change after it's been claimed."""

    def __init__(self, text: str):
        super().__init__()
        self.text = text
        # One-shot: called on the next read, then cleared.
        self.on_read: Callable[[], None] | None = None

    def do_ref_formats(self) -> Gdk.ContentFormats:
        builder = Gdk.ContentFormatsBuilder.new()
        builder.add_gtype(GObject.TYPE_STRING)
        return builder.to_formats()

    def do_get_value(self):
        # PyGObject 3.48 returns the caller-allocated GValue: (success, value).
        # GTK serialises the string to text/plain for other apps.
        if self.on_read is not None:
            callback, self.on_read = self.on_read, None
            try:
                callback()
            except Exception:
                log.exception("Clipboard read callback failed")
        return True, self.text


class ClipboardKeeper:
    """Snapshots clipboard text, then runs the claim/decoy/arm/release dance.

    `save()` snapshots the current clipboard text (unchanged from before). `claim()`,
    `arm()` and `release()` are the three steps of the dance described in the module
    docstring; see there for why it's shaped this way.
    """

    def __init__(self, clipboard):
        self._cb = clipboard
        self._generation = 0
        self.saved_text: str | None = None
        self._emoji: str | None = None
        self._ours: SwitchingText | None = None
        # Kept for the provider's whole life, even after release() clears _ours,
        # so this keeper (not just GTK's toggle refs) keeps it alive.
        self._served: SwitchingText | None = None
        # On Wayland, GTK only receives a selection offer while our window has
        # focus. If the picker is re-shown without `notify::is-active` firing
        # (GTK can keep is-active True across hide/show), `on_focused` never
        # calls save() -- but GTK still emits the clipboard's own 'changed'
        # signal, carrying the now-focused offer, so we use that as a backstop.
        self._cb.connect("changed", self._on_changed)

    def _on_changed(self, clipboard) -> None:
        """Re-save on a non-local change that actually carries text.

        Ignores our own claim/release (local=True) and changes with no text
        formats (e.g. the transient empty-format change right after release),
        leaving `saved_text` untouched in both cases. The overlapping-read
        generation counter in `save()` already handles a re-save racing with
        an earlier one.
        """
        if not clipboard.is_local() and clipboard.get_formats().contain_gtype(GObject.TYPE_STRING):
            self.save()

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

    def claim(self, emoji: str, decoy: bool) -> None:
        """Claim the clipboard. Must run inside an input handler of our window.

        Serves the saved old text (the decoy) when `decoy` is true and there is
        saved text, so Mutter's instant copy-on-claim is the old text rather than
        the emoji. Otherwise serves the emoji immediately.
        """
        self._emoji = emoji
        text = self.saved_text if (decoy and self.saved_text is not None) else emoji
        self._ours = self._served = SwitchingText(text)
        self._cb.set_content(self._ours)

    def arm(self, on_read: Callable[[], None] | None = None) -> None:
        """Switch the served text to the emoji, right before sending the paste chord.

        `on_read`, if given, is called once, the first time anything reads the
        emoji from us (normally the target app answering the paste chord). It
        runs inside GTK's read, so it should only schedule work, not release.

        Does nothing if we've never claimed (or have already released). This only
        checks whether we're holding a claimed provider, not whether the clipboard
        is still actually ours right now -- if the user copied something else in
        the meantime, this still flips `_ours.text`, harmlessly, since nothing
        reads it any more; `release()` is what checks live ownership.
        """
        if self._ours is not None:
            self._ours.text = self._emoji
            self._ours.on_read = on_read

    def release(self) -> bool:
        """Give up ownership, if the clipboard is still ours.

        Mutter then takes over serving its own cached copy -- the decoy served at
        claim time -- without any further help from this process. Returns True only
        if we actually released; False if something else already owns the clipboard
        (the user copied something else meanwhile) or we already released.
        """
        if self._ours is None or self._cb.get_content() is not self._ours:
            return False
        self._cb.set_content(None)
        self._ours = None
        return True
