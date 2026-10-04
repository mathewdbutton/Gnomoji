# Gnomoji: open the picker at the text cursor (design)

**Status:** Built and accepted (2026-10-04); hands-on PASS on GNOME 46.

**Changes:** the "window opens where GNOME places it" and "can't reopen where it was dragged"
facts in `CLAUDE.md` and `2026-09-25-emoji-picker-design.md`. Everything else in
`2026-10-02-v2-port-design.md` (trigger, insert, install routes) stays as it is.

## Intent

The picker opens just below the text cursor of the field you double-tapped in, like the Mac
emoji panel, instead of wherever GNOME puts new windows (top-left by default). When there's no
usable cursor position, it opens where you last dragged it; failing that, where GNOME puts it,
as today.

What the user asked for, in order of preference: (1) at the text cursor; (2) if that fails,
where it was last dragged. Their answers: the dragged spot is remembered only until log-out (no
file); the picker goes below the cursor with its left edge lined up, flipping above when there's
no room; the screen edges (especially right and bottom) must be handled.

## Why this is possible now

A Wayland app can't place its own window, which is why the picker couldn't. The extension runs
inside GNOME Shell, which places windows, so it can move the picker with `Meta.Window.move_frame`.
**Only the extension changes.** The Python app, the D-Bus interface, the install routes and
`UNINSTALL.md` stay as they are.

## Spike findings (2026-10-04, GNOME 46, this machine; throwaway probe, not kept)

- GNOME Shell's input method stores the focused text field's cursor rectangle in
  `Main.inputMethod._cursorRect` (`js/misc/inputMethod.js`, `vfunc_set_cursor_location`), in
  screen (stage) coordinates. GNOME 50.0's `inputMethod.js` has the same code and the same field.
  It's private, so the extension reads it defensively (missing or malformed = no position).
- Checked live: Text Editor (window at 562,263 → cursor 574,323, x growing while typing),
  Firefox's address bar (612,43 → 417,43 while typing), the picker's own search box (followed the
  window when it was dragged from 50,82 to 1833,352), and an editor (cursor tracks lines).
- **It isn't cleared when focus moves**: with Firefox focused, it still held Text Editor's old
  position. Hence the "inside the target window" check below.
- **The picker's own search box overwrites it** as soon as the picker opens, so the position must
  be read at the double-tap, not when the picker appears.
- It's only set while IBus is running (`this._context`). Ubuntu and Fedora run IBus by default;
  without it there's no position and the fallback applies.

## Design

### At the double-tap

`_onTap()` already records `this._target` (the focused window) and only emits `DoubleTap` when a
text field has input-method focus. It also saves
`this._cursorAt = {rect, frame: target frame rect, atMs: now}` if `_cursorRect` is present. (The
"inside the target" check happens in `placement.js`, so it's tested.)

### When the picker window appears

Hiding the picker destroys its window; each opening creates a new `Meta.Window`. The extension
connects to `global.display`'s `'window-created'`, but can't recognise the picker there, and
can't move it there either.

On Wayland, `'window-created'` fires while Mutter is still constructing the window, from
`xdg_surface.get_toplevel` (`meta-wayland-xdg-shell.c` `xdg_surface_constructor_get_toplevel` ->
`meta_window_wayland_new` -> `window.c` `meta_window_initable_init` ->
`meta_display_notify_window_created`). The client's `xdg_toplevel.set_app_id` request, which
sets the wm class (`meta_window_set_wm_class`, `xdg-shell.c:281`), arrives later — so
`window.get_wm_class() === 'local.emojipicker.EmojiPicker'` can't match yet; `get_wm_class()` is
still null (same order in Mutter 50.0). GNOME also only places the window later, in
`meta_window_show` (`meta_window_force_placement`, line 2238), and `move_frame` doesn't mark a
window as placed, so an early move would be overwritten anyway even if the window could be
recognised.

So every new window — unless it already has a different, known wm class, which needs no wait —
gets a `'shown'` wait and an `'unmanaged'` wait, tracked per window in a `Map` (several windows
can be created before any of them is shown, and a window destroyed before `'shown'` must drop
its entry rather than being kept referenced). `meta_window_show` emits `'shown'` at its end
(line 2386), after placement and before the next repaint — by which point the app id is also
set, so that's where the picker is recognised (`get_wm_class() === APP_ID`). Both waits for that
window are disconnected first; then, if it's the picker:

1. Read the window's frame rect (its size is known by now).
2. Ask `placement.js` for a position (below) and, if it returns one, `move_frame(true, x, y)`.
3. Clear `this._cursorAt` (a saved position is used at most once).

Moving before the next repaint means it's never drawn in GNOME's spot first. That it doesn't
visibly jump is still a hands-on check.

### Remembering the dragged spot

Connect to `global.display`'s `'grab-op-end'` `(display, window, op)`. If `window` is the picker,
save its frame's `x, y` in `this._dragged`. The picker can't be resized (`window.py`,
`set_resizable(False)`), so any grab on it is a move (mouse or keyboard); this avoids depending
on `Meta.GrabOp` names, which have changed between GNOME versions. It's kept in memory only: lost at log-out or when the extension is disabled. A
cursor placement isn't a drag, so it doesn't overwrite it.

### `extension/placement.js` (new, pure, no GNOME imports)

```js
export const GAP = 4;            // px between the cursor's line and the picker
export const CURSOR_MAX_AGE_MS = 2000;

// cursorAt: {rect, frame, atMs} | null   size: {width, height}   dragged: {x, y} | null
// workAreaFor(rect) -> work area {x, y, width, height} of the monitor that rect is on
export function placePicker({cursorAt, nowMs, size, dragged, workAreaFor}) -> {x, y} | null
```

1. **Cursor**, if `cursorAt` is set, at most `CURSOR_MAX_AGE_MS` old, and its rect is a valid
   rect (finite numbers, height > 0; width may be 0, as GTK and Firefox send) whose top-left
   lies inside `cursorAt.frame`:
   - `wa = workAreaFor(rect)` (top bar and docks excluded).
   - `x = rect.x`, then clamped into `[wa.x, wa.x + wa.width - size.width]`, so it slides left at
     the right edge.
   - Below: `y = rect.y + rect.height + GAP`. If that overflows the work area's bottom, above:
     `y = rect.y - GAP - size.height`. If that overflows the top as well (screen too short),
     clamp `y` into the work area: the only case where it may cover the line being typed.
2. **Dragged spot**, otherwise, if `dragged` is set: `{x, y}` clamped into
   `workAreaFor({x, y, width: size.width, height: size.height})`, so a spot on a monitor that's
   since been unplugged still lands on screen.
3. **`null`** otherwise: leave it where GNOME put it.

If the picker is wider or taller than the work area, clamping puts it at the work area's left or
top edge.

`extension.js` passes `workAreaFor` as: `global.display.get_monitor_index_for_rect(new
Mtk.Rectangle(...))`, then `Main.layoutManager.getWorkAreaForMonitor(index)`.

### Lifecycle

`enable()` connects `'window-created'` and `'grab-op-end'`, and creates the `Map` of pending
`'shown'`/`'unmanaged'` waits. `disable()` disconnects `'window-created'` and `'grab-op-end'`,
disconnects every pending window's `'shown'` and `'unmanaged'` handlers and clears the map (so
nothing is left referencing a window after disable), and clears `_cursorAt` and `_dragged`.

