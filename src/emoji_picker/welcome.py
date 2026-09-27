"""The one-off "Emoji Picker is ready" notification on the very first start."""

import logging
import os
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

WELCOMED_PATH = (
    Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    / "emoji-picker"
    / "welcomed"
)
# GNOME's answer while it hasn't noticed our newly installed desktop file yet (it
# took ~6 s on GNOME 46). The notification is dropped, so we retry.
INVALID_APP = "org.gtk.Notifications.Error.InvalidApp"
RETRY_MS = 1000
TRIES = 30
# The banner hides by itself; this also clears it from the notification list, but
# not so soon that someone who looked away misses it.
KEEP_MS = 60_000

# send(on_result) delivers the notification and calls on_result(None) once it's
# accepted, or on_result(<D-Bus error name>) if it isn't.
Send = Callable[[Callable[[str | None], None]], None]


class Welcome:
    def __init__(
        self,
        send: Send,
        withdraw: Callable[[], None],
        schedule: Callable[[int, Callable[[], None]], None],
        path: Path = WELCOMED_PATH,
        tries: int = TRIES,
    ):
        self._send, self._withdraw, self._schedule = send, withdraw, schedule
        self._path, self._left = path, tries

    def start(self) -> None:
        if self._path.exists():
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            # Can't record it, so skip it rather than show it at every start.
            log.warning("Skipping the welcome notification: can't write %s: %s", self._path, e)
            return
        self._try()

    def _try(self) -> None:
        self._left -= 1
        self._send(self._on_result)

    def _on_result(self, error: str | None) -> None:
        if error is None:
            log.info("Welcome notification shown")
            self._schedule(KEEP_MS, self._withdraw)
            try:
                self._path.touch()
            except OSError as e:
                log.warning("Couldn't record the welcome in %s: %s", self._path, e)
        elif error == INVALID_APP and self._left > 0:
            self._schedule(RETRY_MS, self._try)
        else:
            log.warning("Welcome notification not shown: %s", error)
