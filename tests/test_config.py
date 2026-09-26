from emoji_picker.config import Config, load


def write(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text)
    return path


def test_defaults_match_spec():
    c = Config()
    assert (c.double_tap_ms, c.restore_clipboard, c.restore_delay_ms, c.paste_delay_ms) == (
        300,
        True,
        300,
        80,
    )


def test_missing_file_gives_defaults(tmp_path):
    assert load(tmp_path / "nope.toml") == Config()


def test_reads_values(tmp_path):
    c = load(write(tmp_path, "double_tap_ms = 250\nrestore_clipboard = false\n"))
    assert c.double_tap_ms == 250
    assert c.restore_clipboard is False
    assert c.paste_delay_ms == 80


def test_wrong_type_falls_back_to_default(tmp_path, caplog):
    c = load(write(tmp_path, 'double_tap_ms = "fast"\nrestore_clipboard = 1\n'))
    assert c == Config()
    assert "double_tap_ms" in caplog.text
    assert "restore_clipboard" in caplog.text


def test_bool_is_not_accepted_as_int(tmp_path):
    assert load(write(tmp_path, "paste_delay_ms = true\n")).paste_delay_ms == 80


def test_negative_int_rejected(tmp_path):
    assert load(write(tmp_path, "restore_delay_ms = -5\n")).restore_delay_ms == 300


def test_double_tap_ms_zero_falls_back_to_default(tmp_path, caplog):
    c = load(write(tmp_path, "double_tap_ms = 0\n"))
    assert c.double_tap_ms == 300
    assert "double_tap_ms" in caplog.text


def test_malformed_toml_gives_defaults(tmp_path, caplog):
    assert load(write(tmp_path, "this is = = not toml")) == Config()
    assert "config" in caplog.text.lower()


def test_unknown_key_is_ignored(tmp_path, caplog):
    assert load(write(tmp_path, "colour = 'red'\n")) == Config()
    assert "colour" in caplog.text
