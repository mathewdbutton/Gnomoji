"""Static checks on the CI workflow and smoke tests (they only run on GitHub)."""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "package.yml"
SMOKE = [REPO / "packaging" / "smoke-test-deb.sh", REPO / "packaging" / "smoke-test-rpm.sh"]


def test_workflow_builds_tests_and_smoke_tests_both_packages():
    text = WORKFLOW.read_text()
    for fragment in (
        "packaging/build.sh",
        "python3 -m pytest",
        "gjs",
        "rpm",
        "packaging/smoke-test-deb.sh",
        "packaging/smoke-test-rpm.sh",
        "fedora:44",
        "--draft",
    ):
        assert fragment in text, fragment


def test_release_attaches_all_three_files():
    text = WORKFLOW.read_text()
    for pattern in ("gnomoji_*_all.deb", "gnomoji-*.noarch.rpm", "gnomoji-*.tar.gz"):
        assert pattern in text, pattern


def test_smoke_tests_check_the_extension_and_no_udev_rule():
    for script in SMOKE:
        text = script.read_text()
        assert "gnome-shell/extensions/emoji-picker@mathewdbutton.github.io/metadata.json" in text
        assert "PYTHONPATH=/usr/lib/gnomoji" in text
        assert "want: no udev rule" in text
        assert script.stat().st_mode & 0o111


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck not installed")
def test_smoke_tests_pass_shellcheck():
    subprocess.run(["shellcheck", *map(str, SMOKE)], check=True)
