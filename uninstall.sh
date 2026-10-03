#!/usr/bin/env bash
# Remove Emoji Picker installed with install.sh: its extension, service, app, launcher,
# desktop entry and icon. --purge also deletes recently used emoji, the skin tone and the
# config. Installed from a .deb or .rpm? Remove it with your package manager instead.
set -euo pipefail

DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA_DIR/emoji-picker"
UUID=emoji-picker@mathewdbutton.github.io
EXT_DIR="$DATA_DIR/gnome-shell/extensions/$UUID"
UNIT="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/emoji-picker.service"
APP_ID=local.emojipicker.EmojiPicker
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/emoji-picker"
# A .deb or .rpm's service: if one is installed too, it takes over once ours is gone.
PACKAGE_UNIT=/usr/lib/systemd/user/emoji-picker.service

gnome-extensions disable "$UUID" 2>/dev/null || true
if [ -d "$APP_DIR/emoji_picker" ]; then
    PYTHONPATH="$APP_DIR" /usr/bin/python3 -m emoji_picker.extension_setup --forget 2>/dev/null || true
fi
# It's out of enabled-extensions now, so forget that the app switched it on: a .deb or .rpm
# (now or later) then switches it on again at its first start.
rm -f "$STATE_DIR/extension-enabled"
# Disabling the extension restores this. If GNOME never got the chance, undo it here.
if [ "$(gsettings get org.gnome.mutter locate-pointer-key 2>/dev/null)" = "'Shift_R'" ]; then
    gsettings reset org.gnome.mutter locate-pointer-key || true
fi

# Best effort: with no user bus (e.g. over ssh) systemctl fails, and the files still go.
systemctl --user disable --now emoji-picker 2>/dev/null || true
rm -f "$UNIT"
systemctl --user daemon-reload 2>/dev/null || true
systemctl --user reset-failed emoji-picker 2>/dev/null || true

rm -rf "$EXT_DIR" "$APP_DIR"
rm -f "$HOME/.local/bin/emoji-picker" "$DATA_DIR/applications/$APP_ID.desktop" \
    "$DATA_DIR/icons/hicolor/scalable/apps/$APP_ID.svg"
touch "$DATA_DIR/icons/hicolor" 2>/dev/null || true  # so GNOME Shell notices the icon has gone
echo "Emoji Picker removed."

if [ "${1:-}" = "--purge" ]; then
    rm -rf "$STATE_DIR" "${XDG_CONFIG_HOME:-$HOME/.config}/emoji-picker"
    echo "Recently used emoji, skin tone and config removed."
else
    echo "Kept your recently used emoji, skin tone and config (run with --purge to remove them)."
fi

if [ -e "$PACKAGE_UNIT" ]; then
    systemctl --user start emoji-picker 2>/dev/null || true
    echo "Emoji Picker's .deb or .rpm is installed too: its copy has taken over."
fi

for rule in /etc/udev/rules.d/70-emoji-picker.rules /etc/udev/rules.d/70-emoji-picker-uinput.rules; do
    if [ -e "$rule" ]; then
        echo "An older version's keyboard access rule is still here. Remove it with: sudo rm $rule"
    fi
done
