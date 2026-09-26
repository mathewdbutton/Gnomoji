"""THROWAWAY feasibility probe for the emoji picker. Not part of the app.

Final version from the Task 1 spike (see the spec's "Feasibility results").

Usage:
  1. Copy some text (e.g. the word ORIGINAL) to the clipboard.
  2. Run:  /usr/bin/python3 spike/paste_probe.py shift-insert
     (chord: shift-insert | ctrl-v | ctrl-shift-v)
  3. Within 3 seconds, click into the target app's text field.
  4. When the small window appears, press Enter in it. It claims the clipboard with
     🎉 (GNOME needs that keypress), hides, and sends the paste chord through uinput.
  5. 300 ms later it swaps its own provider back to the saved text, without
     claiming the clipboard again. Paste by hand: you should get ORIGINAL.
  The clipboard empties when the probe exits. Ctrl+C in the terminal to quit.
"""

import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from evdev import UInput, ecodes as e  # noqa: E402
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk  # noqa: E402

class SwitchingText(Gdk.ContentProvider):
    """Serves `text` as a string; GTK converts to text/plain for other apps."""

    def __init__(self, text):
        super().__init__()
        self.text = text

    def do_ref_formats(self):
        b = Gdk.ContentFormatsBuilder.new()
        b.add_gtype(GObject.TYPE_STRING)
        return b.to_formats()

    def do_get_value(self):
        return True, self.text


EMOJI = "🎉"
CHORDS = {
    "ctrl-v": (e.KEY_LEFTCTRL, e.KEY_V),
    "ctrl-shift-v": (e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT, e.KEY_V),
    "shift-insert": (e.KEY_LEFTSHIFT, e.KEY_INSERT),
}
CHORD = CHORDS[sys.argv[1] if len(sys.argv) > 1 else "ctrl-shift-v"]
ui = UInput({e.EV_KEY: [e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT, e.KEY_V, e.KEY_INSERT]}, name="emoji-picker spike keyboard")
state = {"saved": None, "ours": None, "read_started": False}


def log(msg):
    print(f"[{time.monotonic():8.2f}] {msg}", flush=True)


def paste():
    for code in CHORD:
        ui.write(e.EV_KEY, code, 1)
        ui.syn()
    for code in reversed(CHORD):
        ui.write(e.EV_KEY, code, 0)
        ui.syn()


def on_activate(app):
    win = Gtk.ApplicationWindow(application=app, title="spike")
    win.set_default_size(300, 200)
    win.set_decorated(False)
    win.set_child(Gtk.Label(label="Press ENTER here to pick 🎉"))
    keys = Gtk.EventControllerKey()
    keys.connect("key-pressed", lambda _c, keyval, _k, _s: (pick(), True)[1] if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) else False)
    win.add_controller(keys)
    cb = win.get_clipboard()

    def on_read(clipboard, result):
        try:
            text = clipboard.read_text_finish(result)
        except GLib.Error as err:
            log(f"clipboard read FAILED: {err.message}")
            text = None
        state["saved"] = text
        log(f"saved clipboard: {text!r}")
        log(">>> now press ENTER in the spike window")

    def on_active(*_):
        log(f"is-active = {win.is_active()}")
        if win.is_active() and not state["read_started"]:
            state["read_started"] = True
            cb.read_text_async(None, on_read)

    def pick():
        provider = SwitchingText(EMOJI)
        state["ours"] = provider
        cb.set_content(provider)
        win.set_visible(False)
        log("set clipboard to emoji and hid window")
        GLib.timeout_add(80, do_paste)
        return False

    def do_paste():
        paste()
        log(f"sent {sys.argv[1:] or ['ctrl-shift-v']} via uinput")
        GLib.timeout_add(300, restore)
        return False

    def restore():
        log(f"clipboard still ours before restore: {cb.get_content() is state['ours']}")
        if state["saved"] is not None and cb.get_content() is state["ours"]:
            state["ours"].text = state["saved"]
            log("restore: provider now serves the saved text (no new clipboard takeover). Paste by hand to check.")
        return False

    def check_focus():
        if not win.is_active():
            log("WINDOW DID NOT GET FOCUS within 2 s")
        return False

    def show():
        log("presenting window")
        win.present()
        GLib.timeout_add(2000, check_focus)
        return False

    win.connect("notify::is-active", on_active)
    log("click into the target text field now (3 s)...")
    GLib.timeout_add(3000, show)
    app.hold()


app = Adw.Application(application_id="local.emojipicker.Spike")
app.connect("activate", on_activate)
app.run([sys.argv[0]])
