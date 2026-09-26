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
        assert set(e) == {"emoji", "name", "group", "keywords"}
        assert e["emoji"] and e["name"]
        assert all(isinstance(k, str) for k in e["keywords"])


def test_no_skin_tone_variants():
    for e in entries():
        assert not any(0x1F3FB <= ord(c) <= 0x1F3FF for c in e["emoji"]), e


def test_party_popper_is_findable_by_tada():
    popper = next(e for e in entries() if e["emoji"] == "🎉")
    assert "tada" in popper["keywords"]
