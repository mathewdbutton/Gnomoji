"""Detect a double-tap of right Shift by reading keyboards directly from /dev/input."""

import glob
import logging
import selectors
import threading
import time
from collections.abc import Callable

import evdev
from evdev import ecodes

log = logging.getLogger(__name__)

KEY_UP, KEY_DOWN, KEY_REPEAT = 0, 1, 2


class DoubleTapDetector:
    """Pure state machine: feed key events, get True when a double-tap completes."""

    def __init__(self, interval_ms: int, key: int = ecodes.KEY_RIGHTSHIFT):
        self.interval = interval_ms / 1000
        self.key = key
        self._reset()

    def _reset(self) -> None:
        self._down_at: float | None = None
        self._last_tap_up: float | None = None
        self._taps = 0

    def feed(self, code: int, value: int, t: float) -> bool:
        if code != self.key:
            if value == KEY_DOWN:
                self._reset()
            return False
        if value == KEY_REPEAT:
            self._reset()
            return False
        if value == KEY_DOWN:
            if self._last_tap_up is not None and t - self._last_tap_up > self.interval:
                self._taps = 0
            self._down_at = t
            return False
        # KEY_UP
        if self._down_at is None:
            return False
        held, self._down_at = t - self._down_at, None
        if held > self.interval:
            self._reset()
            return False
        self._taps += 1
        self._last_tap_up = t
        if self._taps >= 2:
            self._reset()
            return True
        return False


def check_access(list_devices=evdev.list_devices, event_nodes: list[str] | None = None) -> None:
    """Fail fast with a fix-it message if we can't read any input device."""
    nodes = glob.glob("/dev/input/event*") if event_nodes is None else event_nodes
    if nodes and not list_devices():
        raise PermissionError(
            "Can't read any device in /dev/input. Add your user to the 'input' group "
            "(sudo usermod -aG input $USER), then log out and back in."
        )


def _is_keyboard(device) -> bool:
    return ecodes.KEY_RIGHTSHIFT in device.capabilities().get(ecodes.EV_KEY, [])


class KeyboardWatcher(threading.Thread):
    """Watches every keyboard (with hotplug) and calls on_double_tap from this thread."""

    RESCAN_SECONDS = 2.0

    def __init__(
        self,
        detector: DoubleTapDetector,
        on_double_tap: Callable[[], object],
        ignore_names=frozenset(),
        list_devices=evdev.list_devices,
        open_device=evdev.InputDevice,
    ):
        super().__init__(daemon=True, name="keyboard-watcher")
        self.detector = detector
        self.on_double_tap = on_double_tap
        self.ignore_names = set(ignore_names)
        self._list_devices = list_devices
        self._open_device = open_device
        self._selector = selectors.DefaultSelector()
        self.devices: dict[str, object] = {}
        self._rejected: set[str] = set()

    def run(self) -> None:
        next_scan = 0.0
        while True:
            now = time.monotonic()
            if now >= next_scan:
                self._rescan()
                next_scan = now + self.RESCAN_SECONDS
            for key, _ in self._selector.select(timeout=self.RESCAN_SECONDS):
                self._drain(key.fileobj)

    def _rescan(self) -> None:
        paths = set(self._list_devices())
        for gone in set(self.devices) - paths:
            self._drop(gone)
        self._rejected &= paths
        for path in paths - set(self.devices) - self._rejected:
            try:
                device = self._open_device(path)
            except OSError as e:
                log.debug("Can't open %s: %s", path, e)
                self._rejected.add(path)
                continue
            if device.name in self.ignore_names or not _is_keyboard(device):
                device.close()
                self._rejected.add(path)
                continue
            log.info("Watching keyboard %s (%s)", device.name, path)
            self.devices[path] = device
            self._selector.register(device, selectors.EVENT_READ)

    def _drain(self, device) -> None:
        try:
            for event in device.read():
                if event.type == ecodes.EV_KEY and self.detector.feed(
                    event.code, event.value, event.timestamp()
                ):
                    self.on_double_tap()
        except BlockingIOError:
            pass
        except OSError as e:
            log.info("Keyboard %s went away: %s", device.path, e)
            self._drop(device.path)

    def _drop(self, path: str) -> None:
        device = self.devices.pop(path, None)
        if device is None:
            return
        try:
            self._selector.unregister(device)
        except (KeyError, ValueError):
            pass
        try:
            device.close()
        except OSError:
            pass
