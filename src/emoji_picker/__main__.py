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

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib

from . import config as config_module
from .clipboard import ClipboardKeeper
from .emoji_data import EmojiData, Recents
from .flow import PasteFlow
from .injector import Injector
from .trigger import DoubleTapDetector, KeyboardWatcher, check_access
from .welcome import Welcome
from .window import PickerWindow

APP_ID = "local.emojipicker.EmojiPicker"
EXIT_SETUP_ERROR = 78  # EX_CONFIG: systemd unit is told not to restart on this

log = logging.getLogger("emoji_picker")


def _schedule(ms: int, fn) -> None:
    def once():
        fn()
        return GLib.SOURCE_REMOVE

    GLib.timeout_add(ms, once)


def _notifications(connection: Gio.DBusConnection):
    """Send (and later withdraw) the welcome straight to GNOME's notification service,
    not through Gio.Application.send_notification, which drops errors: we need to see
    InvalidApp to retry while GNOME hasn't noticed our new desktop file yet."""

    def send(on_result) -> None:
        params = GLib.Variant("(ssa{sv})", (APP_ID, "welcome", {
            "title": GLib.Variant("s", "Emoji Picker is ready"),
            "body": GLib.Variant("s", "Double-tap right Shift to open it."),
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


def _exit_on_watcher_crash() -> None:
    """Called from the watcher thread once it has died (trigger.KeyboardWatcher.run
    already logged the traceback). The double-tap trigger is the only way into the
    app, so a dead watcher must take the whole process down rather than leave a
    silently-broken service running.

    We marshal onto the GTK main loop with GLib.idle_add (required even though
    os._exit is thread-safe, to satisfy the "marshal to the main loop" contract and
    keep all GLib-adjacent calls on one thread), then call os._exit(1) there. We
    pick os._exit over quitting the Adw.Application and returning a stored failure
    code from main(): Gio.Application.run() always returns 0 after quit(), so that
    route needs an extra mutable flag threaded back out of the class; os._exit(1)
    gets a guaranteed non-zero (and non-78, so systemd's Restart=on-failure fires)
    exit status in one line, and there is no cleanup worth doing once we know the
    trigger is dead.
    """
    GLib.idle_add(lambda: os._exit(1))


class EmojiPickerApp(Adw.Application):
    def __init__(self, config: config_module.Config, data: EmojiData, injector: Injector):
        super().__init__(application_id=APP_ID)
        self._config, self._data, self._injector = config, data, injector
        self._flow: PasteFlow | None = None
        self._activated = False

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self.hold()  # stay alive with no visible window
        recents = Recents()
        window = PickerWindow(
            self,
            self._data,
            recents,
            on_pick=lambda emoji: self._flow.pick(emoji),
            on_focused=lambda: self._flow.on_focused(),
        )
        self._flow = PasteFlow(
            window, ClipboardKeeper(window.get_clipboard()), self._injector, recents,
            self._config, _schedule,
        )
        KeyboardWatcher(
            DoubleTapDetector(self._config.double_tap_ms),
            on_double_tap=lambda: GLib.idle_add(self._toggle_from_key),
            ignore_names={Injector.NAME},
            on_crash=_exit_on_watcher_crash,
        ).start()
        log.info("Ready: double-tap right Shift to open the picker")
        if (connection := self.get_dbus_connection()) is not None:
            send, withdraw = _notifications(connection)
            Welcome(send, withdraw, _schedule).start()

    def _toggle_from_key(self) -> bool:
        self._flow.toggle()
        return GLib.SOURCE_REMOVE

    def do_activate(self) -> None:
        # The first activation is the service starting, so stay hidden. Later ones come
        # from running `python3 -m emoji_picker` again, which toggles the picker.
        if self._activated:
            self._flow.toggle()
        self._activated = True


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        check_access()
        injector = Injector()
    except PermissionError as e:
        log.error("%s", e)
        return EXIT_SETUP_ERROR
    data = EmojiData.load()
    return EmojiPickerApp(config_module.load(), data, injector).run(sys.argv[:1])


if __name__ == "__main__":
    sys.exit(main())
