# Emoji Picker for Ubuntu — Design

**Status:** Complete draft, awaiting user review.
**Date:** 2026-09-25

## Intent

A Mac-style emoji picker for Ubuntu. Double-tap **right Shift**, a picker pops up,
choose an emoji, and it is inserted into whatever text field had focus.

**Why build it:** the existing options don't fit.

- GNOME's built-in picker (Ctrl+. / IBus Ctrl+Shift+E) is hard to use. You need to
  know an emoji's name, and there's no good way to browse.
- Smile is a large standalone app that copies to the clipboard, leaving you to paste.
  The goal here is something that feels integrated and native.

**Success looks like:** from any app, double-tap right Shift, find an emoji by
searching *or* scrolling, press Enter, and it appears in the field, with no manual
paste and no lasting clipboard damage.

**Nature of the project:** a personal tool, and partly a check that this is feasible
on GNOME + Wayland. Some uncertainty is expected ("not sure if it's possible, but
we'll see").

## Target environment

- Ubuntu 24.04, GNOME 46, **Wayland** session.
- The development user was in the `input` group, with `/dev/uinput` group-writable by `input`
  (later replaced by the `uaccess` udev rule; see below).
- At first only the development setup needed to work. No X11 or other desktops.
- **A keyboard remapper was running** on the development machine. Remappers grab physical
  keyboards via evdev and re-emit keys through their own virtual keyboard, so (a) the
  double-tap watcher may only see keys via the remapper's virtual device, and (b) the remapper
  may grab and remap our uinput paste chord. **Spike result:** (a) right Shift arrived only via
  the remapper's virtual keyboard, which the watcher handles; (b) the remapper didn't grab our
  device (see "Paste chord" below).

## Decisions so far

| Decision | Choice | Reason |
|---|---|---|
| Insertion method | **Clipboard + synthetic paste**, restoring the previous clipboard afterwards | Works in the widest range of apps. Try it and judge how disruptive it is. |
| Language / toolkit | **Python 3.12 + GTK4 / libadwaita** (PyGObject) | Fastest way to prove the idea works end to end, with a native GNOME look. |
| Popup position | **Centred** (Wayland apps can't place themselves at the cursor) | Fine for the feasibility phase. Moving the UI into a GNOME Shell extension later could open it at the cursor. |
| v1 features | Search (name + keywords), scrollable grid with category tabs, **recently used**, **full keyboard navigation** | The core of "easy to find things in". |
| Deferred | Skin-tone picker, kaomoji/symbols, opening at the cursor | Keep v1 small (YAGNI). |

## Dependencies

No pip packages at runtime.

- **Runtime (apt):** `python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`. (`python3-evdev` was dropped
  2026-09-27: `linux_input.py` does the evdev/uinput ioctls with the standard library.)
  Runs on the system Python.
- **Emoji data:** `emoji.json` is generated once by a script from Unicode's
  `emoji-test.txt` plus CLDR annotations (search keywords) and **committed**. Nothing
  is fetched at runtime.
- **Dev only:** a `uv`-managed `.venv` created with `--system-site-packages`, holding
  pytest and ruff. Nothing is installed globally with pip.

## System footprint and rollback

Everything the project adds outside its folder, per implementation step, with the exact
rollback commands, is kept in [`UNINSTALL.md`](../../../UNINSTALL.md). Rules:

- No apt packages are installed (all were already present) and none may be removed.
- No group, udev or shell rc changes. uv is installed with `UV_NO_MODIFY_PATH=1`.
- Since 2026-09-27 (for installs on other machines): `install.sh` may, after asking once, run
  sudo to install the apt/dnf packages and `udev/70-emoji-picker.rules`. That rule gives the
  active seat user keyboard and `/dev/uinput` access via the `uaccess` tag (no `input` group,
  no log-out). It's skipped when access already works (e.g. via a keyboard remapper's own rule).
- Any step that changes something outside the repo updates `UNINSTALL.md` in the same commit.
- Emergency stop: `systemctl --user stop emoji-picker` / `pkill -f emoji_picker`. Exiting
  removes the virtual keyboard and releases any held keys.

## Architecture

*(Section 1, approved)*

One Python process, `emoji-picker`, running as a **systemd user service** started at
login. It stays resident so the popup appears instantly.

| Module | Responsibility | Depends on |
|---|---|---|
| `trigger.py` | Watches every keyboard device in `/dev/input`. Fires when right Shift is pressed, released, and pressed again within ~300 ms **with no other key in between**, so Shift-typing capitals never triggers it. Runs on a background thread and signals the GTK main loop. | `linux_input.py` (stdlib) |
| `injector.py` | Owns a uinput virtual keyboard and exposes `paste()`, which sends the paste chord. | `linux_input.py` (stdlib) |
| `emoji_data.py` | Loads `emoji.json`. Search ranking: exact name, then name prefix, then keyword match. Keeps recents in `~/.local/state/emoji-picker/recent.json`. Pure Python with no GTK, so it's unit-testable. | none |
| `selection.py` | GTK-free selection state for the grid: current index, arrow movement given the column count, whether Enter has a target. | none |
| `config.py` | Loads the optional `config.toml` (stdlib `tomllib`) and applies defaults. | none |
| `clipboard.py` | `ClipboardKeeper`: snapshot text/image on focus; claim with a decoy (or the emoji, if none); arm to the emoji before pasting; release afterwards only if the clipboard is still ours. | Gdk |
| `flow.py` | `PasteFlow`: toggle, and pick → clipboard → hide → paste → restore sequencing with a busy guard. GTK-free and unit-tested with fakes. | none |
| `window.py` | The libadwaita popup: search entry, category tabs, scrolling grid (recents first), keyboard navigation (using `selection.py`). Its clipboard is handed to `clipboard.py` (only the focused app can read the clipboard on Wayland). | GTK4 / Adw |
| `__main__.py` | Entry point: loads config and data, builds the window, starts `trigger`, runs the `Adw.Application` main loop. | all of the above |

### Flow

1. Double-tap right Shift → `trigger` signals the main loop.
2. Window shows and takes focus, then **saves the current clipboard contents**.
3. The user picks an emoji.
4. Window **claims** the clipboard with a provider serving a *decoy* -- the saved old
   text, so Mutter's instant copy-on-claim is the old text, not the emoji (if there's
   no saved text, it serves the emoji from the start) -- and **hides**, then waits
   `paste_delay_ms` (default 80 ms) for focus to return to the original app.
