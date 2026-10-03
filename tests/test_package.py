"""Build the .deb, .rpm and tarball and check what's inside them."""

import gzip
import json
import os
import re
import subprocess
import tarfile
import tomllib
from pathlib import Path

import pytest

from conftest import paths, require  # bin_dir, home, run fixtures come from conftest.py

REPO = Path(__file__).resolve().parent.parent
BUILD = REPO / "packaging" / "build.sh"
APP_ID = "local.emojipicker.EmojiPicker"
UUID = "emoji-picker@mathewdbutton.github.io"
APP = "usr/lib/gnomoji"
EXT = f"usr/share/gnome-shell/extensions/{UUID}"
SERVICE = "usr/lib/systemd/user/gnomoji.service"
DESKTOP = f"usr/share/applications/{APP_ID}.desktop"
DOC = "usr/share/doc/gnomoji"

# Kept in sync with packaging/build.sh's tarball_paths: what install.sh/uninstall.sh need
# plus user docs, not the whole repo (GitHub's own "Source code" download covers that).
TARBALL_PATHS = [
    "install.sh", "uninstall.sh", "src/gnomoji", "extension", "systemd",
    f"desktop/{APP_ID}.desktop", f"desktop/{APP_ID}.svg",
    "packaging/gnomoji", "README.md", "UNINSTALL.md", "LICENSE",
]

