"""The survey screen: every visible question as one compact scrolling form."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import ClassVar

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.css.query import NoMatches
from textual.message import Message
from textual.screen import Screen
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Footer, Static, TextArea

from copier_tui.paths import fit_path, project_name, shown_path
from copier_tui.theme import ROSE, TEXT_MUTED, TEXT_SUBTLE
from copier_tui.widgets import BRANCH_LAST, BRANCH_MORE, HEADER_PATH_FLOOR, FieldRow, HeaderBar
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

CANCEL_HINT = "press escape again to discard every answer and quit"
"""Shown by the first escape; a second one within the arming window quits."""

_WHERE_CHROME = len("destination: ")
"""What the destination line spends on things that are not the path: the word that
introduces it. Padding is not counted - `size` is the content box and has it off already."""

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
    #survey-status {{
        height: 1;
        width: 100%;
    }}
    #survey-hint {{
        /* as wide as what it says and no wider, so an empty hint leaves the whole row
           to the destination beside it */
        width: auto;
        padding: 0 1;
        color: {TEXT_MUTED};
        /* the third of the three one-row lines, and the last to get the rule. Wrapping, its
           second line was clipped, so at 60 columns the cancel warning read `press escape
           again to` - the app's only destructive keystroke, announced half-said. */
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }}
    #survey-where {{
        /* the rest of the row after the hint, not a fixed share: the hint is empty most of
           the time, and a fixed 60% left a path cropped beside a blank */
        width: 1fr;
        height: 1;
        padding: 0 1;
        color: {TEXT_SUBTLE};
        text-align: right;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }}
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("enter", "confirm", "Review", priority=True),
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("down", "focus_next", "Next field", show=False, priority=True),
        Binding("up", "focus_previous", "Previous field", show=False, priority=True),
        # priority: Textual's Input and TextArea bind ctrl+x to `cut` and a focused widget's
        # binding beats the screen's. Full reason in SurveyApp.BINDINGS.
        Binding("ctrl+x", "app.quit_now", "Quit", priority=True),
    ]

    def __init__(self, ui: TemplateUI, dst: Path) -> None:
        """Hold the template UI the rows are built from, and where the answers will land."""
        super().__init__(id="survey-screen")
        self.ui = ui
        self.dst = dst
        self._hint = Static(id="survey-hint")
        self._armed = False
        # the message a refused enter leaves, held rather than merely flagged. It has to
        # survive the focus move `action_confirm` makes right after writing it, or pressing
        # enter with the cursor anywhere but the bad row says nothing at all. Holding a flag
        # instead was worse than not holding it: the arming warning overwrote the message and
        # the flag then vetoed its own removal, so the line kept saying a second escape would
        # discard everything long after that had stopped being true, and the reason enter was
        # refused was gone for good
        self._blocked: Text | None = None
        # fields the reader has actually touched. A survey validates on mount, so every
        # required-but-unanswered question carries an error before a single keystroke - and
        # printing those spelled the opening frame out in red about questions nobody had been
        # asked yet, then moved every row below the cursor as the first character went in.
        # The `!` flag still marks them; the sentence waits until the reader has engaged
        self._touched: set[str] = set()
        # errors already on the form, so a new one can be told from a standing one. An answer
        # invalidated by a change to a DIFFERENT answer is news the reader caused, and it
        # speaks even though its own row was never touched - which is not true of the errors
        # that were there before anything was typed
        self._flagged: set[str] = set()
        # ids already on the form, so a question that has only just appeared can be told from
        # one that was there and has gone wrong
        self._shown: set[str] = set()
        # whether the count is being kept. It starts at a refusal and follows the errors down
        # to nothing, rather than freezing at the number they were when enter was pressed
        self._counting = False
        self._cancel_timer: Timer | None = None
        self._focused_last: Widget | None = None

    def compose(self) -> ComposeResult:
        """Header, the scrolling form, the status line, footer."""
        yield HeaderBar(f"{self.ui.template_name} questionnaire", project=project_name(self.dst))
        yield _Form(id="survey-form")
        # the destination shares the status line rather than sitting in the header, which is
        # already carrying the template name and the field position - and it is the one fact a
        # person filling in thirty answers cannot recover from anything else on the screen
        yield Horizontal(
            self._hint,
            _Destination(_where_text(self.dst, 0), id="survey-where"),
            id="survey-status",
        )
        yield Footer()

    async def on_mount(self) -> None:
        """Build the rows and focus the first one, once it has a control to focus.

        The mounts are awaited because a row composes its control a beat after it mounts
        itself: focusing before that finds the row and not the widget inside it, which
        `_focus_field` reads as a missing field, and the form opens with nothing focused.
        """
        await self._refresh_rows()
        self._focus_first()

    def on_resize(self) -> None:
        """Re-fit the destination line to the room the row actually leaves it.

        It used to crop to a constant, and the stylesheet's own ellipsis then finished the job
        from the right - taking the project name, which is the half the left-crop exists to
        protect. The constant was also wrong: `max-width: 60%` at MIN_WIDTH leaves 34 columns,
        not the 56 it was set to, so the CSS won at every width a person actually uses.
        """
        self.fit_destination()

    def fit_destination(self) -> None:
        """Crop the destination to the box it has right now - re-run whenever that box moves."""
        where = self.query_one("#survey-where", Static)
        room = where.size.width - _WHERE_CHROME
        where.update(_where_text(self.dst, max(room, HEADER_PATH_FLOOR)))

    async def on_screen_resume(self) -> None:
        """Coming back from review: re-read the state, keeping scroll and focus as they were."""
        await self._refresh_rows()
        # an escape pressed before leaving must not still be armed on the way back. No focus
        # event fires when the review screen is popped - the field that had the cursor still
        # has it - so nothing else disarms, and a single escape on return discarded the whole
        # survey. Four presses inside the three-second window, which is not a long reach
        self._disarm()

    async def on_field_row_changed(self, message: FieldRow.Changed) -> None:
        """Push the new value into copier_ui and refresh every row from the new state."""
        message.stop()
        self._touched.add(message.field_id)
        self._blocked = None
        self._disarm()
        self.ui.set(message.field_id, message.value)
        await self._refresh_rows()

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        """The header position follows the focus, and the status line goes quiet again.

        Only a focus that actually moved disarms the cancel. A terminal reports its window
        losing and regaining focus, Textual puts the cursor back on the field that already
        had it, and that arrives here as a descendant focus like any other. Disarming on it
        threw the first escape of a two-press cancel away, so the second press only armed it
        again - the warning appeared, nothing else happened, and three seconds later the
        warning went. Which is the report: a red message and a screen that ignored the keys.
        """
        if event.widget is not self._focused_last:
            # arriving on a row does not promote it. It did, but nothing re-rendered on a
            # focus, so the sentence appeared on the next unrelated keystroke and moved the
            # form under a cursor that was somewhere else by then. A row speaks once it is
            # edited, or once enter is refused
            self._focused_last = event.widget
            self._disarm()
        self._clear_hint()
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
            # enter was the one action key that did not disarm, and the branch it lands in
            # overwrites the arming warning with a validation message - so the safety's whole
            # visible state vanished while the safety stayed on. The next escape, which is the
            # gesture for dismissing a message, discarded every answer instead.
            self._disarm()
            field_id = next(iter(errors))
            # held before the rows are rebuilt, because it is what tells them they may speak:
            # a refusal is the reader engaging with every question at once, so from here the
            # rows explain themselves rather than only flagging
            # a count, not the sentence. Each row now prints its own reason in full, so
            # repeating the first one here put the same words on screen twice, rose both
            # times, and the shared copy is the one that gets cropped. The count is the fact
            # no row can state - and it ends the one-at-a-time treadmill where a reader fixes
            # a field, presses enter, and is handed the next of an unknown number
            left = len(errors)
            answers = "answer needs" if left == 1 else "answers need"
            self._touched |= set(errors)
            self._counting = True
            self._blocked = Text(f"{left} {answers} attention", style=ROSE)
            await self._refresh_rows()
            self._focus_field(field_id)
            self._hint.update(self._blocked)
            return
        self.post_message(self.Confirmed())

    def action_focus_next(self) -> None:
        """Move to the next field, and stay on the last one."""
        self._step_focus(1)

    def action_focus_previous(self) -> None:
        """Move to the previous field, and stay on the first one."""
        self._step_focus(-1)

    def _step_focus(self, step: int) -> None:
        """Move one field along the focus chain, stopping at either end.

        Textual's own `focus_next` and `focus_previous` roll round, so the last field handed
        the cursor back to the first and the form read as though it had jumped somewhere
        rather than ended. A form that stops where it stops is one an arrow can be held down
        on, and the ends are where the eye expects to be told there is no more.
        """
        chain = self.focus_chain
        if self.focused is None or self.focused not in chain:
            return
        # the arrow disarms whether or not it had anywhere to go. Disarming used to be a side
        # effect of the focus moving, which held only while the ends wrapped round: once they
        # stopped, `down` on the last field moved nothing, raised no focus event and left the
        # cancel armed - so escape, a dead arrow, escape discarded the survey, at exactly the
        # place a held arrow key comes to rest. A key the user pressed is a key the user
        # pressed; what the focus did with it is not the question the safety is asking.
        self._disarm()
        self._blocked = None
        target = chain.index(self.focused) + step
        if 0 <= target < len(chain):
            self.set_focus(chain[target])

    def action_cancel(self) -> None:
        """Arm on the first escape, quit on the second - a survey is too costly to lose."""
        if self._armed:
            self.post_message(self.Cancelled())
            return
        self._armed = True
        # the warning takes the whole row. It shares the line with the destination, which
        # claims up to 60 percent of it, so at 60 columns the sentence was ellipsised to
        # `press escape again to` - the reader told to press a key again and not told that it
        # throws away every answer. The destination is on the review screen and in the header;
        # this sentence has nowhere else to be, and it is up for three seconds
        self.query_one("#survey-where", Static).display = False
        self._hint.update(Text(CANCEL_HINT, style=ROSE))
        # the previous timer is stopped, not left to run. Each arming used to start a fresh
        # one and keep no handle, so an earlier timer fired inside a later arming's window and
        # disarmed it - the reader saw the warning, pressed escape well within the three
        # seconds it advertises, and nothing happened. It fails safe, which is why it survived
        self._stop_cancel_timer()
        self._cancel_timer = self.set_timer(CANCEL_WINDOW, self._disarm)

    def _stop_cancel_timer(self) -> None:
        """Drop the pending window, so no earlier one can fire inside a later one."""
        if self._cancel_timer is not None:
            self._cancel_timer.stop()
            self._cancel_timer = None

    def _disarm(self) -> None:
        """Put the safety back on: an armed escape never stands past its window."""
        if not self._armed:
            return
        self._armed = False
        self._stop_cancel_timer()
        self.query_one("#survey-where", Static).display = True
        self._clear_hint()

    async def _refresh_rows(self) -> None:
        """Add, remove and update rows so they match the state's visible, non-preset fields.

        Mounting is awaited so a caller may act on the controls straight afterwards.
        """
        state = self.ui.state()
        schema = self.ui.schema()
        errors = self.ui.validate()
        wanted = askable_ids(state)
        # an answer invalidated by a change to a DIFFERENT answer speaks, because that is
        # news the reader caused - but a question that has only just appeared because of a
        # `when` has not been asked yet, and is exactly what the gate is for. On the first
        # pass this is empty on its own: every error belongs to a visible question, and every
        # visible question is new, so the two subtractions cancel
        self._touched |= set(errors) - self._flagged - (set(wanted) - self._shown)
        self._flagged = set(errors)
        self._shown = set(wanted)
        if self._counting:
            self._counting = bool(errors)
            answers = "answer needs" if len(errors) == 1 else "answers need"
            self._blocked = (
                Text(f"{len(errors)} {answers} attention", style=ROSE) if errors else None
            )
        form = self.query_one("#survey-form", VerticalScroll)
        rows = {row.question.id: row for row in form.query(FieldRow)}
        for field_id, row in rows.items():
            if field_id not in wanted:
                row.remove()
        previous: FieldRow | None = None
        for position, field_id in enumerate(wanted):
            field = replace(state.fields[field_id], errors=tuple(errors.get(field_id, ())))
            spoken = field_id in self._touched
            row = rows.get(field_id)
            if row is None:
                row = FieldRow(schema.by_id(field_id), field, spoken=spoken)
                if previous is None:
                    await form.mount(row, before=0)
                else:
                    await form.mount(row, after=previous)
            else:
                # monotone: a row that has explained itself keeps explaining. Recomputed
                # from scratch each refresh, it went mute on the next keystroke - so pressing
                # enter to learn what was wrong and then typing at the first field erased the
                # whole list, with the other answers still failing
                row.spoken = row.spoken or spoken
                row.update(field)
            # banding is by position in the form as it now stands, not by the order rows
            # were built in: a conditional question appearing or disappearing restripes
            # everything below it, and a form that keeps the old parity reads as though two
            # adjacent questions were one
            row.set_class(position % 2 == 1, "row-alt")
            # a question another answer decides whether to ask leans its ground green and
            # indents its caption: `condition_ids` is what its `when` reads, so the renderer
            # never has to know what the rule says to know there is one
            row.set_class(bool(row.question.condition_ids), "row-cond")
            row.set_branch(*_branch(self.ui, wanted, position))
            previous = row
        self._clear_hint()
        self._show_position()

    def _clear_hint(self) -> None:
        """Empty the line the arming warning and the validation message are printed on.

        It carried a legend of every key that moves or changes something. The footer names
        those keys already, the focused row prints its own help under itself, and a line that
        never changes is one more thing between the reader and the questions - so the row is
        kept, at its one line, and stays blank until there is something to say on it.
        """
        if self._armed:
            return
        # back to the refusal if one still stands, not to blank. The cancel warning borrows
        # this line for three seconds and has to give it back to whatever it interrupted
        self._hint.update(self._blocked or Text(""))

    def _show_position(self) -> None:
        """The header names the template and says which field of how many.

        Which template is being filled in is the one thing a questionnaire cannot be read off
        its own questions, and it is what a person needs when several are open at once.
        """
        rows = list(self.query(FieldRow))
        row = self._focused_owner((FieldRow,))
        place = f"{rows.index(row) + 1} of {len(rows)}" if row in rows else f"{len(rows)} fields"
        # the position first: the title crops from the right, and at 60 to 66 columns the tail
        # was the counter - the one thing on the line the reader cannot infer
        self.query_one(HeaderBar).set_context(f"{place} ⸱ {self.ui.template_name} questionnaire")

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

    None keeps the key inside the control. This is what stops a multi-line editor from
    swallowing the arrow that was meant to walk the form. The editor is the only control that
    claims them: an option list was given them too, and that made `down` - the form's own key -
    commit a different answer on every stacked row it passed.
    """
    row = owner.cursor_location[0]
    last = owner.document.line_count - 1
    return True if (row == 0 if key == "up" else row >= last) else None


