"""The package's install/remove scripts, run against fake systemctl, loginctl and udevadm."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

PACKAGING = Path(__file__).resolve().parent.parent / "packaging"

# Logs each call, fails any call containing $FAKE_FAIL, and answers the queries the scripts make:
# alice (uid 1000) has a running user manager, bob (uid 1001) doesn't.
FAKE = r"""#!/bin/sh
cmd="$(basename "$0") $*"
echo "$cmd" >> "$FAKE_LOG"
if [ -n "$FAKE_FAIL" ] && [ "${cmd#*"$FAKE_FAIL"}" != "$cmd" ]; then exit 1; fi
case "$cmd" in
    "loginctl list-users --no-legend") printf ' 1000 alice no active\n 1001 bob   no closing\n' ;;
    "systemctl --quiet is-active user@1000.service") exit 0 ;;
    "systemctl --quiet is-active user@"*) exit 1 ;;
esac
exit 0
"""

UDEV = [
    "udevadm control --reload",
    "udevadm trigger --subsystem-match=input --subsystem-match=misc --action=change",
]
ALICE = "systemctl --user --machine=alice@.host"


@pytest.fixture
def run(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("systemctl", "loginctl", "udevadm"):
        fake = bin_dir / name
        fake.write_text(FAKE)
        fake.chmod(0o755)
    log = tmp_path / "calls.log"

    def run(script, *args, fail=""):
        log.write_text("")
        env = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "FAKE_LOG": str(log),
            "FAKE_FAIL": fail,
        }
        result = subprocess.run(
            ["sh", str(PACKAGING / "deb" / script), *args],
            env=env, capture_output=True, text=True, check=False,
        )
        return result, log.read_text().splitlines()

    return run


# --- postinst -------------------------------------------------------------------------------


def test_install_grants_access_enables_and_starts_in_running_sessions(run):
    result, calls = run("postinst", "configure", "")
    assert result.returncode == 0, result.stderr
    assert calls[:3] == [*UDEV, "udevadm settle"]
    assert "systemctl --global enable emoji-picker.service" in calls
    reload = calls.index(f"{ALICE} daemon-reload")
    assert calls[reload + 1] == f"{ALICE} restart emoji-picker.service"
    assert not any("bob@" in call for call in calls)


def test_upgrade_restarts_with_the_new_version(run):
    result, calls = run("postinst", "configure", "0.1.0")
    assert result.returncode == 0, result.stderr
    assert f"{ALICE} restart emoji-picker.service" in calls


def test_install_succeeds_when_a_session_refuses(run):
    result, _ = run("postinst", "configure", "", fail="restart")
    assert result.returncode == 0, result.stderr
    assert "alice" in result.stdout
    assert "next log-in" in result.stdout


def test_install_succeeds_without_any_sessions(run):
    result, calls = run("postinst", "configure", "", fail="loginctl")
    assert result.returncode == 0, result.stderr
    assert "systemctl --global enable emoji-picker.service" in calls
    assert not any("restart" in call for call in calls)


def test_install_succeeds_when_enabling_for_everyone_fails(run):
    result, calls = run("postinst", "configure", "", fail="--global enable")
    assert result.returncode == 0, result.stderr
    assert f"{ALICE} restart emoji-picker.service" in calls


def test_install_succeeds_when_udev_fails(run):
    result, calls = run("postinst", "configure", "", fail="udevadm")
    assert result.returncode == 0, result.stderr
    assert "systemctl --global enable emoji-picker.service" in calls


@pytest.mark.parametrize("action", ["abort-upgrade", "abort-remove"])
def test_postinst_ignores_other_actions(run, action):
    result, calls = run("postinst", action, "0.1.0")
    assert result.returncode == 0, result.stderr
    assert calls == []


# --- prerm ----------------------------------------------------------------------------------


def test_remove_stops_in_running_sessions_and_disables(run):
    result, calls = run("prerm", "remove")
    assert result.returncode == 0, result.stderr
    assert f"{ALICE} stop emoji-picker.service" in calls
    assert calls[-1] == "systemctl --global disable emoji-picker.service"
    assert not any("bob@" in call for call in calls)


def test_remove_succeeds_when_stopping_fails(run):
    result, calls = run("prerm", "remove", fail="stop")
    assert result.returncode == 0, result.stderr
    assert "alice" in result.stdout
    assert "systemctl --global disable emoji-picker.service" in calls


def test_remove_succeeds_when_disabling_fails(run):
    result, calls = run("prerm", "remove", fail="--global disable")
    assert result.returncode == 0, result.stderr
    assert "all users" in result.stdout
    assert f"{ALICE} stop emoji-picker.service" in calls


def test_upgrade_leaves_the_running_picker_alone(run):
    result, calls = run("prerm", "upgrade", "0.2.0")
    assert result.returncode == 0, result.stderr
    assert calls == []


# --- postrm ---------------------------------------------------------------------------------


@pytest.mark.parametrize("action", ["remove", "purge"])
def test_removal_reloads_udev(run, action):
    result, calls = run("postrm", action)
    assert result.returncode == 0, result.stderr
    assert calls == UDEV


def test_removal_succeeds_when_udev_fails(run):
    result, _ = run("postrm", "remove", fail="udevadm")
    assert result.returncode == 0, result.stderr


def test_postrm_upgrade_does_nothing(run):
    result, calls = run("postrm", "upgrade", "0.2.0")
    assert result.returncode == 0, result.stderr
    assert calls == []


# --- all packaging scripts ------------------------------------------------------------------


def test_launcher_runs_the_installed_package():
    text = (PACKAGING / "emoji-picker").read_text()
    assert 'exec /usr/bin/python3 -m emoji_picker "$@"' in text


def test_scripts_are_executable():
    for script in (PACKAGING / "emoji-picker", *(PACKAGING / "deb").glob("post*"),
                   PACKAGING / "deb" / "prerm"):
        assert os.access(script, os.X_OK), script


@pytest.mark.skipif(not shutil.which("shellcheck"), reason="shellcheck not installed")
def test_scripts_pass_shellcheck():
    scripts = sorted(
        p for p in PACKAGING.rglob("*") if p.is_file() and p.name != "control"
    )
    result = subprocess.run(
        ["shellcheck", *map(str, scripts)], capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout
