"""What the form looks like: row banding, field grounds, option chips, disabled rows.

These are the cues that tell a reader where one question ends and the next begins, which of
its options is the answer, and which rows the cursor may not edit. They are asserted here
rather than left to a screenshot because every one of them regressed silently at least once.
"""

from __future__ import annotations

import ast
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
import re
from textwrap import wrap
from typing import Any
import unicodedata

import pytest
from rich.cells import cell_len
from textual.widgets import Static

from copier_tui import __version__, inline
from copier_tui.app import SurveyApp
from copier_tui.inline import FREE, TAKEN, InlineOptions
from copier_tui.screens import SurveyScreen
from copier_tui.theme import PALETTES, PULSE_CYCLE, PULSE_INTERVAL, THEMES, pulse_shades
from copier_tui.widgets import BRANCH_LAST, BRANCH_MORE, RAIL, FieldRow
from copier_ui import TemplateUI

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
REFERENCE = Path("/home/lab/workspace/private/copier-projects/copier-data-science")

BAND = "row-alt"
"""The class the survey puts on every second visible row."""

MODES = ("dark", "light")
"""The two themes. A test of a rule the palette states runs in both."""

P = PALETTES["dark"]
"""The palette a test reads when it does not name a theme: the theme a survey opens in."""

RESTING = ("row", "row-alt", "row-cond", "row-alt-cond")
CURRENT = ("row-focus", "row-cond-focus")
ROW_GROUNDS = (*RESTING, *CURRENT)
"""Every ground a row can have, by role: two bands, each band on a conditional row, and the
two the cursor takes."""


@asynccontextmanager
async def survey(
    dst: Path,
    template: str = "tui_flow",
    size: tuple[int, int] = (100, 40),
    data: dict[str, Any] | None = None,
    mode: str = "dark",
) -> AsyncIterator[tuple[SurveyApp, Any]]:
    """A running survey over a fixture template, paused on its first screen."""
    with TemplateUI.from_template(str(FIXTURES / template), dst=dst, data=data) as ui:
        app = SurveyApp(ui, dst, {"quiet": True, "unsafe": True}, THEMES[mode].name)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            yield app, pilot


def rows(app: SurveyApp) -> list[FieldRow]:
    """The mounted rows, in the order the form shows them."""
    return list(app.screen.query(FieldRow))


def banding(app: SurveyApp) -> list[bool]:
    """Whether each visible row wears the band, top to bottom."""
    return [BAND in row.classes for row in rows(app)]


def option_grounds(options: InlineOptions) -> dict[str, str]:
    """Map each option's label to the background it is painted on.

    Read off the painted strip rather than the source Text, and matched on the label alone -
    a chip also carries its filled-or-empty circle.
    """
    grounds: dict[str, str] = {}
    for line in range(max(1, options.size.height)):
        for segment in options.render_line(line):
            label = segment.text.strip(f" {TAKEN}{FREE}")
            if label and segment.style and segment.style.bgcolor:
                grounds[label] = segment.style.bgcolor.triplet.hex
    return grounds


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


@pytest.mark.parametrize("mode", MODES)
async def test_a_typing_ground_carries_the_band_through_the_control(
    mode: str, tmp_path: Path
) -> None:
    """Field ground: a text box spans the row, so it takes the band or the stripe vanishes.

    Five consecutive text questions otherwise merge into one lit block - the same
    undifferentiated wall the banding exists to break up.
    """
    p = PALETTES[mode]
    async with survey(tmp_path / "out", mode=mode) as (app, _):
        grounds = {
            row.question.id: row.query_one(f"#ctl-{row.question.id}").styles.background.hex6
            for row in rows(app)
            if row.question.id in {"name", "token"}
        }
        # `name` is the first row and holds the focus on mount, so it wears the focus ground
        assert grounds["name"].lower() == p["field-focus"]
        assert grounds["token"].lower() == p["field"]
        assert p["field-alt"] != p["field"]
        assert p["row-alt"] != p["row"]
        # app CSS outranks a widget's default sheet whatever the specificity, so the ground
        # only lands if the rule lives in BASE_CSS - it did not, and the test passed anyway
        # for as long as the field ground happened to equal the generic Input background
        assert p["field"] != p["surface"]


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
        grounds = option_grounds(app.screen.query_one("#ctl-advanced", InlineOptions))
        # no focus here, so the answer wears its resting blue
        assert grounds["No"] == P["picked"]
        assert grounds["Yes"] != P["picked"]


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


async def test_the_first_field_holds_the_focus_as_soon_as_the_form_opens(tmp_path: Path) -> None:
    """Focus: the form opens on a question, not on nothing.

    A row mounts a beat before the control it composes, so focusing without awaiting the
    mount finds the row and not the widget inside it - and the failure is silent, because a
    missing control is indistinguishable from a field that has gone away.
    """
    async with survey(tmp_path / "out") as (app, _):
        assert app.screen.focused is not None
        assert app.screen.focused.id == "ctl-name"


async def test_every_place_the_cursor_stops_is_a_control(tmp_path: Path) -> None:
    """Focus: no stop in the walk offers nothing to do.

    A VerticalScroll takes focus by default so it can be scrolled, which put a dead stop
    between every pair of questions - nothing highlighted, nothing editable, a press that
    went nowhere. Textual scrolls the focused control into view by itself.
    """
    async with survey(tmp_path / "out") as (app, pilot):
        stops = []
        for _ in range(8):
            await pilot.press("down")
            await pilot.pause()
            stops.append(getattr(app.screen.focused, "id", None))
        assert all(stop and stop.startswith("ctl-") for stop in stops), stops
        assert app.screen.query_one("#survey-form").can_focus is False


