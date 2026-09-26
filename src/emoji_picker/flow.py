"""Sequencing for show/hide and pick → clipboard → paste → restore. No GTK."""

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
        self._recents.add(emoji.char)
        self._clipboard.set_text(emoji.char)
        self._window.dismiss()
        self._schedule(self._config.paste_delay_ms, self._paste)

    def _paste(self) -> None:
        try:
            self._injector.paste()
        except OSError as e:
            log.error("Paste failed (emoji left on clipboard): %s", e)
            self._busy = False
            return
        if self._config.restore_clipboard:
            self._schedule(self._config.restore_delay_ms, self._restore)
        else:
            self._busy = False

    def _restore(self) -> None:
        try:
            self._clipboard.restore()
        finally:
            self._busy = False
