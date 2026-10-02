import logging
from pathlib import Path

from gi.repository import Gio, GLib

from emoji_picker.shell import BUS_NAME, INTERFACE, OBJECT_PATH, UUID, ShellLink

EXTENSION_JS = Path(__file__).parent.parent / "extension" / "extension.js"


class FakeConnection:
    """Records Gio.DBusConnection.signal_subscribe/call like a real session bus."""

    def __init__(self, fail_with=None, reply=None):
        self.subscriptions, self.calls = [], []
        self.fail_with = fail_with
        self.reply = reply

    def signal_subscribe(self, sender, interface, member, path, arg0, flags, callback):
        self.subscriptions.append((sender, interface, member, path, arg0, flags, callback))
        return len(self.subscriptions)

    def call(self, name, path, interface, method, params, reply_type, flags, timeout,
             cancellable, callback):
        self.calls.append((name, path, interface, method, params.unpack()))
        callback(self, "result")

    def call_finish(self, result):
        if self.fail_with:
            raise self.fail_with
        return self.reply


def test_constants_match_the_extension():
    source = EXTENSION_JS.read_text(encoding="utf-8")
    assert f"'{OBJECT_PATH}'" in source
    assert f'interface name="{INTERFACE}"' in source
    assert BUS_NAME == "org.gnome.Shell"


def test_double_tap_signal_calls_back():
    conn = FakeConnection()
    taps = []
    ShellLink(conn).on_double_tap(lambda: taps.append(1))
    sender, interface, member, path, arg0, flags, callback = conn.subscriptions[0]
    assert (sender, interface, member, path, arg0) == (BUS_NAME, INTERFACE, "DoubleTap", OBJECT_PATH, None)
    assert flags == Gio.DBusSignalFlags.NONE
    callback(conn, ":1.5", OBJECT_PATH, INTERFACE, "DoubleTap", GLib.Variant("()", ()))
    assert taps == [1]


def test_subscribes_by_bus_name_so_a_late_extension_still_works():
    # A subscription filtered on the well-known name keeps working when the extension
    # (inside GNOME Shell) exports its object after we subscribed.
    conn = FakeConnection()
    ShellLink(conn).on_double_tap(lambda: None)
    assert conn.subscriptions[0][0] == "org.gnome.Shell"


def test_insert_calls_the_extension():
    conn = FakeConnection()
    ShellLink(conn).insert("🎉")
    assert conn.calls == [(BUS_NAME, OBJECT_PATH, INTERFACE, "Insert", ("🎉",))]


def test_insert_failure_is_logged_not_raised(caplog):
    conn = FakeConnection(fail_with=GLib.Error("No such interface"))
    ShellLink(conn).insert("🎉")
    assert "extension" in caplog.text
    assert "No such interface" in caplog.text


def test_ready_signal_calls_back():
    conn = FakeConnection()
    readies = []
    ShellLink(conn).on_ready(lambda: readies.append(1))
    sender, interface, member, path, arg0, _flags, callback = conn.subscriptions[0]
    assert (sender, interface, member, path, arg0) == (BUS_NAME, INTERFACE, "Ready", OBJECT_PATH, None)
    callback(conn, ":1.5", OBJECT_PATH, INTERFACE, "Ready", GLib.Variant("()", ()))
    assert readies == [1]


def test_configure_sends_the_double_tap_window():
    conn = FakeConnection()
    ShellLink(conn).configure(250)
    name, path, interface, method, params = conn.calls[0]
    assert (name, path, interface, method) == (BUS_NAME, OBJECT_PATH, INTERFACE, "Configure")
    assert params == ({"double-tap-ms": 250},)


def test_configure_before_the_extension_loads_is_not_an_error(caplog):
    # At login the service can start before GNOME Shell enables the extension; Ready
    # will trigger a re-send, so this is logged quietly rather than as an error.
    conn = FakeConnection(fail_with=GLib.Error("No such interface"))
    ShellLink(conn).configure(300)
    assert "ERROR" not in caplog.text


def info(state: float) -> GLib.Variant:
    return GLib.Variant("(a{sv})", ({"state": GLib.Variant("d", state)},))


def test_extension_active_asks_gnome_shell_about_our_uuid():
    conn = FakeConnection(reply=info(1.0))
    answers = []
    ShellLink(conn).extension_active(answers.append)
    assert conn.calls == [
        ("org.gnome.Shell", "/org/gnome/Shell", "org.gnome.Shell.Extensions",
         "GetExtensionInfo", (UUID,)),
    ]
    assert answers == [True]


def test_extension_known_but_not_running_is_not_active():
    conn = FakeConnection(reply=info(2.0))  # INACTIVE
    answers = []
    ShellLink(conn).extension_active(answers.append)
    assert answers == [False]


def test_extension_unknown_to_gnome_is_not_active():
    # Newly installed extension files are only noticed at log-in: GNOME answers {}.
    conn = FakeConnection(reply=GLib.Variant("(a{sv})", ({},)))
    answers = []
    ShellLink(conn).extension_active(answers.append)
    assert answers == [False]


def test_extension_state_query_failing_counts_as_not_active(caplog):
    caplog.set_level(logging.INFO)
    conn = FakeConnection(fail_with=GLib.Error("No GNOME Shell here"))
    answers = []
    ShellLink(conn).extension_active(answers.append)
    assert answers == [False]
    assert "No GNOME Shell here" in caplog.text