@pytest.mark.parametrize("mode", MODES)
async def test_the_three_option_states_each_have_their_own_ground(
    mode: str, tmp_path: Path
) -> None:
    """Option chips: chosen, under the cursor, and passed over are three separate grounds.

    The answer is the only one that changes hue, so being chosen is never inferred from which
    neutral is brighter, and nothing is dimmed out of legibility - the options passed over are
    the alternatives being decided against.

    An option passed over has one ground on the row the cursor is on and another elsewhere.
    The cursor's row is the surface band, which the resting chip is six parts off, so on that
    row every alternative would otherwise be a label with no chip under it.
    """
    p = PALETTES[mode]
    async with survey(tmp_path / "out", mode=mode) as (app, pilot):
        options = app.screen.query_one("#ctl-advanced", InlineOptions)
        assert option_grounds(options)["Yes"] == p["option"]  # the cursor is on another row

        app.screen.set_focus(options)
        await pilot.pause()
        grounds = option_grounds(options)
        # the cursor starts on the answer, so that chip shows the cursor's own cyan
        assert grounds["No"] == p["cursor-picked"]
        assert grounds["Yes"] == p["option-focus"]
        chips = {p["picked"], p["cursor-picked"], p["option"], p["option-focus"], p["cursor"]}
        assert len(chips) == 5

        await pilot.press("right")
        await pilot.pause()
        moved = option_grounds(options)
        assert moved["Yes"] == p["cursor-picked"]
        # left behind by the cursor, the old answer is an ordinary alternative again
        assert moved["No"] == p["option-focus"]


def option_text(options: InlineOptions) -> str:
    """Everything the option row paints, lines joined by a newline."""
    lines = []
    for line in range(max(1, options.size.height)):
        lines.append("".join(segment.text for segment in options.render_line(line)))
    return "\n".join(lines)


async def test_the_answer_is_a_filled_circle_and_the_rest_are_empty(tmp_path: Path) -> None:
    """Option shape: chosen is said in the glyph as well as the colour.

    Colour alone asks the reader to know which of two grounds means chosen. A filled circle
    against empty ones needs no key, and survives a terminal that renders the palette poorly.
    """
    async with survey(tmp_path / "out") as (app, pilot):
        app.screen.set_focus(app.screen.query_one("#ctl-advanced", InlineOptions))
        await pilot.pause()
        painted = option_text(app.screen.query_one("#ctl-advanced", InlineOptions))
        assert f"{TAKEN} No" in painted
        assert f"{FREE} Yes" in painted
        assert painted.count(TAKEN) == 1


@pytest.mark.parametrize("mode", MODES)
async def test_the_cursor_shows_even_when_it_sits_on_the_answer(mode: str, tmp_path: Path) -> None:
    """Cursor: where you are and what is chosen are two facts, and both must show at once.

    The cursor starts on the answer every time. The shape says which option is chosen and the
    chip's ground says where the cursor is, so the chip under the cursor has a ground no other
    chip on the row has - on the answer and off it. Nothing is drawn beside the chip: a
    square used to mark it, from when the two grounds were one shade apart.
    """
    p = PALETTES[mode]
    async with survey(tmp_path / "out", template="tui_kinds", mode=mode) as (app, pilot):
        options = app.screen.query_one("#ctl-extras", InlineOptions)
        app.screen.set_focus(options)
        await pilot.pause()
        labels = [choice.label for choice in options.choices]
        assert options.value == [], "the fixture ticks nothing, so the cursor is off the answer"

        grounds = option_grounds(options)
        assert grounds[labels[0]] == p["cursor"]
        assert [grounds[label] for label in labels[1:]] == [p["option-focus"]] * (len(labels) - 1)

        await pilot.press("space")
        await pilot.press("right")
        await pilot.pause()
        grounds = option_grounds(options)
        # ticked and left behind: chosen, on the row the cursor is on
        assert grounds[labels[0]] == p["picked-focus"]
        assert grounds[labels[1]] == p["cursor"]

        await pilot.press("left")
        await pilot.pause()
        assert option_grounds(options)[labels[0]] == p["cursor-picked"]

        painted = option_text(options)
        assert painted.count(TAKEN) == 1
        assert "\u25fc" not in painted, "the square beside the cursor's chip is gone"
        # the first chip starts in the control's first cell: no cell is kept for a mark
        assert painted.startswith(f" {TAKEN} {labels[0]} ")


async def test_short_options_share_a_line(tmp_path: Path) -> None:
    """Option layout: side by side while they fit.

    A yes and a no read fastest side by side and stacking them spends rows the form has not
    got. The other half of the rule - labels too long for the width go one per line - is
    asserted in test_tui_widgets.py, which can give the row a width to be too narrow.
    """
    async with survey(tmp_path / "out", template="tui_kinds") as (app, pilot):
        await pilot.pause()
        short = app.screen.query_one("#ctl-enabled", InlineOptions)
        assert "\n" not in option_text(short).rstrip("\n")


async def test_the_header_names_the_template_it_is_asking_about(tmp_path: Path) -> None:
    """Header: which template this is cannot be read off the questions themselves.

    Several questionnaires open at once look alike from the inside, and the source is the one
    fact none of the questions carries.
    """
    async with survey(tmp_path / "out") as (app, _):
        title = str(app.screen.query_one("#hdr-title", Static).visual)
        assert "tui_flow questionnaire" in title
        assert "survey" not in title


