import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "src" / "emoji_picker" / "data" / "emoji.json"
GROUPS = [
    "Smileys & Emotion",
    "People & Body",
    "Animals & Nature",
    "Food & Drink",
    "Travel & Places",
    "Activities",
    "Objects",
    "Symbols",
    "Flags",
]


def entries():
    return json.loads(DATA.read_text(encoding="utf-8"))


def test_count_and_group_order():
    data = entries()
    assert len(data) == 1898
    assert list(dict.fromkeys(e["group"] for e in data)) == GROUPS


def test_every_entry_is_well_formed():
    for e in entries():
        assert set(e) - {"tones"} == {"emoji", "name", "group", "keywords"}
        assert e["emoji"] and e["name"]
        assert all(isinstance(k, str) for k in e["keywords"])


def _tones_in(char):
    return [c for c in char if 0x1F3FB <= ord(c) <= 0x1F3FF]


def test_skin_tone_variants_only_appear_in_tones():
    for e in entries():
        assert not _tones_in(e["emoji"]), e


def test_each_tones_list_is_the_five_tones_in_order():
    for e in entries():
        if "tones" in e:
            assert len(e["tones"]) == 5, e
            for i, char in enumerate(e["tones"]):
                assert set(_tones_in(char)) == {chr(0x1F3FB + i)}, (e, char)


def test_tones_cover_people_and_skip_everything_else():
    by_char = {e["emoji"]: e for e in entries()}
    assert by_char["👍"]["tones"][2] == "👍🏽"
    assert by_char["🧑‍🤝‍🧑"]["tones"][4] == "🧑🏿‍🤝‍🧑🏿"
    assert "tones" not in by_char["🍔"]
    assert "tones" not in by_char["😀"]


def test_party_popper_is_findable_by_tada():
    popper = next(e for e in entries() if e["emoji"] == "🎉")
    assert "tada" in popper["keywords"]
