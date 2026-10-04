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
