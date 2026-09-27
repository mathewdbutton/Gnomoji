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
