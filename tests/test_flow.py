from emoji_picker.config import Config
from emoji_picker.emoji_data import Emoji
from emoji_picker.flow import PasteFlow

POPPER = Emoji("🎉", "party popper", "Activities", ())


class World:
    """Fakes for every collaborator, logging calls to one shared list."""

    def __init__(self, config=None):
        if config is None:
            config = Config()
        self.log, self.timers, self.visible = [], [], False
        self.paste_error = None
        self.on_read = None
        self.flow = PasteFlow(self, self, self, self, config, self.schedule)

    # window
    def get_visible(self):
        return self.visible

    def show_picker(self):
        self.visible = True
        self.log.append("show")

    def dismiss(self):
        self.visible = False
        self.log.append("dismiss")

    # clipboard keeper
    def save(self):
        self.log.append("save")

    def claim(self, emoji, decoy):
        self.log.append(f"claim {emoji} decoy={decoy}")

    def arm(self, on_read=None):
        self.log.append("arm")
        self.on_read = on_read

    def release(self):
        self.log.append("release")
        return True

    # injector
    def paste(self):
        if self.paste_error:
            raise self.paste_error
        self.log.append("paste")

    # recents
    def add(self, char):
        self.log.append(f"recent {char}")

    # scheduler
    def schedule(self, ms, fn):
        self.timers.append((ms, fn))

    def run_timer(self):
        ms, fn = self.timers.pop(0)
        self.log.append(f"after {ms}")
        fn()


def test_toggle_shows_then_dismisses():
    w = World()
    w.flow.toggle()
    w.flow.toggle()
    assert w.log == ["show", "dismiss"]


def test_on_focused_saves_clipboard():
    w = World()
    w.flow.on_focused()
    assert w.log == ["save"]


def test_pick_runs_full_sequence_with_configured_delays():
    w = World()
    w.visible = True
    w.flow.pick(POPPER)
    w.run_timer()
    w.run_timer()
    assert w.log == [
        "claim 🎉 decoy=True",
        "recent 🎉",
        "dismiss",
        "after 80",
        "arm",
        "paste",
        "after 300",
        "release",
    ]
    assert not w.flow.busy


def test_toggle_ignored_while_pasting():
    w = World()
    w.flow.pick(POPPER)
    w.flow.toggle()  # during paste delay
    w.run_timer()
    w.flow.toggle()  # during restore delay
    assert "show" not in w.log
    w.run_timer()
    w.flow.toggle()  # finished: works again
    assert w.log[-1] == "show"


def test_second_pick_while_busy_is_ignored():
    w = World()
    w.flow.pick(POPPER)
    w.flow.pick(POPPER)
    assert w.log.count("claim 🎉 decoy=True") == 1


def test_no_restore_when_disabled():
    w = World(Config(restore_clipboard=False))
    w.flow.pick(POPPER)
    assert w.log[0] == "claim 🎉 decoy=False"
    w.run_timer()
    assert w.timers == []
    assert "release" not in w.log
    assert w.log[-2] == "arm"  # arm() ran too (harmless: already serving the emoji)
    assert w.log[-1] == "paste"
    assert not w.flow.busy


def test_pick_resets_busy_and_reraises_when_claim_raises():
    w = World()

    def boom(emoji, decoy):
        raise ValueError("boom")

    w.claim = boom
    try:
        w.flow.pick(POPPER)
        raised = False
    except ValueError:
        raised = True
    assert raised
    assert not w.flow.busy


def test_paste_failure_clears_busy():
    w = World()
    w.paste_error = OSError(19, "No such device")
    w.flow.pick(POPPER)
    w.run_timer()
    assert not w.flow.busy
    assert w.timers == []
    w.on_read()  # the user pastes the leftover emoji by hand later
    assert w.timers == []
    assert "release" not in w.log


def test_unexpected_paste_error_also_clears_busy():
    w = World()
    w.paste_error = ValueError("closed device")
    w.flow.pick(POPPER)
    w.run_timer()
    assert not w.flow.busy
    assert w.timers == []


def test_release_follows_the_apps_read_instead_of_waiting_the_full_delay():
    w = World()
    w.flow.pick(POPPER)
    w.run_timer()  # paste delay: arm + paste, fallback scheduled
    w.on_read()  # the target app reads the emoji
    assert [ms for ms, _ in w.timers] == [300, 50]
    _, fn = w.timers.pop(1)
    fn()
    assert w.log[-1] == "release"
    assert not w.flow.busy
    w.run_timer()  # the 300 ms fallback now does nothing
    assert w.log.count("release") == 1


def test_each_read_restarts_the_grace_period():
    w = World()
    w.flow.pick(POPPER)
    w.run_timer()
    fallback = w.timers.pop(0)[1]
    w.on_read()
    first = w.timers.pop(0)[1]
    w.on_read()  # a second read, e.g. the editor after the paste event
    second = w.timers.pop(0)[1]
    first()
    fallback()  # a read supersedes the fallback too
    assert "release" not in w.log
    second()
    assert w.log.count("release") == 1
    assert not w.flow.busy


def test_late_read_after_fallback_release_does_nothing():
    w = World()
    w.flow.pick(POPPER)
    w.run_timer()
    w.run_timer()  # fallback releases: nothing read it
    w.on_read()  # a late read (served by our old provider)
    assert w.timers == []
    assert w.log.count("release") == 1


def test_stale_fallback_does_not_release_a_later_pick():
    w = World()
    w.flow.pick(POPPER)
    w.run_timer()
    w.on_read()
    fallback = w.timers.pop(0)[1]
    w.timers.pop(0)[1]()  # early release
    w.flow.pick(POPPER)  # a second pick starts
    w.run_timer()  # its paste
    fallback()  # the first pick's fallback fires late
    assert w.log.count("release") == 1
    assert w.flow.busy


def test_no_read_callback_when_restore_disabled():
    w = World(Config(restore_clipboard=False))
    w.flow.pick(POPPER)
    w.run_timer()
    assert w.on_read is None


def test_release_after_read_uses_configured_delay():
    w = World(Config(release_after_read_ms=120))
    w.flow.pick(POPPER)
    w.run_timer()
    w.on_read()
    assert [ms for ms, _ in w.timers] == [300, 120]


def test_set_config_applies_to_next_pick():
    w = World()
    w.flow.set_config(Config(paste_delay_ms=150))
    w.flow.pick(POPPER)
    assert [ms for ms, _ in w.timers] == [150]


def test_config_change_mid_paste_uses_pick_time_config():
    w = World()
    w.flow.pick(POPPER)
    w.flow.set_config(Config(restore_clipboard=False, restore_delay_ms=999))
    w.run_timer()
    assert w.on_read is not None  # armed with a read callback, as restore was on at pick time
    w.run_timer()
    assert w.log[-2:] == ["after 300", "release"]
    assert not w.flow.busy
