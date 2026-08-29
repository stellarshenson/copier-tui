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
from textwrap import wrap
from typing import Any
import unicodedata

import pytest
from rich.cells import cell_len
from textual.widgets import Static

from copier_tui import __version__, inline
from copier_tui.app import SurveyApp
from copier_tui.inline import CURSOR, FREE, TAKEN, InlineOptions
from copier_tui.screens import SurveyScreen
from copier_tui.theme import (
    ANSWER_FG,
    ANSWER_FOCUS_FG,
    CURSOR_BG,
    CURSOR_FG,
    CURSOR_PICKED_BG,
    CURSOR_PICKED_FG,
    CYAN_BRIGHT,
    FIELD_ALT_BG,
    FIELD_ALT_COND_BG,
    FIELD_BG,
    FIELD_COND_BG,
    FIELD_COND_FOCUS_BG,
    FIELD_FOCUS_BG,
    MARK_SHADES,
    OPTION_BG,
    OPTION_FG,
    PICKED_BG,
    PICKED_FG,
    PULSE_CYCLE,
    PULSE_INTERVAL,
    PULSE_SHADES,
    ROW_ALT_BG,
    ROW_ALT_COND_BG,
    ROW_BG,
    ROW_COND_BG,
    ROW_COND_FOCUS_BG,
    ROW_FOCUS_BG,
    SURFACE_BG,
)
from copier_tui.widgets import BRANCH_LAST, BRANCH_MORE, RAIL, FieldRow
from copier_ui import TemplateUI

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
REFERENCE = Path("/home/lab/workspace/private/copier-data-science")

BAND = "row-alt"
"""The class the survey puts on every second visible row."""


@asynccontextmanager
async def survey(
    dst: Path,
    template: str = "tui_flow",
    size: tuple[int, int] = (100, 40),
    data: dict[str, Any] | None = None,
) -> AsyncIterator[tuple[SurveyApp, Any]]:
    """A running survey over a fixture template, paused on its first screen."""
    with TemplateUI.from_template(str(FIXTURES / template), dst=dst, data=data) as ui:
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


def option_grounds(options: InlineOptions) -> dict[str, str]:
    """Map each option's label to the background it is painted on.

    Read off the painted strip rather than the source Text, and matched on the label alone -
    a chip also carries its cursor mark and its filled-or-empty circle.
    """
    grounds: dict[str, str] = {}
    for line in range(max(1, options.size.height)):
        for segment in options.render_line(line):
            label = segment.text.strip(f" {TAKEN}{FREE}{CURSOR}")
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
        # `name` is the first row and holds the focus on mount, so it wears the focus ground
        assert grounds["name"].lower() == FIELD_FOCUS_BG.lower()
        assert grounds["token"].lower() == FIELD_BG.lower()
        assert FIELD_ALT_BG != FIELD_BG
        assert ROW_ALT_BG != ROW_BG
        # app CSS outranks a widget's default sheet whatever the specificity, so the ground
        # only lands if the rule lives in BASE_CSS - it did not, and the test passed anyway
        # for as long as FIELD_BG happened to equal the generic Input background
        assert FIELD_BG != SURFACE_BG


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


async def test_the_three_option_states_each_have_their_own_ground(tmp_path: Path) -> None:
    """Option chips: chosen, under the cursor, and passed over are three separate grounds.

    The answer is the only one that changes hue, so being chosen is never inferred from which
    neutral is brighter, and nothing is dimmed out of legibility - the options passed over are
    the alternatives being decided against.
    """
    async with survey(tmp_path / "out") as (app, pilot):
        app.screen.set_focus(app.screen.query_one("#ctl-advanced", InlineOptions))
        await pilot.pause()
        options = app.screen.query_one("#ctl-advanced", InlineOptions)
        grounds = option_grounds(options)
        # the cursor starts on the answer, so that chip shows the cursor's brighter blue
        assert grounds["No"] == CURSOR_PICKED_BG
        assert grounds["Yes"] == OPTION_BG
        assert len({PICKED_BG, CURSOR_PICKED_BG, OPTION_BG, CURSOR_BG}) == 4

        await pilot.press("right")
        await pilot.pause()
        moved = option_grounds(options)
        assert moved["Yes"] == CURSOR_PICKED_BG
        # left behind by the cursor, the old answer is an ordinary alternative again
        assert moved["No"] == OPTION_BG


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


