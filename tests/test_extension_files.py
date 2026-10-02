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
    assert meta["name"] == "Emoji Picker"


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
