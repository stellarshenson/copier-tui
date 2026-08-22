"""The Textual application and the survey entry point."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, ClassVar

from rich.text import Text
from textual import events
from textual.app import App, SystemCommand
from textual.binding import Binding
from textual.geometry import Size
from textual.screen import Screen
from textual.widgets import Static

from copier_tui.errors import EXIT_CANCELLED, EXIT_FAILURE, EXIT_OK
from copier_tui.screens import ExecutionScreen, ReviewScreen, SurveyScreen
from copier_tui.screens.survey import askable_ids
from copier_tui.theme import BASE_CSS, HEADER_CSS, MIN_HEIGHT, MIN_WIDTH, THEME
from copier_ui import TemplateUI


class SurveyApp(App[int]):
    """Drives survey, review and execution, and returns a process exit code.

    Review is pushed on top of the survey rather than replacing it, so coming back finds
    the form exactly as it was left - same scroll offset, same focused field - while every
    row re-reads the state on resume and shows whatever the new answers recomputed.
    """

    CSS = HEADER_CSS + BASE_CSS
    TITLE = "copier-tui"

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+c", "cancel", "Cancel", priority=True, show=False),
    ]

    def __init__(self, ui: TemplateUI, dst: Path, copier_kwargs: dict[str, Any]) -> None:
        """Hold the loaded template UI, the destination and copier's own flags."""
        super().__init__()
        self.ui = ui
        self.dst = dst
        self.copier_kwargs = copier_kwargs

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        """copier-tui's palette is the brand; drop Textual's theme switcher."""
        for command in super().get_system_commands(screen):
            if command.title != "Change theme":
                yield command

    def on_mount(self) -> None:
        """Register the palette, then open the survey - or review when nothing is asked."""
        self.register_theme(THEME)
        self.theme = THEME.name
        if self._has_questions():
            self._push(SurveyScreen(self.ui))
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

    def action_cancel(self) -> None:
        """Leave without writing anything."""
        self.exit(EXIT_CANCELLED)

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
                self.screen.mount(
                    Static(
                        Text(f"terminal too small\nresize to {MIN_WIDTH} x {MIN_HEIGHT}"),
                        id="resize-prompt",
                    )
                )
        else:
            prompt.remove()


def run_survey(ui: TemplateUI, dst: Path, copier_kwargs: dict[str, Any]) -> int:
    """Run the app to completion and return its exit code."""
    exit_code = SurveyApp(ui, dst, copier_kwargs).run()
    return EXIT_CANCELLED if exit_code is None else exit_code
