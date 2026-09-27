"""Sequencing for show/hide and pick → claim → paste → release. No GTK.

See clipboard.py's module docstring for why the clipboard step is claim (with a
decoy)/arm/release rather than claim-and-swap-back.
"""

import logging
from collections.abc import Callable
from functools import partial

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
        self._active = config  # the config of the paste in progress (see set_config)
        self._schedule = schedule
        self._busy = False
        self._release_token = 0
        self._pending_release: int | None = None

    def set_config(self, config: Config) -> None:
        """Takes effect from the next pick; a paste in progress keeps the settings it
        started with, so a claim with a decoy is always followed by its release."""
        self._config = config

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
        self._active = self._config
        try:
            self._clipboard.claim(emoji.char, decoy=self._active.restore_clipboard)
            self._recents.add(emoji.char)
            self._window.dismiss()
            self._schedule(self._active.paste_delay_ms, self._paste)
        except Exception:
            self._busy = False
            raise

    def _paste(self) -> None:
        # The release happens release_after_read_ms after the target app's *last* read
        # of the emoji (each read restarts it, in case an app reads more than once), or
        # after restore_delay_ms if nothing reads it, e.g. the paste landed nowhere.
        restore = self._active.restore_clipboard
        if restore:
            token = self._new_release_token()
        self._clipboard.arm(on_read=self._on_read if restore else None)
        try:
            self._injector.paste()
        except Exception:
            log.exception("Paste failed (emoji left on clipboard)")
            self._pending_release = None
            self._busy = False
            return
        if restore:
            self._schedule(self._active.restore_delay_ms, partial(self._restore, token, "no read, fallback"))
        else:
            self._busy = False

    def _on_read(self) -> None:
        """The target app read the emoji: (re)start the grace period, superseding earlier timers."""
        if self._pending_release is None:
            return
        token = self._new_release_token()
        self._schedule(self._active.release_after_read_ms, partial(self._restore, token, "after read"))

    def _new_release_token(self) -> int:
        self._release_token += 1
        self._pending_release = self._release_token
        return self._release_token

    def _restore(self, token: int, reason: str) -> None:
        """Release once, from whichever timer is still current."""
        if self._pending_release != token:
            return
        self._pending_release = None
        try:
            if self._clipboard.release():
                log.info("Clipboard handed back (%s)", reason)
        finally:
            self._busy = False
