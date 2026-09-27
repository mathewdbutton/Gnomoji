# Emoji Picker .deb Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an installable `emoji-picker_<version>_all.deb` that friends double-click in App
Center, with CI that builds it on a `v*` tag and attaches it to a draft GitHub Release.

**Architecture:** Packaging lives in a new `packaging/` folder: maintainer scripts (`deb/`), a
launcher, a build script that assembles the package from `git archive HEAD`, and a smoke test
used by CI. The app code doesn't change; the existing service and desktop templates are filled in
by the build script. Tests run the maintainer scripts against fake `systemctl`/`loginctl`/`udevadm`
and inspect a real built `.deb` with `dpkg-deb`.

**Tech Stack:** POSIX sh (maintainer scripts), bash (build and smoke test), `dpkg-deb`, pytest,
GitHub Actions (`ubuntu-24.04`, `gh`).

**Spec:** `docs/superpowers/specs/2026-09-27-deb-package-design.md`. Read it before starting.
Also read the repo's `CLAUDE.md`.

## Global Constraints

- Package name `emoji-picker`, file `emoji-picker_<version>_all.deb`, `Architecture: all`.
- Version comes only from `pyproject.toml` `[project] version`.
- `Depends: python3 (>= 3.11), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, fonts-noto-color-emoji`
  (the same apt list as `APT_PACKAGES` in `install.sh`).
- Maintainer: `Mathew Button <mat@pushbutton.xyz>` (the identity already on public commits).
  Homepage: `https://github.com/mathewdbutton/emoji-picker`.
- Licence MIT, `Copyright (c) 2026 Mathew Button`.
- Install paths exactly as the spec's "Package contents" table.
- The application code in `src/emoji_picker/` does not change.
- Runtime is `/usr/bin/python3` plus distro packages only. No pip packages.
- Maintainer scripts never touch home directories. Session and `--global` steps are best-effort:
  they never make the script exit non-zero.
- The package contains only committed files (`git archive HEAD`).
- **Staging:** always `git add` explicit paths, never `git add -A` / `git add .`. The user
  test-pastes emoji into open repo files; unexpected emoji in a tracked file are test pastes. Leave
  them alone and don't commit them.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Lint: `uv run ruff check` must stay clean (line length 100).

## Review Focus

1. **Building with the user's default umask 002** must not produce group-writable files in the
   package. The build forces modes, and Task 2 tests that no packaged file is group- or
   world-writable.
2. **Uncommitted edits and untracked files** (test pastes, `CLAUDE.local.md`) must never reach the
   package. Task 2 builds from a dirty clone and checks.
3. **Installing with no desktop session, a stopped user manager, or a session that refuses the
   restart** must still install successfully and say the picker will start at next log-in. Task 1
   tests each of these.
4. **Upgrades** must not stop or disable the picker (`prerm upgrade` is a no-op) and must restart
   it with the new version (`postinst configure <old-version>`). Task 1 tests both.
5. **`Depends` drifting from `install.sh`'s package list** would make the two install routes
   disagree. Task 2 tests that they match.

---

### Task 1: Maintainer scripts and launcher

**Files:**
- Create: `packaging/deb/postinst`, `packaging/deb/prerm`, `packaging/deb/postrm` (mode 755)
- Create: `packaging/emoji-picker` (mode 755)
- Test: `tests/test_maintainer_scripts.py`

**Interfaces:**
- Consumes: nothing.
- Produces: the three maintainer scripts and the launcher, which Task 2 copies into the package
  as `DEBIAN/postinst`, `DEBIAN/prerm`, `DEBIAN/postrm` and `usr/bin/emoji-picker`. The
  `test_scripts_pass_shellcheck` test checks every file under `packaging/` except
  `deb/control`, so it also covers the scripts Tasks 2 and 3 add.

dpkg calls `postinst configure <old-version-or-empty>`, `prerm remove` / `prerm upgrade <new>`,
and `postrm remove|purge|upgrade ...`. The scripts find running user managers with
`loginctl list-users --no-legend` (columns: `UID USER LINGER STATE`), skip users whose
`user@<uid>.service` isn't active, and act on each with `systemctl --user --machine=<user>@.host`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_maintainer_scripts.py`:

```python
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
            env=env, capture_output=True, text=True,
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
    result, calls = run("postinst", "configure", "", fail="restart")
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
    assert "systemctl --global disable emoji-picker.service" in calls


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
    result, calls = run("postrm", "remove", fail="udevadm")
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
    result = subprocess.run(["shellcheck", *map(str, scripts)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_maintainer_scripts.py -q`
Expected: FAIL. The scripts don't exist (`sh: 0: cannot open .../postinst`, and `FileNotFoundError`
for the launcher). `test_scripts_pass_shellcheck` is skipped if shellcheck isn't installed. The
user can install it with `sudo apt install shellcheck` in their own terminal; CI always has it.

