"""The survey screen driven through the Textual pilot: layout, navigation, keys, errors."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from textual.containers import VerticalScroll
from textual.widgets import Static, TextArea

from copier_tui.app import SurveyApp
from copier_tui.inline import InlineOptions
from copier_tui.screens import ReviewScreen, SurveyScreen
from copier_tui.screens import survey as survey_screen
from copier_tui.screens.survey import CANCEL_HINT, KEY_HINT
from copier_tui.widgets import FieldRow
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
    """Whatever the one reserved line under the form currently says."""
    return str(app.screen.query_one("#survey-hint", Static).visual)


def field_help(app: SurveyApp, field_id: str) -> str:
    """What a row prints under itself: its help, or the problem with its answer."""
    return str(app.screen.query_one(f"#help-{field_id}", Static).visual)


def options_of(app: SurveyApp, field_id: str) -> str:
    """The option line a picking question shows on its own row."""
    return str(app.screen.query_one(f"#ctl-{field_id}", InlineOptions).render())


async def test_only_visible_askable_questions_are_shown(tmp_path: Path) -> None:
    """A hidden question is neither displayed nor reachable by navigation."""
    async with survey(tmp_path / "out") as (app, _):
        assert isinstance(app.screen, SurveyScreen)
        assert row_ids(app) == ["name", "advanced", "token"]
        assert app.ui.state().fields["detail"].visible is False
        assert not app.screen.query("#ctl-detail")


async def test_a_plain_field_costs_exactly_one_row(tmp_path: Path) -> None:
    """Label, control and status glyph share one line, so a long survey stays short.

    The caption line is measured rather than the row, because the focused row also carries
    the blank line it keeps either side of itself - that spacing is the point of it, and
    asserting on the row alone would call the row under the cursor a regression.
    """
    async with survey(tmp_path / "out", template="tui_kinds") as (app, _):
        for field_id in ("text", "where", "count", "ratio", "enabled", "flavour", "token"):
            row = app.screen.query_one(f"#row-{field_id}", FieldRow)
            head = row.query_one(".field-head")
            assert head.size.height == 1, f"{field_id} caption is {head.size.height} rows tall"
            if not row.has_focus_within:
                assert row.size.height == 1, f"{field_id} is {row.size.height} rows tall"


async def test_the_whole_form_is_about_one_line_per_question(tmp_path: Path) -> None:
    """Twelve questions of every kind occupy under 15 lines, editors and lists included.

    virtual_size is no measure here - a VerticalScroll reports its viewport when the content
    is shorter than it. The bottom of the last row is where the form actually ends.
    """
    async with survey(tmp_path / "out", template="tui_kinds") as (app, _):
        rows = list(app.screen.query(FieldRow))
        form = app.screen.query_one("#survey-form", VerticalScroll)
        assert len(rows) == 12
        used = rows[-1].region.bottom - form.region.y
        assert used <= 15, f"twelve questions took {used} lines"


async def test_fields_open_on_their_default(tmp_path: Path) -> None:
    """Every field opens prefilled, and an untouched default carries no warning glyph.

    An untouched default is the answer most in need of checking, so it is not marked as an
    exception; the glyph column is kept for a problem and for a field this answer set rules
    out, which are the two things worth interrupting a reader for.
    """
    async with survey(tmp_path / "out") as (app, _):
        row = app.screen.query_one("#row-name", FieldRow)
        assert row.value == "demo"
        assert str(row.query_one("#flag-name", Static).visual).strip() == ""


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


async def test_a_description_is_the_caption_and_is_never_cut(tmp_path: Path) -> None:
    """copier has no separate description: the caption IS it, so it must arrive whole.

    `Question.get_message` renders the template's `help`, which is why a caption and its
    help are the same sentence for every question that declares one. Cutting the caption
    therefore deletes the description, which is the part that says what to answer.
    """
    async with survey(tmp_path / "out", template="tui_kinds") as (app, _):
        row = app.screen.query_one("#row-flavour", FieldRow)
        assert row.question.label == row.question.help
        caption = str(row.query_one(".field-label", Static).visual)
        assert caption == "Which flavour the build uses"
        assert "\u2026" not in caption


async def test_the_same_sentence_is_never_printed_twice(tmp_path: Path) -> None:
    """With help and caption identical, repeating it under the row would say nothing."""
    async with survey(tmp_path / "out", template="tui_kinds") as (app, pilot):
        app.screen.query_one("#ctl-flavour").focus()
        await pilot.pause()
        assert field_help(app, "flavour") == ""


async def test_the_line_under_the_form_says_what_the_keys_do(tmp_path: Path) -> None:
    """Every key that moves or changes something is named where the eye already rests."""
    async with survey(tmp_path / "out", template="tui_kinds") as (app, _):
        legend = hint(app)
        assert legend == KEY_HINT
        for key in ("up", "down", "left", "right", "enter"):
            assert key in legend


async def test_every_option_is_on_the_row_not_behind_a_menu(tmp_path: Path) -> None:
    """What was passed over stays legible beside what was taken, without opening anything."""
    async with survey(tmp_path / "out", template="tui_kinds") as (app, _):
        line = options_of(app, "flavour")
        for label in ("a", "b"):
            assert label in line


async def test_every_row_is_captioned_by_its_question_not_its_variable_name(
    tmp_path: Path,
) -> None:
    """A person meeting the template reads questions, never snake_case identifiers."""
    async with survey(tmp_path / "out", template="tui_kinds") as (app, _):
        labels = {
            row.question.id: str(row.query_one(".field-label", Static).visual)
            for row in app.screen.query(FieldRow)
        }
        assert labels["flavour"].startswith("Which flavour the build uses")
        # no declared help falls back to copier's own `var_name (type)`, never a bare id
        assert labels["count"].startswith("count (int)")


async def test_an_invalid_field_blocks_finishing_but_not_navigation(tmp_path: Path) -> None:
    """The glyph marks the row, the hint names the problem, and enter goes back to it."""
    async with survey(tmp_path / "out") as (app, pilot):
        app.screen.query_one("#ctl-name").focus()
        await pilot.pause()
        for _ in range(4):
            await pilot.press("backspace")
        await pilot.pause()

        assert str(app.screen.query_one("#flag-name", Static).visual) == "!"
        assert "name is required" in field_help(app, "name")

        await pilot.press("down")
        await pilot.pause()
        assert app.focused.id == "ctl-advanced"

        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, SurveyScreen)
        assert app.focused.id == "ctl-name"
        assert "name is required" in field_help(app, "name")


async def test_enter_confirms_from_a_boolean_too(tmp_path: Path) -> None:
    """A boolean is picked with the arrows, so enter stays the confirm key everywhere."""
    async with survey(tmp_path / "out") as (app, pilot):
        app.screen.query_one("#ctl-advanced").focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ReviewScreen)
        assert app.ui.state().fields["advanced"].value is False


async def test_an_answer_outside_its_new_choices_is_kept_flagged_and_not_faked(
    tmp_path: Path,
) -> None:
    """A recompute can strand an answer. Nothing is silently corrected, nothing is invented.

    The state keeps the value and the review shows it. The option row cannot light any
    option, because none of them is the answer, so it lights none rather than lighting a
    neighbour the user never picked.
    """
    async with survey(tmp_path / "out", template="tui_kinds") as (app, pilot):
        app.ui.set("flavour", "zzz")
        await app.screen._refresh_rows()
        await pilot.pause()

        assert app.ui.state().fields["flavour"].value == "zzz"
        assert str(app.screen.query_one("#flag-flavour", Static).visual) == "!"
        assert app.screen.query_one("#ctl-flavour", InlineOptions).value == "zzz"

        app.screen._focus_field("flavour")
        await pilot.pause()
        assert "not in" in field_help(app, "flavour")


async def test_a_question_that_failed_to_load_is_disabled_and_blocks(tmp_path: Path) -> None:
    """A load error shows as a disabled field carrying its message, and blocks the finish."""
    async with survey(tmp_path / "out", template="tui_broken") as (app, pilot):
        assert row_ids(app) == ["good", "bad"]
        assert app.screen.query_one("#ctl-bad").disabled is True

        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, SurveyScreen)
        assert "nonsense" in field_help(app, "bad")


async def test_enter_confirms_from_a_choice_field(tmp_path: Path) -> None:
    """A choice claims left and right, never enter, so one key confirms from anywhere."""
    async with survey(tmp_path / "out", template="tui_kinds") as (app, pilot):
        app.screen.query_one("#ctl-flavour").focus()
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ReviewScreen)


async def test_the_arrows_choose_without_opening_anything(tmp_path: Path) -> None:
    """Right takes the next option there and then; the questions around it never move."""
    async with survey(tmp_path / "out", template="tui_kinds") as (app, pilot):
        before = row_ids(app)
        app.screen.query_one("#ctl-flavour").focus()
        await pilot.pause()

        await pilot.press("right")
        await pilot.pause()
        assert app.ui.state().fields["flavour"].value == "b"
        assert row_ids(app) == before


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
    """Stepping to another field puts the safety back on."""
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


async def test_editing_an_answer_disarms_a_pending_escape(tmp_path: Path) -> None:
    """So does typing. A control consumes its own keys, so the change message is the signal."""
    async with survey(tmp_path / "out") as (app, pilot):
        app.screen.query_one("#ctl-name").focus()
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert hint(app) == CANCEL_HINT

        await pilot.press("x")
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
