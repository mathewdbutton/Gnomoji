import os
import subprocess
import sys
from pathlib import Path

from emoji_picker.extension_setup import enable, enable_once, forget
from emoji_picker.shell import UUID

SRC = Path(__file__).resolve().parent.parent / "src"


class FakeSettings:
    def __init__(self, enabled=(), disabled=()):
        self.lists = {"enabled-extensions": list(enabled), "disabled-extensions": list(disabled)}

    def get_strv(self, key):
        return list(self.lists[key])

    def set_strv(self, key, value):
        self.lists[key] = list(value)


def test_enable_adds_us_and_keeps_the_others():
    s = FakeSettings(enabled=["other@x"])
    enable(s)
    assert s.lists["enabled-extensions"] == ["other@x", UUID]


def test_enable_is_idempotent():
    s = FakeSettings(enabled=[UUID])
    enable(s)
    assert s.lists["enabled-extensions"] == [UUID]


def test_enable_clears_us_from_disabled_which_would_win():
    s = FakeSettings(disabled=["other@x", UUID])
    enable(s)
    assert s.lists["disabled-extensions"] == ["other@x"]


def test_forget_removes_us_from_both_lists():
    s = FakeSettings(enabled=["a@x", UUID], disabled=[UUID, "b@x"])
    forget(s)
    assert s.lists == {"enabled-extensions": ["a@x"], "disabled-extensions": ["b@x"]}


def test_first_start_enables_and_writes_the_marker(tmp_path):
    s, marker = FakeSettings(), tmp_path / "state" / "extension-enabled"
    assert enable_once(s, marker) is True
    assert UUID in s.lists["enabled-extensions"]
    assert marker.exists()


def test_later_starts_leave_a_switched_off_extension_off(tmp_path):
    s, marker = FakeSettings(disabled=[UUID]), tmp_path / "extension-enabled"
    marker.touch()
    assert enable_once(s, marker) is False
    assert s.lists == {"enabled-extensions": [], "disabled-extensions": [UUID]}


def test_upgraders_from_0_2_with_only_the_welcome_marker_still_get_it(tmp_path):
    (tmp_path / "welcomed").touch()  # written by 0.2.x
    s = FakeSettings()
    assert enable_once(s, tmp_path / "extension-enabled") is True
    assert UUID in s.lists["enabled-extensions"]


def test_no_gnome_shell_settings_logs_and_carries_on(tmp_path, caplog):
    assert enable_once(None, tmp_path / "extension-enabled") is True
    assert "GNOME Shell" in caplog.text


def test_unwritable_marker_does_not_raise(tmp_path, caplog):
    blocker = tmp_path / "file"
    blocker.write_text("")
    s = FakeSettings()
    assert enable_once(s, blocker / "extension-enabled") is True
    assert UUID in s.lists["enabled-extensions"]
    assert "extension-enabled" in caplog.text


def test_cli_never_touches_real_settings_and_reports_a_missing_schema(tmp_path):
    # GSETTINGS_BACKEND=memory: nothing reaches the user's dconf. Exit 0 if GNOME Shell's
    # schema is installed (it switched us on in memory), 1 with a message if it isn't (CI).
    env = {**os.environ, "GSETTINGS_BACKEND": "memory", "PYTHONPATH": str(SRC)}
    result = subprocess.run(
        [sys.executable, "-m", "emoji_picker.extension_setup"],
        env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode in (0, 1), result.stderr
    if result.returncode == 1:
        assert "GNOME Shell" in result.stderr
