"""Detect a double-tap of right Shift by reading keyboards directly from /dev/input."""

import glob
import logging
import selectors
import threading
import time
from collections.abc import Callable

from . import linux_input
from .linux_input import EV_KEY, KEY_RIGHTSHIFT

log = logging.getLogger(__name__)

KEY_UP, KEY_DOWN, KEY_REPEAT = 0, 1, 2


class DoubleTapDetector:
    """Pure state machine: feed key events, get True when a double-tap completes."""

    def __init__(self, interval_ms: int, key: int = KEY_RIGHTSHIFT):
        self.interval = interval_ms / 1000
        self.key = key
        self._reset()

    def set_interval(self, interval_ms: int) -> None:
        """Safe from another thread while the watcher is in feed(): rebinding one float is
        atomic, and a change mid-feed can at worst misjudge a single tap."""
        self.interval = interval_ms / 1000

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


def check_access(list_devices=linux_input.list_devices, event_nodes: list[str] | None = None) -> None:
    """Fail fast with a fix-it message if we can't read any input device."""
    nodes = glob.glob("/dev/input/event*") if event_nodes is None else event_nodes
    if nodes and not list_devices():
        raise PermissionError(
            "Can't read any keyboard in /dev/input. Run ./install.sh from the "
            "emoji-picker folder: it sets up keyboard access."
        )


def _is_keyboard(device) -> bool:
    return device.has_key(KEY_RIGHTSHIFT)


class KeyboardWatcher(threading.Thread):
    """Watches every keyboard (with hotplug) and calls on_double_tap from this thread."""

    RESCAN_SECONDS = 2.0

    def __init__(
        self,
        detector: DoubleTapDetector,
        on_double_tap: Callable[[], object],
        ignore_names=frozenset(),
        list_devices=linux_input.list_devices,
        open_device=linux_input.InputDevice,
        on_crash: Callable[[], object] | None = None,
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
        self.on_crash = on_crash

    def run(self) -> None:
        try:
            self._run_loop()
        except Exception:
            log.exception("Keyboard watcher crashed; the picker will stop responding")
            if self.on_crash is not None:
                self.on_crash()

    def _run_loop(self) -> None:
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
            try:
                if device.name in self.ignore_names or not _is_keyboard(device):
                    device.close()
                    self._rejected.add(path)
                    continue
                log.info("Watching keyboard %s (%s)", device.name, path)
                self.devices[path] = device
                self._selector.register(device, selectors.EVENT_READ)
            except OSError as e:
                log.debug("Device %s failed during inspection: %s", path, e)
                self._rejected.add(path)
                try:
                    device.close()
                except OSError:
                    pass

    def _drain(self, device) -> None:
        try:
            for event in device.read():
                if event.type == EV_KEY and self.detector.feed(
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
