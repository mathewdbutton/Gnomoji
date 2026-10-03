"""The one-off welcome notification after the extension is first switched on."""

import logging
from collections.abc import Callable

log = logging.getLogger(__name__)

# GNOME's answer while it hasn't noticed our newly installed desktop file yet (it
# took ~6 s on GNOME 46). The notification is dropped, so we retry.
INVALID_APP = "org.gtk.Notifications.Error.InvalidApp"
RETRY_MS = 1000
TRIES = 30
# The banner hides by itself; this also clears it from the notification list, but
# not so soon that someone who looked away misses it.
KEEP_MS = 60_000

READY = ("Emoji Picker is ready", "Double-tap right Shift in a text field to open it.")
LOG_OUT = ("Emoji Picker is installed", "Log out and back in once to finish setting it up.")


def message(active: bool) -> tuple[str, str]:
    """Title and body: ready if the extension is running, else ask for one log-out."""
    return READY if active else LOG_OUT


# Right after the first start switches the extension on, GNOME Shell may not have turned it
# on yet, so a "not running" answer waits this long for its Ready signal, then asks again.
READY_WAIT_MS = 3000


class ActiveCheck:
    """Answer once whether the extension is running, allowing for it to start any moment.

    ask(callback) asks GNOME Shell (callback(True/False)); on_ready(callback) subscribes to
    the extension's Ready signal; answer(active) gets the verdict, exactly once.
    """

    def __init__(
        self,
        ask: Callable[[Callable[[bool], None]], None],
        on_ready: Callable[[Callable[[], None]], None],
        schedule: Callable[[int, Callable[[], None]], None],
        answer: Callable[[bool], None],
    ):
        self._ask, self._on_ready, self._schedule = ask, on_ready, schedule
        self._answer = answer
        self._done = False

    def start(self) -> None:
        self._ask(self._first_answer)

    def _first_answer(self, active: bool) -> None:
        if active:
            self._finish(True)
            return
        self._on_ready(lambda: self._finish(True))
        self._schedule(READY_WAIT_MS, self._ask_again)

    def _ask_again(self) -> None:
        if not self._done:
            self._ask(self._finish)

    def _finish(self, active: bool) -> None:
        if not self._done:
            self._done = True
            self._answer(active)


# send(on_result) delivers the notification and calls on_result(None) once it's
# accepted, or on_result(<D-Bus error name>) if it isn't.
Send = Callable[[Callable[[str | None], None]], None]


class Welcome:
    def __init__(
        self,
        send: Send,
        withdraw: Callable[[], None],
        schedule: Callable[[int, Callable[[], None]], None],
        tries: int = TRIES,
    ):
        self._send, self._withdraw, self._schedule = send, withdraw, schedule
        self._left = tries

    def start(self) -> None:
        self._try()

    def _try(self) -> None:
        self._left -= 1
        self._send(self._on_result)

    def _on_result(self, error: str | None) -> None:
        if error is None:
            log.info("Welcome notification shown")
            self._schedule(KEEP_MS, self._withdraw)
        elif error == INVALID_APP and self._left > 0:
            self._schedule(RETRY_MS, self._try)
        else:
            log.warning("Welcome notification not shown: %s", error)
