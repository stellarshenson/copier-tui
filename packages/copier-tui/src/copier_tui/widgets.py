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

from rich.cells import cell_len, set_cell_size
from rich.text import Text
from textual import events
from textual.app import ComposeResult, RenderResult
from textual.containers import Horizontal, Vertical
from textual.geometry import Offset
from textual.message import Message
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Input, Static, TextArea

from copier_tui import __version__
from copier_tui.inline import BOOL_CHOICES, InlineOptions
from copier_tui.paths import fit_name
from copier_tui.theme import (
    HELP_LINES,
    LABEL_LINES,
    LABEL_WIDTH,
    PULSE_CYCLE,
    PULSE_INTERVAL,
    PULSE_STEPS,
    color,
)
from copier_tui.wrapping import install as install_wrapping
from copier_ui import FieldState, Kind, Question

install_wrapping()
"""Both of Textual's wraps are replaced here, before the first control is built.

The editors are built in this module and the static text is drawn from it, so this is the
last point common to both."""

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

HEADER_FIXED = 4
"""Columns the header spends on padding: 2 for `#hdr-version`'s and 2 for `#hdr-title`'s, both
set in `theme.py`, so this is the number to revisit if that padding changes. Everything else
the right-hand cell costs is measured from its own text."""

HEADER_SEP = " \u2e31 "
"""What stands between the header's parts. U+2E31 WORD SEPARATOR MIDDLE DOT, not the U+00B7 it
looks identical to: U+00B7 has an ambiguous East Asian width, so a terminal set to render such
characters wide gives it two cells where `rich.cells.cell_len` counts one."""

_BRAND_TEXT = f"copier-tui v{__version__}"
"""The right-hand cell: the tool and the version, the two facts that never change between
screens - so they sit where the eye is not reading the run's own state."""

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

    def scroll_cursor_visible(self, center: bool = False, animate: bool = False) -> Offset:
        """Bring the caret onto the screen, scrolling the form when the box cannot.

        A box is as tall as its answer, so the caret's row is a row of the form, not of the
        box - and the box has nothing left to scroll. Textual scrolls a widget into view when
        the focus moves and never again, so typing past the fold wrote characters onto no row
        at all: the text was in the answer and nowhere on screen. It bites twice, and the
        second is why capping the height does not fix it - a box that fits the form still puts
        its last line below the form's last row when the rows above it fill the rest.

        Only while this editor has the focus. `FieldRow.update` rewrites every control on any
        change, which puts the caret back at the end of editors nobody is typing in; without
        the guard each of those dragged the form off to its own row.
        """
        offset = super().scroll_cursor_visible(center, animate)
        if not self.has_focus:
            return offset
        # the walk ends at the app, which is a node rather than a widget and answers no
        # question about scrolling
        form = next(
            (
                node
                for node in self.ancestors
                if isinstance(node, Widget) and node.allow_vertical_scroll
            ),
            None,
        )
        if form is None:
            return offset
        caret = self.cursor_screen_offset.y
        view = form.content_region
        if caret < view.y:
            form.scroll_to(y=form.scroll_offset.y - (view.y - caret), animate=animate)
        elif caret >= view.bottom:
            form.scroll_to(y=form.scroll_offset.y + (caret - view.bottom + 1), animate=animate)
        return offset


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
        return TextArea(
            _as_text(field.value),
            soft_wrap=True,
            compact=True,
            id=control_id,
            classes="field-doc",
        )
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
    """One-row header: project, context and position left, the tool and its version right."""

    def __init__(self, context: str = "", project: str | None = None) -> None:
        """Build the header: the screen's context, and the project - the destination
        directory's name, which is what the run is FOR and the one word that names it on
        every screen. It replaced the review's full path, whose only surviving part after a
        crop was this same word."""
        super().__init__(id="app-header")
        self._label_context = context
        self._project = project
        self._position = ""

    def compose(self) -> ComposeResult:
        """The title cell and the version cell."""
        yield Static(self._title(), id="hdr-title")
        yield Static(_BRAND_TEXT, id="hdr-version")

    def on_resize(self) -> None:
        """Re-fit the title to the width the bar actually has.

        A path in the header used to be cropped to a constant, which is both too aggressive on
        a wide terminal - a project name cut with half the row empty beside it - and no help on
        a narrow one, where the stylesheet's own ellipsis took the tail instead. The width is
        known here and nowhere earlier, so this is where the decision belongs.
        """
        self.query_one("#hdr-title", Static).update(self._title())

    def set_position(self, position: str) -> None:
        """Rewrite the position: the survey keeps its field counter here as focus moves."""
        self._position = position
        self.query_one("#hdr-title", Static).update(self._title())

    def _title(self) -> Text:
        """The title cell: the project, the screen's context, and the field position.

        The project leads because it names what the run is for, and it and the position are
        the two facts nothing else on the screen carries - so both are written in the bright
        accent and the context between them is not. The tool's own name and version say the
        same thing on every screen of every run, so they sit in the right-hand cell.

        The three are cropped in the order they can be spared. The position is never cropped:
        it is eight cells and the one thing on the row a reader cannot work out. The project
        name is shortened from the left, so what survives is its end - the stylesheet crops
        from the right as a backstop, and on a name like `customer-portal-v2` that removes
        exactly the part that tells two projects apart. The context gives way first and keeps
        its head, since `questionnaire` is worth less than the template it names.
        """
        title = Text(no_wrap=True, overflow="ellipsis")
        # the project and the field position are the two parts of the title nothing else on
        # the screen says, so they take the bright accent
        lead = f"bold {color(self.app, 'cyan-bright')}"
        # what the row has for the title: everything the right-hand cell and the padding
        # are not using
        room = self.size.width - cell_len(_BRAND_TEXT) - HEADER_FIXED
        parts: list[tuple[str, str]] = []
        if self._project:
            spare = room - _spent(self._label_context, self._position)
            parts.append((fit_name(self._project, max(spare, HEADER_PATH_FLOOR)), lead))
        if self._label_context:
            spare = room - _spent(*(part for part, _ in parts), self._position)
            parts.append((_crop(self._label_context, max(spare, 0)), color(self.app, "text")))
        if self._position:
            parts.append((self._position, lead))
        for part, style in parts:
            if not part:
                continue
            if title.plain:
                title.append(HEADER_SEP, style=color(self.app, "subtle"))
            title.append(part, style=style)
        return title


def _spent(*parts: str) -> int:
    """Cells the parts beside this one take, each with the separator that precedes it."""
    return sum(cell_len(part) + len(HEADER_SEP) for part in parts if part)


def _crop(text: str, limit: int) -> str:
    """`text`, or its head behind a `...` marker when it is wider than `limit`."""
    if cell_len(text) <= limit:
        return text
    if limit <= len("..."):
        return set_cell_size(text, max(limit, 0))
    return set_cell_size(text, limit - len("...")) + "..."


class _Head(Horizontal):
    """The caption with its control, and the tree's line down the caption column.

    A row is as tall as its tallest part, so a caption of one line beside five stacked options
    leaves four empty lines under it. Where the tree runs on below the row - the next row is
    its first child, or its sibling - those lines carry the tree's vertical line, so the
    connector column is unbroken from a question to what hangs from it.

    The container draws the line itself, on every one of its lines, and the caption and the
    control are drawn over it. It shows in exactly the cells neither covers, and it costs no
    layout: written into the caption instead, it would make the caption as tall as the control
    and hold the row at that height after the control had shrunk.
    """

    def __init__(self) -> None:
        """Start with no line to draw."""
        super().__init__(classes="field-head")
        self._rail = ""

    def set_rail(self, ink: str) -> None:
        """Draw the line in `ink`, or stop drawing it when `ink` is empty."""
        if ink != self._rail:
            self._rail = ink
            self.refresh()

    def render(self) -> RenderResult:
        """The line, in the caption's first column, where every connector is drawn."""
        if not self._rail:
            return super().render()
        return Text("\n".join([f" {RAIL}"] * self.size.height), style=self._rail)


_PULSE_CSS = "\n    ".join(
    f"FieldRow.pulse-{step}:focus-within {{ border-left: thick $st-pulse-{step}; }}"
    for step in range(PULSE_STEPS)
)
"""One rule per shade, keyed by a class the focused row cycles through."""


class FieldRow(Vertical):
    """One question: a caption-and-control line, and the help the focused row shows."""

    DEFAULT_CSS = f"""
    FieldRow {{
        height: auto;
        background: $st-row;
        border-left: thick $st-row;
    }}
    FieldRow.row-alt {{
        background: $st-row-alt;
        border-left: thick $st-row-alt;
    }}
    FieldRow.row-cond {{
        background: $st-row-cond;
        border-left: thick $st-row-cond;
    }}
    FieldRow.row-alt.row-cond {{
        background: $st-row-alt-cond;
        border-left: thick $st-row-alt-cond;
    }}
    FieldRow:focus-within {{
        background: $st-row-focus;
        border-left: thick $st-bar;
    }}
    /* the row under the cursor is drawn in the other theme's colours, ground and ink both:
       light with dark ink in the dark theme, dark with light ink in the light one. It is one
       ground on every row, so walking the form does not make the current row change shade
       between the two bands.

       The row is the same height under the cursor as away from it, apart from the help it
       prints. It used to open a blank line above and below itself, so every row under the
       cursor moved on each press of an arrow; the ground says where the cursor is now.

       Background only. These carry no `border-left`, because that is the breathing bar's and
       the bar is set by `_PULSE_CSS` below, whose rules match one class and a pseudo-class.
       A restated rule naming two classes and a pseudo-class outranks every one of them, so
       the bar stopped where it stood on any row that was banded AND conditional. */
    /* the one exception the user reads a meaning off: a question another answer decides
       whether to ask keeps its green lean while it is the row being read. This one IS needed -
       `FieldRow.row-cond` matches as strongly as `FieldRow:focus-within` and comes first, so
       without it a focused conditional row keeps its unfocused band. The plain and banded
       cases need no such restatement: `FieldRow:focus-within` is written after both bands and
       wins the tie on source order, which was measured rather than assumed. */
    FieldRow.row-cond:focus-within {{
        background: $st-row-cond-focus;
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
        color: $st-text;
    }}
    FieldRow:focus-within .field-label {{
        color: $st-caption-focus;
        text-style: bold;
    }}
    FieldRow.row-off .field-label {{
        color: $st-subtle;
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
        color: $st-subtle;
    }}
    FieldRow > .field-head > TextArea {{
        /* every editor is as tall as what it holds: an answer that wraps onto five lines
           gets five, one that wraps onto ten gets ten. A cap here scrolled the rest out of
           sight, and a prefilled answer taller than the cap opened showing its tail,
           because the cursor starts at the end of the value - so the one field whose whole
           point is to be read back before the write was the one that could not be. */
        height: auto;
    }}
    FieldRow > .field-head > .field-doc {{
        /* the exception: a multiline or structured answer is a document, not a sentence,
           and is written and read by scrolling. Left uncapped it would push every question
           below it off the form. */
        max-height: 6;
    }}
    FieldRow > .field-help {{
        display: none;
        height: auto;
        padding: 0 2 0 {LABEL_WIDTH};
        color: $st-muted;
    }}
    FieldRow:focus-within > .field-help.has-help {{
        display: block;
        /* the cap belongs to help, not to errors. Help is ambient - it is on every focused
           question, so a line of it costs a row of the form throughout. An error is on a
           handful of rows, only when something is wrong, and stops the form advancing until
           it is read; capped, a long validator sentence lost half its words with nothing on
           screen marking the cut, ending on a clause that reads as finished. */
        max-height: {HELP_LINES};
        color: $st-help-focus;
    }}
    FieldRow > .field-help.has-error {{
        display: block;
        color: $st-error;
    }}
    FieldRow .field-flag.flag-error {{
        color: $st-error;
        text-style: bold;
    }}
    FieldRow .field-flag.flag-off {{
        color: $st-amber;
    }}
    /* the tree's line crosses the help as well, where the tree runs on below the row: the
       help sits between this row's caption and the row below, so it would otherwise cut the
       connector column for as long as the cursor is on a parent or on a child with a
       sibling. A left border one cell in is the same glyph in the same column as the line
       the head draws above it. */
    FieldRow > .field-help.has-rail {{
        margin: 0 0 0 1;
        border-left: solid $st-subtle;
    }}
    FieldRow:focus-within > .field-help.has-rail {{
        border-left: solid $st-rail-focus;
    }}
    /* an error on the row under the cursor is on that row's ground, which is the other
       theme's, so it takes the other theme's error ink. Written after the two rules above
       and with the pseudo-class on top of their selectors, so it outranks both. */
    FieldRow:focus-within > .field-help.has-error,
    FieldRow:focus-within .field-flag.flag-error {{
        color: $st-error-focus;
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
        self._head = _Head()
        self._label = Static(classes="field-label")
        self._branch = ""
        self._run_below = False
        self._control = control_for(question, field)
        self._flag = Static(classes="field-flag", id=f"flag-{question.id}")
        self._help = Static(classes="field-help", id=f"help-{question.id}")
        self._last_value: Any = None
        self._pulse: Timer | None = None
        self._beat = 0
        self._current = False

    def compose(self) -> ComposeResult:
        """The caption line with its control, and the help under it."""
        with self._head:
            yield self._label
            yield self._control
            yield self._flag
        yield self._help

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
        self._label.update(self._caption())

    def _caption(self) -> Text:
        """The caption as it is drawn now: wrapped to the gutter, behind its connector."""
        return _label_text(self.question, self._branch, self._caption_width(), self._rail_ink())

    def _rail_ink(self) -> str:
        """The tree's ink on this row's ground.

        The row under the cursor has the other theme's ground, so the tree has an ink of its
        own there.
        """
        return color(self.app, "rail-focus" if self._current else "subtle")

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
        left = 1 if spoken else self._label.outer_size.width
        # where the tree's line crosses the help it takes two cells of its own, a margin and
        # the border that draws it, and the words keep the column they had
        taken = 2 if self._run_below else 0
        self._help.styles.padding = (0, 2, 0, max(left - taken, 0))

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
        self._set_current(True)
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
        for step in range(PULSE_STEPS):
            self.remove_class(f"pulse-{step}")
        self._set_current(False)

    def _set_current(self, current: bool) -> None:
        """Redraw the caption for the ground it is now on: the cursor's row, or a band.

        The stylesheet recolours everything else when the focus moves. The tree connector is
        a span inside the caption with an ink of its own, which a stylesheet cannot reach.
        """
        if current == self._current:
            return
        self._current = current
        if self._branch:
            self._label.update(self._caption())
        self._head.set_rail(self._rail_ink() if self._run_below else "")

    def _breathe(self) -> None:
        """Move the bar one step round the cycle."""
        shade = PULSE_CYCLE[self._beat % len(PULSE_CYCLE)]
        self._beat += 1
        for step in range(PULSE_STEPS):
            self.set_class(step == shade, f"pulse-{step}")

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
        self._label.update(self._caption())
        self._flag.update(_flag_text(field))
        self._flag.set_class(bool(field.errors), "flag-error")
        self._flag.set_class(not field.errors and not field.enabled, "flag-off")
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

    def set_branch(self, glyph: str, run_below: bool = False) -> None:
        """Print a tree connector before the caption, and carry the tree on below it.

        The form owns both because only the form knows what sits around this row, and a
        connector is a statement about its neighbours rather than about this question.
        `run_below` is whether the tree goes on into the next row: the lines of this row
        under its caption then carry the tree's vertical line.
        """
        if (glyph, run_below) == (self._branch, self._run_below):
            return
        self._branch, self._run_below = glyph, run_below
        self._label.update(self._caption())
        self._head.set_rail(self._rail_ink() if run_below else "")
        self._help.set_class(run_below, "has-rail")
        self._indent()

    def _write_value(self, field: FieldState) -> None:
        """Push the state's value into the control."""
        control = self._control
        if isinstance(control, InlineOptions):
            choices = BOOL_CHOICES if self.question.kind is Kind.BOOL else field.choices
            control.set_options(choices, field.value)
        elif isinstance(control, TextArea):
            control.text = _as_text(field.value)
            if isinstance(control, WrapInput):
                # a rewritten editor starts at the top left, the same as a new one, so the
                # cursor is put back where `WrapInput.on_mount` puts it
                control.move_cursor(control.document.end)
        else:
            control.value = _as_text(field.value)
            # an `Input` moves its cursor to the end for its first value only; rewritten, it
            # keeps the old position, which is inside the new value
            control.cursor_position = len(control.value)

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


