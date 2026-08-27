"""The survey screen driven through the Textual pilot: layout, navigation, keys, errors."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import Any

import pytest
from textual.containers import VerticalScroll
from textual.widgets import Footer, Static, TextArea

from copier_tui.app import SurveyApp
from copier_tui.errors import EXIT_CANCELLED
from copier_tui.inline import InlineOptions
from copier_tui.screens import ReviewScreen, SurveyScreen
from copier_tui.screens import survey as survey_screen
from copier_tui.screens.survey import CANCEL_HINT
from copier_tui.theme import MIN_HEIGHT, MIN_WIDTH
from copier_tui.widgets import FieldRow
from copier_ui import TemplateUI

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
REFERENCE = Path("/home/lab/workspace/private/copier-data-science")


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
    """A caption is never repeated under its own row - only what the caption does not say."""
    async with survey(tmp_path / "out", template="tui_kinds") as (app, pilot):
        app.screen.query_one("#ctl-flavour").focus()
        await pilot.pause()
        shown = field_help(app, "flavour")
        assert app.screen.query(FieldRow).first().question.label not in shown
        # what it does carry is the one key that answers a picking question, which the footer
        # cannot name because it means something else on every other row. One clause, not two
        # joined by a hyphen: the pair wrapped at the narrow sizes and left the hyphen hanging
        # at the end of a line, reading as a subtraction
        assert shown == "space cycles the answer", shown


async def test_the_line_under_the_form_stays_blank_until_it_has_something_to_say(
    tmp_path: Path,
) -> None:
    """The status line is reserved, not filled.

    It carried a legend of every key that moves or changes something. The footer names those
    keys already and the focused row prints its own help under itself, so the legend was a
    line of text between the reader and the questions that never changed. The row is still
    there, still one line, so nothing on screen moves when a message does arrive.
    """
    async with survey(tmp_path / "out", template="tui_kinds") as (app, _):
        assert hint(app) == ""
        assert app.screen.query_one("#survey-status").size.height == 1


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


async def test_the_survey_says_where_the_template_will_be_rendered(tmp_path: Path) -> None:
    """The destination sits beside the key legend, home-relative where that shortens it.

    It is the one fact a person filling in thirty answers cannot recover from anything else on
    the screen, and by then the command line that carried it has scrolled away.
    """
    dst = tmp_path / "out"
    async with survey(dst) as (app, _):
        shown = str(app.screen.query_one("#survey-where", Static).visual)
        # the tail is what names the project, so that is what a crop has to keep. A pytest
        # tmp_path runs past the line's width, which is the case a real deep path is in too
        assert shown.endswith(f"{dst.parent.name}/out"), shown

    home = Path.home() / "somewhere-under-home"
    with TemplateUI.from_template(str(FIXTURES / "tui_flow"), dst=home) as ui:
        app = SurveyApp(ui, home, {})
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            shown = str(app.screen.query_one("#survey-where", Static).visual)
    assert shown.endswith("~/somewhere-under-home"), shown


async def test_the_survey_names_a_relative_destination_in_full(tmp_path: Path) -> None:
    """A destination given relatively is still named on screen, by the part that names it.

    `copier-tui update` defaults its destination to the current directory, and the survey
    printed the `.` it was handed - a line that says the answers are going where the reader
    already is, which is the one thing they did not need telling.
    """
    here = os.getcwd()
    try:
        os.chdir(tmp_path)
        with TemplateUI.from_template(str(FIXTURES / "tui_flow"), dst=Path(".")) as ui:
            app = SurveyApp(ui, Path("."), {})
            async with app.run_test(size=(100, 40)) as pilot:
                await pilot.pause()
                shown = str(app.screen.query_one("#survey-where", Static).visual)
    finally:
        os.chdir(here)
    # cropped from the left when it is long, so what survives is the end - the directory the
    # answers are going into, which is the half of a path that identifies anything
    assert shown.rstrip().endswith(tmp_path.resolve().name), shown
    assert shown.strip() != "destination: .", (
        "a bare dot names the one place the reader is standing"
    )


async def test_ctrl_x_quits_from_the_survey(tmp_path: Path) -> None:
    """One key, no arming, and it is offered in the footer.

    Escape is a single ambiguous byte, so a second one can be read as the introducer of
    whatever the terminal says next and never arrive. ctrl+x introduces nothing.
    """
    dst = tmp_path / "out"
    async with survey(dst) as (app, pilot):
        assert app.active_bindings["ctrl+x"].binding.description == "Quit"
        # escape keeps its own footer entry: two bindings sharing one action name leave only
        # one of them showing, and which one survives depends on the screen
        assert app.active_bindings["escape"].binding.description == "Cancel"
        await pilot.press("ctrl+x")
        await pilot.pause()
    assert app.return_value == EXIT_CANCELLED
    assert not dst.exists(), "a quit before the review writes nothing"


async def test_the_form_gets_every_row_the_chrome_is_not_using(tmp_path: Path) -> None:
    """The form fills the screen: header, status line and footer take one row each.

    The status line's CSS was written for an id nothing carried, so the row it styles fell
    back to a Horizontal's own `height: 1fr` and split the screen with the form. The form was
    laid out at half the terminal, the questions were cut off partway down, and the rows the
    status line was holding stayed blank all the way to the footer.
    """
    dst = tmp_path / "out"
    async with survey(dst, size=(100, 40)) as (app, _):
        form = app.screen.query_one("#survey-form", VerticalScroll)
        status = app.screen.query_one("#survey-status")
        assert status.size.height == 1, status.size
        # the region is the rows the form owns; its size is one less, for the top padding
        assert form.region.height == 40 - 3, form.region


async def test_a_form_that_fits_neither_scrolls_nor_shows_a_bar(tmp_path: Path) -> None:
    """Content shorter than the screen leaves nothing to scroll and nothing to scroll with.

    The size is deliberately modest: a terminal that holds every question with rows to spare,
    and small enough that a form given only half the screen would have shown a scrollbar over
    content the user could see the end of.
    """
    dst = tmp_path / "out"
    async with survey(dst, template="tui_kinds", size=(100, 26)) as (app, _):
        form = app.screen.query_one("#survey-form", VerticalScroll)
        assert form.virtual_size.height <= form.container_size.height, form.virtual_size
        assert form.max_scroll_y == 0
        assert not form.show_vertical_scrollbar


@pytest.mark.skipif(
    not Path("/home/lab/workspace/private/copier-data-science").is_dir(),
    reason="the reference template is not checked out",
)
async def test_a_form_too_tall_for_the_screen_still_scrolls(tmp_path: Path) -> None:
    """The other half of the claim: a form that genuinely overflows keeps its scrollbar.

    It takes a template with more questions than the screen has rows. This used to be done by
    running a twelve-question fixture in a narrow terminal, on the reasoning that the captions
    would wrap and outgrow the screen - which stopped being true when the gutter became a share
    of the row, since a caption re-wrapped into a narrower gutter is still capped in height.
    The reference template asks twenty-three, which no supported height can hold.
    """
    dst = tmp_path / "out"
    with TemplateUI.from_template(str(REFERENCE), dst=dst, unsafe=True) as ui:
        app = SurveyApp(ui, dst, {"quiet": True, "unsafe": True})
        async with app.run_test(size=(100, MIN_HEIGHT)) as pilot:
            await pilot.pause()
            form = app.screen.query_one("#survey-form", VerticalScroll)
            assert form.virtual_size.height > form.container_size.height, form.virtual_size
            assert form.max_scroll_y > 0
            assert form.show_vertical_scrollbar


async def test_a_long_destination_is_cropped_rather_than_wrapped(tmp_path: Path) -> None:
    """The destination stays on its one row however long the path is.

    Textual's visual pipeline drops a Rich `Text`'s own `no_wrap` and `overflow`, so a path
    longer than the row folded onto two further lines, carrying the status line - and the
    arrow that introduces it - away from the legend it belongs beside.
    """
    dst = tmp_path / Path(*[f"a-long-directory-name-{index}" for index in range(8)])
    async with survey(dst, size=(100, 40)) as (app, _):
        where = app.screen.query_one("#survey-where", Static)
        assert where.size.height == 1, where.size
        assert app.screen.query_one("#survey-status").size.height == 1


async def test_the_cursor_stops_at_the_last_field(tmp_path: Path) -> None:
    """Down on the last field stays there rather than rolling round to the first."""
    dst = tmp_path / "out"
    async with survey(dst, template="tui_kinds") as (app, pilot):
        for _ in range(len(row_ids(app)) + 3):
            await pilot.press("down")
        assert app.screen.focused is app.screen.focus_chain[-1]


async def test_the_cursor_stops_at_the_first_field(tmp_path: Path) -> None:
    """And up on the first field stays there rather than rolling round to the last."""
    dst = tmp_path / "out"
    async with survey(dst, template="tui_kinds") as (app, pilot):
        await pilot.press("down", "down")
        for _ in range(6):
            await pilot.press("up")
        assert app.screen.focused is app.screen.focus_chain[0]


async def test_a_multiselect_names_the_key_that_ticks_an_option(tmp_path: Path) -> None:
    """The focused multiselect says `space` under itself; no other question does.

    A multiselect answers to nothing else - the arrows walk its options without ticking any of
    them - and the key was named in exactly two places, the key legend and the command
    palette's key panel, both since removed. That left a question no key the interface names
    can answer.
    """
    async with survey(tmp_path / "out", template="tui_kinds") as (app, pilot):
        screen = app.screen
        screen.set_focus(screen.query_one("#ctl-extras", InlineOptions))
        await pilot.pause()
        assert "space ticks" in field_help(app, "extras")

        screen.set_focus(screen.query_one("#ctl-flavour", InlineOptions))
        await pilot.pause()
        # a single choice names space too - it cycles the answer, and a reader who has just
        # learned it on a multiselect row will try it here
        assert "space cycles" in field_help(app, "flavour")


async def test_the_tick_key_still_works_where_it_is_not_named(tmp_path: Path) -> None:
    """Naming the key on one kind of question must not take it from the others."""
    async with survey(tmp_path / "out", template="tui_kinds") as (app, pilot):
        options = app.screen.query_one("#ctl-flavour", InlineOptions)
        app.screen.set_focus(options)
        await pilot.pause()
        before = options.value
        await pilot.press("space")
        await pilot.pause()
        assert options.value != before, "space still walks a single choice forward"


async def test_help_belongs_to_the_focused_row_and_costs_the_others_nothing(
    tmp_path: Path,
) -> None:
    """A row's help opens a line under it only while it has the focus.

    The line was opened by an inline `display`, which overrode the very stylesheet rule that
    keeps help to the focused row - so every question carrying help spent a second line
    whether or not anyone was reading it, on a layout whose whole point is one row each.
    """
    async with survey(tmp_path / "out", template="tui_kinds") as (app, pilot):
        screen = app.screen
        rows = {row.question.id: row for row in screen.query(FieldRow)}
        screen.set_focus(screen.query_one("#ctl-extras", InlineOptions))
        await pilot.pause()
        focused = rows["extras"].region.height

        screen.set_focus(screen.query_one("#ctl-flavour", InlineOptions))
        await pilot.pause()
        assert rows["extras"].region.height < focused, (
            "the help line must close again when the cursor leaves the row"
        )


async def test_the_quit_key_quits_from_every_kind_of_field(tmp_path: Path) -> None:
    """ctrl+x is the way out from any row, including the ones that want the key for cut.

    Textual's own `Input` and `TextArea` bind ctrl+x to `cut`, and a focused widget's binding
    beats the screen's - so without priority the advertised quit key silently became the
    editor's cut on every text field, which is five rows in six. Nothing tested it: the only
    quit test pressed the key on the first field and never walked the form.
    """
    async with survey(tmp_path / "out", template="tui_kinds") as (app, pilot):
        seen = set()
        for _ in range(12):
            focused = app.focused
            assert focused is not None
            bound = {
                binding.action
                for _, binding, _, _ in app.active_bindings.values()
                if binding.key == "ctrl+x"
            }
            assert bound == {"app.quit_now"}, (
                f"ctrl+x is {bound} on {type(focused).__name__}, not the quit key the footer names"
            )
            seen.add(type(focused).__name__)
            await pilot.press("down")
            await pilot.pause()
        assert {"WrapInput", "Input", "TextArea", "InlineOptions"} <= seen, seen


async def test_an_armed_cancel_does_not_survive_a_trip_to_review(tmp_path: Path) -> None:
    """Escape, review, back, escape - the survey is NOT discarded.

    No focus event fires when the review screen is popped: the field that had the cursor still
    has it. So nothing disarmed, and one escape on return threw away every answer. Four presses
    inside the three-second window, which is not a long reach for a hesitant hand.
    """
    async with survey(tmp_path / "out") as (app, pilot):
        screen = app.screen
        await pilot.press("escape")
        await pilot.pause()
        assert screen._armed

        await pilot.press("enter")  # to review
        await pilot.pause()
        await pilot.press("escape")  # and back again
        await pilot.pause()
        assert not screen._armed, "the cancel came back from review still armed"

        await pilot.press("escape")
        await pilot.pause()
        assert app.return_value is None, "one escape after review discarded the survey"


async def test_the_header_never_wraps_and_so_never_loses_the_path(tmp_path: Path) -> None:
    """The header bar is one row, so its title is cropped rather than wrapped.

    A wrapped title keeps only its first line, and that line ends at the last space it fitted -
    which on the review screen took the whole destination off the screen at 80 columns and left
    a dangling separator. The review screen is the last thing read before anything is written,
    and where it will be written is the fact it exists to confirm.
    """
    dst = tmp_path / "churn-pipeline"
    dst.mkdir()
    with TemplateUI.from_template(str(FIXTURES / "tui_flow"), dst=dst) as ui:
        for width in (120, 100, 80, 70, 60):
            app = SurveyApp(ui, dst, {})
            async with app.run_test(size=(width, 24)) as pilot:
                await pilot.press("enter")  # onto the review screen
                await pilot.pause()
                title = app.screen.query_one("#hdr-title", Static)
                assert title.region.height == 1, f"the title wrapped at {width} columns"
                assert dst.name in str(title.visual), f"the destination is unnamed at {width}"


async def test_a_destination_too_long_for_the_bar_loses_its_head_not_its_tail(
    tmp_path: Path,
) -> None:
    """What survives a crop is the end of the project name, because that is what names it.

    The stylesheet's own ellipsis takes characters off the right, which on a name removes the
    part that tells two projects apart. The header shortens from the left first, and it does
    so against the width the row actually has - a constant was both too aggressive on a wide
    terminal and no help on a narrow one.
    """
    dst = tmp_path / "a-project-with-a-name-far-too-long-for-a-narrow-terminal-bar"
    dst.mkdir()
    with TemplateUI.from_template(str(FIXTURES / "tui_flow"), dst=dst) as ui:
        app = SurveyApp(ui, dst, {})
        async with app.run_test(size=(70, 24)) as pilot:
            await pilot.press("enter")
            await pilot.pause()
            title = app.screen.query_one("#hdr-title", Static)
            shown = str(title.visual)
            assert title.region.height == 1
            # the project word sits between the app name and the context, cropped from the
            # left: its end is what tells two projects apart
            assert "terminal-bar ⸱ review" in shown, shown
            assert str(tmp_path) not in shown, "the head was kept and the project name cut"


async def test_the_review_prints_the_words_the_answer_was_given_in(tmp_path: Path) -> None:
    """The last screen before a write says `Yes`, not `True`, and names what was ticked.

    A bool's two labels live in the renderer, not in the state, so nothing resolved them and
    the review printed the value behind the answer. On the reference template that is eleven
    of twenty-three questions reading as Python on the screen that asks for confirmation.
    """
    async with survey(tmp_path / "out", template="tui_kinds") as (app, pilot):
        app.ui.set("enabled", True)
        app.ui.set("extras", ["x", "y"])
        await pilot.press("enter")
        await pilot.pause()
        printed = {
            str(row.query(Static)[0].visual): str(row.query(Static)[1].visual)
            for row in app.screen.query(".review-answer")
            if len(row.query(Static)) == 2
        }
        assert printed["enabled (bool)"] == "Yes", printed["enabled (bool)"]
        assert printed["extras"] == "x, y", printed["extras"]


async def test_a_multiselect_nobody_ticked_reads_as_a_choice_not_an_absence(
    tmp_path: Path,
) -> None:
    """Ticking none of the options is a decision, and reads as one.

    `[]` is not how a person writes an answer, but neither is `not set` - that is what the
    review says about a question nobody reached, in the same words and the same grey, so
    "I chose none of these" and "I skipped this" were indistinguishable on the screen whose
    job is to be read before anything is written.
    """
    async with survey(tmp_path / "out", template="tui_kinds") as (app, pilot):
        await pilot.press("enter")
        await pilot.pause()
        printed = {
            str(row.query(Static)[0].visual): str(row.query(Static)[1].visual)
            for row in app.screen.query(".review-answer")
            if len(row.query(Static)) == 2
        }
        assert printed["extras"] == "none selected", printed["extras"]


async def test_arriving_on_a_failing_row_does_not_make_it_speak(tmp_path: Path) -> None:
    """A focus alone leaves a failing row silent; only an edit or a refused enter speaks.

    Focus once promoted the row, but nothing re-rendered on a focus - so the sentence
    surfaced on the next unrelated keystroke and moved the form under a cursor that was
    somewhere else by then. The template fails at mount, because a value changed after
    mount is news the reader caused and rightly speaks.
    """
    (tmp_path / "template").mkdir()
    (tmp_path / "template" / "README.md").write_text("x\n")
    (tmp_path / "copier.yml").write_text(
        "_subdirectory: template\n"
        "first:\n  type: str\n  default: ''\n"
        '  validator: "{% if not first %}first is required{% endif %}"\n'
        "second:\n  type: str\n  default: ''\n"
    )
    dst = tmp_path / "out"
    with TemplateUI.from_template(str(tmp_path), dst=dst) as ui:
        app = SurveyApp(ui, dst, {"quiet": True})
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("up")
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("z")  # an edit on the OTHER row
            await pilot.pause()
            assert field_help(app, "first") == "", "a focus alone made the row speak"


async def test_a_blocked_enter_disarms_the_cancel(tmp_path: Path) -> None:
    """escape, an enter the validator refuses, escape - the survey is NOT discarded.

    The refused branch overwrites the arming warning with a validation message, and it re-
    focuses a field that already had the cursor, so `set_focus` returns early and no focus
    event fires. The safety's whole visible state was replaced while the safety stayed on, and
    the next escape - the gesture for dismissing a message - threw away every answer.
    """
    async with survey(tmp_path / "out") as (app, pilot):
        screen = app.screen
        app.ui.set("name", "")
        await screen._refresh_rows()
        await pilot.pause()

        await pilot.press("escape")
        await pilot.pause()
        assert screen._armed

        await pilot.press("enter")  # refused by the validator
        await pilot.pause()
        assert not screen._armed, "a blocked enter left the cancel armed and its warning gone"

        await pilot.press("escape")
        await pilot.pause()
        assert app.return_value is None, "escape after a blocked enter discarded the survey"


async def test_an_answer_is_legible_at_the_width_the_app_asks_for(tmp_path: Path) -> None:
    """At MIN_WIDTH every row shows its answer, not just its caption.

    The caption gutter was a constant 56 in a terminal the app itself declares usable at 60,
    so the answer column was 0 columns wide and every row showed a question and nothing else -
    with no resize prompt, because 60 is not too small. The gutter is a share of the row now.
    """
    async with survey(tmp_path / "out", template="tui_kinds", size=(MIN_WIDTH, 30)) as (app, _):
        for row in app.screen.query(FieldRow):
            control = row.query_one(f"#ctl-{row.question.id}")
            assert control.size.width >= 12, f"{row.question.id} has {control.size.width} columns"


async def test_the_destination_keeps_its_tail_at_the_narrowest_supported_width(
    tmp_path: Path,
) -> None:
    """The status line crops from the left, so the directory being written to survives."""
    dst = tmp_path / "deeply" / "nested" / "somewhere" / "my-analytics-project"
    dst.mkdir(parents=True)
    with TemplateUI.from_template(str(FIXTURES / "tui_flow"), dst=dst) as ui:
        app = SurveyApp(ui, dst, {})
        async with app.run_test(size=(MIN_WIDTH, 24)) as pilot:
            await pilot.pause()
            shown = str(app.screen.query_one("#survey-where", Static).visual)
            assert shown.endswith(dst.name), shown


async def test_the_overwrite_warning_leads_with_the_risk(tmp_path: Path) -> None:
    """The one line that says an existing project may be overwritten says it first.

    It is one row over a wrapping Static, so led by the path it wrapped and the second line was
    clipped - at 60 columns it read as an amber path and nothing else.
    """
    dst = tmp_path / "already-here"
    dst.mkdir()
    (dst / "mine.txt").write_text("keep me", encoding="utf-8")
    with TemplateUI.from_template(str(FIXTURES / "tui_flow"), dst=dst) as ui:
        app = SurveyApp(ui, dst, {})
        async with app.run_test(size=(MIN_WIDTH, 24)) as pilot:
            await pilot.press("enter")
            await pilot.pause()
            warning = app.screen.query_one("#review-warning", Static)
            assert warning.region.height == 1
            assert str(warning.visual).startswith("existing files may be overwritten")


@pytest.mark.skipif(not REFERENCE.is_dir(), reason="the reference template is not checked out")
@pytest.mark.parametrize("width", [60, 80, 100, 120])
async def test_walking_the_form_does_not_change_a_single_answer(
    width: int, tmp_path: Path
) -> None:
    """Holding `down` to the bottom of the survey rewrites nothing.

    `down` is the form's own key. Binding it to a stacked option list looked right - a column
    read with the arrows that read a column - and was a data-loss defect: moving is choosing
    on a single-choice question, so every stacked answer the cursor passed was committed to
    its next option. Twelve of twenty-three at 60 columns, silently, with nothing on screen
    saying so and no way to arrow back to what had been there.

    Which keys do answer the question is said on the row's own help line instead.
    """
    dst = tmp_path / "out"
    with TemplateUI.from_template(str(REFERENCE), dst=dst, unsafe=True) as ui:
        app = SurveyApp(ui, dst, {"quiet": True, "unsafe": True})
        async with app.run_test(size=(width, 40)) as pilot:
            await pilot.pause()
            state = ui.state()
            before = {id: state.fields[id].value for id in state.visible_ids}
            for _ in range(60):
                await pilot.press("down")
                await pilot.pause()
            state = ui.state()
            changed = {
                id: (before.get(id), state.fields[id].value)
                for id in state.visible_ids
                if before.get(id, "<new>") != state.fields[id].value
            }
            assert not changed, changed


async def test_options_on_one_line_leave_the_arrows_to_the_form(tmp_path: Path) -> None:
    """Unstacked, the options read as a row, so up and down still move between questions."""
    async with survey(tmp_path / "out", template="tui_kinds", size=(140, 30)) as (app, pilot):
        options = app.screen.query_one("#ctl-flavour", InlineOptions)
        app.screen.set_focus(options)
        await pilot.pause()
        assert not options.stacked, "this width was chosen so the list fits one line"

        await pilot.press("down")
        await pilot.pause()
        assert app.focused is not options, "down should have moved to the next question"


@pytest.mark.parametrize("width", [60, 80, 100])
async def test_the_cancel_warning_is_readable_whole(width: int, tmp_path: Path) -> None:
    """The app's one destructive keystroke says what it does, at every supported width.

    The warning shares its row with the destination, which claims up to 60 percent of it, so
    at 60 columns it was ellipsised to `press escape again to` - the reader told to press a key
    again and not told that it throws away every answer. It takes the whole row while it is up:
    the destination is on the review screen and in the header, and this sentence has nowhere
    else to be.
    """
    dst = tmp_path / "clients" / "acme" / "data-platform" / "ingest-service"
    dst.mkdir(parents=True)
    with TemplateUI.from_template(str(FIXTURES / "tui_flow"), dst=dst) as ui:
        app = SurveyApp(ui, dst, {})
        async with app.run_test(size=(width, 24)) as pilot:
            await pilot.press("escape")
            await pilot.pause()
            box = app.screen.query_one("#survey-hint", Static)
            assert box.size.width >= len(CANCEL_HINT), (
                f"the warning has {box.size.width} columns for {len(CANCEL_HINT)} characters"
            )
            assert not app.screen.query_one("#survey-where", Static).display


@pytest.mark.parametrize("size", [(100, 17), (80, 17), (59, 24), (30, 8)])
async def test_the_resize_advisory_covers_nothing_that_carries_a_warning(
    size: tuple[int, int], tmp_path: Path
) -> None:
    """The prompt takes a row from the form; it never paints over one that says something.

    Three attempts at this widget each fixed the last and broke a neighbour: centred it covered
    six rows of the form, docked flush it covered the footer where the keys are named, lifted
    one row it covered the status line - which is where the cancel warning says that a second
    escape discards every answer. Both bottom rows of every screen are load-bearing, so there
    was never a free row to overlay; it is a row of the layout now.
    """
    dst = tmp_path / "out"
    with TemplateUI.from_template(str(FIXTURES / "tui_flow"), dst=dst) as ui:
        app = SurveyApp(ui, dst, {})
        async with app.run_test(size=size) as pilot:
            await pilot.press("escape")
            await pilot.pause()
            prompt = app.screen.query("#resize-prompt")
            assert prompt, f"no prompt at {size}, which is under the minimum"
            taken = {
                app.screen.query_one("#survey-status").region.y,
                app.screen.query(Footer).first().region.y,
            }
            assert prompt.first(Static).region.y not in taken
            assert str(app.screen.query_one("#survey-hint", Static).visual) == CANCEL_HINT


@pytest.mark.parametrize("park_on", ["ctl-name", "ctl-advanced", "ctl-token"])
async def test_a_refused_enter_says_why_wherever_the_cursor_was(
    park_on: str, tmp_path: Path
) -> None:
    """Enter that the validator refuses explains itself, whatever row the cursor was on.

    Pressing enter from anywhere but the bad row used to jump the cursor across a form of two
    dozen questions and say nothing at all: the message was written and then the focus move it
    triggers blanked it. The test that covered this pressed enter on the already-focused field,
    where `set_focus` returns early and no focus event fires; its own docstring said so.

    The reason lives on the row now and the shared line counts what is left, so this asserts
    both - the same words in both places was one sentence on screen twice, rose both times,
    with the shared copy the one that gets cropped.
    """
    async with survey(tmp_path / "out") as (app, pilot):
        screen = app.screen
        app.ui.set("name", "")
        await screen._refresh_rows()
        await pilot.pause()
        screen.set_focus(screen.query_one(f"#{park_on}"))
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()
        # the reason is on the offending row, in full, wherever the cursor started
        assert "required" in field_help(app, "name")
        # and the shared line carries the one fact no row can state
        assert "attention" in str(screen.query_one("#survey-hint", Static).visual)


@pytest.mark.parametrize("size", [(30, 8), (40, 10), (59, 24)])
async def test_the_resize_advisory_reads_as_advice_and_keeps_its_numbers(
    size: tuple[int, int], tmp_path: Path
) -> None:
    """The advisory is ink like the warnings beside it, one row, and never loses its numbers.

    Filled amber across the width it was the loudest thing on screen and the least urgent -
    both real warnings are ink, so a fill outranked them, and this one is permanent where the
    cancel warning lives three seconds. It also wrapped, so at 30 columns it clipped away the
    size it exists to name.
    """
    with TemplateUI.from_template(str(FIXTURES / "tui_flow"), dst=tmp_path / "out") as ui:
        app = SurveyApp(ui, tmp_path / "out", {})
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            prompt = app.screen.query("#resize-prompt").first(Static)
            assert prompt.size.height == 1
            assert not prompt.styles.background.a, "an advisory is ink, not a fill"
            assert str(MIN_WIDTH) in str(prompt.visual)
            assert str(MIN_HEIGHT) in str(prompt.visual)
