"""Generate src/emoji_picker/data/emoji.json from Unicode + CLDR sources.

One-off, needs network:  /usr/bin/python3 tools/build_emoji_data.py
The Unicode version is pinned to what fonts-noto-color-emoji on Ubuntu 24.04 can draw.
"""

import json
import re
import urllib.request
from pathlib import Path

EMOJI_VERSION = "15.1"
EMOJI_TEST_URL = f"https://unicode.org/Public/emoji/{EMOJI_VERSION}/emoji-test.txt"
CLDR = "https://raw.githubusercontent.com/unicode-org/cldr-json/main/cldr-json"
ANNOTATION_URLS = [
    f"{CLDR}/cldr-annotations-full/annotations/en/annotations.json",
    f"{CLDR}/cldr-annotations-derived-full/annotationsDerived/en/annotations.json",
]
OUT = Path(__file__).resolve().parent.parent / "src" / "emoji_picker" / "data" / "emoji.json"

SKIN_TONES = range(0x1F3FB, 0x1F3FF + 1)
SKIP_GROUPS = {"Component"}
LINE = re.compile(
    r"^(?P<cps>[0-9A-F ]+?)\s*;\s*fully-qualified\s*#\s*\S+\s+E[\d.]+\s+(?P<name>.+)$"
)


def parse_emoji_test(text: str) -> list[dict]:
    """Fully-qualified emoji in file order. A base emoji gets a "tones" list (light to
    dark) when all five single-tone variants exist; mixed-tone variants are dropped."""
    entries, group = [], None
    by_key: dict[tuple[int, ...], dict] = {}
    toned: dict[tuple[int, ...], dict[int, str]] = {}
    for line in text.splitlines():
        if line.startswith("# group:"):
            group = line.split(":", 1)[1].strip()
            continue
        match = LINE.match(line)
        if not match or group in SKIP_GROUPS:
            continue
        codepoints = [int(cp, 16) for cp in match["cps"].split()]
        char = "".join(map(chr, codepoints))
        tones = {cp for cp in codepoints if cp in SKIN_TONES}
        if len(tones) == 1:
            toned.setdefault(_key(codepoints), {}).setdefault(tones.pop(), char)
        elif not tones:
            entry = {"emoji": char, "name": match["name"], "group": group}
            entries.append(entry)
            by_key.setdefault(_key(codepoints), entry)
    for key, variants in toned.items():
        if key in by_key and len(variants) == len(SKIN_TONES):
            by_key[key]["tones"] = [variants[tone] for tone in SKIN_TONES]
    return entries


def _key(codepoints: list[int]) -> tuple[int, ...]:
    """Match a toned variant to its base: the tone replaces the base's FE0F, if any."""
    return tuple(cp for cp in codepoints if cp != 0xFE0F and cp not in SKIN_TONES)


def keywords_by_emoji(annotation_docs: list[dict]) -> dict[str, list[str]]:
    keywords: dict[str, list[str]] = {}
    for doc in annotation_docs:
        # Handle both "annotations" and "annotationsDerived" structures
        if "annotations" in doc:
            annotations = doc["annotations"].get("annotations", {})
        elif "annotationsDerived" in doc:
            annotations = doc["annotationsDerived"].get("annotations", {})
        else:
            continue
        for char, annotation in annotations.items():
            keywords.setdefault(char, []).extend(annotation.get("default", []))
    return keywords


def attach_keywords(entries: list[dict], keywords: dict[str, list[str]]) -> list[dict]:
    for entry in entries:
        raw = keywords.get(entry["emoji"]) or keywords.get(entry["emoji"].replace("️", ""), [])
        kept: list[str] = []
        for keyword in (k.lower() for k in raw):
            if keyword != entry["name"].lower() and keyword not in kept:
                kept.append(keyword)
        entry["keywords"] = kept
    return entries


def render(entries: list[dict]) -> str:
    return "[\n" + ",\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n]\n"


def _fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read().decode("utf-8")


def main() -> None:
    entries = parse_emoji_test(_fetch(EMOJI_TEST_URL))
    docs = [json.loads(_fetch(url)) for url in ANNOTATION_URLS]
    attach_keywords(entries, keywords_by_emoji(docs))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(entries), encoding="utf-8")
    print(f"wrote {len(entries)} emoji to {OUT}")


if __name__ == "__main__":
    main()
