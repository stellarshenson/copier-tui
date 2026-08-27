"""How a destination is written on screen, wherever a screen writes one."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from copier_tui.paths import fit_path, shown_path


def test_the_current_directory_is_named_rather_than_pointed_at(tmp_path: Path) -> None:
    """`update` defaults its destination to `.`, which names nothing the reader can check.

    A bare dot is the one place the reader is already standing. Resolved, it says which
    project the answers are about to land in - the only reason the line is on screen.
    """
    here = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert shown_path(Path(".")) == str(tmp_path.resolve())
    finally:
        os.chdir(here)


def test_a_path_under_home_is_written_home_relative() -> None:
    """The prefix a person already knows is replaced by the character that stands for it."""
    assert shown_path(Path.home() / "work" / "thing") == "~/work/thing"
    assert shown_path(Path.home()) == "~"


def test_a_path_outside_home_is_written_whole(tmp_path: Path) -> None:
    """Nothing to shorten, so nothing is shortened."""
    assert shown_path(tmp_path) == str(tmp_path.resolve())


def test_a_destination_that_does_not_exist_yet_still_resolves(tmp_path: Path) -> None:
    """`copy` names a directory that is not there yet, and it is still a path to show."""
    assert shown_path(tmp_path / "not-made-yet") == str(tmp_path.resolve() / "not-made-yet")


def test_a_relative_path_is_resolved_against_the_working_directory(tmp_path: Path) -> None:
    """`copier-tui copy <template> ../elsewhere` is as unreadable as a bare dot."""
    here = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert shown_path(Path("./sub/dir")) == str(tmp_path.resolve() / "sub" / "dir")
    finally:
        os.chdir(here)


@pytest.mark.parametrize(
    "path",
    [
        "/a/b/c/d/e/f/g/h/i/j/k/l/m/n/o/p",
        "/" + "x" * 40,
        "/tmp",
        "/",
        "/tmp/tmpsznj1zlq/customer-churn-prediction-pipeline",
    ],
)
@pytest.mark.parametrize("limit", [0, 1, 4, 5, 12, 20, 47, 200])
def test_a_fitted_path_never_outgrows_the_room_it_was_given(path: str, limit: int) -> None:
    """`fit_path` returns at most `limit` characters, and never more than it was handed.

    The first version budgeted two characters for a prefix that costs four, and let the last
    component in whatever its length - so it could return a string longer than its limit, and
    on a path with no separators longer than the path itself.
    """
    fitted = fit_path(Path(path), limit)
    assert len(fitted) <= max(limit, 0), f"{fitted!r} is longer than {limit}"
    assert len(fitted) <= len(shown_path(Path(path))), f"{fitted!r} grew its input"


def test_a_fitted_path_keeps_the_end_and_marks_what_it_dropped() -> None:
    """What survives is the tail, and a leading marker says the head was cut."""
    fitted = fit_path(Path("/one/two/three/four/five/my-project"), 24)
    assert fitted.endswith("my-project"), fitted
    assert fitted.startswith("..."), fitted
    assert "…" not in fitted, "the marker must be ASCII - U+2026 is ambiguous width"
