import pytest

from emoji_picker.emoji_data import Emoji, EmojiData, Recents, SkinTone

GRIN = Emoji("😀", "grinning face", "Smileys & Emotion", ("face", "grin"))
CRY = Emoji("😢", "crying face", "Smileys & Emotion", ("sad", "tear"))
POPPER = Emoji("🎉", "party popper", "Activities", ("celebration", "party", "tada"))
PARTYING = Emoji("🥳", "partying face", "Smileys & Emotion", ("celebration", "party", "hat"))
FAMILY = Emoji("👨‍👩‍👧", "family: man, woman, girl", "People & Body", ("family",))
HEART = Emoji("❤️", "red heart", "Smileys & Emotion", ("love", "heart"))
WAVE = Emoji(
    "👋", "waving hand", "People & Body", ("wave",), tones=("👋🏻", "👋🏼", "👋🏽", "👋🏾", "👋🏿")
)


def data():
    return EmojiData([GRIN, CRY, POPPER, PARTYING, FAMILY, HEART, WAVE])


# --- EmojiData -------------------------------------------------------------


def test_groups_in_first_seen_order():
    assert data().groups == ["Smileys & Emotion", "Activities", "People & Body"]


def test_in_group_and_get():
    d = data()
    assert d.in_group("Activities") == [POPPER]
    assert d.get("🥳") is PARTYING
    assert d.get("🦖") is None


def test_empty_query_returns_nothing():
    assert data().search("") == []
    assert data().search("   ") == []


def test_exact_name_ranks_first():
    assert data().search("party popper")[0] is POPPER


def test_name_prefix_matches_in_data_order():
    assert data().search("party") == [POPPER, PARTYING]


def test_name_prefix_beats_keyword_match():
    balloon = Emoji("🎈", "balloon", "Activities", ("party",))
    d = EmojiData([balloon, POPPER])
    assert d.search("party") == [POPPER, balloon]


def test_word_in_name_matches():
    assert data().search("face") == [GRIN, CRY, PARTYING]
    assert data().search("girl") == [FAMILY]


def test_keyword_match():
    assert data().search("sad") == [CRY]
    assert data().search("tada") == [POPPER]


def test_query_is_case_and_space_insensitive():
    assert data().search("  Party  ") == data().search("party")
    assert data().search("RED   heart") == [HEART]


def test_load_real_data():
    d = EmojiData.load()
    assert len(d.emojis) == 1898
    assert d.search("tada")[0].char == "🎉"


def test_load_reads_tones():
    d = EmojiData.load()
    assert d.get("👍").tones[2] == "👍🏽"
    assert d.get("🍔").tones == ()


# --- Skin tones ------------------------------------------------------------


def test_with_tone_picks_that_variant_and_keeps_the_rest():
    medium = WAVE.with_tone(3)
    assert medium.char == "👋🏽"
    assert (medium.name, medium.group, medium.keywords) == (WAVE.name, WAVE.group, WAVE.keywords)


def test_with_tone_zero_or_no_tones_leaves_emoji_alone():
    assert WAVE.with_tone(0) is WAVE
    assert POPPER.with_tone(3) is POPPER


def test_in_group_and_search_apply_the_tone():
    d = data()
    assert [e.char for e in d.in_group("People & Body", tone=5)] == ["👨‍👩‍👧", "👋🏿"]
    assert [e.char for e in d.search("wav", tone=1)] == ["👋🏻"]
    assert d.in_group("People & Body") == [FAMILY, WAVE]


def test_get_finds_toned_variants():
    assert data().get("👋🏾") == WAVE.with_tone(4)


def test_load_fails_loudly_on_missing_or_corrupt_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        EmojiData.load(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{nope")
    with pytest.raises(ValueError):
        EmojiData.load(bad)


# --- Recents ---------------------------------------------------------------


def test_missing_file_is_empty(tmp_path):
    assert Recents(tmp_path / "recent.json").items == []


def test_add_puts_newest_first_and_dedupes(tmp_path):
    r = Recents(tmp_path / "recent.json")
    for c in ["😀", "🎉", "😀"]:
        r.add(c)
    assert r.items == ["😀", "🎉"]


def test_limit_is_enforced(tmp_path):
    r = Recents(tmp_path / "recent.json", limit=3)
    for c in ["1", "2", "3", "4", "5"]:
        r.add(c)
    assert r.items == ["5", "4", "3"]


def test_default_limit_is_24(tmp_path):
    r = Recents(tmp_path / "recent.json")
    for i in range(30):
        r.add(chr(0x1F600 + i))
    assert len(r.items) == 24


def test_persists_multi_codepoint_emoji_exactly(tmp_path):
    path = tmp_path / "state" / "recent.json"
    r = Recents(path)
    r.add("👨‍👩‍👧")
    r.add("❤️")
    assert Recents(path).items == ["❤️", "👨‍👩‍👧"]


def test_corrupt_file_is_treated_as_empty_and_overwritten(tmp_path):
    path = tmp_path / "recent.json"
    path.write_text("{not json")
    r = Recents(path)
    assert r.items == []
    r.add("😀")
    assert Recents(path).items == ["😀"]


def test_non_string_entries_are_dropped(tmp_path):
    path = tmp_path / "recent.json"
    path.write_text('["😀", 5, null, "🎉"]')
    assert Recents(path).items == ["😀", "🎉"]
    path.write_text('{"not": "a list"}')
    assert Recents(path).items == []


def test_resolve_skips_unknown_emoji(tmp_path):
    path = tmp_path / "recent.json"
    path.write_text('["🦖", "😀"]')
    assert Recents(path).resolve(data()) == [GRIN]


def test_resolve_keeps_each_recent_in_the_tone_it_was_picked(tmp_path):
    path = tmp_path / "recent.json"
    path.write_text('["👋🏽", "👋", "👋🏿"]')
    assert [e.char for e in Recents(path).resolve(data())] == ["👋🏽", "👋", "👋🏿"]


def test_unwritable_location_does_not_raise(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("")
    r = Recents(blocker / "recent.json")
    r.add("😀")
    assert r.items == ["😀"]


# --- SkinTone --------------------------------------------------------------


def test_skin_tone_defaults_to_zero_without_a_file(tmp_path):
    assert SkinTone(tmp_path / "skin-tone.json").value == 0


def test_skin_tone_persists(tmp_path):
    path = tmp_path / "state" / "skin-tone.json"
    SkinTone(path).set(4)
    assert SkinTone(path).value == 4


@pytest.mark.parametrize("text", ["{nope", "6", "-1", '"3"', "true", "2.0"])
def test_skin_tone_ignores_a_bad_file(tmp_path, text):
    path = tmp_path / "skin-tone.json"
    path.write_text(text)
    assert SkinTone(path).value == 0


def test_skin_tone_unwritable_location_does_not_raise(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("")
    tone = SkinTone(blocker / "skin-tone.json")
    tone.set(2)
    assert tone.value == 2
