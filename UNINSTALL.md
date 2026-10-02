# Uninstalling the emoji picker

Everything the picker puts on your machine outside its own folder, and how to remove it. Keep
this file accurate: any change that installs or changes something outside the repo must update
it in the same commit.

All three install routes (`.deb`, `.rpm`, `install.sh`) put the same files down; only the
prefix differs.

## If you installed the `.deb`

Open the `.deb` you installed from in App Center again and click **Uninstall** (Emoji Picker
doesn't appear in App Center's search or installed list), or `sudo apt remove emoji-picker`.

| What | Where |
|---|---|
| App code | `/usr/lib/emoji-picker/emoji_picker/` |
| Launcher | `/usr/bin/emoji-picker` |
| User service, enabled for everyone | `/usr/lib/systemd/user/emoji-picker.service` |
| GNOME Shell extension | `/usr/share/gnome-shell/extensions/emoji-picker@mathewdbutton.github.io/` |
| Desktop entry, icon | `/usr/share/applications/local.emojipicker.EmojiPicker.desktop`, `/usr/share/icons/hicolor/scalable/apps/local.emojipicker.EmojiPicker.svg` |
| Package docs | `/usr/share/doc/emoji-picker/` |

## If you installed the `.rpm`

`sudo dnf remove emoji-picker`. Same files as the `.deb` table above.

## If you ran `install.sh` (tarball or a clone)

```bash
~/.local/share/emoji-picker/uninstall.sh           # keep recents, skin tone and config
~/.local/share/emoji-picker/uninstall.sh --purge   # also delete them
```

| What | Where |
|---|---|
| App code | `~/.local/share/emoji-picker/emoji_picker/` |
| Launcher | `~/.local/bin/emoji-picker` |
| User service, enabled for you | `~/.config/systemd/user/emoji-picker.service` |
| GNOME Shell extension | `~/.local/share/gnome-shell/extensions/emoji-picker@mathewdbutton.github.io/` |
| Desktop entry, icon | `~/.local/share/applications/local.emojipicker.EmojiPicker.desktop`, `~/.local/share/icons/hicolor/scalable/apps/local.emojipicker.EmojiPicker.svg` |
| Uninstaller itself | `~/.local/share/emoji-picker/uninstall.sh` |

## State and config (any route)

None of the routes above touch these; they're per-user data, not part of the install. Only
`uninstall.sh --purge` deletes them (a package never does, since packages don't touch home
folders):

| File | Written by |
|---|---|
| `~/.local/state/emoji-picker/recent.json` | The picker, on your first pick |
| `~/.local/state/emoji-picker/skin-tone.json` | The picker, when you first choose a tone |
| `~/.local/state/emoji-picker/extension-enabled` | The picker, the first time it switches the extension on for you |
| `~/.local/state/emoji-picker/welcomed` | 0.2.x only; no longer written, but may still be there from an upgrade |
| `~/.config/emoji-picker/config.toml` | You, if you create one |

To delete them by hand instead of `--purge`:

```bash
rm -rf ~/.local/state/emoji-picker ~/.config/emoji-picker
```

## After removing a package or running uninstall.sh

- **The extension stays listed in `enabled-extensions`.** Removing files doesn't reach each
  user's GNOME settings, so the UUID (`emoji-picker@mathewdbutton.github.io`) can still be in
  `org.gnome.shell enabled-extensions`. This is harmless: `gnome-extensions` won't show it (the
  files are gone), and GNOME ignores the stale UUID. `uninstall.sh` (not a package) removes it
  from the list for you.
- **The "locate pointer" key may still be set to `Shift_R`.** GNOME doesn't disable
  extensions at log-out, so if the picker was still enabled at your last log-out, the
  extension's `Shift_R` setting is still active until something resets it. `uninstall.sh`
  resets it for you. After removing a package, reset it by hand if you use GNOME's Locate
  Pointer feature (off by default):
  ```bash
  gsettings reset org.gnome.mutter locate-pointer-key
  ```

## 0.2.x leftovers

0.2 used a udev rule and the clipboard; 0.3 doesn't, and the rule isn't part of this package
any more. If you installed 0.2.x from a clone (not the `.deb`), you may still have:

- **`/etc/udev/rules.d/70-emoji-picker.rules`**, left by that old install. Nothing removes it
  automatically: `sudo rm /etc/udev/rules.d/70-emoji-picker.rules`.
- **Membership of the `input` group**, if you joined it only for the picker (skip this if
  another program, such as a keyboard remapper, needs it):
  ```bash
  sudo gpasswd -d "$USER" input   # then log out and back in
  ```
- **Keyboard access from that rule.** Access it granted lasts until your next log-in even
  after you upgrade to 0.3.0 or remove the rule — GNOME re-reads udev rules at boot/log-in,
  not live, so the old access doesn't disappear until then.

## Checking it's all gone

```bash
systemctl --user status emoji-picker             # "Unit emoji-picker.service could not be found."
gnome-extensions info emoji-picker@mathewdbutton.github.io 2>&1   # "No such extension"
ls ~/.local/state/emoji-picker ~/.config/emoji-picker 2>&1        # "No such file or directory" (after --purge)
ls /etc/udev/rules.d/70-emoji-picker.rules 2>&1                   # "No such file or directory" (0.2.x leftover)
```

## Development tools

Only if you set up the development environment (see the README):

- `.venv/` lives inside the repo and goes with it.
- **uv**, if you installed it just for this: `rm -f ~/.local/bin/uv ~/.local/bin/uvx && rm -rf ~/.cache/uv ~/.local/share/uv`
