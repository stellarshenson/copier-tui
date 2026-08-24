"""The survey screen: every visible question as one compact scrolling form."""

from __future__ import annotations

from dataclasses import replace
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.message import Message
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Footer, Static, TextArea

from copier_tui.theme import ROSE, TEXT_MUTED
from copier_tui.widgets import FieldRow, HeaderBar
from copier_ui import State, TemplateUI

_ACTION_KEY = {
    "confirm": "enter",
    "cancel": "escape",
    "focus_next": "down",
    "focus_previous": "up",
}
"""Screen action to the key it is bound to, for check_action."""

_ENTER_OWNERS = (TextArea,)
"""Controls with nothing else that does enter's job - an editor breaks the line. Everything
else leaves enter alone, so one key confirms the survey from anywhere in the form.

Options are picked with left and right, so a choice never claims enter and never claims the
arrows that walk the form."""

_ARROW_OWNERS = (TextArea,)
"""Controls that move a cursor of their own with up and down, at anything but their edge."""

KEY_HINT = "up down  move    left right  choose    enter  review and create"
"""The legend under the form. Every key that moves or changes something is named, because a
survey nobody can navigate is worse than one that spends a row saying how."""

CANCEL_HINT = "press escape again to discard every answer and quit"
"""Shown by the first escape; a second one within the arming window quits."""

CANCEL_WINDOW = 3.0
"""Seconds an armed escape stays armed. After that the safety goes back on by itself."""


class _Form(VerticalScroll):
    """The scrolling form, which is never itself a place the cursor stops.

    A VerticalScroll takes focus by default so it can be scrolled, which put a stop between
    every pair of questions where no row was focused, nothing highlighted and nothing could
    be edited - a dead press that reads as a row offering no answer. Textual scrolls the
    focused control into view on its own, so the container has nothing to focus for.
    """

    can_focus = False


