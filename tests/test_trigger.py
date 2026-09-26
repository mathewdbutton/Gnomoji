import os
from collections import namedtuple

import pytest
from evdev import ecodes

from emoji_picker.trigger import DoubleTapDetector, KeyboardWatcher, check_access

RS, LS, A = ecodes.KEY_RIGHTSHIFT, ecodes.KEY_LEFTSHIFT, ecodes.KEY_A
DOWN, UP, REPEAT = 1, 0, 2


def tap(key, start, hold=0.05):
    return [(start, key, DOWN), (start + hold, key, UP)]


def fired(events, interval_ms=300):
    d = DoubleTapDetector(interval_ms)
    return [d.feed(code, value, t) for t, code, value in events]


# --- DoubleTapDetector -----------------------------------------------------


def test_double_tap_fires_on_second_release():
    assert fired(tap(RS, 0.0) + tap(RS, 0.15)) == [False, False, False, True]


def test_slow_second_tap_does_not_fire():
    assert not any(fired(tap(RS, 0.0) + tap(RS, 0.5)))


def test_slow_tap_then_quick_tap_fires():
    assert fired(tap(RS, 0.0) + tap(RS, 1.0) + tap(RS, 1.15))[-1] is True


def test_long_hold_is_not_a_tap():
    assert not any(fired([(0.0, RS, DOWN), (0.5, RS, UP)] + tap(RS, 0.6)))


def test_auto_repeat_cancels():
    events = [(0.0, RS, DOWN), (0.05, RS, REPEAT), (0.1, RS, UP)] + tap(RS, 0.2)
    assert not any(fired(events))


def test_other_key_between_taps_cancels():
    assert not any(fired(tap(RS, 0.0) + tap(A, 0.08, 0.02) + tap(RS, 0.15)))


def test_shift_used_for_capital_then_taps():
    capital = [(0.0, RS, DOWN), (0.02, A, DOWN), (0.04, A, UP), (0.06, RS, UP)]
    results = fired(capital + tap(RS, 0.15) + tap(RS, 0.3))
    assert results[:6] == [False] * 6  # capital + first tap: nothing
    assert results[-1] is True  # the two clean taps after it still work


def test_left_shift_is_ignored():
    assert not any(fired(tap(LS, 0.0) + tap(LS, 0.15)))


def test_triple_tap_fires_once():
    results = fired(tap(RS, 0.0) + tap(RS, 0.15) + tap(RS, 0.3))
    assert results.count(True) == 1


# --- KeyboardWatcher -------------------------------------------------------

Event = namedtuple("Event", "type code value t")
Event.timestamp = lambda self: self.t


class FakeDevice:
    def __init__(self, path, name="kbd", keys=(RS, A)):
        self.path, self.name, self._keys = path, name, list(keys)
        self._r, self._w = os.pipe()
        self.events, self.fail, self.closed = [], False, False

    def fileno(self):
        return self._r

    def capabilities(self):
        return {ecodes.EV_KEY: self._keys}

    def read(self):
        if self.fail:
            raise OSError(19, "No such device")
        events, self.events = self.events, []
        return events

    def close(self):
        if not self.closed:
            self.closed = True
            os.close(self._r)
            os.close(self._w)


class FakeInput:
    def __init__(self, devices):
        self.devices = {d.path: d for d in devices}
        self.opens = []

    def list_devices(self):
        return list(self.devices)

    def open(self, path):
        self.opens.append(path)
        return self.devices[path]


def watcher(fake, calls=None, **kw):
    return KeyboardWatcher(
        DoubleTapDetector(300),
        on_double_tap=lambda: calls.append(1) if calls is not None else None,
        list_devices=fake.list_devices,
        open_device=fake.open,
        **kw,
    )


def test_rescan_keeps_keyboards_only():
    kbd = FakeDevice("/dev/input/event1")
    mouse = FakeDevice("/dev/input/event2", name="mouse", keys=[ecodes.BTN_LEFT])
    ours = FakeDevice("/dev/input/event3", name="emoji-picker virtual keyboard")
    fake = FakeInput([kbd, mouse, ours])
    w = watcher(fake, ignore_names={"emoji-picker virtual keyboard"})
    w._rescan()
    assert set(w.devices) == {"/dev/input/event1"}
    assert mouse.closed and ours.closed


def test_rejected_devices_are_not_reopened_every_scan():
    mouse = FakeDevice("/dev/input/event2", name="mouse", keys=[ecodes.BTN_LEFT])
    fake = FakeInput([mouse])
    w = watcher(fake)
    w._rescan()
    w._rescan()
    assert fake.opens == ["/dev/input/event2"]


def test_unplugged_device_is_dropped_and_new_one_added():
    kbd1, kbd2 = FakeDevice("/dev/input/event1"), FakeDevice("/dev/input/event4")
    fake = FakeInput([kbd1])
    w = watcher(fake)
    w._rescan()
    del fake.devices[kbd1.path]
    fake.devices[kbd2.path] = kbd2
    w._rescan()
    assert set(w.devices) == {kbd2.path}
    assert kbd1.closed


def test_device_that_fails_to_open_is_skipped():
    fake = FakeInput([])
    fake.devices["/dev/input/event9"] = None
    fake.open = lambda path: (_ for _ in ()).throw(PermissionError(13, "denied"))
    w = watcher(fake)
    w._rescan()
    assert w.devices == {}


def test_device_that_fails_during_inspection_is_skipped():
    bad = FakeDevice("/dev/input/event1")
    good = FakeDevice("/dev/input/event2")

    def bad_capabilities():
        raise OSError(19, "No such device")

    bad.capabilities = bad_capabilities
    fake = FakeInput([bad, good])
    w = watcher(fake)
    w._rescan()
    assert "/dev/input/event1" not in w.devices
    assert "/dev/input/event2" in w.devices
    assert "/dev/input/event1" in w._rejected
    # Verify it's not reopened on the next scan
    w._rescan()
    assert fake.opens.count("/dev/input/event1") == 1


def test_drain_feeds_detector_and_calls_back():
    kbd = FakeDevice("/dev/input/event1")
    calls = []
    w = watcher(FakeInput([kbd]), calls)
    w._rescan()
    kbd.events = [
        Event(ecodes.EV_KEY, RS, 1, 0.0),
        Event(ecodes.EV_SYN, 0, 0, 0.0),
        Event(ecodes.EV_KEY, RS, 0, 0.05),
        Event(ecodes.EV_KEY, RS, 1, 0.15),
        Event(ecodes.EV_KEY, RS, 0, 0.2),
    ]
    w._drain(kbd)
    assert calls == [1]


def test_drain_read_error_drops_device():
    kbd = FakeDevice("/dev/input/event1")
    w = watcher(FakeInput([kbd]))
    w._rescan()
    kbd.fail = True
    w._drain(kbd)
    assert w.devices == {}


# --- check_access ----------------------------------------------------------


def test_check_access_raises_when_nodes_exist_but_none_readable():
    with pytest.raises(PermissionError, match="input"):
        check_access(list_devices=list, event_nodes=["/dev/input/event0"])


def test_check_access_passes_when_something_readable():
    check_access(list_devices=lambda: ["/dev/input/event0"], event_nodes=["/dev/input/event0"])
