#!/usr/bin/env bash
# Install a built .deb, check it, remove it, and check it's gone. For CI: it needs sudo and
# changes the system, so run it on a throwaway machine.
# Usage: packaging/smoke-test-deb.sh dist/emoji-picker_<version>_all.deb
set -euo pipefail

deb="$(realpath "$1")"
WANTS=/etc/systemd/user/graphical-session.target.wants/emoji-picker.service
EXT=/usr/share/gnome-shell/extensions/emoji-picker@mathewdbutton.github.io
fail() { echo "✗ $*" >&2; exit 1; }

sudo apt-get install -y "$deb"

files="$(mktemp)"
dpkg -L emoji-picker > "$files"
for f in /usr/bin/emoji-picker \
         /usr/lib/systemd/user/emoji-picker.service \
         /usr/lib/emoji-picker/emoji_picker/__main__.py \
         /usr/share/gnome-shell/extensions/emoji-picker@mathewdbutton.github.io/metadata.json \
         "$EXT/extension.js" \
         /usr/share/applications/local.emojipicker.EmojiPicker.desktop \
         /usr/share/icons/hicolor/scalable/apps/local.emojipicker.EmojiPicker.svg; do
    [ -f "$f" ] || fail "missing $f"
done
if ls /usr/lib/udev/rules.d/*emoji-picker* >/dev/null 2>&1; then fail "a udev rule was installed (want: no udev rule)"; fi
[ -L "$WANTS" ] || fail "not enabled for all users ($WANTS)"
# From /, so nothing but the installed package can be imported.
(cd / && PYTHONPATH=/usr/lib/emoji-picker /usr/bin/python3 -c 'import emoji_picker.emoji_data as d; assert d.DATA_PATH.is_file()') \
    || fail "the installed package doesn't import or is missing its data"

sudo apt-get remove -y emoji-picker

while read -r f; do
    if [ -f "$f" ] || [ -L "$f" ]; then fail "left behind: $f"; fi
done < "$files"
[ ! -e /usr/lib/emoji-picker ] || fail "left behind: /usr/lib/emoji-picker"
[ ! -e "$WANTS" ] || fail "still enabled for all users ($WANTS)"
echo "✓ .deb smoke test passed"