class SurveyScreen(Screen[None]):
    """The whole visible survey, scrollable, navigable in any order.

    It never dismisses itself. Review is stacked on top and popped off again, so the form
    underneath keeps its scroll offset and its focused field for the whole run.
    """

    class Confirmed(Message):
        """Every answer is valid and the user asked to move on."""

    class Cancelled(Message):
        """The user confirmed the second escape and wants out."""

    DEFAULT_CSS = f"""
    #survey-form {{
        width: 100%;
        height: 1fr;
        padding: 1 2 0 0;
        scrollbar-size-vertical: 1;
    }}
    #survey-hint {{
        height: 1;
        width: 100%;
        padding: 0 1;
        color: {TEXT_MUTED};
    }}
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("enter", "confirm", "Review", priority=True),
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("down", "focus_next", "Next field", show=False, priority=True),
        Binding("up", "focus_previous", "Previous field", show=False, priority=True),
    ]

    def __init__(self, ui: TemplateUI) -> None:
        """Hold the template UI the rows are built from."""
        super().__init__(id="survey-screen")
        self.ui = ui
        self._hint = Static(id="survey-hint")
        self._armed = False

    def compose(self) -> ComposeResult:
        """Header, the scrolling form, the key legend, footer."""
        yield HeaderBar(f"{self.ui.template_name} questionnaire")
        yield _Form(id="survey-form")
        yield self._hint
        yield Footer()

    async def on_mount(self) -> None:
        """Build the rows and focus the first one, once it has a control to focus.

        The mounts are awaited because a row composes its control a beat after it mounts
        itself: focusing before that finds the row and not the widget inside it, which
        `_focus_field` reads as a missing field, and the form opens with nothing focused.
        """
        await self._refresh_rows()
        self._focus_first()

    async def on_screen_resume(self) -> None:
        """Coming back from review: re-read the state, keeping scroll and focus as they were."""
        await self._refresh_rows()

    async def on_field_row_changed(self, message: FieldRow.Changed) -> None:
        """Push the new value into copier_ui and refresh every row from the new state."""
        message.stop()
        self._disarm()
        self.ui.set(message.field_id, message.value)
        await self._refresh_rows()

    def on_descendant_focus(self) -> None:
        """The header position follows the focus; the legend is a constant."""
        self._disarm()
        self._show_hint()
        self._show_position()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Give a key back to the control that owns it.

        Returning None greys the screen's binding for this key, which is what lets the key
        reach the focused control instead. Enter belongs to a multiline editor, which breaks
        the line with it; up and down belong to a cursor that still has somewhere to go, so
        an editor hands the focus on at its own first and last line rather than trapping it.
        """
        key = _ACTION_KEY.get(action)
        if key is None:
            return True
        if key == "enter":
            owner = self._focused_owner(_ENTER_OWNERS)
            return owner is None or not getattr(owner, "owns_enter", True)
        if key in ("up", "down"):
            owner = self._focused_owner(_ARROW_OWNERS)
            return True if owner is None else _at_edge(owner, key)
        return True

    def _focused_owner(self, types: tuple[type[Widget], ...]) -> Widget | None:
        """The focused control, or the control enclosing it, when it is one of these."""
        focused = self.focused
        if focused is None:
            return None
        if isinstance(focused, types):
            return focused
        return next((node for node in focused.ancestors if isinstance(node, types)), None)

    async def action_confirm(self) -> None:
        """Advance to review, or point at the first field that is not ready."""
        errors = self.ui.validate()
        if errors:
            await self._refresh_rows()
            field_id, messages = next(iter(errors.items()))
            self._focus_field(field_id)
            self._hint.update(Text(f"{field_id} - {messages[0]}", style=ROSE))
            return
        self.post_message(self.Confirmed())

    def action_focus_next(self) -> None:
        """Move to the next field. Screen has no focus_next action of its own."""
        self.focus_next()

    def action_focus_previous(self) -> None:
        """Move to the previous field."""
        self.focus_previous()

    def action_cancel(self) -> None:
        """Arm on the first escape, quit on the second - a survey is too costly to lose."""
        if self._armed:
            self.post_message(self.Cancelled())
            return
        self._armed = True
        self._hint.update(Text(CANCEL_HINT, style=ROSE))
        self.set_timer(CANCEL_WINDOW, self._disarm)

    def _disarm(self) -> None:
        """Put the safety back on: an armed escape never stands past its window."""
        if not self._armed:
            return
        self._armed = False
        self._show_hint()

    async def _refresh_rows(self) -> None:
        """Add, remove and update rows so they match the state's visible, non-preset fields.

        Mounting is awaited so a caller may act on the controls straight afterwards.
        """
        state = self.ui.state()
        schema = self.ui.schema()
        errors = self.ui.validate()
        wanted = askable_ids(state)
        form = self.query_one("#survey-form", VerticalScroll)
        rows = {row.question.id: row for row in form.query(FieldRow)}
        for field_id, row in rows.items():
            if field_id not in wanted:
                row.remove()
        previous: FieldRow | None = None
        for position, field_id in enumerate(wanted):
            field = replace(state.fields[field_id], errors=tuple(errors.get(field_id, ())))
            row = rows.get(field_id)
            if row is None:
                row = FieldRow(schema.by_id(field_id), field)
                if previous is None:
                    await form.mount(row, before=0)
                else:
                    await form.mount(row, after=previous)
            else:
                row.update(field)
            # banding is by position in the form as it now stands, not by the order rows
            # were built in: a conditional question appearing or disappearing restripes
            # everything below it, and a form that keeps the old parity reads as though two
            # adjacent questions were one
            row.set_class(position % 2 == 1, "row-alt")
            previous = row
        self._show_hint()
        self._show_position()

    def _show_hint(self) -> None:
        """Say what the keys do. A field's own help and errors are printed under the field.

        The line is a constant legend rather than a per-field message because the focused
        row now carries everything specific to it, and a legend that never changes is one
        the eye stops having to re-read.
        """
        if self._armed:
            return
        self._hint.update(Text(KEY_HINT, style=TEXT_MUTED))

    def _show_position(self) -> None:
        """The header names the template and says which field of how many.

        Which template is being filled in is the one thing a questionnaire cannot be read off
        its own questions, and it is what a person needs when several are open at once.
        """
        rows = list(self.query(FieldRow))
        row = self._focused_owner((FieldRow,))
        place = f"{rows.index(row) + 1} of {len(rows)}" if row in rows else f"{len(rows)} fields"
        self.query_one(HeaderBar).set_context(f"{self.ui.template_name} questionnaire - {place}")

    def _focus_first(self) -> None:
        """Put the cursor in the first field."""
        rows = self.query(FieldRow)
        if rows:
            self._focus_field(rows.first(FieldRow).question.id)

    def _focus_field(self, field_id: str | None) -> None:
        """Scroll a field into view and focus its control.

        The screen is asked directly rather than through `Widget.focus`, which defers the
        real call to the next beat of the app's message pump: on the first paint the control
        is not laid out yet when that beat arrives, it fails the visibility half of
        `focusable`, and the focus is dropped without a word. The form then opened with no
        row focused at all.
        """
        if field_id is None:
            return
        try:
            control = self.query_one(f"#ctl-{field_id}")
        except NoMatches:
            return
        self.set_focus(control)
        control.scroll_visible()


def _at_edge(owner: Widget, key: str) -> bool | None:
    """True when the cursor is against the control's end and the key should leave it.

    None keeps the key inside the control. This is what stops a multi-line editor or a
    long option list from swallowing the arrow that was meant to walk the form.
    """
    if isinstance(owner, TextArea):
        row = owner.cursor_location[0]
        last = owner.document.line_count - 1
        return True if (row == 0 if key == "up" else row >= last) else None
    return None


def askable_ids(state: State) -> list[str]:
    """The visible fields the user is asked for: presets came in with --data."""
    return [field_id for field_id in state.visible_ids if not state.fields[field_id].preset]
