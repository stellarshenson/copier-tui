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

from copier_tui.paths import fit_path
from copier_tui.theme import (
    AMBER,
    CYAN_BRIGHT,
    LABEL_WIDTH,
    ROW_ALT_BG,
    ROW_BG,
    TEXT,
    TEXT_SUBTLE,
)
from copier_tui.widgets import HEADER_PATH_FLOOR, HeaderBar, display_value
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
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }}
    .review-answer {{
        height: auto;
        width: 100%;
        background: {ROW_BG};
    }}
    .review-answer.row-alt {{
        background: {ROW_ALT_BG};
    }}
    .review-caption {{
        /* a share of the row capped at the old fixed width, as the form's gutter is. Flat at
           56 this left the value column ONE column wide at MIN_WIDTH, so every answer stacked
           a character per row - `demo` as four rows - on the screen whose whole job is to be
           read before anything is written. */
        width: 60%;
        max-width: {LABEL_WIDTH};
        height: auto;
        /* no max-height. The survey caps a caption at three lines because thirty rows have to
           fit one screen; this screen has one job, which is to be read before anything is
           written, and a caption cut here removes exactly the words being checked. The row
           grows instead - which is what the compose docstring below has always claimed. */
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
        # priority: Textual's Input and TextArea bind ctrl+x to `cut` and a focused widget's
        # binding beats the screen's. Full reason in SurveyApp.BINDINGS.
        Binding("ctrl+x", "app.quit_now", "Quit", priority=True),
    ]

    def __init__(self, ui: TemplateUI, dst: Path) -> None:
        """Hold the template UI and the destination being reviewed."""
        super().__init__(id="review-screen")
        self.ui = ui
        self.dst = dst

    def compose(self) -> ComposeResult:
        """Header, one line per answer, the destination warning, footer."""
        # the path goes to the header whole; it crops it to the width the row actually has,
        # keeping the tail, because the project name is the half that identifies anything
        yield HeaderBar("review", self.dst)
        yield VerticalScroll(*self._answer_lines(), id="review-list")
        yield Static(self._destination_note(), id="review-warning")
        yield Footer()

    def action_confirm(self) -> None:
        """Dismiss with True to start the render."""
        self.dismiss(True)

    def action_back(self) -> None:
        """Dismiss with False to return to the survey."""
        self.dismiss(False)

    def on_resize(self) -> None:
        """Re-fit the warning's path to the room the row has, as the other lines do."""
        self.query_one("#review-warning", Static).update(self._destination_note())

    def _destination_note(self) -> Text:
        """Warn when the destination already holds files the render could overwrite."""
        if _is_not_empty(self.dst):
            # the risk goes first. This line is one row, and led by the path it wrapped, so
            # the clipped second line took the words - at 60 columns it read as an amber path
            # and nothing else, on the only element in the app that says an existing project
            # is about to be overwritten
            # cropped from the left like every other path on screen: the stylesheet's
            # ellipsis takes the tail, which is the name of the project being warned about
            room = self.size.width - len("existing files may be overwritten - ") - 2
            return Text(
                f"existing files may be overwritten - {fit_path(self.dst, max(room, HEADER_PATH_FLOOR))}"
            )
        return Text("")

    def _answer_lines(self) -> list[Static | Horizontal]:
        """One row per visible answer: the question whole, then what it will be answered with.

        This is the last screen before anything is written, so a caption cut here removes
        exactly the words someone is checking. Captions wrap instead, as they do in the form.
        """
        state = self.ui.state()
        lines: list[Static | Horizontal] = []
        for position, field_id in enumerate(state.visible_ids):
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
                    classes="review-answer row-alt" if position % 2 else "review-answer",
                    id=f"review-{field_id}",
                )
            )
        if not lines:
            lines.append(Static(Text("this template asks nothing"), id="review-empty"))
        return lines


def _is_not_empty(dst: Path) -> bool:
    """True when the destination directory already holds something."""
    return dst.is_dir() and any(dst.iterdir())
