"""Options rendered in place, on one line, instead of behind a menu.

A dropdown answers "what is chosen" and hides "what else was possible", and while it is open
it paints over the questions around it, which are exactly what the user is comparing against.
This renders every option of a question on a single line: the one in force is lit, the ones
passed over stay legible beside it, and left and right move between them without opening
anything.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any, ClassVar

from rich._wrap import divide_line
from rich.cells import cell_len, set_cell_size
from rich.text import Text
from textual.binding import Binding
from textual.geometry import Size
from textual.message import Message
from textual.widgets import Static

from copier_tui.theme import (
    CURSOR_BG,
    CURSOR_FG,
    CURSOR_PICKED_BG,
    CURSOR_PICKED_FG,
    MARK_SHADES,
    OPTION_BG,
    OPTION_FG,
    PICKED_BG,
    PICKED_FG,
)
from copier_ui import Choice

BOOL_CHOICES = (Choice(label="No", value=False), Choice(label="Yes", value=True))
"""A boolean is a two-option question, and reads better as one than as a toggle whose
current state has to be inferred from which side a knob sits on."""

GAP = " "
"""One space between chips on a row that fits on one line."""

TAKEN = "\u25cf"
FREE = "\u25cb"
"""Filled and empty circle: whether an option is the answer, said in the shape as well as in
the colour. Both measure one cell, so neither shifts the column the labels start in."""

CURSOR = "\u25fc"
"""Marks the option the cursor is on, and only while the row has the focus.

A solid square that fills its cell, rather than the small triangle it started as: at one row
per question the mark is the only thing saying where along the options the cursor stands, and
a glyph a third the height of its cell is a mark the eye has to go looking for. A square also
cannot be confused with the chip it sits beside, whose own mark is a circle - which rules out
the large circle, the one shape that reads as strongly at this size.

Every candidate was checked for East Asian width first. This one is N, so no terminal may draw
it two cells wide. `\u25b6` and `\u25a0` are the obvious triangle and square and both are
Ambiguous: a terminal set to render ambiguous characters wide gives them two cells while
`rich.cells.cell_len` counts one, and everything after the mark lands a column out.

