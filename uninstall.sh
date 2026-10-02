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

gnome-extensions disable "$UUID" 2>/dev/null || true
if [ -d "$APP_DIR/emoji_picker" ]; then
    PYTHONPATH="$APP_DIR" /usr/bin/python3 -m emoji_picker.extension_setup --forget 2>/dev/null || true
fi
# Disabling the extension restores this. If GNOME never got the chance, undo it here.
if [ "$(gsettings get org.gnome.mutter locate-pointer-key 2>/dev/null)" = "'Shift_R'" ]; then
    gsettings reset org.gnome.mutter locate-pointer-key
fi

systemctl --user disable --now emoji-picker 2>/dev/null || true
rm -f "$UNIT"
systemctl --user daemon-reload
systemctl --user reset-failed emoji-picker 2>/dev/null || true

rm -rf "$EXT_DIR" "$APP_DIR"
rm -f "$HOME/.local/bin/emoji-picker" "$DATA_DIR/applications/$APP_ID.desktop" \
    "$DATA_DIR/icons/hicolor/scalable/apps/$APP_ID.svg"
touch "$DATA_DIR/icons/hicolor" 2>/dev/null || true  # so GNOME Shell notices the icon has gone
echo "Emoji Picker removed."

if [ "${1:-}" = "--purge" ]; then
    rm -rf "${XDG_STATE_HOME:-$HOME/.local/state}/emoji-picker" "${XDG_CONFIG_HOME:-$HOME/.config}/emoji-picker"
    echo "Recently used emoji, skin tone and config removed."
else
    echo "Kept your recently used emoji, skin tone and config (run with --purge to remove them)."
fi

for rule in /etc/udev/rules.d/70-emoji-picker.rules /etc/udev/rules.d/70-emoji-picker-uinput.rules; do
    if [ -e "$rule" ]; then
        echo "An older version's keyboard access rule is still here. Remove it with: sudo rm $rule"
    fi
done
