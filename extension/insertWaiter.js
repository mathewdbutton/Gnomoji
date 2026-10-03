// After the picker asks to insert, extension.js checks the text with acceptInsert(), then
// polls and asks decide() what to do. No GNOME imports, so it can be unit-tested with plain gjs
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

// Insert() takes one emoji, so refuse anything that couldn't be one: the longest in
// src/gnomoji/data/emoji.json is 10 code points (a kiss with two skin tones), and
// tests/test_emoji_json.py checks they all fit. Control characters (C0, DEL, C1) never
// appear in an emoji and could act as keys (Enter, Tab, Escape) in the target app.
export const MAX_INSERT_CODE_POINTS = 32;
const CONTROL = /[\u0000-\u001f\u007f-\u009f]/u;

export function acceptInsert(text) {
    if (typeof text !== 'string' || text === '')
        return false;
    if ([...text].length > MAX_INSERT_CODE_POINTS)
        return false;
    return !CONTROL.test(text);
}
