# Emoji Picker: notes for Claude

A Mac-style emoji picker for GNOME on **Wayland** (built on Ubuntu 24.04 / GNOME 46).
Double-tap **right Shift**, search or browse, press Enter, and the emoji is pasted into the
focused field. The old clipboard **text** comes back afterwards.

Machine-specific notes, project status and working preferences live in `CLAUDE.local.md`
(git-ignored, so it may not exist). Anything about one particular machine or person goes there,
never in this file.

## Read these before changing anything

- `docs/superpowers/specs/2026-09-25-emoji-picker-design.md` is the design and the source of truth.
  Its **"Feasibility results"** section records platform facts proven by hand. Don't
  "simplify" code that depends on them.
- `UNINSTALL.md` lists everything the project puts outside the repo. **Any change that
  touches something outside the repo must update it in the same commit.**
- `README.md` covers install, use, config and troubleshooting.
- **User-facing files stay general**: `README.md`, `UNINSTALL.md`, `install.sh`, `uninstall.sh`,
  `udev/`, `systemd/` and `desktop/`. People install from them on fresh machines.

## Hard-won platform facts (don't regress these)

- **Paste chord is Shift+Insert.** GTK apps ignore Ctrl+Shift+V. Terminals are out of scope.
- **The clipboard can only be claimed during user input in our window.** `PasteFlow.pick`
  must call `ClipboardKeeper.claim` synchronously from the Enter/click handler, before
  hiding. A claim from a timer is silently refused.
- **Never claim the clipboard a second time.** After the initial claim, we only change
  what our `SwitchingText` provider serves (arm) or give up ownership (release,
  `set_content(None)`); see the next bullet.
- **Mutter caches the clipboard's text/plain value the instant a claim happens**, and
  serves that cached copy once our ownership ends. This is why we claim/arm/release rather
  than claim-and-swap-back: claim with a **decoy** (the saved old text) so Mutter's instant
  copy is the old text, not the emoji; **arm** (switch the provider to the emoji) right before
  the paste chord; **release** (`set_content(None)`) afterwards so Mutter takes over serving
  the decoy, with no need to keep the picker running or keep our window focused. Claiming
  still needs input in our window (see above); releasing does not. Release happens
  `release_after_read_ms` (50 ms) after the target app's last read of the emoji
  (`arm(on_read=...)`; each read restarts the wait), with `restore_delay_ms` as the fallback
  when nothing reads it.
- **On re-show, GTK may not re-emit `notify::is-active`** (it can keep `is-active` True
  across hide/show), so `_on_active_changed`'s `on_focused → save()` path can be silently
  skipped, leaving a stale saved text served as the decoy. But GTK reliably emits the
  clipboard's own `changed` signal carrying the current offer when our window gains focus
  (Wayland only sends selection offers to the focused client), so `ClipboardKeeper` also
  listens for `changed` and re-`save()`s on any non-local change that carries text.
  `show_picker` also calls `_on_active_changed()` once so click-away works after re-show.
- **PyGObject 3.48:** `SwitchingText.do_get_value(self)` must return `(True, text)`. Async
  `do_write_mime_type_async` is broken when GTK calls it from C. Tests check the provider
  through GTK's C API with ctypes (`served_by_gtk` in `tests/test_clipboard.py`).
- **Only text is restored.** An image or file on the clipboard is replaced by the emoji
  (accepted limitation).
- **Keyboard remappers (Toshy, keyd, xremap) grab the physical keyboards** and re-emit keys
  from their own virtual keyboard. The watcher must NOT ignore other virtual keyboards; it only
  skips our own 2-key one (`Injector.NAME`).
- **Keyboard and `/dev/uinput` access comes from `udev/70-emoji-picker.rules`**: `TAG+="uaccess"`
  on keyboards and uinput. logind's `73-seat-late.rules` turns the tag into an ACL for the active
  seat user on the `change` trigger, so no group and no log-out. `install.sh` tests real access,
  not group membership, and asks once before running sudo for packages and the rule. Older
  installs used `70-emoji-picker-uinput.rules` + the `input` group; `uninstall.sh --purge`
  removes either rule.
