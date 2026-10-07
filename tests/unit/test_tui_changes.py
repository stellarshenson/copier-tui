"""The before/after account of a render: added, changed, deleted, conflicted."""

from __future__ import annotations

from pathlib import Path

from copier_tui.changes import Changes, diff, snapshot
from copier_tui.screens.execution import BANNER_ROLES, _counts_line


def test_the_four_counts_come_from_the_directory_alone(tmp_path: Path) -> None:
    """A run that adds, edits, removes and conflicts is read back as exactly those four."""
    (tmp_path / "keep.txt").write_text("same\n")
    (tmp_path / "edit.txt").write_text("old\n")
    (tmp_path / "gone.txt").write_text("bye\n")
    (tmp_path / "merge.txt").write_text("clean\n")
    before = snapshot(tmp_path)

    (tmp_path / "new.txt").write_text("hello\n")
    (tmp_path / "edit.txt").write_text("new\n")
    (tmp_path / "gone.txt").unlink()
    (tmp_path / "merge.txt").write_text("<<<<<<< before updating\nx\n=======\ny\n>>>>>>> after\n")
    (tmp_path / "other.txt").write_text("fine\n")
    (tmp_path / "other.txt.rej").write_text("--- a\n+++ b\n")
    changes = diff(before, snapshot(tmp_path))

    assert changes.added == ("new.txt", "other.txt")
    assert changes.changed == ("edit.txt", "merge.txt")
    assert changes.deleted == ("gone.txt",)
    assert changes.conflicted == ("merge.txt", "other.txt")


def test_git_is_not_part_of_the_account(tmp_path: Path) -> None:
    """copier's own git work under `.git` is neither added nor changed."""
    (tmp_path / ".git" / "objects").mkdir(parents=True)
    (tmp_path / ".git" / "objects" / "ab").write_bytes(b"x")
    assert snapshot(tmp_path) == {}


def test_a_missing_destination_is_an_empty_snapshot(tmp_path: Path) -> None:
    """`copy` into a directory that does not exist yet starts from nothing."""
    assert snapshot(tmp_path / "absent") == {}


def test_what_went_wrong_is_printed_in_the_error_ink() -> None:
    """Banner: deleted files, conflicts and the conflicted paths are text, so they take `error`.

    They were printed in `rose`, the failure colour. In the dark theme it is 3.87:1 on the
    banner and 3.50:1 on the file list, under the 4.5:1 floor every other text ink is held to.
    """
    assert "error" in BANNER_ROLES and "rose" not in BANNER_ROLES
    ink = {role: f"ink-{role}" for role in BANNER_ROLES}
    text = _counts_line(Changes(deleted=("gone.txt",), conflicted=("merge.txt",)), ink)
    styles = {text.plain[span.start : span.end].strip(): str(span.style) for span in text.spans}
    assert styles["1 deleted"] == "ink-error"
    assert styles["1 conflict"] == "bold ink-error"
    assert styles["merge.txt"] == "ink-error"
