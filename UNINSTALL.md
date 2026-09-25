# Uninstalling / rolling back the emoji picker

Everything this project adds to the machine outside its own folder, which step adds
it, and how to remove it. Keep this file accurate: any step that installs or changes
something outside the repo must add a row here in the same commit.

## Emergency stop

If keys ever behave strangely (e.g. a modifier seems stuck, or keys are being
doubled), stop the picker:

```bash
systemctl --user stop emoji-picker    # if installed as a service (Task 11+)
pkill -f emoji_picker                 # if running in a terminal
pkill -f paste_probe.py               # if the Task 1 spike is running
```

When the process exits, the kernel removes its virtual keyboard and releases any
keys it was holding down.

## Footprint by step

| Task | What it adds outside the repo | Rollback |
|---|---|---|
| 1. Feasibility spike | A temporary uinput virtual keyboard ("emoji-picker spike keyboard"), removed automatically when the script exits. **Only if you agree during the task:** the GNOME setting `org.gnome.mutter center-new-windows`. | Nothing for the keyboard. `gsettings reset org.gnome.mutter center-new-windows` if it was changed. |
| 2. Scaffold | **uv**, installed with `UV_NO_MODIFY_PATH=1` so shell rc files are **not** edited (`~/.local/bin` is already on PATH). Adds `~/.local/bin/uv`, `~/.local/bin/uvx`, cache in `~/.cache/uv`, data in `~/.local/share/uv`. `.venv/` lives inside the repo. | `rm -f ~/.local/bin/uv ~/.local/bin/uvx && rm -rf ~/.cache/uv ~/.local/share/uv` |
| 3. Emoji data | Nothing. Sources are downloaded in memory; only `src/emoji_picker/data/emoji.json` (inside the repo) is written. | None |
| 4–10 | Nothing installed. Group memberships, udev rules and apt packages are **not** touched. The window preview (Task 10) doesn't write recents. | None |
| 11. Service | `~/.config/systemd/user/emoji-picker.service` and its enable symlink in `~/.config/systemd/user/graphical-session.target.wants/`. At runtime: `~/.local/state/emoji-picker/recent.json`. If you create one: `~/.config/emoji-picker/config.toml`. Logs go to the user journal (rotated automatically). | See **Full teardown** |
| apt packages | **Nothing installed.** `python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`, `python3-evdev` and `fonts-noto-color-emoji` were all already present. **Don't remove them**: Ubuntu's own tools depend on `python3-gi`. | None |

## Full teardown

```bash
# 1. Stop and remove the service
systemctl --user disable --now emoji-picker
rm -f ~/.config/systemd/user/emoji-picker.service
systemctl --user daemon-reload && systemctl --user reset-failed

# 2. Remove runtime state and config
rm -rf ~/.local/state/emoji-picker ~/.config/emoji-picker

# 3. Remove uv (skip if you want to keep it for other projects)
rm -f ~/.local/bin/uv ~/.local/bin/uvx && rm -rf ~/.cache/uv ~/.local/share/uv

# 4. Only if it was changed during Task 1
gsettings reset org.gnome.mutter center-new-windows


# 6. Remove the project (this also deletes the 'untitled' note in the folder)
rm -rf ~/projects/emoji-picker
```

## Checking it's all gone

```bash
systemctl --user status emoji-picker          # "Unit emoji-picker.service could not be found."
ls ~/.local/state/emoji-picker ~/.config/emoji-picker 2>&1   # "No such file or directory"
command -v uv                                  # no output (if uv was removed)
gsettings get org.gnome.mutter center-new-windows            # false
```
