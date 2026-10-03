"""dev-setup.sh against fake gjs/git/dpkg-deb/rpmbuild/rpm/shellcheck/fc-list/fc-match/
apt-get/sudo/uv (style borrowed from conftest.py's bin_dir/run fixtures), so no real package
install, sudo, or uv run ever happens. Runs the real script in place (it only ever touches
this repo's own .venv through the faked `uv`), never against the installed system."""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "dev-setup.sh"
BASH = shutil.which("bash") or "/usr/bin/bash"

# Everything dev-setup.sh looks for on PATH, besides the hardcoded /usr/bin/python3. Present
# by default; a test removes one to simulate it being missing. fc-list answers the one query
# the script makes of it; everything else just logs its call and exits 0.
ALL_TOOLS = ("gjs", "git", "dpkg-deb", "rpmbuild", "rpm", "shellcheck", "fc-list", "fc-match",
             "apt-get", "sudo", "uv")
FAKE = r"""#!/bin/sh
echo "$(basename "$0") $*" >> "$FAKE_LOG"
case "$(basename "$0") $*" in
    "fc-list Noto Color Emoji") echo "/usr/share/fonts/NotoColorEmoji.ttf: Noto Color Emoji:style=Regular" ;;
esac
exit 0
"""
# Reports uid 0, for the "refuses to run as root" test; falls back to the real id otherwise.
ID_ROOT = '#!/bin/sh\n[ "$1" = "-u" ] && echo 0 || exec /usr/bin/id "$@"\n'


@pytest.fixture
def bin_dir(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ALL_TOOLS:
        fake = bin_dir / name
        fake.write_text(FAKE)
        fake.chmod(0o755)
    return bin_dir


@pytest.fixture
def run(tmp_path, bin_dir):
    log = tmp_path / "calls.log"

    def run(missing=(), overrides=None):
        for name in missing:
            (bin_dir / name).unlink(missing_ok=True)
        for name, content in (overrides or {}).items():
            fake = bin_dir / name
            fake.write_text(content)
            fake.chmod(0o755)
        log.write_text("")
        env = {
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "HOME": str(tmp_path / "home"),
            "FAKE_LOG": str(log),
        }
        result = subprocess.run(
            [BASH, str(SCRIPT)], env=env, capture_output=True, text=True,
            check=False, stdin=subprocess.DEVNULL,
            # stdin=DEVNULL alone doesn't detach the controlling terminal: without this, a
            # real terminal running this test would have dev-setup.sh's `read ... < /dev/tty`
            # block on the user's keyboard (the prompt itself is swallowed by capture_output).
            # A new session has no controlling tty, so /dev/tty reliably fails to open instead.
            start_new_session=True,
        )
        return result, log.read_text().splitlines()

    return run


def test_dev_setup_refuses_to_run_as_root(run):
    result, calls = run(overrides={"id": ID_ROOT})
    assert result.returncode != 0
    assert "without sudo" in result.stdout + result.stderr
    assert calls == []


def test_dev_setup_skips_the_install_step_when_everything_is_present(run):
    result, calls = run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Missing:" not in result.stdout
    assert not any(c.startswith(("apt-get", "sudo")) for c in calls)
    # Reached the venv/test step, using the faked uv:
    assert "uv sync" in calls
    assert "uv run pytest -q" in calls
    assert "uv run ruff check" in calls
    assert "Ready!" in result.stdout


def test_dev_setup_prints_the_install_command_and_exits_without_a_terminal(run):
    # subprocess.run gives the child no controlling terminal, so /dev/tty can't be read here
    # (confirmed: `bash -c 'read -r x < /dev/tty'` fails the same way in this environment) —
    # exactly the "no terminal to ask on" case the script is meant to handle.
    result, calls = run(missing=("shellcheck",))
    assert result.returncode == 1
    output = result.stdout + result.stderr
    assert "sudo apt-get install -y" in output
    assert "shellcheck" in output
    assert not any(c.startswith(("apt-get", "sudo")) for c in calls)


def test_dev_setup_only_lists_the_missing_packages(run):
    result, calls = run(missing=("shellcheck",))
    output = result.stdout + result.stderr
    assert "shellcheck" in output
    for present in ("gjs", "rpm", "fonts-noto-color-emoji", "dpkg"):
        assert present not in output
    assert not any(c.startswith(("apt-get", "sudo")) for c in calls)


def test_dev_setup_tells_you_to_install_uv_yourself(run):
    result, calls = run(missing=("uv",))
    assert result.returncode == 1
    output = result.stdout + result.stderr
    assert "curl -LsSf https://astral.sh/uv/install.sh | sh" in output
    assert not any(c.startswith(("apt-get", "sudo")) for c in calls)
    assert not any(c.startswith("uv") for c in calls)
