// Turns single right-Shift taps into double-taps. No GNOME imports, so it can be
// unit-tested with plain gjs (tests/extension/test_tap_detector.js).

export const DOUBLE_TAP_MS = 300;
export const MIN_DOUBLE_TAP_MS = 50;

export class TapDetector {
    constructor(windowMs = DOUBLE_TAP_MS) {
        this._windowMs = windowMs;
        this._last = null;
    }

    // Change the window (from the picker's config). Returns false, leaving the window
    // unchanged, unless `ms` is an integer of at least MIN_DOUBLE_TAP_MS.
    setWindow(ms) {
        if (!Number.isInteger(ms) || ms < MIN_DOUBLE_TAP_MS)
            return false;
        this._windowMs = ms;
        return true;
    }

    // Record a tap at `nowMs` (monotonic milliseconds). Returns true if it completes a
    // double-tap; the next tap then starts a new pair.
    tap(nowMs) {
        if (this._last !== null && nowMs - this._last <= this._windowMs) {
            this._last = null;
            return true;
        }
        this._last = nowMs;
        return false;
    }
}