- [ ] **Step 3: Write the maintainer scripts and launcher**

`packaging/deb/postinst`:

```sh
#!/bin/sh
# Runs as root after the package is unpacked, on install and on upgrade.
# Only unpacking can fail the install: the steps below are best-effort, and a failure prints a
# line saying what happens instead.
set -e

if [ "$1" = configure ]; then
    # Let the person at the screen read keyboards and use uinput now, with no log-out.
    udevadm control --reload || true
    udevadm trigger --subsystem-match=input --subsystem-match=misc --action=change || true
    udevadm settle || true

    systemctl --global enable emoji-picker.service \
        || echo "emoji-picker: couldn't enable it for all users. Each user can run: systemctl --user enable --now emoji-picker"

    # Start it (on upgrade: swap in the new version) in every running user session.
    loginctl list-users --no-legend 2>/dev/null | while read -r uid user _; do
        systemctl --quiet is-active "user@$uid.service" 2>/dev/null || continue
        if ! { systemctl --user --machine="$user@.host" daemon-reload \
               && systemctl --user --machine="$user@.host" restart emoji-picker.service; }; then
            echo "emoji-picker: couldn't start it for $user; it will start at their next log-in."
        fi
    done
fi

exit 0
```

`packaging/deb/prerm`:

```sh
#!/bin/sh
# Runs as root before the package's files are removed. On upgrade it does nothing: postinst
# restarts the picker with the new version instead.
set -e

if [ "$1" = remove ]; then
    loginctl list-users --no-legend 2>/dev/null | while read -r uid user _; do
        systemctl --quiet is-active "user@$uid.service" 2>/dev/null || continue
        systemctl --user --machine="$user@.host" stop emoji-picker.service || true
    done
    systemctl --global disable emoji-picker.service || true
fi

exit 0
```

`packaging/deb/postrm`:

```sh
#!/bin/sh
# Runs as root after the package's files are removed. Reloading udev drops the rule's keyboard
# access for devices from now on; access already granted ends at the next log-in.
set -e

case "$1" in
    remove|purge)
        udevadm control --reload || true
        udevadm trigger --subsystem-match=input --subsystem-match=misc --action=change || true
        ;;
esac

exit 0
```

`packaging/emoji-picker`:

```sh
#!/bin/sh
# Run the emoji picker. If it's already running, this opens or closes it instead.
exec /usr/bin/python3 -m emoji_picker "$@"
```

Then: `chmod 755 packaging/deb/postinst packaging/deb/prerm packaging/deb/postrm packaging/emoji-picker`

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_maintainer_scripts.py -q && uv run ruff check`
Expected: all pass (shellcheck test skipped if not installed); ruff clean.

- [ ] **Step 5: Commit**

```bash
git add packaging/deb/postinst packaging/deb/prerm packaging/deb/postrm packaging/emoji-picker \
    tests/test_maintainer_scripts.py
git commit -m "Package scripts: enable for everyone, start in running sessions

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Licence and build script

**Files:**
- Create: `LICENSE`
- Modify: `pyproject.toml` (add `license = "MIT"` under `[project]`, after `description`)
- Modify: `.gitignore` (add `dist/`)
- Create: `packaging/deb/control` (template)
- Create: `packaging/build-deb.sh` (mode 755)
- Test: `tests/test_package.py`

**Interfaces:**
- Consumes: Task 1's `packaging/deb/{postinst,prerm,postrm}` and `packaging/emoji-picker`. The
  existing templates `systemd/emoji-picker.service` (has a `# Template: ... @SRC@ ...` comment
  line and `Environment=PYTHONPATH=@SRC@`) and `desktop/local.emojipicker.EmojiPicker.desktop`
  (has `Exec=env PYTHONPATH=@SRC@ /usr/bin/python3 -m emoji_picker`).
- Produces: `packaging/build-deb.sh [OUT_DIR]`. Run from inside a git repo, it builds from that
  repo's `HEAD` and takes its packaging files (`deb/`, `emoji-picker`) from its own folder. It
  writes `OUT_DIR/emoji-picker_<version>_all.deb` (default `OUT_DIR`: `<repo>/dist`) and prints
  the path on stdout. Tasks 3 and 5 rely on this.

**Commit LICENSE first.** The build uses `git archive HEAD`, so `LICENSE` must be committed before
the package tests can pass.

- [ ] **Step 1: Add the licence and commit it**

`LICENSE`:

```
MIT License

Copyright (c) 2026 Mathew Button

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

In `pyproject.toml`, add the line `license = "MIT"` after `description = ...`. In `.gitignore`, add
a line `dist/`.

Run: `uv run pytest -q` (still passes; `uv` accepts the licence field).

```bash
git add LICENSE pyproject.toml .gitignore
git commit -m "License the project under MIT

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: Write the failing package tests**

