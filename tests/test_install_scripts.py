"""install.sh and uninstall.sh in a throwaway home, with fake systemctl, gnome-extensions,
gnome-shell, gsettings and fc-list (fixtures and paths() in conftest.py, shared with
tests/test_package.py). GSETTINGS_BACKEND=memory keeps the real dconf untouched."""

import os
import subprocess
from pathlib import Path

import pytest

from conftest import paths

REPO = Path(__file__).resolve().parent.parent
UUID = "emoji-picker@mathewdbutton.github.io"
APP_ID = "local.emojipicker.EmojiPicker"


def test_install_copies_everything_into_the_home_folder(run, home):
    result, calls = run(REPO / "install.sh")
    assert result.returncode == 0, result.stdout + result.stderr
    p = paths(home)
    assert (p["app"] / "gnomoji" / "__main__.py").is_file()
    assert (p["app"] / "gnomoji" / "data" / "emoji.json").is_file()
    assert os.access(p["app"] / "uninstall.sh", os.X_OK)
    for name in ("extension.js", "tapDetector.js", "insertWaiter.js", "metadata.json"):
        assert (p["ext"] / name).is_file(), name
    assert not (p["ext"] / name).is_symlink()
    assert os.access(p["bin"], os.X_OK)
    assert p["desktop"].is_file() and p["icon"].is_file()
    assert "systemctl --user enable gnomoji" in calls
    assert "systemctl --user restart gnomoji" in calls
    assert not list(p["app"].rglob("__pycache__"))


def test_templates_point_at_the_copied_code_with_quotes(run, home):
    run(REPO / "install.sh")
    p, app = paths(home), paths(home)["app"]
    unit = p["unit"].read_text()
    assert f'Environment="PYTHONPATH={app}"' in unit
    assert "ExecStart=/usr/bin/python3 -m gnomoji" in unit
    assert "@APPDIR@" not in unit
    assert f'Exec=env "PYTHONPATH={app}" /usr/bin/python3 -m gnomoji' in p["desktop"].read_text()
    assert f'export PYTHONPATH="{app}"' in p["bin"].read_text()


def test_installed_comments_dont_name_the_app_folder(run, home):
    # The templates' comments mustn't contain the placeholder, or the filled-in files say
    # "# Template: /home/.../gnomoji is the folder...".
    run(REPO / "install.sh")
    app = str(paths(home)["app"])
    for name in ("unit", "bin", "desktop"):
        for line in paths(home)[name].read_text().splitlines():
            if line.startswith("#") and not line.startswith("#!"):
                assert app not in line, (name, line)


def test_installed_launcher_finds_the_code(run, home):
    run(REPO / "install.sh")
    app = paths(home)["app"]
    script = paths(home)["bin"].read_text().replace(
        'exec /usr/bin/python3 -m gnomoji "$@"',
        'exec /usr/bin/python3 -c "import gnomoji.emoji_data as d; print(d.DATA_PATH)"',
    )
    out = subprocess.run(["sh", "-c", script], capture_output=True, text=True, check=True).stdout
    assert out.strip() == str(app / "gnomoji" / "data" / "emoji.json")


def test_reinstall_replaces_old_files(run, home):
    run(REPO / "install.sh")
    p = paths(home)
    (p["app"] / "gnomoji" / "gone_in_new_version.py").write_text("")
    (p["ext"] / "gone.js").write_text("")
    result, _ = run(REPO / "install.sh")
    assert result.returncode == 0
    assert not (p["app"] / "gnomoji" / "gone_in_new_version.py").exists()
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
    assert "systemctl --user disable --now gnomoji" in calls


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


def test_install_refuses_to_run_as_root(run, home, bin_dir):
    (bin_dir / "id").write_text('#!/bin/sh\n[ "$1" = "-u" ] && echo 0 || /usr/bin/id "$@"\n')
    (bin_dir / "id").chmod(0o755)
    result, calls = run(REPO / "install.sh")
    assert result.returncode != 0
    assert "without sudo" in result.stdout + result.stderr
    assert not (home / ".local").exists()
    assert calls == []


@pytest.mark.parametrize("char", ["%", '"', "$", "`", "\\"])
def test_install_refuses_a_data_folder_the_templates_cant_hold(run, home, char):
    data = home / f"odd{char}data"
    result, calls = run(REPO / "install.sh", XDG_DATA_HOME=str(data))
    assert result.returncode != 0
    assert "can't install into" in (result.stdout + result.stderr).lower()
    assert not data.exists()
    assert not any(c.startswith("systemctl") for c in calls)


def test_install_allows_spaces_and_sed_specials_in_the_data_folder(run, home):
    data = home / "my data & | stuff"
    result, _ = run(REPO / "install.sh", XDG_DATA_HOME=str(data))
    assert result.returncode == 0, result.stdout + result.stderr
    unit = (home / ".config" / "systemd" / "user" / "gnomoji.service").read_text()
    assert f'Environment="PYTHONPATH={data / "gnomoji"}"' in unit


def test_update_mentions_logging_out_to_load_the_new_extension(run):
    result, _ = run(REPO / "install.sh", FAKE_EXT_STATE="ACTIVE")
    assert result.returncode == 0
    assert "Done!" in result.stdout
    assert "If this was an update, log out and back in to load the new version." in result.stdout


def test_uninstall_forgets_the_switched_on_marker(run, home):
    # Else a later .deb/.rpm sees the marker and never switches the extension back on.
    state = home / ".local" / "state" / "emoji-picker"
    state.mkdir(parents=True)
    (state / "extension-enabled").write_text("")
    (state / "recent.json").write_text("[]")
    run(REPO / "install.sh")
    result, _ = run(paths(home)["app"] / "uninstall.sh")
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (state / "extension-enabled").exists()
    assert (state / "recent.json").exists()


def uninstaller_with_package_unit(tmp_path: Path, unit: Path) -> Path:
    """uninstall.sh, looking for the package's unit at `unit` instead of /usr/lib."""
    text = (REPO / "uninstall.sh").read_text()
    line = "PACKAGE_UNIT=/usr/lib/systemd/user/gnomoji.service"
    assert line in text
    script = tmp_path / "uninstall-test.sh"
    script.write_text(text.replace(line, f'PACKAGE_UNIT="{unit}"'))
    return script


def test_uninstall_hands_over_to_an_installed_package(run, tmp_path):
    unit = tmp_path / "package.service"
    unit.write_text("")
    _, calls = run(uninstaller_with_package_unit(tmp_path, unit))
    reload, start = "systemctl --user daemon-reload", "systemctl --user start gnomoji"
    assert start in calls
    assert calls.index(reload) < calls.index(start)


def test_uninstall_starts_nothing_without_a_package(run, tmp_path):
    _, calls = run(uninstaller_with_package_unit(tmp_path, tmp_path / "missing.service"))
    assert "systemctl --user start gnomoji" not in calls


def test_uninstall_finishes_without_a_user_bus(run, home):
    run(REPO / "install.sh")
    p = paths(home)
    result, _ = run(p["app"] / "uninstall.sh", FAKE_FAIL="systemctl")
    assert result.returncode == 0, result.stdout + result.stderr
    for name, path in p.items():
        assert not path.exists(), name
    assert "Gnomoji removed." in result.stdout
