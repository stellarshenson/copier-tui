"""copier_tui holds no semantics: it reads copier_ui state and nothing else."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import copier_tui

PACKAGE = Path(copier_tui.__file__).parent
MODULES = sorted(PACKAGE.rglob("*.py"))


def imported_roots(module: Path) -> set[str]:
    """The top-level names a module imports."""
    roots: set[str] = set()
    for node in ast.walk(ast.parse(module.read_text())):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_the_package_was_found() -> None:
    """The scan below is worth nothing if it looked at no files."""
    assert len(MODULES) >= 8


@pytest.mark.parametrize("module", MODULES, ids=lambda path: path.name)
def test_no_module_parses_a_template(module: Path) -> None:
    """No yaml parser and no Jinja environment: copier.yml is copier_ui's business."""
    assert {"yaml", "jinja2"}.isdisjoint(imported_roots(module))


def test_only_the_cli_touches_copier() -> None:
    """copier reaches copier_tui through copier_ui, except for the CLI it subclasses."""
    importers = {module.name for module in MODULES if "copier" in imported_roots(module)}
    assert importers == {"cli.py"}
