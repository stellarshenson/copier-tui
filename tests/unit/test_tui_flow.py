"""Survey to review to execution: what reaches the destination, and the exit code."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import copier
import pytest
from textual.containers import VerticalScroll
from textual.pilot import Pilot
from textual.widgets import ProgressBar, Static
from textual.widgets._progress_bar import Bar

from copier_tui.app import SurveyApp
from copier_tui.errors import EXIT_CANCELLED, EXIT_FAILURE, EXIT_OK
from copier_tui.screens import ExecutionScreen, ReviewScreen, SurveyScreen
from copier_tui.widgets import FieldRow
from copier_ui import TemplateUI

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
REFERENCE = Path("/home/lab/workspace/private/copier-data-science")


@asynccontextmanager
async def running(dst: Path, template: str = "tui_flow") -> AsyncIterator[tuple[SurveyApp, Pilot]]:
    """A running app over a fixture template, paused on its first screen."""
    with TemplateUI.from_template(str(FIXTURES / template), dst=dst) as ui:
        app = SurveyApp(ui, dst, {"quiet": True, "unsafe": True})
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            yield app, pilot


async def wait_until(pilot: Pilot, done: Callable[[], bool], limit: int = 200) -> bool:
    """Pump the app until a condition holds, or give up."""
    for _ in range(limit):
        if done():
            return True
        await pilot.pause(0.05)
    return done()


async def test_nothing_is_written_before_the_review_is_confirmed(tmp_path: Path) -> None:
    """The review screen renders with the destination still untouched."""
    dst = tmp_path / "out"
    async with running(dst) as (app, pilot):
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ReviewScreen)
        assert not dst.exists()


async def test_the_review_lists_every_answer_and_masks_secrets(tmp_path: Path) -> None:
    """Every visible answer is on the confirmation screen; the secret is not."""
    dst = tmp_path / "out"
    async with running(dst) as (app, pilot):
        await pilot.press("enter")
        await pilot.pause()
        lines = app.screen.query(".review-answer")
        assert [line.id for line in lines] == ["review-name", "review-advanced", "review-token"]
        text = "\n".join(str(line.visual) for line in lines)
        assert "name" in text and "demo" in text
        assert "token" in text and "***" in text
        assert "s3cret" not in text


async def test_the_review_names_the_questions_not_the_variables(tmp_path: Path) -> None:
    """The last screen before anything is written reads as questions, like the survey.

    This is the moment of commitment, so it is the worst place to fall back to snake_case.
    """
    async with running(tmp_path / "out", template="tui_kinds") as (app, pilot):
        await pilot.press("enter")
        await pilot.pause()
        text = "\n".join(str(line.visual) for line in app.screen.query(".review-answer"))
        assert "Which flavour the build uses" in text
        assert "flavour  " not in text


async def test_going_back_from_the_review_returns_to_the_survey(tmp_path: Path) -> None:
    """The review's back key reopens the survey with the answers still in place."""
    dst = tmp_path / "out"
    async with running(dst) as (app, pilot):
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ReviewScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, SurveyScreen)
        assert not dst.exists()


async def test_cancelling_leaves_the_destination_untouched(tmp_path: Path) -> None:
    """Quitting before confirmation writes nothing and exits non-zero.

    Escape is a two-press confirm on the survey, so an accidental key cannot lose a survey.
    """
    dst = tmp_path / "out"
    async with running(dst) as (app, pilot):
        await pilot.press("escape")
        await pilot.pause()
        assert app.is_running
        await pilot.press("escape")
        assert await wait_until(pilot, lambda: not app.is_running)
        assert app.return_value == EXIT_CANCELLED
        assert not dst.exists()


async def test_a_confirmed_render_writes_the_project_and_exits_zero(tmp_path: Path) -> None:
    """Confirming runs copier on its own screen and reports success."""
    dst = tmp_path / "out"
    async with running(dst) as (app, pilot):
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ExecutionScreen)
        status = app.screen.query_one("#exec-status", Static)
        assert await wait_until(pilot, lambda: f"written to {dst}" in str(status.visual))
        assert (dst / "name.txt").read_text().strip() == "demo"
        shown = "\n".join(str(widget.visual) for widget in app.screen.query(Static))
        assert shown.count(str(dst)) == 1, "the destination belongs on the screen once"

        await pilot.press("space")
        assert await wait_until(pilot, lambda: not app.is_running)
        assert app.return_value == EXIT_OK


