"""Render criteria: copier is called with the answers, and refuses an invalid state."""

from __future__ import annotations

from pathlib import Path

import pytest
from ui_support import load

from copier_ui import RenderRefusedError


def test_render_hands_the_answers_to_copier_as_data(tmp_path: Path) -> None:
    """Render: run_copy receives data=answers, so nothing is prompted and the answer lands."""
    dst = tmp_path / "dst"
    with load("ui_deps", dst) as ui:
        ui.set("project", "written")
        ui.render(quiet=True)
    assert (dst / "out.txt").read_text().strip() == "written"


def test_render_accepts_an_explicit_destination_and_copier_kwargs(tmp_path: Path) -> None:
    """Render: the destination argument and copier keyword arguments both reach copier."""
    dst = tmp_path / "elsewhere"
    with load("ui_deps", tmp_path / "dst") as ui:
        ui.render(dst, quiet=True, pretend=True)
    assert not dst.exists()


def test_render_refuses_an_invalid_state_and_names_the_fields(tmp_path: Path) -> None:
    """Edge: render with an invalid state - refused, offending fields named, nothing written."""
    dst = tmp_path / "dst"
    with load("ui_deps", dst) as ui:
        ui.set("use_docker", True)
        ui.set("port", 80)
        with pytest.raises(RenderRefusedError) as caught:
            ui.render(quiet=True)
    assert list(caught.value.errors) == ["port"]
    assert "port" in str(caught.value)
    assert not dst.exists()