async def test_the_cursor_shows_even_when_it_sits_on_the_answer(tmp_path: Path) -> None:
    """Cursor: where you are and what is chosen are two facts, and both must show at once.

    The cursor starts on the answer every time, so a ground that only says "chosen" leaves
    the row with nothing to say "and you are here" - the mark carries it instead.
    """
    async with survey(tmp_path / "out") as (app, pilot):
        options = app.screen.query_one("#ctl-advanced", InlineOptions)
        app.screen.set_focus(options)
        await pilot.pause()
        assert f"{CURSOR} {TAKEN} No" in option_text(options)

        await pilot.press("right")
        await pilot.pause()
        painted = option_text(options)
        assert f"{CURSOR} {TAKEN} Yes" in painted
        assert painted.count(CURSOR) == 1


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


def test_the_breath_moves_in_steps_too_small_to_see() -> None:
    """Focus bar: consecutive phases are near-identical, so the bar reads as a breath.

    Four shades a third of a second apart was a sequence of shades rather than a breath. The
    bound is on the ramp itself because it is what went wrong - a cycle can be any length and
    still look stepped if the colours between its phases are far apart.
    """
    frames = [PULSE_SHADES[index] for index in PULSE_CYCLE]
    jumps = [
        max(abs(int(a[i : i + 2], 16) - int(b[i : i + 2], 16)) for i in (1, 3, 5))
        for a, b in zip(frames, frames[1:] + frames[:1])
    ]
    assert max(jumps) <= 12, jumps
    assert PULSE_INTERVAL * len(PULSE_CYCLE) < 2.5


async def test_the_focused_row_leans_its_ground_towards_blue(tmp_path: Path) -> None:
    """Row ground: the row under the cursor tints its band, on either band.

    Small on purpose - the row already carries a breathing bar, a blank line either side and
    a lit caption. Each tint stays nearer its own band than the other band, so a focused row
    is never read as a banded one.
    """
    async with survey(tmp_path / "out") as (app, pilot):
        grounds = {row.question.id: row.styles.background.hex6.lower() for row in rows(app)}
        assert grounds["name"] == ROW_FOCUS_BG  # first row, focused on mount
        assert grounds["token"] == ROW_BG

        app.screen.set_focus(app.screen.query_one("#ctl-advanced", InlineOptions))
        await pilot.pause()
        banded = {row.question.id: row.styles.background.hex6.lower() for row in rows(app)}
        assert banded["advanced"] == ROW_FOCUS_BG  # one plate, whatever band the row is in
        assert banded["name"] == ROW_BG

        def blue(colour: str) -> int:
            return int(colour[5:7], 16)

        assert blue(ROW_FOCUS_BG) - blue(ROW_BG) < blue(ROW_ALT_BG) - blue(ROW_BG)


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
        assert by_id["detail"].styles.background.hex6.lower() == ROW_COND_BG
        assert by_id["token"].styles.background.hex6.lower() == ROW_ALT_BG
        # the control spans the row, so a neutral typing ground would cut the tint in half
        # across the widest part of the question
        assert (
            by_id["detail"].query_one("#ctl-detail").styles.background.hex6.lower()
            == FIELD_COND_BG
        )
        assert (
            by_id["token"].query_one("#ctl-token").styles.background.hex6.lower() == FIELD_ALT_BG
        )

        def caption(field_id: str) -> str:
            return str(by_id[field_id].query_one(".field-label", Static).visual)

        assert caption("detail").startswith(BRANCH_LAST)
        assert not caption("token").startswith((BRANCH_LAST, BRANCH_MORE))


def test_the_two_row_tints_lean_on_different_channels() -> None:
    """Row ground: focus leans blue and a conditional question leans green, by construction.

    Two tints a few parts apart on one channel are one tint the reader cannot place, so the
    axes are asserted rather than the hexes - either lean may be retuned, but not onto the
    other's channel.

    The focus lean is measured from the first band alone, because there is one focus ground
    and not one per band: the plate under the cursor is the thing the reader is watching, and
    a plate that changed shade with the banding flickered on every press of an arrow.
    """

    def channels(colour: str) -> tuple[int, int, int]:
        return tuple(int(colour[i : i + 2], 16) for i in (1, 3, 5))

    _, base_green, base_blue = channels(ROW_BG)
    _, focus_green, focus_blue = channels(ROW_FOCUS_BG)
    assert focus_blue > base_blue and focus_green - base_green <= 1

    for band, cond in ((ROW_BG, ROW_COND_BG), (ROW_ALT_BG, ROW_ALT_COND_BG)):
        _, band_green, band_blue = channels(band)
        _, cond_green, cond_blue = channels(cond)
        assert cond_green > band_green and cond_blue < band_blue

    # the conditional lean survives the cursor, on the same axes and by the same amounts
    _, cond_focus_green, cond_focus_blue = channels(ROW_COND_FOCUS_BG)
    assert cond_focus_green - focus_green == 8
    assert focus_blue - cond_focus_blue == 6


