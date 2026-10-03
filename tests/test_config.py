import logging

from gnomoji.config import Config, Reloader, load


def write(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text)
    return path


def test_defaults_match_spec():
    assert Config() == Config(double_tap_ms=300)


def test_missing_file_gives_defaults(tmp_path):
    assert load(tmp_path / "nope.toml") == Config()


def test_reads_values(tmp_path):
    assert load(write(tmp_path, "double_tap_ms = 250\n")).double_tap_ms == 250


def test_wrong_type_falls_back_to_default(tmp_path, caplog):
    assert load(write(tmp_path, 'double_tap_ms = "fast"\n')) == Config()
    assert "double_tap_ms" in caplog.text


def test_bool_is_not_accepted_as_int(tmp_path):
    assert load(write(tmp_path, "double_tap_ms = true\n")).double_tap_ms == 300


def test_double_tap_ms_below_50_falls_back_to_default(tmp_path, caplog):
    assert load(write(tmp_path, "double_tap_ms = 49\n")).double_tap_ms == 300
    assert "double_tap_ms" in caplog.text


def test_double_tap_ms_above_2000_falls_back_to_default(tmp_path, caplog):
    # A typo with an extra digit would overflow the D-Bus u32 sent to the extension.
    assert load(write(tmp_path, "double_tap_ms = 30000000000\n")).double_tap_ms == 300
    assert load(write(tmp_path, "double_tap_ms = 2000\n")).double_tap_ms == 2000
    assert "double_tap_ms" in caplog.text


def test_malformed_toml_gives_defaults(tmp_path, caplog):
    assert load(write(tmp_path, "this is = = not toml")) == Config()
    assert "config" in caplog.text.lower()


def test_unknown_key_is_ignored(tmp_path, caplog):
    assert load(write(tmp_path, "colour = 'red'\n")) == Config()
    assert "colour" in caplog.text


def test_old_clipboard_settings_are_ignored_with_a_warning(tmp_path, caplog):
    text = (
        "double_tap_ms = 250\nrestore_clipboard = false\nrestore_delay_ms = 300\n"
        "paste_delay_ms = 80\nrelease_after_read_ms = 50\n"
    )
    with caplog.at_level(logging.WARNING):
        assert load(write(tmp_path, text)) == Config(double_tap_ms=250)
    for key in ("restore_clipboard", "restore_delay_ms", "paste_delay_ms", "release_after_read_ms"):
        assert key in caplog.text


# --- live reload: load(fallback=...) -----------------------------------------------

EDITED = Config(double_tap_ms=250)


def test_invalid_value_keeps_fallback_value(tmp_path, caplog):
    c = load(write(tmp_path, 'double_tap_ms = "fast"\n'), fallback=EDITED)
    assert c.double_tap_ms == 250
    assert "double_tap_ms" in caplog.text
    assert "250" in caplog.text


def test_malformed_toml_keeps_fallback(tmp_path, caplog):
    assert load(write(tmp_path, "this is = = not toml"), fallback=EDITED) == EDITED
    assert "keeping previous settings" in caplog.text


def test_missing_file_gives_defaults_even_with_fallback(tmp_path):
    assert load(tmp_path / "nope.toml", fallback=EDITED) == Config()


def test_absent_key_reverts_to_default_not_fallback(tmp_path):
    assert load(write(tmp_path, "# nothing set\n"), fallback=EDITED) == Config()


# --- live reload: Reloader --------------------------------------------------------


class Timers:
    def __init__(self):
        self.pending = []

    def schedule(self, ms, fn):
        self.pending.append((ms, fn))

    def run_all(self):
        while self.pending:
            _, fn = self.pending.pop(0)
            fn()


def make_reloader(path, current=None):
    timers, changes = Timers(), []
    reloader = Reloader(path, current or Config(), changes.append, timers.schedule)
    return reloader, timers, changes


def test_reloader_debounces_to_one_reload(tmp_path):
    path = write(tmp_path, "double_tap_ms = 250\n")
    reloader, timers, changes = make_reloader(path)
    for _ in range(3):
        reloader.file_changed()
    assert [ms for ms, _ in timers.pending] == [200, 200, 200]
    timers.run_all()
    assert changes == [Config(double_tap_ms=250)]


def test_reloader_calls_on_change_with_new_config(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    path = write(tmp_path, "")
    reloader, timers, changes = make_reloader(path)
    path.write_text("double_tap_ms = 400\n")
    reloader.file_changed()
    timers.run_all()
    assert changes == [Config(double_tap_ms=400)]
    assert reloader.current == Config(double_tap_ms=400)
    assert "double_tap_ms 300 -> 400" in caplog.text


def test_reloader_skips_on_change_when_unchanged(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    path = write(tmp_path, "double_tap_ms = 300\n")
    reloader, timers, changes = make_reloader(path)
    reloader.file_changed()
    timers.run_all()
    assert changes == []
    assert "reloaded" not in caplog.text.lower()


def test_reloader_bad_edit_keeps_last_good(tmp_path, caplog):
    path = write(tmp_path, "double_tap_ms = 250\n")
    reloader, timers, changes = make_reloader(path)
    reloader.file_changed()
    timers.run_all()
    path.write_text("double_tap_ms = = oops")
    reloader.file_changed()
    timers.run_all()
    assert changes == [Config(double_tap_ms=250)]
    assert reloader.current == Config(double_tap_ms=250)
    assert "keeping previous settings" in caplog.text


def test_reloader_file_created_later(tmp_path):
    path = tmp_path / "sub" / "config.toml"
    reloader, timers, changes = make_reloader(path)
    path.parent.mkdir()
    path.write_text("double_tap_ms = 400\n")
    reloader.file_changed()
    timers.run_all()
    assert changes == [Config(double_tap_ms=400)]


def test_reloader_on_change_error_is_logged_not_raised(tmp_path, caplog):
    path = write(tmp_path, "double_tap_ms = 250\n")

    def boom(config):
        raise RuntimeError("consumer broke")

    timers = Timers()
    Reloader(path, Config(), boom, timers.schedule).file_changed()
    timers.run_all()  # must not raise
    assert "consumer broke" in caplog.text


def test_real_file_monitor_drives_the_reloader(tmp_path):
    """Real Gio.FileMonitor + GLib timers, as __main__ wires them (no display needed)."""
    import os
    import time

    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib

    def schedule(ms, fn):
        GLib.timeout_add(ms, lambda: (fn(), GLib.SOURCE_REMOVE)[1])

    path = tmp_path / "config.toml"
    changes = []
    reloader = Reloader(path, Config(), changes.append, schedule)
    monitor = Gio.File.new_for_path(str(path)).monitor_file(Gio.FileMonitorFlags.NONE, None)
    monitor.connect("changed", lambda *_: reloader.file_changed())

    def spin_until(done, seconds=5.0):
        ctx, end = GLib.MainContext.default(), time.monotonic() + seconds
        while not done() and time.monotonic() < end:
            ctx.iteration(False)
            time.sleep(0.01)

    path.write_text("double_tap_ms = 400\n")  # created
    spin_until(lambda: len(changes) == 1)
    tmp = tmp_path / "config.toml.tmp"  # an editor's save-by-rename
    tmp.write_text("double_tap_ms = 450\n")
    os.rename(tmp, path)
    spin_until(lambda: len(changes) == 2)
    assert changes == [Config(double_tap_ms=400), Config(double_tap_ms=450)]
