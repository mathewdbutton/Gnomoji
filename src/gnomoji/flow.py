"""Show/hide the picker, and pick → hide → insert. No GTK.

Inserting is the Shell extension's job (see shell.py); the window must be hidden first
so focus can go back to the app the double-tap came from.
"""

import logging

from .emoji_data import Emoji

log = logging.getLogger(__name__)


class PickerFlow:
    def __init__(self, window, shell, recents):
        self._window = window
        self._shell = shell
        self._recents = recents

    def toggle(self) -> None:
        """Double-tap handler: open the picker, or close it if it's open."""
        if self._window.get_visible():
            self._window.dismiss()
        else:
            self._window.show_picker()

    def pick(self, emoji: Emoji) -> None:
        log.info("Picked %s; asking the extension to insert it", emoji.char)
        self._recents.add(emoji.char)
        self._window.dismiss()
        self._shell.insert(emoji.char)
