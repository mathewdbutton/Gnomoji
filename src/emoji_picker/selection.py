"""Keyboard selection over a grid split into sections (e.g. categories). No GTK.

Sections are stacked vertically; each starts on a fresh row and wraps at
`columns`. The selection is a flat index across all sections, or None.
"""


class Selection:
    def __init__(self, section_sizes: list[int], columns: int):
        if columns < 1:
            raise ValueError("columns must be >= 1")
        self.columns = columns
        self.sizes = list(section_sizes)
        self.index: int | None = None

    @property
    def total(self) -> int:
        return sum(self.sizes)

    def reset(self, section_sizes: list[int], select_first: bool = False) -> None:
        self.sizes = list(section_sizes)
        self.index = 0 if select_first and self.total else None

    def select(self, index: int | None) -> None:
        if index is None or self.total == 0:
            self.index = None
        else:
            self.index = max(0, min(index, self.total - 1))

    def section_start(self, section: int) -> int:
        return sum(self.sizes[:section])

    def locate(self, index: int) -> tuple[int, int]:
        for section, size in enumerate(self.sizes):
            if index < size:
                return section, index
            index -= size
        raise IndexError(index)

    def move(self, dx: int, dy: int) -> None:
        if self.total == 0:
            return
        if self.index is None:
            self.index = 0
            return
        if dx:
            self.select(self.index + dx)
            return
        section, offset = self.locate(self.index)
        row, col = divmod(offset, self.columns)
        size = self.sizes[section]
        if dy > 0:
            if (row + 1) * self.columns < size:
                self.index = self.section_start(section) + min(offset + self.columns, size - 1)
            elif (below := self._neighbour(section, 1)) is not None:
                self.index = self.section_start(below) + min(col, self.sizes[below] - 1)
        elif dy < 0:
            if row > 0:
                self.index -= self.columns
            elif (above := self._neighbour(section, -1)) is not None:
                last_row_start = (self.sizes[above] - 1) // self.columns * self.columns
                self.index = self.section_start(above) + min(
                    last_row_start + col, self.sizes[above] - 1
                )

    def next_section(self, step: int) -> None:
        """Select the first item of the next (step=1) or previous (step=-1) section.

        Wraps around at either end, skipping empty sections.
        """
        if self.total == 0:
            return
        if self.index is None:
            current = -1 if step > 0 else len(self.sizes)
        else:
            current = self.locate(self.index)[0]
        target = (current + step) % len(self.sizes)
        while not self.sizes[target]:
            target = (target + step) % len(self.sizes)
        self.index = self.section_start(target)

    def _neighbour(self, section: int, step: int) -> int | None:
        s = section + step
        while 0 <= s < len(self.sizes):
            if self.sizes[s]:
                return s
            s += step
        return None
