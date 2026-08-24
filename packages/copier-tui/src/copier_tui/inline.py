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

from rich.text import Text
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Static

from copier_tui.theme import CURSOR_BG, CURSOR_FG, OPTION_BG, OPTION_FG, PICKED_BG, PICKED_FG
from copier_ui import Choice

BOOL_CHOICES = (Choice(label="No", value=False), Choice(label="Yes", value=True))
"""A boolean is a two-option question, and reads better as one than as a toggle whose
current state has to be inferred from which side a knob sits on."""

GAP = " "
"""One space between chips. Each label already carries a space of its own padding on both
sides, so the gap the eye sees is the same three columns as before the chips existed."""


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
        max-height: 2;
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
        """Draw the options: lit for in force, plain for passed over, marked for the cursor.

        The line folds onto a second row rather than being cut. An option list that does not
        fit is the one case where hiding an alternative is unavoidable, and a second row is
        cheaper than a reader who never learns the option was there.
        """
        text = Text(overflow="fold")
        for index, choice in enumerate(self.choices):
            if index:
                text.append(GAP)
            if self._in_force(choice):
                # the answer, on a filled chip - the one state that changes hue, so being
                # chosen never has to be inferred from which neutral is brighter. A ticked
                # multiselect option is chosen in exactly the same sense, and looks it
                style = f"bold {PICKED_FG} on {PICKED_BG}"
            elif index == self._cursor:
                style = f"{CURSOR_FG} on {CURSOR_BG}"
            else:
                # every option gets a ground, not only the answer: a bare label among chips
                # reads as prose, and the question's own caption then reads as one more
                # option of its own answer. Set back a step, never dimmed out of legibility
                style = f"{OPTION_FG} on {OPTION_BG}"
            if index == self._cursor and self.has_focus:
                # chosen and under the cursor are two different facts and can hold at once,
                # so the cursor is an underline rather than a ground that would hide the first
                style = f"{style} underline"
            text.append(f" {choice.label} ", style=style)
        self.update(text)

    def _in_force(self, choice: Choice) -> bool:
        """Whether this option is the answer, or among them."""
        if self._multiple:
            return choice.value in (self._value or [])
        return choice.value == self._value

    def on_focus(self) -> None:
        """Repaint so the cursor mark appears."""
        self._paint()

    def on_blur(self) -> None:
        """Repaint so the cursor mark goes away with the focus."""
        self._paint()