async def test_ctrl_c_does_not_leave_the_survey(tmp_path: Path) -> None:
    """Keys: ctrl+c belongs to the terminal, which copies with it.

    It used to be bound to cancel, so reaching for copy threw away every answer given so far.
    """
    async with survey(tmp_path / "out") as (app, pilot):
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert app.is_running
        assert isinstance(app.screen, SurveyScreen)


async def test_the_focus_bar_breathes_while_the_cursor_rests_on_a_question(
    tmp_path: Path,
) -> None:
    """Focus bar: the mark beside the focused question cycles shades, and only that one.

    Driven by classes rather than inline styles, because Textual cannot clear an inline style
    once set - the bar would keep the last shade it was given after the focus had moved on.
    """
    async with survey(tmp_path / "out") as (app, pilot):
        rows = {row.question.id: row for row in app.screen.query(FieldRow)}

        def shade(field_id: str) -> str | None:
            worn = [name for name in rows[field_id].classes if name.startswith("pulse-")]
            return worn[0] if worn else None

        seen = []
        for _ in range(len(PULSE_CYCLE)):
            seen.append(shade("name"))
            await pilot.pause(PULSE_INTERVAL + 0.01)
        assert None not in seen
        assert len(set(seen)) > 1, seen
        assert shade("token") is None

        await pilot.press("down")
        await pilot.pause()
        assert shade("name") is None
        assert shade("advanced") is not None


@pytest.mark.parametrize("mode", MODES)
def test_the_breath_moves_in_steps_too_small_to_see(mode: str) -> None:
    """Focus bar: consecutive phases are near-identical, so the bar reads as a breath.

    Four shades a third of a second apart was a sequence of shades rather than a breath. The
    bound is on the ramp itself because it is what went wrong - a cycle can be any length and
    still look stepped if the colours between its phases are far apart.
    """
    shades = pulse_shades(mode)
    frames = [shades[index] for index in PULSE_CYCLE]
    jumps = [
        max(abs(int(a[i : i + 2], 16) - int(b[i : i + 2], 16)) for i in (1, 3, 5))
        for a, b in zip(frames, frames[1:] + frames[:1])
    ]
    assert max(jumps) <= 12, jumps
    assert PULSE_INTERVAL * len(PULSE_CYCLE) < 2.5


@pytest.mark.parametrize("mode", MODES)
async def test_the_row_under_the_cursor_is_the_reverse_of_the_form(
    mode: str, tmp_path: Path
) -> None:
    """Row ground: the current row is drawn in reversed colours, ground and ink both.

    The row is the only thing that says where the cursor is without moving anything, so it
    has to be seen at a glance: light with dark ink in the dark theme, dark with light ink in
    the light one, and at least 7:1 from every band. Lifted onto the surface it stood 1.40:1
    from them, which was not enough. It is the same ground on either band, so walking the
    form does not make the current row change shade.
    """
    p = PALETTES[mode]
    async with survey(tmp_path / "out", mode=mode) as (app, pilot):
        grounds = {row.question.id: row.styles.background.hex6.lower() for row in rows(app)}
        assert grounds["name"] == p["row-focus"]  # first row, focused on mount
        assert grounds["token"] == p["row"]

        app.screen.set_focus(app.screen.query_one("#ctl-advanced", InlineOptions))
        await pilot.pause()
        banded = {row.question.id: row.styles.background.hex6.lower() for row in rows(app)}
        assert banded["advanced"] == p["row-focus"]  # one ground, whatever band the row is in
        assert banded["name"] == p["row"]

        caption = app.screen.query_one("#row-advanced .field-label")
        assert caption.styles.color.hex6.lower() == p["caption-focus"]

    for current in CURRENT:
        for band in RESTING:
            assert contrast(p[current], p[band]) >= 7.0, f"{mode}: {current} against {band}"
    # reversed: the form is light ink on a dark ground or the other way round, and the
    # current row is the opposite
    form_is_dark = _relative_luminance(p["row"]) < _relative_luminance(p["text"])
    row_is_dark = _relative_luminance(p["row-focus"]) < _relative_luminance(p["caption-focus"])
    assert row_is_dark is not form_is_dark


async def test_a_conditional_row_leans_green_and_hangs_off_its_answer(tmp_path: Path) -> None:
    """Row ground: a question another answer decides whether to ask says so twice.

    Green because the cursor owns the blue lean, and a tree connector because a tint this
    small cannot carry the meaning alone. `detail` is the only conditional question in the
    fixture, so the other three rows are what says the cue is not simply on everything.
    """
    async with survey(tmp_path / "out") as (app, pilot):
        app.screen.set_focus(app.screen.query_one("#ctl-advanced", InlineOptions))
        await pilot.press("right")
        await pilot.pause()

        marked = {row.question.id for row in rows(app) if "row-cond" in row.classes}
        assert marked == {"detail"}

        by_id = {row.question.id: row for row in rows(app)}
        assert by_id["detail"].styles.background.hex6.lower() == P["row-cond"]
        assert by_id["token"].styles.background.hex6.lower() == P["row-alt"]
        # the control spans the row, so a neutral typing ground would cut the tint in half
        # across the widest part of the question
        assert (
            by_id["detail"].query_one("#ctl-detail").styles.background.hex6.lower()
            == P["field-cond"]
        )
        assert (
            by_id["token"].query_one("#ctl-token").styles.background.hex6.lower() == P["field-alt"]
        )

        def caption(field_id: str) -> str:
            return str(by_id[field_id].query_one(".field-label", Static).visual)

        assert caption("detail").startswith(BRANCH_LAST)
        assert not caption("token").startswith((BRANCH_LAST, BRANCH_MORE))


