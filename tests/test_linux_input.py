import os
import struct
import time

import pytest

from emoji_picker import linux_input as li

# --- ioctl numbers, checked against the kernel headers' values ----------------


def test_ioctl_numbers_match_the_kernel():
    assert li.EVIOCGNAME(256) == 0x81004506
    assert li.EVIOCGBIT(li.EV_KEY, 96) == 0x80604521
    assert li.UI_SET_EVBIT == 0x40045564
    assert li.UI_SET_KEYBIT == 0x40045565
    assert li.UI_DEV_SETUP == 0x405C5503
    assert li.UI_DEV_CREATE == 0x5501
    assert li.UI_DEV_DESTROY == 0x5502


def test_key_codes_match_the_kernel():
    assert (li.EV_SYN, li.EV_KEY, li.SYN_REPORT) == (0, 1, 0)
    assert (li.KEY_A, li.KEY_LEFTSHIFT, li.KEY_RIGHTSHIFT, li.KEY_INSERT) == (30, 42, 54, 110)
    assert li.BTN_LEFT == 0x110


# --- event parsing ----------------------------------------------------------------


def test_parse_events_reads_type_code_value_and_time():
    raw = struct.pack(li.EVENT_FORMAT, 12, 500_000, li.EV_KEY, li.KEY_RIGHTSHIFT, 1)
    raw += struct.pack(li.EVENT_FORMAT, 12, 750_000, li.EV_SYN, li.SYN_REPORT, 0)
    events = li.parse_events(raw)
    assert [(e.type, e.code, e.value) for e in events] == [
        (li.EV_KEY, li.KEY_RIGHTSHIFT, 1),
        (li.EV_SYN, li.SYN_REPORT, 0),
    ]
    assert events[0].timestamp() == pytest.approx(12.5)


def test_has_bit_reads_a_little_endian_bitmask():
    mask = bytearray(16)
    mask[li.KEY_RIGHTSHIFT // 8] |= 1 << (li.KEY_RIGHTSHIFT % 8)
    assert li.has_bit(bytes(mask), li.KEY_RIGHTSHIFT)
    assert not li.has_bit(bytes(mask), li.KEY_LEFTSHIFT)
    assert not li.has_bit(bytes(mask), 8 * len(mask) + 5)  # past the end


# --- real round trip through /dev/uinput -------------------------------------------

needs_uinput = pytest.mark.skipif(
    not os.access("/dev/uinput", os.W_OK), reason="needs write access to /dev/uinput"
)


@needs_uinput
def test_virtual_keyboard_round_trip():
    name = f"emoji-picker test keyboard {os.getpid()}"
    keyboard = li.VirtualKeyboard(name, [li.KEY_RIGHTSHIFT, li.KEY_INSERT])
    try:
        device = None
        for _ in range(50):  # udev takes a moment to create and permission the node
            for path in li.list_devices():
                try:
                    candidate = li.InputDevice(path)
                except OSError:
                    continue
                if candidate.name == name:
                    device = candidate
                    break
                candidate.close()
            if device is not None:
                break
            time.sleep(0.05)
        if device is None:
            pytest.skip("our virtual keyboard's node isn't readable here")
        try:
            assert device.path.startswith("/dev/input/event")
            assert device.has_key(li.KEY_RIGHTSHIFT)
            assert device.has_key(li.KEY_INSERT)
            assert not device.has_key(li.KEY_A)
            with pytest.raises(BlockingIOError):
                device.read()  # nothing yet, and it doesn't block

            keyboard.write(li.EV_KEY, li.KEY_RIGHTSHIFT, 1)
            keyboard.syn()
            keyboard.write(li.EV_KEY, li.KEY_RIGHTSHIFT, 0)
            keyboard.syn()
            time.sleep(0.05)
            keys = [(e.code, e.value) for e in device.read() if e.type == li.EV_KEY]
            assert keys == [(li.KEY_RIGHTSHIFT, 1), (li.KEY_RIGHTSHIFT, 0)]
        finally:
            device.close()
    finally:
        keyboard.close()


def test_virtual_keyboard_without_access_raises_oserror(monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError(13, "Permission denied", "/dev/uinput")

    monkeypatch.setattr(li.os, "open", denied)
    with pytest.raises(OSError):
        li.VirtualKeyboard("x", [li.KEY_INSERT])