async def test_a_failed_render_shows_the_message_and_keeps_partial_output(
    tmp_path: Path,
) -> None:
    """copier's own failure reaches the execution screen; what it wrote stays put."""
    dst = tmp_path / "out"
    with TemplateUI.from_template(str(FIXTURES / "tui_flow"), dst=dst) as ui:

        def failing_render(target: Any = None, **copier_kwargs: Any) -> None:
            dst.mkdir(parents=True, exist_ok=True)
            (dst / "half-written.txt").write_text("partial\n")
            raise RuntimeError("copier gave up")

        ui.render = failing_render  # type: ignore[method-assign]
        app = SurveyApp(ui, dst, {})
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            status = app.screen.query_one("#exec-status", Static)
            assert await wait_until(pilot, lambda: "copier gave up" in str(status.visual))

            await pilot.press("space")
            assert await wait_until(pilot, lambda: not app.is_running)
            assert app.return_value == EXIT_FAILURE
            assert (dst / "half-written.txt").read_text() == "partial\n"


async def test_a_template_with_no_questions_goes_straight_to_review(tmp_path: Path) -> None:
    """Nothing to ask means no survey, and the render still completes."""
    dst = tmp_path / "out"
    async with running(dst, template="tui_empty") as (app, pilot):
        assert isinstance(app.screen, ReviewScreen)
        assert app.screen.query("#review-empty")

        await pilot.press("enter")
        await pilot.pause()
        verdict = app.screen.query_one("#exec-verdict", Static)
        assert await wait_until(pilot, lambda: str(verdict.visual).strip())
        await pilot.press("space")
        assert await wait_until(pilot, lambda: not app.is_running)
        assert app.return_value == EXIT_OK
        assert (dst / "README.md").exists()


async def test_a_non_empty_destination_warns_before_confirmation(tmp_path: Path) -> None:
    """The user is told the destination already holds files, and can still go back."""
    dst = tmp_path / "out"
    dst.mkdir()
    (dst / "mine.txt").write_text("keep me\n")
    async with running(dst) as (app, pilot):
        await pilot.press("enter")
        await pilot.pause()
        warning = app.screen.query_one("#review-warning", Static)
        assert "not empty" in str(warning.visual)

        await pilot.press("escape")
        assert await wait_until(pilot, lambda: isinstance(app.screen, SurveyScreen))
        assert (dst / "mine.txt").read_text() == "keep me\n"


async def test_recopy_opens_the_survey_seeded_from_the_answers_file(tmp_path: Path) -> None:
    """recopy reads .copier-answers.yml, so the survey opens on the previous answers."""
    dst = tmp_path / "proj"
    copier.run_copy(
        str(FIXTURES / "tui_flow"), dst, data={"name": "zed"}, defaults=True, quiet=True
    )
    with TemplateUI.from_template(None, dst=dst, operation="recopy") as ui:
        app = SurveyApp(ui, dst, {"quiet": True})
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            row = app.screen.query_one("#row-name", FieldRow)
            assert row.value == "zed"
            assert ui.state().fields["name"].is_default is False


@pytest.mark.skipif(not REFERENCE.is_dir(), reason="the reference template is not checked out")
async def test_an_unmodified_third_party_template_runs(tmp_path: Path) -> None:
    """A real template with conditional questions surveys and reviews with no changes to it."""
    dst = tmp_path / "demo-proj"
    with TemplateUI.from_template(str(REFERENCE), dst=dst, unsafe=True) as ui:
        app = SurveyApp(ui, dst, {"quiet": True, "unsafe": True})
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, SurveyScreen)
            assert len(app.screen.query(FieldRow)) == len(ui.state().visible_ids)

            ui.set("python_version_choice", "other")
            app.screen._refresh_rows()
            await pilot.pause()
            assert app.screen.query("#row-python_version_custom")

            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, ReviewScreen)
            assert not dst.exists()


@pytest.mark.skipif(not REFERENCE.is_dir(), reason="the reference template is not checked out")
async def test_review_and_back_keep_the_scroll_offset_and_the_focused_field(
    tmp_path: Path,
) -> None:
    """The headline round trip: go to review, come back, carry on where you were.

    Review is stacked over the survey rather than replacing it, so nothing is rebuilt. The
    check is deliberately made on a form taller than its viewport and on a field far enough
    down to have scrolled, because a rebuilt form would come back at offset zero.
    """
    dst = tmp_path / "demo-proj"
    with TemplateUI.from_template(str(REFERENCE), dst=dst, unsafe=True) as ui:
        app = SurveyApp(ui, dst, {"quiet": True, "unsafe": True})
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            survey = app.screen
            assert isinstance(survey, SurveyScreen)

            far = [row.question.id for row in survey.query(FieldRow)][-1]
            survey._focus_field(far)
            await pilot.pause()
            offset = survey.query_one("#survey-form", VerticalScroll).scroll_offset.y
            assert offset > 0, "the form did not scroll - the check would prove nothing"
            assert app.focused.id == f"ctl-{far}"

            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, ReviewScreen)

            await pilot.press("escape")
            await pilot.pause()
            assert app.screen is survey
            assert survey.query_one("#survey-form", VerticalScroll).scroll_offset.y == offset
            assert app.focused.id == f"ctl-{far}"


