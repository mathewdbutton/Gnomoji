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
    result = subprocess.run(
        [str(BUILD), str(out)], cwd=cwd, capture_output=True, text=True, check=False
    )
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
    apt_packages = re.search(
        r"^APT_PACKAGES=\((.*)\)$", install_sh, re.MULTILINE
    ).group(1).split()
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
    assert "ConditionUser=!@system" in text


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