Create `tests/test_package.py`:

```python
"""Build the .deb and check what's inside it."""

import gzip
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BUILD = REPO / "packaging" / "build-deb.sh"
APP_ID = "local.emojipicker.EmojiPicker"
PKG = "usr/lib/python3/dist-packages/emoji_picker"
SERVICE = "usr/lib/systemd/user/emoji-picker.service"
DESKTOP = f"usr/share/applications/{APP_ID}.desktop"
DOC = "usr/share/doc/emoji-picker"

EXPECTED_FILES = [
    f"{PKG}/__main__.py",
    f"{PKG}/data/emoji.json",
    f"{PKG}/data/fonts.conf",
    "usr/bin/emoji-picker",
    SERVICE,
    DESKTOP,
    f"usr/share/icons/hicolor/scalable/apps/{APP_ID}.svg",
    "usr/lib/udev/rules.d/70-emoji-picker.rules",
    f"{DOC}/copyright",
    f"{DOC}/changelog.gz",
]
UNWANTED = re.compile(
    r"(^|/)(tests|docs|tools|spike|packaging|\.superpowers|__pycache__)(/|$)|CLAUDE|\.pyc$"
)

pytestmark = pytest.mark.skipif(
    not (shutil.which("dpkg-deb") and shutil.which("git")), reason="needs dpkg-deb and git"
)


def build(out: Path, cwd: Path = REPO) -> Path:
    result = subprocess.run([str(BUILD), str(out)], cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    (deb,) = out.glob("emoji-picker_*_all.deb")
    assert result.stdout.strip() == str(deb)
    return deb


def extract(deb: Path, dest: Path) -> Path:
    subprocess.run(["dpkg-deb", "-x", str(deb), str(dest)], check=True)
    subprocess.run(["dpkg-deb", "-e", str(deb), str(dest / "DEBIAN")], check=True)
    return dest


def field(deb: Path, name: str) -> str:
    return subprocess.run(
        ["dpkg-deb", "-f", str(deb), name], check=True, capture_output=True, text=True
    ).stdout.strip()


def pyproject_version() -> str:
    with open(REPO / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


@pytest.fixture(scope="module")
def deb(tmp_path_factory):
    return build(tmp_path_factory.mktemp("dist"))


@pytest.fixture(scope="module")
def root(deb, tmp_path_factory):
    return extract(deb, tmp_path_factory.mktemp("root"))


def test_name_and_fields(deb):
    version = pyproject_version()
    assert deb.name == f"emoji-picker_{version}_all.deb"
    assert field(deb, "Package") == "emoji-picker"
    assert field(deb, "Version") == version
    assert field(deb, "Architecture") == "all"
    assert field(deb, "Maintainer") == "Mathew Button <mat@pushbutton.xyz>"
    assert int(field(deb, "Installed-Size")) > 0


def test_depends_match_install_sh(deb):
    install_sh = (REPO / "install.sh").read_text()
    apt_packages = re.search(r"^APT_PACKAGES=\((.*)\)$", install_sh, re.M).group(1).split()
    depends = [d.strip() for d in field(deb, "Depends").split(",")]
    assert depends[0] == "python3 (>= 3.11)"
    assert sorted(depends[1:]) == sorted(apt_packages)


def test_files_are_where_the_spec_says(root):
    for rel in EXPECTED_FILES:
        assert (root / rel).is_file(), rel


def test_whole_python_package_is_included(root):
    tracked = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "HEAD", "src/emoji_picker"],
        cwd=REPO, check=True, capture_output=True, text=True,
    ).stdout.split()
    for path in tracked:
        rel = Path(path).relative_to("src/emoji_picker")
        assert (root / PKG / rel).is_file(), path


def test_launcher_and_maintainer_scripts_are_executable(root):
    for rel in ["usr/bin/emoji-picker", "DEBIAN/postinst", "DEBIAN/prerm", "DEBIAN/postrm"]:
        assert (root / rel).stat().st_mode & 0o777 == 0o755, rel


def test_files_are_root_owned_and_not_group_writable(deb):
    listing = subprocess.run(
        ["dpkg-deb", "-c", str(deb)], check=True, capture_output=True, text=True
    ).stdout.splitlines()
    for line in listing:
        mode, owner = line.split()[:2]
        assert owner == "root/root", line
        assert mode[5] != "w" and mode[8] != "w", line


def test_service_runs_the_installed_package(root):
    text = (root / SERVICE).read_text()
    assert "@SRC@" not in text
    assert "PYTHONPATH" not in text
    assert "ExecStart=/usr/bin/python3 -m emoji_picker\n" in text
    assert "WantedBy=graphical-session.target" in text


def test_desktop_entry_runs_the_installed_package(root):
    text = (root / DESKTOP).read_text()
    assert "@SRC@" not in text
    assert "PYTHONPATH" not in text
    assert "Exec=/usr/bin/python3 -m emoji_picker\n" in text
    assert "NoDisplay=true" in text


def test_nothing_unwanted(root):
    for path in root.rglob("*"):
        rel = path.relative_to(root).as_posix()
        assert not UNWANTED.search(rel), rel


def test_copyright_covers_the_code_icon_and_data(root):
    text = (root / DOC / "copyright").read_text()
    assert "Copyright (c) 2026 Mathew Button" in text
    assert "MIT License" in text
    assert "Apache" in text  # the Noto Emoji icon
    assert "Unicode" in text  # emoji.json, from Unicode and CLDR data


def test_changelog_names_the_version(root):
    text = gzip.decompress((root / DOC / "changelog.gz").read_bytes()).decode()
    assert text.startswith(f"emoji-picker ({pyproject_version()}) ")


def test_builds_only_committed_files(tmp_path):
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(REPO), str(clone)], check=True)
    (clone / "src/emoji_picker/leak.py").write_text("LEAK = 1\n")
    with open(clone / "src/emoji_picker/__init__.py", "a") as f:
        f.write("# uncommitted edit\n")
    root = extract(build(tmp_path / "dist", cwd=clone), tmp_path / "root")
    assert not (root / PKG / "leak.py").exists()
    assert "uncommitted edit" not in (root / PKG / "__init__.py").read_text()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_package.py -q`
