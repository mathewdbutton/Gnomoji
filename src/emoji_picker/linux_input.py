"""The little of Linux evdev/uinput the picker needs, using only the standard library.

Replaces python-evdev: read key events from /dev/input/event*, and create a virtual
keyboard through /dev/uinput. Constants and struct layouts are from the kernel's
<linux/input.h>, <linux/input-event-codes.h> and <linux/uinput.h>.
"""

import fcntl
import glob
import os
import struct
from typing import NamedTuple

EV_SYN, EV_KEY = 0x00, 0x01
SYN_REPORT = 0
KEY_A, KEY_LEFTSHIFT, KEY_RIGHTSHIFT, KEY_INSERT = 30, 42, 54, 110
BTN_LEFT = 0x110
KEY_MAX = 0x2FF
BUS_VIRTUAL = 0x06

# struct input_event: struct timeval (two C longs), __u16 type, __u16 code, __s32 value.
EVENT_FORMAT = "llHHi"
EVENT_SIZE = struct.calcsize(EVENT_FORMAT)
# struct uinput_setup: struct input_id (4 x __u16), char name[80], __u32 ff_effects_max.
SETUP_FORMAT = "=4H80sI"

_IOC_WRITE, _IOC_READ = 1, 2


def _ioc(direction: int, kind: str, nr: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord(kind) << 8) | nr


def EVIOCGNAME(length: int) -> int:
    return _ioc(_IOC_READ, "E", 0x06, length)


def EVIOCGBIT(event_type: int, length: int) -> int:
    return _ioc(_IOC_READ, "E", 0x20 + event_type, length)


UI_SET_EVBIT = _ioc(_IOC_WRITE, "U", 100, struct.calcsize("i"))
UI_SET_KEYBIT = _ioc(_IOC_WRITE, "U", 101, struct.calcsize("i"))
UI_DEV_SETUP = _ioc(_IOC_WRITE, "U", 3, struct.calcsize(SETUP_FORMAT))
UI_DEV_CREATE = _ioc(0, "U", 1, 0)
UI_DEV_DESTROY = _ioc(0, "U", 2, 0)


class Event(NamedTuple):
    sec: int
    usec: int
    type: int
    code: int
    value: int

    def timestamp(self) -> float:
        return self.sec + self.usec / 1_000_000


def parse_events(raw: bytes) -> list[Event]:
    return [Event(*fields) for fields in struct.iter_unpack(EVENT_FORMAT, raw)]


def has_bit(mask: bytes, bit: int) -> bool:
    byte = bit // 8
    return byte < len(mask) and bool(mask[byte] & (1 << (bit % 8)))


def list_devices() -> list[str]:
    """The /dev/input/event* nodes we're allowed to read."""
    return sorted(p for p in glob.glob("/dev/input/event*") if os.access(p, os.R_OK))


class InputDevice:
    """One /dev/input/event* node, opened non-blocking (usable with selectors)."""

    def __init__(self, path: str):
        self.path = path
        self._fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            name = bytearray(256)
            fcntl.ioctl(self._fd, EVIOCGNAME(len(name)), name)
            self.name = name.split(b"\0", 1)[0].decode(errors="replace")
            keys = bytearray(KEY_MAX // 8 + 1)
            fcntl.ioctl(self._fd, EVIOCGBIT(EV_KEY, len(keys)), keys)
            self._keys = bytes(keys)
        except OSError:
            os.close(self._fd)
            raise

    def fileno(self) -> int:
        return self._fd

    def has_key(self, code: int) -> bool:
        return has_bit(self._keys, code)

    def read(self) -> list[Event]:
        """Pending events. Raises BlockingIOError if there are none."""
        return parse_events(os.read(self._fd, EVENT_SIZE * 64))

    def close(self) -> None:
        if self._fd >= 0:
            fd, self._fd = self._fd, -1
            os.close(fd)


class VirtualKeyboard:
    """A keyboard made through /dev/uinput. The kernel removes it when we close it or exit."""

    def __init__(self, name: str, keys: list[int]):
        self._fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            fcntl.ioctl(self._fd, UI_SET_EVBIT, EV_KEY)
            for key in keys:
                fcntl.ioctl(self._fd, UI_SET_KEYBIT, key)
            setup = struct.pack(SETUP_FORMAT, BUS_VIRTUAL, 0, 0, 1, name.encode()[:79], 0)
            fcntl.ioctl(self._fd, UI_DEV_SETUP, setup)
            fcntl.ioctl(self._fd, UI_DEV_CREATE)
        except OSError:
            os.close(self._fd)
            raise

    def write(self, event_type: int, code: int, value: int) -> None:
        os.write(self._fd, struct.pack(EVENT_FORMAT, 0, 0, event_type, code, value))

    def syn(self) -> None:
        self.write(EV_SYN, SYN_REPORT, 0)

    def close(self) -> None:
        if self._fd >= 0:
            fd, self._fd = self._fd, -1
            try:
                fcntl.ioctl(fd, UI_DEV_DESTROY)
            finally:
                os.close(fd)