### Opening without a double-tap

`gnomoji` from a terminal: no `_cursorAt`, so the dragged spot or
GNOME's placement, as above. The DoubleTap toggle closing an open picker creates no window, and
the saved position simply expires after 2 s.

## Files

- `extension/placement.js`: new, as above.
- `extension/extension.js`: the double-tap save, the two signal handlers, the header comment
  (a third job: "Placement").
- `tests/extension/test_placement.js`: new gjs tests, run by `tests/test_extension_js.py`.
- `tests/test_package.py`, `tests/test_install_scripts.py`: add `placement.js` to the extension
  file lists. `install.sh` and `packaging/build.sh` already copy `extension/*.js`.
- `tests/test_extension_files.py`: source checks that `extension.js` imports `placePicker`, only
  moves the window whose wm class is the app id, and disconnects its new handlers in `disable()`.
- `CLAUDE.md`: rewrite the two placement facts.
- `2026-09-25-emoji-picker-design.md`: a pointer at its placement text to this spec.
- `README.md`: one line on where the picker opens.
- `UNINSTALL.md`: no change (nothing new on disk).

## Testing

**gjs unit tests** (`test_placement.js`), using a 1920×1048 work area at 0,32 (a 1080p screen under a 32 px top bar) and a 380×420
picker:

- cursor in the middle → left edge at cursor x, top at cursor bottom + 4;
- near the right edge → slides left to `wa.x + wa.width - 380`, still below;
- near the bottom → opens above (`rect.y - 4 - 420`);
- bottom-right corner → both;
- near the left or top → pushed back inside;
- work area too short for above and below → clamped inside;
- second monitor (work area at 1920,0) → placed on that monitor's work area;
- cursor older than 2 s, outside the target frame, missing, NaN or zero height → dragged spot;
- dragged spot off every monitor → clamped into the work area it's given;
- nothing → `null`;
- a zero-width cursor (GTK, Firefox) is accepted.

**Hands-on** (needs a log-out, since extension code only loads at log-in): Text Editor and Firefox
with the cursor in the middle, at the right edge, and at the bottom of the screen; drag the picker,
then open it with `gnomoji` → dragged spot; no visible jump when it opens; picks still insert.

**Hands-on result (2026-10-04, Ubuntu 24.04, GNOME 46, `.deb` built from the branch): PASS.**
The extension came up after one log-out with no JS errors in the Shell log. Over a few minutes
in Text Editor and Firefox it logged ten `placed the picker at x,y` lines (Firefox's address bar
gave 347,65: its cursor at y 43, height 18, plus the 4 px gap), one `picker shown, no position to
use`, and three picks inserted in 10-11 ms, as before. The user's verdict: "it worked well". The
final review caught, before this test, that the picker can't be recognised at `'window-created'`
on Wayland (no app id yet); it's recognised at `'shown'` (see above). GNOME 47-50 not tried by
hand; the Mutter 50.0 source has the same signal order.
