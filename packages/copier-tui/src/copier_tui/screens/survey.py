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
from textual.widgets import Footer, OptionList, Select, SelectionList, Static, TextArea

from copier_tui.theme import ROSE, TEXT_MUTED, TEXT_SUBTLE
from copier_tui.widgets import FieldRow, HeaderBar
from copier_ui import State, TemplateUI

_ACTION_KEY = {
    "confirm": "enter",
    "cancel": "escape",
    "focus_next": "down",
    "focus_previous": "up",
}
"""Screen action to the key it is bound to, for check_action."""

_ENTER_OWNERS = (OptionList, TextArea)
"""Controls with nothing else that does enter's job: an open menu picks, an editor breaks
the line. Everything else leaves enter alone, so one key confirms from anywhere in the form.

A Switch and a collapsed Select are deliberately absent - space already toggles the one and
opens the other. Handing them enter as well would cost the user the confirm key on every
boolean and every choice, and the menu's own enter would close onto the Select that opened
it, so a survey could never be confirmed from a choice field at all.
"""

_ARROW_OWNERS = (OptionList, TextArea)
"""Controls that move a cursor of their own with up and down, at anything but their edge.

SelectionList and the Select overlay are both OptionList subclasses, so both are covered.
"""

OPEN_HINT = "space opens the list"
"""Fallback for a collapsed choice control whose question declares no help.

A field's own description always outranks it: help is the only text distinguishing one
choice from another, and a constant key hint that hides it costs more than it teaches.
"""

CANCEL_HINT = "press escape again to discard every answer and quit"
"""Shown by the first escape; a second one within the arming window quits."""

CANCEL_WINDOW = 3.0
"""Seconds an armed escape stays armed. After that the safety goes back on by itself."""


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
        """Header, the scrolling form, the one reserved hint line, footer."""
        yield HeaderBar("survey")
        yield VerticalScroll(id="survey-form")
        yield self._hint
        yield Footer()

    def on_mount(self) -> None:
        """Build the rows and focus the first one."""
        self._refresh_rows()
        self.call_after_refresh(self._focus_first)

    def on_screen_resume(self) -> None:
        """Coming back from review: re-read the state, keeping scroll and focus as they were."""
        self._refresh_rows()

    def on_field_row_changed(self, message: FieldRow.Changed) -> None:
        """Push the new value into copier_ui and refresh every row from the new state."""
        message.stop()
        self._disarm()
        self.ui.set(message.field_id, message.value)
        self._refresh_rows()

    def on_descendant_focus(self) -> None:
        """The hint line and the header position follow the focus."""
        self._disarm()
        self._show_hint()
        self._show_position()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Give a key back to the control that owns it.

        Returning None greys the screen's binding for this key, which is what lets the key
        reach the focused control instead. Enter belongs to an open menu and to an editor;
        escape belongs to an open menu, which it closes; up and down belong to a cursor that
        still has somewhere to go, so a control hands the focus on at its own first and last
        line rather than trapping it.
        """
        key = _ACTION_KEY.get(action)
        if key is None:
            return True
        if key == "enter":
            return self._focused_owner(_ENTER_OWNERS) is None
        if key in ("up", "down"):
            owner = self._focused_owner(_ARROW_OWNERS)
            return True if owner is None else _at_edge(owner, key)
        if key == "escape":
            return None if self._open_menu() else True
        return True

    def _open_menu(self) -> bool:
        """True while a choice menu is showing: escape closes that before it arms a quit."""
        select = self._focused_owner((Select,))
        return isinstance(select, Select) and select.expanded

    def _focused_owner(self, types: tuple[type[Widget], ...]) -> Widget | None:
        """The focused control, or the control enclosing it, when it is one of these."""
        focused = self.focused
        if focused is None:
            return None
        if isinstance(focused, types):
            return focused
        return next((node for node in focused.ancestors if isinstance(node, types)), None)

    def action_confirm(self) -> None:
        """Advance to review, or point at the first field that is not ready."""
        errors = self.ui.validate()
        if errors:
            self._refresh_rows()
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

    def _refresh_rows(self) -> None:
        """Add, remove and update rows so they match the state's visible, non-preset fields."""
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
        for field_id in wanted:
            field = replace(state.fields[field_id], errors=tuple(errors.get(field_id, ())))
            row = rows.get(field_id)
            if row is None:
                row = FieldRow(schema.by_id(field_id), field)
                if previous is None:
                    form.mount(row, before=0)
                else:
                    form.mount(row, after=previous)
            else:
                row.update(field)
            previous = row
        self._show_hint()
        self._show_position()

    def _show_hint(self) -> None:
        """Write the focused field's problem, or its help, or how to open its list."""
        if self._armed:
            return
        row = self._focused_owner((FieldRow,))
        if not isinstance(row, FieldRow):
            self._hint.update(Text(""))
            return
        if row.field.errors:
            self._hint.update(Text(row.field.errors[0], style=ROSE))
            return
        if row.question.help:
            self._hint.update(Text(row.question.help, style=TEXT_MUTED))
            return
        if isinstance(self.focused, Select) and not self.focused.expanded:
            self._hint.update(Text(OPEN_HINT, style=TEXT_SUBTLE))
            return
        self._hint.update(Text(""))

    def _show_position(self) -> None:
        """The header says which field of how many, so the eye has an anchor while scrolling."""
        rows = list(self.query(FieldRow))
        row = self._focused_owner((FieldRow,))
        place = f"{rows.index(row) + 1} of {len(rows)}" if row in rows else f"{len(rows)} fields"
        self.query_one(HeaderBar).set_context(f"survey - {place}")

    def _focus_first(self) -> None:
        """Put the cursor in the first field."""
        rows = self.query(FieldRow)
        if rows:
            self._focus_field(rows.first(FieldRow).question.id)

    def _focus_field(self, field_id: str | None) -> None:
        """Scroll a field into view and focus its control."""
        if field_id is None:
            return
        try:
            control = self.query_one(f"#ctl-{field_id}")
        except NoMatches:
            return
        control.focus()
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
    if isinstance(owner, SelectionList):
        index = owner.highlighted
        if index is None:
            return True
        last = owner.option_count - 1
        return True if (index == 0 if key == "up" else index >= last) else None
    return None


def askable_ids(state: State) -> list[str]:
    """The visible fields the user is asked for: presets came in with --data."""
    return [field_id for field_id in state.visible_ids if not state.fields[field_id].preset]