async def test_a_banded_conditional_row_still_yields_its_grounds_to_the_cursor(
    tmp_path: Path,
) -> None:
    """Row ground: the cursor wins on a row wearing both classes, ground and control alike.

    Textual ranks by specificity first, and a row matching on two classes outranks the focus
    rule that matches on one - so the combination has to be spelled out or the focused row
    keeps its conditional tint and stops looking focused. The fixture's one conditional
    question always lands on the plain band, so the band is put on it here.
    """
    async with survey(tmp_path / "out") as (app, pilot):
        app.screen.set_focus(app.screen.query_one("#ctl-advanced", InlineOptions))
        await pilot.press("right")
        await pilot.pause()

        row = {r.question.id: r for r in rows(app)}["detail"]
        row.add_class(BAND)
        await pilot.pause()
        assert row.styles.background.hex6.lower() == ROW_ALT_COND_BG
        assert row.query_one("#ctl-detail").styles.background.hex6.lower() == FIELD_ALT_COND_BG

        app.screen.set_focus(row.query_one("#ctl-detail"))
        await pilot.pause()
        assert row.styles.background.hex6.lower() == ROW_COND_FOCUS_BG
        ground = row.query_one("#ctl-detail").styles.background.hex6.lower()
        assert ground == FIELD_COND_FOCUS_BG


async def test_the_focused_row_paints_the_blank_line_either_side_of_itself(
    tmp_path: Path,
) -> None:
    """Row ground: the spacing around the focused row belongs to the row, not to the gap.

    The blank lines are two widgets of the row's own rather than margin or padding. Margin
    sits outside the widget, so it took the form's ground and cut the plate into a strip with
    the screen showing through; padding took the ground but stayed empty, and a run of
    children has to cross it.
    """
    async with survey(tmp_path / "out") as (app, _):
        row = rows(app)[0]  # `name`, focused on mount
        rails = list(row.query(".field-rail"))
        assert len(rails) == 2
        assert all(rail.display for rail in rails)
        assert row.styles.margin.top == 0
        assert row.region.height == 3

        painted = {
            segment.style.bgcolor.triplet.hex.lower()
            for line in range(row.region.height)
            for segment in row.render_line(line)
            if segment.style and segment.style.bgcolor
        }
        assert painted == {ROW_FOCUS_BG}


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


async def test_the_run_crosses_the_blank_line_the_cursor_opens(tmp_path: Path) -> None:
    """Tree connectors: the spacing around the focused row does not break the run.

    The blank line the cursor opens either side of itself landed in the middle of a run of
    children and cut the column the connectors are read down. It carries the run now, and
    only where the run actually crosses it - the row above being a sibling or the question
    the child hangs from, and never below a last child.
    """
    async with survey(tmp_path / "out", template="tui_tree") as (app, pilot):

        def rails(field_id: str) -> list[str]:
            row = {r.question.id: r for r in rows(app)}[field_id]
            return [str(rail.visual) for rail in row.query(".field-rail")]

        app.screen.set_focus(app.screen.query_one("#ctl-bucket"))
        await pilot.pause()
        # the run comes down from the parent directly above, so the first child is not a gap
        assert rails("bucket") == [RAIL, RAIL]

        app.screen.set_focus(app.screen.query_one("#ctl-region"))
        await pilot.pause()
        assert rails("region") == [RAIL, ""]  # the run above a last child, nothing below it

        app.screen.set_focus(app.screen.query_one("#ctl-owner"))
        await pilot.pause()
        assert rails("owner") == ["", ""]  # a row in no run at all opens two blank lines