5. Right before sending the paste chord, the provider is **armed**: switched to serve
   the emoji, so `injector.paste()`'s paste request gets it.
6. `release_after_read_ms` (default 50 ms) after the target app's last read of the emoji, since each read restarts the wait (or after `restore_delay_ms`,
   default 300 ms, if nothing reads it), if the clipboard is still ours, we
   **release** it (`set_content(None)`) rather than claiming it again. Mutter then
   takes over serving its own cached copy -- the decoy, i.e. the old text -- with no
   further help from us (see Error handling for the safety checks and Feasibility
   result 12).

### Paste chord: Shift+Insert for every app (decided 2026-09-26)

The spike showed GTK apps (GNOME Text Editor) **ignore Ctrl+Shift+V**, even when
pressed by hand. Tested by hand, **Shift+Insert** pastes in GNOME Text Editor (GTK), the
browser, Zed and Konsole; GNOME Terminal ignores it. Decision: **always send
Shift+Insert**. Terminals are out of scope (emoji are rarely
needed there), so no per-app detection. (Per-app detection *was* possible: the
`focused-window-dbus@flexagoon.com` GNOME extension reports the focused `wm_class` over
D-Bus. It's recorded here in case terminals matter later.)

The remapper does **not** grab our virtual keyboard: it only grabs devices with a
full QWERTY + A–Z key set, and ours has two keys. So our chord reaches GNOME unaltered.

This, together with focus returning reliably after the window hides, is **the first
thing to prove** during implementation.

## Picker window behaviour

*(Section 2, approved)*

### Layout

About 380×420 px, centred, no title bar, a rounded libadwaita card with its shadow.

```
┌──────────────────────────────────────┐
│ 🔍 Search emoji…                     │
├──────────────────────────────────────┤
│ 🕘 😀 🐻 🍔 ⚽ ✈️ 💡 🔣 🏁            │  ← category tabs
├──────────────────────────────────────┤
│ Recently used                        │
│ 👍 🎉 😂 ❤️ 🙏 🔥 ✅ 👀              │
│ Smileys & Emotion                    │
│ 😀 😃 😄 😁 😆 😅 🤣 😂              │
│ …                                    │
├──────────────────────────────────────┤
│ 🎉  party popper                     │  ← name of the selected emoji
└──────────────────────────────────────┘
```

### Selection and Enter

- **On open:** the search box has focus, the grid is scrolled to the top, and
  **nothing is selected**.
- **Enter does nothing unless there is a selection.** Enter on an empty search with
  no selection is a no-op.
- **Typing** filters the grid to matches (exact name, then prefix, then keyword),
  hides category headers, and **selects the first match**, so "tada" + Enter works.
- **Clearing the search** restores the full grid and clears the selection.
- **The first arrow key press** with no selection selects the first emoji in the grid.

### Keys and mouse

- Arrow keys move the selection around the grid while keyboard focus stays in the
  search box, so typing keeps working.
- Enter inserts the selected emoji. Esc closes without inserting.
- Page Up/Down scroll the grid. Ctrl+Tab / Ctrl+Shift+Tab jump between categories.
- Clicking a category tab scrolls to it. Clicking an emoji inserts it. Hovering
  shows its name in the footer.
- **Losing focus** without a choice closes the window without inserting.
- **Double-tapping right Shift while the window is open** closes it (a toggle).

### Recents and data

- Up to **24** recents, most recent first. Choosing an emoji moves it to the front.
- Rendered with the system **Noto Color Emoji** font. Emoji the font can't draw are
  left out when `emoji.json` is generated.
- The window and grid are built once at startup and then shown/hidden. Filtering
  across the ~1,900 emoji must keep up with typing.

## Error handling

*(Section 3, approved)*

**Principle:** never leave the user worse off. The worst case is "the emoji is on the
clipboard"; previous clipboard **text** is never lost. (Images and files can't be
restored; see Feasibility results.)

