"""Make our process use the fast bitmap Noto Color Emoji font. No GTK.

See docs/superpowers/specs/2026-09-25-emoji-picker-design.md, Feasibility result 11:
on at least one dev machine, fontconfig resolves "Noto Color Emoji" to a
user-installed COLRv1 *vector* font whose first layout of each distinct glyph costs
~50ms; across the picker's ~1,900 emoji that blocks the GTK main loop for minutes.
Ubuntu's apt CBDT *bitmap* font is ~250x faster. `use_fast_emoji_font` points
FONTCONFIG_FILE at a bundled fontconfig file (`data/fonts.conf`) that hides the
upstream vector filename from fontconfig for this process only: nothing outside
the repo is read, written or otherwise touched.

Must run before fontconfig is initialised. Empirically (see the font-fix report),
`import gi; gi.require_version(...)` alone does NOT touch fontconfig, but the very
first `from gi.repository import <anything>` does -- so this must be called before
that first import, not merely before GTK/Adw objects are constructed.
"""

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

BUNDLED_CONF = Path(__file__).parent / "data" / "fonts.conf"


def use_fast_emoji_font(environ: dict = os.environ) -> None:
    """Set FONTCONFIG_FILE to our bundled conf, unless it's already set.

    `environ` defaults to the real process environment; callers pass a plain dict
    in tests. Must be called before fontconfig initialises (see module docstring).
    """
    if "FONTCONFIG_FILE" in environ:
        log.info(
            "FONTCONFIG_FILE is already set to %r; leaving it alone (not applying %s)",
            environ["FONTCONFIG_FILE"],
            BUNDLED_CONF,
        )
        return
    environ["FONTCONFIG_FILE"] = str(BUNDLED_CONF)
