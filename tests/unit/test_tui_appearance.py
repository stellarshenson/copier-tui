"""What the form looks like: row banding, field grounds, option chips, disabled rows.

These are the cues that tell a reader where one question ends and the next begins, which of
its options is the answer, and which rows the cursor may not edit. They are asserted here
rather than left to a screenshot because every one of them regressed silently at least once.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import Any

from copier_tui.app import SurveyApp
from copier_tui.inline import InlineOptions
from copier_tui.screens.execution import _detached_stdin
from copier_tui.theme import FIELD_ALT_BG, FIELD_BG, PICKED_BG, ROW_ALT_BG, ROW_BG
from copier_tui.widgets import FieldRow
from copier_ui import TemplateUI

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

BAND = "row-alt"
"""The class the survey puts on every second visible row."""


@asynccontextmanager
async def survey(
    dst: Path, template: str = "tui_flow", size: tuple[int, int] = (100, 40)
) -> AsyncIterator[tuple[SurveyApp, Any]]:
    """A running survey over a fixture template, paused on its first screen."""
    with TemplateUI.from_template(str(FIXTURES / template), dst=dst) as ui:
        app = SurveyApp(ui, dst, {"quiet": True, "unsafe": True})
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            yield app, pilot


def rows(app: SurveyApp) -> list[FieldRow]:
    """The mounted rows, in the order the form shows them."""
    return list(app.screen.query(FieldRow))


def banding(app: SurveyApp) -> list[bool]:
    """Whether each visible row wears the band, top to bottom."""
    return [BAND in row.classes for row in rows(app)]


async def test_the_form_alternates_a_band_down_the_rows(tmp_path: Path) -> None:
    """Row banding: every second question sits on the lighter of the two grounds.

    Thirty rows of caption-then-control at the same brightness give the eye nothing to count
    by, and a caption that wraps looks like the next question starting.
    """
    async with survey(tmp_path / "out") as (app, _):
        assert banding(app) == [False, True, False]


async def test_the_band_restripes_when_a_conditional_question_appears(tmp_path: Path) -> None:
    """Row banding: parity follows position in the form as it now stands, not build order.

    `detail` appears between `advanced` and `token`, so everything below it must flip. A row
    keeping the parity it was born with puts two same-coloured rows side by side, which reads
    as one question with a very long caption.
    """
    async with survey(tmp_path / "out") as (app, pilot):
        assert [row.question.id for row in rows(app)] == ["name", "advanced", "token"]
        assert banding(app) == [False, True, False]

        app.screen.set_focus(app.screen.query_one("#ctl-advanced", InlineOptions))
        await pilot.press("right")
        await pilot.pause()

        assert [row.question.id for row in rows(app)] == ["name", "advanced", "detail", "token"]
        assert banding(app) == [False, True, False, True]


async def test_a_typing_ground_carries_the_band_through_the_control(tmp_path: Path) -> None:
    """Field ground: a text box spans the row, so it takes the band or the stripe vanishes.

    Five consecutive text questions otherwise merge into one lit block - the same
    undifferentiated wall the banding exists to break up.
    """
    async with survey(tmp_path / "out") as (app, _):
        grounds = {
            row.question.id: row.query_one(f"#ctl-{row.question.id}").styles.background.hex6
            for row in rows(app)
            if row.question.id in {"name", "token"}
        }
        assert grounds["name"].lower() == FIELD_BG.lower()
        assert grounds["token"].lower() == FIELD_BG.lower()
        assert FIELD_ALT_BG != FIELD_BG
        assert ROW_ALT_BG != ROW_BG


async def test_an_option_row_takes_no_typing_ground(tmp_path: Path) -> None:
    """Field ground: only what can be typed into gets one.

    An option row says "pick me" with the chip under the answer; giving it a typing ground as
    well invites the reader to type into a widget that ignores every letter.
    """
    async with survey(tmp_path / "out") as (app, _):
        options = app.screen.query_one("#ctl-advanced", InlineOptions)
        assert options.styles.background.a == 0


async def test_the_answer_sits_on_a_chip_and_the_alternatives_do_not(tmp_path: Path) -> None:
    """Option chips: taken and passed-over differ by ground, not by which blue is brighter."""
    async with survey(tmp_path / "out") as (app, _):
        options = app.screen.query_one("#ctl-advanced", InlineOptions)
        # the painted strip, not the source Text: what a reader sees is the assertion
        grounds = {
            segment.text.strip(): segment.style.bgcolor.triplet.hex
            if segment.style and segment.style.bgcolor
            else None
            for segment in options.render_line(0)
            if segment.text.strip()
        }
        assert grounds["No"] == PICKED_BG
        assert grounds["Yes"] != PICKED_BG


async def test_a_row_the_answers_rule_out_is_marked_inert(tmp_path: Path) -> None:
    """Disabled rows: a question that cannot be edited says so, rather than only greying out.

    A live caption over a dead control read as a row that merely was not focused yet.
    """
    async with survey(tmp_path / "out", template="ui_exprerror") as (app, _):
        broken = {row.question.id: row for row in rows(app) if not row.field.enabled}
        assert broken, "the fixture is meant to leave at least one field disabled"
        for row in broken.values():
            assert "row-off" in row.classes
            assert row.query_one(f"#ctl-{row.question.id}").disabled


def test_the_render_runs_with_stdin_detached() -> None:
    """Exit: nothing copier starts inherits the keyboard the form is reading.

    A template's tasks are subprocesses holding this process's own descriptors, so under
    `--trust` a task that reads stdin eats the keystrokes meant for the app - after which
    "press any key to close" never fires again. Descriptor 0 is moved for the render and put
    back afterwards; 1 and 2 stay, because Textual paints the screen through 1.
    """
    before = os.fstat(0)
    with _detached_stdin():
        inside = os.stat(os.devnull)
        assert os.fstat(0).st_rdev == inside.st_rdev
    after = os.fstat(0)
    assert (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)
