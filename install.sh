#!/usr/bin/env bash
# Install the emoji picker as a systemd user service, running from this folder.
# Checks everything first and prints fix-it commands; never runs sudo itself.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
PYTHON=/usr/bin/python3
problems=0

problem() {
    problems=1
    printf '\n✗ %s\n' "$1"
    shift
    printf '    %s\n' "$@"
}

echo "Checking requirements..."

if ! "$PYTHON" - <<'PY' 2>/dev/null
import sys
assert sys.version_info >= (3, 11)
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: F401
import evdev  # noqa: F401
PY
then
    problem "Missing Python 3.11+, GTK 4, libadwaita or python-evdev for $PYTHON." \
        "Ubuntu/Debian: sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-evdev fonts-noto-color-emoji" \
        "Fedora:        sudo dnf install python3-gobject gtk4 libadwaita python3-evdev google-noto-color-emoji-fonts"
fi

if ! id -nG | tr ' ' '\n' | grep -qx input; then
    if getent group input | cut -d: -f4 | tr ',' '\n' | grep -qx "$USER"; then
        problem "You're in the 'input' group, but this login session doesn't know yet." \
            "Log out and back in (or reboot), then run ./install.sh again."
    else
        problem "Your user isn't in the 'input' group, so the picker can't see the right Shift key." \
            "Note: this lets any program you run read keyboard input. See the README." \
            "sudo usermod -aG input \"\$USER\"    # then log out and back in"
    fi
fi

if [ ! -w /dev/uinput ]; then
    problem "/dev/uinput isn't writable, so the picker can't send the paste keystroke." \
        "sudo cp \"$REPO/udev/70-emoji-picker-uinput.rules\" /etc/udev/rules.d/" \
        "sudo udevadm control --reload && sudo udevadm trigger --subsystem-match=misc --action=change" \
        "(needs the 'input' group above too; if it still fails, reboot)"
fi

if [ "${XDG_SESSION_TYPE:-}" != "wayland" ]; then
    printf '\n! Your session is %s, not Wayland. The picker is only tested on GNOME Wayland.\n' \
        "${XDG_SESSION_TYPE:-unknown}"
fi

if [ "$problems" -ne 0 ]; then
    printf '\nFix the above, then run ./install.sh again.\n'
    exit 1
fi

echo "All good. Installing the service..."
mkdir -p "$UNIT_DIR"
sed "s|@SRC@|$REPO/src|" "$REPO/systemd/emoji-picker.service" > "$UNIT_DIR/emoji-picker.service"
systemctl --user daemon-reload
systemctl --user enable emoji-picker
systemctl --user restart emoji-picker

echo
echo "Done! Double-tap right Shift in any text field."
echo "It runs from $REPO, so keep that folder where it is (re-run ./install.sh if you move it)."
echo "Logs: journalctl --user -u emoji-picker -f"
