// Gnomoji, Shell half. The Python app (src/gnomoji) draws the picker window;
// this extension does the two things only GNOME Shell can:
//
// 1. Trigger. Extensions can't see keys going to apps, but Mutter's "locate pointer"
//    key is a modifier-only tap detector that runs for them and lets the key continue
//    to the app (mutter 46 keybindings.c, process_locate_pointer_key). We point it at
//    Shift_R, count taps on the `global` 'locate-pointer' signal, and emit the D-Bus
//    signal DoubleTap when a text field has input-method focus.
// 2. Insert. Each double-tap arms one Insert(text); without one, or for text that couldn't
//    be an emoji (acceptInsert in insertWaiter.js), it's refused. Insert waits for focus
//    to come back to the window that was focused at the double-tap and for its text
//    field to check in with the input method, then commits the text the way the
//    on-screen keyboard does (Main.inputMethod.commit). Apps without input-method focus
//    (Qt apps like Konsole, X11 apps) can't be reached; there is deliberately no
//    clipboard fallback.
// 3. Placement. At the double-tap we also save the text cursor's position (GNOME's input
//    method keeps it in the private Main.inputMethod._cursorRect, in screen coordinates; the
//    picker's own search box overwrites it once the picker opens, so it can't be read later).
//    When the picker's window is shown we move it just below that cursor (placement.js), or to
//    where it was last dragged (kept in memory until log-out or screen lock). The app can't
//    place its own window on Wayland; GNOME Shell can.
//
// The double-tap window comes from the picker's config file via Configure(a{sv}). The picker sends
// them at its startup and again whenever we emit Ready (on enable), so they arrive
// whichever of us starts first.
//
// Changes here only load at the next login. Logs:
//   journalctl -f -o cat /usr/bin/gnome-shell | grep gnomoji

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Mtk from 'gi://Mtk';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

import {TapDetector} from './tapDetector.js';
import {acceptInsert, decide} from './insertWaiter.js';
import {placePicker} from './placement.js';

const KEY = 'locate-pointer-key';
const POLL_MS = 10;
const APP_ID = 'local.emojipicker.EmojiPicker'; // the picker's app id (src/gnomoji/__main__.py)
const DBUS_PATH = '/io/github/mathewdbutton/EmojiPicker';
const DBUS_IFACE = `<node>
  <interface name="io.github.mathewdbutton.EmojiPicker">
    <method name="Insert"><arg type="s" direction="in" name="text"/></method>
    <method name="Configure"><arg type="a{sv}" direction="in" name="settings"/></method>
    <signal name="DoubleTap"/>
    <signal name="Ready"/>
  </interface>
</node>`;

function log(msg) {
    console.log(`[gnomoji] ${msg}`);
}

function nowMs() {
    return GLib.get_monotonic_time() / 1000;
}

export default class EmojiPickerExtension extends Extension {
    enable() {
        this._mutter = new Gio.Settings({schema_id: 'org.gnome.mutter'});
        this._oldKey = this._mutter.get_user_value(KEY);
        this._mutter.set_string(KEY, 'Shift_R');
        this._taps = new TapDetector();
        this._target = null;
        this._pollId = 0;
        this._cursorAt = null; // the text cursor saved at the last double-tap
        this._dragged = null; // where the picker was last dragged, until log-out or screen lock
        this._shownWait = null; // {window, id}: a new picker window we're waiting to see shown
        this._createdId = global.display.connect('window-created', (_display, window) => this._onWindowCreated(window));
        this._grabEndId = global.display.connect('grab-op-end', (_display, window) => this._onGrabEnd(window));
        this._tapId = global.connect('locate-pointer', () => this._onTap());
        this._dbus = Gio.DBusExportedObject.wrapJSObject(DBUS_IFACE, this);
        this._dbus.export(Gio.DBus.session, DBUS_PATH);
        this._dbus.emit_signal('Ready', null);
        log('enabled');
    }

    disable() {
        global.disconnect(this._tapId);
        global.display.disconnect(this._createdId);
        global.display.disconnect(this._grabEndId);
        this._cancelShownWait();
        this._cursorAt = null;
        this._dragged = null;
        this._stopPolling();
        this._dbus.unexport();
        // GNOME doesn't disable extensions at log-out, so dconf may still hold the 'Shift_R'
        // we wrote at enable() (from before a log-out, or a crash). Restore the user's own
        // value if we have one and it isn't that, otherwise go back to the default.
        if (this._oldKey === null || this._oldKey.unpack() === 'Shift_R')
            this._mutter.reset(KEY);
        else
            this._mutter.set_value(KEY, this._oldKey);
        this._mutter = null;
        this._dbus = null;
        this._taps = null;
        this._target = null;
        log('disabled');
    }

    _onTap() {
        if (!this._taps.tap(nowMs()))
            return;
        if (Main.modalCount > 0 || !global.display.focus_window)
            return; // no picker for Shell entries (overview, Alt+F2, a password prompt) or when no window has focus
        if (!Main.inputMethod.currentFocus)
            return; // no text field (or a Qt/X11 app): nowhere to insert, so don't open
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
    }

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

    // D-Bus method: settings from the picker's config file. Values arrive as GLib.Variants.
    Configure(settings) {
        const tapValue = settings['double-tap-ms'];
        if (tapValue === undefined)
            return;
        const ms = tapValue instanceof GLib.Variant ? tapValue.recursiveUnpack() : tapValue;
        if (!this._taps.setWindow(ms))
            log(`ignoring invalid double-tap-ms: ${ms}`);
    }

    // D-Bus method. The picker hides its window before calling this. Any process in the
    // session can call it, so it only takes one emoji-sized text, once per double-tap.
    Insert(text) {
        if (!acceptInsert(text)) {
            log('insert refused: not an emoji (too long, empty or has control characters)');
            return;
        }
        const target = this._target;
        if (target === null) {
            log('insert refused: no double-tap is waiting for one');
            return;
        }
        this._target = null; // a second Insert needs a new double-tap
        log(`insert requested (IM focus now: ${Boolean(Main.inputMethod.currentFocus)})`);
        this._stopPolling();
        const start = nowMs();
        let backSince = null;
        this._pollId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, POLL_MS, () => {
            const now = nowMs();
            // Main.modalCount === 0: a Shell modal (e.g. the overview) can hold input-method
            // focus over the target even while it's the focus_window, so don't commit into it.
            const focusBack = Main.modalCount === 0 && global.display.focus_window === target;
            if (focusBack && backSince === null)
                backSince = now;
            const imFocus = Boolean(Main.inputMethod.currentFocus);
            const verdict = decide({
                elapsedMs: now - start,
                focusBack,
                backForMs: focusBack ? now - backSince : 0,
                imFocus,
            });
            if (verdict === 'wait')
                return GLib.SOURCE_CONTINUE;
            if (verdict === 'commit') {
                Main.inputMethod.commit(text);
                log(`inserted after ${Math.round(now - start)} ms (focus back after ${Math.round(backSince - start)} ms)`);
            } else {
                log(`couldn't insert: ${verdict} after ${Math.round(now - start)} ms`);
            }
            this._pollId = 0;
            return GLib.SOURCE_REMOVE;
        });
    }

    _stopPolling() {
        if (this._pollId) {
            GLib.source_remove(this._pollId);
            this._pollId = 0;
        }
    }
}
