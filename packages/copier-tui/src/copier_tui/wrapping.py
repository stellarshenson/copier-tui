"""Where an answer breaks when it is wider than its box.

Textual breaks at whitespace and folds anything holding none one character at a time. A
template answer is rarely prose - it is a hostname, a path, or a comma-separated list of
them - so the fold cut `stellars-tech.eu` into `stellars-tech.` and `eu`, which reads as two
values where the writer put one. This ranks the places a line may end instead, in the order
CSS ranks them: the ordinary opportunities first, the ones inside a word only where the line
offers none, and the fold only where it offers neither.
"""

from __future__ import annotations

from bisect import bisect_right

from rich.cells import get_character_cell_size
from textual import content
from textual.document import _wrapped_document
from textual.expand_tabs import get_tab_widths

NATURAL = ","
"""Breaks ranked with a space, because they end something.

A comma separates the items of every template answer that holds more than one, so a line
ending on one ends where the writer already ended a value."""

FALLBACK = "-./"
"""Breaks taken only where the line offers no natural one.

Inside a token these are part of the word: `stellars-tech.eu` and `src/main` are each one
thing, and breaking them by preference is the defect this module exists for. They are a way
of not folding, not a place to end a line. `_` is absent on purpose - it joins words into a
single identifier and never separates two."""


def _cell_offsets(text: str, tab_sections: list[tuple[str, int]]) -> list[int]:
    """The width of every prefix of `text`: entry `i` is what `text[:i]` occupies in cells.

    Cells rather than characters, and a table rather than a measurement per candidate: a tab
    is as wide as the distance to its stop, an emoji is two cells, a combining mark is none,
    and each of them has to be counted where it actually falls.
    """
    offsets = [0]
    total = 0
    for section, tab_width in tab_sections:
        for character in section:
            total += get_character_cell_size(character)
            offsets.append(total)
        if tab_width:
            total += tab_width
            offsets.append(total)
    return offsets


def _ink_offsets(text: str, offsets: list[int]) -> list[int]:
    """`offsets` with each prefix's own trailing whitespace discounted.

    A line's trailing space hangs past the edge rather than occupying a cell of it - the rule
    every wrapper outside an editor keeps, `rich` included. Measured with the space counted, a
    word that ends exactly at the edge is pushed to the next line and every line comes out one
    word short; over a three-line box that costs the last line, and the caption is cut.
    """
    ink = [0]
    for index, character in enumerate(text):
        ink.append(ink[index] if character.isspace() else offsets[index + 1])
    return ink


def _starts(text: str, after: str, *, space: bool = False) -> list[int]:
    """The offsets a line may start at, given the characters a break may follow.

    A line never starts on a blank, so the whitespace a break leaves behind stays on the line
    it ended, the way every wrapper leaves it.
    """
    return [
        index
        for index in range(1, len(text))
        if not text[index].isspace()
        and (text[index - 1] in after or (space and text[index - 1].isspace()))
    ]


def _last_before(starts: list[int], start: int, room: int) -> int | None:
    """The furthest of `starts` that opens a line after `start` and still fits in `room`."""
    index = bisect_right(starts, room)
    if index and starts[index - 1] > start:
        return starts[index - 1]
    return None


def _first_after(starts: list[int], start: int) -> int | None:
    """The first of `starts` past `start`, whether it fits or not."""
    index = bisect_right(starts, start)
    return starts[index] if index < len(starts) else None


def compute_wrap_offsets(
    text: str,
    width: int,
    tab_size: int,
    fold: bool = True,
    precomputed_tab_sections: list[tuple[str, int]] | None = None,
    *,
    hang: bool = False,
) -> list[int]:
    """The offsets to break `text` at so that every line fits `width` cells.

    Greedy, the way a terminal wraps: each line runs to the furthest break that still fits,
    and the ranking decides which break that is. A natural one wins; a fallback is reached
    only where the line holds no natural one; the fold is reached only where it holds
    neither, which is the single case Textual handles today.

    `hang` decides whether a line's trailing space occupies a cell of the width or hangs past
    it. An editor counts it, because the cursor can sit on it and Textual measures the box
    that way; static text does not, because `rich` does not, and a line that counted it would
    come out a word short of the one beside it drawn by anything else.
    """
    if width <= 0:
        return []
    tab_sections = precomputed_tab_sections or get_tab_widths(text, min(tab_size, width))
    offsets = _cell_offsets(text, tab_sections)
    fit = _ink_offsets(text, offsets) if hang else offsets
    if fit[-1] <= width:
        return []
    natural = _starts(text, NATURAL, space=True)
    fallback = _starts(text, FALLBACK)
    breaks: list[int] = []
    start = 0
    while fit[-1] - offsets[start] > width:
        # the furthest offset that still fits. Equal widths bisect right, so a combining mark
        # stays on the line of the character it is drawn over
        limit = offsets[start] + width
        room = bisect_right(fit, limit) - 1
        end = _last_before(natural, start, room)
        if end is None and fold:
            # nothing natural on this line, so break inside the token: on its own punctuation
            # where it has any, character by character where it has none. The fold counts every
            # cell - there is no trailing space in the middle of a word to hang
            end = _last_before(fallback, start, room) or max(
                bisect_right(offsets, limit) - 1, start + 1
            )
        if end is None:
            # folding off - the token keeps its line and overruns it, breaking at the next
            # natural opportunity, because that is the whole of what folding off asks for
            end = _first_after(natural, start)
        if end is None or end >= len(text):
            # a last character wider than the whole box overruns its line; giving it one of
            # its own would leave the line before it empty
            break
        breaks.append(end)
        start = end
    return breaks


def divide_line(text: str, width: int, fold: bool = True) -> list[int]:
    """The same offsets under the name, signature and spacing rule `rich` wraps static text by.

    The tab stop is the conventional 8 and is never read: `Content` expands every tab before
    it calls this, so no text arriving here holds one.
    """
    return compute_wrap_offsets(text, width, 8, fold, hang=True)


def install() -> None:
    """Put this wrapper in front of the two Textual wraps at once.

    Textual wraps text in two places that share nothing. An editor goes through
    `WrappedDocument`, which reads `compute_wrap_offsets` as a module global; everything
    else - a `Static`, a `Label`, the review screen's answers - goes through `Content`,
    which holds its own import of `rich`'s `divide_line` and reads that. Neither offers a
    hook, so the names are the seam, and both have to be replaced: patching only the editor
    left the review screen folding a hostname in half on the last screen before a write.

    What this does not reach, deliberately: `inline.py` calls `rich`'s `divide_line` by
    the name it imported, so an option list keeps folding the way the count that reserves
    its height measures it, and the two cannot disagree.

    What it does reach, and must: every caption on the survey. Only a conditional question's
    caption is pre-wrapped by `textwrap`, because its tree connector has to be carried down
    the lines it wraps onto; every other caption is handed over whole and wrapped here, in a
    box three lines tall - which is the box a line ending one word short overflows.
    """
    _wrapped_document.compute_wrap_offsets = compute_wrap_offsets
    content.divide_line = divide_line
