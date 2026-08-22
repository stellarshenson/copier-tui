"""Purity and Sync API criteria: no display library, no event loop, no coroutines."""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
import subprocess
import sys
import threading

import pytest
from ui_support import load

import copier_ui
from copier_ui import TemplateUI

DISPLAY_MODULES = ("textual", "rich", "prompt_toolkit", "curses", "blessed")

_PROBE = """
import json, sys, importlib
importlib.import_module(sys.argv[1])
roots = {name.partition('.')[0] for name in sys.modules}
print(json.dumps(sorted(roots & set(json.loads(sys.argv[2])))))
"""


def _imported_display_modules(module: str, names: tuple[str, ...]) -> list[str]:
    """Import one module in a fresh interpreter and report which of names it pulled in."""
    result = subprocess.run(
        [sys.executable, "-c", _PROBE, module, json.dumps(list(names))],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_purity_imports_no_display_library() -> None:
    """Purity: copier_ui adds no display library to what copier itself already loads.

    copier_ui wraps copier, and ``import copier`` alone pulls in prompt_toolkit through
    questionary. That is copier's dependency, not copier_ui's, and copier_ui cannot drop it
    without deferring the copier import into function bodies, which would hide the dependency
    rather than remove it. So the assertion is the delta: whatever copier brings is copier's,
    everything else is copier_ui's and must be empty. textual, rich, curses and blessed are
    forbidden outright, since copier loads none of them.
    """
    loaded = _imported_display_modules("copier_ui", DISPLAY_MODULES)
    via_copier = _imported_display_modules("copier", DISPLAY_MODULES)
    assert via_copier == ["prompt_toolkit"], (
        f"copier's own display imports changed to {via_copier}; revisit this exemption"
    )
    assert sorted(set(loaded) - set(via_copier)) == [], (
        f"'import copier_ui' loaded {loaded}, beyond the {via_copier} copier itself loads"
    )
    assert [name for name in loaded if name != "prompt_toolkit"] == []


def test_purity_copier_ui_source_never_imports_a_display_library() -> None:
    """Purity: no copier_ui module names a display library in its own source."""
    package = Path(copier_ui.__file__).parent
    offenders = [
        f"{module.name}: {name}"
        for module in sorted(package.glob("*.py"))
        for name in DISPLAY_MODULES
        if f"import {name}" in module.read_text()
    ]
    assert offenders == []


def test_sync_api_has_no_coroutine_entry_points() -> None:
    """Sync API: every public TemplateUI call is an ordinary function."""
    public = [
        member
        for name, member in inspect.getmembers(TemplateUI, callable)
        if not name.startswith("_")
    ]
    assert public
    assert [m for m in public if inspect.iscoroutinefunction(m)] == []
    assert [m for m in public if inspect.isasyncgenfunction(m)] == []


def test_sync_api_runs_without_an_event_loop_or_extra_threads(tmp_path: Path) -> None:
    """Sync API: a load, a set and a validate need no running loop and start no thread."""
    with pytest.raises(RuntimeError):
        asyncio.get_running_loop()
    before = threading.active_count()
    with load("ui_deps", tmp_path / "dst") as ui:
        ui.set("use_docker", True)
        ui.validate()
        ui.answers()
    assert threading.active_count() == before
