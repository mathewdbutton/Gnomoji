"""Switch the GNOME Shell extension on for this person, once.

GNOME turns extensions on per person (org.gnome.shell enabled-extensions), and a .deb or
.rpm can't do that for anyone, so the app does it on its first start. A marker file makes
it once only: someone who later switches it off in the Extensions app keeps it off. The
marker is separate from 0.2.x's "welcomed", so people upgrading get it once too.

`python3 -m emoji_picker.extension_setup` switches it on now (install.sh runs this);
`--forget` takes it out of both lists (uninstall.sh runs this).
"""

import logging
import sys
from pathlib import Path

from .emoji_data import STATE_DIR
from .shell import UUID

log = logging.getLogger(__name__)

MARKER_PATH = STATE_DIR / "extension-enabled"
ENABLED, DISABLED = "enabled-extensions", "disabled-extensions"


def enable(settings) -> None:
    enabled = settings.get_strv(ENABLED)
    if UUID not in enabled:
        settings.set_strv(ENABLED, [*enabled, UUID])
    # disabled-extensions wins over enabled-extensions.
    forget_disabled(settings)


def forget(settings) -> None:
    enabled = settings.get_strv(ENABLED)
    if UUID in enabled:
        settings.set_strv(ENABLED, [u for u in enabled if u != UUID])
    forget_disabled(settings)


def forget_disabled(settings) -> None:
    disabled = settings.get_strv(DISABLED)
    if UUID in disabled:
        settings.set_strv(DISABLED, [u for u in disabled if u != UUID])


def enable_once(settings, marker: Path = MARKER_PATH) -> bool:
    """On this person's first start, switch the extension on. True if it was the first start."""
    if marker.exists():
        return False
    if settings is None:
        log.warning("GNOME Shell's settings aren't installed: can't switch the extension on")
    else:
        enable(settings)
        log.info("Switched the Gnomoji extension on (first start)")
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    except OSError as e:
        log.warning("Couldn't record the first start in %s: %s", marker, e)
    return True


def shell_settings():
    """org.gnome.shell settings, or None if GNOME Shell's schema isn't installed."""
    from gi.repository import Gio

    source = Gio.SettingsSchemaSource.get_default()
    if source is None or source.lookup("org.gnome.shell", True) is None:
        return None
    return Gio.Settings.new("org.gnome.shell")


def main(argv: list[str]) -> int:
    from gi.repository import Gio

    settings = shell_settings()
    if settings is None:
        print("GNOME Shell's settings aren't installed here.", file=sys.stderr)
        return 1
    if "--forget" in argv:
        forget(settings)
    else:
        enable(settings)
    Gio.Settings.sync()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