- **No python-evdev:** `linux_input.py` does the evdev reads and the uinput keyboard with stdlib
  `fcntl`/`struct`. Its ioctl numbers are tested against the kernel's values, and
  `tests/test_linux_input.py` has a real uinput round trip (skipped without access).
- **GNOME needs ~6 s to notice a new desktop file** (measured, GNOME 46). Until then
  `org.gtk.Notifications.AddNotification` fails with `InvalidApp` and the notification is lost;
  `Gio.Application.send_notification` hides that error. So the welcome goes over D-Bus directly
  (`__main__._notifications`) and `Welcome` retries every second (up to 30 s).
- **GNOME Shell only rescans icons when the theme's top folder's mtime changes**, not a
  subfolder's. `install.sh`/`uninstall.sh` `touch ~/.local/share/icons/hicolor` after changing the
  icon; without it notifications show "icon missing" placeholders until the next log-in.
- **Memory: judge by PSS, not RSS** (`/proc/<pid>/smaps_rollup`); over half of RSS is shared
  libraries. GTK's GPU renderer loads Mesa/LLVM/Vulkan (+~70 MB RSS) and grows texture caches,
  so `__main__.py` defaults `GSK_RENDERER=cairo` (an explicit env var still wins). Measured:
  214 MB RSS / 104 MB PSS → 112 MB RSS / 61 MB PSS, flat with use. The emoji count barely
  matters. Don't remove it without measuring.
- **fontconfig can resolve "Noto Color Emoji" to a slow vector (COLRv1) font**, e.g. a hand-installed
  `NotoColorEmoji-Regular.ttf` outranking the distro's fast CBDT bitmap font. First layout of
  ~1,900 emoji then blocks the GTK main loop for minutes. `fonts.py`'s `use_fast_emoji_font()`
  points `FONTCONFIG_FILE` at a bundled conf that hides it, for our process only, and must run
  before the first `from gi.repository import ...` anywhere (that import initialises fontconfig;
  `import gi` / `gi.require_version()` alone don't). The same font makes *other* apps slow to
  draw each new emoji the first time, which looks like a paste delay; the picker's side is ~0.1 s.
- **Config reloads live** (`config.Reloader` fed by a `Gio.FileMonitor` in `__main__`, kept on
  `self`: a garbage-collected monitor silently stops). `PasteFlow` snapshots the config at pick
  time (`_active`), so a reload mid-paste can't split a decoy claim from its release.
- **The window opens where GNOME places it** (top-left by default).
- **The picker can't reopen where it was dragged.** Hiding unmaps it, so GNOME re-places it.
  Minimise-instead-of-hide keeps the position, but `present()` from our keyboard trigger (not
  input in our window) gets no focus: GNOME shows a "… is ready" notification instead.

## Commands

```bash
uv run pytest -q && uv run ruff check            # 149 tests, lint (ruff flags unused noqa, RUF100)
PYTHONPATH=src timeout 120 /usr/bin/python3 -m emoji_picker   # foreground run
.venv/bin/python -m emoji_picker.window          # window preview; doesn't paste (steals focus!)
journalctl --user -u emoji-picker -f             # service logs, once installed
```

Runtime uses **only** `/usr/bin/python3` plus distro packages. `.venv` (uv, `--system-site-packages`)
is for pytest/ruff only. No pip packages at runtime. The installed service runs from the working
tree, so the checked-out branch is what runs.

## Parked alternative: v2 on branch `build/shell-extension`

A GNOME Shell extension version (no clipboard, no udev) is built on `build/shell-extension`, but
parked: in Firefox the first emoji inserted into each text box shows ~1 s late (Firefox side,
unexplained). See that branch's `docs/superpowers/specs/2026-09-27-shell-extension-design.md`
"Acceptance results". `main` stays on this clipboard design. An IBus input method is the
"proper" future approach (see the spec's Follow-ups).
