"""Entry point: python3 -m emoji_picker"""

import logging
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib

from . import config as config_module
from .clipboard import ClipboardKeeper
from .emoji_data import EmojiData, Recents
from .flow import PasteFlow
from .injector import Injector
from .trigger import DoubleTapDetector, KeyboardWatcher, check_access
from .window import PickerWindow

APP_ID = "local.emojipicker.EmojiPicker"
EXIT_SETUP_ERROR = 78  # EX_CONFIG: systemd unit is told not to restart on this

log = logging.getLogger("emoji_picker")


def _schedule(ms: int, fn) -> None:
    def once():
        fn()
        return GLib.SOURCE_REMOVE

    GLib.timeout_add(ms, once)


class EmojiPickerApp(Adw.Application):
    def __init__(self, config: config_module.Config, data: EmojiData, injector: Injector):
        super().__init__(application_id=APP_ID)
        self._config, self._data, self._injector = config, data, injector
        self._flow: PasteFlow | None = None
        self._activated = False

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self.hold()  # stay alive with no visible window
        recents = Recents()
        window = PickerWindow(
            self,
            self._data,
            recents,
            on_pick=lambda emoji: self._flow.pick(emoji),
            on_focused=lambda: self._flow.on_focused(),
        )
        self._flow = PasteFlow(
            window, ClipboardKeeper(window.get_clipboard()), self._injector, recents,
            self._config, _schedule,
        )
        KeyboardWatcher(
            DoubleTapDetector(self._config.double_tap_ms),
            on_double_tap=lambda: GLib.idle_add(self._toggle_from_key),
            ignore_names={Injector.NAME},
        ).start()
        log.info("Ready: double-tap right Shift to open the picker")

    def _toggle_from_key(self) -> bool:
        self._flow.toggle()
        return GLib.SOURCE_REMOVE

    def do_activate(self) -> None:
        # The first activation is the service starting, so stay hidden. Later ones come
        # from running `python3 -m emoji_picker` again, which toggles the picker.
        if self._activated:
            self._flow.toggle()
        self._activated = True


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        check_access()
        injector = Injector()
    except PermissionError as e:
        log.error("%s", e)
        return EXIT_SETUP_ERROR
    data = EmojiData.load()
    return EmojiPickerApp(config_module.load(), data, injector).run(sys.argv[:1])


if __name__ == "__main__":
    sys.exit(main())
