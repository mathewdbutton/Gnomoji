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


def method(name: str) -> str:
    text = source()
    start = text.index(f"    {name}(")
    return text[start:text.index("\n    }\n", start)]


def test_extension_knows_the_picker_app_id():
    main = (EXTENSION.parent / "src" / "gnomoji" / "__main__.py").read_text(encoding="utf-8")
    assert 'APP_ID = "local.emojipicker.EmojiPicker"' in main
    assert "const APP_ID = 'local.emojipicker.EmojiPicker';" in source()
    assert "get_wm_class() === APP_ID" in method("_isPicker")


def test_extension_places_the_picker_after_gnome_does():
    text = source()
    assert "import {placePicker} from './placement.js';" in text
    created = method("_onWindowCreated")
    # 'window-created' is before GNOME's own placement; moving there would be undone.
    assert "move_frame" not in created
    assert "connect('shown'" in created
    # On Wayland, 'window-created' is also before the app id is set, so the early return must
    # only skip windows already known to be something else, not ones with no wm class yet.
    assert "wmClass && wmClass !== APP_ID" in created
    assert "connect('unmanaged'" in created
    assert created.index("this._isPicker(window)") < created.index("this._place(window)")
    assert "move_frame(true, at.x, at.y)" in method("_place")


def test_cursor_is_read_at_the_double_tap_only():
    code = [line for line in source().splitlines() if not line.strip().startswith("//")]
    assert sum("_cursorRect" in line for line in code) == 1
    assert "_cursorRect" in method("_onTap")
    assert "this._cursorAt = null;" in method("_place")  # used at most once


def test_only_picker_drags_are_remembered():
    body = method("_onGrabEnd")
    assert "this._isPicker(window)" in body
    assert body.index("this._isPicker(window)") < body.index("this._dragged =")


def test_work_area_falls_back_to_the_primary_monitor():
    body = method("_workAreaFor")
    assert "get_monitor_index_for_rect" in body
    assert "get_primary_monitor()" in body


def test_disable_disconnects_placement_handlers():
    body = method("disable")
    for fragment in (
        "global.display.disconnect(this._createdId)",
        "global.display.disconnect(this._grabEndId)",
        "this._cancelShownWait(window)",
        "this._shownWaits = null;",
        "this._cursorAt = null;",
        "this._dragged = null;",
    ):
        assert fragment in body, fragment
