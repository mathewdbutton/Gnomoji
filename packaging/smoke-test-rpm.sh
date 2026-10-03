#!/usr/bin/env bash
# Install a built .rpm, check it, remove it, and check it's gone. For CI, inside a
# fedora:44 container (runs as root there).
# Usage: packaging/smoke-test-rpm.sh dist/gnomoji-<version>-1.noarch.rpm
set -euo pipefail

rpm_file="$(realpath "$1")"
WANTS=/etc/systemd/user/graphical-session.target.wants/gnomoji.service
EXT=/usr/share/gnome-shell/extensions/emoji-picker@mathewdbutton.github.io
fail() { echo "✗ $*" >&2; exit 1; }

dnf install -y "$rpm_file"

files="$(mktemp)"
rpm -ql gnomoji > "$files"
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
(cd / && PYTHONPATH=/usr/lib/gnomoji /usr/bin/python3 -c 'import emoji_picker.emoji_data as d; assert d.DATA_PATH.is_file()') \
    || fail "the installed package doesn't import or is missing its data"

dnf remove -y gnomoji

while read -r f; do
    if [ -f "$f" ] || [ -L "$f" ]; then fail "left behind: $f"; fi
done < "$files"
[ ! -e /usr/lib/gnomoji ] || fail "left behind: /usr/lib/gnomoji (bytecode?)"
[ ! -e "$WANTS" ] || fail "still enabled for all users ($WANTS)"
echo "✓ .rpm smoke test passed"
