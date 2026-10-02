#!/usr/bin/env bash
# Install a built .rpm, check it, remove it, and check it's gone. For CI, inside a
# fedora:44 container (runs as root there).
# Usage: packaging/smoke-test-rpm.sh dist/emoji-picker-<version>-1.noarch.rpm
set -euo pipefail

rpm_file="$(realpath "$1")"
WANTS=/etc/systemd/user/graphical-session.target.wants/emoji-picker.service
EXT=/usr/share/gnome-shell/extensions/emoji-picker@mathewdbutton.github.io
fail() { echo "✗ $*" >&2; exit 1; }

dnf install -y "$rpm_file"

files="$(mktemp)"
rpm -ql emoji-picker > "$files"
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
(cd / && PYTHONPATH=/usr/lib/emoji-picker /usr/bin/python3 -c 'import emoji_picker.emoji_data as d; assert d.DATA_PATH.is_file()') \
    || fail "the installed package doesn't import or is missing its data"

dnf remove -y emoji-picker

while read -r f; do
    if [ -f "$f" ] || [ -L "$f" ]; then fail "left behind: $f"; fi
done < "$files"
[ ! -e /usr/lib/emoji-picker ] || fail "left behind: /usr/lib/emoji-picker (bytecode?)"
[ ! -e "$WANTS" ] || fail "still enabled for all users ($WANTS)"
echo "✓ .rpm smoke test passed"
