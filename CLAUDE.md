# Gnomoji: notes for Claude

Gnomoji brings a Mac-style emoji panel to GNOME on **Wayland** (built on Ubuntu 24.04 / GNOME
46; GNOME 47-50 supported too, see below). Double-tap **right Shift**, search or browse, press
Enter, and a small GNOME Shell extension types the emoji into the focused field. No clipboard.

Machine-specific notes, project status and working preferences live in `CLAUDE.local.md`
(git-ignored, so it may not exist). Anything about one particular machine or person goes there,
never in this file.

## Read these before changing anything

- `docs/superpowers/specs/2026-10-02-v2-port-design.md` is the current design for how the
  double-tap is triggered and the emoji inserted (the GNOME Shell extension), and for all
  three install routes (`.deb`, `.rpm`, `install.sh`). Don't "simplify" code that depends on
  its facts.
- `docs/superpowers/specs/2026-09-25-emoji-picker-design.md` stays the reference for the
  window, emoji data, search, recents and skin tone — triggering and inserting there are
  superseded (see the pointer at its top).
- `docs/superpowers/specs/2026-09-27-deb-package-design.md` stays the reference for the `.deb`
  beyond what the v2-port spec changes (its udev parts are superseded; see its own pointer).
- `UNINSTALL.md` lists everything the project puts outside the repo, from all three install
  routes. **Any change that installs something outside the repo, by any route, must update it
  in the same commit.**
- `README.md` covers install, use, config and troubleshooting.
- **User-facing files stay general**: `README.md`, `UNINSTALL.md`, `install.sh`, `uninstall.sh`,
  `extension/`, `systemd/`, `desktop/` and `packaging/`. People install from them on fresh
  machines.

## Hard-won platform facts (don't regress these)

- **Extensions can't see keys going to apps**, so the trigger is Mutter's "locate pointer" key
  (`org.gnome.mutter locate-pointer-key`), which Mutter runs for extensions and still passes
  through to the app. `extension/extension.js` points it at `Shift_R` while enabled and counts
  taps on the `global` `'locate-pointer'` signal; it restores the previous value on disable.
  GNOME doesn't disable extensions at log-out, so if the picker was still enabled at your last
  log-out, `locate-pointer-key` is still `Shift_R` until something resets it (`uninstall.sh`
  does; see `UNINSTALL.md`).
- **The insert waits for focus to return** to the window that was focused at the double-tap,
  and for that window's text field to check in with GNOME's input method (10-25 ms normally;
  the extension gives up after 200 ms with focus back but no text field, or 1.5 s if focus
  never comes back). Apps without GNOME input-method focus — Qt apps like Konsole, X11 apps —
  can't be reached this way. There is deliberately no clipboard fallback.
- **`Insert` is armed once per double-tap.** Any process in the session can call it (no
  sender check, by decision), so the extension refuses it unless a `DoubleTap` armed it, takes
  the arm at once (a second `Insert` needs a new double-tap), and refuses text that couldn't be
  an emoji (`acceptInsert` in `extension/insertWaiter.js`: at most 32 code points, no C0/C1
  control characters). Picking from a picker opened with `gnomoji` rather than a
  double-tap therefore inserts nothing unless an unused double-tap is still armed.
- **Extension code only loads at the next log-in**, and GNOME only notices newly installed
  extension files at log-in too. Extensions are switched on per person, not system-wide, which
  is why `extension_setup.enable_once` exists: the app switches the extension on for the
  current person on its first start (gated by `~/.local/state/emoji-picker/extension-enabled`,
  kept separate from 0.2.x's `welcomed` marker so people upgrading from 0.2.x get the
  switch-on too, even though they already have `welcomed`). `uninstall.sh` takes the extension
  out of `enabled-extensions`, so it always deletes that marker (not only with `--purge`), and
  starts the package's service if a `.deb`/`.rpm` is installed too. Right after `enable_once`,
  GNOME Shell may not have turned the extension on yet, so the welcome's "ready or log out?"
  check (`welcome.ActiveCheck`) waits up to 3 s for `Ready` before asking for a log-out.
- **GNOME 50 works** (checked by hand 2026-10-03, Fedora 44 Workstation in a VM, GNOME Shell
  50.0): `install.sh` from a tarball needed no extra packages, the extension came up ACTIVE after
  one log-out, the locate-pointer trigger still works, picks went into Text Editor and Firefox,
  and right-Shift capitals don't open the picker. GNOME 47-49 untested.