def _label_text(
    question: Question, branch: str = "", width: int = _CAPTION_WIDTH, rail: str = ""
) -> Text:
    """The question caption behind its tree connector, wrapped rather than cut.

    The connector keeps a colour of its own, `rail`, because it is structure rather than
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
        caption.append(branch if index == 0 else _BRANCH_TAIL[branch], style=rail)
        caption.append(line)
    return caption


def _help_text(question: Question, field: FieldState) -> Text:
    """What the focused row says under itself: the problem, else the question's own help.

    The words only. The stylesheet colours them, by whether the line is help or an error.

    Help that only repeats the caption is dropped. copier falls back to the help string for
    the prompt caption, so a template whose question carries help and nothing else ends up
    with the same sentence twice, one line above the other, saying nothing the second time.
    """
    if field.errors:
        return Text(field.errors[0], overflow="fold")
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
    # the example is what a reader needs before answering and the key names are what they need
    # while answering; both at once overflowed the two-line box from 60 to 83 columns and the
    # example - the half that was there first - was the half that got cut
    if not help and question.placeholder and field.value in (None, "", [], {}, ()):
        # a placeholder written into the value column reads as an answer nobody gave; said
        # here it is plainly guidance, and the field stays visibly empty until it is answered
        hint = f"for example: {question.placeholder}"
        help = hint
    return Text(help, overflow="fold")


def _flag_text(field: FieldState) -> Text:
    """One glyph for the row's standing: a problem, or a field this answer set rules out.

    The colour is the stylesheet's, by the class the row puts on the flag for each standing.
    """
    if field.errors:
        return Text("!")
    if not field.enabled:
        return Text("-")
    return Text(" ")
