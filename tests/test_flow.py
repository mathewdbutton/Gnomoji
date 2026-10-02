from emoji_picker.emoji_data import Emoji
from emoji_picker.flow import PickerFlow

POPPER = Emoji("🎉", "party popper", "Activities", ())


class World:
    """Fakes for the window, the Shell link and recents, logging calls to one list."""

    def __init__(self):
        self.log, self.visible = [], False
        self.flow = PickerFlow(self, self, self)

    # window
    def get_visible(self):
        return self.visible

    def show_picker(self):
        self.visible = True
        self.log.append("show")

    def dismiss(self):
        self.visible = False
        self.log.append("dismiss")

    # shell link
    def insert(self, text):
        # The window must already be hidden, or focus can't go back to the app.
        self.log.append(f"insert {text} (visible={self.visible})")

    # recents
    def add(self, char):
        self.log.append(f"recent {char}")


def test_toggle_shows_then_dismisses():
    w = World()
    w.flow.toggle()
    w.flow.toggle()
    assert w.log == ["show", "dismiss"]


def test_pick_records_recent_hides_then_inserts():
    w = World()
    w.flow.toggle()
    w.flow.pick(POPPER)
    assert w.log == ["show", "recent 🎉", "dismiss", "insert 🎉 (visible=False)"]


def test_multi_codepoint_emoji_is_inserted_whole():
    w = World()
    family = Emoji("👨‍👩‍👧", "family: man, woman, girl", "People & Body", ())
    w.flow.pick(family)
    assert w.log[-1] == "insert 👨‍👩‍👧 (visible=False)"
