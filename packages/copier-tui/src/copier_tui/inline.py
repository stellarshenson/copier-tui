"""Options rendered in place, on one line, instead of behind a menu.

A dropdown answers "what is chosen" and hides "what else was possible", and while it is open
it paints over the questions around it, which are exactly what the user is comparing against.
This renders every option of a question on a single line: the one in force is lit, the ones
passed over stay legible beside it, and left and right move between them without opening
anything.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from rich.cells import cell_len
from rich.text import Text
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Static

from copier_tui.theme import (
    CURSOR_BG,
    CURSOR_FG,
    CURSOR_PICKED_BG,
    CURSOR_PICKED_FG,
    CYAN_BRIGHT,
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

CURSOR = "\u25b8"
"""Marks the option the cursor is on, and only while the row has the focus.

The ground alone could not carry this. When the cursor sits on the answer - which is where it
starts, every time - a ground says "chosen" and has nothing left to say "and you are here", so
the two facts collapsed into one and the row stopped showing which option was about to move."""

INLINE_BUDGET = 42
"""Columns assumed for the option row before it has been laid out and can measure itself."""


class InlineOptions(Static):
    """Every option of one question on one line, the chosen one lit."""

    can_focus = True

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("left", "previous", "Previous option", show=False),
        Binding("right", "next", "Next option", show=False),
        Binding("space", "toggle", "Pick", show=False),
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
        self.set_options(choices, value)

    def set_options(self, choices: Sequence[Choice], value: Any) -> None:
        """Replace the options and the value, keeping the cursor on the chosen one."""
        self.choices = tuple(choices)
        self._value = list(value) if self._multiple and isinstance(value, (list, tuple)) else value
        self._cursor = self._initial_cursor()
        self._paint()

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
        separator = GAP if self._fits(chips) else "\n"
        text = Text(overflow="fold")
        for index, spans in enumerate(chips):
            if index:
                text.append(separator)
            for span, style in spans:
                text.append(span, style=style)
        self.update(text)

    def _chip(self, index: int, choice: Choice) -> list[tuple[str, str]]:
        """One option as painted: the cursor mark, then the chip with its shape and ground.

        The mark is a separate span so it can sit on the row's own dark ground rather than on
        the chip: a caret inside the chip has only the chip to contrast against, and the
        brightest colour tried there managed 2.91:1.
        """
        chosen = self._in_force(choice)
        here = index == self._cursor and self._has_cursor
        label = f" {TAKEN if chosen else FREE} {choice.label} "
        # the shape already says which option is chosen, which leaves the ground free to say
        # where the cursor is - two facts that hold at once, since the cursor starts on the
        # answer every time. Under the cursor the ground inverts: bright with dark ink, in
        # the cyan over the answer and in a neutral over an alternative
        if here and chosen:
            style = f"bold {CURSOR_PICKED_FG} on {CURSOR_PICKED_BG}"
        elif here:
            style = f"bold {CURSOR_FG} on {CURSOR_BG}"
        elif chosen:
            style = f"bold {PICKED_FG} on {PICKED_BG}"
        else:
            # set back a step, never dimmed out of legibility: these are the alternatives the
            # reader is deciding against, so they have to stay readable to be worth showing
            style = f"{OPTION_FG} on {OPTION_BG}"
        mark = (CURSOR, f"bold {CYAN_BRIGHT}") if here else (" ", "")
        return [mark, (label, style)]

    def _fits(self, chips: list[list[tuple[str, str]]]) -> bool:
        """Whether every chip fits on one line at the width the row actually has."""
        width = self.size.width or INLINE_BUDGET
        room = sum(cell_len(span) for spans in chips for span, _ in spans)
        return room + len(chips) - 1 <= width

    def on_resize(self) -> None:
        """Re-decide between one line and a stack now that the real width is known."""
        self._paint()

    def _in_force(self, choice: Choice) -> bool:
        """Whether this option is the answer, or among them."""
        if self._multiple:
            return choice.value in (self._value or [])
        return choice.value == self._value

    def on_focus(self) -> None:
        """Repaint so the cursor mark appears."""
        self._has_cursor = True
        self._paint()

    def on_blur(self) -> None:
        """Repaint so the cursor mark goes away with the focus."""
        self._has_cursor = False
        self._paint()
