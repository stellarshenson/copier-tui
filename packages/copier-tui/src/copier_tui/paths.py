"""How a destination is written on screen."""

from __future__ import annotations

from pathlib import Path

from rich.cells import cell_len


def shown_path(dst: Path) -> str:
    """The destination as a person can act on it: absolute, home-relative where that is shorter.

    `update` and `recopy` default their destination to the current directory, which arrives
    here as a bare `.` - a name for the one place the reader is already standing, and the one
    name they cannot check anything against. Resolving it says which project this is. The `~`
    prefix keeps that answer short, because the part it stands in for is the part already
    known; the tail is the part that identifies the project.
    """
    # both sides are resolved or neither comparison holds: a home reached through a symlink -
    # `/home/user` pointing at `/Users/user`, or at a mounted volume, which is the normal
    # layout on macOS and in many containers - resolves on the destination's side only, and
    # then never matches, so the `~` shortening quietly does nothing for those users
    try:
        home = str(Path.home().resolve())
    except RuntimeError:
        # no HOME and no passwd entry - a container running as an arbitrary uid. There is
        # nothing to shorten against, and `expanduser` would raise the same way
        return str(Path(dst).resolve())
    shown = str(Path(dst).expanduser().resolve())
    if shown == home:
        return "~"
    if shown.startswith(home + "/"):
        return "~" + shown[len(home) :]
    return shown


PREFIX = ".../"
"""What marks a path that has had its leading components dropped.

Three ASCII dots rather than `\u2026`, whose East Asian width is ambiguous - a terminal set to
render such characters wide would give it two cells where Rich counts one."""


def _tail(text: str, limit: int) -> str:
    """The last `limit` CELLS of `text`.

    `set_cell_size` crops to a width but keeps the HEAD, which is the end this module exists
    to throw away. A character whose cell would straddle the limit is dropped rather than
    half-painted, so the result can come back one cell short - never one over.
    """
    kept: list[str] = []
    used = 0
    for char in reversed(text):
        width = cell_len(char)
        if used + width > limit:
            break
        kept.append(char)
        used += width
    return "".join(reversed(kept))


def fit_path(dst: Path, limit: int) -> str:
    """`shown_path`, shortened from the LEFT when it is longer than `limit`.

    Cropping a path from the right is cropping off the answer. The head is the part the reader
    already knows - a temp directory, a workspace root - and the tail is the part that says
    which project this is, so an ellipsis at the end leaves them holding the half that
    identifies nothing. This drops leading components instead.

    Measured in CELLS, not characters: the limit is terminal columns, and a path with CJK or
    emoji in it counted by characters comes back wider than the row it was fitted to - after
    which the stylesheet's right-hand ellipsis takes the project name, which is the outcome
    this function exists to prevent. The option list had the same confusion; this module was
    written in the same change and inherited it.

    The head is dropped, marked with a leading ellipsis, and whole components are kept rather
    than cutting one in half - except where not one whole component fits, when it cuts the
    tail of the last one rather than returning something longer than the limit it was asked
    for.
    """
    shown = shown_path(dst)
    if cell_len(shown) <= limit:
        return shown
    if limit <= len(PREFIX):
        # no room for the marker and anything worth marking; the tail alone is the best answer
        return _tail(shown, limit) if limit > 0 else ""
    kept: list[str] = []
    # the prefix costs four characters and has to come out of the budget, or the result is
    # longer than the limit it was given - and on a path with no separators to cut at, longer
    # than the path itself
    room = max(limit - len(PREFIX), 1)
    for part in reversed(shown.split("/")):
        candidate = "/".join([part, *kept])
        if cell_len(candidate) > room:
            break
        kept.insert(0, part)
    if not kept:
        return PREFIX + _tail(shown, room)
    return PREFIX + "/".join(kept)
