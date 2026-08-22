"""The survey screen driven through the Textual pilot: navigation, revisibility, errors."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from textual.widgets import OptionList, SelectionList, Static, TextArea

from copier_tui.app import SurveyApp
from copier_tui.screens import JumpScreen, SurveyScreen
from copier_tui.widgets import FieldRow
from copier_ui import TemplateUI

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@asynccontextmanager
async def survey(
    dst: Path, template: str = "tui_flow", data: dict[str, Any] | None = None
) -> AsyncIterator[tuple[SurveyApp, Any]]:
    """A running survey over a fixture template, paused on its first screen."""
    with TemplateUI.from_template(str(FIXTURES / template), dst=dst, data=data) as ui:
        app = SurveyApp(ui, dst, {"quiet": True, "unsafe": True})
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            yield app, pilot


def row_ids(app: SurveyApp) -> list[str]:
    """The question ids the survey currently shows, in order."""
    return [row.question.id for row in app.screen.query(FieldRow)]


async def test_only_visible_askable_questions_are_shown(tmp_path: Path) -> None:
    """A hidden question is neither displayed nor reachable by navigation."""
    async with survey(tmp_path / "out") as (app, _):
        assert isinstance(app.screen, SurveyScreen)
        assert row_ids(app) == ["name", "advanced", "token"]
        assert app.ui.state().fields["detail"].visible is False
        assert not app.screen.query("#ctl-detail")


async def test_fields_open_on_their_default_and_say_so(tmp_path: Path) -> None:
    """The value is prefilled and the label marks it as an untouched default."""
    async with survey(tmp_path / "out") as (app, _):
        row = app.screen.query_one("#row-name", FieldRow)
        assert row.value == "demo"
        assert "default" in str(row.query_one(".field-label", Static).visual)


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


async def test_jump_reaches_an_arbitrary_question(tmp_path: Path) -> None:
    """The overview lists the visible questions and focuses the one chosen."""
    async with survey(tmp_path / "out") as (app, pilot):
        await pilot.press("f2")
        await pilot.pause()
        assert isinstance(app.screen, JumpScreen)
        options = app.screen.query_one("#jump-list", OptionList)
        assert [option.id for option in options._options] == ["name", "advanced", "token"]

        options.highlighted = 2
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, SurveyScreen)
        assert app.focused.id == "ctl-token"


async def test_the_overview_masks_secrets(tmp_path: Path) -> None:
    """A secret's value never reaches the overview line."""
    async with survey(tmp_path / "out") as (app, pilot):
        await pilot.press("f2")
        await pilot.pause()
        lines = [
            option.prompt.plain
            for option in app.screen.query_one("#jump-list", OptionList)._options
        ]
        assert any("token  =  ***" in line for line in lines)
        assert not any("s3cret" in line for line in lines)


async def test_a_preset_answer_is_not_asked(tmp_path: Path) -> None:
    """A value given with --data is seeded and its question drops out of the survey."""
    async with survey(tmp_path / "out", data={"name": "seeded"}) as (app, pilot):
        assert "name" not in row_ids(app)
        assert app.ui.answers()["name"] == "seeded"
        await pilot.press("f2")
        await pilot.pause()
        options = app.screen.query_one("#jump-list", OptionList)
        assert "name" not in [option.id for option in options._options]


async def test_an_invalid_field_blocks_finishing_but_not_navigation(tmp_path: Path) -> None:
    """The message renders next to the field, the survey stays put, focus still moves."""
    async with survey(tmp_path / "out") as (app, pilot):
        app.screen.query_one("#ctl-name").focus()
        await pilot.pause()
        for _ in range(4):
            await pilot.press("backspace")
        await pilot.pause()

        error = app.screen.query_one("#err-name", Static)
        assert error.display is True
        assert "name is required" in str(error.visual)

        await pilot.press("down")
        await pilot.pause()
        assert app.focused.id == "ctl-advanced"

        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, SurveyScreen)
        assert app.screen.query_one("#warn-box", Static).display is True


async def test_a_question_that_failed_to_load_is_disabled_and_blocks(tmp_path: Path) -> None:
    """A load error shows as a disabled field carrying its message, and blocks the finish."""
    async with survey(tmp_path / "out", template="tui_broken") as (app, pilot):
        assert row_ids(app) == ["good", "bad"]
        assert app.screen.query_one("#ctl-bad").disabled is True
        assert "nonsense" in str(app.screen.query_one("#err-bad", Static).visual)

        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, SurveyScreen)
        assert app.screen.query_one("#warn-box", Static).display is True


async def test_a_menu_keeps_the_keys_it_owns(tmp_path: Path) -> None:
    """Enter opens a choice menu and the arrows move inside it, not between fields."""
    async with survey(tmp_path / "out", template="tui_kinds") as (app, pilot):
        select = app.screen.query_one("#ctl-flavour")
        select.focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert select.expanded is True

        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()
        assert select.expanded is False
        assert app.ui.state().fields["flavour"].value == "b"


async def test_an_editor_and_a_multiselect_keep_the_arrow_keys(tmp_path: Path) -> None:
    """Controls with a cursor of their own keep up and down; focus stays where it is."""
    async with survey(tmp_path / "out", template="tui_kinds") as (app, pilot):
        editor = app.screen.query_one("#ctl-config", TextArea)
        editor.focus()
        await pilot.pause()
        await pilot.press("down")
        await pilot.pause()
        assert app.focused is editor

        options = app.screen.query_one("#ctl-extras", SelectionList)
        options.focus()
        await pilot.pause()
        await pilot.press("down")
        await pilot.pause()
        assert app.focused is options
        assert options.highlighted == 1


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
