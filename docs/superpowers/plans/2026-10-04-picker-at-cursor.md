# Open the picker at the text cursor: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Gnomoji picker opens just below the text cursor of the field you double-tapped in;
without a usable cursor position, where you last dragged it; failing that, where GNOME puts it.

**Architecture:** Extension-only. At the double-tap, `extension.js` saves GNOME's input-method
cursor rectangle. When the picker's new window is shown (after GNOME has placed it), it asks a new
pure module, `placement.js`, for a position and moves the window with `move_frame`. Drags of the
picker are remembered in memory via `grab-op-end`. The Python app, D-Bus interface, install routes
and `UNINSTALL.md` don't change.

**Tech Stack:** GJS (GNOME Shell 46-50 extension, ES modules), plain `gjs -m` unit tests run by
pytest, pytest static source checks.

**Spec:** `docs/superpowers/specs/2026-10-04-picker-at-cursor-design.md`

## Global Constraints

- Supported GNOME: 46-50 (`extension/metadata.json` `shell-version`); no version-specific code paths.
- The picker's app id is `local.emojipicker.EmojiPicker` (`src/gnomoji/__main__.py` `APP_ID`).
- `GAP = 4` px; `CURSOR_MAX_AGE_MS = 2000`.
- The dragged spot lives in memory only (no file, no settings): `UNINSTALL.md` stays unchanged.
- `placement.js` imports nothing from GNOME, so `gjs -m` can test it.
- No skipped tests: anything needing `gjs` goes through `tests/test_extension_js.py` (which calls `require("gjs")`).
- Extension code only loads at the next log-in: behaviour in GNOME is checked by hand (Task 4).
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Before every commit: `uv run pytest -q && uv run ruff check` (214 tests pass at the start).

## Review Focus

1. **App id drift.** If `APP_ID` in `__main__.py` ever changes, the extension silently stops
   recognising the picker. Expected: a test fails. (Task 2, `test_extension_knows_the_picker_app_id`.)
2. **A cursor rect off every monitor** (`get_monitor_index_for_rect` returns -1). Expected: the
   primary monitor's work area, not a crash. (Task 2, `test_work_area_falls_back_to_the_primary_monitor`.)
3. **Extension disabled while a `'shown'` handler is pending** (picker window created, not yet
   shown). Expected: handler disconnected, nothing moves later. (Task 2, `test_disable_disconnects_placement_handlers`.)
4. **Dragging some other window.** Expected: the picker's fallback spot doesn't change.
   (Task 2, `test_only_picker_drags_are_remembered`.)
