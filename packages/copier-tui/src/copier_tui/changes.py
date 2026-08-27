"""What a render did to the destination, told by comparing before with after.

copier writes the tree and reports nothing back, so the only account of a run is the
directory itself. A snapshot before the render and one after give the four numbers a
person wants at the end: added, changed, deleted, and left with a conflict to resolve.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path

SNAPSHOT_LIMIT = 5000
"""Files a snapshot stops at, so a huge tree cannot stall the screen before or after a run."""

CONFLICT_MARKER = b"<<<<<<< "
"""How an inline conflict starts. copier's `--conflict inline` writes these; the default
`rej` mode writes a `.rej` file beside the path instead, and both count."""


@dataclass(frozen=True)
class Changes:
    """The render's effect on the destination, as relative paths."""

    added: tuple[str, ...] = ()
    changed: tuple[str, ...] = ()
    deleted: tuple[str, ...] = ()
    conflicted: tuple[str, ...] = field(default=())


def snapshot(dst: Path) -> dict[str, tuple[str, bool]]:
    """Every file under `dst` → (content digest, whether it holds a conflict marker).

    Directories are not entries: a directory is only what its files make it. `.git` is
    pruned before it is entered, for the same reason the file watcher prunes it.
    """
    found: dict[str, tuple[str, bool]] = {}
    if not dst.is_dir():
        return found
    for top, dirs, files in os.walk(dst):
        dirs[:] = sorted(d for d in dirs if d != ".git")
        rel = Path(top).relative_to(dst)
        for name in sorted(files):
            path = Path(top) / name
            try:
                data = path.read_bytes()
            except OSError:
                continue
            digest = hashlib.blake2b(data, digest_size=16).hexdigest()
            found[str(rel / name)] = (digest, CONFLICT_MARKER in data)
            if len(found) >= SNAPSHOT_LIMIT:
                return found
    return found


def diff(before: dict[str, tuple[str, bool]], after: dict[str, tuple[str, bool]]) -> Changes:
    """What changed between two snapshots.

    A conflict is a `.rej` file, or a file whose content carries an inline marker - counted
    once per path, and reported against the file the person has to open. A `.rej` is not
    also an addition: it is the conflict's own artefact, not part of the project.
    """
    rejects = {p for p in after if p.endswith(".rej")}
    conflicted = sorted(
        {p[: -len(".rej")] for p in rejects} | {p for p, (_, m) in after.items() if m}
    )
    added = sorted(p for p in after if p not in before and p not in rejects)
    deleted = sorted(p for p in before if p not in after and p not in rejects)
    changed = sorted(
        p for p in after if p in before and before[p][0] != after[p][0] and p not in rejects
    )
    return Changes(tuple(added), tuple(changed), tuple(deleted), tuple(conflicted))
