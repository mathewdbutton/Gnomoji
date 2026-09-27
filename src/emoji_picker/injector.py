"""A uinput virtual keyboard that sends the paste chord (Shift+Insert)."""

from .linux_input import EV_KEY, KEY_INSERT, KEY_LEFTSHIFT, VirtualKeyboard

CHORD = (KEY_LEFTSHIFT, KEY_INSERT)


class Injector:
    NAME = "emoji-picker virtual keyboard"

    def __init__(self, device=None):
        if device is None:
            try:
                device = VirtualKeyboard(self.NAME, list(CHORD))
            except OSError as e:
                raise PermissionError(
                    f"Can't create a virtual keyboard via /dev/uinput ({e}). Run "
                    "./install.sh from the emoji-picker folder: it sets up access."
                ) from e
        self._device = device

    def paste(self) -> None:
        for code in CHORD:
            self._key(code, 1)
        for code in reversed(CHORD):
            self._key(code, 0)

    def _key(self, code: int, value: int) -> None:
        self._device.write(EV_KEY, code, value)
        self._device.syn()