Expected: FAIL. `build-deb.sh` doesn't exist, so every test errors in `build`.

- [ ] **Step 4: Write the control template**

`packaging/deb/control` (placeholders are filled in by the build script):

```
Package: emoji-picker
Version: @VERSION@
Architecture: all
Maintainer: Mathew Button <mat@pushbutton.xyz>
Installed-Size: @INSTALLED_SIZE@
Depends: python3 (>= 3.11), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, fonts-noto-color-emoji
Section: utils
Priority: optional
Homepage: https://github.com/mathewdbutton/emoji-picker
Description: Double-tap right Shift emoji picker for GNOME on Wayland
 Double-tap right Shift in any text field to open an emoji picker. Search or
 browse, press Enter, and the emoji is pasted in. The text on your clipboard
 is put back afterwards.
```

- [ ] **Step 5: Write the build script**

`packaging/build-deb.sh`:

```bash
#!/usr/bin/env bash
# Build emoji-picker_<version>_all.deb from the last commit of the git repo you're in.
# Usage: packaging/build-deb.sh [OUT_DIR]      (default OUT_DIR: <repo>/dist)
# Only committed files go in: uncommitted edits and untracked files never do. The packaging
# files (deb/, emoji-picker) come from this script's own folder. Prints the .deb's path.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(git rev-parse --show-toplevel)"
OUT="${1:-$REPO/dist}"
APP_ID=local.emojipicker.EmojiPicker
umask 022

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
src="$work/src"
root="$work/root"
mkdir "$src"
git -C "$REPO" archive HEAD | tar -x -C "$src"

version="$(python3 -c 'import sys, tomllib
print(tomllib.load(open(sys.argv[1], "rb"))["project"]["version"])' "$src/pyproject.toml")"
maintainer="$(sed -n 's/^Maintainer: //p' "$HERE/deb/control")"

# The code, with its data files. Python finds it here without PYTHONPATH.
install -d "$root/usr/lib/python3/dist-packages"
cp -r "$src/src/emoji_picker" "$root/usr/lib/python3/dist-packages/"
install -D -m 755 "$HERE/emoji-picker" "$root/usr/bin/emoji-picker"

# install.sh's templates. Here the code is on Python's normal path, so the service drops its
# PYTHONPATH line (and the comment about it) and the desktop entry runs python3 directly.
install -d "$root/usr/lib/systemd/user" "$root/usr/share/applications"
sed '/@SRC@/d' "$src/systemd/emoji-picker.service" \
    > "$root/usr/lib/systemd/user/emoji-picker.service"
sed 's|^Exec=env PYTHONPATH=@SRC@ |Exec=|' "$src/desktop/$APP_ID.desktop" \
    > "$root/usr/share/applications/$APP_ID.desktop"
install -D -m 644 "$src/desktop/$APP_ID.svg" "$root/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
install -D -m 644 "$src/udev/70-emoji-picker.rules" "$root/usr/lib/udev/rules.d/70-emoji-picker.rules"

doc="$root/usr/share/doc/emoji-picker"
install -d "$doc"
{
    echo "emoji-picker: https://github.com/mathewdbutton/emoji-picker"
    echo
    echo "The icon is the pinching hand emoji from Noto Emoji, Copyright Google LLC, under the"
    echo "Apache License 2.0 (/usr/share/common-licenses/Apache-2.0)."
    echo "The emoji names and keywords come from Unicode's emoji data and CLDR, under the"
    echo "Unicode License v3 (https://www.unicode.org/license.txt)."
    echo
    echo "Everything else:"
    echo
    cat "$src/LICENSE"
} > "$doc/copyright"
printf 'emoji-picker (%s) unstable; urgency=medium\n\n  * Release %s: https://github.com/mathewdbutton/emoji-picker/releases\n\n -- %s  %s\n' \
    "$version" "$version" "$maintainer" "$(git -C "$REPO" log -1 --format=%cD)" \
    | gzip -9n > "$doc/changelog.gz"

# Normalise modes: the user's umask or the source files mustn't decide them.
find "$root" -type d -exec chmod 755 {} +
find "$root" -type f -exec chmod 644 {} +
chmod 755 "$root/usr/bin/emoji-picker"

install -d "$root/DEBIAN"
sed -e "s/@VERSION@/$version/" -e "s/@INSTALLED_SIZE@/$(du -sk "$root/usr" | cut -f1)/" \
    "$HERE/deb/control" > "$root/DEBIAN/control"
chmod 644 "$root/DEBIAN/control"
install -m 755 "$HERE/deb/postinst" "$HERE/deb/prerm" "$HERE/deb/postrm" "$root/DEBIAN/"

mkdir -p "$OUT"
deb="$(cd "$OUT" && pwd)/emoji-picker_${version}_all.deb"
dpkg-deb --root-owner-group -Zxz --build "$root" "$deb" >/dev/null
echo "$deb"
```