The ground alone could not carry this. When the cursor sits on the answer - which is where it
starts, every time - a ground says "chosen" and has nothing left to say "and you are here", so
the two facts collapsed into one and the row stopped showing which option was about to move."""


CHIP_FLOOR = 6
"""The least room a label is ever wrapped into. Below it the split is one character per line -
measured, a four-option row 131 lines tall, each carrying a single letter - which is shredding
rather than wrapping. It happens only under MIN_WIDTH, where the advisory is already up, so the
row clips instead and the reader is being told to resize."""

CHIP_CHROME = 5
"""Cells a stacked chip spends on things that are not its label: the cursor mark, the space
before the shape, the shape itself, the space after it, and the trailing space that closes the
ground. Named because the wrapper and the height count both subtract it, and they must not
disagree - which is the drift this whole mechanism exists to make impossible."""


def _wrapped(label: str, room: int) -> list[str]:
    """A chip's label broken into the lines it will occupy, never fewer than one.

    Divided by CELLS, not by characters. `textwrap` counts characters, and a terminal draws
    cells: an emoji or a CJK label counted by characters overflows its column, Rich re-wraps
    it inside a box whose height came from the character count, and the surplus lines - whole
    later options - are clipped away with nothing reporting it. Measured on an emoji label,
    an option vanished at 24 of the 71 widths from 50 to 120, one of them MIN_WIDTH.

    That is exactly the defect this module was rewritten to make impossible, reintroduced by
    the rewrite, in the one file that documents cell width on every glyph it prints.
    """
    room = max(room, CHIP_FLOOR)
    if not label:
        return [""]
    lines: list[str] = []
    start = 0
    for offset in [*divide_line(label, room, fold=True), len(label)]:
        piece = label[start:offset].rstrip()
        if piece or not lines:
            lines.append(piece)
        start = offset
    return lines or [""]


def _stack(
    choices: Sequence[Choice],
    marks: Sequence[tuple[str, str, str]],
    width: int,
    shade: str,
) -> Text:
    """Every option on its own line or lines, each chip a rectangle under its own mark.

    The wrapping is done here rather than left to Rich, and that is the whole point. It used to
    be modelled - the height reserved by dividing a chip's width by the column's - while the
    paint let Rich word-wrap the same text, so the two disagreed in both directions: a blank
    row under the list at 60 to 66 columns, and below 60 an option rendered as a bare shape
    glyph with its label cut off entirely. Reserving and painting from one list of lines is the
    only way they cannot drift, and it was the same drift twice before.

    A continuation line is indented under its own mark and carries the chip's ground for the
    full column, so a wrapped option stays one rectangle. Folded, it resumed at column zero
    with no shape glyph, which read as a further unmarked option - and a reader counts what is
    ticked by counting the filled shapes.
    """
    room = width - CHIP_CHROME
    text = Text()
    first = True
    for choice, (cursor, shape, style) in zip(choices, marks, strict=False):
        for index, line in enumerate(_wrapped(choice.label, room)):
            if not first:
                text.append("\n")
            first = False
            text.append(cursor if index == 0 else " ", style=f"bold {shade}")
            body = f" {shape} {line} " if index == 0 else f"   {line} "
            # padded by cells, and one cell short of the column: `str.ljust` counts characters,
            # and the shape glyph is ambiguous width, so a terminal set to render such
            # characters wide draws the chip a cell past its box. The one-line path reserves
            # the same cell per chip and says why
            text.append(set_cell_size(body, max(width - 2, 1)), style=style)
    return text


def _stacked_height(choices: Sequence[Choice], width: int) -> int:
    """Lines the stacked form takes at `width` - the same count `_stack` will paint."""
    room = width - CHIP_CHROME
    return sum(len(_wrapped(choice.label, room)) for choice in choices)


class InlineOptions(Static):
    """Every option of one question on one line, the chosen one lit."""

    can_focus = True

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("left", "previous", "Previous option", show=False),
        Binding("right", "next", "Next option", show=False),
        Binding("space", "toggle", "Pick", show=False),
        # up and down are deliberately NOT bound. A stacked list is read as a column, and
        # binding the column's own arrows to it looked right and was a data-loss defect:
        # `_move` commits the value on every step, so holding `down` to walk the form
        # rewrote every stacked answer it passed - twelve of twenty-three at 60 columns,
        # silently, with no way to arrow back to what had been there. `down` belongs to the
        # form. Which keys DO answer the question is said on the row's own help line.
    ]

    DEFAULT_CSS = """
    InlineOptions {
        width: 1fr;
        height: auto;
    }
    """

    class Changed(Message):
        """The user moved to a different option, or toggled one."""

        def __init__(self, value: Any) -> None:
            """Carry the new value, single or list depending on the question."""
            super().__init__()
            self.value = value

    def __init__(
        self,
        choices: Sequence[Choice],
        value: Any,
        *,
        multiple: bool = False,
        **kwargs: Any,
    ) -> None:
        """Render the options, putting the cursor on the one currently in force."""
        super().__init__(**kwargs)
        self._multiple = multiple
        # tracked here rather than read from `has_focus`, which is a reactive Textual has not
        # finished setting when it delivers the Focus event: painting from it drew the row as
        # though it were still blurred, so the cursor mark never appeared on arrival
        self._has_cursor = False
        self._stacked = False
        self._mark_shade = MARK_SHADES[0]
        self.set_options(choices, value)

    def set_options(self, choices: Sequence[Choice], value: Any) -> None:
        """Replace the options and the value, keeping the cursor on the chosen one.

        A label is flattened here, once, rather than defended against at each of the three
        places that measure one. A break inside a label is a break no single-line chip could
        render, and it defeated all three: `divide_line` does not treat it as a break, so the
        stacked height came back one line short; `cell_len` counts it as one cell, so the fit
        test judged the chips to fit a single row; and the paint then put them on two. The
        options after such a label were simply not on the screen.
        """
        self.choices = tuple(
            replace(choice, label=" ".join(choice.label.split())) for choice in choices
        )
        self._value = list(value) if self._multiple and isinstance(value, (list, tuple)) else value
        self._cursor = self._initial_cursor()
        self._paint()

    @property
    def stacked(self) -> bool:
        """Whether the options are drawn one per line, and so read as a column."""
        return self._stacked

    @property
    def value(self) -> Any:
        """The value in force: one option's value, or the list of ticked ones."""
        if self._multiple:
            return [c.value for c in self.choices if c.value in (self._value or [])]
        return self._value

    def action_previous(self) -> None:
        """Move one option left, stopping at the first."""
        self._move(-1)

    def action_next(self) -> None:
        """Move one option right, stopping at the last."""
        self._move(1)

    def action_toggle(self) -> None:
        """Tick the option under the cursor, or cycle a single-choice question forward.

        Space is the key a person tries on a setting they want flipped, so on a two-option
        question it flips it; on a longer one it walks the same way right does, wrapping at
        the end so repeated presses always reach every option.
        """
        if not self.choices:
            return
        if not self._multiple:
            self._cursor = (self._cursor + 1) % len(self.choices)
            self._value = self.choices[self._cursor].value
            self._paint()
            self.post_message(self.Changed(self.value))
            return
        picked = self.choices[self._cursor].value
        current = list(self._value or [])
        if picked in current:
            current.remove(picked)
        else:
            current.append(picked)
        self._value = current
        self._paint()
        self.post_message(self.Changed(self.value))

    def _move(self, step: int) -> None:
        """Walk the cursor, and for a single-choice question take the option it lands on.

        Moving is choosing here: with every option on screen there is nothing a separate
        confirm step would tell the user that the lit option does not already say.
        """
        if not self.choices:
            return
        self._cursor = max(0, min(len(self.choices) - 1, self._cursor + step))
        if not self._multiple:
            self._value = self.choices[self._cursor].value
        self._paint()
        self.post_message(self.Changed(self.value))

    def _initial_cursor(self) -> int:
        """Put the cursor on the option in force, or at the start when none is."""
        chosen = (self._value or [None])[0] if self._multiple else self._value
        for index, choice in enumerate(self.choices):
            if choice.value == chosen:
                return index
        return 0

    def _paint(self) -> None:
        """Draw every option as a chip, on one line where they fit and stacked where they do not.

        Short answers - a yes and a no, a handful of one-word choices - read fastest side by
        side, and stacking them wastes rows the form does not have. Long labels side by side
        run past the edge, and the option that falls off is an alternative the reader never
        learns about, so those go one per line instead.
        """
        chips = [self._chip(index, choice) for index, choice in enumerate(self.choices)]
        self._stacked = not self._fits(chips)
        if not self._stacked:
            text = Text(overflow="fold")
            for index, spans in enumerate(chips):
                if index:
                    text.append(GAP)
                for span, style in spans:
                    text.append(span, style=style)
            self.update(text)
            return
        self.update(_stack(self.choices, self._marks(), self.size.width, self._mark_shade))

    def _marks(self) -> list[tuple[str, str, str]]:
        """Per option: the cursor mark, the shape glyph and the chip's style.

        The one place a chip's colour is decided, for both the one-line and the stacked paint.
        It was decided twice, in the same four-way branch written out in both - which is the
        two-derivations-that-must-agree shape this module was rewritten to be rid of.

        The shape already says which option is chosen, which leaves the ground free to say
        where the cursor is - two facts that hold at once, since the cursor starts on the
        answer every time. Under the cursor the ground inverts: bright with dark ink, in the
        cyan over the answer and in a neutral over an alternative. Nothing is dimmed out of
        legibility: the alternatives are what the reader is deciding against.
        """
        marks = []
        for index, choice in enumerate(self.choices):
            chosen = self._in_force(choice)
            here = index == self._cursor and self._has_cursor
            if here and chosen:
                style = f"bold {CURSOR_PICKED_FG} on {CURSOR_PICKED_BG}"
            elif here:
                style = f"bold {CURSOR_FG} on {CURSOR_BG}"
            elif chosen:
                style = f"bold {PICKED_FG} on {PICKED_BG}"
            else:
                style = f"{OPTION_FG} on {OPTION_BG}"
            marks.append((CURSOR if here else " ", TAKEN if chosen else FREE, style))
        return marks

    def _chip(self, index: int, choice: Choice) -> list[tuple[str, str]]:
        """One option as painted: the cursor mark, then the chip with its shape and ground.

        The mark is a separate span so it can sit on the row's own dark ground rather than on
        the chip: a caret inside the chip has only the chip to contrast against, and the
        brightest colour tried there managed 2.91:1.
        """
        cursor, shape, style = self._marks()[index]
        mark = (cursor, f"bold {self._mark_shade}") if cursor == CURSOR else (" ", "")
        return [mark, (f" {shape} {choice.label} ", style)]

    def get_content_height(self, container: Size, viewport: Size, width: int) -> int:
        """How many lines the options need at `width`, answered before anything is painted.

        This is the hook the whole stacking decision has to hang off. Textual asks for a
        height during layout, and the height it was given came from whatever had last been
        painted - which, the first time round, was painted before the widget had a width, so
        every row claimed one line. A question whose options needed four then had three of
        them cut off, and on the reference template at 100 columns five of twenty-three showed
        an incomplete list. `Python version` showed exactly one option, and it was not the one
        in force: the row read as a question whose only answer was unticked.

        Repainting on resize does not fix it. The content changes and the allocated height
        does not, so the row grew into its stack only when something else forced a layout -
        the cursor arriving and leaving - and the form visibly settled as it was read.
        """
        chips = [self._chip(index, choice) for index, choice in enumerate(self.choices)]
        if self._fits_in(chips, width):
            return 1
        return _stacked_height(self.choices, width)

    def _fits(self, chips: list[list[tuple[str, str]]]) -> bool:
        """Whether every chip fits on one line at the width the row actually has.

        A margin is kept for the option marks. `\u25cf` and `\u25cb` are ambiguous width, and no
        width-neutral pair reads as filled-against-empty at this size, so a terminal set to
        render ambiguous characters wide draws each chip a cell wider than `cell_len` counts.
        Without the margin the row is judged to fit when it does not and the last option is
        pushed off the edge - which is the outcome the stacking exists to prevent.

        Before the first layout there is no width to measure against, and the answer here is
        one line rather than a guess. A guess that came out stacked cost four blank lines
        under a five-option question: the row was laid out at the height the stack needed,
        the real width arrived, the row repainted itself on one line - and the lines it had
        vacated stayed on the screen, because only the widget's own region was repainted.
        They cleared when the cursor reached the row and something redrew that patch, which
        is a form that visibly settles while it is being read. Starting on one line cannot
        do that: a row that turns out to need the stack grows into it, and growing pushes
        the rows below down, where they repaint at their new place.
        """
        return self._fits_in(chips, self.size.width)

    def _fits_in(self, chips: list[list[tuple[str, str]]], width: int) -> bool:
        """The same question against a width supplied rather than measured."""
        if not width:
            return True
        room = sum(cell_len(span) for spans in chips for span, _ in spans)
        # one cell per chip for the mark inside its label, which `cell_len` under-counts on a
        # terminal set to render ambiguous-width characters wide
        return room + len(chips) - 1 + len(chips) <= width

    def on_resize(self) -> None:
        """Re-decide between one line and a stack now that the real width is known."""
        self._paint()

    def _in_force(self, choice: Choice) -> bool:
        """Whether this option is the answer, or among them."""
        if self._multiple:
            return choice.value in (self._value or [])
        return choice.value == self._value

    def set_mark_shade(self, shade: str) -> None:
        """Take the next colour of the row's breath, so mark and bar are never out of phase.

        The row owns the beat rather than the control keeping one of its own: two things
        breathing on separate timers drift apart, and the pair reads as two signals rather
        than one row being answered.
        """
        if shade == self._mark_shade:
            return
        self._mark_shade = shade
        if self._has_cursor:
            self._paint()

    def on_focus(self) -> None:
        """Repaint so the cursor mark appears."""
        self._has_cursor = True
        self._paint()

    def on_blur(self) -> None:
        """Repaint so the cursor mark goes away with the focus."""
        self._has_cursor = False
        self._paint()