async def test_the_cursor_mark_blinks_on_the_bars_clock(tmp_path: Path) -> None:
    """Focus bar: the mark on the option row takes its colour from the row's own beat.

    Two things breathing on separate timers drift apart and read as two signals rather than
    one row being answered, so the row drives both and the mark never keeps a beat of its own.
    """
    async with survey(tmp_path / "out") as (app, pilot):
        row = {r.question.id: r for r in rows(app)}["advanced"]
        app.screen.set_focus(app.screen.query_one("#ctl-advanced", InlineOptions))
        await pilot.pause()

        def mark_ink() -> str:
            for line in range(max(1, row.size.height)):
                for segment in row.query_one("#ctl-advanced", InlineOptions).render_line(line):
                    if CURSOR in segment.text and segment.style and segment.style.color:
                        return segment.style.color.triplet.hex.lower()
            raise AssertionError("the cursor mark was never painted")

        # the beat is driven by hand here: the row's own timer keeps running through an
        # awaited pause, so a sampled cycle skips phases and misses the ends of the ramp
        row._pulse.stop()
        row._beat = 0
        seen = set()
        for _ in range(len(PULSE_CYCLE)):
            row._breathe()
            await pilot.pause()
            seen.add(mark_ink())
        assert seen == {shade.lower() for shade in MARK_SHADES}


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


def test_the_cursor_is_told_apart_from_the_option_it_sits_on() -> None:
    """Option chips: where the cursor is and what is chosen are separate at a glance.

    Both were painted in the same blue a shade apart, which measured 1.32:1 - a reader moving
    along a row could not see the cursor at all, because the only chip that changed changed
    into the colour the chosen chip already was. 3:1 is the floor for telling two interface
    surfaces apart, and it is asserted rather than eyeballed because the pair that failed it
    looked deliberate: the docstring beside them described an inversion the colours never had.
    """
    assert contrast(CURSOR_PICKED_BG, PICKED_BG) >= 3.0
    assert contrast(CURSOR_BG, OPTION_BG) >= 3.0


def test_every_ink_clears_the_floor_on_every_ground_it_lands_on() -> None:
    """Every pair the palette actually paints, held to 4.5:1 - not only the option chips.

    The typing grounds went unasserted, and one of them drifted below the floor when the
    conditional lean was applied to it: the orange answer measured 4.19:1 on the focused
    conditional field, which is the most important text in the app on the row it is being
    typed into. It was found by a reviewer, not by this suite.
    """
    for ink, ground in (
        (CURSOR_PICKED_FG, CURSOR_PICKED_BG),
        (CURSOR_FG, CURSOR_BG),
        (PICKED_FG, PICKED_BG),
        (OPTION_FG, OPTION_BG),
        (ANSWER_FG, FIELD_BG),
        (ANSWER_FG, FIELD_ALT_BG),
        (ANSWER_FG, FIELD_COND_BG),
        (ANSWER_FG, FIELD_ALT_COND_BG),
        (ANSWER_FOCUS_FG, FIELD_FOCUS_BG),
        (ANSWER_FOCUS_FG, FIELD_COND_FOCUS_BG),
    ):
        assert contrast(ink, ground) >= 4.5, f"{ink} on {ground} is {contrast(ink, ground):.2f}:1"


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


def test_the_breathing_bar_stays_visible_at_every_phase() -> None:
    """The bar is a graphical indicator, so its dimmest shade still clears 3:1 on its ground.

    The ramp used to reach `#12648b`: 2.50:1 on the focused ground and 2.34:1 on a conditional
    one. Four shades of seventeen fell under the floor, and the cosine spacing dwells at the
    ends, so the only thing saying which row the cursor is on spent about a fifth of every
    cycle below it. The docstring claimed the opposite, which is why this is asserted.
    """
    for ground in (ROW_FOCUS_BG, ROW_COND_FOCUS_BG):
        worst = min(contrast(shade, ground) for shade in PULSE_SHADES)
        assert worst >= 3.0, f"the bar drops to {worst:.2f}:1 on {ground}"


@pytest.mark.skipif(
    not Path("/home/lab/workspace/private/copier-data-science").is_dir(),
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
            assert ink["orders-api"] == CYAN_BRIGHT.lower()
            assert ink["1 of 3"] == CYAN_BRIGHT.lower()
            assert ink["tui_flow questionnaire"] != CYAN_BRIGHT.lower()


async def test_a_bool_row_names_no_key_it_does_not_need(tmp_path: Path) -> None:
    """Help: two options are read off the row itself, so naming the key that flips them is noise.

    A multiselect still names `space` - ticking is not visible in its options - and a choice
    still says the key cycles them. A switch says neither, having nothing the row does not show.
    """
    async with survey(tmp_path / "out") as (app, pilot):
        row = {r.question.id: r for r in rows(app)}["advanced"]
        app.screen.set_focus(row.query_one(InlineOptions))
        await pilot.pause()
        assert "space" not in str(row.query_one(".field-help", Static).visual)
