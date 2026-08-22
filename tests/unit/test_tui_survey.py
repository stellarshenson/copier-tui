"""The survey screen driven through the Textual pilot: layout, navigation, keys, errors."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from textual.containers import VerticalScroll
from textual.widgets import Select, SelectionList, Static, TextArea
from textual.widgets._select import SelectCurrent

from copier_tui.app import SurveyApp
from copier_tui.screens import ReviewScreen, SurveyScreen
from copier_tui.screens import survey as survey_screen
from copier_tui.screens.survey import CANCEL_HINT, OPEN_HINT
from copier_tui.widgets import ChoiceSelect, FieldRow
from copier_ui import TemplateUI

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@asynccontextmanager
async def survey(
    dst: Path,
    template: str = "tui_flow",
    data: dict[str, Any] | None = None,
    size: tuple[int, int] = (100, 40),
) -> AsyncIterator[tuple[SurveyApp, Any]]:
    """A running survey over a fixture template, paused on its first screen."""
    with TemplateUI.from_template(str(FIXTURES / template), dst=dst, data=data) as ui:
        app = SurveyApp(ui, dst, {"quiet": True, "unsafe": True})
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            yield app, pilot


def row_ids(app: SurveyApp) -> list[str]:
    """The question ids the survey currently shows, in order."""
    return [row.question.id for row in app.screen.query(FieldRow)]


def hint(app: SurveyApp) -> str:
    """Whatever the one reserved hint line currently says."""
    return str(app.screen.query_one("#survey-hint", Static).visual)


async def test_only_visible_askable_questions_are_shown(tmp_path: Path) -> None:
    """A hidden question is neither displayed nor reachable by navigation."""
    async with survey(tmp_path / "out") as (app, _):
        assert isinstance(app.screen, SurveyScreen)
        assert row_ids(app) == ["name", "advanced", "token"]
        assert app.ui.state().fields["detail"].visible is False
        assert not app.screen.query("#ctl-detail")


async def test_a_plain_field_costs_exactly_one_row(tmp_path: Path) -> None:
    """Label, control and status glyph share one line, so a long survey stays short."""
    async with survey(tmp_path / "out", template="tui_kinds") as (app, _):
        for field_id in ("text", "where", "count", "ratio", "enabled", "flavour", "token"):
            row = app.screen.query_one(f"#row-{field_id}", FieldRow)
            assert row.size.height == 1, f"{field_id} is {row.size.height} rows tall"


async def test_the_whole_form_is_about_one_line_per_question(tmp_path: Path) -> None:
    """Eleven questions of every kind occupy under 14 lines, editors and lists included.

    virtual_size is no measure here - a VerticalScroll reports its viewport when the content
    is shorter than it. The bottom of the last row is where the form actually ends.
    """
    async with survey(tmp_path / "out", template="tui_kinds") as (app, _):
        rows = list(app.screen.query(FieldRow))
        form = app.screen.query_one("#survey-form", VerticalScroll)
        assert len(rows) == 11
        used = rows[-1].region.bottom - form.region.y
        assert used <= 14, f"eleven questions took {used} lines"


async def test_a_choice_control_shows_its_answer_not_its_prompt(tmp_path: Path) -> None:
    """The prompt stands in for an answer outside the choices - never for a real one.

    Select keeps its constructed value private until it mounts, so a row that writes the
    same value in first leaves the label unpainted and the control reads "select..." over
    an answer it is actually holding.
    """
    async with survey(tmp_path / "out", template="tui_kinds") as (app, _):
        select = app.screen.query_one("#ctl-flavour", ChoiceSelect)
        assert select.value is not Select.NULL
        assert str(select.query_one(SelectCurrent).label) == "a"


async def test_fields_open_on_their_default_and_say_so(tmp_path: Path) -> None:
    """The value is prefilled and one dim glyph marks it as an untouched default."""
    async with survey(tmp_path / "out") as (app, _):
        row = app.screen.query_one("#row-name", FieldRow)
        assert row.value == "demo"
        assert str(row.query_one("#flag-name", Static).visual) == "·"


async def test_changing_an_answer_reveals_a_dependent_field(tmp_path: Path) -> None:
    """Live revisibility: the visible set updates without restarting the survey."""
    async with survey(tmp_path / "out") as (app, pilot):
        screen = app.screen
        assert "detail" not in row_ids(app)
        app.screen.query_one("#ctl-advanced").focus()
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
        assert app.ui.state().fields["advanced"].value is True
        assert "detail" in row_ids(app)
        assert app.screen is screen


async def test_hiding_a_field_again_removes_its_row(tmp_path: Path) -> None:
    """The reverse direction: an answer that hides a field drops it from the survey."""
    async with survey(tmp_path / "out") as (app, pilot):
        app.screen.query_one("#ctl-advanced").focus()
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
        assert "detail" in row_ids(app)
        await pilot.press("space")
        await pilot.pause()
        assert "detail" not in row_ids(app)


async def test_back_and_forward_keep_the_answer(tmp_path: Path) -> None:
    """Moving away from an edited field and back leaves the answer in place."""
    async with survey(tmp_path / "out") as (app, pilot):
        app.screen.query_one("#ctl-name").focus()
        await pilot.pause()
        for _ in range(4):
            await pilot.press("backspace")
        await pilot.press(*"zed")
        await pilot.pause()
        assert app.ui.state().fields["name"].value == "zed"

        await pilot.press("down")
        await pilot.pause()
        assert app.focused.id == "ctl-advanced"

        await pilot.press("up")
        await pilot.pause()
        assert app.focused.id == "ctl-name"
        assert app.screen.query_one("#row-name", FieldRow).value == "zed"
        assert app.ui.state().fields["name"].value == "zed"


async def test_a_preset_answer_is_not_asked(tmp_path: Path) -> None:
    """A value given with --data is seeded and its question drops out of the survey."""
    async with survey(tmp_path / "out", data={"name": "seeded"}) as (app, _):
        assert "name" not in row_ids(app)
        assert app.ui.answers()["name"] == "seeded"


async def test_the_hint_line_carries_the_focused_field_s_help(tmp_path: Path) -> None:
    """Help costs no row of its own - the one reserved line follows the focus."""
    async with survey(tmp_path / "out", template="tui_kinds") as (app, pilot):
        app.screen.query_one("#ctl-flavour").focus()
        await pilot.pause()
        assert hint(app) == OPEN_HINT


async def test_an_invalid_field_blocks_finishing_but_not_navigation(tmp_path: Path) -> None:
    """The glyph marks the row, the hint names the problem, and enter goes back to it."""
    async with survey(tmp_path / "out") as (app, pilot):
        app.screen.query_one("#ctl-name").focus()
        await pilot.pause()
        for _ in range(4):
            await pilot.press("backspace")
        await pilot.pause()

        assert str(app.screen.query_one("#flag-name", Static).visual) == "!"
        assert "name is required" in hint(app)

        await pilot.press("down")
        await pilot.pause()
        assert app.focused.id == "ctl-advanced"

        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, SurveyScreen)
        assert app.focused.id == "ctl-name"
        assert "name is required" in hint(app)


async def test_enter_confirms_from_a_switch_too(tmp_path: Path) -> None:
    """Space already toggles a boolean, so enter stays the confirm key everywhere."""
    async with survey(tmp_path / "out") as (app, pilot):
        app.screen.query_one("#ctl-advanced").focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ReviewScreen)
        assert app.ui.state().fields["advanced"].value is False


async def test_a_question_that_failed_to_load_is_disabled_and_blocks(tmp_path: Path) -> None:
    """A load error shows as a disabled field carrying its message, and blocks the finish."""
    async with survey(tmp_path / "out", template="tui_broken") as (app, pilot):
        assert row_ids(app) == ["good", "bad"]
        assert app.screen.query_one("#ctl-bad").disabled is True

        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, SurveyScreen)
        assert "nonsense" in hint(app)


async def test_space_opens_a_menu_and_the_arrows_move_inside_it(tmp_path: Path) -> None:
    """A choice control owns space and, once open, the arrows and enter."""
    async with survey(tmp_path / "out", template="tui_kinds") as (app, pilot):
        select = app.screen.query_one("#ctl-flavour")
        select.focus()
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
        assert select.expanded is True

        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()
        assert select.expanded is False
        assert app.ui.state().fields["flavour"].value == "b"


async def test_enter_on_a_closed_menu_confirms_the_survey(tmp_path: Path) -> None:
    """Enter never re-opens a menu it just closed - from a collapsed choice it advances."""
    async with survey(tmp_path / "out", template="tui_kinds") as (app, pilot):
        select = app.screen.query_one("#ctl-flavour")
        select.focus()
        await pilot.pause()
        assert select.expanded is False

        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ReviewScreen)


async def test_an_editor_keeps_the_arrows_until_its_last_line(tmp_path: Path) -> None:
    """A cursor that still has somewhere to go keeps the key; at the edge it hands focus on."""
    async with survey(tmp_path / "out", template="tui_kinds") as (app, pilot):
        editor = app.screen.query_one("#ctl-config", TextArea)
        editor.focus()
        editor.text = "one\ntwo"
        editor.cursor_location = (0, 0)
        await pilot.pause()

        await pilot.press("down")
        await pilot.pause()
        assert app.focused is editor
        assert editor.cursor_location[0] == 1

        await pilot.press("down")
        await pilot.pause()
        assert app.focused is not editor


async def test_a_multiselect_keeps_the_arrows_until_its_last_option(tmp_path: Path) -> None:
    """Same rule for an option list: it moves its highlight, then lets the form take over."""
    async with survey(tmp_path / "out", template="tui_kinds") as (app, pilot):
        options = app.screen.query_one("#ctl-extras", SelectionList)
        options.focus()
        await pilot.pause()

        await pilot.press("down")
        await pilot.pause()
        assert app.focused is options
        assert options.highlighted == 1

        await pilot.press("down")
        await pilot.pause()
        assert app.focused is not options


async def test_escape_takes_two_presses_and_says_so(tmp_path: Path) -> None:
    """A survey is too costly to lose to one stray key: the first escape only arms."""
    async with survey(tmp_path / "out") as (app, pilot):
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, SurveyScreen)
        assert hint(app) == CANCEL_HINT

        await pilot.press("escape")
        await pilot.pause()
        assert app.return_value is not None


async def test_moving_the_focus_disarms_a_pending_escape(tmp_path: Path) -> None:
    """Anything but a second escape puts the safety back on."""
    async with survey(tmp_path / "out") as (app, pilot):
        await pilot.press("escape")
        await pilot.pause()
        assert hint(app) == CANCEL_HINT

        await pilot.press("down")
        await pilot.pause()
        assert hint(app) != CANCEL_HINT

        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, SurveyScreen)


async def test_escape_closes_an_open_menu_before_it_arms_a_quit(tmp_path: Path) -> None:
    """Escape reaches the transient thing first: an open list closes, the survey stays put."""
    async with survey(tmp_path / "out", template="tui_kinds") as (app, pilot):
        select = app.screen.query_one("#ctl-flavour")
        select.focus()
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
        assert select.expanded is True

        await pilot.press("escape")
        await pilot.pause()
        assert select.expanded is False
        assert hint(app) != CANCEL_HINT


async def test_editing_an_answer_disarms_a_pending_escape(tmp_path: Path) -> None:
    """A keystroke that changes an answer is not the confirmation the armed escape wants."""
    async with survey(tmp_path / "out") as (app, pilot):
        app.screen.query_one("#ctl-name").focus()
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert hint(app) == CANCEL_HINT

        await pilot.press("z")
        await pilot.pause()
        assert hint(app) != CANCEL_HINT

        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, SurveyScreen)


async def test_the_arming_window_lapses_on_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An escape armed and then forgotten does not quit the survey minutes later."""
    monkeypatch.setattr(survey_screen, "CANCEL_WINDOW", 0.5)
    async with survey(tmp_path / "out") as (app, pilot):
        await pilot.press("escape")
        await pilot.pause()
        assert hint(app) == CANCEL_HINT

        await pilot.pause(0.8)
        assert hint(app) != CANCEL_HINT

        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, SurveyScreen)


