"""The review screen: every answer, confirmed before anything is written."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Static

from copier_tui.theme import CYAN_BRIGHT, ROSE, TEXT_MUTED
from copier_tui.widgets import HeaderBar, display_value
from copier_ui import TemplateUI


class ReviewScreen(Screen[bool]):
    """Lists every answer and warns when the destination is not empty."""

    DEFAULT_CSS = f"""
    #review-list {{
        width: 100%;
        height: 1fr;
        padding: 1;
    }}
    #review-warning {{
        padding: 1;
        color: {ROSE};
    }}
    #review-empty {{
        color: {TEXT_MUTED};
    }}
    .review-answer {{
        height: auto;
    }}
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("enter", "confirm", "Create", priority=True),
        Binding("escape", "back", "Back", priority=True),
    ]

    def __init__(self, ui: TemplateUI, dst: Path) -> None:
        """Hold the template UI and the destination being reviewed."""
        super().__init__(id="review-screen")
        self.ui = ui
        self.dst = dst

    def compose(self) -> ComposeResult:
        """Header, the destination warning, one line per answer, footer."""
        yield HeaderBar(f"review · {self.dst}")
        if _is_not_empty(self.dst):
            yield Static(
                Text(f"{self.dst} already exists and is not empty - files may be overwritten"),
                id="review-warning",
            )
        yield VerticalScroll(*self._answer_lines(), id="review-list")
        yield Footer()

    def action_confirm(self) -> None:
        """Dismiss with True to start the render."""
        self.dismiss(True)

    def action_back(self) -> None:
        """Dismiss with False to return to the survey."""
        self.dismiss(False)

    def _answer_lines(self) -> list[Static]:
        """One static per visible answer, secrets masked."""
        state = self.ui.state()
        lines = []
        for field_id in state.visible_ids:
            text = Text(field_id, style=f"bold {CYAN_BRIGHT}")
            text.append("  =  ")
            text.append(display_value(state.fields[field_id]))
            lines.append(Static(text, classes="review-answer", id=f"review-{field_id}"))
        if not lines:
            lines.append(Static(Text("this template asks nothing"), id="review-empty"))
        return lines


def _is_not_empty(dst: Path) -> bool:
    """True when the destination directory already holds something."""
    return dst.is_dir() and any(dst.iterdir())
