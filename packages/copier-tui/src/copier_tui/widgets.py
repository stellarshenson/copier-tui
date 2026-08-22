"""Kind to widget mapping and the field row.

Holds no semantics: label, help, value, choices, errors and default-ness all come from
copier_ui state.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Select, SelectionList, Static, Switch, TextArea

from copier_tui import __version__
from copier_tui.theme import AMBER, CYAN_BRIGHT, ROSE, TEXT_MUTED, TEXT_SUBTLE
from copier_ui import Choice, FieldState, Kind, Question

_INPUT_TYPE = {Kind.INTEGER: "integer", Kind.FLOAT: "number"}


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
    """A field's value on one line, with secrets masked."""
    if field.secret:
        return "***"
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
    """Build the input control for a question, prefilled with the field's current value."""
    widget = TextArea if question.multiline else WIDGET_BY_KIND[question.kind]
    control_id = f"ctl-{question.id}"
    if widget is ChoiceSelectionList:
        return ChoiceSelectionList(field.choices, field.value, id=control_id)
    if widget is ChoiceSelect:
        return ChoiceSelect(field.choices, field.value, id=control_id)
    if widget is Switch:
        return Switch(value=bool(field.value), id=control_id)
    if widget is TextArea:
        return TextArea(_as_text(field.value), soft_wrap=True, id=control_id)
    return Input(
        value=_as_text(field.value),
        placeholder=question.placeholder,
        password=question.secret,
        type=_INPUT_TYPE.get(question.kind, "text"),
        select_on_focus=False,
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
    """One-row header: app name left, version right."""

    def __init__(self, context: str = "") -> None:
        """Build the header, optionally folding extra context into the title cell."""
        super().__init__(id="app-header")
        self._context = context

    def compose(self) -> ComposeResult:
        """The title cell and the version cell."""
        title = f"copier-tui · {self._context}" if self._context else "copier-tui"
        yield Static(title, id="hdr-title")
        yield Static(f"v{__version__}", id="hdr-version")


class FieldRow(Vertical):
    """Label, help, control, default marker and inline error for one question."""

    DEFAULT_CSS = f"""
    FieldRow {{
        height: auto;
        padding: 0 1 1 1;
    }}
    .field-help {{
        color: {TEXT_MUTED};
    }}
    .field-error {{
        color: {ROSE};
        display: none;
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
        self._label = Static(_label_text(question, field), classes="field-label")
        self._help = Static(Text(question.help), classes="field-help")
        self._control = control_for(question, field)
        self._error = Static(classes="field-error", id=f"err-{question.id}")
        self._last_value: Any = None

    def compose(self) -> ComposeResult:
        """Label, help when there is any, the control, then the error line."""
        yield self._label
        if self.question.help:
            yield self._help
        yield self._control
        yield self._error

    def on_mount(self) -> None:
        """Apply the initial state to the control and the error line."""
        self.update(self._field)

    def update(self, field: FieldState) -> None:
        """Apply new state: value, choices, default marker, errors."""
        self._field = field
        self._label.update(_label_text(self.question, field))
        self._control.disabled = not field.enabled
        if not self._control.has_focus:
            self._write_value(field)
        self._last_value = self.value
        self._error.update(Text("\n".join(field.errors)))
        self._error.display = bool(field.errors)

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
        """A choice picked."""
        event.stop()
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
    """The question label, marked when the value is still the computed default."""
    text = Text(question.label, style=f"bold {CYAN_BRIGHT}")
    if field.is_default:
        text.append("  default", style=TEXT_SUBTLE)
    if not field.enabled:
        text.append("  unavailable", style=AMBER)
    return text
