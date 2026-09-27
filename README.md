# Emoji Picker

Double-tap **right Shift** anywhere in GNOME (Wayland) to open an emoji picker. Search or
browse, press Enter (or click), and the emoji is pasted into the field you were typing in.
Your clipboard is put back afterwards.

## Requirements

- **GNOME on Wayland.** Tested on Ubuntu 24.04 (GNOME 46). Other desktops and X11 are untested.
- Ubuntu/Debian (apt) or Fedora (dnf, untested). `./install.sh` installs what's missing.

## Install

Clone the repo wherever you like, then:

```bash
./install.sh
```

It checks what's missing, lists what it needs sudo for, and asks once before doing it:

- **Packages:** Python GTK 4, libadwaita and a colour emoji font. A standard Ubuntu GNOME
  desktop already has all of them, so usually nothing is installed.
- **Keyboard access:** a udev rule (`udev/70-emoji-picker.rules`) lets the person logged in at
  the screen read keyboards (to spot the right-Shift double-tap) and create a virtual keyboard
  (to send the paste keystroke). Access is tied to your active desktop session, like a webcam
  or sound card: other users and remote logins don't get it, and no log-out is needed.

Then it installs a systemd user service that starts with your desktop session and runs from the
cloned folder, plus an icon and a hidden desktop entry (no sudo). The first time the picker starts,
a notification says it's ready. If you move the folder, run `./install.sh` again. Say no at the prompt and it
prints the commands so you can run them yourself.

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
./uninstall.sh           # remove the service, keep recents, config and keyboard access
./uninstall.sh --purge   # also delete recents and config, and offer to remove the udev rule
```

[UNINSTALL.md](UNINSTALL.md) lists everything the picker adds to your machine.

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
  `./install.sh`, which checks permissions. If it says access didn't apply, reboot and run it again.
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
