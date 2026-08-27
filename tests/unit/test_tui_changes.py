"""The before/after account of a render: added, changed, deleted, conflicted."""

from __future__ import annotations

from pathlib import Path

from copier_tui.changes import diff, snapshot


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
