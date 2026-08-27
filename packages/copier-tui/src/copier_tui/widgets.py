"""Kind to widget mapping and the field row.

Holds no semantics: label, help, value, choices, errors and default-ness all come from
copier_ui state. A question is one row - caption, then the control - and the focused row
grows by the lines its help needs. A choice shows every option on its own row rather than
behind a menu, so what was passed over is legible beside what was taken.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
import json
from textwrap import wrap
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
from copier_tui.paths import fit_name
from copier_tui.theme import (
    AMBER,
    CYAN,
    CYAN_BRIGHT,
    ERROR_FG,
    HELP_LINES,
    LABEL_LINES,
    LABEL_WIDTH,
    MARK_SHADES,
    PULSE_CYCLE,
    PULSE_INTERVAL,
    PULSE_SHADES,
    ROW_ALT_BG,
    ROW_ALT_COND_BG,
    ROW_BG,
    ROW_COND_BG,
    ROW_COND_FOCUS_BG,
    ROW_FOCUS_BG,
    TEXT,
    TEXT_MUTED,
    TEXT_SUBTLE,
    VALUE_LINES,
)
from copier_ui import FieldState, Kind, Question

BRANCH_MORE = "\u251c\u2500 "
BRANCH_LAST = "\u2514\u2500 "
RAIL = "\u2502"
_BRANCH_TAIL = {BRANCH_MORE: f"{RAIL}  ", BRANCH_LAST: "   "}
"""The connectors a conditional question prints before its caption, and what carries on down
the lines its caption wraps onto.

A question another answer decides whether to ask is drawn as that answer's child. Where
several children of one answer sit together, all but the last take the through connector: a
row claiming to be the last child of a run it is in the middle of reads as two runs.

The tail is why the caption is wrapped here rather than left to Rich. A caption long enough
to wrap ran its second line back under the connector, which put prose where the tree is and
broke the column the connectors are read down."""

HEADER_FIXED = 8
"""Columns the header spends on things that are not the title: 3 for the separator before the
path, 1 for the `v`, 2 for `#hdr-version`'s padding and 2 for `#hdr-title`'s - every one of
them set in `theme.py`, so this is the number to revisit if that padding changes."""

HEADER_PATH_FLOOR = 12
"""The least the path is ever cropped to. Below about 45 columns the stylesheet's own ellipsis
takes over, which is under MIN_WIDTH, where the resize prompt is already up."""

_CAPTION_WIDTH = LABEL_WIDTH - 3
"""Columns the caption has when the gutter is at its cap: the gutter less its padding.

