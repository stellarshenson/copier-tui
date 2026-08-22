"""Kind to widget mapping and the field row.

Holds no semantics: label, help, value, choices, errors and default-ness all come from
copier_ui state. Every field is one row - label gutter, control, one status glyph - so a
long survey stays a short screen; the focused field's help goes to the screen's hint line.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Select, SelectionList, Static, Switch, TextArea

from copier_tui import __version__
from copier_tui.theme import AMBER, CYAN_BRIGHT, LABEL_WIDTH, ROSE, TEXT_SUBTLE
from copier_ui import Choice, FieldState, Kind, Question

_INPUT_TYPE = {Kind.INTEGER: "integer", Kind.FLOAT: "number"}

NO_CHOICE = "no answer yet"
"""Shown by a choice control whose answer is not among its current choices.

A recompute can narrow the choices out from under an answer, and this is the honest render
of that: the field is blank, and picking the blank back is a no-op rather than an answer.
"""


def _as_text(value: Any) -> str:
    """Render a field value as editable text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, indent=2, default=str)
    return str(value)


def display_value(field: FieldState) -> str:
    """A field's value on one line: secrets masked, an unset one left blank."""
    if field.secret:
        return "***" if field.value else ""
    for choice in field.choices:
        if choice.value == field.value:
            return choice.label
    return " ".join(_as_text(field.value).split())


def _index_of(value: Any, values: Sequence[Any]) -> int | None:
    """The position of a choice value, or None when it is not among the choices."""
    for index, candidate in enumerate(values):
        if candidate == value:
            return index
    return None


class ChoiceSelect(Select[int]):
    """One-of-many choice. The option value is the choice index, so any value works."""

    def __init__(self, choices: Sequence[Choice], value: Any, **kwargs: Any) -> None:
        """Build the select over the given choices, showing the current value."""
        self.choice_values: tuple[Any, ...] = tuple(choice.value for choice in choices)
        index = _index_of(value, self.choice_values)
        super().__init__(
            [(choice.label, position) for position, choice in enumerate(choices)],
            value=Select.NULL if index is None else index,
            prompt=NO_CHOICE,
            compact=True,
            **kwargs,
        )


class ChoiceSelectionList(SelectionList[int]):
    """Many-of-many choice. The option value is the choice index, so any value works."""

    def __init__(self, choices: Sequence[Choice], value: Any, **kwargs: Any) -> None:
        """Build the selection list over the given choices, showing the current values."""
        self.choice_values: tuple[Any, ...] = tuple(choice.value for choice in choices)
        selected = value if isinstance(value, (list, tuple)) else ()
        super().__init__(
            *[
                (choice.label, position, choice.value in selected)
                for position, choice in enumerate(choices)
            ],
            compact=True,
            **kwargs,
        )


WIDGET_BY_KIND: Mapping[Kind, type[Widget]] = {
    Kind.STRING: Input,
    Kind.PATH: Input,
    Kind.SECRET: Input,
    Kind.INTEGER: Input,
    Kind.FLOAT: Input,
    Kind.BOOL: Switch,
    Kind.CHOICE: ChoiceSelect,
    Kind.MULTISELECT: ChoiceSelectionList,
    Kind.STRUCTURED: TextArea,
}
"""string/path/integer/float -> Input, secret -> Input(password), bool -> Switch,
choice -> Select, multiselect -> SelectionList, structured -> TextArea."""


def control_for(question: Question, field: FieldState) -> Widget:
    """Build the input control for a question, prefilled with the field's current value.

    A secret question always gets the masked Input, whatever its kind: no choice list or
    editor may put the value on screen in the clear.
    """
    if question.secret:
        widget: type[Widget] = Input
    else:
        widget = TextArea if question.multiline else WIDGET_BY_KIND[question.kind]
    control_id = f"ctl-{question.id}"
    if widget is ChoiceSelectionList:
        return ChoiceSelectionList(field.choices, field.value, id=control_id)
    if widget is ChoiceSelect:
        return ChoiceSelect(field.choices, field.value, id=control_id)
    if widget is Switch:
        return Switch(value=bool(field.value), id=control_id)
    if widget is TextArea:
        return TextArea(_as_text(field.value), soft_wrap=True, compact=True, id=control_id)
    return Input(
        value=_as_text(field.value),
        placeholder=question.placeholder,
        password=question.secret,
        type=_INPUT_TYPE.get(question.kind, "text"),
        select_on_focus=False,
        compact=True,
        id=control_id,
    )