@pytest.mark.parametrize("mode", MODES)
async def test_the_caret_is_drawn_in_the_colours_of_the_field_it_is_in(
    mode: str, tmp_path: Path
) -> None:
    """Field ground: the caret and a selection use the current row's colours, not the theme's.

    The field being typed into is on the row under the cursor, whose colours are the other
    theme's. Textual colours a caret from the theme's own foreground and background, which on
    that field is a light block on white in the dark theme and a dark block on slate in the
    light one. The caret is a block in the answer's ink and a selection is the cursor chip's
    pair, on the wrapping editor and on the one-line input alike.
    """
    p = PALETTES[mode]
    async with survey(tmp_path / "out", template="tui_kinds", mode=mode) as (app, pilot):
        for field_id, part in (("text", "text-area"), ("count", "input")):
            control = app.screen.query_one(f"#ctl-{field_id}")
            app.screen.set_focus(control)
            await pilot.pause()
            assert control.styles.background.hex6.lower() == p["field-focus"]
            caret = control.get_component_styles(f"{part}--cursor")
            assert caret.background.hex6.lower() == p["answer-focus"], field_id
            assert caret.color.hex6.lower() == p["field-focus"], field_id
            selection = control.get_component_styles(f"{part}--selection")
            assert selection.background.hex6.lower() == p["cursor"], field_id
            assert selection.color.hex6.lower() == p["cursor-ink"], field_id


@pytest.mark.parametrize("mode", MODES)
def test_the_cursor_and_the_condition_are_told_by_different_properties(mode: str) -> None:
    """Row ground: the cursor changes how light a row is, a condition changes its hue.

    Two cues on one property are one cue the reader cannot place, so the properties are
    asserted rather than the hexes - either may be retuned, but not onto the other's.

    A conditional row leans green and stays as light as its band: under 1.1:1 against it,
    where the current row is at least 1.2:1 against every band. The lean survives the cursor,
    so the conditional current row is green of the plain current row and about as light.
    """
    p = PALETTES[mode]

    def channels(colour: str) -> tuple[int, int, int]:
        return tuple(int(colour[i : i + 2], 16) for i in (1, 3, 5))

    for band, cond in (("row", "row-cond"), ("row-alt", "row-alt-cond")):
        _, band_green, band_blue = channels(p[band])
        _, cond_green, cond_blue = channels(p[cond])
        assert cond_green > band_green and cond_blue < band_blue
        assert contrast(p[cond], p[band]) < 1.1

    _, focus_green, focus_blue = channels(p["row-focus"])
    _, cond_focus_green, cond_focus_blue = channels(p["row-cond-focus"])
    assert cond_focus_green > focus_green and cond_focus_blue < focus_blue
    assert cond_focus_green > cond_focus_blue  # it reads green, where the plain one reads blue
    assert contrast(p["row-cond-focus"], p["row-focus"]) < 1.1


@pytest.mark.parametrize("mode", MODES)
async def test_a_banded_conditional_row_still_yields_its_grounds_to_the_cursor(
    mode: str, tmp_path: Path
) -> None:
    """Row ground: the cursor wins on a row wearing both classes, ground and control alike.

    Textual ranks by specificity first, and a row matching on two classes outranks the focus
    rule that matches on one - so the combination has to be spelled out or the focused row
    keeps its conditional tint and stops looking focused. The fixture's one conditional
    question always lands on the plain band, so the band is put on it here.
    """
    p = PALETTES[mode]
    async with survey(tmp_path / "out", mode=mode) as (app, pilot):
        app.screen.set_focus(app.screen.query_one("#ctl-advanced", InlineOptions))
        await pilot.press("right")
        await pilot.pause()

        row = {r.question.id: r for r in rows(app)}["detail"]
        row.add_class(BAND)
        await pilot.pause()
        assert row.styles.background.hex6.lower() == p["row-alt-cond"]
        assert row.query_one("#ctl-detail").styles.background.hex6.lower() == p["field-alt-cond"]

        app.screen.set_focus(row.query_one("#ctl-detail"))
        await pilot.pause()
        assert row.styles.background.hex6.lower() == p["row-cond-focus"]
        ground = row.query_one("#ctl-detail").styles.background.hex6.lower()
        assert ground == p["field-cond-focus"]


async def test_no_row_moves_when_the_cursor_moves(tmp_path: Path) -> None:
    """Row size: the row under the cursor is as tall as it is anywhere else.

    The current row used to open a blank line above and below itself, so every row under the
    cursor moved down by two on each press of an arrow and back up on the next. None of the
    three questions here prints help, so each is one line with the cursor on it and one line
    without, and every row stays on the line it started on.
    """
    async with survey(tmp_path / "out") as (app, pilot):
        before = {row.question.id: row.region.y for row in rows(app)}
        for row in rows(app):
            app.screen.set_focus(row.query_one(f"#ctl-{row.question.id}"))
            await pilot.pause()
            assert row.region.height == 1, f"{row.question.id} is {row.region.height} rows tall"
            assert row.region.height == row.query_one(".field-head").region.height
            assert {r.question.id: r.region.y for r in rows(app)} == before

            painted = {
                segment.style.bgcolor.triplet.hex.lower()
                for segment in row.render_line(0)
                if segment.style and segment.style.bgcolor
            }
            assert painted == {P["row-focus"]}


