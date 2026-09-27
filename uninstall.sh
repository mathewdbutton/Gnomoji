#!/usr/bin/env bash
# Remove the emoji picker service. Pass --purge to also delete recents and config.
set -euo pipefail

UNIT="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/emoji-picker.service"

systemctl --user disable --now emoji-picker 2>/dev/null || true
rm -f "$UNIT"
systemctl --user daemon-reload
systemctl --user reset-failed emoji-picker 2>/dev/null || true
echo "Service removed."

if [ "${1:-}" = "--purge" ]; then
    rm -rf "${XDG_STATE_HOME:-$HOME/.local/state}/emoji-picker" "${XDG_CONFIG_HOME:-$HOME/.config}/emoji-picker"
    echo "Recents and config removed."
else
    echo "Kept your recents and config (run with --purge to remove them)."
fi

echo "Permission changes (the 'input' group, the udev rule) are left alone. See UNINSTALL.md to undo them."
