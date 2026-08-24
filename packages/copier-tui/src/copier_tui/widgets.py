"""Kind to widget mapping and the field row.

Holds no semantics: label, help, value, choices, errors and default-ness all come from
copier_ui state. A question is one row - caption, then the control - and the focused row
grows by the lines its help needs. A choice shows every option on its own row rather than
behind a menu, so what was passed over is legible beside what was taken.
"""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Input, Static, TextArea

from copier_tui import __version__
from copier_tui.inline import BOOL_CHOICES, InlineOptions
from copier_tui.theme import (
    AMBER,
    CYAN,
    CYAN_BRIGHT,
    HELP_LINES,
    LABEL_LINES,
    LABEL_WIDTH,
    PULSE_CYCLE,
    PULSE_INTERVAL,
    PULSE_SHADES,
    ROSE,
    ROW_ALT_BG,
    ROW_ALT_FOCUS_BG,
    ROW_BG,
    ROW_FOCUS_BG,
    TEXT,
    TEXT_MUTED,
    TEXT_SUBTLE,
    VALUE_LINES,
)
from copier_ui import FieldState, Kind, Question

_INPUT_TYPE = {Kind.INTEGER: "integer", Kind.FLOAT: "number"}

_WRAPPED_KINDS = (Kind.STRING, Kind.PATH)
"""Free-text kinds whose answer is often longer than the column it is written in.

A single-line input scrolls the overflow out of sight, so the one field where a person
writes a sentence is the one field that never shows the sentence. These wrap instead."""


class WrapInput(TextArea):
    """A one-line answer that wraps onto a second line instead of scrolling out of sight.

    It is a TextArea because Textual's Input cannot wrap, but the question behind it is not
    multiline: enter is left to the screen so it still confirms the survey, and the widget
    reports that by not owning the key.
    """

    owns_enter = False

    def __init__(self, text: str, **kwargs: Any) -> None:
        """Build the wrapping editor over the current value."""
        super().__init__(text, soft_wrap=True, compact=True, **kwargs)

    def on_mount(self) -> None:
        """Put the cursor after the answer, where a text field's cursor belongs.

        An editor starts at the top left, which for a prefilled one-line answer means the
        first thing typed lands in front of the default and the first backspace does
        nothing at all.
        """
        self.move_cursor(self.document.end)

    async def _on_key(self, event: events.Key) -> None:
        """Let enter reach the screen; a single-line answer has no line to break."""
        if event.key == "enter":
            return
        await super()._on_key(event)


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


WIDGET_BY_KIND: Mapping[Kind, type[Widget]] = {
    Kind.STRING: WrapInput,
    Kind.PATH: WrapInput,
    Kind.SECRET: Input,
    Kind.INTEGER: Input,
    Kind.FLOAT: Input,
    Kind.BOOL: InlineOptions,
    Kind.CHOICE: InlineOptions,
    Kind.MULTISELECT: InlineOptions,
    Kind.STRUCTURED: TextArea,
}
"""string/path -> wrapping editor, integer/float -> Input, secret -> Input(password),
bool/choice/multiselect -> options on the row, structured -> TextArea."""


def control_for(question: Question, field: FieldState) -> Widget:
    """Build the input control for a question, prefilled with the field's current value.

    A secret question always gets the masked Input, whatever its kind: no option row or
    editor may put the value on screen in the clear.
    """
    control_id = f"ctl-{question.id}"
    if question.secret:
        widget: type[Widget] = Input
    else:
        widget = TextArea if question.multiline else WIDGET_BY_KIND[question.kind]
    if widget is InlineOptions:
        choices = BOOL_CHOICES if question.kind is Kind.BOOL else field.choices
        return InlineOptions(
            choices,
            field.value,
            multiple=question.kind is Kind.MULTISELECT,
            id=control_id,
        )
    if widget is WrapInput:
        return WrapInput(_as_text(field.value), id=control_id)
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
    if isinstance(control, InlineOptions):
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


_PULSE_CSS = "\n    ".join(
    f"FieldRow.pulse-{index}:focus-within {{ border-left: thick {shade}; }}"
    for index, shade in enumerate(PULSE_SHADES)
)
"""One rule per shade, keyed by a class the focused row cycles through."""


