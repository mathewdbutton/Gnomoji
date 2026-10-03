"""Static checks on the extension's files (their behaviour is tested by hand in GNOME)."""

import json
from pathlib import Path

EXTENSION = Path(__file__).parent.parent / "extension"
UUID = "emoji-picker@mathewdbutton.github.io"


def source() -> str:
    return (EXTENSION / "extension.js").read_text(encoding="utf-8")


def test_metadata_is_valid():
    meta = json.loads((EXTENSION / "metadata.json").read_text(encoding="utf-8"))
    assert meta["uuid"] == UUID
    assert meta["shell-version"] == ["46", "47", "48", "49", "50"]
    assert meta["name"] == "Gnomoji"


def test_extension_restores_the_locate_pointer_key():
    text = source()
    assert "locate-pointer-key" in text
    assert "get_user_value(KEY)" in text
    assert "this._mutter.reset(KEY)" in text
    assert "this._mutter.set_value(KEY, this._oldKey)" in text


def test_extension_ignores_shell_modal_state():
    assert "Main.modalCount" in source()


def test_extension_declares_the_dbus_contract():
    text = source()
    for fragment in (
        '<method name="Insert"><arg type="s" direction="in" name="text"/></method>',
        '<method name="Configure"><arg type="a{sv}" direction="in" name="settings"/></method>',
        '<signal name="DoubleTap"/>',
        '<signal name="Ready"/>',
        "'double-tap-ms'",
    ):
        assert fragment in text


def test_no_settle_delay_is_left():
    for path in EXTENSION.glob("*.js"):
        text = path.read_text(encoding="utf-8")
        for gone in ("insert-delay-ms", "settle", "Settle"):
            assert gone not in text, (path.name, gone)


def test_extension_never_uses_the_clipboard():
    text = source()
    assert "Clipboard" not in text
    assert "notify_keyval" not in text


def insert_method() -> str:
    text = source()
    start = text.index("    Insert(text) {")
    return text[start:text.index("\n    }\n", start)]


def test_insert_checks_the_text_before_anything_else():
    text = source()
    assert "import {acceptInsert, decide} from './insertWaiter.js';" in text
    body = insert_method()
    assert "if (!acceptInsert(text))" in body
    assert body.index("acceptInsert(text)") < body.index("timeout_add")


def test_each_double_tap_arms_one_insert():
    body = insert_method()
    # Refused unless a double-tap armed it...
    assert "if (target === null)" in body
    assert body.index("target === null") < body.index("timeout_add")
    # ...and disarmed as soon as it's taken, so a second Insert needs a new double-tap.
    assert "this._target = null;" in body
    assert body.index("this._target = null;") < body.index("timeout_add")
