"""The survey screen: every visible question as one scrolling form."""

from __future__ import annotations

from dataclasses import replace
from typing import ClassVar

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.screen import ModalScreen, Screen
from textual.widgets import Footer, OptionList, Static, TextArea
from textual.widgets.option_list import Option

from copier_tui.theme import CYAN_BRIGHT, SURFACE_BG, TEXT_MUTED
from copier_tui.widgets import FieldRow, HeaderBar, display_value
from copier_ui import Schema, State, TemplateUI


class SurveyScreen(Screen[bool]):
    """The whole visible survey, scrollable, navigable in any order."""

    DEFAULT_CSS = """
    #survey-form {
        width: 100%;
        height: 1fr;
        padding: 1 1 0 1;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("enter", "confirm", "Review", priority=True),
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("f2", "jump", "Overview"),
        Binding("down", "focus_next", "Next field", show=False),
        Binding("up", "focus_previous", "Previous field", show=False),
    ]

    def __init__(self, ui: TemplateUI) -> None:
        """Hold the template UI the rows are built from."""
        super().__init__(id="survey-screen")
        self.ui = ui
        self._warn = Static(id="warn-box")
        self._focus_before_warning: object = None

    def compose(self) -> ComposeResult:
        """Header, the scrolling form, the blocking warning popup, footer."""
        yield HeaderBar("survey")
        yield VerticalScroll(id="survey-form")
        yield self._warn
        yield Footer()

    def on_mount(self) -> None:
        """Build the rows and focus the first one."""
        self._refresh_rows()
        self.call_after_refresh(self._focus_first)

    def on_field_row_changed(self, message: FieldRow.Changed) -> None:
        """Push the new value into copier_ui and refresh every row from the new state."""
        message.stop()
        self.ui.set(message.field_id, message.value)
        self._refresh_rows()

    def on_key(self, event: events.Key) -> None:
        """Any key dismisses the blocking warning popup."""
        if self._warn.display:
            event.stop()
            self._dismiss_warning()

    def action_jump(self) -> None:
        """Open the overview and focus the chosen field."""
        if self._warn.display:
            self._dismiss_warning()
            return
        self.app.push_screen(JumpScreen(self.ui.schema(), self.ui.state()), self._focus_field)

    def action_confirm(self) -> None:
        """Dismiss with True to advance to the review screen."""
        focused = self.focused
        if isinstance(focused, TextArea):
            focused.insert("\n")
            return
        if self._warn.display:
            self._dismiss_warning()
            return
        errors = self.ui.validate()
        if errors:
            self._show_warning(errors)
            return
        self.dismiss(True)

    def action_cancel(self) -> None:
        """Dismiss with False, leaving the destination untouched."""
        if self._warn.display:
            self._dismiss_warning()
            return
        self.dismiss(False)

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

    def _show_warning(self, errors: dict[str, list[str]]) -> None:
        """Block the advance and name the fields that need attention."""
        names = ", ".join(errors)
        self._warn.update(Text(f"{len(errors)} field(s) need attention\n{names}"))
        self._warn.display = True
        self._focus_before_warning = self.focused
        self.set_focus(None)

    def _dismiss_warning(self) -> None:
        """Hide the popup and give focus back."""
        self._warn.display = False
        if self._focus_before_warning is not None:
            self.set_focus(self._focus_before_warning)
            self._focus_before_warning = None


class JumpScreen(ModalScreen[str | None]):
    """Overview of visible questions and their current values."""

    DEFAULT_CSS = f"""
    #jump-list {{
        width: 100%;
        height: 1fr;
    }}
    #jump-title {{
        padding: 1 1 0 1;
        color: {CYAN_BRIGHT};
    }}
    #jump-empty {{
        padding: 1;
        color: {TEXT_MUTED};
        background: {SURFACE_BG};
    }}
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "close", "Close", priority=True),
    ]

    def __init__(self, schema: Schema, state: State) -> None:
        """Hold the questions and the state the overview lists."""
        super().__init__(id="jump-screen")
        self.schema = schema
        self.state = state

    def compose(self) -> ComposeResult:
        """Header, one option per visible question, footer."""
        yield HeaderBar("overview")
        yield Static("jump to a question", id="jump-title")
        options = [
            Option(
                Text(f"{field_id}  =  {display_value(self.state.fields[field_id])}"),
                id=field_id,
            )
            for field_id in askable_ids(self.state)
        ]
        if options:
            yield OptionList(*options, id="jump-list")
        else:
            yield Static("no questions to jump to", id="jump-empty")
        yield Footer()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Return the chosen field id."""
        event.stop()
        self.dismiss(event.option.id)

    def action_close(self) -> None:
        """Return without choosing."""
        self.dismiss(None)


def askable_ids(state: State) -> list[str]:
    """The visible fields the user is asked for: presets came in with --data."""
    return [field_id for field_id in state.visible_ids if not state.fields[field_id].preset]
