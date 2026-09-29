"""The picker popup: search entry, category tabs, emoji grid and footer."""

import logging
from collections.abc import Callable

from .fonts import use_fast_emoji_font

# Must run before fontconfig initialises (before the first `from gi.repository import
# ...` below), so that a direct `python -m emoji_picker.window` preview also gets the
# fast font -- __main__.py already does this earlier for the normal app path, and this
# call is then a no-op (FONTCONFIG_FILE is already set). See fonts.py.
use_fast_emoji_font()

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk, Pango

from .emoji_data import TONE_COUNT, Emoji, EmojiData, Recents, SkinTone
from .selection import Selection, section_in_view

log = logging.getLogger(__name__)

COLUMNS = 8
MAX_RESULTS = 200
RECENT = "Recently used"
TONE_HANDS = ["✋", *(f"✋{chr(0x1F3FB + i)}" for i in range(TONE_COUNT))]
ICONS = {
    RECENT: "🕘",
    "Smileys & Emotion": "😀",
    "People & Body": "👋",
    "Animals & Nature": "🐻",
    "Food & Drink": "🍔",
    "Travel & Places": "✈️",
    "Activities": "⚽",
    "Objects": "💡",
    "Symbols": "🔣",
    "Flags": "🏁",
}
CSS = """
.emoji-cell { font-family: "Noto Color Emoji"; font-size: 22px; padding: 4px; }
.emoji-tab { font-family: "Noto Color Emoji"; font-size: 16px; padding: 2px 4px; min-width: 0; }
.emoji-tab.current { background: alpha(currentColor, 0.12); }
.tone-picker { font-family: "Noto Color Emoji"; }
.tone-list { background: @popover_bg_color; border-radius: 8px; padding: 4px;
             box-shadow: 0 2px 8px alpha(black, 0.3); }
.section-title { font-weight: bold; margin: 8px 8px 2px 8px; }
.clear-recents { font-size: small; min-height: 0; padding: 0 6px; margin: 6px 4px 0 0; }
.footer { padding: 6px 10px; }
.drag-strip { padding: 6px 0 4px 0; }
.drag-handle { background: alpha(currentColor, 0.25); border-radius: 2px; min-width: 36px; min-height: 4px; }
"""


