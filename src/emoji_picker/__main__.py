"""Entry point: python3 -m emoji_picker"""

import logging
import os
import sys

from .fonts import use_fast_emoji_font

# Must run before fontconfig initialises. Empirically, `import gi` and
# `gi.require_version(...)` alone don't touch fontconfig, but the very first
# `from gi.repository import <anything>` does -- so this has to come before that
# import below, not merely before any GTK/Adw object is constructed. See fonts.py.
use_fast_emoji_font()

# GTK's GPU renderer loads Mesa, LLVM and Vulkan (~70 MB RSS) and keeps growing texture
# caches; software rendering is plenty for a small popup. Set before GTK initialises;
# an explicit GSK_RENDERER in the environment still wins.
os.environ.setdefault("GSK_RENDERER", "cairo")

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib

from . import config as config_module
from . import extension_setup
from .emoji_data import EmojiData, Recents, SkinTone
from .flow import PickerFlow
from .shell import ShellLink
from .welcome import Welcome, message
from .window import PickerWindow

APP_ID = "local.emojipicker.EmojiPicker"

log = logging.getLogger("emoji_picker")


def _schedule(ms: int, fn) -> None:
    def once():
        fn()
        return GLib.SOURCE_REMOVE

    GLib.timeout_add(ms, once)


def _notifications(connection: Gio.DBusConnection, title: str, body: str):
    """Send (and later withdraw) the welcome straight to GNOME's notification service,
    not through Gio.Application.send_notification, which drops errors: we need to see
    InvalidApp to retry while GNOME hasn't noticed our new desktop file yet."""

    def send(on_result) -> None:
        params = GLib.Variant("(ssa{sv})", (APP_ID, "welcome", {
            "title": GLib.Variant("s", title),
            "body": GLib.Variant("s", body),
            "icon": Gio.ThemedIcon.new(APP_ID).serialize(),
        }))

        def done(conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
            try:
                conn.call_finish(result)
            except GLib.Error as e:
                on_result(Gio.DBusError.get_remote_error(e) or e.message)
                return
            on_result(None)

        _call(connection, "AddNotification", params, done)

    def withdraw() -> None:
        _call(connection, "RemoveNotification", GLib.Variant("(ss)", (APP_ID, "welcome")), None)

    return send, withdraw


def _call(connection: Gio.DBusConnection, method: str, params: GLib.Variant, done) -> None:
    connection.call(
        "org.gtk.Notifications", "/org/gtk/Notifications", "org.gtk.Notifications",
        method, params, None, Gio.DBusCallFlags.NONE, -1, None, done,
    )


class EmojiPickerApp(Adw.Application):
    def __init__(self, config: config_module.Config, data: EmojiData):
        super().__init__(application_id=APP_ID)
        self._config, self._data = config, data
        self._flow: PickerFlow | None = None
        self._activated = False

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self.hold()  # stay alive with no visible window
        recents = Recents()
        window = PickerWindow(
            self, self._data, recents, SkinTone(), on_pick=lambda emoji: self._flow.pick(emoji)
        )
        connection = self.get_dbus_connection()
        self._shell = ShellLink(connection)
        self._flow = PickerFlow(window, self._shell, recents)
        self._shell.on_double_tap(self._flow.toggle)
        # The extension (re)loaded after us: send it the settings again.
        self._shell.on_ready(lambda: self._shell.configure(self._config.double_tap_ms))
        self._shell.configure(self._config.double_tap_ms)
        self._watch_config()
        self._first_start(connection)
        log.info("Ready: double-tap right Shift in a text field to open the picker")

    def _first_start(self, connection: Gio.DBusConnection) -> None:
        """Switch the extension on the first time this person runs us, then say whether
        it's ready or needs one log-out (GNOME only notices new extensions at log-in)."""
        if not extension_setup.enable_once(extension_setup.shell_settings()):
            return

        def welcome(active: bool) -> None:
            send, withdraw = _notifications(connection, *message(active))
            Welcome(send, withdraw, _schedule).start()

        self._shell.extension_active(welcome)

    def _watch_config(self) -> None:
        """Apply config.toml edits live. GLib's monitor also reports a file (or folder)
        created later, and editors' save-by-rename; the Reloader debounces the bursts."""
        path = config_module.DEFAULT_PATH
        self._reloader = config_module.Reloader(path, self._config, self._apply_config, _schedule)
        try:
            # Kept on self: a garbage-collected monitor silently stops reporting.
            self._config_monitor = Gio.File.new_for_path(str(path)).monitor_file(
                Gio.FileMonitorFlags.NONE, None
            )
        except GLib.Error as e:
            log.warning("Config changes need a restart: can't watch %s: %s", path, e)
            return
        self._config_monitor.connect("changed", lambda *_: self._reloader.file_changed())

    def _apply_config(self, config: config_module.Config) -> None:
        self._config = config
        self._shell.configure(config.double_tap_ms)

    def do_activate(self) -> None:
        # The first activation is the service starting, so stay hidden. Later ones come
        # from running `python3 -m emoji_picker` again, which toggles the picker.
        if self._activated:
            self._flow.toggle()
        self._activated = True


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return EmojiPickerApp(config_module.load(), EmojiData.load()).run(sys.argv[:1])


if __name__ == "__main__":
    sys.exit(main())
