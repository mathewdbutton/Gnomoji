"""The picker's link to its GNOME Shell extension (extension/extension.js) over D-Bus.

The extension spots the right-Shift double-tap and emits DoubleTap; we answer by
toggling the picker. After a pick we hide the window and call Insert(text), and the
extension types it into the app that was focused (GNOME's input method, no clipboard).
The double-tap window from the config file goes over
with Configure, at our startup and whenever the extension emits Ready.
The extension exports its object on GNOME Shell's own session-bus connection, so we
address it by the bus name org.gnome.Shell.
"""

import logging
from collections.abc import Callable

from gi.repository import Gio, GLib

log = logging.getLogger(__name__)

BUS_NAME = "org.gnome.Shell"
OBJECT_PATH = "/io/github/mathewdbutton/EmojiPicker"
INTERFACE = "io.github.mathewdbutton.EmojiPicker"
UUID = "emoji-picker@mathewdbutton.github.io"
ACTIVE = 1.0  # GNOME Shell's ExtensionState.ACTIVE (named ENABLED before GNOME 46)


class ShellLink:
    def __init__(self, connection):
        self._connection = connection

    def on_double_tap(self, callback: Callable[[], None]) -> None:
        """Call `callback` on the main loop whenever the extension reports a double-tap.

        The subscription is by bus name, so it works even if the extension is enabled
        after we start (e.g. the service starts before GNOME Shell loads extensions).
        """
        self._connection.signal_subscribe(
            BUS_NAME, INTERFACE, "DoubleTap", OBJECT_PATH, None,
            Gio.DBusSignalFlags.NONE, lambda *_args: callback(),
        )

    def on_ready(self, callback: Callable[[], None]) -> None:
        """Call `callback` whenever the extension is (re)enabled, to (re)send settings."""
        self._connection.signal_subscribe(
            BUS_NAME, INTERFACE, "Ready", OBJECT_PATH, None,
            Gio.DBusSignalFlags.NONE, lambda *_args: callback(),
        )

    def insert(self, text: str) -> None:
        """Ask the extension to type `text` into the app the double-tap came from."""
        self._connection.call(
            BUS_NAME, OBJECT_PATH, INTERFACE, "Insert", GLib.Variant("(s)", (text,)),
            None, Gio.DBusCallFlags.NONE, -1, None, self._on_insert_done,
        )

    def configure(self, double_tap_ms: int) -> None:
        """Send the extension the double-tap window from the config file."""
        settings = {"double-tap-ms": GLib.Variant("u", double_tap_ms)}
        self._connection.call(
            BUS_NAME, OBJECT_PATH, INTERFACE, "Configure", GLib.Variant("(a{sv})", (settings,)),
            None, Gio.DBusCallFlags.NONE, -1, None, self._on_configure_done,
        )

    def extension_active(self, callback: Callable[[bool], None]) -> None:
        """Ask GNOME Shell whether our extension is running; answer True or False."""

        def done(connection, result) -> None:
            try:
                (info,) = connection.call_finish(result).unpack()
            except GLib.Error as e:
                log.info("Couldn't ask GNOME Shell about the extension: %s", e.message)
                callback(False)
                return
            callback(info.get("state") == ACTIVE)

        self._connection.call(
            BUS_NAME, "/org/gnome/Shell", "org.gnome.Shell.Extensions", "GetExtensionInfo",
            GLib.Variant("(s)", (UUID,)), None, Gio.DBusCallFlags.NONE, -1, None, done,
        )

    def _on_insert_done(self, connection, result) -> None:
        try:
            connection.call_finish(result)
        except GLib.Error as e:
            log.error("Couldn't insert (is the Gnomoji extension enabled?): %s", e.message)

    def _on_configure_done(self, connection, result) -> None:
        try:
            connection.call_finish(result)
        except GLib.Error as e:
            # Normal at login: the extension isn't enabled yet, and resends follow on Ready.
            log.info("Extension not ready for settings yet (will resend when it is): %s", e.message)
