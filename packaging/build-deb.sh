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
