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
) -> list[int]:
    """The offsets to break `text` at so that every line fits `width` cells.

    Greedy, the way a terminal wraps: each line runs to the furthest break that still fits,
    and the ranking decides which break that is. A natural one wins; a fallback is reached
    only where the line holds no natural one; the fold is reached only where it holds
    neither, which is the single case Textual handles today.
    """
    if width <= 0:
        return []
    tab_sections = precomputed_tab_sections or get_tab_widths(text, min(tab_size, width))
    offsets = _cell_offsets(text, tab_sections)
    if offsets[-1] <= width:
        return []
    natural = _starts(text, NATURAL, space=True)
    fallback = _starts(text, FALLBACK)
    breaks: list[int] = []
    start = 0
    while offsets[-1] - offsets[start] > width:
        # the furthest offset that still fits. Equal widths bisect right, so a combining mark
        # stays on the line of the character it is drawn over
        room = bisect_right(offsets, offsets[start] + width) - 1
        end = _last_before(natural, start, room)
        if end is None and fold:
            # nothing natural on this line, so break inside the token: on its own punctuation
            # where it has any, character by character where it has none
            end = _last_before(fallback, start, room) or max(room, start + 1)
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


def install() -> None:
    """Put this wrapper in front of Textual's.

    `WrappedDocument` reads `compute_wrap_offsets` as a module global and offers no hook of
    its own, so that name is the whole seam - and both of its call sites read it, so
    replacing it is complete.
    """
    _wrapped_document.compute_wrap_offsets = compute_wrap_offsets
