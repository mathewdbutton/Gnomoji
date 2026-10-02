"""install.sh and uninstall.sh in a throwaway home, with fake systemctl, gnome-extensions,
gnome-shell, gsettings and fc-list. GSETTINGS_BACKEND=memory keeps the real dconf untouched."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
UUID = "emoji-picker@mathewdbutton.github.io"
APP_ID = "local.emojipicker.EmojiPicker"

FAKE = r"""#!/bin/sh
echo "$(basename "$0") $*" >> "$FAKE_LOG"
case "$(basename "$0") $*" in
    "gnome-shell --version") echo "GNOME Shell 46.0" ;;
    "fc-list Noto Color Emoji") echo "/usr/share/fonts/NotoColorEmoji.ttf: Noto Color Emoji:style=Regular" ;;
    "gsettings get org.gnome.mutter locate-pointer-key") echo "'Shift_R'" ;;
    "gnome-extensions info "*) echo "  State: INACTIVE" ;;
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
def run(tmp_path, home):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("systemctl", "gnome-extensions", "gnome-shell", "gsettings", "fc-list"):
        (bin_dir / name).write_text(FAKE)
        (bin_dir / name).chmod(0o755)
    log = tmp_path / "calls.log"

    def run(script: Path, *args):
        log.write_text("")
        env = {
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "HOME": str(home),
            "FAKE_LOG": str(log),
            "GSETTINGS_BACKEND": "memory",
            "XDG_SESSION_TYPE": "wayland",
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
        "app": data / "emoji-picker",
        "ext": data / "gnome-shell" / "extensions" / UUID,
        "unit": home / ".config" / "systemd" / "user" / "emoji-picker.service",
        "bin": home / ".local" / "bin" / "emoji-picker",
        "desktop": data / "applications" / f"{APP_ID}.desktop",
        "icon": data / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg",
    }


def test_install_copies_everything_into_the_home_folder(run, home):
    result, calls = run(REPO / "install.sh")
    assert result.returncode == 0, result.stdout + result.stderr
    p = paths(home)
    assert (p["app"] / "emoji_picker" / "__main__.py").is_file()
    assert (p["app"] / "emoji_picker" / "data" / "emoji.json").is_file()
    assert os.access(p["app"] / "uninstall.sh", os.X_OK)
    for name in ("extension.js", "tapDetector.js", "insertWaiter.js", "metadata.json"):
        assert (p["ext"] / name).is_file(), name
    assert not (p["ext"] / name).is_symlink()
    assert os.access(p["bin"], os.X_OK)
    assert p["desktop"].is_file() and p["icon"].is_file()
    assert "systemctl --user enable emoji-picker" in calls
    assert "systemctl --user restart emoji-picker" in calls
    assert not list(p["app"].rglob("__pycache__"))


def test_templates_point_at_the_copied_code_with_quotes(run, home):
    run(REPO / "install.sh")
    p, app = paths(home), paths(home)["app"]
    unit = p["unit"].read_text()
    assert f'Environment="PYTHONPATH={app}"' in unit
    assert "ExecStart=/usr/bin/python3 -m emoji_picker" in unit
    assert "@APPDIR@" not in unit
    assert f'Exec=env "PYTHONPATH={app}" /usr/bin/python3 -m emoji_picker' in p["desktop"].read_text()
    assert f'export PYTHONPATH="{app}"' in p["bin"].read_text()


def test_installed_launcher_finds_the_code(run, home):
    run(REPO / "install.sh")
    app = paths(home)["app"]
    script = paths(home)["bin"].read_text().replace(
        'exec /usr/bin/python3 -m emoji_picker "$@"',
        'exec /usr/bin/python3 -c "import emoji_picker.emoji_data as d; print(d.DATA_PATH)"',
    )
    out = subprocess.run(["sh", "-c", script], capture_output=True, text=True, check=True).stdout
    assert out.strip() == str(app / "emoji_picker" / "data" / "emoji.json")


def test_reinstall_replaces_old_files(run, home):
    run(REPO / "install.sh")
    p = paths(home)
    (p["app"] / "emoji_picker" / "gone_in_new_version.py").write_text("")
    (p["ext"] / "gone.js").write_text("")
    result, _ = run(REPO / "install.sh")
    assert result.returncode == 0
    assert not (p["app"] / "emoji_picker" / "gone_in_new_version.py").exists()
    assert not (p["ext"] / "gone.js").exists()


def test_install_never_uses_sudo(run):
    _, calls = run(REPO / "install.sh")
    assert not any(c.startswith("sudo") for c in calls)
    assert "sudo " not in (REPO / "install.sh").read_text().replace("sudo apt", "").replace("sudo dnf", "")


def test_install_asks_for_a_log_out_when_the_extension_is_not_running(run):
    result, _ = run(REPO / "install.sh")
    assert "log out and back in once" in result.stdout.lower()


def test_uninstall_removes_everything_and_resets_the_key(run, home):
    run(REPO / "install.sh")
    p = paths(home)
    result, calls = run(p["app"] / "uninstall.sh")
    assert result.returncode == 0, result.stdout + result.stderr
    for name, path in p.items():
        assert not path.exists(), name
    assert f"gnome-extensions disable {UUID}" in calls
    assert "gsettings reset org.gnome.mutter locate-pointer-key" in calls
    assert "systemctl --user disable --now emoji-picker" in calls


def test_uninstall_keeps_state_and_config_unless_purged(run, home):
    state = home / ".local" / "state" / "emoji-picker"
    config = home / ".config" / "emoji-picker"
    for d in (state, config):
        d.mkdir(parents=True)
        (d / "x").write_text("")
    run(REPO / "install.sh")
    run(paths(home)["app"] / "uninstall.sh")
    assert state.exists() and config.exists()
    run(REPO / "install.sh")
    run(paths(home)["app"] / "uninstall.sh", "--purge")
    assert not state.exists() and not config.exists()


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck not installed")
def test_scripts_pass_shellcheck():
    subprocess.run(["shellcheck", str(REPO / "install.sh"), str(REPO / "uninstall.sh")], check=True)