def read_control(question: Question, control: Widget) -> Any:
    """Read the control's current value."""
    if isinstance(control, ChoiceSelect):
        if control.value is Select.NULL:
            return None
        return control.choice_values[control.value]
    if isinstance(control, ChoiceSelectionList):
        return [control.choice_values[index] for index in sorted(control.selected)]
    if isinstance(control, Switch):
        return control.value
    if isinstance(control, TextArea):
        return control.text
    return control.value


class HeaderBar(Horizontal):
    """One-row header: app name and context left, version right."""

    def __init__(self, context: str = "") -> None:
        """Build the header, optionally folding extra context into the title cell."""
        super().__init__(id="app-header")
        self._label_context = context

    def compose(self) -> ComposeResult:
        """The title cell and the version cell."""
        yield Static(self._title(), id="hdr-title")
        yield Static(f"v{__version__}", id="hdr-version")

    def set_context(self, context: str) -> None:
        """Rewrite the context: the survey keeps the field position here as focus moves."""
        self._label_context = context
        self.query_one("#hdr-title", Static).update(self._title())

    def _title(self) -> str:
        """The title cell's text: the app name, and the screen's context after it."""
        return f"copier-tui · {self._label_context}" if self._label_context else "copier-tui"


class FieldRow(Horizontal):
    """One question on one row: label gutter, control, status glyph."""

    DEFAULT_CSS = f"""
    FieldRow {{
        height: auto;
        max-height: 6;
    }}
    FieldRow:focus-within > .field-label {{
        text-style: bold;
    }}
    FieldRow > .field-label {{
        width: 45%;
        max-width: {LABEL_WIDTH};
        height: 1;
        padding: 0 1 0 0;
        text-align: right;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }}
    FieldRow > .field-flag {{
        width: 2;
        height: 1;
        text-align: center;
    }}
    FieldRow > Input, FieldRow > Select, FieldRow > SelectionList, FieldRow > TextArea {{
        width: 1fr;
    }}
    FieldRow > SelectionList, FieldRow > TextArea {{
        height: auto;
        max-height: 6;
    }}
    FieldRow > Switch {{
        width: 4;
    }}
    """

    class Changed(Message):
        """The user changed a field's value."""

        def __init__(self, field_id: str, value: Any) -> None:
            """Carry the field id and its new value."""
            super().__init__()
            self.field_id = field_id
            self.value = value

        def __repr__(self) -> str:
            """Name the field only - a secret value must never reach a log line."""
            return f"FieldRow.Changed(field_id={self.field_id!r})"

    def __init__(self, question: Question, field: FieldState) -> None:
        """Build the row for a question and its current state."""
        super().__init__(id=f"row-{question.id}")
        self.question = question
        self._field = field
        self._label = Static(classes="field-label")
        self._control = control_for(question, field)
        self._flag = Static(classes="field-flag", id=f"flag-{question.id}")
        self._last_value: Any = None

    def compose(self) -> ComposeResult:
        """The label gutter, the control, then the one-cell status glyph."""
        yield self._label
        yield self._control
        yield self._flag

    def on_mount(self) -> None:
        """Show the label and the glyph; the control already holds its constructed value."""
        self._chrome(self._field)
        self._last_value = self.value

    @property
    def field(self) -> FieldState:
        """The state this row currently shows, for the screen's hint line."""
        return self._field

    def update(self, field: FieldState) -> None:
        """Apply new state: value, choices, default marker, errors.

        A control that has not mounted yet is left alone. It was built from this same
        state, so there is nothing to write - and writing anyway breaks Select, which
        stores its value privately in the constructor and only assigns the reactive on
        mount. An assignment that lands first leaves the reactive already equal to the
        target, so the watcher that paints the label never fires and the control shows
        its prompt over a value it is holding.
        """
        self._chrome(field)
        if self._control.is_mounted and not self._control.has_focus:
            self._write_value(field)
        self._last_value = self.value

    def _chrome(self, field: FieldState) -> None:
        """Everything about a row that is not the control's value."""
        self._field = field
        self._label.update(_label_text(self.question, field))
        self._flag.update(_flag_text(field))
        self._control.disabled = not field.enabled

    def _write_value(self, field: FieldState) -> None:
        """Push the state's value into the control."""
        control = self._control
        if isinstance(control, ChoiceSelect):
            values = tuple(choice.value for choice in field.choices)
            if values != control.choice_values:
                control.choice_values = values
                control.set_options(
                    [(choice.label, position) for position, choice in enumerate(field.choices)]
                )
            index = _index_of(field.value, control.choice_values)
            control.value = Select.NULL if index is None else index
        elif isinstance(control, ChoiceSelectionList):
            values = tuple(choice.value for choice in field.choices)
            if values != control.choice_values:
                control.choice_values = values
                control.clear_options()
                control.add_options(
                    [(choice.label, position) for position, choice in enumerate(field.choices)]
                )
            selected = field.value if isinstance(field.value, (list, tuple)) else ()
            for position, choice in enumerate(field.choices):
                if choice.value in selected:
                    control.select(position)
                else:
                    control.deselect(position)
        elif isinstance(control, Switch):
            control.value = bool(field.value)
        elif isinstance(control, TextArea):
            control.text = _as_text(field.value)
        else:
            control.value = _as_text(field.value)

    @property
    def value(self) -> Any:
        """The control's current value."""
        return read_control(self.question, self._control)

    def _emit(self) -> None:
        """Announce a real change - a value we wrote ourselves is not one."""
        value = self.value
        if value == self._last_value:
            return
        self._last_value = value
        self.post_message(self.Changed(self.question.id, value))

    def on_input_changed(self, event: Input.Changed) -> None:
        """A keystroke in a text, path, secret or numeric input."""
        event.stop()
        self._emit()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """A boolean toggled."""
        event.stop()
        self._emit()

    def on_select_changed(self, event: Select.Changed) -> None:
        """A choice picked. The blank is never an answer.

        Rebuilding the options blanks the select for a beat - our own write, not a choice
        of None. Textual also offers the prompt as a selectable row, so the user can pick
        the blank; that is not an answer either, and returning bare would leave the control
        showing `no answer yet` over a value the state still holds and still renders.
        """
        event.stop()
        if event.value is Select.NULL:
            self._write_value(self._field)
            return
        self._emit()

    def on_selection_list_selected_changed(self, event: SelectionList.SelectedChanged) -> None:
        """A multiselect option toggled."""
        event.stop()
        self._emit()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """An edit in a structured or multiline editor."""
        event.stop()
        self._emit()


def _label_text(question: Question, field: FieldState) -> Text:
    """The question caption, dimmed while the value is still the computed default.

    A caption longer than the gutter is clipped by the gutter itself, so the width can be
    a share of the terminal rather than a constant; the focused row's caption is shown in
    full on the hint line, which is what keeps a long question readable on one line.
    """
    style = TEXT_SUBTLE if field.is_default else f"bold {CYAN_BRIGHT}"
    return Text(question.label, style=style, no_wrap=True, overflow="ellipsis")


def _flag_text(field: FieldState) -> Text:
    """One glyph for the row's standing: a problem, an unavailable field, or a default."""
    if field.errors:
        return Text("!", style=f"bold {ROSE}")
    if not field.enabled:
        return Text("-", style=AMBER)
    if field.is_default:
        return Text("·", style=TEXT_SUBTLE)
    return Text(" ")