async def test_children_of_one_answer_are_drawn_as_a_run(tmp_path: Path) -> None:
    """Tree connectors: only the last child of an answer closes the run.

    Two questions hanging off the same answer both printing the last-child connector reads
    as two runs of one rather than one run of two.
    """
    async with survey(tmp_path / "out", template="tui_tree") as (app, _):

        def caption(field_id: str) -> str:
            row = {r.question.id: r for r in rows(app)}[field_id]
            return str(row.query_one(".field-label", Static).visual)

        assert [row.question.id for row in rows(app)] == ["storage", "bucket", "region", "owner"]
        assert caption("bucket").startswith(BRANCH_MORE)
        assert caption("region").startswith(BRANCH_LAST)
        assert not caption("storage").startswith((BRANCH_MORE, BRANCH_LAST))
        assert not caption("owner").startswith((BRANCH_MORE, BRANCH_LAST))


async def test_a_child_whose_answer_was_supplied_draws_no_connector(tmp_path: Path) -> None:
    """Tree connectors: nothing hangs off a row that is not on the form.

    An answer given with --data is never asked for, so its children are on their own and a
    connector under them points at the question above, which decides nothing about them.
    """
    async with survey(tmp_path / "out", template="tui_tree", data={"storage": "s3"}) as (app, _):
        shown = [row.question.id for row in rows(app)]
        assert "storage" not in shown
        for row in rows(app):
            caption = str(row.query_one(".field-label", Static).visual)
            assert not caption.startswith((BRANCH_MORE, BRANCH_LAST)), row.question.id


async def test_a_wrapped_child_caption_hangs_off_its_connector(tmp_path: Path) -> None:
    """Tree connectors: the lines a caption wraps onto keep clear of the connector column.

    A caption long enough to wrap ran its second line back under the connector, which put
    prose where the tree is and broke the column the connectors are read down. The run is
    carried on down a child with more siblings below it and left blank on the last.
    """
    async with survey(tmp_path / "out", template="tui_tree") as (app, _):
        captions = {
            row.question.id: str(row.query_one(".field-label", Static).visual).splitlines()
            for row in rows(app)
        }
        assert len(captions["bucket"]) > 1, captions["bucket"]
        assert captions["bucket"][0].startswith(BRANCH_MORE)
        assert all(line.startswith("\u2502  ") for line in captions["bucket"][1:])

        assert len(captions["region"]) > 1, captions["region"]
        assert captions["region"][0].startswith(BRANCH_LAST)
        assert all(line.startswith("   ") for line in captions["region"][1:])
        assert not any(line.startswith("\u2502") for line in captions["region"][1:])


async def test_the_cursor_opens_no_gap_inside_a_run(tmp_path: Path) -> None:
    """Tree connectors: a child with the cursor on it still touches the rows around it.

    The connector column is read down the captions, so it is unbroken exactly when each row
    of a run starts on the line after the one before it ends. The blank line the cursor used
    to open either side of itself landed inside the run and had to carry a rail across; no
    line opens now, so there is nothing to cross.
    """
    async with survey(tmp_path / "out", template="tui_tree") as (app, pilot):
        by_id = {row.question.id: row for row in rows(app)}
        for field_id in ("bucket", "region"):
            app.screen.set_focus(app.screen.query_one(f"#ctl-{field_id}"))
            await pilot.pause()
            assert by_id["bucket"].region.y == by_id["storage"].region.bottom
            assert by_id["region"].region.y == by_id["bucket"].region.bottom
            head = by_id[field_id].query_one(".field-head").region.height
            assert by_id[field_id].region.height == head


async def test_a_child_apart_from_its_answer_draws_no_connector(tmp_path: Path) -> None:
    """Tree connectors: a child asked for further down the form hangs from nothing.

    A connector joins a row to the row its run starts under. The JupyterLab extension template
    asks for the extension kind first and for the MIME type fields last, after the repository
    URL, and their connectors made them read as children of the repository. The row keeps
    the conditional ground, which is what says it is conditional.
    """
    async with survey(tmp_path / "out", template="tui_tree_tall") as (app, _):
        by_id = {row.question.id: row for row in rows(app)}
        captions = {
            field_id: str(row.query_one(".field-label", Static).visual)
            for field_id, row in by_id.items()
        }
        assert list(captions) == ["storage", "bucket", "mode", "region", "owner", "endpoint"]
        assert captions["region"].startswith(BRANCH_LAST)
        assert not captions["endpoint"].startswith((BRANCH_MORE, BRANCH_LAST))
        assert "row-cond" in by_id["endpoint"].classes


