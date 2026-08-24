"""The review screen: every answer, confirmed before anything is written."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Static

from copier_tui.theme import AMBER, CYAN_BRIGHT, LABEL_LINES, LABEL_WIDTH, TEXT, TEXT_SUBTLE
from copier_tui.widgets import HeaderBar, display_value
from copier_ui import TemplateUI

UNSET = "not set"
"""Stands in for an answer with no value, so a blank line is never mistaken for one."""


class ReviewScreen(Screen[bool]):
    """Lists every answer and warns when the destination is not empty."""

    DEFAULT_CSS = f"""
    #review-list {{
        width: 100%;
        height: 1fr;
        padding: 1 2 0 1;
        scrollbar-size-vertical: 1;
    }}
    #review-warning {{
        height: 1;
        width: 100%;
        padding: 0 1;
        color: {AMBER};
    }}
    .review-answer {{
        height: auto;
        width: 100%;
    }}
    .review-caption {{
        width: {LABEL_WIDTH};
        height: auto;
        max-height: {LABEL_LINES};
        padding: 0 2 0 1;
    }}
    .review-value {{
        width: 1fr;
        height: auto;
    }}
    #review-empty {{
        color: {TEXT_SUBTLE};
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
        """Header, one line per answer, the destination warning, footer."""
        yield HeaderBar(f"review · {self.dst}")
        yield VerticalScroll(*self._answer_lines(), id="review-list")
        yield Static(self._destination_note(), id="review-warning")
        yield Footer()

    def action_confirm(self) -> None:
        """Dismiss with True to start the render."""
        self.dismiss(True)

    def action_back(self) -> None:
        """Dismiss with False to return to the survey."""
        self.dismiss(False)

    def _destination_note(self) -> Text:
        """Warn when the destination already holds files the render could overwrite."""
        if _is_not_empty(self.dst):
            return Text(f"{self.dst} is not empty - existing files may be overwritten")
        return Text("")

    def _answer_lines(self) -> list[Static | Horizontal]:
        """One row per visible answer: the question whole, then what it will be answered with.

        This is the last screen before anything is written, so a caption cut here removes
        exactly the words someone is checking. Captions wrap instead, as they do in the form.
        """
        state = self.ui.state()
        lines: list[Static | Horizontal] = []
        for field_id in state.visible_ids:
            field = state.fields[field_id]
            value = display_value(field)
            lines.append(
                Horizontal(
                    Static(
                        Text(
                            self.ui.schema().by_id(field_id).label,
                            style=f"bold {CYAN_BRIGHT}",
                            overflow="fold",
                        ),
                        classes="review-caption",
                    ),
                    Static(
                        Text(value, style=TEXT, overflow="fold")
                        if value
                        else Text(UNSET, style=TEXT_SUBTLE),
                        classes="review-value",
                    ),
                    classes="review-answer",
                    id=f"review-{field_id}",
                )
            )
        if not lines:
            lines.append(Static(Text("this template asks nothing"), id="review-empty"))
        return lines


def _is_not_empty(dst: Path) -> bool:
    """True when the destination directory already holds something."""
    return dst.is_dir() and any(dst.iterdir())
