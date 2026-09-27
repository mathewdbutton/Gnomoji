# Emoji Picker

Double-tap **right Shift** anywhere in GNOME (Wayland) to open an emoji picker. Search or
browse, press Enter (or click), and the emoji is pasted into the field you were typing in.
Your clipboard is put back afterwards.

## Requirements

- **GNOME on Wayland.** Tested on Ubuntu 24.04 (GNOME 46). Other desktops and X11 are untested.
- Ubuntu/Debian (apt) or Fedora (dnf, untested). `./install.sh` installs what's missing.

## Install

Download `emoji-picker_<version>_all.deb` from the
[latest release](https://github.com/mathewdbutton/emoji-picker/releases/latest) and double-click
it. App Center opens; click **Install**. It warns that the package comes from outside the Ubuntu
store: that's expected for a download like this.

The first time it starts for you, a notification says the picker is ready, within a few
seconds. No log-out needed (on a reinstall or upgrade it just starts, with no notification).

What the package sets up:

- **Packages:** Python GTK 4, libadwaita and a colour emoji font, if missing. A standard Ubuntu
  GNOME desktop already has them.
- **Keyboard access:** a udev rule lets the person logged in at the screen read keyboards (to spot
  the right-Shift double-tap) and create a virtual keyboard (to send the paste keystroke). Access
  is tied to your active desktop session, like a webcam or sound card: other users and remote
  logins don't get it. See [Privacy and security](#privacy-and-security).
- **The picker** as a user service, turned on for every account on the computer. It starts when
  you log in.

Prefer a terminal? `sudo apt install ./emoji-picker_<version>_all.deb`

**Updating:** download the newer `.deb` and install it the same way. App Center shows **Install**
again for the newer version, and clicking it does the update. The running picker switches to the new version.

### From source

Clone the repo wherever you like, then run `./install.sh`. It checks what's missing, lists what it
needs sudo for, and asks once before doing it (say no and it prints the commands instead). The
service then runs from the cloned folder, so keep it where it is (or re-run `./install.sh` after
moving it). Don't also install the `.deb`: the clone's service takes precedence over it.

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
| Run `emoji-picker` again (`PYTHONPATH=src python3 -m emoji_picker` from a source checkout) | Toggles the picker (open if closed, close if open) |

## Configuration

Optional `~/.config/emoji-picker/config.toml`:

```toml
double_tap_ms = 300       # max gap between taps
restore_clipboard = true  # set false to leave the emoji on the clipboard
restore_delay_ms = 300    # restore after this if no app reads the emoji
release_after_read_ms = 50  # restore this long after the app reads the emoji
paste_delay_ms = 80       # wait for focus to return before pasting
```

Changes apply a moment after you save; no restart needed. If a value is invalid, the picker
keeps the previous setting and logs a warning (`journalctl --user -u emoji-picker -f`).

## Uninstall

**Installed from the `.deb`:** open the .deb you installed from in App Center again and click
**Uninstall** (Emoji Picker doesn't appear in App Center's search or installed list), or
`sudo apt remove emoji-picker`. If you no longer have the file, the apt command works (or download
it again). Your recents and config stay in your home folder; see [UNINSTALL.md](UNINSTALL.md) to
delete them.

**Installed from source:**

```bash
./uninstall.sh           # remove the service, keep recents, config and keyboard access
./uninstall.sh --purge   # also delete recents and config, and offer to remove the udev rule
```

[UNINSTALL.md](UNINSTALL.md) lists everything the picker adds to your machine.

## Privacy and security

The picker reads every key press so it can spot the right-Shift double-tap. It only checks
whether each one is right Shift: it never stores, logs or sends your keystrokes, and it has no
network code.

For that, the udev rule gives the person logged in at the screen direct access to keyboards and
to the virtual-keyboard device. That access isn't limited to the picker: any program you run gets
it too, so a malicious program could read your typing or type for you without needing an admin
password. Keyboard remappers such as keyd or xremap need the same access. The login screen,
other user accounts and remote logins don't get it. Uninstalling removes the rule; access
already granted ends when you log out.

The `.deb` is unsigned and its install scripts run as root, so only install one you got from
this project's GitHub releases or from someone you trust.

## Known limitations

- **Terminals:** many ignore Shift+Insert, so the paste doesn't land. The emoji is left on the
  clipboard only briefly, so set `restore_clipboard = false` if you want to paste it by hand.
- **Pages that drop focus:** some web pages (e.g. DuckDuckGo's search box) lose keyboard focus
  whenever the window does, so the paste has nowhere to go.
- **Only text is restored:** if your clipboard held an image or files, it may hold the emoji
  afterwards instead.

## Troubleshooting

- Logs: `journalctl --user -u emoji-picker -f`
- Nothing happens on double-tap: check the logs for a permissions message. Log out and back in,
  or reboot, so keyboard access applies. From source, re-run `./install.sh`, which checks it.
- An app pastes your old text instead of the emoji: it read the clipboard late. Raise
  `release_after_read_ms` (e.g. to 200).
- The emoji didn't paste into some app: nothing read it, so it stays on the
  clipboard for `restore_delay_ms` (default 300 ms) after being sent. Set `restore_clipboard = false` if that
  app needs a manual paste.
- App Center shows an error when opening the .deb: close App Center and open the file again.
- Picker never appears / very slow first open: check `fc-match "Noto Color Emoji" file`. If it
  points at a vector `NotoColorEmoji-Regular.ttf` instead of Ubuntu's bitmap `NotoColorEmoji.ttf`,
  that font's first layout can block the GTK main loop for minutes. The picker hides the
  upstream vector font for itself only (`src/emoji_picker/fonts.py`); nothing system-wide changes.
- A new emoji takes a moment to appear the first time, in any app: that same vector font is slow
  for every app, not just the picker. If `fc-match` points at it, removing it (e.g. from
  `/usr/local/share/fonts`, then `fc-cache -f`) makes apps use the fast bitmap font.

## Development

```bash
uv venv --system-site-packages --python /usr/bin/python3 && uv sync
uv run pytest && uv run ruff check
packaging/build-deb.sh                      # build dist/emoji-picker_<version>_all.deb from HEAD
.venv/bin/python -m emoji_picker.window   # preview the window without pasting
/usr/bin/python3 tools/build_emoji_data.py  # regenerate emoji.json (network)
```
