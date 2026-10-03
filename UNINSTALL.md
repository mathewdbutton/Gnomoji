# Uninstalling Gnomoji

Everything the picker puts on your machine outside its own folder, and how to remove it. Keep
this file accurate: any change that installs or changes something outside the repo must update
it in the same commit.

All three install routes (`.deb`, `.rpm`, `install.sh`) put the same files down; only the
prefix differs.

## If you installed the `.deb`

Open the `.deb` you installed from in App Center again and click **Uninstall** (Gnomoji
doesn't appear in App Center's search or installed list), or `sudo apt remove gnomoji`.

| What | Where |
|---|---|
| App code | `/usr/lib/gnomoji/` (the `gnomoji/` package, plus the shared `enable-for-everyone`/`disable-for-everyone` helper scripts) |
| Launcher | `/usr/bin/gnomoji` |
| User service, enabled for everyone | `/usr/lib/systemd/user/gnomoji.service` |
| GNOME Shell extension | `/usr/share/gnome-shell/extensions/emoji-picker@mathewdbutton.github.io/` |
| Desktop entry, icon | `/usr/share/applications/local.emojipicker.EmojiPicker.desktop`, `/usr/share/icons/hicolor/scalable/apps/local.emojipicker.EmojiPicker.svg` |
| Package docs | `/usr/share/doc/gnomoji/` |

## If you installed the `.rpm`

`sudo dnf remove gnomoji`. Same files as the `.deb` table above.

## If you ran `install.sh` (tarball or a clone)

```bash
~/.local/share/gnomoji/uninstall.sh           # keep recents, skin tone and config
~/.local/share/gnomoji/uninstall.sh --purge   # also delete them
```

If the `.deb` or `.rpm` is installed as well, `uninstall.sh` starts the package's copy once its
own is gone.

| What | Where |
|---|---|
| App code | `~/.local/share/gnomoji/gnomoji/` |
| Launcher | `~/.local/bin/gnomoji` |
| User service, enabled for you | `~/.config/systemd/user/gnomoji.service` |
| GNOME Shell extension | `~/.local/share/gnome-shell/extensions/emoji-picker@mathewdbutton.github.io/` |
| Desktop entry, icon | `~/.local/share/applications/local.emojipicker.EmojiPicker.desktop`, `~/.local/share/icons/hicolor/scalable/apps/local.emojipicker.EmojiPicker.svg` |
| Uninstaller itself | `~/.local/share/gnomoji/uninstall.sh` |

## State and config (any route)

None of the routes above touch these; they're per-user data, not part of the install. Only
`uninstall.sh --purge` deletes them all (a package never does, since packages don't touch home
folders); plain `uninstall.sh` deletes only `extension-enabled`:

| File | Written by |
|---|---|
| `~/.local/state/emoji-picker/recent.json` | The picker, on your first pick |
| `~/.local/state/emoji-picker/skin-tone.json` | The picker, when you first choose a tone |
| `~/.local/state/emoji-picker/extension-enabled` | The picker, the first time it switches the extension on for you. `uninstall.sh` always deletes it, since it also switches the extension off: a `.deb` or `.rpm` installed afterwards then switches it on again |
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

## If you had an earlier `emoji-picker` install

Nothing was ever published under the name `emoji-picker` (no GitHub release, no tag). If you
installed an earlier `emoji-picker` package or `install.sh` copy from this project, remove it
first (`sudo apt remove emoji-picker`, or `~/.local/share/emoji-picker/uninstall.sh`), then
install Gnomoji.

## Checking it's all gone

```bash
systemctl --user status gnomoji                  # "Unit gnomoji.service could not be found."
gnome-extensions info emoji-picker@mathewdbutton.github.io 2>&1   # "No such extension"
ls ~/.local/state/emoji-picker ~/.config/emoji-picker 2>&1        # "No such file or directory" (after --purge)
ls /etc/udev/rules.d/70-emoji-picker.rules 2>&1                   # "No such file or directory" (0.2.x leftover)
```

## Development tools

Only if you set up the development environment (see the README):

- `.venv/` lives inside the repo and goes with it.
- **uv**, if you installed it just for this: `rm -f ~/.local/bin/uv ~/.local/bin/uvx && rm -rf ~/.cache/uv ~/.local/share/uv`