async def test_the_tree_runs_down_a_row_taller_than_its_caption(tmp_path: Path) -> None:
    """Tree connectors: the line goes on down the lines a row has under its caption.

    A question whose options stack is several lines tall and its caption is one. The lines
    under the caption were blank, so the tree stopped at a parent and started again at its
    first child, and stopped again at every tall child inside the run. The help line of the
    row the cursor is on is one more line of the row, and the tree crosses it the same way.
    """
    async with survey(tmp_path / "out", template="tui_tree_tall") as (app, pilot):
        by_id = {row.question.id: row for row in rows(app)}

        def under_caption(field_id: str) -> list[tuple[str, str]]:
            """What shows in the tree's column on each line under the caption, and its ink."""
            head = by_id[field_id].query_one(".field-head")
            label = by_id[field_id].query_one(".field-label", Static)
            shown = []
            for line in range(label.region.height, head.region.height):
                at = (head.region.x + 1, head.region.y + line)
                assert app.screen.get_widget_at(*at)[0] is head, (
                    f"{field_id}: line {line} is covered"
                )
                first = next(iter(head.render_line(line)))
                shown.append((first.text[:2], first.style.color.triplet.hex.lower()))
            return shown

        app.screen.set_focus(app.screen.query_one("#ctl-owner"))
        await pilot.pause()
        for field_id in ("storage", "mode"):
            lines = under_caption(field_id)
            assert len(lines) >= 3, f"{field_id} is not taller than its caption"
            assert set(lines) == {(f" {RAIL}", P["subtle"])}, field_id
        for field_id in ("region", "owner", "endpoint"):
            head = by_id[field_id].query_one(".field-head")
            painted = "".join(segment.text for segment in head.render_line(0))
            assert RAIL not in painted, f"{field_id} draws a line with nothing under it"

        # `mode` is the tall row that has something to print under itself: nothing is ticked,
        # so it prints its placeholder as an example; a row with an answer has no line to cross
        app.screen.set_focus(app.screen.query_one("#ctl-mode"))
        await pilot.pause()
        assert set(under_caption("mode")) == {(f" {RAIL}", P["rail-focus"])}
        crossed = by_id["mode"].query_one(".field-help", Static)
        assert crossed.display and crossed.styles.border_left[0] == "solid"
        assert crossed.styles.border_left[1].hex.lower() == P["rail-focus"]
        assert crossed.region.y == by_id["region"].region.y - 1

        answer = app.screen.query_one("#ctl-mode")
        assert crossed.content_region.x == answer.region.x, "the line moved the help text"


@pytest.mark.parametrize("mode", MODES)
async def test_the_scrollbar_thumb_stands_out_from_its_track(tmp_path: Path, mode: str) -> None:
    """Scrollbar: the thumb is a mark, and clears 3:1 on its track in both themes.

    A theme that names neither colour gets both derived from its primary and its background:
    2.06:1 in the dark theme and 1.72:1 in the light one, on the one mark that says the form
    goes on below the screen.
    """
    async with survey(tmp_path / "out", template="tui_kinds", mode=mode) as (app, _):
        form = app.screen.query_one("#survey-form")
        thumb = form.styles.scrollbar_color.hex6.lower()
        track = form.styles.scrollbar_background.hex6.lower()
        assert (thumb, track) == (PALETTES[mode]["subtle"], PALETTES[mode]["chrome"])
        assert contrast(thumb, track) >= 3.0


