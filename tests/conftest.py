"""Shared fixtures: a throwaway home with fake systemctl, gnome-extensions, gnome-shell,
gsettings and fc-list, used by tests/test_install_scripts.py and tests/test_package.py.
GSETTINGS_BACKEND=memory keeps the real dconf untouched."""

import subprocess
from pathlib import Path

import pytest

UUID = "emoji-picker@mathewdbutton.github.io"
APP_ID = "local.emojipicker.EmojiPicker"

# FAKE_FAIL: a program name that fails every call (e.g. systemctl with no user bus).
FAKE = r"""#!/bin/sh
echo "$(basename "$0") $*" >> "$FAKE_LOG"
[ "$(basename "$0")" = "${FAKE_FAIL:-}" ] && exit 1
case "$(basename "$0") $*" in
    "gnome-shell --version") echo "GNOME Shell 46.0" ;;
    "fc-list Noto Color Emoji") echo "/usr/share/fonts/NotoColorEmoji.ttf: Noto Color Emoji:style=Regular" ;;
    "gsettings get org.gnome.mutter locate-pointer-key") echo "'Shift_R'" ;;
    "gnome-extensions info "*) echo "  State: ${FAKE_EXT_STATE:-INACTIVE}" ;;
esac
exit 0
"""


@pytest.fixture
def home(tmp_path):
    # A space in the path, so quoting mistakes show up.
    home = tmp_path / "home dir"
    home.mkdir()
    return home


@pytest.fixture
def bin_dir(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("systemctl", "gnome-extensions", "gnome-shell", "gsettings", "fc-list"):
        (bin_dir / name).write_text(FAKE)
        (bin_dir / name).chmod(0o755)
    return bin_dir


@pytest.fixture
def run(tmp_path, home, bin_dir):
    log = tmp_path / "calls.log"

    def run(script: Path, *args, **extra_env):
        log.write_text("")
        env = {
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "HOME": str(home),
            "FAKE_LOG": str(log),
            "GSETTINGS_BACKEND": "memory",
            "XDG_SESSION_TYPE": "wayland",
            **extra_env,
        }
        result = subprocess.run(
            ["bash", str(script), *args], env=env, capture_output=True, text=True,
            check=False, stdin=subprocess.DEVNULL,
        )
        return result, log.read_text().splitlines()

    return run


def paths(home: Path) -> dict[str, Path]:
    data = home / ".local" / "share"
    return {
        "app": data / "gnomoji",
        "ext": data / "gnome-shell" / "extensions" / UUID,
        "unit": home / ".config" / "systemd" / "user" / "gnomoji.service",
        "bin": home / ".local" / "bin" / "gnomoji",
        "desktop": data / "applications" / f"{APP_ID}.desktop",
        "icon": data / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg",
    }
