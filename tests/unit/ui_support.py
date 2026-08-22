"""Shared helpers for the copier_ui unit tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import subprocess
from typing import Any

from copier_ui import TemplateUI

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@contextmanager
def load(name: str, dst: Path, **kwargs: Any) -> Iterator[TemplateUI]:
    """Load a fixture template by directory name and close it afterwards."""
    ui = TemplateUI.from_template(str(FIXTURES / name), dst=dst, **kwargs)
    try:
        yield ui
    finally:
        ui.close()


def git_template(root: Path) -> Path:
    """Make a two-tag git repository template, the local stand-in for a remote URL."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "template").mkdir()
    (root / "template" / "out.txt.jinja").write_text("{{ name }}\n")
    config = root / "copier.yml"
    git = ["git", "-c", "user.email=t@example.com", "-c", "user.name=t"]
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for tag, default in (("v1.0.0", "one"), ("v2.0.0", "two")):
        config.write_text(f"_subdirectory: template\n\nname:\n  type: str\n  default: {default}\n")
        subprocess.run([*git, "-C", str(root), "add", "-A"], check=True)
        subprocess.run([*git, "-C", str(root), "commit", "-qm", tag], check=True)
        subprocess.run([*git, "-C", str(root), "tag", tag], check=True)
    return root
