# Emoji Picker

Double-tap **right Shift** in a text field in GNOME (Wayland) to open an emoji picker. Search
or browse, then Enter (or click) types the emoji straight into the field. A small GNOME Shell
extension does the typing: no clipboard, no special keyboard access, and no `sudo` for the
picker itself.

## Requirements

- **GNOME 46-50 on Wayland.** Tested on Ubuntu 24.04 (GNOME 46). GNOME 47-50 (for example
  Fedora 44, Ubuntu 26.04) is supported but not yet tested by hand.
- Python 3.11+ with GTK 4, libadwaita and the Noto Color Emoji font. All of this is standard on
  an Ubuntu or Fedora GNOME desktop already.

## Install

Pick whichever fits. All three install the same app; only how they get onto your machine
differs.

### Ubuntu/Debian (.deb)

Download `emoji-picker_<version>_all.deb` from the
[latest release](https://github.com/mathewdbutton/emoji-picker/releases/latest) and
double-click it. App Center opens; click **Install**. It warns that the package comes from
outside the Ubuntu store: that's expected for a download like this.

Prefer a terminal? `sudo apt install ./emoji-picker_<version>_all.deb`

### Fedora (.rpm)

Download `emoji-picker-<version>-1.noarch.rpm` from the
[latest release](https://github.com/mathewdbutton/emoji-picker/releases/latest), then:

```bash
sudo dnf install ./emoji-picker-<version>-1.noarch.rpm
```

### Any distro, no sudo (tarball)

```bash
tar -xzf emoji-picker-<version>.tar.gz
cd emoji-picker-<version>
./install.sh
```

It checks what's missing and prints the `apt`/`dnf` command for it if so (it never runs
`sudo` itself). Once it's done, you can delete the folder.

### After any of these

**Log out and back in once.** GNOME only notices a newly installed extension at log-in; a
notification tells you if this is needed. After that, double-tap right Shift in a text field.

**Updating:** install the newer `.deb`, `.rpm` or tarball the same way (re-run `install.sh`
for the tarball).

Don't mix a package with `install.sh` on the same machine: the home-folder copy from
`install.sh` wins over the package's.

### From source

Clone the repo, then run `./install.sh`. It copies the code into your home folder, so re-run
it after you change anything. To try your changes without installing, point `install.sh` at
the clone first: the extension has to be installed for the double-tap to work at all, there's
no way to run the picker standalone.

## Use

| Key | Action |
|---|---|
| Right Shift ×2 | Open / close |
| Type | Search (the first match is selected) |
| Arrows | Move the selection |
| Enter | Insert the selected emoji (does nothing if none is selected) |
| Click | Insert the clicked emoji |
| Page Up / Page Down | Scroll a page at a time |
| Esc | Close (or close the skin tone list, if open) |
| Ctrl+Tab / Ctrl+Shift+Tab | Next / previous category |
| Click ✋ (next to the search box) | Choose a skin tone. It applies to every emoji that has tones, except "Recently used", which keeps the tone you picked each one in. It's remembered. |
| Click **Clear** (on the "Recently used" heading) | Empty the recently used list. It fills up again as you pick. |
| Run `emoji-picker` again | Toggles the picker (open if closed, close if open) |

## Configuration

Optional `~/.config/emoji-picker/config.toml`:

```toml
double_tap_ms = 300   # max gap between the right-Shift taps (50-2000)
```

Changes apply a moment after you save; no restart needed. If a value is invalid, the picker
keeps the previous setting and logs a warning (`journalctl --user -u emoji-picker -f`).

An old config file from 0.2 may still have `restore_clipboard`, `restore_delay_ms`,
`paste_delay_ms` or `release_after_read_ms`: those were clipboard settings and no longer do
anything. The picker logs "unknown config key" for each and otherwise works fine.

## Apps it can't type into

- **Qt apps** (e.g. Konsole) **and X11 apps.** The double-tap does nothing there: GNOME's
  extensions can only type into apps using GNOME's own input method, which Qt and X11 apps
  don't use.
- **Pages that drop keyboard focus when another window opens** (e.g. DuckDuckGo's search
  box). The picker is a separate window, so the insert has nowhere to land.

## Privacy and security

The picker doesn't read your keystrokes and never touches the clipboard. The extension
reacts only to GNOME's own "locate pointer" key (set to right Shift while the picker is
running) and types only the emoji you click or press Enter on.

## Uninstall

See [UNINSTALL.md](UNINSTALL.md) for every file each route installs and how to remove it.
Short version:

- `.deb`: `sudo apt remove emoji-picker`
- `.rpm`: `sudo dnf remove emoji-picker`
- tarball / source: `~/.local/share/emoji-picker/uninstall.sh` (add `--purge` to also delete
  your recents, skin tone and config)

## Troubleshooting

- **Double-tap does nothing:**
  `gnome-extensions info emoji-picker@mathewdbutton.github.io` should say `State: ACTIVE`. If
  it doesn't, log out and back in, or switch it on by hand in the Extensions app.
- **Logs:**
  ```bash
  journalctl --user -u emoji-picker -f                                  # the app
  journalctl -f -o cat /usr/bin/gnome-shell | grep emoji-picker         # the extension
  ```
- **A new emoji takes a moment to appear the first time, in any app:** a hand-installed
  vector (COLRv1) Noto Color Emoji font is slow to draw each emoji the first time, for every
  app, not just the picker. Check `fc-match "Noto Color Emoji" file`: if it points at a
  `NotoColorEmoji-Regular.ttf` rather than a bitmap `NotoColorEmoji.ttf`, removing the vector
  one (e.g. from `/usr/local/share/fonts`, then `fc-cache -f`) fixes it for every app. The
  picker already hides that font for itself only, so its own picks are never slow.

## Development

```bash
uv venv --system-site-packages --python /usr/bin/python3 && uv sync
uv run pytest -q && uv run ruff check
packaging/build.sh                        # builds the .deb, .rpm and .tar.gz from HEAD into dist/
.venv/bin/python -m emoji_picker.window   # preview the window; doesn't insert (steals focus!)
/usr/bin/python3 tools/build_emoji_data.py  # regenerate emoji.json (network)
```
