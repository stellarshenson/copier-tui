"""The Textual application and the survey entry point."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, ClassVar

from rich.text import Text
from textual.app import App, SystemCommand
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Static

from copier_tui.errors import EXIT_CANCELLED, EXIT_FAILURE, EXIT_OK
from copier_tui.screens import ExecutionScreen, ReviewScreen, SurveyScreen
from copier_tui.screens.survey import askable_ids
from copier_tui.theme import BASE_CSS, HEADER_CSS, MIN_HEIGHT, MIN_WIDTH
from copier_ui import TemplateUI


class SurveyApp(App[int]):
    """Drives survey, review and execution, and returns a process exit code."""

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
        """Push the survey screen, or the review screen when there is nothing to ask."""
        if self._has_questions():
            self._push(SurveyScreen(self.ui), self._after_survey)
        else:
            self._push(ReviewScreen(self.ui, self.dst), self._after_review)

    def on_resize(self) -> None:
        """Show the resize prompt below MIN_WIDTH or MIN_HEIGHT, hide it above."""
        self._check_size()

    def action_cancel(self) -> None:
        """Leave without writing anything."""
        self.exit(EXIT_CANCELLED)

    def _has_questions(self) -> bool:
        """True when at least one field is visible and not already answered by --data."""
        return bool(askable_ids(self.ui.state()))

    def _push(self, screen: Screen[bool], callback: Callable[[bool | None], None]) -> None:
        """Push a screen and re-check the terminal size once it has laid out."""
        self.push_screen(screen, callback)
        self.call_after_refresh(self._check_size)

    def _after_survey(self, advance: bool | None) -> None:
        """Survey confirmed goes to review; cancelled ends the run."""
        if advance:
            self._push(ReviewScreen(self.ui, self.dst), self._after_review)
        else:
            self.exit(EXIT_CANCELLED)

    def _after_review(self, confirmed: bool | None) -> None:
        """Review confirmed starts the render; back returns to the survey."""
        if confirmed:
            self._push(
                ExecutionScreen(self.ui, self.dst, self.copier_kwargs), self._after_execution
            )
        elif self._has_questions():
            self._push(SurveyScreen(self.ui), self._after_survey)
        else:
            self.exit(EXIT_CANCELLED)

    def _after_execution(self, ok: bool | None) -> None:
        """The render's verdict is the process exit code."""
        self.exit(EXIT_OK if ok else EXIT_FAILURE)

    def _check_size(self) -> None:
        """Mount or drop the resize prompt on the screen currently on top."""
        prompt = self.screen.query("#resize-prompt")
        if self.size.width < MIN_WIDTH or self.size.height < MIN_HEIGHT:
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