Then: `chmod 755 packaging/build-deb.sh`

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest -q && uv run ruff check`
Expected: all pass, ruff clean. The packaging files don't need to be committed for this: the
tests call the working-tree script (`BUILD`), which takes `deb/` and the launcher from its own
folder and only the app files from `HEAD` (in `test_builds_only_committed_files`, the clone's
`HEAD`).

Also run `packaging/build-deb.sh` once by hand. It should print `.../dist/emoji-picker_0.1.0_all.deb`.
Check `git status --short` shows nothing from `dist/`.

- [ ] **Step 7: Commit**

```bash
git add packaging/deb/control packaging/build-deb.sh tests/test_package.py
git commit -m "Build a .deb from the last commit: packaging/build-deb.sh

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: CI: build, smoke-test and draft a release

**Files:**
- Create: `packaging/smoke-test.sh` (mode 755)
- Create: `.github/workflows/package.yml`

**Interfaces:**
- Consumes: `packaging/build-deb.sh` (Task 2) and the package tests (Tasks 1 and 2).
- Produces: `packaging/smoke-test.sh <path-to-.deb>`, which needs sudo and apt. It exits
  non-zero with a message naming what's wrong.

The smoke test can't run in pytest: it installs system-wide. It runs in CI on a throwaway runner.
Don't run it on the user's machine (it would replace their installed picker). Its correctness is
checked by shellcheck locally (`test_scripts_pass_shellcheck` picks it up) and by the first CI run.

- [ ] **Step 1: Write the smoke test**

`packaging/smoke-test.sh`:

```bash
#!/usr/bin/env bash
# Install a built .deb, check it, remove it, and check it's gone. For CI: it needs sudo and
# changes the system, so run it on a throwaway machine.
# Usage: packaging/smoke-test.sh dist/emoji-picker_<version>_all.deb
set -euo pipefail

deb="$(realpath "$1")"
WANTS=/etc/systemd/user/graphical-session.target.wants/emoji-picker.service
fail() { echo "✗ $*" >&2; exit 1; }

sudo apt-get install -y "$deb"

files="$(mktemp)"
dpkg -L emoji-picker > "$files"
for f in /usr/bin/emoji-picker \
         /usr/lib/systemd/user/emoji-picker.service \
         /usr/lib/udev/rules.d/70-emoji-picker.rules \
         /usr/share/applications/local.emojipicker.EmojiPicker.desktop \
         /usr/share/icons/hicolor/scalable/apps/local.emojipicker.EmojiPicker.svg; do
    [ -f "$f" ] || fail "missing $f"
done
[ -L "$WANTS" ] || fail "not enabled for all users ($WANTS)"
# From /, so nothing but the installed package can be imported.
(cd / && /usr/bin/python3 -c 'import emoji_picker.emoji_data as d; assert d.DATA_PATH.is_file()') \
    || fail "the installed package doesn't import or is missing its data"

sudo apt-get remove -y emoji-picker

while read -r f; do
    if [ -f "$f" ] || [ -L "$f" ]; then fail "left behind: $f"; fi
done < "$files"
[ ! -e "$WANTS" ] || fail "still enabled for all users ($WANTS)"
echo "✓ Smoke test passed"
```

Then: `chmod 755 packaging/smoke-test.sh`

- [ ] **Step 2: Write the workflow**

`.github/workflows/package.yml`:

```yaml
# Builds and checks the .deb on pull requests. On a v* tag it also creates a draft GitHub
# Release with the .deb attached; publish it by hand after trying it.
name: Package

on:
  pull_request:
  push:
    tags: ["v*"]

permissions:
  contents: write

jobs:
  deb:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4

      - name: Check the tag matches pyproject.toml
        if: startsWith(github.ref, 'refs/tags/v')
        run: |
          version="$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"
          if [ "$GITHUB_REF_NAME" != "v$version" ]; then
            echo "::error::Tag $GITHUB_REF_NAME doesn't match version $version in pyproject.toml"
            exit 1
          fi

      - name: Install test tools
        run: sudo apt-get update && sudo apt-get install -y shellcheck python3-pytest

      - name: Package tests
        run: python3 -m pytest -q -p no:cacheprovider tests/test_maintainer_scripts.py tests/test_package.py

      - name: Build
        run: packaging/build-deb.sh

      - name: Smoke test
        run: packaging/smoke-test.sh dist/emoji-picker_*_all.deb

      - name: Draft release
        if: startsWith(github.ref, 'refs/tags/v')
        env:
          GH_TOKEN: ${{ github.token }}
        run: gh release create "$GITHUB_REF_NAME" dist/emoji-picker_*_all.deb --draft --title "$GITHUB_REF_NAME" --generate-notes
```

The package tests use the system's pytest (Ubuntu 24.04 has 7.4, which reads `pythonpath` from
`pyproject.toml`). They don't import GTK, so the rest of the suite, which needs a display,
isn't run here.

- [ ] **Step 3: Check locally**

Run: `uv run pytest -q && uv run ruff check`
Expected: all pass. If shellcheck is installed, `test_scripts_pass_shellcheck` now covers
`smoke-test.sh` and `build-deb.sh`.