def _relative_luminance(colour: str) -> float:
    """WCAG relative luminance of a `#rrggbb` string."""
    raw = colour.lstrip("#")
    channels = [int(raw[at : at + 2], 16) / 255 for at in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(one: str, other: str) -> float:
    """The WCAG contrast ratio between two colours, brighter over darker."""
    first, second = _relative_luminance(one), _relative_luminance(other)
    return (max(first, second) + 0.05) / (min(first, second) + 0.05)


@pytest.mark.parametrize("mode", MODES)
def test_the_cursor_is_told_apart_from_the_option_it_sits_on(mode: str) -> None:
    """Option chips: where the cursor is and what is chosen are separate at a glance.

    Both were painted in the same blue a shade apart, which measured 1.32:1 - a reader moving
    along a row could not see the cursor at all, because the only chip that changed changed
    into the colour the chosen chip already was. 3:1 is the floor for telling two interface
    surfaces apart, and it is asserted rather than eyeballed because the pair that failed it
    looked deliberate: the docstring beside them described an inversion the colours never had.
    """
    p = PALETTES[mode]
    # the chips the cursor's chip sits beside are the ones of its own row
    assert contrast(p["cursor-picked"], p["picked-focus"]) >= 3.0
    assert contrast(p["cursor"], p["option-focus"]) >= 3.0


TEXT_ON = (
    # captions, answers and option labels, each on the ground it is written on
    *(("text", ground) for ground in ("screen", "chrome", "surface", *RESTING)),
    *(("cyan-bright", ground) for ground in ("chrome", "surface", "row", "row-alt")),
    *(("answer", ground) for ground in ("field", "field-alt", "field-cond", "field-alt-cond")),
    ("option-ink", "option"),
    ("picked-ink", "picked"),
    # the footer, the status lines and the file list
    *(("muted", ground) for ground in ("screen", "chrome", "surface")),
    # the destination line, the version, and the caption of a row the answers rule out
    *(("subtle", ground) for ground in ("screen", "chrome", *RESTING)),
    # an error under a question the cursor is not on, and the failure text in the banner
    # and in the file list
    *(("error", ground) for ground in (*RESTING, "chrome", "surface")),
    # the row under the cursor: its caption, its help, an error, the answer being typed and
    # its caret, and the four chips an option can have there
    *(("caption-focus", ground) for ground in CURRENT),
    *(("help-focus", ground) for ground in CURRENT),
    *(("error-focus", ground) for ground in CURRENT),
    ("answer-focus", "field-focus"),
    ("answer-focus", "field-cond-focus"),
    ("option-focus-ink", "option-focus"),
    ("picked-focus-ink", "picked-focus"),
    ("cursor-ink", "cursor"),
    ("cursor-picked-ink", "cursor-picked"),
    # the verdicts and warnings printed on the screen ground, and the counts in the banner
    ("rose", "screen"),
    ("mint", "screen"),
    ("mint", "chrome"),
    ("orange", "chrome"),
    ("amber", "screen"),
)
"""Every ink and the grounds it is written on as text, by role. Each pair is held to 4.5:1."""

MARKS_ON = (
    # the bar beside the current row at rest, and the tree connector on that row
    *(("bar", ground) for ground in CURRENT),
    *(("rail-focus", ground) for ground in CURRENT),
    # the flag of a row the answers rule out
    *(("amber", ground) for ground in RESTING),
    # the progress bar on its track
    ("orange", "surface"),
    ("mint", "surface"),
    # the border of the failed banner
    ("rose", "chrome"),
)
"""Every mark that is not text and the grounds it is drawn on. Each pair is held to 3:1."""


@pytest.mark.parametrize("mode", MODES)
def test_every_ink_clears_the_floor_on_every_ground_it_lands_on(mode: str) -> None:
    """Every pair the palette actually paints, in each theme: 4.5:1 for text, 3:1 for a mark.

    The typing grounds went unasserted, and one of them drifted below the floor when the
    conditional lean was applied to it: the orange answer measured 4.19:1 on the focused
    conditional field, which is the most important text in the app on the row it is being
    typed into. It was found by a reviewer, not by this suite.
    """
    p = PALETTES[mode]
    for floor, pairs in ((4.5, TEXT_ON), (3.0, MARKS_ON)):
        for ink, ground in pairs:
            measured = contrast(p[ink], p[ground])
            assert measured >= floor, f"{mode}: {ink} on {ground} is {measured:.2f}:1"


def test_both_themes_define_the_same_roles() -> None:
    """Palette: a role one theme lacks is a variable the stylesheet cannot resolve there."""
    assert set(PALETTES["dark"]) == set(PALETTES["light"])
    for mode in MODES:
        for role, value in PALETTES[mode].items():
            assert value == value.lower() and len(value) == 7 and value[0] == "#", (mode, role)


def test_no_colour_is_written_outside_the_palette() -> None:
    """Palette: a hex colour in a stylesheet or a style is one theme's colour in both themes.

    Every colour is a role, read from the theme being shown. A literal would be right in the
    theme it was chosen in and wrong in the other, with nothing reporting it.
    """
    package = Path(inline.__file__).parent
    for source in sorted(package.rglob("*.py")):
        if source.name == "theme.py":
            continue
        found = re.findall(r"#[0-9a-fA-F]{6}\b", source.read_text(encoding="utf-8"))
        assert not found, f"{source.name} writes {found}"


@pytest.mark.parametrize("mode", MODES)
async def test_the_survey_opens_in_the_theme_it_is_given(mode: str, tmp_path: Path) -> None:
    """Theme: the grounds on screen are the ones the named theme defines."""
    p = PALETTES[mode]
    async with survey(tmp_path / "out", mode=mode) as (app, _):
        assert app.theme == THEMES[mode].name
        assert app.screen.styles.background.hex6.lower() == p["screen"]
        header = app.screen.query_one("#app-header")
        assert header.styles.background.hex6.lower() == p["chrome"]
        assert rows(app)[-1].styles.background.hex6.lower() == p["row"]


def test_no_new_glyph_the_tui_prints_has_an_ambiguous_width() -> None:
    """Glyphs: nothing new may join the handful whose width the terminal gets to choose.

    A character whose East Asian width is `A` is one cell in most terminals and two in any
    terminal set to render ambiguous characters wide - while `rich.cells.cell_len` counts one
    either way. Rich then lays the row out a cell short of what the terminal draws and
    everything after the glyph sits a column off.

    The source text is parsed rather than scanned, because every offender in this package is
    written as a `\\uXXXX` escape and a scan of the characters in the file sees none of them.
    The first version of this test did scan, reported the one literal middle dot, and was
    taken as proof there were no others - there were six.

    The survivors are listed, not fixed. Every box-drawing character in Unicode is ambiguous
    width; there is no neutral set, so the conditional tree cannot be drawn without them. The
    two option marks could be swapped, and are not: `●` and `○` are the shapes a reader knows,
    and both are already width-safe beside each other. The point of the list is that it cannot
    grow without someone deciding it should.
    """
    known = {
        0x2500,  # ─ the tree's horizontal, and no box-drawing character is width neutral
        0x2502,  # │
        0x251C,  # ├
        0x2514,  # └
        0x25CB,  # ○ the option not taken
        0x25CF,  # ● the option in force
    }
    found: set[int] = set()
    for source in Path(inline.__file__).parent.rglob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        # a string that is a statement on its own is documentation - a docstring, or the
        # explanation this codebase writes under a constant - and is never painted. The
        # docstring saying why U+25B6 was rejected must not read as a use of U+25B6
        documentation = {
            id(node.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in documentation:
                continue
            found.update(
                ord(char)
                for char in node.value
                if ord(char) > 0x7F
                and unicodedata.east_asian_width(char) in ("A", "W")
                and cell_len(char) == 1
            )
    new = sorted(found - known)
    assert not new, [f"U+{cp:04X} {unicodedata.name(chr(cp), '?')}" for cp in new]


async def test_the_bar_breathes_on_every_kind_of_row(tmp_path: Path) -> None:
    """Focus bar: no row's ground rule may outrank the beat and freeze it.

    The rules that keep the plate one colour under the cursor name two classes and a
    pseudo-class, which outranks every rule the beat is written with. Setting a border in them
    stopped the bar dead on any row that was both banded and conditional - while the option
    mark beside it, coloured in code rather than in CSS, went on breathing. One row in four
    showed two halves of one signal out of step.
    """
    async with survey(tmp_path / "out", template="tui_tree") as (app, pilot):
        for row in rows(app):
            id = row.question.id
            app.screen.set_focus(row.query_one(f"#ctl-{id}"))
            await pilot.pause()
            # the beat is driven by hand: its own timer keeps running through an awaited
            # pause, so a sampled cycle skips phases and misses the ends of the ramp
            row._pulse.stop()
            row._beat = 0
            seen = set()
            for _ in range(len(PULSE_CYCLE)):
                row._breathe()
                await pilot.pause()
                seen.add(str(row.styles.border_left))
            classes = sorted(c for c in row.classes if c.startswith("row-"))
            assert len(seen) > 1, f"the bar is frozen on {id} ({' '.join(classes) or 'plain'})"


@pytest.mark.parametrize("mode", MODES)
def test_the_breathing_bar_stays_visible_at_every_phase(mode: str) -> None:
    """The bar is a graphical indicator, so its weakest shade still clears 3:1 on its ground.

    The ramp used to reach `#12648b`: 2.50:1 on the focused ground and 2.34:1 on a conditional
    one. Four shades of seventeen fell under the floor, and the cosine spacing dwells at the
    ends, so the only thing saying which row the cursor is on spent about a fifth of every
    cycle below it. The docstring claimed the opposite, which is why this is asserted.
    """
    p = PALETTES[mode]
    for ground in CURRENT:
        worst = min(contrast(shade, p[ground]) for shade in pulse_shades(mode))
        assert worst >= 3.0, f"{mode}: the bar drops to {worst:.2f}:1 on {ground}"


@pytest.mark.skipif(
    not Path("/home/lab/workspace/private/copier-projects/copier-data-science").is_dir(),
    reason="the reference template is not checked out",
)
@pytest.mark.parametrize("width", [60, 70, 80, 100, 120])
async def test_no_question_loses_the_end_of_its_sentence(width: int, tmp_path: Path) -> None:
    """A caption fits the lines it is given, at every width the app supports.

    The cap was sized against a gutter fixed at 56 columns; the gutter is a share of the row
    now, so at 80 two of the reference template's questions lost the end of their sentence, at
    70 four did and at 60 seven - with no ellipsis and nowhere else to read them.

    The height is what is measured, not the text. A caption with no tree connector is handed to
    Textual unwrapped and folded at paint time, so it carries no newlines to count and reading
    its text back says nothing about what fits. Two earlier attempts at this check reported all
    clear against captions that were visibly cut.
    """
    dst = tmp_path / "out"
    with TemplateUI.from_template(str(REFERENCE), dst=dst, unsafe=True) as ui:
        app = SurveyApp(ui, dst, {"unsafe": True, "quiet": True})
        async with app.run_test(size=(width, 40)) as pilot:
            await pilot.pause()
            for row in rows(app):
                label = row.query_one(".field-label", Static)
                if not label.size.width:
                    continue
                needed = len(wrap(row.question.label, label.size.width) or [""])
                assert needed <= label.size.height, (
                    f"{row.question.id} needs {needed} lines and has {label.size.height}"
                )


async def test_the_header_leads_with_the_project_and_ends_with_the_tool(tmp_path: Path) -> None:
    """Header: the two facts nothing else on the screen carries lead and close the title.

    The tool's own name and version say the same thing on every screen of every run, so they
    were moved out of the title into the right-hand cell. What is left is read in the order a
    person needs it: which project, which template, which field - the project and the field
    counter written in the accent, the context between them not.
    """
    dst = tmp_path / "orders-api"
    dst.mkdir()
    with TemplateUI.from_template(str(FIXTURES / "tui_flow"), dst=dst) as ui:
        app = SurveyApp(ui, dst, {})
        async with app.run_test(size=(100, 24)) as pilot:
            await pilot.pause()
            title = app.screen.query_one("#hdr-title", Static)
            shown = str(title.visual)
            assert shown.startswith("orders-api ⸱ "), shown
            assert shown.endswith(" ⸱ 1 of 3"), shown
            assert "copier-tui" not in shown, "the tool name belongs in the right-hand cell"
            assert str(app.screen.query_one("#hdr-version", Static).visual) == (
                f"copier-tui v{__version__}"
            )

            ink = {}
            for segment in title.render_line(0):
                if segment.text.strip() and segment.style and segment.style.color:
                    ink[segment.text] = segment.style.color.triplet.hex.lower()
            assert ink["orders-api"] == P["cyan-bright"].lower()
            assert ink["1 of 3"] == P["cyan-bright"].lower()
            assert ink["tui_flow questionnaire"] != P["cyan-bright"].lower()


async def test_a_bool_row_names_no_key_it_does_not_need(tmp_path: Path) -> None:
    """Help: two options are read off the row itself, so naming the key that flips them is noise.

    A multiselect's `space` is named on the status line, not on the row, as ticking is not
    visible in its options. A switch and a single choice name no key anywhere.
    """
    async with survey(tmp_path / "out") as (app, pilot):
        row = {r.question.id: r for r in rows(app)}["advanced"]
        app.screen.set_focus(row.query_one(InlineOptions))
        await pilot.pause()
        assert "space" not in str(row.query_one(".field-help", Static).visual)
