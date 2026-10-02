// After the picker asks to insert, extension.js polls and asks decide() what to do.
// No GNOME imports, so it can be unit-tested with plain gjs
// (tests/extension/test_insert_waiter.js).

export const NO_IM_FOCUS_MS = 200; // focus is back, but no text field has checked in
export const GIVE_UP_MS = 1500; // focus never came back to the target window

// elapsedMs: since Insert was called.
// focusBack: the focused window is the one recorded at the double-tap.
// backForMs: how long focusBack has been true (0 if it isn't).
// imFocus: a text field has input-method focus.
export function decide({elapsedMs, focusBack, backForMs, imFocus}) {
    if (focusBack && imFocus)
        return 'commit';
    if (focusBack && backForMs >= NO_IM_FOCUS_MS)
        return 'no-text-field';
    if (elapsedMs >= GIVE_UP_MS)
        return 'focus-lost';
    return 'wait';
}
