import json

from build_emoji_data import attach_keywords, keywords_by_emoji, parse_emoji_test, render

SAMPLE = """\
# group: Smileys & Emotion
# subgroup: face-smiling
1F600                                                  ; fully-qualified     # 😀 E1.0 grinning face
2764 FE0F                                              ; fully-qualified     # ❤️ E0.6 red heart
2764                                                   ; unqualified         # ❤ E0.6 red heart
# group: People & Body
1F44D                                                  ; fully-qualified     # 👍 E0.6 thumbs up
1F44D 1F3FB                                            ; fully-qualified     # 👍🏻 E1.0 thumbs up: light skin tone
1F468 200D 1F469 200D 1F467                            ; fully-qualified     # 👨‍👩‍👧 E2.0 family: man, woman, girl
# group: Component
1F3FB                                                  ; component           # 🏻 E1.0 light skin tone
# group: Activities
1F389                                                  ; fully-qualified     # 🎉 E0.6 party popper
"""

ANNOTATIONS = {
    "annotations": {
        "annotations": {
            "❤": {"default": ["love", "heart", "red heart"], "tts": ["red heart"]},
            "🎉": {"default": ["party", "Tada", "tada"], "tts": ["party popper"]},
        }
    }
}
DERIVED = {
    "annotations": {"annotations": {"👨‍👩‍👧": {"default": ["family"], "tts": ["x"]}}}
}


def test_keeps_fully_qualified_in_order_without_skin_tones():
    chars = [e["emoji"] for e in parse_emoji_test(SAMPLE)]
    assert chars == ["😀", "❤️", "👍", "👨‍👩‍👧", "🎉"]


def test_records_group_and_name():
    entries = {e["emoji"]: e for e in parse_emoji_test(SAMPLE)}
    assert entries["🎉"]["group"] == "Activities"
    assert entries["👨‍👩‍👧"]["name"] == "family: man, woman, girl"
    assert "Component" not in {e["group"] for e in entries.values()}


def test_keywords_match_without_variation_selector_and_are_deduped():
    entries = attach_keywords(parse_emoji_test(SAMPLE), keywords_by_emoji([ANNOTATIONS, DERIVED]))
    by_char = {e["emoji"]: e for e in entries}
    assert by_char["❤️"]["keywords"] == ["love", "heart"]  # name itself dropped
    assert by_char["🎉"]["keywords"] == ["party", "tada"]  # lowercased + deduped
    assert by_char["👨‍👩‍👧"]["keywords"] == ["family"]
    assert by_char["😀"]["keywords"] == []


def test_render_is_valid_json_one_entry_per_line():
    entries = attach_keywords(parse_emoji_test(SAMPLE), {})
    text = render(entries)
    assert json.loads(text) == entries
    assert text.count("\n") == len(entries) + 2
    assert "🎉" in text  # not \u-escaped