class _Destination(Static):
    """The destination line, which re-fits its path whenever its own box changes size.

    The box is the rest of the row after the hint, so it moves when a hint appears or
    goes - not only when the terminal does - and the screen's own resize never sees that.
    """

    def on_resize(self) -> None:
        """Ask the screen to crop the path to the new width."""
        screen = self.screen
        if isinstance(screen, SurveyScreen):
            screen.fit_destination()


def _where_text(dst: Path, room: int) -> Text:
    """Where the answers will be written, cropped from the left to the room it has.

    A room of zero means the row has not been laid out yet - the first paint, before any
    resize - and the path goes out whole for the stylesheet to crop until `on_resize` arrives.
    """
    if room <= 0:
        return Text(f"destination: {shown_path(dst)}", style=TEXT_SUBTLE)
    return Text(f"destination: {fit_path(dst, room)}", style=TEXT_SUBTLE)


def _branch(ui: TemplateUI, order: list[str], position: int) -> tuple[str, bool]:
    """The connector the row prints, and whether a sibling sits directly above it.

    `condition_ids` is what a question's `when` reads, so the renderer never has to know what
    the rule says to know there is one, or which answer it hangs from.
    """
    schema = ui.schema()
    parents = schema.by_id(order[position]).condition_ids
    if not parents or not any(parent in order for parent in parents):
        # an answer supplied with --data is never asked for, so its children would otherwise
        # hang off a row that is not on the form
        return "", False

    def shares(index: int) -> bool:
        return 0 <= index < len(order) and schema.by_id(order[index]).condition_ids == parents

    return (BRANCH_MORE if shares(position + 1) else BRANCH_LAST), shares(position - 1)


def askable_ids(state: State) -> list[str]:
    """The visible fields the user is asked for: presets came in with --data."""
    return [field_id for field_id in state.visible_ids if not state.fields[field_id].preset]
