# Emoji Picker

Double-tap **right Shift** anywhere in GNOME (Wayland) to open an emoji picker. Search or
browse, press Enter (or click), and the emoji is pasted into the field you were typing in.
Your clipboard is put back afterwards.

## Requirements

- **GNOME on Wayland.** Tested on Ubuntu 24.04 (GNOME 46). Other desktops and X11 are untested.
- Python 3.11+ with GTK 4, libadwaita and python-evdev, plus a colour emoji font:

  ```bash
  # Ubuntu / Debian
  sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-evdev fonts-noto-color-emoji
  # Fedora (untested)
  sudo dnf install python3-gobject gtk4 libadwaita python3-evdev google-noto-color-emoji-fonts
  ```

### Permissions (one-off, needs sudo)

The picker needs two things a normal app doesn't:

1. **Reading the keyboard**, to spot the right-Shift double-tap anywhere on screen. That means
   being in the `input` group:

   ```bash
   sudo usermod -aG input "$USER"
   ```

   Be aware: this lets **any** program you run read all keyboard input, not just this one.
   Keyboard remappers (Toshy, keyd, xremap) need the same access. If you're already in the
   group for one of those, you're set.

2. **A virtual keyboard**, to send the paste keystroke (Shift+Insert). Most distros only let
   root create one, so install the included udev rule. It lets the `input` group use
   `/dev/uinput`:

   ```bash
   sudo cp udev/70-emoji-picker-uinput.rules /etc/udev/rules.d/
   sudo udevadm control --reload && sudo udevadm trigger --subsystem-match=misc --action=change
   ```

Then **log out and back in** so the group change applies. `./install.sh` checks both and tells
you exactly what's missing.

## Install

Clone the repo wherever you like, then:

```bash
./install.sh
```

This installs a systemd user service that starts with your desktop session and runs from the
cloned folder. If you move the folder, run `./install.sh` again.

To try it without installing, run `PYTHONPATH=src /usr/bin/python3 -m emoji_picker` from the repo
(Ctrl+C to stop).

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
restore_delay_ms = 300    # restore after this if no app reads the emoji
release_after_read_ms = 50  # restore this long after the app reads the emoji
paste_delay_ms = 80       # wait for focus to return before pasting
```

Restart after changes: `systemctl --user restart emoji-picker`.

## Uninstall

```bash
./uninstall.sh           # remove the service, keep recents and config
./uninstall.sh --purge   # also delete recents and config
```

To also undo the permission changes, see [UNINSTALL.md](UNINSTALL.md).

## Known limitations

- **Terminals:** many ignore Shift+Insert, so the paste doesn't land. The emoji is left on the
  clipboard only briefly, so set `restore_clipboard = false` if you want to paste it by hand.
- **Pages that drop focus:** some web pages (e.g. DuckDuckGo's search box) lose keyboard focus
  whenever the window does, so the paste has nowhere to go.
- **Only text is restored:** if your clipboard held an image or files, it may hold the emoji
  afterwards instead.

## Troubleshooting

- Logs: `journalctl --user -u emoji-picker -f`
- Nothing happens on double-tap: check the logs for a permissions message, and re-run
  `./install.sh`, which checks permissions.
- An app pastes your old text instead of the emoji: it read the clipboard late. Raise
  `release_after_read_ms` (e.g. to 200).
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