class FieldRow(Vertical):
    """One question: a caption-and-control line, and the help the focused row shows."""

    DEFAULT_CSS = f"""
    FieldRow {{
        height: auto;
        background: {ROW_BG};
        border-left: thick {ROW_BG};
    }}
    FieldRow.row-alt {{
        background: {ROW_ALT_BG};
        border-left: thick {ROW_ALT_BG};
    }}
    FieldRow:focus-within {{
        background: {ROW_FOCUS_BG};
        border-left: thick {CYAN};
        margin: 1 0;
    }}
    FieldRow.row-alt:focus-within {{
        background: {ROW_ALT_FOCUS_BG};
    }}
    {_PULSE_CSS}
    FieldRow > .field-head {{
        height: auto;
    }}
    FieldRow .field-label {{
        width: {LABEL_WIDTH};
        height: auto;
        max-height: {LABEL_LINES};
        padding: 0 2 0 1;
        text-align: left;
        text-wrap: wrap;
        color: {TEXT};
    }}
    FieldRow:focus-within .field-label {{
        color: {CYAN_BRIGHT};
        text-style: bold;
    }}
    FieldRow.row-off .field-label {{
        color: {TEXT_SUBTLE};
    }}
    FieldRow .field-flag {{
        width: 2;
        height: 1;
        text-align: center;
    }}
    FieldRow > .field-head > Input,
    FieldRow > .field-head > InlineOptions,
    FieldRow > .field-head > TextArea {{
        width: 1fr;
    }}
    FieldRow > .field-head > InlineOptions:disabled {{
        color: {TEXT_SUBTLE};
    }}
    FieldRow > .field-head > TextArea {{
        height: auto;
        max-height: 6;
    }}
    FieldRow > .field-head > WrapInput {{
        max-height: {VALUE_LINES};
    }}
    FieldRow > .field-help {{
        display: none;
        height: auto;
        max-height: {HELP_LINES};
        padding: 0 2 0 {LABEL_WIDTH};
        color: {TEXT_MUTED};
    }}
    FieldRow:focus-within > .field-help {{
        display: block;
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
        self._help = Static(classes="field-help", id=f"help-{question.id}")
        self._last_value: Any = None
        self._pulse: Timer | None = None
        self._beat = 0

    def compose(self) -> ComposeResult:
        """The caption line with its control, then the help the focused row reveals."""
        with Horizontal(classes="field-head"):
            yield self._label
            yield self._control
            yield self._flag
        yield self._help

    def on_mount(self) -> None:
        """Show the caption, the help and the glyph; the control holds its own value."""
        self._chrome(self._field)
        self._last_value = self.value

    def on_descendant_focus(self) -> None:
        """Start the bar breathing when the cursor arrives in this question."""
        self._beat = 0
        self._breathe()
        if self._pulse is None:
            self._pulse = self.set_interval(PULSE_INTERVAL, self._breathe)

    def on_descendant_blur(self) -> None:
        """Stop it and drop every shade class, so the stylesheet owns the bar again."""
        if self._pulse is not None:
            self._pulse.stop()
            self._pulse = None
        for index in range(len(PULSE_SHADES)):
            self.remove_class(f"pulse-{index}")

    def _breathe(self) -> None:
        """Move the bar one step round the cycle."""
        shade = PULSE_CYCLE[self._beat % len(PULSE_CYCLE)]
        self._beat += 1
        for index in range(len(PULSE_SHADES)):
            self.set_class(index == shade, f"pulse-{index}")

    @property
    def field(self) -> FieldState:
        """The state this row currently shows, for the screen's message line."""
        return self._field

    def update(self, field: FieldState) -> None:
        """Apply new state: value, choices, default marker, errors.

        A control that has not mounted yet is left alone. It was built from this same state,
        so there is nothing to write, and a control that has the focus is left alone because
        the user is the authority on its value until they leave it.
        """
        self._chrome(field)
        if self._control.is_mounted and not self._control.has_focus:
            self._write_value(field)
        self._last_value = self.value

    def _chrome(self, field: FieldState) -> None:
        """Everything about a row that is not the control's value."""
        self._field = field
        self._label.update(_label_text(self.question))
        self._flag.update(_flag_text(field))
        help = _help_text(self.question, field)
        self._help.update(help)
        # an empty Static still occupies its row, and a blank line under every question
        # that declares no help is the wasted space the whole layout is trying to recover
        self._help.display = bool(help.plain)
        self._control.disabled = not field.enabled
        # the caption greys with the control: a row this answer set rules out must not look
        # like a row that is merely unfocused, which is what a live caption over a dead
        # control looked like
        self.set_class(not field.enabled, "row-off")

    def _write_value(self, field: FieldState) -> None:
        """Push the state's value into the control."""
        control = self._control
        if isinstance(control, InlineOptions):
            choices = BOOL_CHOICES if self.question.kind is Kind.BOOL else field.choices
            control.set_options(choices, field.value)
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

    def on_inline_options_changed(self, event: InlineOptions.Changed) -> None:
        """An option taken, or a multiselect option ticked."""
        event.stop()
        self._emit()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """An edit in a structured or multiline editor."""
        event.stop()
        self._emit()


def _label_text(question: Question) -> Text:
    """The question caption, wrapped rather than cut, and carrying no colour of its own.

    Hue on a caption used to mean "you have changed this", which read as a state of the
    question rather than of its answer - a blue line looks like a heading or something the
    form will not let you touch, and it sat on rows the cursor then walked straight into.
    The row's band, its field grounds and its focus bar say where the cursor is and what can
    be edited; what the answer happens to be is the answer's own business, so the stylesheet
    colours this by focus and nothing else.
    """
    return Text(question.label, overflow="fold")


def _help_text(question: Question, field: FieldState) -> Text:
    """What the focused row says under itself: the problem, else the question's own help.

    Help that only repeats the caption is dropped. copier falls back to the help string for
    the prompt caption, so a template whose question carries help and nothing else ends up
    with the same sentence twice, one line above the other, saying nothing the second time.
    """
    if field.errors:
        return Text(field.errors[0], style=ROSE, overflow="fold")
    help = "" if question.help == question.label else question.help
    if not display_value(field) and question.placeholder:
        # a placeholder written into the value column reads as an answer nobody gave; said
        # here it is plainly guidance, and the field stays visibly empty until it is answered
        hint = f"for example: {question.placeholder}"
        help = f"{help}  -  {hint}" if help else hint
    return Text(help, style=TEXT_MUTED, overflow="fold")


def _flag_text(field: FieldState) -> Text:
    """One glyph for the row's standing: a problem, or a field this answer set rules out."""
    if field.errors:
        return Text("!", style=f"bold {ROSE}")
    if not field.enabled:
        return Text("-", style=AMBER)
    return Text(" ")
