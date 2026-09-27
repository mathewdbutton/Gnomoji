"""Optional user configuration from ~/.config/emoji-picker/config.toml."""

import logging
import os
import tomllib
from collections.abc import Callable
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
    release_after_read_ms: int = 50


def load(path: Path = DEFAULT_PATH, fallback: Config | None = None) -> Config:
    """Read config. A missing file or key gives the default. An unreadable file or an
    invalid value keeps `fallback`'s (the previous settings when reloading; else defaults)."""
    previous = Config() if fallback is None else fallback
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Config()
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        keeping = "keeping previous settings" if fallback is not None else "using defaults"
        log.warning("Ignoring unreadable config %s (%s): %s", path, keeping, e)
        return previous

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
            kept = getattr(previous, name)
            values[name] = kept
            log.warning("Invalid %s = %r in %s; using %r", name, raw[name], path, kept)
    return Config(**values)


class Reloader:
    """Re-reads the config after the file changes (debounced: editors save in bursts, and
    by rename) and hands a changed Config to on_change. Keeps the last good settings."""

    DEBOUNCE_MS = 200

    def __init__(
        self,
        path: Path,
        current: Config,
        on_change: Callable[[Config], None],
        schedule: Callable[[int, Callable[[], None]], object],
    ):
        self.path, self.current = path, current
        self._on_change, self._schedule = on_change, schedule
        self._token = 0

    def file_changed(self) -> None:
        self._token += 1
        token = self._token
        self._schedule(self.DEBOUNCE_MS, lambda: self._reload(token))

    def _reload(self, token: int) -> None:
        if token != self._token:
            return
        new = load(self.path, fallback=self.current)
        if new == self.current:
            return
        changes = ", ".join(
            f"{f.name} {getattr(self.current, f.name)} -> {getattr(new, f.name)}"
            for f in fields(Config)
            if getattr(self.current, f.name) != getattr(new, f.name)
        )
        log.info("Config reloaded: %s", changes)
        self.current = new
        try:
            self._on_change(new)
        except Exception:
            log.exception("Applying the reloaded config failed")


# double_tap_ms must be positive or every tap is rejected (held > 0 in DoubleTapDetector);
# the other int fields are delays, which are meaningful at 0.
MIN_INT = {"double_tap_ms": 50}


def _valid(expected: type, value: object, minimum: int = 0) -> bool:
    if expected is bool:
        return isinstance(value, bool)
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum
