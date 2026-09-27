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

## If you installed the .deb

Open the .deb you installed from in App Center again and click **Uninstall** (Emoji Picker doesn't
appear in App Center's search or installed list), or `sudo apt remove emoji-picker`. If you no
longer have the file, the apt command works (or download it again). That removes everything the
package installed:

| What | Where |
|---|---|
| The code | `/usr/lib/python3/dist-packages/emoji_picker/` |
| Launcher | `/usr/bin/emoji-picker` |
| User service, turned on for all users | `/usr/lib/systemd/user/emoji-picker.service` and `/etc/systemd/user/graphical-session.target.wants/emoji-picker.service` |
| Desktop entry and icon | `/usr/share/applications/local.emojipicker.EmojiPicker.desktop`, `/usr/share/icons/hicolor/scalable/apps/local.emojipicker.EmojiPicker.svg` |
| Keyboard access rule | `/usr/lib/udev/rules.d/70-emoji-picker.rules` (access already granted ends at your next log-in) |
| Package docs | `/usr/share/doc/emoji-picker/` |

Packages never touch home folders, so each user's recents and config stay. To delete them:

```bash
rm -rf ~/.local/state/emoji-picker ~/.config/emoji-picker
```

Packages installed as dependencies (GTK, libadwaita, the emoji font) stay too. Usually keep them:
other apps depend on them.

A source install's `/etc/udev/rules.d/70-emoji-picker.rules` (left by `./uninstall.sh` without
`--purge`) overrides the packaged rule of the same name and keeps keyboard access after
`apt remove`; `./uninstall.sh --purge` (or `sudo rm` it) removes it.

The rest of this file is about installs from source (`./install.sh`).

## What gets added

| What | Added by | Remove with |
|---|---|---|
| `~/.config/systemd/user/emoji-picker.service` and its enable link in `~/.config/systemd/user/graphical-session.target.wants/` | `./install.sh` | `./uninstall.sh` |
| `~/.local/share/applications/local.emojipicker.EmojiPicker.desktop` (hidden; gives the window its name) | `./install.sh` | `./uninstall.sh` |
| `~/.local/share/icons/hicolor/scalable/apps/local.emojipicker.EmojiPicker.svg` (the app icon) | `./install.sh` | `./uninstall.sh` |
| `~/.local/state/emoji-picker/recent.json` (recently used emoji) | The picker, on first pick | `./uninstall.sh --purge` |
| `~/.local/state/emoji-picker/welcomed` (the "ready" notification was shown) | The picker, on its first start | `./uninstall.sh --purge` |
| `~/.config/emoji-picker/config.toml` | You, if you create one | `./uninstall.sh --purge` |
| Logs | The user journal (rotated automatically) | Nothing needed |
| `/etc/udev/rules.d/70-emoji-picker.rules` (keyboard access for the person at the screen) | `./install.sh`, with your OK | `./uninstall.sh --purge` (asks first) |
| `/etc/udev/rules.d/70-emoji-picker-uinput.rules` and membership of the `input` group | Older versions: you, by hand | See below |
| System packages (GTK, libadwaita, emoji font), if they were missing | `./install.sh`, with your OK | Usually keep them: other apps depend on them (Ubuntu's own tools need `python3-gi`) |

## Full teardown

```bash
# 1. Service, recents, config and the udev rule (answer yes when asked)
./uninstall.sh --purge

# 2. Older versions only: the input group, if you joined it just for the picker
#    (skip if a keyboard remapper such as Toshy, keyd or xremap needs it)
sudo gpasswd -d "$USER" input      # then log out and back in

# 3. The project folder
rm -rf /path/to/emoji-picker
```

## Checking it's all gone

```bash
systemctl --user status emoji-picker     # "Unit emoji-picker.service could not be found."
ls ~/.local/state/emoji-picker ~/.config/emoji-picker 2>&1   # "No such file or directory"
ls ~/.local/share/applications/local.emojipicker.* ~/.local/share/icons/hicolor/scalable/apps/local.emojipicker.* 2>&1   # "No such file or directory"
ls /etc/udev/rules.d/70-emoji-picker*.rules 2>&1             # "No such file or directory"
id -nG | grep -w input                   # no output (if you left the group)
```

## Development tools

Only if you set up the development environment (see the README):

- `.venv/` lives inside the repo and goes with it.
- **uv**, if you installed it just for this: `rm -f ~/.local/bin/uv ~/.local/bin/uvx && rm -rf ~/.cache/uv ~/.local/share/uv`
