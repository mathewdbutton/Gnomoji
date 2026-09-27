from emoji_picker.selection import Selection


def sel(sizes, index=None, columns=4):
    s = Selection(sizes, columns)
    s.select(index)
    return s


def test_starts_with_nothing_selected():
    assert Selection([10], 4).index is None


def test_first_move_selects_first_item():
    for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
        s = Selection([10], 4)
        s.move(dx, dy)
        assert s.index == 0


def test_move_on_empty_grid_does_nothing():
    for sizes in ([], [0, 0]):
        s = Selection(sizes, 4)
        s.move(0, 1)
        assert s.index is None


def test_left_right_clamp_at_ends():
    s = sel([3], 0)
    s.move(-1, 0)
    assert s.index == 0
    s = sel([3], 2)
    s.move(1, 0)
    assert s.index == 2


def test_right_crosses_into_next_section():
    s = sel([2, 3], 1)
    s.move(1, 0)
    assert s.index == 2


def test_down_within_section():
    s = sel([10], 1)
    s.move(0, 1)
    assert s.index == 5


def test_down_into_short_last_row_clamps():
    s = sel([10], 7)
    s.move(0, 1)
    assert s.index == 9


def test_down_from_last_row_enters_next_section_same_column():
    s = sel([6, 8], 5)  # section 0 row 1 col 1
    s.move(0, 1)
    assert s.index == 7  # section 1 offset 1


def test_down_into_narrow_next_section_clamps():
    s = sel([4, 2], 3)  # col 3
    s.move(0, 1)
    assert s.index == 5  # section 1 offset 1 (last)


def test_down_at_very_end_stays():
    s = sel([5], 4)
    s.move(0, 1)
    assert s.index == 4


def test_up_within_section():
    s = sel([10], 6)
    s.move(0, -1)
    assert s.index == 2


def test_up_into_previous_section_last_row():
    s = sel([6, 8], 8)  # section 1 offset 2, col 2
    s.move(0, -1)
    assert s.index == 5  # section 0 last row is offsets 4-5; col 2 clamps to 5


def test_up_at_top_stays():
    s = sel([10], 2)
    s.move(0, -1)
    assert s.index == 2


def test_empty_sections_are_skipped():
    s = sel([4, 0, 4], 1)
    s.move(0, 1)
    assert s.index == 5


def test_reset():
    s = sel([5], 3)
    s.reset([5], select_first=True)
    assert s.index == 0
    s.reset([0], select_first=True)
    assert s.index is None
    s.reset([5])
    assert s.index is None


def test_select_clamps_and_accepts_none():
    s = sel([5], 99)
    assert s.index == 4
    s.select(None)
    assert s.index is None


def test_locate_and_section_start():
    s = Selection([3, 0, 4, 2], 4)
    assert s.locate(4) == (2, 1)
    assert s.section_start(3) == 7


def test_next_section_forward_and_back():
    s = Selection([3, 0, 4, 2], 4)
    s.next_section(1)
    assert s.index == 0
    s.select(1)
    s.next_section(1)
    assert s.index == 3
    s.next_section(1)
    assert s.index == 7
    s.next_section(-1)
    assert s.index == 3
    s.next_section(-1)
    assert s.index == 0


def test_next_section_wraps_both_ways():
    s = sel([3, 0, 4, 2], 7)  # last section
    s.next_section(1)
    assert s.index == 0  # back to the first
    s.next_section(-1)
    assert s.index == 7  # round to the last


def test_next_section_wrap_skips_empty_sections():
    s = sel([0, 3, 4, 0], 3)  # last non-empty section
    s.next_section(1)
    assert s.index == 0  # section 1, skipping empty section 0
    s.next_section(-1)
    assert s.index == 3  # section 2, skipping empty section 3


def test_next_section_with_one_section_stays():
    s = sel([0, 5, 0], 2)
    s.next_section(1)
    assert s.index == 0
