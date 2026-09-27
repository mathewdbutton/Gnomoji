# Uninstalling the emoji picker

Everything the picker puts on your machine outside its own folder, and how to remove it.
Keep this file accurate: any change that installs or changes something outside the repo
must update it in the same commit.

## Emergency stop

If keys ever behave strangely (e.g. a modifier seems stuck, or keys are being
doubled), stop the picker:

```bash
systemctl --user stop emoji-picker    # if installed as a service
pkill -f emoji_picker                 # if running in a terminal
```

When the process exits, the kernel removes its virtual keyboard and releases any
keys it was holding down.

## What gets added

| What | Added by | Remove with |
|---|---|---|
| `~/.config/systemd/user/emoji-picker.service` and its enable link in `~/.config/systemd/user/graphical-session.target.wants/` | `./install.sh` | `./uninstall.sh` |
| `~/.local/state/emoji-picker/recent.json` (recently used emoji) | The picker, on first pick | `./uninstall.sh --purge` |
| `~/.config/emoji-picker/config.toml` | You, if you create one | `./uninstall.sh --purge` |
| Logs | The user journal (rotated automatically) | Nothing needed |
| `/etc/udev/rules.d/70-emoji-picker-uinput.rules` | You, from the README's Permissions step | See below |
| Membership of the `input` group | You, from the README's Permissions step | See below |
| System packages (GTK, libadwaita, python-evdev, emoji font) | You, from the README's Requirements | Usually keep them: other apps depend on them (Ubuntu's own tools need `python3-gi`) |

## Full teardown

```bash
# 1. Service, recents and config
./uninstall.sh --purge

# 2. The udev rule (skip if another tool, e.g. a keyboard remapper, needs /dev/uinput)
sudo rm -f /etc/udev/rules.d/70-emoji-picker-uinput.rules
sudo udevadm control --reload && sudo udevadm trigger --subsystem-match=misc --action=change

# 3. The input group (skip if a keyboard remapper such as Toshy, keyd or xremap needs it)
sudo gpasswd -d "$USER" input      # then log out and back in

# 4. The project folder
rm -rf /path/to/emoji-picker
```

## Checking it's all gone

```bash
systemctl --user status emoji-picker     # "Unit emoji-picker.service could not be found."
ls ~/.local/state/emoji-picker ~/.config/emoji-picker 2>&1   # "No such file or directory"
ls /etc/udev/rules.d/70-emoji-picker-uinput.rules 2>&1       # "No such file or directory"
id -nG | grep -w input                   # no output (if you left the group)
```

## Development tools

Only if you set up the development environment (see the README):

- `.venv/` lives inside the repo and goes with it.
- **uv**, if you installed it just for this: `rm -f ~/.local/bin/uv ~/.local/bin/uvx && rm -rf ~/.cache/uv ~/.local/share/uv`
