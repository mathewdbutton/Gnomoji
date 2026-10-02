from emoji_picker.welcome import INVALID_APP, KEEP_MS, Welcome, message


class FakeGnome:
    """Answers each send with the next queued result (None = accepted)."""

    def __init__(self, *results):
        self.results = list(results)
        self.sent = 0
        self.withdrawn = 0

    def send(self, on_result):
        self.sent += 1
        on_result(self.results.pop(0))

    def withdraw(self):
        self.withdrawn += 1


class FakeTimers:
    def __init__(self):
        self.pending = []

    def schedule(self, ms, fn):
        self.pending.append((ms, fn))

    def run_all(self):
        while self.pending:
            _, fn = self.pending.pop(0)
            fn()


def make(gnome, tries=30):
    timers = FakeTimers()
    return Welcome(gnome.send, gnome.withdraw, timers.schedule, tries=tries), timers


def test_sends_once():
    gnome = FakeGnome(None)
    welcome, timers = make(gnome)
    welcome.start()
    timers.run_all()
    assert gnome.sent == 1


def test_retries_while_gnome_does_not_know_the_app_yet():
    # GNOME takes a few seconds to notice a newly installed desktop file.
    gnome = FakeGnome(INVALID_APP, INVALID_APP, None)
    welcome, timers = make(gnome)
    welcome.start()
    timers.run_all()
    assert gnome.sent == 3


def test_gives_up_after_the_last_try():
    gnome = FakeGnome(INVALID_APP, INVALID_APP)
    welcome, timers = make(gnome, tries=2)
    welcome.start()
    timers.run_all()
    assert gnome.sent == 2


def test_other_errors_give_up_without_retrying():
    gnome = FakeGnome("org.freedesktop.DBus.Error.ServiceUnknown")
    welcome, timers = make(gnome)
    welcome.start()
    timers.run_all()
    assert gnome.sent == 1


def test_accepted_welcome_is_withdrawn_after_a_minute():
    gnome = FakeGnome(None)
    welcome, timers = make(gnome)
    welcome.start()
    assert [ms for ms, _ in timers.pending] == [KEEP_MS]
    assert KEEP_MS == 60_000
    assert gnome.withdrawn == 0
    timers.run_all()
    assert gnome.withdrawn == 1


def test_nothing_withdrawn_when_never_shown():
    gnome = FakeGnome("org.freedesktop.DBus.Error.ServiceUnknown")
    welcome, timers = make(gnome)
    welcome.start()
    timers.run_all()
    assert gnome.withdrawn == 0


def test_message_when_the_extension_is_running():
    assert message(True) == (
        "Emoji Picker is ready", "Double-tap right Shift in a text field to open it."
    )


def test_message_when_a_log_out_is_needed():
    assert message(False) == (
        "Emoji Picker is installed", "Log out and back in once to finish setting it up."
    )
