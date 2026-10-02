// Emoji Picker, Shell half. The Python app (src/emoji_picker) draws the picker window;
// this extension does the two things only GNOME Shell can:
//
// 1. Trigger. Extensions can't see keys going to apps, but Mutter's "locate pointer"
//    key is a modifier-only tap detector that runs for them and lets the key continue
//    to the app (mutter 46 keybindings.c, process_locate_pointer_key). We point it at
//    Shift_R, count taps on the `global` 'locate-pointer' signal, and emit the D-Bus
//    signal DoubleTap when a text field has input-method focus.
// 2. Insert. Insert(text) waits for focus to come back to the window that was focused
//    at the double-tap and for its text field to check in with the input method, then
//    commits the text the way the on-screen keyboard does (Main.inputMethod.commit).
//    Apps without input-method focus (Qt apps like Konsole, X11 apps) can't be
//    reached; there is deliberately no clipboard fallback.
//
// The double-tap window comes from the picker's config file via Configure(a{sv}). The picker sends
// them at its startup and again whenever we emit Ready (on enable), so they arrive
// whichever of us starts first.
//
// Changes here only load at the next login. Logs:
//   journalctl -f -o cat /usr/bin/gnome-shell | grep emoji-picker

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

import {TapDetector} from './tapDetector.js';
import {decide} from './insertWaiter.js';

const KEY = 'locate-pointer-key';
const POLL_MS = 10;
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
    console.log(`[emoji-picker] ${msg}`);
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
        this._tapId = global.connect('locate-pointer', () => this._onTap());
        this._dbus = Gio.DBusExportedObject.wrapJSObject(DBUS_IFACE, this);
        this._dbus.export(Gio.DBus.session, DBUS_PATH);
        this._dbus.emit_signal('Ready', null);
        log('enabled');
    }

    disable() {
        global.disconnect(this._tapId);
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
        this._dbus.emit_signal('DoubleTap', null);
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

    // D-Bus method. The picker hides its window before calling this.
    Insert(text) {
        log(`insert requested (IM focus now: ${Boolean(Main.inputMethod.currentFocus)})`);
        this._stopPolling();
        const target = this._target;
        const start = nowMs();
        let backSince = null;
        this._pollId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, POLL_MS, () => {
            const now = nowMs();
            // Main.modalCount === 0: a Shell modal (e.g. the overview) can hold input-method
            // focus over the target even while it's the focus_window, so don't commit into it.
            const focusBack = target !== null && Main.modalCount === 0 && global.display.focus_window === target;
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
