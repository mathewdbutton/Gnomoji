"""use_fast_emoji_font: point FONTCONFIG_FILE at our bundled conf, process-only.

See docs/superpowers/specs/2026-09-25-emoji-picker-design.md, Feasibility result 11:
a user-installed COLRv1 "Noto Color Emoji" made first layout take minutes on this
machine. The bundled fonts.conf hides that file from fontconfig for our process only.
"""

import os
import subprocess

from conftest import require
from gnomoji.fonts import BUNDLED_CONF, use_fast_emoji_font


def test_sets_fontconfig_file_when_unset():
    environ = {}
    use_fast_emoji_font(environ=environ)
    assert environ["FONTCONFIG_FILE"] == str(BUNDLED_CONF)
    assert BUNDLED_CONF.is_file()


def test_does_not_override_existing_fontconfig_file(caplog):
    caplog.set_level("INFO")
    environ = {"FONTCONFIG_FILE": "/some/other/fonts.conf"}
    use_fast_emoji_font(environ=environ)
    assert environ["FONTCONFIG_FILE"] == "/some/other/fonts.conf"
    assert "FONTCONFIG_FILE" in caplog.text


def test_bundled_conf_includes_system_fonts_conf():
    text = BUNDLED_CONF.read_text(encoding="utf-8")
    assert "<include>/etc/fonts/fonts.conf</include>" in text


def test_bundled_conf_hides_vector_noto_color_emoji_from_fc_match():
    require("fc-match")
    result = subprocess.run(
        ["fc-match", "Noto Color Emoji", "file"],
        env={**os.environ, "FONTCONFIG_FILE": str(BUNDLED_CONF)},
        capture_output=True,
        text=True,
        check=True,
    )
    assert not result.stdout.strip().endswith("NotoColorEmoji-Regular.ttf")
