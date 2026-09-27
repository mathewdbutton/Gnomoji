from emoji_picker.welcome import INVALID_APP, KEEP_MS, Welcome


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


def make(tmp_path, gnome, tries=30):
    timers = FakeTimers()
    marker = tmp_path / "emoji-picker" / "welcomed"
    return Welcome(gnome.send, gnome.withdraw, timers.schedule, marker, tries=tries), timers, marker


def test_first_start_sends_once_and_records_it(tmp_path):
    gnome = FakeGnome(None)
    welcome, timers, marker = make(tmp_path, gnome)
    welcome.start()
    timers.run_all()
    assert gnome.sent == 1
    assert marker.exists()


def test_not_sent_again_once_recorded(tmp_path):
    gnome = FakeGnome()
    welcome, _, marker = make(tmp_path, gnome)
    marker.parent.mkdir(parents=True)
    marker.touch()
    welcome.start()
    assert gnome.sent == 0


def test_retries_while_gnome_does_not_know_the_app_yet(tmp_path):
    # GNOME takes a few seconds to notice a newly installed desktop file.
    gnome = FakeGnome(INVALID_APP, INVALID_APP, None)
    welcome, timers, marker = make(tmp_path, gnome)
    welcome.start()
    assert not marker.exists()
    timers.run_all()
    assert gnome.sent == 3
    assert marker.exists()


def test_gives_up_after_the_last_try_without_recording(tmp_path):
    gnome = FakeGnome(INVALID_APP, INVALID_APP)
    welcome, timers, marker = make(tmp_path, gnome, tries=2)
    welcome.start()
    timers.run_all()
    assert gnome.sent == 2
    assert not marker.exists()  # try again at the next start


def test_other_errors_give_up_without_retrying(tmp_path):
    gnome = FakeGnome("org.freedesktop.DBus.Error.ServiceUnknown")
    welcome, timers, marker = make(tmp_path, gnome)
    welcome.start()
    timers.run_all()
    assert gnome.sent == 1
    assert not marker.exists()


def test_unwritable_location_skips_the_welcome_without_raising(tmp_path, caplog):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("")
    gnome = FakeGnome()
    timers = FakeTimers()
    # Can't record the welcome, so skip it rather than show it at every start.
    Welcome(gnome.send, gnome.withdraw, timers.schedule, blocker / "welcomed").start()
    assert gnome.sent == 0
    assert "welcome" in caplog.text


def test_accepted_welcome_is_withdrawn_after_a_minute(tmp_path):
    gnome = FakeGnome(None)
    welcome, timers, _ = make(tmp_path, gnome)
    welcome.start()
    assert [ms for ms, _ in timers.pending] == [KEEP_MS]
    assert KEEP_MS == 60_000
    assert gnome.withdrawn == 0
    timers.run_all()
    assert gnome.withdrawn == 1


def test_nothing_withdrawn_when_never_shown(tmp_path):
    gnome = FakeGnome("org.freedesktop.DBus.Error.ServiceUnknown")
    welcome, timers, _ = make(tmp_path, gnome)
    welcome.start()
    timers.run_all()
    assert gnome.withdrawn == 0
