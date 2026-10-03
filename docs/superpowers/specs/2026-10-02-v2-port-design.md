# Emoji Picker 0.3.0: the GNOME Shell extension design on `main`, with .deb, .rpm and tarball (design)

**Status:** Draft for review (2026-10-02).

## Renamed to Gnomoji (2026-10-03)

Fedora already ships an unrelated package called `emoji-picker` (the ibus-typing-booster emoji
picker), so this project's package, built files, launcher command, app code dir, doc dir,
systemd service and visible name were renamed. Everywhere below that still says "Emoji Picker" /
`emoji-picker` in that sense, read "Gnomoji" / `gnomoji` instead (the rest of this document is
unchanged). Full brief: `.superpowers/sdd/2026-10-02-v2-port/rename-brief.md`.

| What | From | To |
|---|---|---|
| Package name (.deb `Package:`, .rpm `Name:`) | `emoji-picker` | `gnomoji` |
| Built files | `emoji-picker_<v>_all.deb`, `emoji-picker-<v>-1.noarch.rpm`, `emoji-picker-<v>.tar.gz` (prefix `emoji-picker-<v>/`) | `gnomoji_<v>_all.deb`, `gnomoji-<v>-1.noarch.rpm`, `gnomoji-<v>.tar.gz` (prefix `gnomoji-<v>/`) |
| Command / launcher | `/usr/bin/emoji-picker`, `~/.local/bin/emoji-picker`; template `packaging/emoji-picker` | `/usr/bin/gnomoji`, `~/.local/bin/gnomoji`; template `packaging/gnomoji` |
| App code dir (`@APPDIR@`) | `/usr/lib/emoji-picker`, `${XDG_DATA_HOME:-$HOME/.local/share}/emoji-picker` | `/usr/lib/gnomoji`, `${XDG_DATA_HOME:-$HOME/.local/share}/gnomoji` |
| Doc dir | `/usr/share/doc/emoji-picker` | `/usr/share/doc/gnomoji` |
| systemd user service | `emoji-picker.service` (template `systemd/emoji-picker.service`) | `gnomoji.service` (template `systemd/gnomoji.service`) |
| Visible name | "Emoji Picker" | "Gnomoji": window title, welcome notification titles, desktop entry `Name=`, extension `metadata.json` `name`/`description`, README/UNINSTALL/CLAUDE.md, install/uninstall messages |
| Extension log prefix | `[emoji-picker]` | `[gnomoji]` |

Kept unchanged: the extension UUID `emoji-picker@mathewdbutton.github.io`, the app id
`local.emojipicker.EmojiPicker`, the `~/.local/state/emoji-picker/` and
`~/.config/emoji-picker/` state/config folders, and the repo/folder name. (The Python package
`emoji_picker` was kept at the time of this rename but was itself renamed to `gnomoji` on
2026-10-03, in `src/gnomoji/`.)

**Supersedes:** triggering and inserting in `2026-09-25-emoji-picker-design.md` (the clipboard
design), and the udev parts of `2026-09-27-deb-package-design.md`. Both stay the reference for
everything this spec doesn't change: the picker window, emoji data, search, recents, skin tone,
Clear, config reload and the fast-font fix.

## Intent

Same product: double-tap **right Shift**, pick an emoji, and it goes into the text field you
were typing in. Version 0.3.0 changes three things:

1. **How the double-tap is noticed and the emoji inserted.** A small GNOME Shell extension does
   both, as designed and built on the parked branch `build/shell-extension` ("v2"). No
   clipboard, no keyboard reading, no virtual keyboard, no udev rule, no `sudo` for the
   picker itself.
2. **It reaches Fedora.** A friend runs Fedora. Support GNOME 46 (Ubuntu 24.04) to GNOME 50
   (Fedora 44, Ubuntu 26.04).
3. **Three ways to install:** a `.deb`, an `.rpm`, and a tarball with an install script that
   needs no root and works on any distro with GNOME.

**Why now:** v2 was parked on 2026-09-27 over a ~1 s delay on the first emoji in each Firefox
text box. That test ran with a slow vector (COLRv1) emoji font installed, which was found
later the same day to make other apps slow the first time they draw each emoji. Retested on
2026-10-02 with only the bitmap font: instant in a fresh text box, in a second box, and after
restarting Firefox.

**Decisions (user, 2026-10-02):**
- v2 **replaces** v1. There is no clipboard fallback, so apps without GNOME input-method focus
  (Qt apps like Konsole, X11 apps) can't receive emoji.
- Ship all three: tarball + install script, `.deb`, `.rpm`.
- Not Flatpak: the extension can't be shipped inside a Flatpak, so it would be two installs from
  two stores, both reviewed.
- Not now: moving the whole picker into the extension (a single install from
  extensions.gnome.org). Possible later as its own spike.

## How the port is done

New branch `build/v2-port` off current `main` (worktree `../emoji-picker-port`). v2's pieces
are copied across from `build/shell-extension` by hand, as files, not merged: the two branches
share no history since `main`'s history was rewritten, and that branch still holds unscrubbed
notes. Nothing from it is pushed.

## The app

**Removed** (as on v2):
- `trigger.py`, `linux_input.py` (keyboard watcher), `injector.py` (virtual keyboard),
  `clipboard.py`, and their tests.
- `udev/70-emoji-picker.rules`, and install.sh's package/rule/sudo steps.
- The clipboard-era settings `restore_clipboard`, `restore_delay_ms`, `paste_delay_ms`,
  `release_after_read_ms`. An old config file that still has them logs "unknown key" for
  each and otherwise works.

**Added from v2:**
- `extension/`: `extension.js`, `tapDetector.js`, `insertWaiter.js`, `metadata.json`.
  `metadata.json` declares `"shell-version": ["46", "47", "48", "49", "50"]`, once the
  GNOME 50 check (Testing, step 1) passes.
- `src/emoji_picker/shell.py`: the D-Bus link (`ShellLink`).
- v2's `flow.py`: on a pick, add to recents, **hide the window first**, then
  `ShellLink.insert(char)`. The `DoubleTap` signal toggles the picker.
- Tests: `tests/extension/*.js` (run with `gjs -m` through `tests/test_extension_js.py`,
  skipped without `gjs`), `test_extension_files.py`, `test_shell.py`, and v2's `test_flow.py`
  adapted to `main`'s window.

**Changed from v2:**
- **`insert_delay_ms` is dropped**, from the config, the D-Bus `Configure` keys, the extension
  and the docs. It was added while chasing the Firefox delay, which turned out to be the font.
  `Configure(a{sv})` keeps one key: `double-tap-ms` (`u`, at least 50).
- **Config reload stays.** `main`'s `Reloader` keeps working; when `double_tap_ms` changes, the
  app re-sends `Configure`.

**Kept from `main`, unchanged:** the window (skin tone list, Clear button, tabs, keyboard
navigation, click-away), `emoji_data.py`, `selection.py`, `fonts.py`, the software renderer
default, the app id `local.emojipicker.EmojiPicker` and its 🤏 icon, and toggling by running
`emoji-picker` again.

The D-Bus interface, the trigger (Mutter's locate-pointer key) and the insert (the input
method's commit, waiting for focus to return) are as in v2's spec
(`build/shell-extension:docs/superpowers/specs/2026-09-27-shell-extension-design.md`), minus
`insert-delay-ms`. That spec's text is carried into this repo's docs (see Docs).

## Switching the extension on

GNOME turns extensions on per person, and only notices newly installed extension files at
log-in. A system package can't do the first for anyone.

- **On its first start for a person**, the app adds the extension's UUID
  (`emoji-picker@mathewdbutton.github.io`) to `org.gnome.shell enabled-extensions` and removes
  it from `disabled-extensions` (the latter wins). It does this **once**: the existing
  first-start marker (`~/.local/state/emoji-picker/welcomed`) gates it, so a person who later
  switches it off in the Extensions app keeps it off.
- **The welcome notification** (existing `welcome.py`, with its retries) then says one of:
  - "Emoji Picker is ready. Double-tap right Shift in a text field." if the extension is
    already running (it answers on D-Bus); or
  - "Log out and back in once to finish setting up Emoji Picker." otherwise.
- `install.sh` enables the extension the same way and prints the same message.
- A person who installed 0.2.x already has `welcomed`, so that marker can't gate the switch-on.
  It gets its own marker, `~/.local/state/emoji-picker/extension-enabled`: no marker means
  switch on, write the marker, and send the welcome (in the right state), even if `welcomed`
  exists. So upgraders get the switch-on and the "log out once" message once too.

## Install layout

All three routes install the same tree; only the prefix differs.

| Piece | `.deb` / `.rpm` | `install.sh` (no root) |
|---|---|---|
| Extension | `/usr/share/gnome-shell/extensions/emoji-picker@mathewdbutton.github.io/` | `~/.local/share/gnome-shell/extensions/emoji-picker@mathewdbutton.github.io/` |
| App code | `/usr/lib/emoji-picker/emoji_picker/` | `~/.local/share/emoji-picker/emoji_picker/` |
| Launcher | `/usr/bin/emoji-picker` | `~/.local/bin/emoji-picker` |
| Service | `/usr/lib/systemd/user/emoji-picker.service`, enabled globally | `~/.config/systemd/user/emoji-picker.service`, enabled for the user |
| Desktop entry, icon | `/usr/share/applications/`, `/usr/share/icons/hicolor/…` | `~/.local/share/applications/`, `~/.local/share/icons/hicolor/…` |
| Uninstaller | (package manager) | `~/.local/share/emoji-picker/uninstall.sh` |

- App code moves out of Python's own folder (`/usr/lib/python3/dist-packages` today) to
  `/usr/lib/emoji-picker`, reached with `PYTHONPATH` in the service, launcher and desktop
  entry. Fedora's site-packages path changes with each Python version; this one doesn't, and
  both formats share it.
- The service keeps `ConditionUser=!@system` (no picker on the login screen) and
  `PartOf=graphical-session.target`.
- **`install.sh` copies**, never symlinks, so the downloaded folder can be deleted after. It
  works the same from a clone (re-run it after changing code). It never runs `sudo`: if Python
  GTK 4, libadwaita, the emoji font or GNOME Shell are missing, it prints the `apt`/`dnf`
  command and stops.
- **Installing both a package and `install.sh`:** the home-folder copies win: systemd prefers
  the user's unit, and GNOME loads a user extension over a system one with the same UUID (to
  confirm during hands-on). Documented, not prevented.

## Uninstalling

- `.deb` / `.rpm`: removal deletes the files and disables the service globally. It can't reach
  each user's settings, so the extension stays listed in `enabled-extensions` (harmless), and
  `org.gnome.mutter locate-pointer-key` stays `Shift_R` (GNOME doesn't disable extensions at
  log-out, so it's still set). It only matters if someone uses GNOME's Locate Pointer feature,
  which is off by default. `UNINSTALL.md` gives the fix:
  `gsettings reset org.gnome.mutter locate-pointer-key`.
- `uninstall.sh`: disables and removes the extension, removes it from both extension lists,
  resets `locate-pointer-key` if it is `Shift_R`, removes the service, launcher, desktop entry,
  icon and app code. `--purge` also deletes `~/.local/state/emoji-picker` and
  `~/.config/emoji-picker`.
- **Upgrading from 0.2.x** removes the `.deb`'s udev rule (it's no longer in the package). A
  rule left in `/etc/udev/rules.d/` by an old clone install isn't the package's; `UNINSTALL.md`
  says to delete it.

## Packages

One build script, `packaging/build.sh [OUT_DIR]`, builds from `git archive HEAD` (committed
files only, as today) into `dist/`:

- `emoji-picker_<version>_all.deb` (`dpkg-deb`)
- `emoji-picker-<version>-1.noarch.rpm` (`rpmbuild` with a spec file that packages the
  prebuilt tree; `rpm` is installable on Ubuntu, so one machine builds both)
