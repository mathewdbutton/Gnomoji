"""Optional user configuration from ~/.config/emoji-picker/config.toml."""

import logging
import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_PATH = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "emoji-picker" / "config.toml"
)


@dataclass(frozen=True)
class Config:
    double_tap_ms: int = 300
    restore_clipboard: bool = True
    restore_delay_ms: int = 300
    paste_delay_ms: int = 80


def load(path: Path = DEFAULT_PATH) -> Config:
    """Read config, falling back to the default for anything missing or invalid."""
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Config()
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        log.warning("Ignoring unreadable config %s: %s", path, e)
        return Config()

    known = {f.name: f for f in fields(Config)}
    for key in raw.keys() - known.keys():
        log.warning("Ignoring unknown config key %r in %s", key, path)

    values = {}
    for name, f in known.items():
        if name not in raw:
            continue
        if _valid(f.type, raw[name], MIN_INT.get(name, 0)):
            values[name] = raw[name]
        else:
            log.warning("Invalid %s = %r in %s; using default %r", name, raw[name], path, f.default)
    return Config(**values)


# double_tap_ms must be positive or every tap is rejected (held > 0 in DoubleTapDetector);
# the other int fields are delays, which are meaningful at 0.
MIN_INT = {"double_tap_ms": 50}


def _valid(expected: type, value: object, minimum: int = 0) -> bool:
    if expected is bool:
        return isinstance(value, bool)
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum
