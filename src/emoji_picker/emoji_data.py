"""Emoji dataset, search ranking and recently-used tracking. No GTK."""

import json
import logging
import os
from dataclasses import dataclass, replace
from pathlib import Path

log = logging.getLogger(__name__)

DATA_PATH = Path(__file__).parent / "data" / "emoji.json"
STATE_DIR = (
    Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "emoji-picker"
)
RECENTS_PATH = STATE_DIR / "recent.json"
SKIN_TONE_PATH = STATE_DIR / "skin-tone.json"
TONE_COUNT = 5  # skin tones 1-5, light to dark; 0 is the default (no tone)


@dataclass(frozen=True)
class Emoji:
    char: str
    name: str
    group: str
    keywords: tuple[str, ...]
    tones: tuple[str, ...] = ()  # the five toned variants, light to dark, if it has them

    def with_tone(self, tone: int) -> "Emoji":
        """This emoji in skin tone 1-5; itself for tone 0 or if it has no tones."""
        if not tone or not self.tones:
            return self
        return replace(self, char=self.tones[tone - 1])


class EmojiData:
    def __init__(self, emojis: list[Emoji]):
        self.emojis = emojis
        self.groups = list(dict.fromkeys(e.group for e in emojis))
        self._by_char = {e.char: e for e in emojis}
        for emoji in emojis:
            for tone in range(1, len(emoji.tones) + 1):
                toned = emoji.with_tone(tone)
                self._by_char[toned.char] = toned
        self._words = [_words(e.name) for e in emojis]

    @classmethod
    def load(cls, path: Path = DATA_PATH) -> "EmojiData":
        """Load the bundled dataset. Errors propagate: a bad data file is a bug."""
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls([
            Emoji(r["emoji"], r["name"], r["group"], tuple(r["keywords"]), tuple(r.get("tones", ())))
            for r in raw
        ])

    def get(self, char: str) -> Emoji | None:
        """Any emoji by its character, toned variants included."""
        return self._by_char.get(char)

    def in_group(self, group: str, tone: int = 0) -> list[Emoji]:
        return [e.with_tone(tone) for e in self.emojis if e.group == group]

    def search(self, query: str, tone: int = 0) -> list[Emoji]:
        """Rank: exact name, name prefix, word-in-name prefix, keyword prefix."""
        q = " ".join(query.lower().split())
        if not q:
            return []
        ranked = []
        for i, emoji in enumerate(self.emojis):
            rank = self._rank(emoji, self._words[i], q)
            if rank is not None:
                ranked.append((rank, i, emoji))
        ranked.sort(key=lambda t: (t[0], t[1]))
        return [emoji.with_tone(tone) for _, _, emoji in ranked]

    @staticmethod
    def _rank(emoji: Emoji, words: list[str], q: str) -> int | None:
        name = emoji.name.lower()
        if name == q:
            return 0
        if name.startswith(q):
            return 1
        if any(w.startswith(q) for w in words):
            return 2
        if any(k.startswith(q) for k in emoji.keywords):
            return 3
        return None


def _words(name: str) -> list[str]:
    return name.lower().replace(":", " ").replace(",", " ").split()


class Recents:
    """Most-recently-used emoji, newest first, persisted as a JSON list."""

    def __init__(self, path: Path = RECENTS_PATH, limit: int = 24):
        self.path = path
        self.limit = limit
        self.items: list[str] = self._load()

    def add(self, char: str) -> None:
        self.items = [char] + [c for c in self.items if c != char]
        del self.items[self.limit :]
        self._save()

    def clear(self) -> None:
        self.items = []
        self._save()

    def resolve(self, data: EmojiData) -> list[Emoji]:
        return [emoji for c in self.items if (emoji := data.get(c)) is not None]

    def _load(self) -> list[str]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, ValueError) as e:
            log.warning("Ignoring unreadable recents file %s: %s", self.path, e)
            return []
        if not isinstance(raw, list):
            log.warning("Ignoring recents file %s: expected a list", self.path)
            return []
        return [c for c in raw if isinstance(c, str)][: self.limit]

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.items, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
        except OSError as e:
            log.warning("Could not save recents to %s: %s", self.path, e)


class SkinTone:
    """The chosen skin tone (0 = default, 1-5 light to dark), persisted as a JSON number."""

    def __init__(self, path: Path = SKIN_TONE_PATH):
        self.path = path
        self.value = self._load()

    def set(self, tone: int) -> None:
        self.value = tone
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(tone), encoding="utf-8")
            tmp.replace(self.path)
        except OSError as e:
            log.warning("Could not save skin tone to %s: %s", self.path, e)

    def _load(self) -> int:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return 0
        except (OSError, ValueError) as e:
            log.warning("Ignoring unreadable skin tone file %s: %s", self.path, e)
            return 0
        if type(raw) is not int or not 0 <= raw <= TONE_COUNT:
            log.warning("Ignoring skin tone file %s: expected 0-%d", self.path, TONE_COUNT)
            return 0
        return raw
