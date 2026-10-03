#!/usr/bin/env bash
# Build the .deb, .rpm and .tar.gz from the last commit of the git repo you're in.
# Usage: packaging/build.sh [OUT_DIR]      (default OUT_DIR: <repo>/dist)
# Only committed files go in; uncommitted edits and untracked files never do. The packaging
# files come from this script's own folder. Prints each built file's path. The .rpm needs
# rpmbuild (Ubuntu: sudo apt install rpm); without it the .rpm is skipped with a warning.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(git rev-parse --show-toplevel)"
OUT="${1:-$REPO/dist}"
APP_ID=local.emojipicker.EmojiPicker
UUID=emoji-picker@mathewdbutton.github.io
APP=/usr/lib/gnomoji
umask 022

# Not under $TMPDIR: the rpmbuild --define values below split on spaces.
work="$(mktemp -d /tmp/gnomoji-build.XXXXXX)"
trap 'rm -rf "$work"' EXIT
src="$work/src"
root="$work/root"
mkdir "$src"
git -C "$REPO" archive HEAD | tar -x -C "$src"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"

version="$(python3 -c 'import sys, tomllib
print(tomllib.load(open(sys.argv[1], "rb"))["project"]["version"])' "$src/pyproject.toml")"
maintainer="$(sed -n 's/^Maintainer: //p' "$HERE/deb/control")"

# --- The installed tree, the same for both packages ---------------------------------------
fill() { sed "s|@APPDIR@|$APP|g" "$1" > "$2"; }

install -d "$root$APP" "$root/usr/bin" "$root/usr/lib/systemd/user" "$root/usr/share/applications" \
    "$root/usr/share/gnome-shell/extensions/$UUID"
cp -r "$src/src/gnomoji" "$root$APP/"
install -m 755 "$HERE/enable-for-everyone" "$HERE/disable-for-everyone" "$root$APP/"
cp "$src"/extension/*.js "$src/extension/metadata.json" "$root/usr/share/gnome-shell/extensions/$UUID/"
fill "$HERE/gnomoji" "$root/usr/bin/gnomoji"
fill "$src/systemd/gnomoji.service" "$root/usr/lib/systemd/user/gnomoji.service"
fill "$src/desktop/$APP_ID.desktop" "$root/usr/share/applications/$APP_ID.desktop"
install -D -m 644 "$src/desktop/$APP_ID.svg" "$root/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"

doc="$root/usr/share/doc/gnomoji"
install -d "$doc"
{
    echo "Gnomoji: https://github.com/mathewdbutton/Gnomoji"
    echo
    echo "The icon is the pinching hand emoji from Noto Emoji, Copyright Google LLC, under the"
    echo "Apache License 2.0 (https://www.apache.org/licenses/LICENSE-2.0)."
    echo "The emoji names and keywords come from Unicode's emoji data and CLDR, under the"
    echo "Unicode License v3 (https://www.unicode.org/license.txt)."
    echo
    echo "Everything else:"
    echo
    cat "$src/LICENSE"
} > "$doc/copyright"

# Normalise modes: the user's umask or the source files mustn't decide them.
find "$root" -type d -exec chmod 755 {} +
find "$root" -type f -exec chmod 644 {} +
chmod 755 "$root/usr/bin/gnomoji" "$root$APP/enable-for-everyone" "$root$APP/disable-for-everyone"

# --- .deb -------------------------------------------------------------------------------
deb_root="$work/deb"
cp -a "$root" "$deb_root"
printf 'gnomoji (%s) unstable; urgency=medium\n\n  * Release %s: https://github.com/mathewdbutton/Gnomoji/releases\n\n -- %s  %s\n' \
    "$version" "$version" "$maintainer" "$(git -C "$REPO" log -1 --format=%cD)" \
    | gzip -9n > "$deb_root/usr/share/doc/gnomoji/changelog.gz"
chmod 644 "$deb_root/usr/share/doc/gnomoji/changelog.gz"
install -d "$deb_root/DEBIAN"
sed -e "s/@VERSION@/$version/" -e "s/@INSTALLED_SIZE@/$(du -sk "$deb_root/usr" | cut -f1)/" \
    "$HERE/deb/control" > "$deb_root/DEBIAN/control"
chmod 644 "$deb_root/DEBIAN/control"
install -m 755 "$HERE/deb/postinst" "$HERE/deb/prerm" "$deb_root/DEBIAN/"
deb="$OUT/gnomoji_${version}_all.deb"
dpkg-deb --root-owner-group -Zxz --build "$deb_root" "$deb" >/dev/null
echo "$deb"

# --- .rpm -------------------------------------------------------------------------------
if command -v rpmbuild >/dev/null; then
    rpmbuild --quiet -bb --define "_topdir $work/rpm" --define "stage $root" \
        --define "pkgversion $version" "$HERE/rpm/gnomoji.spec" >/dev/null
    rpm="$OUT/gnomoji-${version}-1.noarch.rpm"
    cp "$work/rpm/RPMS/noarch/gnomoji-${version}-1.noarch.rpm" "$rpm"
    echo "$rpm"
else
    echo "build.sh: rpmbuild not found, skipping the .rpm (Ubuntu: sudo apt install rpm)" >&2
fi

# --- tarball --------------------------------------------------------------------------
# Install-only: just what install.sh/uninstall.sh need plus user docs, not the whole repo.
# GitHub's own "Source code" download already offers the full repo for that.
tarball="$OUT/gnomoji-${version}.tar.gz"
tarball_paths=(
    install.sh uninstall.sh src/gnomoji extension systemd
    "desktop/$APP_ID.desktop" "desktop/$APP_ID.svg"
    packaging/gnomoji README.md UNINSTALL.md LICENSE
)
git -C "$REPO" archive --format=tar.gz --prefix="gnomoji-${version}/" -o "$tarball" \
    HEAD -- "${tarball_paths[@]}"
echo "$tarball"