@pytest.mark.skipif(not REFERENCE.is_dir(), reason="the reference template is not checked out")
async def test_an_answer_changed_after_coming_back_still_recomputes(tmp_path: Path) -> None:
    """Coming back is not a read-only view - the form still recalculates the rest."""
    dst = tmp_path / "demo-proj"
    with TemplateUI.from_template(str(REFERENCE), dst=dst, unsafe=True) as ui:
        app = SurveyApp(ui, dst, {"quiet": True, "unsafe": True})
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            survey = app.screen
            assert not survey.query("#row-python_version_custom")

            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, ReviewScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert app.screen is survey

            ui.set("python_version_choice", "other")
            survey._refresh_rows()
            await pilot.pause()
            assert survey.query("#row-python_version_custom")

            await pilot.press("enter")
            await pilot.pause()
            assert app.screen.query("#review-python_version_custom")


async def test_a_dry_run_says_nothing_was_written(tmp_path: Path) -> None:
    """--pretend reports what copier would do, so the screen must not claim a render."""
    dst = tmp_path / "out"
    with TemplateUI.from_template(str(FIXTURES / "tui_flow"), dst=dst) as ui:
        app = SurveyApp(ui, dst, {"quiet": True, "pretend": True})
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("enter")
            status = app.screen.query_one("#exec-status", Static)
            assert await wait_until(pilot, lambda: "nothing written" in str(status.visual))
            assert not dst.exists()


async def test_the_progress_bar_takes_the_width_of_the_screen(tmp_path: Path) -> None:
    """Both the widget and the bar it draws stretch - either left alone renders a stub.

    ProgressBar defaults to `width: auto`, and the Bar inside it to a fixed 32 cells, so a
    rule on only one of the two still leaves a bar that does not reach the edge.
    """
    dst = tmp_path / "out"
    async with running(dst) as (app, pilot):
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        progress = app.screen.query_one("#exec-progress", ProgressBar)
        bar = progress.query_one(Bar)
        assert progress.size.width == app.screen.query_one("#exec-body").size.width
        assert bar.size.width >= progress.size.width - 1


async def focus_control(pilot: Pilot, app: SurveyApp, control_id: str, limit: int = 60) -> bool:
    """Walk the form downward with the arrow key until a control has the focus."""
    for _ in range(limit):
        if app.focused is not None and app.focused.id == control_id:
            return True
        await pilot.press("down")
        await pilot.pause()
    return app.focused is not None and app.focused.id == control_id


@pytest.mark.skipif(not REFERENCE.is_dir(), reason="the reference template is not checked out")
async def test_the_round_trip_runs_on_the_keyboard_alone(tmp_path: Path) -> None:
    """The headline requirement, driven the way a user drives it: keys only, no private calls.

    Walk down to a choice, open its list, pick the answer that reveals a conditional field,
    walk on to the bottom of a form taller than the viewport, go to review, come back. The
    revealed field, the scroll offset and the focused control all have to survive.
    """
    dst = tmp_path / "demo-proj"
    with TemplateUI.from_template(str(REFERENCE), dst=dst, unsafe=True) as ui:
        app = SurveyApp(ui, dst, {"quiet": True, "unsafe": True})
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            survey = app.screen
            assert isinstance(survey, SurveyScreen)
            assert not survey.query("#row-python_version_custom")

            assert await focus_control(pilot, app, "ctl-python_version_choice")
            await pilot.press("space")
            await pilot.pause()
            await pilot.press("end")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert ui.state().fields["python_version_choice"].value == "other"
            assert survey.query("#row-python_version_custom")

            last = [row.question.id for row in survey.query(FieldRow)][-1]
            assert await focus_control(pilot, app, f"ctl-{last}")
            form = survey.query_one("#survey-form", VerticalScroll)
            offset = form.scroll_offset.y
            assert offset > 0, "the form did not scroll - the check would prove nothing"

            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, ReviewScreen)
            assert app.screen.query("#review-python_version_custom")
            assert not dst.exists()

            await pilot.press("escape")
            await pilot.pause()
            assert app.screen is survey
            assert form.scroll_offset.y == offset
            assert app.focused.id == f"ctl-{last}"
