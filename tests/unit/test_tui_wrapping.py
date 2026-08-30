"""Where a long answer breaks when it is wider than its box.

A template answer is a hostname, a path, or a comma-separated list of them, and Textual's own
wrapper folds any of those one character at a time, which cuts a value in half and reads as
two. The ladder asserted here is the fix: a break where the writer ended something, a break
inside a token only where the line offers none, a fold only where it offers neither.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from rich.cells import cell_len
from textual import content
from textual.widgets import Static, TextArea

from copier_tui import inline
from copier_tui.app import SurveyApp
from copier_tui.screens import ReviewScreen
from copier_tui.widgets import WrapInput
from copier_tui.wrapping import compute_wrap_offsets, divide_line
from copier_ui import TemplateUI

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

HOSTS = (
    "*.stellars-tech.eu,*.stellars-tech.com,stellars-tech.eu,"
    "*.lab.stellars-tech.eu,lab.stellars-tech.eu"
)
"""The answer that reported this: seven values, not one space between them."""


def _rich_lines(text: str, width: int) -> list[str]:
    """The lines rich itself draws `text` on, as the thing static text is measured against."""
    from rich._wrap import divide_line as rich_divide

    lines = []
    start = 0
    for offset in rich_divide(text, width, fold=True):
        lines.append(text[start:offset])
        start = offset
    lines.append(text[start:])
    return lines


def wrapped(text: str, width: int) -> list[str]:
    """The lines `text` is drawn on in a box `width` cells wide."""
    lines = []
    start = 0
    for offset in compute_wrap_offsets(text, width, tab_size=4):
        lines.append(text[start:offset])
        start = offset
    lines.append(text[start:])
    return lines


@asynccontextmanager
async def box(dst: Path) -> AsyncIterator[tuple[WrapInput, object]]:
    """The first text control of a running survey, ready to be written into."""
    with TemplateUI.from_template(str(FIXTURES / "tui_flow"), dst=dst) as ui:
        app = SurveyApp(ui, dst, {"quiet": True, "unsafe": True})
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            yield app.screen.query_one("#ctl-name", WrapInput), pilot


def test_a_list_of_values_breaks_where_the_writer_ended_one() -> None:
    """Natural break: after a comma, and nowhere inside the value it separates.

    This is the reported defect. Folded by cell count, the same answer read
    `stellars-tech.` on one line and `eu,*.lab.` on the next - a hostname split into two
    that each look real, in the one field where the reader is checking exactly that.
    """
    lines = wrapped(HOSTS, 52)

    assert lines == [
        "*.stellars-tech.eu,*.stellars-tech.com,",
        "stellars-tech.eu,*.lab.stellars-tech.eu,",
        "lab.stellars-tech.eu",
    ]
    assert all(cell_len(line) <= 52 for line in lines)


def test_prose_still_breaks_at_its_spaces() -> None:
    """Natural break: a space outranks nothing, so a sentence wraps as it always did.

    The ladder is only reached where a line holds no space; a caption or a sentence answer
    must come out of it unchanged.
    """
    assert wrapped("Every hostname the certificate should cover", 24) == [
        "Every hostname the ",
        "certificate should cover",
    ]


def test_a_token_wider_than_the_box_breaks_on_its_own_punctuation() -> None:
    """Fallback break: with no space and no comma on the line, `-` `.` and `/` are taken.

    Reached only here. Ranked with a comma they would break `stellars-tech.eu` by preference,
    which is the defect rather than the fix.
    """
    assert wrapped("*.nas.stellars-tech.example.eu", 12) == [
        "*.nas.",
        "stellars-",
        "tech.",
        "example.eu",
    ]
    assert wrapped("packages/copier_tui/wrapping.py", 12) == [
        "packages/",
        "copier_tui/",
        "wrapping.py",
    ]


def test_an_underscore_is_a_letter_and_never_a_break() -> None:
    """Fallback break: `_` joins words into one identifier, so it separates nothing.

    `_copier_conf_answers` is a single name. Breaking it reads as two, and the reader has no
    way to tell that from a name that really is hyphenated.
    """
    lines = wrapped("_copier_conf_answers_file", 12)

    assert lines == ["_copier_conf", "_answers_fil", "e"]
    assert not any(line.endswith("_") for line in lines[:-1])


def test_a_run_with_no_break_in_it_is_folded() -> None:
    """Last resort: a token offering nothing to break on is still cut to fit.

    Wide characters are counted in cells, not characters - six characters of Japanese fill a
    twelve-cell box, and counting them as six would overflow it by half.
    """
    assert wrapped("abcdefghijklmnopqrst", 8) == ["abcdefgh", "ijklmnop", "qrst"]
    assert wrapped("こんにちは世", 6) == ["こんに", "ちは世"]
    # a character wider than the whole box overruns its line rather than being given one
    # with nothing on it, which is what a box one cell wide does to the last of these
    assert wrapped("ab世", 1) == ["a", "b", "世"]


async def test_the_answer_box_wraps_on_the_ladder(tmp_path: Path) -> None:
    """The control mounted in the survey uses it, not Textual's wrapper.

    Textual takes no hook for this, so the wrapper is put in place by replacing the name its
    document reads. That is the kind of arrangement a version bump breaks silently, and the
    only thing that catches it is asserting the lines a real control is drawn on.
    """
    async with box(tmp_path / "out") as (control, pilot):
        control.text = HOSTS
        await pilot.pause()

        sections = control.wrapped_document.get_sections(0)

        assert sections[0].endswith(",")
        assert all(section.endswith(",") for section in sections[:-1])


def test_the_wrapper_answers_the_calls_textual_makes_of_it() -> None:
    """The contract Textual's own wrapper offers, since this stands in for it by name.

    Wrapping off is a width of nothing; a tab is as wide as the distance to its stop, not one
    cell; and folding off means an oversized token keeps its line and overruns it rather than
    being cut. Nothing in the survey reaches the last two, and an upgrade that started to
    would otherwise reach them untested.
    """
    assert compute_wrap_offsets("anything at all", 0, tab_size=4) == []
    assert wrapped("ab\tcdef ghij", 8) == ["ab\t", "cdef ", "ghij"]

    assert compute_wrap_offsets("aaaa bbbbbbbb cc", 4, tab_size=4, fold=False) == [5, 14]


@asynccontextmanager
async def prefilled(dst: Path, value: str, size: tuple[int, int]) -> AsyncIterator[Any]:
    """A survey over a one-question template whose answer is already `value`.

    Written as a template default rather than typed, because that is the path that carries a
    long answer in practice - a Jinja default, `--data`, or `recopy` seeding from the answers
    file - and the one where the control opens holding more than fits.
    """
    (dst / "template").mkdir(parents=True)
    (dst / "template" / "README.md").write_text("x\n")
    (dst / "copier.yml").write_text(
        f'_subdirectory: template\nhosts:\n  type: str\n  default: "{value}"\n'
    )
    with TemplateUI.from_template(str(dst), dst=dst / "out") as ui:
        app = SurveyApp(ui, dst / "out", {"quiet": True, "unsafe": True})
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            yield app, pilot


@pytest.mark.parametrize("size", [(100, 40), (70, 40), (60, 40)])
async def test_the_answer_box_is_as_tall_as_the_answer_needs(
    size: tuple[int, int], tmp_path: Path
) -> None:
    """ACC-TUI-135: the box shows every line it wraps onto, and shows them from the first.

    It used to stop at three, which cost the reader the rest - and cost them the head rather
    than the tail, because the cursor opens at the end of a prefilled value, so the box was
    already scrolled past the beginning before anything was typed. Both go away together:
    a box the height of its own content has nothing to scroll.
    """
    async with prefilled(tmp_path, HOSTS, size) as (app, _):
        control = app.screen.query_one("#ctl-hosts", WrapInput)
        sections = control.wrapped_document.get_sections(0)

        assert control.size.height == len(sections), "the box is not the height of its answer"
        assert control.scroll_offset.y == 0, "the box opened past the start of the answer"


async def test_a_document_answer_keeps_its_cap(tmp_path: Path) -> None:
    """The exception: a multiline answer is scrolled, not grown.

    An answer is a sentence and is read whole; a `multiline` or `type: json` answer is a
    document, and letting one grow without limit pushes every question below it off the form.
    """
    (tmp_path / "template").mkdir(parents=True)
    (tmp_path / "template" / "README.md").write_text("x\n")
    (tmp_path / "copier.yml").write_text(
        "_subdirectory: template\n"
        'notes:\n  type: str\n  multiline: true\n  default: "' + r"\n".join("l" * 9) + '"\n'
    )
    with TemplateUI.from_template(str(tmp_path), dst=tmp_path / "out") as ui:
        app = SurveyApp(ui, tmp_path / "out", {"quiet": True, "unsafe": True})
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            editor = app.screen.query_one("#ctl-notes", TextArea)

            assert "field-doc" in editor.classes
            assert editor.size.height == 6
            assert editor.virtual_size.height > editor.size.height


@pytest.mark.parametrize("size", [(80, 40), (60, 40)])
async def test_the_review_screen_wraps_on_the_ladder_too(
    size: tuple[int, int], tmp_path: Path
) -> None:
    """The last screen before a write breaks an answer where the writer ended a value.

    Textual wraps in two places that share nothing: an editor through `WrappedDocument`, and
    every `Static` through `Content`, which holds its own import of rich's `divide_line`.
    Replacing only the first left the review folding a hostname in half on the one screen
    whose whole job is to be checked - which is the screen where two hostnames that each look
    real do the most damage.
    """
    async with prefilled(tmp_path, HOSTS, size) as (app, pilot):
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ReviewScreen)

        value = app.screen.query_one(".review-value", Static)
        drawn = [
            "".join(segment.text for segment in value.render_line(row)).rstrip()
            for row in range(value.size.height)
        ]

        assert all(line.endswith(",") for line in drawn[:-1]), drawn
        assert "".join(drawn) == HOSTS


def test_the_option_rows_keep_the_wrapper_that_measures_them() -> None:
    """What the patch deliberately leaves alone.

    An option list folds its chips with rich's own `divide_line` and reserves its height by
    counting the same folds. Both sides have to move together or the list reserves a height
    it does not paint, so the module that does the counting keeps the wrapper it counts with.
    """
    from rich._wrap import divide_line

    assert inline.divide_line is divide_line
    assert content.divide_line is not divide_line


def test_static_text_hangs_its_trailing_space_the_way_rich_does() -> None:
    """A line's trailing space hangs past the edge rather than taking a cell of it.

    Counted, a word ending exactly at the edge is pushed to the next line and every line
    comes out one word short. Over the three-line caption box that costs the last line: at a
    60-column terminal the caption gutter is 30 cells, and this question wrapped to four
    lines where rich wraps it to three, so `exported skills)` was cut off the question the
    reader is being asked.
    """
    caption = (
        "Scaffold an agents/ folder for deployable agentic resources (workflows, exported skills)"
    )

    drawn = []
    start = 0
    for offset in divide_line(caption, 30):
        drawn.append(caption[start:offset])
        start = offset
    drawn.append(caption[start:])

    assert drawn == [
        "Scaffold an agents/ folder for ",
        "deployable agentic resources ",
        "(workflows, exported skills)",
    ]
    assert drawn == _rich_lines(caption, 30)


def test_an_editor_still_counts_the_space_its_cursor_can_sit_on() -> None:
    """The hanging rule is the static text convention and stops there.

    Textual measures an editor's box with the trailing space counted, and the cursor can be
    put on it, so the wrapper Textual's own document reads keeps counting it. The two
    conventions belong to two hosts, not to two opinions.
    """
    assert wrapped("aaa bbbb cc", 8) == ["aaa ", "bbbb cc"]
    assert _rich_lines("aaa bbbb cc", 8) == ["aaa bbbb ", "cc"]


@pytest.mark.parametrize("chars", [250, 600])
async def test_typing_past_the_fold_brings_the_form_with_it(chars: int, tmp_path: Path) -> None:
    """ACC-TUI-135's other half: the row grows with the answer AND the form scrolls.

    A box is as tall as its answer, so the caret's row is a row of the form and the box has
    nothing left to scroll. Textual scrolls a widget into view when the focus moves and never
    again, so at 60x18 a 250-character answer put the typed characters on no row at all -
    they were in the value and nowhere on screen. The height tests run at 40 rows, which is
    why nothing else in the suite can see this.
    """
    words = "machine learning pipeline predicting customer churn behavioural telemetry "
    (tmp_path / "template").mkdir(parents=True)
    (tmp_path / "template" / "README.md").write_text("x\n")
    (tmp_path / "copier.yml").write_text(
        "_subdirectory: template\n"
        f'description:\n  type: str\n  default: "{(words * 9)[:chars].strip()}"\n'
    )
    with TemplateUI.from_template(str(tmp_path), dst=tmp_path / "out") as ui:
        app = SurveyApp(ui, tmp_path / "out", {"quiet": True, "unsafe": True})
        async with app.run_test(size=(60, 18)) as pilot:
            await pilot.pause()
            control = app.screen.query_one("#ctl-description", WrapInput)
            form = app.screen.query_one("#survey-form")
            control.focus()
            await pilot.pause()
            control.move_cursor(control.document.end)
            await pilot.pause()

            await pilot.press("X")
            await pilot.pause()

            view = form.content_region
            caret = control.cursor_screen_offset.y
            assert control.size.height > view.height, "the answer is not taller than the form"
            assert view.y <= caret < view.bottom, (
                f"caret at {caret}, form shows {view.y}-{view.bottom - 1}"
            )


async def test_an_editor_nobody_is_typing_in_does_not_drag_the_form(tmp_path: Path) -> None:
    """The scroll follows the caret only while the editor has the focus.

    `FieldRow.update` rewrites every control whenever any answer changes, which puts each
    editor's caret back at the end of its own value. Unguarded, every one of those pulled the
    form to a row nobody was looking at, and walking the form stopped keeping its place.
    """
    words = "machine learning pipeline predicting customer churn behavioural telemetry "
    (tmp_path / "template").mkdir(parents=True)
    (tmp_path / "template" / "README.md").write_text("x\n")
    (tmp_path / "copier.yml").write_text(
        "_subdirectory: template\n"
        "top:\n  type: str\n  default: short\n"
        f'far:\n  type: str\n  default: "{(words * 9)[:400].strip()}"\n'
    )
    with TemplateUI.from_template(str(tmp_path), dst=tmp_path / "out") as ui:
        app = SurveyApp(ui, tmp_path / "out", {"quiet": True, "unsafe": True})
        async with app.run_test(size=(60, 18)) as pilot:
            await pilot.pause()
            top = app.screen.query_one("#ctl-top", WrapInput)
            far = app.screen.query_one("#ctl-far", WrapInput)
            form = app.screen.query_one("#survey-form")
            top.focus()
            await pilot.pause()
            resting = form.scroll_offset.y

            # the caret of the long unfocused answer, put back where FieldRow.update puts it
            far.move_cursor(far.document.end)
            far.scroll_cursor_visible()
            await pilot.pause()

            assert far.size.height > form.content_region.height, "the other answer is not long"
            assert form.scroll_offset.y == resting, "an unfocused editor moved the form"