Only the starting value. The gutter is a share of the row now, so a caption wrapped to this
and then placed in a narrower box wraps a second time and is clipped by `LABEL_LINES` - the
reader loses the second half of the question. `FieldRow` re-wraps to the width the gutter
actually has, which is why the wrapping is done here in the first place: the tree connectors
have to be carried down onto the lines a caption wraps onto, and Rich cannot do that."""

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
    """A field's value on one line, in the words it was answered with.

    The review screen is the last thing read before anything is written, and it was printing
    the values behind the answers rather than the answers: `True` where the user picked `Yes`,
    `["x", "y"]` where they ticked two options, `[]` where they ticked none. On the reference
    template that is eleven of twenty-three questions reading as Python. A bool is the case
    that cannot resolve itself - its two labels live in the renderer, not in the state - so
    they are supplied here, from the same pair the option row draws.
    """
    if field.secret:
        return "***" if field.value else ""
    choices = field.choices or (BOOL_CHOICES if isinstance(field.value, bool) else ())
    # gated on there being choices, not on the value being a list: a `type: json` answer that
    # happens to parse to a sequence was being flattened to a bare comma list, so `["a, b"]`
    # and `["a", "b"]` both read `a, b`. A multiselect always carries choices, so the case this
    # is for is untouched and a structured value falls back to its own rendering
    if choices and isinstance(field.value, (list, tuple)):
        # "none of these" is a decision; the review screen's `not set` is what it says about a
        # question nobody reached, in the same words and the same grey
        if not field.value:
            return "none selected"
        return ", ".join(_label_of(choices, value) for value in field.value)
    return _label_of(choices, field.value)


def _label_of(choices: Any, value: Any) -> str:
    """One value as its label, or as itself where the choices do not name it."""
    for choice in choices:
        if choice.value == value:
            return choice.label
    return " ".join(_as_text(value).split())


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

    def __init__(self, context: str = "", project: str | None = None) -> None:
        """Build the header: the screen's context, and the project - the destination
        directory's name, which is what the run is FOR and the one word that names it on
        every screen. It replaced the review's full path, whose only surviving part after a
        crop was this same word."""
        super().__init__(id="app-header")
        self._label_context = context
        self._project = project

    def compose(self) -> ComposeResult:
        """The title cell and the version cell."""
        yield Static(self._title(), id="hdr-title")
        yield Static(f"v{__version__}", id="hdr-version")

    def on_resize(self) -> None:
        """Re-fit the title to the width the bar actually has.

        A path in the header used to be cropped to a constant, which is both too aggressive on
        a wide terminal - a project name cut with half the row empty beside it - and no help on
        a narrow one, where the stylesheet's own ellipsis took the tail instead. The width is
        known here and nowhere earlier, so this is where the decision belongs.
        """
        self.query_one("#hdr-title", Static).update(self._title())

    def set_context(self, context: str) -> None:
        """Rewrite the context: the survey keeps the field position here as focus moves."""
        self._label_context = context
        self.query_one("#hdr-title", Static).update(self._title())

    def _title(self) -> str:
        """The title cell's text: the app name, the project, and the screen's context.

        A project name too long for the row is shortened from the left, so what survives is
        its end. The stylesheet crops from the right as a backstop, and on a name like
        `customer-portal-v2` that removes exactly the part that tells two projects apart, so
        this has to get there first.

        The separator is U+2E31 WORD SEPARATOR MIDDLE DOT rather than the U+00B7 middle dot it
        looks identical to. U+00B7 has an ambiguous East Asian width, so a terminal configured
        to render ambiguous characters wide gives it two cells while `rich.cells.cell_len`
        counts one, and the header's right-aligned half is pushed a cell out. U+2E31 is width
        neutral, which no terminal has the latitude to widen.
        """
        parts = ["copier-tui"]
        if self._label_context:
            parts.append(self._label_context)
        if self._project:
            # what the row has left, once the fixed halves have taken theirs: the version cell,
            # this bar's padding, and the words already in `parts`
            room = self.size.width - len(" ⸱ ".join(parts)) - len(__version__) - HEADER_FIXED
            parts.insert(1, fit_name(self._project, max(room, HEADER_PATH_FLOOR)))
        return " ⸱ ".join(parts)


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
    FieldRow.row-cond {{
        background: {ROW_COND_BG};
        border-left: thick {ROW_COND_BG};
    }}
    FieldRow.row-alt.row-cond {{
        background: {ROW_ALT_COND_BG};
        border-left: thick {ROW_ALT_COND_BG};
    }}
    FieldRow:focus-within {{
        background: {ROW_FOCUS_BG};
        border-left: thick {CYAN};
    }}
    FieldRow > .field-rail {{
        display: none;
        height: 1;
        padding: 0 0 0 1;
        color: {TEXT_SUBTLE};
    }}
    FieldRow:focus-within > .field-rail {{
        display: block;
    }}
    /* the plate under the cursor is one ground on every row, so walking the form does not make
       the lifted row flicker between the two bands. The banded rules are restated here rather
       than left to fall through: a row matching two classes outranks a bare `:focus-within`,
       and would keep its own band colour under the cursor.

       Background only. These carry no `border-left`, because that is the breathing bar's and
       the bar is set by `_PULSE_CSS` below, whose rules match one class and a pseudo-class.
       A restated rule naming two classes and a pseudo-class outranks every one of them, so
       the bar stopped where it stood on any row that was banded AND conditional - while the
       option mark beside it, coloured in code rather than in CSS, went on breathing. Two
       halves of one signal, visibly out of step, on precisely one row in four. */
    /* the one exception the user reads a meaning off: a question another answer decides
       whether to ask keeps its green lean while it is the row being read. This one IS needed -
       `FieldRow.row-cond` matches as strongly as `FieldRow:focus-within` and comes first, so
       without it a focused conditional row keeps its unfocused band. The plain and banded
       cases need no such restatement: `FieldRow:focus-within` is written after both bands and
       wins the tie on source order, which was measured rather than assumed. */
    FieldRow.row-cond:focus-within {{
        background: {ROW_COND_FOCUS_BG};
    }}
    {_PULSE_CSS}
    FieldRow > .field-head {{
        height: auto;
    }}
    FieldRow .field-label {{
        /* a share of the row, capped at the width it used to take outright. Fixed at 56 it
           left the answer column 0 columns wide at MIN_WIDTH - the width the resize prompt
           tells the reader to reach - so every row showed its caption and nothing beside it,
           and no prompt said anything was wrong, because 60 is not too small. Above about 93
           columns the cap binds and the layout is what it always was. */
        width: 60%;
        max-width: {LABEL_WIDTH};
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
        padding: 0 2 0 {LABEL_WIDTH};
        color: {TEXT_MUTED};
    }}
    FieldRow:focus-within > .field-help.has-help {{
        display: block;
        /* the cap belongs to help, not to errors. Help is ambient - it is on every focused
           question, so a line of it costs a row of the form throughout. An error is on a
           handful of rows, only when something is wrong, and stops the form advancing until
           it is read; capped, a long validator sentence lost half its words with nothing on
           screen marking the cut, ending on a clause that reads as finished. */
        max-height: {HELP_LINES};
    }}
    FieldRow > .field-help.has-error {{
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

    def __init__(self, question: Question, field: FieldState, *, spoken: bool = True) -> None:
        """Build the row for a question and its current state.

        `spoken` is whether this row may print the reason its answer is refused. The flag in
        the gutter marks it either way; the sentence waits until the reader has engaged with
        the question, because a survey validates on mount and would otherwise open spelling
        out in red every question nobody has been asked yet.
        """
        super().__init__(id=f"row-{question.id}")
        self.spoken = spoken
        self.question = question
        self._field = field
        self._label = Static(classes="field-label")
        self._branch = ""
        self._rail_above = Static(classes="field-rail")
        self._rail_below = Static(classes="field-rail")
        self._control = control_for(question, field)
        self._flag = Static(classes="field-flag", id=f"flag-{question.id}")
        self._help = Static(classes="field-help", id=f"help-{question.id}")
        self._last_value: Any = None
        self._pulse: Timer | None = None
        self._beat = 0

    def compose(self) -> ComposeResult:
        """A spacer line, the caption line with its control, the help, and a spacer again.

        The spacers are the blank line the focused row keeps either side of itself. They are
        widgets rather than padding because a run of children has to cross them: padding is
        empty by definition, so the tree broke wherever the cursor landed inside a run.
        """
        yield self._rail_above
        with Horizontal(classes="field-head"):
            yield self._label
            yield self._control
            yield self._flag
        yield self._help
        yield self._rail_below

    def on_mount(self) -> None:
        """Show the caption, the help and the glyph; the control holds its own value."""
        self._chrome(self._field)
        self._last_value = self.value

    def _caption_width(self) -> int:
        """Columns the caption has, from the gutter's real width rather than its cap.

        `Widget.size` is the content box - Textual has already taken the padding off - so
        subtracting it again, as this did, spent three columns of every caption twice and cost
        a word on the rows that wrap.
        """
        measured = self._label.size.width
        return measured if measured else _CAPTION_WIDTH

    def on_resize(self) -> None:
        """Re-wrap the caption and re-indent the help to the gutter's real width.

        The gutter is a share of the row, so neither can be a constant: a caption wrapped to
        the cap and then laid out in a narrower box wraps again and is clipped at three lines,
        and the help line indented to the cap had zero columns left at MIN_WIDTH.

        The indent was a constant equal to the old fixed gutter, so at MIN_WIDTH it left the
        help nothing at all - zero columns - and at 72 it left eleven, which is three lines of
        a sentence in a box capped at two. Textual takes padding in cells, so a share has to be
        measured rather than declared.
        """
        self._indent()
        self._label.update(_label_text(self.question, self._branch, self._caption_width()))

    def _indent(self) -> None:
        """Set the help's left padding to the column it belongs under.

        Help aligns to the control it explains, so it is indented to the gutter's real width -
        the OUTER width, not the content width, because the control column starts at the
        label's outer edge and indenting to its content box put the help three columns left of
        everything it sits under.

        An error takes the left margin instead. Indented to the gutter it had 22 cells at
        MIN_WIDTH, so one long validator sentence filled the form and pushed every other
        question off screen; the `!` and the rose tie it to its row without the alignment.

        Both callers go through here: living in `on_resize` alone, the indent only followed a
        change of WIDTH, so an error arriving or clearing left the previous message's indent
        behind.
        """
        spoken = bool(self._field.errors) and self.spoken
        self._help.styles.padding = (0, 2, 0, 1 if spoken else self._label.outer_size.width)

    def on_descendant_focus(self) -> None:
        """Start the bar breathing, and let the row explain itself.

        Arriving on a row is engaging with it, and the screen records that - it owns the flag,
        because a row rebuilt from state would otherwise lose what the widget knew.

        Not when the platform has asked for no animation. The beat is a plain interval rather
        than a Textual animation, so nothing else stands it down, and what it does is loop for
        as long as the row holds the focus - which on a thirty-seven question form is most of
        the session. A reader who has turned motion off is left with the static bar the
        stylesheet already draws, which is the same cue without the movement.
        """
        self._beat = 0
        if self.app.animation_level == "none":
            return
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
        if isinstance(self._control, InlineOptions):
            self._control.set_mark_shade(MARK_SHADES[0])

    def _breathe(self) -> None:
        """Move the bar one step round the cycle, and blink the cursor mark on the same clock."""
        phase = self._beat % len(PULSE_CYCLE)
        shade = PULSE_CYCLE[phase]
        self._beat += 1
        for index in range(len(PULSE_SHADES)):
            self.set_class(index == shade, f"pulse-{index}")
        if isinstance(self._control, InlineOptions):
            # four states per cycle: two blinks per breath of the bar
            self._control.set_mark_shade(MARK_SHADES[(phase * 4 // len(PULSE_CYCLE)) % 2])

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
        self._label.update(_label_text(self.question, self._branch, self._caption_width()))
        self._flag.update(_flag_text(field))
        help = _help_text(self.question, field if self.spoken else replace(field, errors=()))
        self._help.update(help)
        # a class, not `display`: an inline display overrides the stylesheet, and the rule it
        # was overriding is the one that keeps help to the focused row. A row with help spent
        # a second line whether or not anyone was reading it, which is the space the one-row
        # layout exists to recover. Empty help stays classless so it can never open a line
        self._help.set_class(bool(help.plain) and not field.errors, "has-help")
        # an error is not help. Help is worth a row only while the cursor is on the question it
        # explains; a problem with an answer is worth a row wherever it is, or a row the user
        # has moved off shows a bare `!` and nothing that says what is wrong with it
        self._help.set_class(bool(field.errors) and self.spoken, "has-error")
        self._indent()
        self._control.disabled = not field.enabled
        # the caption greys with the control: a row this answer set rules out must not look
        # like a row that is merely unfocused, which is what a live caption over a dead
        # control looked like
        self.set_class(not field.enabled, "row-off")

    def set_branch(self, glyph: str, sibling_above: bool = False) -> None:
        """Print a tree connector before the caption, and carry the run over the spacers.

        The form owns both because only the form knows what sits around this row, and a
        connector is a statement about its neighbours rather than about this question. A
        spacer carries the run only where the run actually crosses it - under a row with a
        sibling below, over a row with one above - so a rail never points at nothing.
        """
        rail = Text(RAIL, style=TEXT_SUBTLE)
        self._rail_above.update(rail if sibling_above else Text(""))
        self._rail_below.update(rail if glyph == BRANCH_MORE else Text(""))
        if glyph == self._branch:
            return
        self._branch = glyph
        self._label.update(_label_text(self.question, self._branch, self._caption_width()))

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


def _label_text(question: Question, branch: str = "", width: int = _CAPTION_WIDTH) -> Text:
    """The question caption behind its tree connector, wrapped rather than cut.

    The connector keeps a colour of its own, muted, because it is structure rather than
    words - it must not brighten with the caption when the cursor arrives on the row.

    Hue on a caption used to mean "you have changed this", which read as a state of the
    question rather than of its answer - a blue line looks like a heading or something the
    form will not let you touch, and it sat on rows the cursor then walked straight into.
    The row's band, its field grounds and its focus bar say where the cursor is and what can
    be edited; what the answer happens to be is the answer's own business, so the stylesheet
    colours this by focus and nothing else.
    """
    if not branch:
        return Text(question.label, overflow="fold")
    caption = Text(overflow="fold")
    for index, line in enumerate(wrap(question.label, max(width - len(branch), 8)) or [""]):
        if index:
            caption.append("\n")
        caption.append(branch if index == 0 else _BRANCH_TAIL[branch], style=TEXT_SUBTLE)
        caption.append(line)
    return caption


def _help_text(question: Question, field: FieldState) -> Text:
    """What the focused row says under itself: the problem, else the question's own help.

    Help that only repeats the caption is dropped. copier falls back to the help string for
    the prompt caption, so a template whose question carries help and nothing else ends up
    with the same sentence twice, one line above the other, saying nothing the second time.
    """
    if field.errors:
        return Text(field.errors[0], style=ERROR_FG, overflow="fold")
    help = "" if question.help == question.label else question.help
    # the same precedence `control_for` uses - secret, then multiline, then kind - because it
    # is the same decision. Tested kind-first, a `type: str` question with `choices` and
    # `multiline: true` got a TextArea and a help line naming three keys it does not have,
    # while the hint it needs was withheld
    if question.secret:
        pass
    elif question.multiline or question.kind is Kind.STRUCTURED:
        # on these two the editor owns enter, so the screen's Review entry is taken out of the
        # footer while the cursor is here - leaving two keys on screen and both abandon the run
        move = "arrows leave the row to review"
        help = f"{help}  -  {move}" if help else move
    elif question.kind is Kind.MULTISELECT:
        pick = "space ticks an option"
        help = f"{help}  -  {pick}" if help else pick
    elif question.kind is Kind.BOOL:
        # "flips" rather than "cycles": on two options that is what the key does, and it is
        # what `action_toggle` calls it
        pick = "space flips"
        help = f"{help}  -  {pick}" if help else pick
    elif question.kind is Kind.CHOICE:
        pick = "space cycles the answer"
        help = f"{help}  -  {pick}" if help else pick
    # the example is what a reader needs before answering and the key names are what they need
    # while answering; both at once overflowed the two-line box from 60 to 83 columns and the
    # example - the half that was there first - was the half that got cut
    if not help and question.placeholder and field.value in (None, "", [], {}, ()):
        # a placeholder written into the value column reads as an answer nobody gave; said
        # here it is plainly guidance, and the field stays visibly empty until it is answered
        hint = f"for example: {question.placeholder}"
        help = hint
    return Text(help, style=TEXT_MUTED, overflow="fold")


def _flag_text(field: FieldState) -> Text:
    """One glyph for the row's standing: a problem, or a field this answer set rules out."""
    if field.errors:
        return Text("!", style=f"bold {ERROR_FG}")
    if not field.enabled:
        return Text("-", style=AMBER)
    return Text(" ")
