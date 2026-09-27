#!/usr/bin/env bash
# Install the emoji picker as a systemd user service, running from this folder.
# Checks what's missing, says what it will do, and asks once before using sudo.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_ID=local.emojipicker.EmojiPicker
PYTHON=/usr/bin/python3
RULE=70-emoji-picker.rules
APT_PACKAGES=(python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 fonts-noto-color-emoji)
DNF_PACKAGES=(python3-gobject gtk4 libadwaita google-noto-color-emoji-fonts)

has_packages() {
    "$PYTHON" - <<'PY' 2>/dev/null
import sys
assert sys.version_info >= (3, 11)
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: F401
PY
}

# True if at least one keyboard in /dev/input is readable by us.
can_read_keyboard() {
    local node
    for node in /dev/input/event*; do
        [ -r "$node" ] || continue
        udevadm info -q property -n "$node" 2>/dev/null | grep -qx 'ID_INPUT_KEYBOARD=1' && return 0
    done
    return 1
}

has_access() { can_read_keyboard && [ -w /dev/uinput ]; }

ask() {  # ask "Question" -> 0 for yes (the default), 1 for no
    local reply
    (: </dev/tty) 2>/dev/null || return 1  # no terminal to ask on
    read -r -p "$1 [Y/n] " reply </dev/tty || return 1
    [[ -z "$reply" || "$reply" =~ ^[Yy] ]]
}

echo "Checking requirements..."
steps=()
commands=()

if ! has_packages; then
    if command -v apt-get >/dev/null; then
        steps+=("Install packages: ${APT_PACKAGES[*]}")
        commands+=("sudo apt-get install -y ${APT_PACKAGES[*]}")
    elif command -v dnf >/dev/null; then
        steps+=("Install packages: ${DNF_PACKAGES[*]}")
        commands+=("sudo dnf install -y ${DNF_PACKAGES[*]}")
    else
        printf '\n✗ Missing Python 3.11+, GTK 4 or libadwaita for %s,\n' "$PYTHON"
        printf '  and there is no apt or dnf here. Install them yourself, then run ./install.sh again.\n'
        exit 1
    fi
fi

if ! has_access; then
    steps+=("Let you (the person at the screen) read keyboards and send keystrokes: add /etc/udev/rules.d/$RULE")
    commands+=("sudo install -m 644 $(printf %q "$REPO/udev/$RULE") /etc/udev/rules.d/"
               "sudo udevadm control --reload"
               "sudo udevadm trigger --subsystem-match=input --subsystem-match=misc --action=change"
               "sudo udevadm settle")
fi

if [ "${XDG_SESSION_TYPE:-}" != "wayland" ]; then
    printf '\n! Your session is %s, not Wayland. The picker is only tested on GNOME Wayland.\n' \
        "${XDG_SESSION_TYPE:-unknown}"
fi

if [ ${#steps[@]} -gt 0 ]; then
    printf '\nTo set up, this needs sudo to:\n'
    printf '  • %s\n' "${steps[@]}"
    printf '\n'
    if ! ask "Continue?"; then
        printf '\nNothing changed. To do it yourself, run:\n'
        printf '  %s\n' "${commands[@]}"
        exit 1
    fi
    for cmd in "${commands[@]}"; do
        printf '→ %s\n' "$cmd"
        eval "$cmd"
    done

    if ! has_packages; then
        printf '\n✗ The packages still aren'\''t usable by %s. See the errors above.\n' "$PYTHON"
        exit 1
    fi
    if ! has_access; then
        printf '\n✗ Keyboard access didn'\''t apply to this session yet. Reboot, then run ./install.sh again.\n'
        exit 1
    fi
fi

echo "All good. Installing the service..."
# The icon and (hidden) desktop entry give the picker its name and icon in Alt+Tab
# and on its notifications.
mkdir -p "$DATA_DIR/icons/hicolor/scalable/apps" "$DATA_DIR/applications"
cp "$REPO/desktop/$APP_ID.svg" "$DATA_DIR/icons/hicolor/scalable/apps/"
# GNOME Shell only rescans icons when the theme's top folder changes, not a subfolder.
touch "$DATA_DIR/icons/hicolor"
sed "s|@SRC@|$REPO/src|" "$REPO/desktop/$APP_ID.desktop" > "$DATA_DIR/applications/$APP_ID.desktop"
mkdir -p "$UNIT_DIR"
sed "s|@SRC@|$REPO/src|" "$REPO/systemd/emoji-picker.service" > "$UNIT_DIR/emoji-picker.service"
systemctl --user daemon-reload
systemctl --user enable emoji-picker
systemctl --user restart emoji-picker

echo
echo "Done! Double-tap right Shift in any text field."
echo "It runs from $REPO, so keep that folder where it is (re-run ./install.sh if you move it)."
echo "Logs: journalctl --user -u emoji-picker -f"
