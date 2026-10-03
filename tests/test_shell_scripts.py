"""Runs shellcheck over every shell script in the repo. Scripts are found from `git ls-files`
by extension or shebang, not a hand-kept list, so a new script is covered automatically.
Replaces the three separate shellcheck tests that used to live in test_ci_files.py,
test_install_scripts.py and test_maintainer_scripts.py."""

import subprocess
from pathlib import Path

from conftest import require

REPO = Path(__file__).resolve().parent.parent
SHELL_INTERPRETERS = {"sh", "bash", "dash", "ksh", "zsh"}


def is_shell_script(path: Path) -> bool:
    if path.suffix == ".sh":
        return True
    try:
        with open(path, "rb") as f:
            first_line = f.readline().decode("utf-8", "replace").strip()
    except OSError:
        return False
    if not first_line.startswith("#!"):
        return False
    interpreter = Path(first_line.split()[-1]).name
    return interpreter in SHELL_INTERPRETERS


def shell_scripts() -> list[Path]:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO, check=True, capture_output=True, text=True
    ).stdout.split()
    return [REPO / rel for rel in tracked if is_shell_script(REPO / rel)]


SCRIPTS = shell_scripts()


def test_shell_scripts_found():
    # A sanity check on the discovery logic itself: if this ever comes back empty, something
    # is wrong with it (there are over a dozen tracked shell scripts), not with the repo.
    assert SCRIPTS, "no shell scripts found via git ls-files"


def test_shell_scripts_pass_shellcheck():
    require("shellcheck")
    subprocess.run(["shellcheck", *map(str, SCRIPTS)], check=True)
