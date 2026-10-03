#!/usr/bin/env bash
# One-command dev setup for Gnomoji: checks for (and offers to install) the system packages
# the tests and packaging need, sets up .venv the way this project expects (uv,
# --system-site-packages, so PyGObject/Adw come from the distro, not pip), then runs the
# test suite and linter once to confirm it's ready. See CLAUDE.md "Commands".
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
    printf '✗ Run ./dev-setup.sh as yourself, without sudo.\n' >&2
    exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON=/usr/bin/python3

has_python_gtk() {
    "$PYTHON" - <<'PY' 2>/dev/null
import sys
assert sys.version_info >= (3, 12)
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: F401
PY
}

has_font() {
    command -v fc-list >/dev/null 2>&1 && command -v fc-match >/dev/null 2>&1 \
        && fc-list "Noto Color Emoji" 2>/dev/null | grep -q .
}

# Ubuntu/Debian (apt) only: this script doesn't know other distros' package names. On
# anything else it lists what's needed and stops; see the README's "Developing" section for
# the plain dependency list.
# Check name -> human description, and the apt package(s) that provide it. uv is handled
# separately below: it's never installed via apt.
declare -A DESCRIPTIONS=(
    [python_gtk]="Python 3.12+ with GTK 4 and libadwaita, importable by /usr/bin/python3"
    [font]="Noto Color Emoji font and fontconfig (fc-list/fc-match)"
    [gjs]="gjs"
    [git]="git"
    [dpkg_deb]="dpkg-deb"
    [rpm]="rpmbuild and rpm"
    [shellcheck]="shellcheck"
)
declare -A APT_PKGS=(
    [python_gtk]="python3-gi gir1.2-gtk-4.0 gir1.2-adw-1"
    [font]="fonts-noto-color-emoji fontconfig"
    [gjs]="gjs"
    [git]="git"
    [dpkg_deb]="dpkg"
    [rpm]="rpm"
    [shellcheck]="shellcheck"
)

echo "Checking requirements..."
missing=()
has_python_gtk || missing+=(python_gtk)
has_font || missing+=(font)
command -v gjs >/dev/null 2>&1 || missing+=(gjs)
command -v git >/dev/null 2>&1 || missing+=(git)
command -v dpkg-deb >/dev/null 2>&1 || missing+=(dpkg_deb)
{ command -v rpmbuild >/dev/null 2>&1 && command -v rpm >/dev/null 2>&1; } || missing+=(rpm)
command -v shellcheck >/dev/null 2>&1 || missing+=(shellcheck)

if [ "${#missing[@]}" -gt 0 ]; then
    echo
    echo "Missing:"
    for check in "${missing[@]}"; do
        printf '  - %s\n' "${DESCRIPTIONS[$check]}"
    done

    apt_pkgs=()
    for check in "${missing[@]}"; do
        # shellcheck disable=SC2206  # word-splitting this is intended
        apt_pkgs+=(${APT_PKGS[$check]})
    done

    if command -v apt-get >/dev/null 2>&1; then
        cmd="sudo apt-get install -y ${apt_pkgs[*]}"
    else
        printf '\n✗ This only automates install on Ubuntu/Debian (apt). Install the equivalent of:\n'
        printf '  %s\n' "${apt_pkgs[*]}"
        exit 1
    fi

    echo
    printf 'This will run:\n  %s\n\n' "$cmd"
    printf 'Install these packages? [Y/n] '
    if read -r reply < /dev/tty 2>/dev/null; then
        case "$reply" in
            ""|[Yy]*) ;;
            *)
                echo "Not installing. Run that command yourself, then re-run ./dev-setup.sh." >&2
                exit 1 ;;
        esac
    else
        printf '\nNo terminal to ask on. Run this yourself, then re-run ./dev-setup.sh:\n  %s\n' \
            "$cmd" >&2
        exit 1
    fi
    eval "$cmd"
fi

if ! command -v uv >/dev/null 2>&1; then
    printf '\n✗ uv is not installed. Install it with:\n'
    printf '  curl -LsSf https://astral.sh/uv/install.sh | sh\n'
    printf 'Then re-run ./dev-setup.sh.\n'
    exit 1
fi

echo
echo "Setting up .venv..."
cd "$HERE"
if [ ! -d .venv ]; then
    uv venv --system-site-packages --python "$PYTHON"
fi
uv sync

echo
echo "Running tests..."
if uv run pytest -q && uv run ruff check; then
    echo
    echo "Ready! Try: uv run pytest -q && uv run ruff check"
else
    echo
    echo "Setup finished, but pytest/ruff reported problems above." >&2
    exit 1
fi
