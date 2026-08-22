"""Edge criteria: broken types, cycles, forward references, empty and missing templates."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest
from ui_support import FIXTURES, load

from copier_ui import CircularDependencyError, TemplateLoadError, TemplateUI, UnknownFieldError


def test_edge_unknown_type_is_a_load_error_on_the_question(tmp_path: Path) -> None:
    """Edge: unknown type - reported as a field load error naming the id, not a crash."""
    with load("ui_badtype", tmp_path / "dst") as ui:
        question = ui.schema().by_id("wrong")
        assert question.load_error is not None
        assert question.load_error.startswith("wrong: ")
        assert "colour" in question.load_error
        field = ui.state().fields["wrong"]
        assert field.enabled is False
        assert field.errors == (question.load_error,)
        assert ui.state().fields["good"].value == "fine"
        assert list(ui.validate()) == ["wrong"]


def test_edge_circular_dependency_names_the_cycle_members(tmp_path: Path) -> None:
    """Edge: circular dependency - detected at load and reported with its members."""
    with pytest.raises(CircularDependencyError) as caught:
        TemplateUI.from_template(str(FIXTURES / "ui_cycle"), dst=tmp_path / "dst")
    assert set(caught.value.cycle) == {"alpha", "beta"}
    assert "alpha" in str(caught.value)
    assert "beta" in str(caught.value)


def test_edge_forward_reference_uses_the_later_questions_default(tmp_path: Path) -> None:
    """Edge: forward reference - a when naming a later question sees that default."""
    with load("ui_forward", tmp_path / "dst") as ui:
        assert ui.schema().ids() == ("early", "later")
        assert ui.state().fields["early"].visible is True
        ui.set("later", "no")
        assert ui.state().fields["early"].visible is False


def test_edge_empty_template_yields_an_empty_schema_that_renders(tmp_path: Path) -> None:
    """Edge: empty template - empty schema, valid state, and a render that still works."""
    dst = tmp_path / "dst"
    with load("ui_empty", dst) as ui:
        assert ui.schema().questions == ()
        assert ui.state().visible_ids == ()
        assert ui.answers() == {}
        assert ui.validate() == {}
        ui.render(quiet=True)
    assert (dst / "out.txt").exists()


def test_edge_missing_copier_yml_raises_before_any_state(tmp_path: Path) -> None:
    """Edge: missing copier.yml - a named load error, raised before a state exists."""
    with pytest.raises(TemplateLoadError) as caught:
        TemplateUI.from_template(str(FIXTURES / "ui_nocopier"), dst=tmp_path / "dst")
    assert "ui_nocopier" in str(caught.value)


def test_edge_missing_path_raises_a_load_error(tmp_path: Path) -> None:
    """Edge: missing copier.yml - a path that does not exist is a load error, not a traceback."""
    with pytest.raises(TemplateLoadError):
        TemplateUI.from_template(str(tmp_path / "absent"), dst=tmp_path / "dst")


@pytest.mark.parametrize("id", ["broken_when", "broken_default"])
def test_edge_expression_error_marks_the_field_and_spares_the_rest(
    tmp_path: Path, id: str
) -> None:
    """Edge: expression error - the field carries the message, the rest of the state works."""
    with load("ui_exprerror", tmp_path / "dst") as ui:
        field = ui.state().fields[id]
        assert field.enabled is False
        assert field.errors == ("division by zero",)
        assert ui.validate()[id] == ["division by zero"]
        assert ui.state().fields["good"].value == "fine"
        ui.set("good", "still-usable")
        assert ui.state().fields["good"].value == "still-usable"


def test_edge_set_unknown_id_raises_naming_the_id(tmp_path: Path) -> None:
    """Edge: set unknown id - a KeyError-style error carrying the id."""
    with load("ui_deps", tmp_path / "dst") as ui, pytest.raises(UnknownFieldError) as caught:
        ui.set("no_such_question", 1)
    assert isinstance(caught.value, KeyError)
    assert "no_such_question" in str(caught.value)


def test_edge_set_hidden_field_keeps_the_value_for_later(tmp_path: Path) -> None:
    """Edge: set hidden field - accepted while hidden, and returned when it is visible again."""
    with load("ui_deps", tmp_path / "dst") as ui:
        ui.set("image", "kept")
        assert ui.state().fields["image"].visible is False
        assert ui.state().fields["image"].value == "kept"
        assert "image" not in ui.answers()
        ui.set("use_docker", True)
        assert ui.state().fields["image"].visible is True
        assert ui.answers()["image"] == "kept"


def _hostile_template(root: Path, module: str) -> Path:
    """A template whose only Jinja extension writes a marker file when it is imported."""
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{module}.py").write_text(
        "from pathlib import Path\n\n"
        "from jinja2.ext import Extension\n\n"
        "Path(__file__).with_name('marker').write_text('executed')\n\n\n"
        "class Probe(Extension):\n"
        "    pass\n"
    )
    template = root / "template"
    template.mkdir()
    (template / "copier.yml").write_text(
        f"_jinja_extensions:\n  - {module}.Probe\n\nname:\n  type: str\n  default: x\n"
    )
    return template


def test_edge_untrusted_template_is_refused_before_its_extension_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Edge: unsafe template - refused at load, and its extension never gets imported."""
    monkeypatch.syspath_prepend(str(tmp_path))
    template = _hostile_template(tmp_path, "ui_refused_ext")
    with pytest.raises(TemplateLoadError) as caught:
        TemplateUI.from_template(str(template), dst=tmp_path / "dst")
    assert "jinja_extensions" in str(caught.value)
    assert not (tmp_path / "marker").exists()
    assert "ui_refused_ext" not in sys.modules


def test_edge_unsafe_flag_admits_a_template_with_extensions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Edge: unsafe template - explicit trust loads it, so the gate is a gate and not a wall."""
    monkeypatch.syspath_prepend(str(tmp_path))
    template = _hostile_template(tmp_path, "ui_trusted_ext")
    with TemplateUI.from_template(str(template), dst=tmp_path / "dst", unsafe=True) as ui:
        assert ui.schema().ids() == ("name",)
    assert (tmp_path / "marker").exists()
