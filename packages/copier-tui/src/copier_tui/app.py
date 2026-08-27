"""The Textual application and the survey entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from rich.text import Text
from textual import events
from textual.app import App
from textual.binding import Binding
from textual.geometry import Size
from textual.screen import Screen
from textual.widgets import Footer, Static

from copier_tui.errors import EXIT_CANCELLED, EXIT_FAILURE, EXIT_OK
from copier_tui.paths import shown_path
from copier_tui.screens import ExecutionScreen, ReviewScreen, SurveyScreen
from copier_tui.screens.survey import askable_ids
from copier_tui.theme import (
    AMBER,
    BASE_CSS,
    HEADER_CSS,
    MIN_HEIGHT,
    MIN_WIDTH,
    THEME,
)
from copier_ui import TemplateUI


class SurveyApp(App[int]):
    """Drives survey, review and execution, and returns a process exit code.

    Review is pushed on top of the survey rather than replacing it, so coming back finds
    the form exactly as it was left - same scroll offset, same focused field - while every
    row re-reads the state on resume and shows whatever the new answers recomputed.
    """

    CSS = HEADER_CSS + BASE_CSS
    TITLE = "copier-tui"
    # no command palette. It offers a survey nothing it cannot already do with a named key,
    # and it opens a panel over the questions, which is the one thing this form does not do
    ENABLE_COMMAND_PALETTE = False

    BINDINGS: ClassVar[list[Binding]] = [
        # ctrl+c is deliberately not bound. It is what a terminal copies with, and Textual
        # hands it to a focused input as copy of its own; claiming it here quit the survey
        # mid-answer instead.
        Binding("ctrl+c", "nothing", show=False, system=True),
        # ctrl+x is the way out that cannot be misread. Escape is one ambiguous byte - the
        # terminal sends the same 0x1b to start every sequence it has - so a second escape
        # arriving behind something else is read as that thing's introducer and never reaches
        # the survey. ctrl+x is 0x18, which introduces nothing, so it lands whatever else the
        # terminal is saying at the time.
        #
        # It is bound by each screen rather than here, and its action is named apart from the
        # survey's own `cancel`. Both follow from the same rule: the footer keeps one entry per
        # action, and merges an App-level entry wherever the focused widget's bindings leave
        # room. Sharing `cancel` silently dropped escape's entry; binding it here reordered the
        # whole key list on every arrow press, four different orders across twelve fields.
        #
        # Each screen's copy carries `priority=True` and the action `app.quit_now`, and both
        # are load-bearing. Textual's own Input and TextArea bind ctrl+x to `cut`, and a
        # focused widget's binding beats the screen's - without priority the advertised quit
        # key silently became the editor's cut on five rows in six. And a screen binding's
        # action is looked up on the screen first: unqualified, the key bound, matched, and
        # quietly did nothing at all.
    ]

    def __init__(self, ui: TemplateUI, dst: Path, copier_kwargs: dict[str, Any]) -> None:
        """Hold the loaded template UI, the destination and copier's own flags."""
        super().__init__()
        self.ui = ui
        self.dst = dst
        self.copier_kwargs = copier_kwargs

    def on_mount(self) -> None:
        """Register the palette, then open the survey - or review when nothing is asked."""
        self.register_theme(THEME)
        self.theme = THEME.name
        if self._has_questions():
            self._push(SurveyScreen(self.ui, self.dst))
        else:
            self._open_review()

    def on_resize(self, event: events.Resize) -> None:
        """Show the resize prompt below MIN_WIDTH or MIN_HEIGHT, hide it above.

        The event carries the new size; App.size still reports the old one here.
        """
        self._check_size(event.size)

    def on_survey_screen_confirmed(self, message: SurveyScreen.Confirmed) -> None:
        """The survey is ready: stack review on top of it, leaving the form untouched."""
        message.stop()
        self._open_review()

    def on_survey_screen_cancelled(self, message: SurveyScreen.Cancelled) -> None:
        """The survey was abandoned: leave without writing anything."""
        message.stop()
        self.exit(EXIT_CANCELLED)

    async def action_quit(self) -> None:
        """Textual's own quit key, routed to ours.

        ctrl+q is bound by Textual on every screen at priority, and its `action_quit` waits on
        the worker pool - where the render is a thread blocked in `subprocess.run` that will
        never be joined. Pressed during a render it hung the app, and hung it past rescue,
        because the shutdown it had already begun swallowed the ctrl+x that would have ended
        the children. The action is overridden rather than the key rebound: a second binding
        on the same action would take the screens' own entry out of the footer, which is what
        the footer does with two bindings that share an action name.
        """
        self.action_quit_now()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Stand the quit keys down on a finished render, which any key already closes.

        Returning None takes the binding out of the running, so the key carries on to the
        screen and reaches `ExecutionScreen.on_key` like every other key. Calling that screen's
        own `action_close` from here instead is what the first attempt did, and it hung the
        app: `dismiss` awaits the screen coming off the stack, and it was being called from
        inside the App's action dispatch, which is what has to return before that can happen.
        Both advertised quit keys sat dead on the one screen they were added to rescue, while
        a plain letter closed it correctly - the handler that already existed.
        """
        if action in ("quit_now", "quit"):
            screen = self.screen
            if isinstance(screen, ExecutionScreen) and screen.finished:
                return None
        return True

    def action_quit_now(self) -> None:
        """Leave a run that has no verdict, ending whatever it started on the way out.

        Only an unfinished render reaches this: a finished one is handed back to the screen by
        `check_action` above. An abandoned render leaves as a failure rather than a cancel,
        because a cancel is the promise that nothing was written, and by this point copier has
        been writing into the destination for as long as the run lasted. copier clears up after
        itself only when it created the destination, which is never the case for `update` or
        `recopy` - the two subcommands whose destination is the user's own live project.
        """
        screen = self.screen
        if isinstance(screen, ExecutionScreen):
            screen.abandon()
            # said here rather than by the CLI, which sees only an exit code and cannot tell an
            # abandoned render from a template that failed on its own. Leaving it unsaid was
            # worse than the wrong word: the run stopped halfway through writing and the user
            # was told nothing at all, on a destination that may be their own live project
            left = (
                f"{shown_path(self.dst)} was partly written"
                if screen.leaves_files_behind
                else f"nothing was left in {shown_path(self.dst)}"
            )
            self.exit(EXIT_FAILURE, message=Text(f"abandoned mid-render - {left}", style=AMBER))
            return
        self.exit(EXIT_CANCELLED)

    def action_nothing(self) -> None:
        """Absorb a key the app has no business acting on, so the terminal keeps it."""

    def _has_questions(self) -> bool:
        """True when at least one field is visible and not already answered by --data."""
        return bool(askable_ids(self.ui.state()))

    def _push(self, screen: Screen[Any], callback: Any = None) -> None:
        """Push a screen and re-check the terminal size once it has laid out."""
        self.push_screen(screen, callback)
        self.call_after_refresh(self._check_size)

    def _open_review(self) -> None:
        """Stack the review screen over whatever is showing."""
        self._push(ReviewScreen(self.ui, self.dst), self._after_review)

    def _after_review(self, confirmed: bool | None) -> None:
        """Review confirmed starts the render; back just uncovers the survey again."""
        if confirmed:
            self._push(
                ExecutionScreen(self.ui, self.dst, self.copier_kwargs), self._after_execution
            )
        elif not self._has_questions():
            self.exit(EXIT_CANCELLED)
        else:
            self.call_after_refresh(self._check_size)

    def _after_execution(self, ok: bool | None) -> None:
        """The render's verdict is the process exit code."""
        self.exit(EXIT_OK if ok else EXIT_FAILURE)

    def _check_size(self, size: Size | None = None) -> None:
        """Mount or drop the resize prompt on the screen currently on top."""
        size = self.size if size is None else size
        prompt = self.screen.query("#resize-prompt")
        if size.width < MIN_WIDTH or size.height < MIN_HEIGHT:
            if not prompt:
                # mounted before the footer so it is a row of the layout, not a layer over it.
                # Docked or overlaid it painted over whichever row it landed on, and every
                # screen's bottom two rows are load-bearing: the footer names the keys, and
                # the row above carries the cancel warning on the survey and the overwrite
                # warning on the review. There is no free row to take, so it takes one from
                # the form - which is what an advisory is worth.
                footer = self.screen.query(Footer)
                self.screen.mount(
                    Static(
                        Text(f"resize to {MIN_WIDTH} x {MIN_HEIGHT}"),
                        id="resize-prompt",
                    ),
                    before=footer.first() if footer else None,
                )
        else:
            prompt.remove()


def run_survey(ui: TemplateUI, dst: Path, copier_kwargs: dict[str, Any]) -> int:
    """Run the app to completion and return its exit code.

    Mouse reporting is off. It went off chasing the two-press cancel, on a reading of the
    parser that turned out to be wrong - a terminal's report carries its own escape byte, so
    it never had a keystroke to eat, and the real fault was this end disarming itself. What
    is left is the reason to keep it off: the survey is driven from the keyboard throughout,
    a report per pointer twitch pays for nothing, and asking for none leaves the terminal its
    own selection and copy.
    """
    exit_code = SurveyApp(ui, dst, copier_kwargs).run(mouse=False)
    return EXIT_CANCELLED if exit_code is None else exit_code
