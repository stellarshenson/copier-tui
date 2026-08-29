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

from rich.cells import cell_len

from copier_tui.app import SurveyApp
from copier_tui.widgets import WrapInput
from copier_tui.wrapping import compute_wrap_offsets
from copier_ui import TemplateUI

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

HOSTS = (
    "*.stellars-tech.eu,*.stellars-tech.com,stellars-tech.eu,"
    "*.lab.stellars-tech.eu,lab.stellars-tech.eu"
)
"""The answer that reported this: seven values, not one space between them."""


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
