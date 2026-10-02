#!/usr/bin/env bash
# Install Emoji Picker for you, with no sudo: copies its GNOME Shell extension and the app
# into your home folder and starts the app as a systemd user service. This folder can be
# deleted afterwards. To remove it all: ~/.local/share/emoji-picker/uninstall.sh
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA_DIR/emoji-picker"
UUID=emoji-picker@mathewdbutton.github.io
EXT_DIR="$DATA_DIR/gnome-shell/extensions/$UUID"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
BIN_DIR="$HOME/.local/bin"
APP_ID=local.emojipicker.EmojiPicker
PYTHON=/usr/bin/python3
APT_PACKAGES=(python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 fonts-noto-color-emoji gnome-shell)
DNF_PACKAGES=(python3-gobject gtk4 libadwaita google-noto-color-emoji-fonts gnome-shell)

has_python_gtk() {
    "$PYTHON" - <<'PY' 2>/dev/null
import sys
assert sys.version_info >= (3, 11)
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: F401
PY
}

echo "Checking requirements..."
if ! has_python_gtk || ! command -v gnome-shell >/dev/null \
        || ! fc-list "Noto Color Emoji" 2>/dev/null | grep -q .; then
    printf '\n✗ Missing some of: Python 3.11+ with GTK 4 and libadwaita, the Noto Color Emoji font, GNOME Shell.\n'
    if command -v apt-get >/dev/null; then
        printf '  Install them with:  sudo apt install %s\n' "${APT_PACKAGES[*]}"
    elif command -v dnf >/dev/null; then
        printf '  Install them with:  sudo dnf install %s\n' "${DNF_PACKAGES[*]}"
    else
        printf '  Install them with your package manager.\n'
    fi
    printf '  Then run ./install.sh again.\n'
    exit 1
fi

shell_major="$(gnome-shell --version | grep -oE '[0-9]+' | head -n1 || true)"
case "$shell_major" in
    46|47|48|49|50) ;;
    *) printf '\n! GNOME %s: the extension supports GNOME 46-50, so GNOME may refuse to load it.\n' "$shell_major" ;;
esac
if [ "${XDG_SESSION_TYPE:-}" != "wayland" ]; then
    printf '\n! Your session is %s, not Wayland. The picker is only tested on GNOME Wayland.\n' \
        "${XDG_SESSION_TYPE:-unknown}"
fi

echo "Installing into your home folder..."
# Replace, not merge: files removed in a newer version mustn't linger.
rm -rf "$APP_DIR/emoji_picker" "$EXT_DIR"
mkdir -p "$APP_DIR" "$EXT_DIR" "$UNIT_DIR" "$BIN_DIR" "$DATA_DIR/applications" \
    "$DATA_DIR/icons/hicolor/scalable/apps"
cp -r "$SRC/src/emoji_picker" "$APP_DIR/"
find "$APP_DIR/emoji_picker" -name __pycache__ -type d -prune -exec rm -rf {} +
cp "$SRC"/extension/*.js "$SRC/extension/metadata.json" "$EXT_DIR/"
install -m 755 "$SRC/uninstall.sh" "$APP_DIR/uninstall.sh"

fill() {  # fill TEMPLATE DEST: put the app folder in place of @APPDIR@
    local value="${APP_DIR//\\/\\\\}"
    value="${value//&/\\&}"
    sed "s|@APPDIR@|${value//|/\\|}|g" "$1" > "$2"
}
fill "$SRC/packaging/emoji-picker" "$BIN_DIR/emoji-picker"
chmod 755 "$BIN_DIR/emoji-picker"
fill "$SRC/desktop/$APP_ID.desktop" "$DATA_DIR/applications/$APP_ID.desktop"
cp "$SRC/desktop/$APP_ID.svg" "$DATA_DIR/icons/hicolor/scalable/apps/"
# GNOME Shell only rescans icons when the theme's top folder changes, not a subfolder.
touch "$DATA_DIR/icons/hicolor"
fill "$SRC/systemd/emoji-picker.service" "$UNIT_DIR/emoji-picker.service"

if ! PYTHONPATH="$APP_DIR" PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -m emoji_picker.extension_setup; then
    printf "! Couldn't switch the extension on. Turn on Emoji Picker in the Extensions app.\n"
fi
systemctl --user daemon-reload
systemctl --user enable emoji-picker
systemctl --user restart emoji-picker

echo
if gnome-extensions info "$UUID" 2>/dev/null | grep -q "State: ACTIVE"; then
    echo "Done! Double-tap right Shift in a text field."
else
    echo "Almost done: log out and back in once to finish setting up Emoji Picker."
    echo "Then double-tap right Shift in a text field."
fi
echo "You can delete this folder now. To uninstall: $APP_DIR/uninstall.sh"
