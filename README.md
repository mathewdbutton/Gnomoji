# Emoji Picker

Double-tap **right Shift** anywhere in GNOME (Wayland) to open an emoji picker. Search or
browse, press Enter (or click), and the emoji is pasted into the field you were typing in.
Your clipboard is put back afterwards.

## Requirements

Ubuntu 24.04 / GNOME on Wayland, and these apt packages:

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-evdev fonts-noto-color-emoji
```

Your user must be in the `input` group (`groups | grep input`). If not:
`sudo usermod -aG input $USER`, then log out and back in.

## Install

```bash
mkdir -p ~/.config/systemd/user
cp systemd/emoji-picker.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now emoji-picker
```

The unit expects the repo at `~/projects/emoji-picker`. Edit `PYTHONPATH` in the unit if it lives elsewhere.

## Use

| Key | Action |
|---|---|
| Right Shift ×2 | Open / close |
| Type | Search (the first match is selected) |
| Arrows | Move the selection |
| Enter | Insert the selected emoji (does nothing if none is selected) |
| Click | Insert the clicked emoji |
| Page Up / Page Down | Scroll a page at a time |
| Esc | Close |
| Ctrl+Tab / Ctrl+Shift+Tab | Next / previous category |
| `python3 -m emoji_picker` again | Toggles the picker (open if closed, close if open) |

## Configuration

Optional `~/.config/emoji-picker/config.toml`:

```toml
double_tap_ms = 300       # max gap between taps
restore_clipboard = true  # set false to leave the emoji on the clipboard
restore_delay_ms = 300    # restore after this if no app reads the emoji (normally ~50 ms after it's read)
paste_delay_ms = 80       # wait for focus to return before pasting
```

Restart after changes: `systemctl --user restart emoji-picker`.

## Uninstall

Emergency stop: `systemctl --user stop emoji-picker`. For the full list of what's
installed at each step and how to remove all of it, see [UNINSTALL.md](UNINSTALL.md).

## Troubleshooting

- Logs: `journalctl --user -u emoji-picker -f`
- Nothing happens on double-tap: check the logs for a permissions message.
- The emoji didn't paste into some app: nothing read it, so it stays on the
  clipboard for `restore_delay_ms` (default 300 ms) after being sent. Set `restore_clipboard = false` if that
  app needs a manual paste.
- Picker never appears / very slow first open: check `fc-match "Noto Color Emoji" file`. If it
  points at a vector `NotoColorEmoji-Regular.ttf` instead of Ubuntu's bitmap `NotoColorEmoji.ttf`,
  that font's first layout can block the GTK main loop for minutes. The picker hides the
  upstream vector font for itself only (`src/emoji_picker/fonts.py`); nothing system-wide changes.

## Development

```bash
uv venv --system-site-packages --python /usr/bin/python3 && uv sync
uv run pytest && uv run ruff check
.venv/bin/python -m emoji_picker.window   # preview the window without pasting
/usr/bin/python3 tools/build_emoji_data.py  # regenerate emoji.json (network)
```