5. **The cursor read too late** (after the picker's own search box overwrote it). Expected: it's
   read in `_onTap`, nowhere else. (Task 2, `test_cursor_is_read_at_the_double_tap_only`.)

---

### Task 1: `placement.js`, the pure placement rules

**Files:**
- Create: `extension/placement.js`
- Create: `tests/extension/test_placement.js`
- Modify: `tests/test_package.py` (the `EXPECTED` file list near line 42, and the extension file loop near line 286)
- Modify: `tests/test_install_scripts.py` (the two `for name in ("extension.js", ...)` loops near lines 25 and 286)

**Interfaces:**
- Consumes: nothing.
- Produces (used by Task 2):
  ```js
  export const GAP = 4;
  export const CURSOR_MAX_AGE_MS = 2000;
  export function validCursor(rect) -> boolean
  export function placePicker({cursorAt, nowMs, size, dragged, workAreaFor}) -> {x, y} | null
  // cursorAt: {rect: {x, y, width, height}, frame: {x, y, width, height}, atMs: number} | null
  // size: {width, height}; dragged: {x, y} | null
  // workAreaFor(rect {x, y, width, height}) -> {x, y, width, height}
  ```

- [ ] **Step 1: Write the failing tests**

Create `tests/extension/test_placement.js`:

```js
import {test, eq, done} from './assert.js';
import {placePicker, validCursor, GAP, CURSOR_MAX_AGE_MS} from '../../extension/placement.js';

// A 1080p screen under a 32 px top bar, a maximised target window, and the 380×420 picker.
const WA = {x: 0, y: 32, width: 1920, height: 1048};
const FRAME = {x: 0, y: 32, width: 1920, height: 1048};
const SIZE = {width: 380, height: 420};
const NOW = 10000;

const cursor = (x, y, over = {}) => ({rect: {x, y, width: 0, height: 22}, frame: FRAME, atMs: NOW, ...over});
const place = over => placePicker({cursorAt: null, nowMs: NOW, size: SIZE, dragged: null, workAreaFor: () => WA, ...over});
const at = (pos, x, y) => {
    eq(pos === null, false, 'position');
    eq(pos.x, x, 'x');
    eq(pos.y, y, 'y');
};

test('constants', () => {
    eq(GAP, 4);
    eq(CURSOR_MAX_AGE_MS, 2000);
});

test('middle: left edge at the cursor, just below its line (a zero-width cursor is fine)', () =>
    at(place({cursorAt: cursor(500, 300)}), 500, 326));

test('right edge: slides left to fit, still below', () =>
    at(place({cursorAt: cursor(1800, 300)}), 1540, 326));

test('bottom edge: opens above the line instead', () =>
    at(place({cursorAt: cursor(500, 900)}), 500, 476));

test('bottom-right corner: slides left and opens above', () =>
    at(place({cursorAt: cursor(1800, 900)}), 1540, 476));

test('left edge: pushed back on screen', () => {
    const frame = {x: -200, y: 100, width: 800, height: 600};
    at(place({cursorAt: {rect: {x: -150, y: 200, width: 0, height: 22}, frame, atMs: NOW}}), 0, 226);
});

test('top edge: pushed below the top bar', () => {
    const frame = {x: 100, y: 0, width: 800, height: 600};
    at(place({cursorAt: {rect: {x: 200, y: 5, width: 0, height: 10}, frame, atMs: NOW}}), 200, 32);
});

test('screen too short for above or below: kept inside the work area', () => {
    const short = {x: 0, y: 32, width: 1920, height: 500};
    at(place({cursorAt: cursor(500, 250), workAreaFor: () => short}), 500, 32);
});

test('picker bigger than the work area: top-left of the work area', () =>
    at(place({cursorAt: cursor(500, 300), size: {width: 2000, height: 1200}}), 0, 32));

test('second monitor: placed in that monitor\'s work area', () => {
    const wa2 = {x: 1920, y: 0, width: 2560, height: 1440};
    const frame = {x: 1920, y: 0, width: 2560, height: 1440};
    const workAreaFor = r => (r.x >= 1920 ? wa2 : WA);
    at(place({cursorAt: {rect: {x: 4300, y: 200, width: 0, height: 22}, frame, atMs: NOW}, workAreaFor}), 4100, 226);
});

test('asks for the work area of the cursor\'s monitor', () => {
    const seen = [];
    place({cursorAt: cursor(500, 300), workAreaFor: r => { seen.push(r); return WA; }});
    eq(seen.length, 1);
    eq(seen[0].x, 500);
    eq(seen[0].y, 300);
});

test('fractional numbers are rounded to whole pixels', () => {
    const c = {rect: {x: 500.6, y: 300.2, width: 0, height: 22.5}, frame: FRAME, atMs: NOW};
    at(place({cursorAt: c}), 501, 327);
});

test('a cursor exactly CURSOR_MAX_AGE_MS old is still used', () =>
    at(place({cursorAt: cursor(500, 300, {atMs: NOW - 2000})}), 500, 326));

const DRAGGED = {x: 700, y: 200};

test('a cursor older than that falls back to the dragged spot', () =>
    at(place({cursorAt: cursor(500, 300, {atMs: NOW - 2001}), dragged: DRAGGED}), 700, 200));

test('a cursor outside the target window (stale, from another app) falls back', () => {
    const frame = {x: 562, y: 263, width: 1440, height: 859};
    at(place({cursorAt: {rect: {x: 616, y: 43, width: 0, height: 18}, frame, atMs: NOW}, dragged: DRAGGED}), 700, 200);
});

test('a missing target frame falls back', () =>
    at(place({cursorAt: cursor(500, 300, {frame: null}), dragged: DRAGGED}), 700, 200));

for (const [name, rect] of [
    ['null', null],
    ['undefined', undefined],
    ['NaN', {x: NaN, y: 300, width: 0, height: 22}],
    ['Infinity', {x: 500, y: Infinity, width: 0, height: 22}],
    ['zero height', {x: 500, y: 300, width: 0, height: 0}],
    ['negative width', {x: 500, y: 300, width: -1, height: 22}],
    ['strings', {x: '500', y: '300', width: '0', height: '22'}],
]) {
    test(`an invalid cursor rect (${name}) falls back`, () => {
        eq(validCursor(rect), false);
        at(place({cursorAt: {rect, frame: FRAME, atMs: NOW}, dragged: DRAGGED}), 700, 200);
    });
}

test('no cursor: the dragged spot', () =>
    at(place({dragged: DRAGGED}), 700, 200));

test('a dragged spot off every monitor is pulled into the work area it\'s given', () => {
    const seen = [];
    at(place({dragged: {x: 5000, y: 3000}, workAreaFor: r => { seen.push(r); return WA; }}), 1540, 660);
    eq(seen[0].width, 380);
    eq(seen[0].height, 420);
});

test('nothing usable: null (leave it where GNOME put it)', () => {
    eq(place({}), null);
    eq(place({cursorAt: cursor(500, 300, {atMs: 0})}), null);
});

done();
```

- [ ] **Step 2: Run them to see them fail**

Run: `gjs -m tests/extension/test_placement.js`
Expected: an import error for `../../extension/placement.js` (file not found).

- [ ] **Step 3: Write `extension/placement.js`**

```js
// Where the picker's window goes when it opens. Pure (no GNOME imports), so it's tested with
// plain gjs (tests/extension/test_placement.js); extension.js feeds it GNOME's numbers.
//
// 1. Just below the text cursor saved at the double-tap (above it when there's no room
//    below), kept inside the work area of the cursor's monitor. Only if that cursor is fresh
//    and inside the window that had focus: GNOME doesn't clear it when focus moves.
// 2. Otherwise where the picker was last dragged, pulled back on screen if needed.
// 3. Otherwise null: leave it where GNOME put it.

export const GAP = 4; // px between the text cursor's line and the picker
export const CURSOR_MAX_AGE_MS = 2000; // a cursor saved longer ago than this is ignored

const isNumber = n => typeof n === 'number' && Number.isFinite(n);

// GTK and Firefox send a zero-width cursor, so only the height has to be positive.
export function validCursor(rect) {
    return Boolean(rect) && [rect.x, rect.y, rect.width, rect.height].every(isNumber) &&
        rect.width >= 0 && rect.height > 0;
}

function contains(area, x, y) {
    return Boolean(area) && [area.x, area.y, area.width, area.height].every(isNumber) &&
        x >= area.x && x < area.x + area.width && y >= area.y && y < area.y + area.height;
}

// When the picker is bigger than the work area, hi < lo and this gives lo (left/top edge).
const clamp = (value, lo, hi) => Math.max(lo, Math.min(value, hi));

function inside(workArea, size, x, y) {
    return {
        x: Math.round(clamp(x, workArea.x, workArea.x + workArea.width - size.width)),
        y: Math.round(clamp(y, workArea.y, workArea.y + workArea.height - size.height)),
    };
}

export function placePicker({cursorAt, nowMs, size, dragged, workAreaFor}) {
    if (cursorAt && nowMs - cursorAt.atMs <= CURSOR_MAX_AGE_MS && validCursor(cursorAt.rect) &&
        contains(cursorAt.frame, cursorAt.rect.x, cursorAt.rect.y)) {
        const rect = cursorAt.rect;
        const workArea = workAreaFor(rect);
        let y = rect.y + rect.height + GAP; // below the line
        if (y + size.height > workArea.y + workArea.height)
            y = rect.y - GAP - size.height; // no room below: above it
        return inside(workArea, size, rect.x, y);
    }
    if (dragged)
        return inside(workAreaFor({...dragged, ...size}), size, dragged.x, dragged.y);
    return null;
}
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `gjs -m tests/extension/test_placement.js`
Expected: every line starts with `ok`, exit code 0.

- [ ] **Step 5: Add `placement.js` to the packaging file lists**

In `tests/test_package.py`, add `f"{EXT}/placement.js",` after `f"{EXT}/insertWaiter.js",` in the
expected file list (near line 42), and add `"placement.js"` to the tuple
`("extension.js", "tapDetector.js", "insertWaiter.js", "metadata.json")` near line 286. In
`tests/test_install_scripts.py`, add `"placement.js"` to both
`("extension.js", "tapDetector.js", "insertWaiter.js", "metadata.json")` tuples (near lines 25 and 286).
`install.sh` and `packaging/build.sh` already copy `extension/*.js`, so they need no change.

- [ ] **Step 6: Run everything**

Run: `uv run pytest -q && uv run ruff check`
Expected: all pass (one more than 214, from `test_js[test_placement.js]`), ruff clean.

- [ ] **Step 7: Commit**

```bash
git add extension/placement.js tests/extension/test_placement.js tests/test_package.py tests/test_install_scripts.py
git commit -m "Extension: placement rules for opening the picker at the text cursor

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: wire placement into `extension.js`

**Files:**
- Modify: `extension/extension.js` (header comment, imports, `enable()`, `disable()`, `_onTap()`, new methods)
- Test: `tests/test_extension_files.py`

**Interfaces:**
- Consumes: `placePicker` from Task 1 (`./placement.js`).
- Produces: nothing other tasks call. New instance fields: `_cursorAt`, `_dragged`, `_createdId`, `_grabEndId`, `_shownWait` (`{window, id}` or `null`).

- [ ] **Step 1: Write the failing static checks**

Append to `tests/test_extension_files.py`:

```python
def method(name: str) -> str:
    text = source()
    start = text.index(f"    {name}(")
    return text[start:text.index("\n    }\n", start)]


def test_extension_knows_the_picker_app_id():
    main = (EXTENSION.parent / "src" / "gnomoji" / "__main__.py").read_text(encoding="utf-8")
    assert 'APP_ID = "local.emojipicker.EmojiPicker"' in main
    assert "const APP_ID = 'local.emojipicker.EmojiPicker';" in source()
    assert "get_wm_class() === APP_ID" in method("_isPicker")


def test_extension_places_the_picker_after_gnome_does():
    text = source()
    assert "import {placePicker} from './placement.js';" in text
    created = method("_onWindowCreated")
    # 'window-created' is before GNOME's own placement; moving there would be undone.
    assert "move_frame" not in created
    assert "connect('shown'" in created
    assert "move_frame(true, at.x, at.y)" in method("_place")


def test_cursor_is_read_at_the_double_tap_only():
    code = [line for line in source().splitlines() if not line.strip().startswith("//")]
    assert sum("_cursorRect" in line for line in code) == 1
    assert "_cursorRect" in method("_onTap")
    assert "this._cursorAt = null;" in method("_place")  # used at most once


def test_only_picker_drags_are_remembered():
    body = method("_onGrabEnd")
    assert "this._isPicker(window)" in body
    assert body.index("this._isPicker(window)") < body.index("this._dragged =")


def test_work_area_falls_back_to_the_primary_monitor():
    body = method("_workAreaFor")
    assert "get_monitor_index_for_rect" in body
    assert "get_primary_monitor()" in body


def test_disable_disconnects_placement_handlers():
    body = method("disable")
    for fragment in (
        "global.display.disconnect(this._createdId)",
        "global.display.disconnect(this._grabEndId)",
        "this._cancelShownWait()",
        "this._cursorAt = null;",
        "this._dragged = null;",
    ):
        assert fragment in body, fragment
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest -q tests/test_extension_files.py`
Expected: the six new tests FAIL (`ValueError: substring not found` or assertion errors); the old ones pass.

- [ ] **Step 3: Change `extension/extension.js`**

3a. In the header comment, after the paragraph for point 2 (ending "clipboard fallback."), add:

```js
// 3. Placement. At the double-tap we also save the text cursor's position (GNOME's input
//    method keeps it in the private Main.inputMethod._cursorRect, in screen coordinates; the
//    picker's own search box overwrites it once the picker opens, so it can't be read later).
//    When the picker's window is shown we move it just below that cursor (placement.js), or to
//    where it was last dragged (kept in memory until log-out). The app can't place its own
//    window on Wayland; GNOME Shell can.
```

3b. Imports and constants. After `import GLib from 'gi://GLib';` add `import Mtk from 'gi://Mtk';`.
After `import {acceptInsert, decide} from './insertWaiter.js';` add
`import {placePicker} from './placement.js';`. After `const POLL_MS = 10;` add:

```js
const APP_ID = 'local.emojipicker.EmojiPicker'; // the picker's app id (src/gnomoji/__main__.py)
```

3c. In `enable()`, after `this._pollId = 0;` add:

```js
        this._cursorAt = null; // the text cursor saved at the last double-tap
        this._dragged = null; // where the picker was last dragged, until log-out
        this._shownWait = null; // {window, id}: a new picker window we're waiting to see shown
        this._createdId = global.display.connect('window-created', (_display, window) => this._onWindowCreated(window));
        this._grabEndId = global.display.connect('grab-op-end', (_display, window) => this._onGrabEnd(window));
```

3d. In `disable()`, after `global.disconnect(this._tapId);` add:

```js
        global.display.disconnect(this._createdId);
        global.display.disconnect(this._grabEndId);
        this._cancelShownWait();
        this._cursorAt = null;
        this._dragged = null;
```

3e. In `_onTap()`, replace

```js
        this._target = global.display.focus_window;
        this._dbus.emit_signal('DoubleTap', null);
```

with

```js
        this._target = global.display.focus_window;
        // Read now: the picker's own search box replaces it as soon as the picker opens.
        // placement.js checks it (GNOME keeps it after focus moves, so it can be another app's).
        const rect = Main.inputMethod._cursorRect;
        const frame = this._target.get_frame_rect();
        this._cursorAt = {
            rect: rect ? {x: rect.x, y: rect.y, width: rect.width, height: rect.height} : null,
            frame: {x: frame.x, y: frame.y, width: frame.width, height: frame.height},
            atMs: nowMs(),
        };
        this._dbus.emit_signal('DoubleTap', null);
```

3f. Add these methods after `_onTap()`:

```js
    _isPicker(window) {
        return window.get_wm_class() === APP_ID; // on Wayland, the app id
    }

    // Hiding the picker destroys its window, so each opening is a new one. GNOME places a
    // window when it's first shown, after 'window-created' (mutter window.c,
    // meta_window_force_placement), so a move here would be undone: wait for 'shown', which
    // comes after placement and before the next repaint.
    _onWindowCreated(window) {
        if (!this._isPicker(window))
            return;
        this._cancelShownWait();
        const id = window.connect('shown', () => {
            this._cancelShownWait();
            this._place(window);
        });
        this._shownWait = {window, id};
    }

    _cancelShownWait() {
        if (this._shownWait) {
            this._shownWait.window.disconnect(this._shownWait.id);
            this._shownWait = null;
        }
    }

    _place(window) {
        const frame = window.get_frame_rect();
        const at = placePicker({
            cursorAt: this._cursorAt,
            nowMs: nowMs(),
            size: {width: frame.width, height: frame.height},
            dragged: this._dragged,
            workAreaFor: rect => this._workAreaFor(rect),
        });
        this._cursorAt = null; // a saved cursor is used at most once
        if (at) {
            window.move_frame(true, at.x, at.y);
            log(`placed the picker at ${at.x},${at.y}`);
        }
    }

    _workAreaFor(rect) {
        const display = global.display;
        let index = display.get_monitor_index_for_rect(new Mtk.Rectangle({
            x: Math.round(rect.x), y: Math.round(rect.y),
            width: Math.max(1, Math.round(rect.width)), height: Math.max(1, Math.round(rect.height)),
        }));
        if (index < 0)
            index = display.get_primary_monitor(); // off every monitor
        const area = Main.layoutManager.getWorkAreaForMonitor(index);
        return {x: area.x, y: area.y, width: area.width, height: area.height};
    }

    // The picker can't be resized (window.py), so any grab on it is a move.
    _onGrabEnd(window) {
        if (!window || !this._isPicker(window))
            return;
        const frame = window.get_frame_rect();
        this._dragged = {x: frame.x, y: frame.y};
    }
```

- [ ] **Step 4: Check the JS parses**

`extension.js` imports GNOME Shell's own files, so it can't load outside GNOME, but gjs parses it
before resolving imports. This prints `SyntaxError: ...` and exits 1 on a syntax error, and
prints an `ImportError` for `resource:///org/gnome/shell/ui/main.js` and exits 0 otherwise:

```bash
check=$(mktemp --suffix=.js)
cat > "$check" <<'EOF'
import(`file://${ARGV[0]}`).then(() => print('loaded'), e => {
    print(`${e.name}: ${e.message}`);
    if (e instanceof SyntaxError) imports.system.exit(1);
});
EOF
gjs -m "$check" "$PWD/extension/extension.js"; echo "exit $?"; rm "$check"
```

Expected: `ImportError: ... /org/gnome/shell/ui/main.js ...` then `exit 0`.

- [ ] **Step 5: Run everything**

Run: `uv run pytest -q && uv run ruff check`
Expected: all pass, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add extension/extension.js tests/test_extension_files.py
git commit -m "Extension: open the picker at the text cursor, or where it was last dragged

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: docs

**Files:**
- Modify: `CLAUDE.md` (the two placement facts near lines 95-98; the test count in "Commands")
- Modify: `README.md` (the "Use" section, after the key table)
- Modify: `docs/superpowers/specs/2026-09-25-emoji-picker-design.md` (the "Popup position" row near line 48, and decision 9 near line 269)

- [ ] **Step 1: CLAUDE.md**

Replace the two bullets

```markdown
- **The window opens where GNOME places it** (top-left by default).
- **The picker can't reopen where it was dragged.** Hiding unmaps it, so GNOME re-places it.
  Minimise-instead-of-hide keeps the position, but `present()` from the double-tap trigger (not
  input in our window) gets no focus: GNOME shows a "… is ready" notification instead.
```

with

```markdown
- **The extension places the picker; the app can't** (Wayland). At the double-tap it saves
  `Main.inputMethod._cursorRect`, the text cursor in screen coordinates (private, same in GNOME
  46 and 50; set only while IBus runs; **not cleared when focus moves**, and **overwritten by the
  picker's own search box** once it opens, so it's read at the double-tap and must lie inside the
  window focused then). Hiding the picker destroys its window, so each opening is a new one; the
  extension moves it on that window's `'shown'` signal. Not on `'window-created'`: GNOME places
  windows after that (`meta_window_force_placement`) and would undo the move. Rules in
  `extension/placement.js`: below the cursor, above it if there's no room, kept in the monitor's
  work area; otherwise the last-dragged spot (memory only, reset at log-out); otherwise GNOME's
  placement. Minimise-instead-of-hide was tried before and doesn't work: `present()` from the
  double-tap trigger gets no focus.
```

Also update the test count in the "Commands" block (`# 214 tests, lint ...`) to the number
`uv run pytest -q` now reports.

- [ ] **Step 2: README.md**

After the "Use" key table (the row starting `| Run \`gnomoji\` again |`), add a blank line and:

```markdown
The picker opens just below the text cursor (above it near the bottom of the screen). When the
app doesn't tell GNOME where its cursor is, or you open the picker with `gnomoji`, it opens where
you last dragged it since logging in, or else where GNOME puts new windows.
```

- [ ] **Step 3: the 2026-09-25 spec**

In the "Popup position" table row, append to its last cell: ` **Done in 0.3.x:** the extension
opens it at the text cursor; see \`2026-10-04-picker-at-cursor-design.md\`.` In decision 9 near
line 269, append to its last cell: ` Superseded by \`2026-10-04-picker-at-cursor-design.md\`.`

- [ ] **Step 4: Run everything**

Run: `uv run pytest -q && uv run ruff check`
Expected: all pass, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md README.md docs/superpowers/specs/2026-09-25-emoji-picker-design.md
git commit -m "Docs: the picker opens at the text cursor

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: hands-on in GNOME (user checkpoint)

Extension code only loads at log-in, and this machine runs the `.deb`, so the user installs a
`.deb` built from the branch and logs out once.

- [ ] **Step 1: Build** (Claude): `packaging/build.sh` (builds from `HEAD`, so commit first).
  Tell the user the `.deb` path in `dist/`.
- [ ] **Step 2: Install** (user, own terminal): `sudo dpkg -i dist/gnomoji_<version>_all.deb`, then log out and back in.
- [ ] **Step 3: Check** (user), watching `journalctl -f -o cat /usr/bin/gnome-shell | grep gnomoji`:
  1. Text Editor, cursor mid-screen: double-tap → picker just below the line, left edges lined up; log shows `placed the picker at ...`.
  2. Cursor near the right edge → picker slid left, still below.
  3. Cursor near the bottom → picker above the line.
  4. Same three in Firefox (address bar and a page's text box).
  5. No visible jump from top-left when it opens.
  6. Drag the picker somewhere, close it, run `gnomoji` in a terminal → opens at the dragged spot.
  7. Picks still insert (Text Editor and Firefox).
- [ ] **Step 4: Record** results in the spec's "Testing" section and commit
  ("Spec: hands-on results").
