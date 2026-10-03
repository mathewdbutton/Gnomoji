#!/usr/bin/env bash
# Install a built .deb, check it, remove it, and check it's gone. For CI: it needs sudo and
# changes the system, so run it on a throwaway machine.
# Usage: packaging/smoke-test-deb.sh dist/gnomoji_<version>_all.deb
set -euo pipefail

deb="$(realpath "$1")"
WANTS=/etc/systemd/user/graphical-session.target.wants/gnomoji.service
EXT=/usr/share/gnome-shell/extensions/emoji-picker@mathewdbutton.github.io
fail() { echo "✗ $*" >&2; exit 1; }

sudo apt-get install -y "$deb"

files="$(mktemp)"
dpkg -L gnomoji > "$files"
for f in /usr/bin/gnomoji \
         /usr/lib/systemd/user/gnomoji.service \
         /usr/lib/gnomoji/emoji_picker/__main__.py \
         /usr/share/gnome-shell/extensions/emoji-picker@mathewdbutton.github.io/metadata.json \
         "$EXT/extension.js" \
         /usr/share/applications/local.emojipicker.EmojiPicker.desktop \
         /usr/share/icons/hicolor/scalable/apps/local.emojipicker.EmojiPicker.svg; do
    [ -f "$f" ] || fail "missing $f"
done
if ls /usr/lib/udev/rules.d/*gnomoji* >/dev/null 2>&1; then fail "a udev rule was installed (want: no udev rule)"; fi
[ -L "$WANTS" ] || fail "not enabled for all users ($WANTS)"
# From /, so nothing but the installed package can be imported.
(cd / && PYTHONPATH=/usr/lib/gnomoji /usr/bin/python3 -c 'import emoji_picker.emoji_data as d; assert d.DATA_PATH.is_file()') \
    || fail "the installed package doesn't import or is missing its data"

sudo apt-get remove -y gnomoji

while read -r f; do
    if [ -f "$f" ] || [ -L "$f" ]; then fail "left behind: $f"; fi
done < "$files"
[ ! -e /usr/lib/gnomoji ] || fail "left behind: /usr/lib/gnomoji"
[ ! -e "$WANTS" ] || fail "still enabled for all users ($WANTS)"
echo "✓ .deb smoke test passed"