- `emoji-picker-<version>.tar.gz`: install-only, not a repo snapshot — just what
  `install.sh`/`uninstall.sh` need plus user docs, under `emoji-picker-<version>/` with
  `install.sh` at the top. (Later renamed `gnomoji-<version>.tar.gz`; GitHub's own "Source
  code" download already covers the full repo.)

| | `.deb` | `.rpm` |
|---|---|---|
| Requires | `python3 (>= 3.11)`, `python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`, `fonts-noto-color-emoji`, `gnome-shell (>= 46)` | `python3 >= 3.11`, `python3-gobject`, `gtk4`, `libadwaita`, `google-noto-color-emoji-fonts`, `gnome-shell >= 46` |
| After install/upgrade | enable globally; restart the service in every running user manager with an active graphical session | the same |
| Before removal | disable globally (removal only, not upgrade) | the same (`%preun` when `$1 = 0`) |

The after-install and before-removal logic lives in one shell script each, shared by
`postinst`/`prerm` and `%post`/`%preun`, so it's written once. Every step past unpacking stays
best-effort and never fails the install, as today. The udev steps go. Bytecode: the `.deb`
keeps `py3compile`/`py3clean`, pointed at `/usr/lib/emoji-picker`; the `.rpm` runs
`python3 -m compileall -q /usr/lib/emoji-picker` in `%post` and deletes its `__pycache__`
folders in `%preun` on removal, so nothing is left behind.

Version: **0.3.0** in `pyproject.toml`, used by all three.

## CI

`.github/workflows/package.yml`:
- **Every pull request:** run pytest with `gjs` installed (so the extension's JS tests run),
  build all three, install and remove the `.deb` in an Ubuntu container and the `.rpm` in a
  `fedora:44` container (the smoke test checks the files land and leave, as today).
- **A `v*` tag:** check the tag matches the version, then a **draft** release with all three
  files.

None of this runs until the user decides to push (`main` is unpushed and untagged on purpose).

## Testing

In order:

1. **GNOME 50 check, before building on it.** In a Fedora 44 VM (GNOME Boxes on the user's
   Ubuntu machine): install with `install.sh` from a clone of `build/v2-port` at that point,
   log out and in, then: does a right-Shift double-tap open the picker, do right-Shift capitals
   not open it, and does a pick reach GNOME Text Editor and Firefox? If the locate-pointer
   trick or the insert fails on GNOME 50, stop and rethink the Fedora side before packaging.
2. **Automated tests, written first** (TDD): the extension's JS modules; `ShellLink`; the flow
   (hide-then-insert order, toggle on `DoubleTap`, re-`Configure` on `Ready` and on config
   reload); the first-start switch-on (once only; not after the user switches it off; once for
   upgraders from 0.2.x); the welcome text in both states; the config without the clipboard
   keys; package contents for all three formats; the shared maintainer scripts against fake
   `systemctl`/`loginctl`, as `test_maintainer_scripts.py` does today.
3. **Hands-on, the user's Ubuntu 24.04 machine:** first `./uninstall.sh` the v2 test install
   from `build/shell-extension`. Then upgrade the installed 0.2.1 `.deb` to 0.3.0, check the
   "log out once" welcome, log out and in, and pick into Text Editor, Firefox and Slack. Check
   skin tone, Clear, Esc, click-away, right-Shift capitals, and that the clipboard is
   untouched. Then remove the `.deb` and try the tarball route.
4. **Hands-on, the Fedora 44 VM:** the `.rpm`, then (after removing it) the tarball's
   `install.sh`.

## Docs

- `README.md`: rewritten for 0.3.0: what it does (no clipboard), the three install routes,
  requirements (GNOME 46-50 on Wayland), the "log out once" step, the apps it can't reach.
  The "Privacy and security" section becomes much shorter (no keyboard access).
- `UNINSTALL.md`: every file each route installs; the Locate Pointer reset; the leftover
  `/etc` udev rule from old clone installs.
- `CLAUDE.md`: drop the clipboard, uinput, udev and evdev platform facts; add the extension
  facts from v2 (extensions can't see keys going to apps, so the locate-pointer trick; the
  insert waits for focus and input-method focus; extension changes load only at log-in; the
  GNOME 50 result). Keep the font, popover and renderer facts. Update commands and the release
  steps.
- The two older specs get a one-line pointer to this one at the top.
- This spec gets an "Acceptance results" section after hands-on.

## Known limitations

- Qt apps (e.g. Konsole) and X11 apps can't receive emoji; the double-tap does nothing there.
- Pages that drop focus when the window changes (e.g. DuckDuckGo's search box) lose the insert.
- GNOME on Wayland only. Each new GNOME release needs `metadata.json` updated (and a check).
- A first install, by any route, needs one log-out before the double-tap works.

## Acceptance results (2026-10-03)

| # | Check | Result | Notes |
|---|---|---|---|
| 1 | GNOME 50: Fedora 44 Workstation VM, `install.sh` from a tarball | PASS | GNOME Shell 50.0; no extra packages needed; extension ACTIVE after one log-out; picks into Text Editor and Firefox; right-Shift capitals don't open it. |
| 2 | Ubuntu 24.04 `.deb`, clean install | PASS | "Log out once" welcome; after log-out the extension loads from `/usr/share/gnome-shell/extensions/`. (A first try straight over 0.2.1 showed "ready": GNOME still held the removed v2 test extension in memory. A clean reinstall after a log-out behaved as designed.) |
| 3 | Ubuntu picks | PASS | Instant in Text Editor, Firefox (fresh box, second box) and Slack: the old Firefox first-insert delay is gone. |
| 4 | Ubuntu picker features | PASS | Skin tone list, Clear, Esc, click-away, right-Shift capitals, clipboard untouched after a pick. The package ships no udev rule. |
| 5 | Fedora 44 `.rpm` | PASS | Installed as a local file through GNOME Software (shows "Potentially Unsafe / Provided by a third party", as for any side-loaded package); welcome shown; picks work. `dnf remove gnomoji` leaves no `/usr/lib/gnomoji`. |
| 6 | Tarball route on Ubuntu | Skipped | Same `install.sh`, covered by check 1 and the install-script tests. |

Found during acceptance: Fedora already ships a package called `emoji-picker` (the
ibus-typing-booster picker), which shadowed ours in GNOME Software and would have clashed on
`/usr/bin/emoji-picker`. Hence the rename to Gnomoji (see the note at the top).

Follow-ups (not in 0.3.0): AppStream metadata so GNOME Software shows the name "Gnomoji" and the
🤏 icon instead of "gnomoji" and a generic gear; possibly systemd sandboxing for the app's service.
