"""Build the .deb, .rpm and tarball and check what's inside them."""

import gzip
import json
import os
import re
import shutil
import subprocess
import tarfile
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BUILD = REPO / "packaging" / "build.sh"
APP_ID = "local.emojipicker.EmojiPicker"
UUID = "emoji-picker@mathewdbutton.github.io"
APP = "usr/lib/gnomoji"
EXT = f"usr/share/gnome-shell/extensions/{UUID}"
SERVICE = "usr/lib/systemd/user/gnomoji.service"
DESKTOP = f"usr/share/applications/{APP_ID}.desktop"
DOC = "usr/share/doc/gnomoji"

INSTALLED_FILES = [
    f"{APP}/emoji_picker/__main__.py",
    f"{APP}/emoji_picker/data/emoji.json",
    f"{APP}/emoji_picker/data/fonts.conf",
    f"{APP}/enable-for-everyone",
    f"{APP}/disable-for-everyone",
    f"{EXT}/extension.js",
    f"{EXT}/tapDetector.js",
    f"{EXT}/insertWaiter.js",
    f"{EXT}/metadata.json",
    "usr/bin/gnomoji",
    SERVICE,
    DESKTOP,
    f"usr/share/icons/hicolor/scalable/apps/{APP_ID}.svg",
    f"{DOC}/copyright",
]
UNWANTED = re.compile(
    r"(^|/)(tests|docs|tools|spike|packaging|udev|\.superpowers|__pycache__)(/|$)|CLAUDE|\.pyc$"
)

needs_deb = pytest.mark.skipif(
    not (shutil.which("dpkg-deb") and shutil.which("git")), reason="needs dpkg-deb and git"
)
needs_rpm = pytest.mark.skipif(
    not (shutil.which("rpmbuild") and shutil.which("rpm")), reason="needs rpmbuild and rpm"
)