INSTALLED_FILES = [
    f"{APP}/gnomoji/__main__.py",
    f"{APP}/gnomoji/data/emoji.json",
    f"{APP}/gnomoji/data/fonts.conf",
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


def version() -> str:
    with open(REPO / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def package_names(var: str) -> list[str]:
    line = re.search(rf"^{var}=\((.*)\)$", (REPO / "install.sh").read_text(), re.MULTILINE)
    return sorted(line.group(1).split())


def tracked_files(*pathspecs: str) -> list[str]:
    """Committed files under the given pathspecs, per git itself (so the test stays honest)."""
    return subprocess.run(["git", "ls-files", "--", *pathspecs], cwd=REPO, check=True,
                          capture_output=True, text=True).stdout.split()


def build(out: Path, cwd: Path = REPO, env: dict[str, str] | None = None) -> list[Path]:
    result = subprocess.run([str(BUILD), str(out)], cwd=cwd, capture_output=True, text=True,
                            check=False, env=env)
    assert result.returncode == 0, result.stderr
    return [Path(line) for line in result.stdout.split()]


@pytest.fixture(scope="module")
def dist(tmp_path_factory):
    require("dpkg-deb", "git")  # build.sh always builds the .deb, and archives via git
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


def test_deb_name_and_fields(deb):
    assert deb.is_file()
    assert deb_field(deb, "Package") == "gnomoji"
    assert deb_field(deb, "Version") == version()
    assert deb_field(deb, "Architecture") == "all"
    assert deb_field(deb, "Maintainer") == "Mathew Button <mat@pushbutton.xyz>"
    assert "clipboard" not in deb_field(deb, "Description").replace("never touches the clipboard", "")


def test_deb_depends_match_install_sh(deb):
    depends = [d.strip() for d in deb_field(deb, "Depends").split(",")]
    assert depends[0] == "python3 (>= 3.11)"
    assert "gnome-shell (>= 46)" in depends
    assert sorted(re.sub(r" \(.*\)", "", d) for d in depends[1:]) == package_names("APT_PACKAGES")


def test_deb_files_are_where_the_spec_says(deb_root):
    for rel in INSTALLED_FILES:
        assert (deb_root / rel).is_file(), rel
    assert (deb_root / DOC / "changelog.gz").is_file()


def test_deb_ships_no_udev_rule(deb_root):
    assert not list(deb_root.rglob("*.rules"))


def test_deb_whole_python_package_is_included(deb_root):
    tracked = subprocess.run(["git", "ls-tree", "-r", "--name-only", "HEAD", "src/gnomoji"],
                             cwd=REPO, check=True, capture_output=True, text=True).stdout.split()
    for path in tracked:
        rel = Path(path).relative_to("src")
        assert (deb_root / APP / rel).is_file(), path


def test_deb_service_desktop_and_launcher_use_the_app_folder(deb_root):
    service = (deb_root / SERVICE).read_text()
    assert f'Environment="PYTHONPATH=/{APP}"' in service
    assert "ExecStart=/usr/bin/python3 -m gnomoji" in service
    assert "ConditionUser=!@system" in service
    assert f'Exec=env "PYTHONPATH=/{APP}" /usr/bin/python3 -m gnomoji' in (
        deb_root / DESKTOP).read_text()
    assert f'export PYTHONPATH="/{APP}"' in (deb_root / "usr/bin/gnomoji").read_text()
    for rel in (SERVICE, DESKTOP, "usr/bin/gnomoji"):
        assert "@APPDIR@" not in (deb_root / rel).read_text(), rel


def test_deb_extension_metadata(deb_root):
    meta = json.loads((deb_root / EXT / "metadata.json").read_text())
    assert meta["uuid"] == UUID
    assert meta["shell-version"] == ["46", "47", "48", "49", "50"]


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


def test_deb_nothing_unwanted(deb_root):
    for path in deb_root.rglob("*"):
        rel = path.relative_to(deb_root).as_posix()
        if rel.startswith("DEBIAN"):
            continue
        assert not UNWANTED.search(rel.replace(APP, "APP")), rel


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
    require("rpmbuild", "rpm")
    return dist / f"gnomoji-{version()}-1.noarch.rpm"


def test_rpm_name_and_version(rpm):
    assert rpm.is_file()
    assert rpm_query(rpm, "--qf", "%{NAME} %{VERSION} %{ARCH}") == f"gnomoji {version()} noarch"


def test_rpm_requires_match_install_sh(rpm):
    requires = [r.strip() for r in rpm_query(rpm, "--requires").splitlines()
                if not r.startswith("rpmlib(") and not r.startswith("/bin/sh")]
    assert "python3 >= 3.11" in requires
    assert "gnome-shell >= 46" in requires
    names = sorted({r.split()[0] for r in requires} - {"python3"})
    assert names == package_names("DNF_PACKAGES")


def test_rpm_has_the_same_files_as_the_deb(rpm, deb_root):
    rpm_files = {f.lstrip("/") for f in rpm_query(rpm, "--list").split()}
    for rel in INSTALLED_FILES:
        assert rel in rpm_files, rel
    assert not any(f.endswith(".rules") for f in rpm_files)


def test_rpm_scripts_enable_and_disable(rpm):
    scripts = rpm_query(rpm, "--scripts")
    assert "/usr/lib/gnomoji/enable-for-everyone" in scripts
    assert "/usr/lib/gnomoji/disable-for-everyone" in scripts


# --- tarball ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tarball(dist):
    return dist / f"gnomoji-{version()}.tar.gz"


def test_tarball_contains_exactly_the_install_only_allow_list(tarball):
    # Install-only, not a repo snapshot: exactly what install.sh/uninstall.sh need plus user
    # docs. The allow-list comes from git itself, so a future tracked file under one of these
    # paths is caught here rather than silently shipped or silently missing.
    prefix = f"gnomoji-{version()}/"
    expected = {prefix.rstrip("/")}
    for f in tracked_files(*TARBALL_PATHS):
        parts = Path(f).parts
        expected.update(prefix + "/".join(parts[:i]) for i in range(1, len(parts) + 1))
    with tarfile.open(tarball) as tar:
        names = {n.rstrip("/") for n in tar.getnames()}
    assert names == expected


def test_tarball_install_scripts_are_executable(tarball):
    prefix = f"gnomoji-{version()}/"
    with tarfile.open(tarball) as tar:
        for rel in ("install.sh", "uninstall.sh"):
            assert tar.getmember(prefix + rel).mode & 0o111, rel


def test_tarball_excludes_dev_only_paths(tarball):
    prefix = f"gnomoji-{version()}/"
    with tarfile.open(tarball) as tar:
        names = tar.getnames()
    for excluded in ("tests", "docs", "tools", ".github", "CLAUDE.md", "CLAUDE.local.md",
                     "pyproject.toml", "uv.lock", ".gitignore", "desktop/README.md",
                     "packaging/build.sh", "packaging/deb", "packaging/rpm",
                     "packaging/smoke-test-deb.sh", "packaging/smoke-test-rpm.sh",
                     "packaging/enable-for-everyone", "packaging/disable-for-everyone"):
        assert not any(n == prefix + excluded or n.startswith(prefix + excluded + "/")
                       for n in names), excluded
    assert not any("CLAUDE.local" in n for n in names)


def test_tarball_installs_with_install_sh(tarball, tmp_path, run, home):
    # Extracts the real tarball and runs its install.sh through the same throwaway-HOME /
    # fake-commands harness as tests/test_install_scripts.py, so this is a real install, not
    # just a path check.
    extract_dir = tmp_path / "extracted"
    extract_dir.mkdir()
    with tarfile.open(tarball) as tar:
        tar.extractall(extract_dir, filter="data")
    root = extract_dir / f"gnomoji-{version()}"

    result, calls = run(root / "install.sh")
    assert result.returncode == 0, result.stdout + result.stderr
    p = paths(home)
    assert (p["app"] / "gnomoji" / "__main__.py").is_file()
    assert (p["app"] / "gnomoji" / "data" / "emoji.json").is_file()
    assert os.access(p["app"] / "uninstall.sh", os.X_OK)
    for name in ("extension.js", "tapDetector.js", "insertWaiter.js", "metadata.json"):
        assert (p["ext"] / name).is_file(), name
    assert p["desktop"].is_file() and p["icon"].is_file()
    assert "systemctl --user enable gnomoji" in calls

    uninstall_result, uninstall_calls = run(p["app"] / "uninstall.sh")
    assert uninstall_result.returncode == 0, uninstall_result.stdout + uninstall_result.stderr
    assert f"gnome-extensions disable {UUID}" in uninstall_calls
    for name, path in p.items():
        assert not path.exists(), name


# --- all formats -------------------------------------------------------------------------


def test_builds_only_committed_files(tmp_path):
    require("dpkg-deb", "git")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(REPO), str(clone)], check=True)
    (clone / "src/gnomoji/leak.py").write_text("LEAK = 1\n")
    with open(clone / "src/gnomoji/__init__.py", "a") as f:
        f.write("# uncommitted edit\n")
    paths = build(tmp_path / "dist", cwd=clone)
    deb = next(p for p in paths if p.suffix == ".deb")
    root = tmp_path / "root"
    subprocess.run(["dpkg-deb", "-x", str(deb), str(root)], check=True)
    assert not (root / APP / "gnomoji/leak.py").exists()
    assert "uncommitted edit" not in (root / APP / "gnomoji/__init__.py").read_text()
    tar = next(p for p in paths if p.name.endswith(".tar.gz"))
    with tarfile.open(tar) as t:
        assert not any(n.endswith("leak.py") for n in t.getnames())


def test_build_work_folder_ignores_tmpdir():
    # rpmbuild's --define "stage $root" / "_topdir ..." split on spaces, so the work folder
    # mustn't come from a TMPDIR that might have them.
    assert 'work="$(mktemp -d /tmp/gnomoji-build.XXXXXX)"' in BUILD.read_text()


def test_builds_with_spaces_in_tmpdir(tmp_path):
    require("dpkg-deb", "git")
    tmp = tmp_path / "temp dir"
    tmp.mkdir()
    paths = build(tmp_path / "dist", env={**os.environ, "TMPDIR": str(tmp)})
    assert any(p.suffix == ".deb" for p in paths)


def test_the_v1_spike_is_gone():
    # 0.2's clipboard/uinput probe: wrong for 0.3, and the tarball ships the whole repo.
    assert not (REPO / "spike").exists()
