"""A uinput virtual keyboard that sends the paste chord (Shift+Insert)."""

from evdev import UInput, ecodes
from evdev.uinput import UInputError

CHORD = (ecodes.KEY_LEFTSHIFT, ecodes.KEY_INSERT)


class Injector:
    NAME = "emoji-picker virtual keyboard"

    def __init__(self, device=None):
        if device is None:
            try:
                device = UInput({ecodes.EV_KEY: list(CHORD)}, name=self.NAME)
            except (OSError, UInputError) as e:
                raise PermissionError(
                    f"Can't create a virtual keyboard via /dev/uinput ({e}). It must be "
                    "writable by the 'input' group and your user must be in that group."
                ) from e
        self._device = device

    def paste(self) -> None:
        for code in CHORD:
            self._key(code, 1)
        for code in reversed(CHORD):
            self._key(code, 0)

    def _key(self, code: int, value: int) -> None:
        self._device.write(ecodes.EV_KEY, code, value)
        self._device.syn()
