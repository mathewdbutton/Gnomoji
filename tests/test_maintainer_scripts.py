"""The shared enable/disable scripts run against fake systemctl and loginctl; the .deb and .rpm scriptlets are checked as text."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

PACKAGING = Path(__file__).resolve().parent.parent / "packaging"

# Logs each call, fails any call containing $FAKE_FAIL, and answers the queries the scripts make:
# alice (uid 1000) has a running user manager with an active graphical session; bob (uid 1001)
# has no running user manager; carol (uid 1002) has a running user manager but no active
# graphical session (e.g. lingering, or logged in over SSH only).
FAKE = r"""#!/bin/sh
cmd="$(basename "$0") $*"
echo "$cmd" >> "$FAKE_LOG"
if [ -n "$FAKE_FAIL" ] && [ "${cmd#*"$FAKE_FAIL"}" != "$cmd" ]; then exit 1; fi
case "$cmd" in
    "loginctl list-users --no-legend") printf ' 1000 alice no active\n 1001 bob   no closing\n 1002 carol no active\n' ;;
    "systemctl --quiet is-active user@1000.service") exit 0 ;;
    "systemctl --quiet is-active user@1002.service") exit 0 ;;
    "systemctl --quiet is-active user@"*) exit 1 ;;
    "systemctl --user --machine=alice@.host --quiet is-active graphical-session.target") exit 0 ;;
    "systemctl --user --machine="*"--quiet is-active graphical-session.target") exit 1 ;;
esac
exit 0
"""

ALICE = "systemctl --user --machine=alice@.host"
SPEC = PACKAGING / "rpm" / "gnomoji.spec"


@pytest.fixture
def run(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("systemctl", "loginctl"):
        fake = bin_dir / name
        fake.write_text(FAKE)
        fake.chmod(0o755)
    log = tmp_path / "calls.log"

    def run(script, fail=""):
        log.write_text("")
        env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
               "FAKE_LOG": str(log), "FAKE_FAIL": fail}
        result = subprocess.run(
            ["sh", str(PACKAGING / script)], env=env, capture_output=True, text=True, check=False
        )
        return result, log.read_text().splitlines()

    return run


def test_enable_turns_it_on_for_everyone_and_starts_it_in_desktop_sessions(run):
    result, calls = run("enable-for-everyone")
    assert result.returncode == 0, result.stderr
    assert "systemctl --global enable gnomoji.service" in calls
    reload = calls.index(f"{ALICE} daemon-reload")
    assert calls[reload + 1] == f"{ALICE} restart gnomoji.service"
    assert not any("bob@" in c or "carol@.host restart" in c for c in calls)


def test_enable_succeeds_when_everything_fails(run):
    for fail in ("--global enable", "restart", "loginctl"):
        result, _ = run("enable-for-everyone", fail=fail)
        assert result.returncode == 0, (fail, result.stderr)


def test_enable_never_touches_udev(run):
    _, calls = run("enable-for-everyone")
    assert not any(c.startswith("udevadm") for c in calls)


def test_disable_stops_it_in_running_sessions_and_turns_it_off(run):
    result, calls = run("disable-for-everyone")
    assert result.returncode == 0, result.stderr
    assert f"{ALICE} stop gnomoji.service" in calls
    assert "systemctl --global disable gnomoji.service" in calls


def test_disable_succeeds_when_everything_fails(run):
    for fail in ("stop", "--global disable"):
        result, _ = run("disable-for-everyone", fail=fail)
        assert result.returncode == 0, (fail, result.stderr)


def test_deb_postinst_compiles_then_enables_on_configure_only():
    text = (PACKAGING / "deb" / "postinst").read_text()
    assert 'if [ "$1" = configure ]; then' in text
    assert text.index("py3compile /usr/lib/gnomoji") < text.index(
        "sh /usr/lib/gnomoji/enable-for-everyone"
    )


def test_deb_prerm_cleans_bytecode_and_disables_only_on_remove():
    text = (PACKAGING / "deb" / "prerm").read_text()
    assert "remove|upgrade) py3clean /usr/lib/gnomoji" in text
    assert 'if [ "$1" = remove ]; then' in text
    assert "sh /usr/lib/gnomoji/disable-for-everyone" in text


def test_rpm_scriptlets_use_the_same_scripts():
    text = SPEC.read_text()
    post = text.split("%post", 1)[1].split("%preun", 1)[0]
    preun = text.split("%preun", 1)[1].split("%files", 1)[0]
    assert "python3 -m compileall -q /usr/lib/gnomoji" in post
    assert "sh /usr/lib/gnomoji/enable-for-everyone" in post
    assert 'if [ "$1" -eq 0 ]; then' in preun
    assert "sh /usr/lib/gnomoji/disable-for-everyone" in preun
    assert "__pycache__" in preun


def test_no_udev_anywhere_in_packaging():
    # The smoke tests (Task 9) mention udev only to check that no rule gets installed.
    for path in PACKAGING.rglob("*"):
        if path.is_file() and not path.name.startswith("smoke-test"):
            assert "udev" not in path.read_text(), path


def test_launcher_template_runs_the_package():
    text = (PACKAGING / "gnomoji").read_text()
    assert 'export PYTHONPATH="@APPDIR@"' in text
    assert 'exec /usr/bin/python3 -m gnomoji "$@"' in text


def test_scripts_are_executable():
    for rel in ("enable-for-everyone", "disable-for-everyone", "deb/postinst", "deb/prerm",
                "gnomoji", "build.sh"):
        assert (PACKAGING / rel).stat().st_mode & 0o111, rel


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck not installed")
def test_scripts_pass_shellcheck():
    scripts = ["enable-for-everyone", "disable-for-everyone", "deb/postinst", "deb/prerm",
               "gnomoji", "build.sh"]
    subprocess.run(["shellcheck", *(str(PACKAGING / s) for s in scripts)], check=True)
