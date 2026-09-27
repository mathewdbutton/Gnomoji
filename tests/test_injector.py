import pytest

import emoji_picker.injector as injector_module
from emoji_picker import linux_input as li
from emoji_picker.injector import Injector

EV = li.EV_KEY
SHIFT, INSERT = li.KEY_LEFTSHIFT, li.KEY_INSERT


class FakeUInput:
    def __init__(self):
        self.log = []

    def write(self, etype, code, value):
        self.log.append((etype, code, value))

    def syn(self):
        self.log.append("syn")


def test_paste_presses_shift_insert_then_releases_in_reverse():
    device = FakeUInput()
    Injector(device=device).paste()
    assert device.log == [
        (EV, SHIFT, 1), "syn",
        (EV, INSERT, 1), "syn",
        (EV, INSERT, 0), "syn",
        (EV, SHIFT, 0), "syn",
    ]  # fmt: skip


def test_uinput_permission_problem_gives_helpful_error(monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError(13, "Permission denied: '/dev/uinput'")

    monkeypatch.setattr(injector_module, "VirtualKeyboard", denied)
    with pytest.raises(PermissionError, match=r"/dev/uinput.*\./install\.sh"):
        Injector()
