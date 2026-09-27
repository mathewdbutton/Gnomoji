#!/usr/bin/env bash
# Remove the emoji picker service. Pass --purge to also delete recents, config and the udev rule.
set -euo pipefail

UNIT="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/emoji-picker.service"
# The current rule, and the one older installs added by hand.
RULES=(/etc/udev/rules.d/70-emoji-picker.rules /etc/udev/rules.d/70-emoji-picker-uinput.rules)

ask() {  # ask "Question" -> 0 for yes (the default), 1 for no
    local reply
    (: </dev/tty) 2>/dev/null || return 1  # no terminal to ask on
    read -r -p "$1 [Y/n] " reply </dev/tty || return 1
    [[ -z "$reply" || "$reply" =~ ^[Yy] ]]
}

systemctl --user disable --now emoji-picker 2>/dev/null || true
rm -f "$UNIT"
systemctl --user daemon-reload
systemctl --user reset-failed emoji-picker 2>/dev/null || true
echo "Service removed."

if [ "${1:-}" != "--purge" ]; then
    echo "Kept your recents, config and keyboard access (run with --purge to remove them)."
    exit 0
fi

rm -rf "${XDG_STATE_HOME:-$HOME/.local/state}/emoji-picker" "${XDG_CONFIG_HOME:-$HOME/.config}/emoji-picker"
echo "Recents and config removed."

found=()
for rule in "${RULES[@]}"; do
    if [ -e "$rule" ]; then found+=("$rule"); fi
done
if [ ${#found[@]} -gt 0 ]; then
    printf 'Keyboard access rule: %s\n' "${found[@]}"
    if ask "Remove it (needs sudo)?"; then
        sudo rm -f "${found[@]}"
        sudo udevadm control --reload
        sudo udevadm trigger --subsystem-match=input --subsystem-match=misc --action=change
        echo "Rule removed. Access already granted ends when you next log in."
    else
        echo "Kept the rule."
    fi
fi

if id -nG | tr ' ' '\n' | grep -qx input; then
    echo "You're in the 'input' group. If you joined it only for the picker, see UNINSTALL.md."
fi