Run: `python3 -c 'import yaml,sys; yaml.safe_load(open(".github/workflows/package.yml"))' && echo ok`
Expected: `ok` (`python3-yaml` ships with Ubuntu desktop; skip this check if it's missing).

The workflow's first real run happens when the branch is pushed and a PR opened, which the user
decides on at the end (see Task 5).

- [ ] **Step 4: Commit**

```bash
git add packaging/smoke-test.sh .github/workflows/package.yml
git commit -m "CI: build and smoke-test the .deb; draft a release on v* tags

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Docs

**Files:**
- Modify: `README.md` (sections "Install", "Uninstall", "Troubleshooting" first bullets, "Development")
- Modify: `UNINSTALL.md` (new section before "What gets added")
- Modify: `CLAUDE.md` ("Read these before changing anything", "Commands", new "Releasing" section)
- Modify: `desktop/README.md` (one line)

**Interfaces:**
- Consumes: paths and commands from Tasks 1–3.
- Produces: nothing code depends on.

- [ ] **Step 1: README.md**

Replace the whole `## Install` section (from `## Install` up to, not including, `## Use`) with:

````markdown
## Install

Download `emoji-picker_<version>_all.deb` from the
[latest release](https://github.com/mathewdbutton/emoji-picker/releases/latest) and double-click
it. App Center opens; click **Install**. It warns that the package comes from outside the Ubuntu
store: that's expected for a download like this.

Within a few seconds a notification says the picker is ready. No log-out needed.

What the package sets up:

- **Packages:** Python GTK 4, libadwaita and a colour emoji font, if missing. A standard Ubuntu
  GNOME desktop already has them.
- **Keyboard access:** a udev rule lets the person logged in at the screen read keyboards (to spot
  the right-Shift double-tap) and create a virtual keyboard (to send the paste keystroke). Access
  is tied to your active desktop session, like a webcam or sound card: other users and remote
  logins don't get it.
- **The picker** as a user service, turned on for every account on the computer. It starts when
  you log in.

Prefer a terminal? `sudo apt install ./emoji-picker_<version>_all.deb`

**Updating:** download the newer `.deb` and install it the same way. The running picker switches to
the new version.

### From source

Clone the repo wherever you like, then run `./install.sh`. It checks what's missing, lists what it
needs sudo for, and asks once before doing it (say no and it prints the commands instead). The
service then runs from the cloned folder, so keep it where it is (or re-run `./install.sh` after
moving it). Don't also install the `.deb`: the clone's service takes precedence over it.

To try it without installing, run `PYTHONPATH=src /usr/bin/python3 -m emoji_picker` from the repo
(Ctrl+C to stop).
````

In the "Use" table, change the last row's first cell from `` `python3 -m emoji_picker` again `` to
`` `emoji-picker` (or `python3 -m emoji_picker`) again ``.

Replace the whole `## Uninstall` section with:

````markdown
## Uninstall

**Installed from the `.deb`:** remove "Emoji Picker" in App Center, or
`sudo apt remove emoji-picker`. Your recents and config stay in your home folder; see
[UNINSTALL.md](UNINSTALL.md) to delete them.

**Installed from source:**

```bash
./uninstall.sh           # remove the service, keep recents, config and keyboard access
./uninstall.sh --purge   # also delete recents and config, and offer to remove the udev rule
```

[UNINSTALL.md](UNINSTALL.md) lists everything the picker adds to your machine.
````

In "Troubleshooting", replace the "Nothing happens on double-tap" bullet with:

```markdown
- Nothing happens on double-tap: check the logs for a permissions message. Log out and back in,
  or reboot, so keyboard access applies. From source, re-run `./install.sh`, which checks it.
```

In "Development", after the `uv run pytest && uv run ruff check` line add:

```bash
packaging/build-deb.sh                      # build dist/emoji-picker_<version>_all.deb from HEAD
```

- [ ] **Step 2: UNINSTALL.md**

Insert before `## What gets added`:

````markdown
## If you installed the .deb

Remove "Emoji Picker" in App Center, or `sudo apt remove emoji-picker`. That removes everything
the package installed:

| What | Where |
|---|---|
| The code | `/usr/lib/python3/dist-packages/emoji_picker/` |
| Launcher | `/usr/bin/emoji-picker` |
| User service, turned on for all users | `/usr/lib/systemd/user/emoji-picker.service` and `/etc/systemd/user/graphical-session.target.wants/emoji-picker.service` |
| Desktop entry and icon | `/usr/share/applications/local.emojipicker.EmojiPicker.desktop`, `/usr/share/icons/hicolor/scalable/apps/local.emojipicker.EmojiPicker.svg` |
| Keyboard access rule | `/usr/lib/udev/rules.d/70-emoji-picker.rules` (access already granted ends at your next log-in) |
| Package docs | `/usr/share/doc/emoji-picker/` |

Packages never touch home folders, so each user's recents and config stay. To delete them:

```bash
rm -rf ~/.local/state/emoji-picker ~/.config/emoji-picker
```

Packages installed as dependencies (GTK, libadwaita, the emoji font) stay too. Usually keep them:
other apps depend on them.

The rest of this file is about installs from source (`./install.sh`).
````

- [ ] **Step 3: CLAUDE.md**

In "Read these before changing anything", replace the `UNINSTALL.md` bullet and the "User-facing
files" bullet with:

```markdown
- `UNINSTALL.md` lists everything the project puts outside the repo, both from `install.sh` and
  from the `.deb`. **Any change that installs something outside the repo, by either route, must
  update it in the same commit.**
- `README.md` covers install, use, config and troubleshooting.
- **User-facing files stay general**: `README.md`, `UNINSTALL.md`, `install.sh`, `uninstall.sh`,
  `udev/`, `systemd/`, `desktop/` and `packaging/`. People install from them on fresh machines.
- `docs/superpowers/specs/2026-09-27-deb-package-design.md` is the design for the `.deb`.
```

(The `README.md` line already exists; keep one copy.)

In "Commands", update the test count on the first line to the number `uv run pytest -q` now
reports, and add:

```bash
packaging/build-deb.sh                           # .deb from HEAD into dist/ (uncommitted edits aren't in it)
```

Replace the paragraph after the Commands block with:

```markdown
Runtime uses **only** `/usr/bin/python3` plus distro packages. `.venv` (uv, `--system-site-packages`)
is for pytest/ruff only. No pip packages at runtime. A source install (`./install.sh`) runs from
the working tree, so the checked-out branch is what runs. A `.deb` install runs the packaged copy.
```

Add a new section after "Commands":

````markdown
## Packaging and releasing

`packaging/build-deb.sh` builds `emoji-picker_<version>_all.deb` from `git archive HEAD`. The
version comes from `pyproject.toml`. The service and desktop entry are `install.sh`'s templates
with `@SRC@` lines removed, so there's one source for each. The maintainer scripts in
`packaging/deb/` enable the user service globally and restart it in every running user manager
(`systemctl --user --machine=<user>@.host`). Every step past unpacking is best-effort and never
fails the install; `prerm upgrade` is a no-op. `tests/test_maintainer_scripts.py` runs them
against fake `systemctl`/`loginctl`/`udevadm`.

CI (`.github/workflows/package.yml`) runs the package tests, builds, and install/remove
smoke-tests (`packaging/smoke-test.sh`) on every PR. To release:

1. Bump `version` in `pyproject.toml`, commit, and merge to `main`.
2. `git tag v<version> && git push origin v<version>`. CI checks the tag matches and creates a
   **draft** release with the `.deb`.
3. Download the `.deb` from the draft, install it, try it, then publish the release.
````

- [ ] **Step 4: desktop/README.md**

Replace the first paragraph with:

```markdown
`install.sh` copies these into `~/.local/share/`, and the `.deb` installs them under
`/usr/share/`, so GNOME shows the picker's name and icon.
```

- [ ] **Step 5: Check and commit**

Run: `uv run pytest -q && uv run ruff check`
Expected: all pass. Read the changed sections once in full for anything personal (names of
the user's machine, their remapper, their home path). Only general wording is allowed in these
files.

```bash
git add README.md UNINSTALL.md CLAUDE.md desktop/README.md
git commit -m "docs: install from the .deb; release steps

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Hands-on acceptance (with the user)

This task needs the user at their desktop. Give them one step at a time, in its own message,
and wait for the result before the next. Commands they run in this session start with `!`.
Anything with `sudo` must go in their own terminal: `!` can't prompt for a password. Don't open
windows on their screen without saying so first.

**Files:** none changed, unless a step fails. Then stop, use superpowers:systematic-debugging, and
fix with a test first.

- [ ] **Step 1: Build**

Run: `packaging/build-deb.sh`. Expected: prints `.../dist/emoji-picker_0.1.0_all.deb`.

- [ ] **Step 2: Switch the user's machine to the package**

Ask the user to run, in this session:

```
! ./uninstall.sh && rm -f ~/.local/state/emoji-picker/welcomed
```

The second part makes the "ready" welcome show again. Then ask them to open the repo's `dist/`
folder in Files, double-click the `.deb`, and install it in App Center.

Pass when:
- the "Emoji Picker is ready" notification appears within ~10 s with no log-out;
- `! systemctl --user status emoji-picker --no-pager` shows it loaded from
  `/usr/lib/systemd/user/emoji-picker.service` and active;
- a double-tap and pick inserts an emoji.

If other udev rules also grant keyboard access on the test machine (see `CLAUDE.local.md`), this
step doesn't prove the packaged rule. Step 6 does.

- [ ] **Step 3: Log-in start**

The user logs out and back in, then double-taps. Pass: the picker opens.

- [ ] **Step 4: Upgrade**

Build a test package with a higher version from a throwaway clone (nothing in the repo changes):

```bash
repo="$PWD" && tmp="$(mktemp -d)" && git clone -q "$repo" "$tmp/c" \
  && sed -i 's/^version = "0.1.0"/version = "0.1.1"/' "$tmp/c/pyproject.toml" \
  && git -C "$tmp/c" -c user.name=test -c user.email=test@example.invalid commit -qam "test bump" \
  && (cd "$tmp/c" && "$repo/packaging/build-deb.sh" "$repo/dist") && rm -rf "$tmp"
```

Note the start time first: `! systemctl --user show emoji-picker -p ExecMainStartTimestamp`.
The user installs `dist/emoji-picker_0.1.1_all.deb` via App Center. Pass: `ExecMainStartTimestamp`
is later than before, `dpkg -s emoji-picker | grep Version` says `0.1.1`, and a pick works.

- [ ] **Step 5: Remove, then reinstall**

The user removes Emoji Picker in App Center. Pass: `! systemctl --user is-active emoji-picker`
says `inactive` (or the unit isn't found), and `! ls /usr/lib/systemd/user/emoji-picker.service`
says "No such file". Then they install `dist/emoji-picker_0.1.0_all.deb` again. It will be their
daily picker until the first real release. Delete `dist/emoji-picker_0.1.1_all.deb`.

- [ ] **Step 6 (optional, the user decides): fresh account, packaged rule only**

This proves the packaged rule grants access on its own. Any other rule that grants keyboard
access must be moved aside first. That includes a leftover `/etc/udev/rules.d/70-emoji-picker.rules`
from `install.sh`: it has the same name, so it overrides the packaged one. Take the other rules'
paths from `CLAUDE.local.md`'s machine notes. The user runs, in their own terminal:

```bash
sudo mkdir -p /root/rules-aside && sudo mv <each other rule> /etc/udev/rules.d/70-emoji-picker.rules /root/rules-aside/
sudo udevadm control --reload && sudo udevadm trigger --subsystem-match=input --subsystem-match=misc --action=change
sudo useradd -m -s /bin/bash pkgtest && sudo passwd pkgtest
```

They log in as `pkgtest` (the package is already enabled for all users) and double-tap in a text
field. Pass: the welcome appears and a pick works. Then they log back in as themselves and undo:

```bash
sudo userdel -r pkgtest
sudo mv /root/rules-aside/* /etc/udev/rules.d/ && sudo rmdir /root/rules-aside
sudo udevadm control --reload && sudo udevadm trigger --subsystem-match=input --subsystem-match=misc --action=change
```

- [ ] **Step 7: Record results and hand off**

Record each step's pass/fail in `CLAUDE.local.md` (Status section). Then use
superpowers:finishing-a-development-branch. Pushing the branch and opening a PR gives the
workflow its first real run. Ask the user before pushing. The first release (tag `v0.1.0`)
happens after merge, following CLAUDE.md's "Packaging and releasing" steps.