class PickerWindow(Adw.ApplicationWindow):
    def __init__(
        self,
        application: Adw.Application,
        data: EmojiData,
        recents: Recents,
        skin_tone: SkinTone,
        on_pick: Callable[[Emoji], None],
        on_focused: Callable[[], None],
    ):
        super().__init__(application=application, title="Emoji Picker")
        self.set_default_size(380, 420)
        self.set_resizable(False)
        self.set_hide_on_close(True)
        self._data, self._recents, self._skin_tone = data, recents, skin_tone
        self._on_pick, self._on_focused = on_pick, on_focused
        self._was_active = False
        self._pressed = False  # a mouse button is down inside the picker (maybe a drag)
        self._selection = Selection([], COLUMNS)
        self._emojis_of: dict[Gtk.FlowBox, list[Emoji]] = {}
        self._title_of: dict[Gtk.FlowBox, str] = {}
        self._active: list[tuple[list[Emoji], Gtk.FlowBox]] = []

        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self._build()

        self.connect("notify::is-active", self._on_active_changed)
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)
        # GNOME takes focus away while it moves the window, so a focus loss during a
        # press is a drag, not a click-away. Button 0 = any button. No "cancel" handler:
        # the WindowHandle cancels this gesture as the drag starts, just before focus goes.
        clicks = Gtk.GestureClick(button=0, propagation_phase=Gtk.PropagationPhase.CAPTURE)
        clicks.connect("pressed", self._on_press)
        clicks.connect("released", lambda *_: self._set_pressed(False))
        self.add_controller(clicks)

    # --- construction ------------------------------------------------------

    def _build(self) -> None:
        self._entry = Gtk.SearchEntry(placeholder_text="Search emoji…", hexpand=True)
        self._entry.set_search_delay(0)
        self._entry.connect("search-changed", self._on_search_changed)
        # Recents keep the tone they were picked in; this applies to everything else.
        # The list is drawn inside the window, not as a popover: GNOME takes focus
        # from the picker when a popup closes, which reads as a click-away.
        self._tone_list = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, visible=False,
            halign=Gtk.Align.END, valign=Gtk.Align.START,
        )
        self._tone_list.add_css_class("tone-list")
        for tone, hand in enumerate(TONE_HANDS):
            button = Gtk.Button(label=hand, can_focus=False)
            button.add_css_class("flat")
            button.add_css_class("tone-picker")
            button.connect("clicked", lambda _b, t=tone: self._on_tone_chosen(t))
            self._tone_list.append(button)
        self._tone_picker = Gtk.ToggleButton(
            label=TONE_HANDS[self._skin_tone.value], tooltip_text="Skin tone", can_focus=False
        )
        self._tone_picker.add_css_class("tone-picker")
        self._tone_picker.connect("toggled", self._on_tone_picker_toggled)
        search_row = Gtk.Box(spacing=6)
        search_row.append(self._entry)
        search_row.append(self._tone_picker)

        titles = [RECENT, *self._data.groups]
        self._tabs = Gtk.Box(spacing=2, halign=Gtk.Align.CENTER)
        self._tab_buttons: dict[str, Gtk.Button] = {}
        for title in titles:
            button = Gtk.Button(label=ICONS.get(title, "•"), tooltip_text=title, can_focus=False)
            button.add_css_class("flat")
            button.add_css_class("emoji-tab")
            button.connect("clicked", lambda _b, t=title: self._jump_to(t))
            self._tabs.append(button)
            self._tab_buttons[title] = button

        self._browse = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._titles: dict[str, Gtk.Widget] = {}
        self._group_boxes: dict[str, Gtk.FlowBox] = {}
        for title in titles:
            label = Gtk.Label(label=title, xalign=0)
            label.add_css_class("section-title")
            heading = label
            if title == RECENT:
                label.set_hexpand(True)
                clear = Gtk.Button(label="Clear", tooltip_text="Clear recently used", can_focus=False)
                clear.add_css_class("flat")
                clear.add_css_class("clear-recents")
                clear.connect("clicked", self._on_clear_recents)
                heading = Gtk.Box()
                heading.append(label)
                heading.append(clear)
            box = self._make_box(
                [] if title == RECENT else self._data.in_group(title, self._skin_tone.value)
            )
            self._title_of[box] = title
            self._browse.append(heading)
            self._browse.append(box)
            self._titles[title] = heading
            self._group_boxes[title] = box

        self._results = self._make_box([])
        self._no_matches = Gtk.Label(label="No matches", margin_top=24)
        self._no_matches.add_css_class("dim-label")
        results_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        results_page.append(self._results)
        results_page.append(self._no_matches)

        self._stack = Gtk.Stack(vhomogeneous=False, hhomogeneous=False)
        self._stack.add_named(self._browse, "browse")
        self._stack.add_named(results_page, "search")
        self._scroll = Gtk.ScrolledWindow(
            vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER, child=self._stack
        )
        adj = self._scroll.get_vadjustment()
        adj.connect("value-changed", self._update_current_tab)
        adj.connect("changed", self._update_current_tab)  # content re-laid out

        self._footer = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self._footer.add_css_class("footer")

        top = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_start=8,
            margin_end=8, margin_bottom=4,
        )
        # Only a visual hint: the WindowHandle below makes every empty spot draggable.
        strip = Gtk.Box()
        strip.add_css_class("drag-strip")
        strip.set_cursor_from_name("grab")
        pill = Gtk.Box(halign=Gtk.Align.CENTER, hexpand=True)
        pill.add_css_class("drag-handle")
        strip.append(pill)
        top.append(search_row)
        top.append(self._tabs)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for widget in (strip, top, Gtk.Separator(), self._scroll, Gtk.Separator(), self._footer):
            content.append(widget)
        self._overlay = Gtk.Overlay(child=content)
        self._overlay.add_overlay(self._tone_list)
        self.set_content(Gtk.WindowHandle(child=self._overlay))

    def _make_box(self, emojis: list[Emoji]) -> Gtk.FlowBox:
        box = Gtk.FlowBox(
            homogeneous=True,
            min_children_per_line=COLUMNS,
            max_children_per_line=COLUMNS,
            selection_mode=Gtk.SelectionMode.SINGLE,
            activate_on_single_click=True,
            can_focus=False,
            valign=Gtk.Align.START,
        )
        box.connect("child-activated", self._on_child_activated)
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_hover, box)
        motion.connect("leave", lambda *_: self._show_footer())
        box.add_controller(motion)
        self._fill(box, emojis)
        return box

    def _fill(self, box: Gtk.FlowBox, emojis: list[Emoji]) -> None:
        box.remove_all()
        for i, emoji in enumerate(emojis):
            label = Gtk.Label(label=emoji.char)
            label.add_css_class("emoji-cell")
            box.append(label)
            box.get_child_at_index(i).set_can_focus(False)
        self._emojis_of[box] = emojis

    # --- public API used by PasteFlow -----------------------------------------

    def show_picker(self) -> None:
        self._entry.set_text("")
        self._enter_browse()
        self._scroll.get_vadjustment().set_value(0)
        self.present()
        self._entry.grab_focus()
        # GTK can keep is-active True across hide/show, so no notify fires on re-show
        # and click-away would be ignored. Sync with the current state once here.
        self._on_active_changed()

    def dismiss(self) -> None:
        self._close_tone_list()
        self._was_active = False
        self.set_visible(False)

    # --- modes ------------------------------------------------------------------

    def _enter_browse(self) -> None:
        recent = self._recents.resolve(self._data)
        self._fill(self._group_boxes[RECENT], recent)
        for widget in (self._titles[RECENT], self._group_boxes[RECENT], self._tab_buttons[RECENT]):
            widget.set_visible(bool(recent))
        self._active = [
            (self._emojis_of[box], box)
            for box in self._group_boxes.values()
            if self._emojis_of[box]
        ]
        self._stack.set_visible_child_name("browse")
        self._selection.reset([len(emojis) for emojis, _ in self._active])
        self._update_highlight()
        self._update_current_tab()

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        query = entry.get_text()
        if not query.strip():
            self._enter_browse()
            return
        results = self._data.search(query, self._skin_tone.value)[:MAX_RESULTS]
        self._fill(self._results, results)
        self._no_matches.set_visible(not results)
        self._active = [(results, self._results)]
        self._stack.set_visible_child_name("search")
        self._scroll.get_vadjustment().set_value(0)
        self._selection.reset([len(results)], select_first=True)
        self._update_highlight()
        self._update_current_tab()

    def _on_tone_picker_toggled(self, button: Gtk.ToggleButton) -> None:
        if button.get_active():
            # Drop the list down from just under the button, lined up with its right edge.
            ok, bounds = button.compute_bounds(self._overlay)
            if ok:
                self._tone_list.set_margin_top(int(bounds.get_y() + bounds.get_height()) + 2)
                right = bounds.get_x() + bounds.get_width()
                self._tone_list.set_margin_end(int(self._overlay.get_width() - right))
        self._tone_list.set_visible(button.get_active())

    def _close_tone_list(self) -> bool:
        """Close the tone list; True if it was open."""
        was_open = self._tone_picker.get_active()
        self._tone_picker.set_active(False)
        return was_open

    def _on_tone_chosen(self, tone: int) -> None:
        self._close_tone_list()
        self._tone_picker.set_label(TONE_HANDS[tone])
        self._skin_tone.set(tone)
        toned_groups = {e.group for e in self._data.emojis if e.tones}
        for title in toned_groups:
            self._fill(self._group_boxes[title], self._data.in_group(title, tone))
        if self._stack.get_visible_child_name() == "search":
            self._on_search_changed(self._entry)
        else:
            self._enter_browse()
        self._entry.grab_focus()

    def _on_clear_recents(self, _button: Gtk.Button) -> None:
        self._recents.clear()
        self._enter_browse()
        self._entry.grab_focus()

    # --- selection & scrolling ---------------------------------------------------

    def _selected(self) -> tuple[Emoji, Gtk.FlowBox, int] | None:
        if self._selection.index is None:
            return None
        section, offset = self._selection.locate(self._selection.index)
        emojis, box = self._active[section]
        return emojis[offset], box, offset

    def _update_highlight(self) -> None:
        for box in self._emojis_of:
            box.unselect_all()
        selected = self._selected()
        if selected is not None:
            _, box, offset = selected
            child = box.get_child_at_index(offset)
            box.select_child(child)
            self._scroll_to(child)
        self._show_footer()

    def _update_current_tab(self, *_args) -> None:
        """Highlight the tab of the category in view; none while searching."""
        titles = []
        if self._stack.get_visible_child_name() == "browse":
            titles = [self._title_of[box] for _, box in self._active]
        tops = []
        for title in titles:
            ok, bounds = self._titles[title].compute_bounds(self._stack)
            tops.append(bounds.get_y() if ok else 0.0)
        i = section_in_view(tops, self._scroll.get_vadjustment().get_value())
        current = titles[i] if i is not None else None
        for title, button in self._tab_buttons.items():
            if title == current:
                button.add_css_class("current")
            else:
                button.remove_css_class("current")

    def _show_footer(self, emoji: Emoji | None = None) -> None:
        if emoji is None and (selected := self._selected()) is not None:
            emoji = selected[0]
        self._footer.set_label(f"{emoji.char}  {emoji.name}" if emoji else "")

    def _scroll_to(self, widget: Gtk.Widget) -> None:
        ok, bounds = widget.compute_bounds(self._stack)
        if not ok:
            return
        adj = self._scroll.get_vadjustment()
        top, bottom = bounds.get_y(), bounds.get_y() + bounds.get_height()
        if top < adj.get_value():
            adj.set_value(top)
        elif bottom > adj.get_value() + adj.get_page_size():
            adj.set_value(bottom - adj.get_page_size())

    def _jump_to(self, title: str) -> None:
        if self._stack.get_visible_child_name() != "browse":
            self._entry.set_text("")
            self._enter_browse()
        ok, bounds = self._titles[title].compute_bounds(self._stack)
        if ok:
            self._scroll.get_vadjustment().set_value(bounds.get_y())

    def _next_section(self, step: int) -> None:
        self._selection.next_section(step)
        self._update_highlight()
        selected = self._selected()
        if selected is not None and self._stack.get_visible_child_name() == "browse":
            self._jump_to(self._title_of[selected[1]])

    # --- input -----------------------------------------------------------------

    def _on_key(self, _controller, keyval: int, _keycode: int, state: Gdk.ModifierType) -> bool:
        moves = {
            Gdk.KEY_Left: (-1, 0),
            Gdk.KEY_Right: (1, 0),
            Gdk.KEY_Up: (0, -1),
            Gdk.KEY_Down: (0, 1),
        }
        if keyval == Gdk.KEY_Escape:
            if not self._close_tone_list():
                self.dismiss()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            selected = self._selected()
            if selected is not None:  # Enter with nothing selected does nothing
                self._on_pick(selected[0])
            return True
        if keyval in moves:
            self._selection.move(*moves[keyval])
            self._update_highlight()
            return True
        if keyval in (Gdk.KEY_Page_Up, Gdk.KEY_Page_Down):
            adj = self._scroll.get_vadjustment()
            step = adj.get_page_size() * (1 if keyval == Gdk.KEY_Page_Down else -1)
            adj.set_value(adj.get_value() + step)
            return True
        if state & Gdk.ModifierType.CONTROL_MASK and keyval in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
            backwards = keyval == Gdk.KEY_ISO_Left_Tab or state & Gdk.ModifierType.SHIFT_MASK
            self._next_section(-1 if backwards else 1)
            return True
        return False

    def _on_child_activated(self, box: Gtk.FlowBox, child: Gtk.FlowBoxChild) -> None:
        self._on_pick(self._emojis_of[box][child.get_index()])

    def _on_hover(self, _controller, x: float, y: float, box: Gtk.FlowBox) -> None:
        child = box.get_child_at_pos(x, y)
        self._show_footer(self._emojis_of[box][child.get_index()] if child else None)

    def _on_press(self, gesture: Gtk.GestureClick, _n: int, x: float, y: float) -> None:
        self._set_pressed(True)
        if not self._tone_picker.get_active():
            return
        target = self.pick(x, y, Gtk.PickFlags.DEFAULT)
        inside = target is not None and (
            target.is_ancestor(self._tone_list) or target is self._tone_list
            or target.is_ancestor(self._tone_picker) or target is self._tone_picker
        )
        if not inside:
            # Like a dropdown: a click elsewhere only closes the list.
            self._close_tone_list()
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)

    def _set_pressed(self, pressed: bool) -> None:
        log.debug("Picker pressed=%s", pressed)
        self._pressed = pressed

    def _on_active_changed(self, *_args) -> None:
        log.debug(
            "Picker is-active=%s (was_active=%s, visible=%s, pressed=%s)",
            self.is_active(), self._was_active, self.get_visible(), self._pressed,
        )
        if self.is_active():
            self._pressed = False
            if not self._was_active:
                self._was_active = True
                self._on_focused()
        elif self._pressed:
            log.info("Picker lost focus mid-press: a drag, staying open")
        elif self._was_active and self.get_visible():
            log.info("Picker lost focus: closing (click-away)")
            self.dismiss()  # clicked away: close without inserting


if __name__ == "__main__":
    # Manual preview: python -m emoji_picker.window. Prints picks and doesn't paste.
    import sys

    def _activate(app: Adw.Application) -> None:
        window = PickerWindow(
            app,
            EmojiData.load(),
            Recents(),
            SkinTone(),
            on_pick=lambda e: print("picked", e.char, e.name, flush=True),
            on_focused=lambda: print("focused", flush=True),
        )
        window.show_picker()

    preview = Adw.Application(application_id="local.emojipicker.Preview")
    preview.connect("activate", _activate)
    sys.exit(preview.run(sys.argv[:1]))