async def test_the_header_says_which_field_of_how_many(tmp_path: Path) -> None:
    """The position is the anchor a scrolling form lacks, and it costs no row of its own."""
    async with survey(tmp_path / "out") as (app, pilot):
        title = app.screen.query_one("#hdr-title", Static)
        assert "1 of 3" in str(title.visual)

        await pilot.press("down")
        await pilot.pause()
        assert "2 of 3" in str(title.visual)


async def test_the_survey_re_reads_the_size_it_was_resized_to_behind_the_review(
    tmp_path: Path,
) -> None:
    """The prompt belongs to the terminal, not to one screen: the uncovered form re-checks."""
    dst = tmp_path / "out"
    with TemplateUI.from_template(str(FIXTURES / "tui_flow"), dst=dst) as ui:
        app = SurveyApp(ui, dst, {})
        async with app.run_test(size=(40, 10)) as pilot:
            await pilot.pause()
            assert app.screen.query("#resize-prompt")

            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, ReviewScreen)
            await pilot.resize_terminal(100, 40)
            await pilot.pause()

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, SurveyScreen)
            assert not app.screen.query("#resize-prompt")


async def test_the_terminal_size_prompt_comes_and_goes(tmp_path: Path) -> None:
    """Below the minimum the app shows a resize prompt, and drops it once resized."""
    dst = tmp_path / "out"
    with TemplateUI.from_template(str(FIXTURES / "tui_flow"), dst=dst) as ui:
        app = SurveyApp(ui, dst, {})
        async with app.run_test(size=(40, 10)) as pilot:
            await pilot.pause()
            assert app.screen.query("#resize-prompt")
            await pilot.resize_terminal(100, 40)
            await pilot.pause()
            assert not app.screen.query("#resize-prompt")
