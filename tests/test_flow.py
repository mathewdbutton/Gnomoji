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

    def set_text(self, text):
        self.log.append(f"set_text {text}")

    def restore(self):
        self.log.append("restore")
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
        "recent 🎉",
        "set_text 🎉",
        "dismiss",
        "after 80",
        "paste",
        "after 300",
        "restore",
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
    assert w.log.count("set_text 🎉") == 1


def test_no_restore_when_disabled():
    w = World(Config(restore_clipboard=False))
    w.flow.pick(POPPER)
    w.run_timer()
    assert w.timers == []
    assert "restore" not in w.log
    assert not w.flow.busy


def test_paste_failure_clears_busy():
    w = World()
    w.paste_error = OSError(19, "No such device")
    w.flow.pick(POPPER)
    w.run_timer()
    assert not w.flow.busy
    assert w.timers == []
