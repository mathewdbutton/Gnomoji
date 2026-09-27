"""Sequencing for show/hide and pick → claim → paste → release. No GTK.

See clipboard.py's module docstring for why the clipboard step is claim (with a
decoy)/arm/release rather than claim-and-swap-back.
"""

import logging
from collections.abc import Callable

from .config import Config
from .emoji_data import Emoji

log = logging.getLogger(__name__)


class PasteFlow:
    def __init__(
        self,
        window,
        clipboard,
        injector,
        recents,
        config: Config,
        schedule: Callable[[int, Callable[[], None]], object],
    ):
        self._window = window
        self._clipboard = clipboard
        self._injector = injector
        self._recents = recents
        self._config = config
        self._schedule = schedule
        self._busy = False
        self._paste_id = 0
        self._pending_release: int | None = None

    @property
    def busy(self) -> bool:
        return self._busy

    def toggle(self) -> None:
        """Double-tap handler. Ignored mid-paste so the clipboard dance isn't disturbed."""
        if self._busy:
            return
        if self._window.get_visible():
            self._window.dismiss()
        else:
            self._window.show_picker()

    def on_focused(self) -> None:
        self._clipboard.save()

    def pick(self, emoji: Emoji) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            self._clipboard.claim(emoji.char, decoy=self._config.restore_clipboard)
            self._recents.add(emoji.char)
            self._window.dismiss()
            self._schedule(self._config.paste_delay_ms, self._paste)
        except Exception:
            self._busy = False
            raise

    def _paste(self) -> None:
        # Once the target app has read the emoji, release after release_after_read_ms
        # (a grace period in case it reads more than once). restore_delay_ms is the
        # fallback for when nothing reads it, e.g. the paste landed nowhere.
        on_read = None
        if self._config.restore_clipboard:
            self._paste_id += 1
            paste_id = self._pending_release = self._paste_id
            on_read = lambda: self._schedule(self._config.release_after_read_ms, lambda: self._restore(paste_id, "after read"))
        self._clipboard.arm(on_read=on_read)
        try:
            self._injector.paste()
        except OSError as e:
            log.error("Paste failed (emoji left on clipboard): %s", e)
            self._pending_release = None
            self._busy = False
            return
        if self._config.restore_clipboard:
            self._schedule(self._config.restore_delay_ms, lambda: self._restore(paste_id, "no read, fallback"))
        else:
            self._busy = False

    def _restore(self, paste_id: int, reason: str) -> None:
        """Release once per paste: whichever of the read or the fallback timer comes first."""
        if self._pending_release != paste_id:
            return
        self._pending_release = None
        try:
            if self._clipboard.release():
                log.info("Clipboard handed back (%s)", reason)
        finally:
            self._busy = False