def version() -> str:
    with open(REPO / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def package_names(var: str) -> list[str]:
    line = re.search(rf"^{var}=\((.*)\)$", (REPO / "install.sh").read_text(), re.MULTILINE)
    return sorted(line.group(1).split())


def build(out: Path, cwd: Path = REPO, env: dict[str, str] | None = None) -> list[Path]:
    result = subprocess.run([str(BUILD), str(out)], cwd=cwd, capture_output=True, text=True,
                            check=False, env=env)
    assert result.returncode == 0, result.stderr
    return [Path(line) for line in result.stdout.split()]


@pytest.fixture(scope="module")
def dist(tmp_path_factory):
    out = tmp_path_factory.mktemp("dist")
    build(out)
    return out


@pytest.fixture(scope="module")
def deb(dist):
    return dist / f"gnomoji_{version()}_all.deb"


@pytest.fixture(scope="module")
def deb_root(deb, tmp_path_factory):
    dest = tmp_path_factory.mktemp("deb")
    subprocess.run(["dpkg-deb", "-x", str(deb), str(dest)], check=True)
    subprocess.run(["dpkg-deb", "-e", str(deb), str(dest / "DEBIAN")], check=True)
    return dest


def deb_field(deb: Path, name: str) -> str:
    return subprocess.run(["dpkg-deb", "-f", str(deb), name], check=True, capture_output=True,
                          text=True).stdout.strip()


# --- .deb ----------------------------------------------------------------------------


@needs_deb
def test_deb_name_and_fields(deb):
    assert deb.is_file()
    assert deb_field(deb, "Package") == "gnomoji"
    assert deb_field(deb, "Version") == version()
    assert deb_field(deb, "Architecture") == "all"
    assert deb_field(deb, "Maintainer") == "Mathew Button <mat@pushbutton.xyz>"
    assert "clipboard" not in deb_field(deb, "Description").replace("never touches the clipboard", "")


@needs_deb
def test_deb_depends_match_install_sh(deb):
    depends = [d.strip() for d in deb_field(deb, "Depends").split(",")]
    assert depends[0] == "python3 (>= 3.11)"
    assert "gnome-shell (>= 46)" in depends
    assert sorted(re.sub(r" \(.*\)", "", d) for d in depends[1:]) == package_names("APT_PACKAGES")


@needs_deb
def test_deb_files_are_where_the_spec_says(deb_root):
    for rel in INSTALLED_FILES:
        assert (deb_root / rel).is_file(), rel
    assert (deb_root / DOC / "changelog.gz").is_file()


@needs_deb
def test_deb_ships_no_udev_rule(deb_root):
    assert not list(deb_root.rglob("*.rules"))


@needs_deb
def test_deb_whole_python_package_is_included(deb_root):
    tracked = subprocess.run(["git", "ls-tree", "-r", "--name-only", "HEAD", "src/emoji_picker"],
                             cwd=REPO, check=True, capture_output=True, text=True).stdout.split()
    for path in tracked:
        rel = Path(path).relative_to("src")
        assert (deb_root / APP / rel).is_file(), path


@needs_deb
def test_deb_service_desktop_and_launcher_use_the_app_folder(deb_root):
    service = (deb_root / SERVICE).read_text()
    assert f'Environment="PYTHONPATH=/{APP}"' in service
    assert "ExecStart=/usr/bin/python3 -m emoji_picker" in service
    assert "ConditionUser=!@system" in service
    assert f'Exec=env "PYTHONPATH=/{APP}" /usr/bin/python3 -m emoji_picker' in (
        deb_root / DESKTOP).read_text()
    assert f'export PYTHONPATH="/{APP}"' in (deb_root / "usr/bin/gnomoji").read_text()
    for rel in (SERVICE, DESKTOP, "usr/bin/gnomoji"):
        assert "@APPDIR@" not in (deb_root / rel).read_text(), rel


@needs_deb
def test_deb_extension_metadata(deb_root):
    meta = json.loads((deb_root / EXT / "metadata.json").read_text())
    assert meta["uuid"] == UUID
    assert meta["shell-version"] == ["46", "47", "48", "49", "50"]


@needs_deb
def test_deb_modes_and_owners(deb, deb_root):
    for rel in ["usr/bin/gnomoji", f"{APP}/enable-for-everyone", f"{APP}/disable-for-everyone",
                "DEBIAN/postinst", "DEBIAN/prerm"]:
        assert (deb_root / rel).stat().st_mode & 0o777 == 0o755, rel
    listing = subprocess.run(["dpkg-deb", "-c", str(deb)], check=True, capture_output=True,
                             text=True).stdout.splitlines()
    for line in listing:
        mode, owner = line.split()[:2]
        assert owner == "root/root", line
        assert mode[5] != "w" and mode[8] != "w", line


@needs_deb
def test_deb_nothing_unwanted(deb_root):
    for path in deb_root.rglob("*"):
        rel = path.relative_to(deb_root).as_posix()
        if rel.startswith("DEBIAN"):
            continue
        assert not UNWANTED.search(rel.replace(APP, "APP")), rel


@needs_deb
def test_deb_copyright_and_changelog(deb_root):
    text = (deb_root / DOC / "copyright").read_text()
    assert "MIT License" in text and "Apache" in text and "Unicode" in text
    changelog = gzip.decompress((deb_root / DOC / "changelog.gz").read_bytes()).decode()
    assert changelog.startswith(f"gnomoji ({version()}) ")


# --- .rpm ----------------------------------------------------------------------------


def rpm_query(rpm: Path, *args: str) -> str:
    return subprocess.run(["rpm", "-qp", *args, str(rpm)], check=True, capture_output=True,
                          text=True).stdout


@pytest.fixture(scope="module")
def rpm(dist):
    return dist / f"gnomoji-{version()}-1.noarch.rpm"


@needs_rpm
def test_rpm_name_and_version(rpm):
    assert rpm.is_file()
    assert rpm_query(rpm, "--qf", "%{NAME} %{VERSION} %{ARCH}") == f"gnomoji {version()} noarch"


@needs_rpm
def test_rpm_requires_match_install_sh(rpm):
    requires = [r.strip() for r in rpm_query(rpm, "--requires").splitlines()
                if not r.startswith("rpmlib(") and not r.startswith("/bin/sh")]
    assert "python3 >= 3.11" in requires
    assert "gnome-shell >= 46" in requires
    names = sorted({r.split()[0] for r in requires} - {"python3"})
    assert names == package_names("DNF_PACKAGES")


@needs_rpm
def test_rpm_has_the_same_files_as_the_deb(rpm, deb_root):
    rpm_files = {f.lstrip("/") for f in rpm_query(rpm, "--list").split()}
    for rel in INSTALLED_FILES:
        assert rel in rpm_files, rel
    assert not any(f.endswith(".rules") for f in rpm_files)


@needs_rpm
def test_rpm_scripts_enable_and_disable(rpm):
    scripts = rpm_query(rpm, "--scripts")
    assert "/usr/lib/gnomoji/enable-for-everyone" in scripts
    assert "/usr/lib/gnomoji/disable-for-everyone" in scripts


# --- tarball ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tarball(dist):
    return dist / f"gnomoji-{version()}.tar.gz"


def test_tarball_is_a_snapshot_with_the_installer(tarball):
    prefix = f"gnomoji-{version()}/"
    with tarfile.open(tarball) as tar:
        names = tar.getnames()
        install = tar.getmember(prefix + "install.sh")
        assert install.mode & 0o111
    assert all(n.startswith(prefix) or n == prefix.rstrip("/") for n in names)
    for rel in ("install.sh", "uninstall.sh", "extension/metadata.json",
                "src/emoji_picker/__main__.py", "systemd/gnomoji.service", "LICENSE"):
        assert prefix + rel in names, rel
    assert not any("CLAUDE.local" in n for n in names)


# --- all formats -------------------------------------------------------------------------


@needs_deb
def test_builds_only_committed_files(tmp_path):
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(REPO), str(clone)], check=True)
    (clone / "src/emoji_picker/leak.py").write_text("LEAK = 1\n")
    with open(clone / "src/emoji_picker/__init__.py", "a") as f:
        f.write("# uncommitted edit\n")
    paths = build(tmp_path / "dist", cwd=clone)
    deb = next(p for p in paths if p.suffix == ".deb")
    root = tmp_path / "root"
    subprocess.run(["dpkg-deb", "-x", str(deb), str(root)], check=True)
    assert not (root / APP / "emoji_picker/leak.py").exists()
    assert "uncommitted edit" not in (root / APP / "emoji_picker/__init__.py").read_text()
    tar = next(p for p in paths if p.name.endswith(".tar.gz"))
    with tarfile.open(tar) as t:
        assert not any(n.endswith("leak.py") for n in t.getnames())


def test_build_work_folder_ignores_tmpdir():
    # rpmbuild's --define "stage $root" / "_topdir ..." split on spaces, so the work folder
    # mustn't come from a TMPDIR that might have them.
    assert 'work="$(mktemp -d /tmp/gnomoji-build.XXXXXX)"' in BUILD.read_text()


@needs_deb
def test_builds_with_spaces_in_tmpdir(tmp_path):
    tmp = tmp_path / "temp dir"
    tmp.mkdir()
    paths = build(tmp_path / "dist", env={**os.environ, "TMPDIR": str(tmp)})
    assert any(p.suffix == ".deb" for p in paths)


def test_the_v1_spike_is_gone():
    # 0.2's clipboard/uinput probe: wrong for 0.3, and the tarball ships the whole repo.
    assert not (REPO / "spike").exists()