- **GNOME needs ~6 s to notice a new desktop file** (measured, GNOME 46). Until then
  `org.gtk.Notifications.AddNotification` fails with `InvalidApp` and the notification is lost;
  `Gio.Application.send_notification` hides that error. So the welcome goes over D-Bus directly
  (`__main__._notifications`) and `Welcome` retries every second (up to 30 s).
- **GNOME Shell only rescans icons when the theme's top folder's mtime changes**, not a
  subfolder's. `install.sh`/`uninstall.sh` `touch ~/.local/share/icons/hicolor` after changing
  the icon; without it notifications show "icon missing" placeholders until the next log-in.
- **Memory: judge by PSS, not RSS** (`/proc/<pid>/smaps_rollup`); over half of RSS is shared
  libraries. GTK's GPU renderer loads Mesa/LLVM/Vulkan (+~70 MB RSS) and grows texture caches,
  so `__main__.py` defaults `GSK_RENDERER=cairo` (an explicit env var still wins). Measured:
  214 MB RSS / 104 MB PSS → 112 MB RSS / 61 MB PSS, flat with use. The emoji count barely
  matters. Don't remove it without measuring.
- **fontconfig can resolve "Noto Color Emoji" to a slow vector (COLRv1) font**, e.g. a
  hand-installed `NotoColorEmoji-Regular.ttf` outranking the distro's fast CBDT bitmap font.
  First layout of ~1,900 emoji then blocks the GTK main loop for minutes. `fonts.py`'s
  `use_fast_emoji_font()` points `FONTCONFIG_FILE` at a bundled conf that hides it, for our
  process only, and must run before the first `from gi.repository import ...` anywhere (that
  import initialises fontconfig; `import gi` / `gi.require_version()` alone don't). The same
  font makes *other* apps slow to draw each new emoji the first time, which looked like a ~1 s
  insert delay on v2's first Firefox test (2026-09-27, parked over it); retested 2026-10-02
  with only the fast bitmap font installed: instant in a fresh text box, a second box, and
  after restarting Firefox.
- **Config reloads live** (`config.Reloader` fed by a `Gio.FileMonitor` in `__main__`, kept on
  `self`: a garbage-collected monitor silently stops). On a change the app re-sends
  `Configure(a{sv})` to the extension with the new `double-tap-ms`; the extension also gets it
  fresh whenever it emits `Ready` (on enable), so whichever of the two starts first still ends
  up configured.
- **No popovers or dropdown popups in the picker.** A GTK popup is its own Wayland surface, and
  ~140 ms after one closes GNOME takes focus from the picker, so click-away closes it (measured,
  GNOME 46, with `Gtk.DropDown` and `Gtk.MenuButton` + `Gtk.Popover`). Taking focus back isn't
  possible (see `present()` below). The skin tone list is a plain box in a `Gtk.Overlay` instead.
- **The extension places the picker; the app can't** (Wayland). At the double-tap it saves
  `Main.inputMethod._cursorRect`, the text cursor in screen coordinates (private, same in GNOME
  46 and 50; set only while IBus runs; **not cleared when focus moves**, and **overwritten by the
  picker's own search box** once it opens, so it's read at the double-tap and must lie inside the
  window focused then). Hiding the picker destroys its window, so each opening is a new one; the
  extension recognises and moves it only on that window's `'shown'` signal, never
  `'window-created'`: on Wayland the wm class (app id) isn't set until `'shown'` (set by the
  client's `xdg_toplevel.set_app_id`, after `'window-created'` fires), and GNOME places windows
  after `'window-created'` too (`meta_window_force_placement`), so checking or moving there would
  miss it or be undone. Each pending window gets its own `'shown'`/`'unmanaged'` wait (a `Map`),
  since more than one can be created before any is shown. Rules in
  `extension/placement.js`: below the cursor, above it if there's no room, kept in the monitor's
  work area; otherwise the last-dragged spot (memory only, reset at log-out or screen lock:
  GNOME switches the extension off while locked); otherwise GNOME's placement.
  Minimise-instead-of-hide was tried before and doesn't work: `present()` from the double-tap
  trigger gets no focus.

## Commands

```bash
./dev-setup.sh                                   # one-command setup: packages (Ubuntu/Debian
                                                  # asks first), .venv, runs the tests once
uv run pytest -q && uv run ruff check            # 221 tests, lint (ruff flags unused noqa, RUF100)
PYTHONPATH=src timeout 120 /usr/bin/python3 -m gnomoji   # foreground run; inserts only with the extension installed
.venv/bin/python -m gnomoji.window          # window preview; doesn't insert (steals focus!)
journalctl --user -u gnomoji -f                  # service logs, once installed
packaging/build.sh                               # .deb, .rpm, .tar.gz from HEAD into dist/ (.rpm needs rpm installed)
```

**No skipped tests over a missing tool.** Every test that needs an external tool (`gjs`,
`shellcheck`, `dpkg-deb`/`git`, `rpmbuild`/`rpm`, `fc-match`) calls `tests/conftest.py`'s
`require(*tools)`, which fails (not skips) with "run ./dev-setup.sh" when one is missing. If
`uv run pytest` ever shows a skip again, that's a regression to fix, not ignore.

Runtime uses **only** `/usr/bin/python3` plus distro packages. `.venv` (uv, `--system-site-packages`)
is for pytest/ruff only. No pip packages at runtime. A source install (`./install.sh`) copies the
code into `~/.local/share/gnomoji`, so re-run it after changing code. A `.deb`/`.rpm` install
runs the packaged copy under `/usr/lib/gnomoji`.

## Packaging and releasing

One script, `packaging/build.sh [OUT_DIR]`, builds all three formats from `git archive HEAD`
(committed files only; uncommitted edits aren't in any of them). The `.tar.gz` is install-only,
not a repo snapshot: `git archive` is given an explicit allow-list of paths (just what
`install.sh`/`uninstall.sh` need, plus user docs), so things like `tests/`, `docs/`,
`CLAUDE.md` and the rest of `packaging/` never ship in it; GitHub's own "Source code" download
already covers the full repo. `tests/test_package.py` checks the tarball's file set against
that same allow-list (derived from `git ls-files`, so it can't drift unnoticed). All three
install the same tree, just at a different prefix: `/usr/lib/gnomoji/gnomoji/` for the `.deb`/`.rpm`,
`~/.local/share/gnomoji/gnomoji/` for `install.sh`. Code is reached via `PYTHONPATH`
in the launcher, service and desktop entry (`packaging/gnomoji`, `systemd/gnomoji.service`,
`desktop/*.desktop`, all templated with `@APPDIR@`) rather than Python's own site-packages:
Fedora's site-packages path changes with each Python version, and this way both formats share
one layout.

The after-install/before-removal logic is shared by the `.deb`'s `postinst`/`prerm` and the
`.rpm`'s `%post`/`%preun`, written once as `packaging/enable-for-everyone` and
`packaging/disable-for-everyone`: enable the user service globally
(`systemctl --global enable`) and restart it in every running user manager with an active
graphical session; before removal (not upgrade), stop it in running sessions and disable it
globally. Every step past unpacking is best-effort and never fails the install or removal. The
`.deb` compiles bytecode with `py3compile`/`py3clean`; the `.rpm` runs
`python3 -m compileall -q` in `%post` and deletes `__pycache__` folders in `%preun` on removal
— both pointed at `/usr/lib/gnomoji`. `tests/test_maintainer_scripts.py` runs the shared
scripts against fake `systemctl`/`loginctl`; `tests/test_package.py` builds all three and checks
their contents; `tests/test_install_scripts.py` runs `install.sh`/`uninstall.sh` in a throwaway
home against fake `systemctl`/`gnome-extensions`/`gnome-shell`/`gsettings`/`fc-list`.

CI (`.github/workflows/package.yml`) on every pull request: runs pytest (with `gjs` installed,
so the extension's JS tests run too), builds all three with `packaging/build.sh`, then
smoke-tests installing and removing the `.deb` on the Ubuntu runner and the `.rpm` in a
`fedora:44` container. On a `v*` tag: checks the tag matches `pyproject.toml`'s version, then
drafts a GitHub Release with all three files (`.deb`, `.rpm`, `.tar.gz`).

To release:

1. Bump `version` in `pyproject.toml`, run `uv lock`, commit, and merge to `main`.
2. `git tag v<version> && git push origin v<version>`. CI checks the tag and creates a
   **draft** release with the `.deb`, `.rpm` and `.tar.gz`.
3. Download the three files from the draft, try each install route, then publish the release.

## v2's origin

v2 was developed on the local branch `build/shell-extension` and ported here in 0.3.0; that
branch is unscrubbed, never push it.