| Situation | Behaviour |
|---|---|
| No permission to read `/dev/input` or write `/dev/uinput` | Exit with a message pointing at `./install.sh`, which sets up the udev rule, visible in `journalctl --user -u emoji-picker`. systemd restarts are rate-limited, so it can't crash-loop. |
| Keyboard plugged in or removed (USB, Bluetooth, dock) | `trigger` watches `/dev/input` for devices appearing and disappearing and adds or drops them without a restart. |
| Current clipboard is empty or not text (image, files) | Only text is saved. If there's no text, skip the restore, so the emoji stays on the clipboard. **Known limitation:** an image or file on the clipboard is replaced by the emoji. |
| Clipboard changed during the paste window | Before releasing, check the clipboard is still owned by our provider (`get_content() is` our provider). If not, someone else claimed it meanwhile; leave it alone (no release, no re-claim). |
| Service stops or restarts | Nothing changes. Mutter (GNOME's compositor) caches the clipboard's text/plain value the instant a claim happens; because we claim with a decoy (the old text) rather than the emoji, and only ever release (never re-claim), Mutter's cached copy is already the old text by the time we let go. If the picker exits before releasing, the clipboard is left owned by us serving whatever it was last armed to (emoji mid-paste, or the decoy); once it exits, Wayland gives ownership to whichever client claims next, same as any app quitting mid-selection. Verified by hand (2026-09-26, Feasibility result 12): `set_content(None)` handed ownership to Mutter and Ctrl+V kept giving the old text even after the probing process exited. |
| Target app ignores Shift+Insert (e.g. GNOME Terminal) | Can't be detected on Wayland. The clipboard is only armed to serve the emoji right before the paste chord is sent, and released `restore_delay_ms` (default 300 ms) after that, so the emoji is visible on the clipboard for about that long. The config option `restore_clipboard = false` leaves it there for pasting by hand. |
| Picker re-shown without a focus-lost/focus-gained toggle (bug I2) | On Wayland, GTK only receives a selection offer while our window is focused, and GTK's `notify::is-active` doesn't reliably re-fire on re-show, so `on_focused → save()` can be skipped and a stale saved text served as the decoy. Fixed by having `ClipboardKeeper` also listen to the clipboard's own `changed` signal and re-`save()` on any non-local change that carries text (GTK emits `changed` with the current offer on focus regardless of whether `is-active` toggled). Local changes (our own claim/release) and changes with no text formats are ignored, and `saved_text` isn't cleared on those. |
| `emoji.json` missing or corrupt | Fail loudly at startup. This is a packaging bug, not something to recover from. |
| Unexpected crash | systemd `Restart=on-failure`, rate-limited. |

### Configuration

An optional `~/.config/emoji-picker/config.toml`, read with the stdlib `tomllib`. Keys
and defaults:

- `double_tap_ms = 300`
- `restore_clipboard = true`
- `restore_delay_ms = 300`
- `release_after_read_ms = 50`
- `paste_delay_ms = 80`: wait between hiding the window and sending the paste

A missing file means all defaults are used. An invalid value is logged and its default
is used instead.

## Testing

*(Section 4, approved)*

1. **Feasibility check (first, throwaway):** a script that saves the clipboard, sets
   an emoji, sends the paste chord through uinput, and restores the clipboard. Run it by
   hand against a terminal (GNOME Terminal / Ptyxis), Firefox or Chrome, VS Code,
   Slack, and a GTK text field (e.g. GNOME Text Editor) **before** building the full
   UI. Record the results in the spec. If it fails, revisit the insertion method
   before going further.
2. **Unit tests (pytest, no display):**
   - `emoji_data`: search ranking; recents order, cap of 24, moving a reused emoji to
     the front, tolerating a corrupt or missing recents file.
   - `trigger`: driven by scripted event sequences through a pure state machine, with
     no real devices. Covers: a double-tap fires; a tap slower than `double_tap_ms`
     doesn't; Shift + another key + Shift doesn't; left Shift doesn't; key auto-repeat
     events are ignored.
   - Selection logic (grid position, arrow movement, Enter behaviour with and without
     a selection), kept in a GTK-free module.
3. **Manual checklist** for the finished picker: each app above, a clipboard holding
   an image, Esc, clicking away, the toggle, and plugging in a keyboard while it's
   running.

## Feasibility results (2026-09-26)

Spike run by hand in GNOME Text Editor, with a keyboard remapper running. **Decision: GO**, with the
design changes below. The final working probe is `spike/paste_probe.py`.

| # | Finding | Consequence for the design |
|---|---|---|
| 1 | Right Shift is only visible on the remapper's virtual keyboard; the remapper grabs the physical keyboards. A mouse also reports as a keyboard. | None: the watcher reads every keyboard, and rescans cover the remapper being stopped. |
| 2 | The remapper only grabs devices with a full QWERTY + A–Z key set. | Our 2-key virtual keyboard reaches GNOME unaltered. No remapper-off test needed. |
| 3 | GTK apps ignore Ctrl+Shift+V (even pressed by hand). By hand, Shift+Insert pastes in Text Editor, the browser, Zed and Konsole, but not GNOME Terminal. | **Always send Shift+Insert.** Terminals are out of scope (a deliberate choice). |
| 4 | A window shown from a timer **does** get keyboard focus, and reading the clipboard on focus works. | Flow steps 1–2 confirmed. |
| 5 | Claiming the clipboard on a timer, with no input in our window, is **silently refused**: the app pasted the *old* clipboard. Claiming inside an Enter keypress handler works: 🎉 pasted. | Claim the clipboard synchronously in the Enter/click handler, **before** hiding. |
| 6 | Claiming the clipboard again after hiding (to restore) is refused. | Restore by **keeping ownership and swapping the text our provider serves** (`SwitchingText`). Verified: 🎉 pastes, then Ctrl+V gives the original text. |
| 7 | PyGObject 3.48's async `do_write_mime_type_async` vfunc fails when GTK calls it (`G_IS_TASK` criticals). A sync `do_get_value(self)` returning `(True, text)` works. | Use the sync form. `Gdk.ContentProvider.get_value()` can't be called from Python either, so tests go through GTK's C API with ctypes. |
| 8 | Offering an image alongside the emoji would make apps paste the image. | **Only text is restored.** An image or file on the clipboard is lost (replaced by the emoji). Known limitation. |
| 9 | The window opens top-left-ish (GNOME's default placement). `center-new-windows` would centre it but applies to every app. | Left as is (a deliberate choice). No GNOME settings changed. |
| 10 | Apps fetch the clipboard data within milliseconds of the paste chord. A 1 s restore delay made a quick manual Ctrl+V paste the emoji again. | `restore_delay_ms` default **300**. |
| 11 | The picker window never appeared: first layout blocked the GTK main loop for minutes. Cause: on the development machine, fontconfig resolved "Noto Color Emoji" to a user-installed **COLRv1 vector** font (`/usr/local/share/fonts/NotoColorEmoji-Regular.ttf`), whose first layout of each distinct glyph costs ~50ms, times ~1,900 emoji. Ubuntu's apt **CBDT bitmap** `NotoColorEmoji.ttf` is ~250x faster. | The picker ships a private `fonts.conf` (`src/emoji_picker/data/fonts.conf`) that hides the vector font from fontconfig, activated via `FONTCONFIG_FILE` in `fonts.py`'s `use_fast_emoji_font()`, called before any `from gi.repository import ...`. **Process-only**: no system file, `/etc`, or `~/.config/fontconfig` is touched. |
| 12 | Mutter keeps its own copy of the clipboard: it reads text/plain the instant any client claims it, and takes over serving that cached copy once the claiming client's ownership ends (`set_content(None)`, or the client exiting). Verified with `.superpowers/sdd/2026-09-25-emoji-picker/probe_release.py` (2026-09-26): Mutter asked for the value 10 ms after a claim serving the old text and got it; the paste chord then got the emoji (armed just before sending it); `set_content(None)` released ownership while the probe's window was unfocused; Ctrl+V gave the old text, and still did after the probing process exited. | Superseded finding 6 (swap-on-restore, which left Mutter's cache holding the emoji forever). New design: **claim** with a decoy (the saved old text) so Mutter's instant copy is the old text; **arm** (switch to the emoji) right before the paste chord; **release** (`set_content(None)`) afterwards, never re-claim. Releasing needs no focus; claiming still does (finding 5 stands). |

## Acceptance results (2026-09-26)

Run by hand with the systemd service installed, on GNOME 46 / Wayland with a keyboard remapper running.

| # | Check | Result | Notes |
|---|---|---|---|
| 1 | Terminal | Out of scope | The user's decision (Feasibility #3): GNOME Terminal ignores Shift+Insert. Konsole accepts it. |
| 2 | Browser | PASS | Firefox URL bar and wikipedia.org search box, at the default `paste_delay_ms` of 80. duckduckgo.com's search box drops focus on any window switch, including a plain Alt+Tab, so nothing can be pasted there. That's a site limitation. |
| 3 | Code editor | PASS | Tested in Zed instead of VS Code. |
| 4 | Electron | PASS | Slack and Signal. |
| 5 | Text Editor + ZWJ | PASS | The family emoji inserts as one glyph. It splits in a terminal (terminal rendering, out of scope). |
| 6 | Image on clipboard | PASS | 🎉 inserts and nothing crashes. The log hinted the image may be re-offered afterwards (unverified). |
| 7 | Esc / click-away | PASS | Click-away initially failed on a re-opened picker. Fixed in 47aad7e (GTK keeps is-active across hide/show). |
| 8 | Double-tap closes | PASS | |
| 9 | Rapid re-tap after pick | PASS | Only one 🎉 went in, and the clipboard came back as before. |
| 10 | Right-Shift capitals | PASS | |
| 11 | External keyboard unplug/replug | PASS | The laptop keyboard also triggers it. |
| 12 | Keyboard remapper | PASS | The remapper's shortcuts were used throughout testing. |
| 13 | Recents persist | PASS | Still there after `systemctl --user restart emoji-picker`. |

Other hands-on fixes during acceptance: the stale clipboard save on re-show (I2, 0f0cd1d) and the slow emoji font (`fonts.py`).

Clipboard disruption verdict: acceptable for now. The emoji is on the clipboard only from
the paste chord until `release_after_read_ms` (50 ms) after the target app reads it (added
during acceptance, 5d5d6cc/0c72eb2), then GNOME serves the old text again.

Follow-ups:
- **The "proper" way is an input method (IBus engine).** It would commit the emoji
  straight into the focused field, the way GNOME's own Ctrl+. picker and CJK input
  methods do: no clipboard, no paste chord, no focus-timing issues, and it works on
  focus-dropping pages like DuckDuckGo. The cost is a much bigger build: an IBus engine
  the user adds as an input source, only where IBus works, and possible interplay with
  keyboard remappers' routing (untested). The clipboard approach stays for now, to be
  revisited later.
- Terminals: out of scope (Shift+Insert isn't universal there). An input method would
  also fix this.
- DuckDuckGo-style pages that drop focus on window switch: known limitation, and one an
  input method would avoid.
