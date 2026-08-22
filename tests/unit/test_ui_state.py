"""State criteria: visibility, recompute, defaults, secrets, serialisation, determinism."""

from __future__ import annotations

import json
from pathlib import Path

from ui_support import FIXTURES, load

from copier_ui import TemplateUI


def test_visibility_evaluates_when_against_current_answers(tmp_path: Path) -> None:
    """Visibility: fields[id].visible is the evaluated when; no when means always visible."""
    with load("ui_deps", tmp_path / "dst") as ui:
        state = ui.state()
        assert state.fields["project"].visible is True
        assert state.fields["image"].visible is False
        assert state.visible_ids == ("project", "use_docker", "flavour")


def test_recompute_on_set_updates_every_dependent_in_one_pass(tmp_path: Path) -> None:
    """Recompute on set: one set re-evaluates visibility, defaults and choices of dependents."""
    with load("ui_deps", tmp_path / "dst") as ui:
        ui.set("use_docker", True)
        assert ui.state().visible_ids == ("project", "use_docker", "image", "port", "flavour")
        ui.set("project", "atlas")
        state = ui.state()
        assert state.fields["image"].value == "atlas-image"
        assert state.fields["flavour"].choices[0].value == "atlas"


def test_computed_defaults_stop_recomputing_once_the_user_sets_the_field(tmp_path: Path) -> None:
    """Computed defaults: a Jinja default follows its dependency until the field is set."""
    with load("ui_deps", tmp_path / "dst") as ui:
        ui.set("use_docker", True)
        ui.set("project", "first")
        assert ui.state().fields["image"].value == "first-image"
        ui.set("image", "pinned")
        ui.set("project", "second")
        assert ui.state().fields["image"].value == "pinned"


def test_explicit_vs_default_is_reported_not_inferred(tmp_path: Path) -> None:
    """Explicit vs default: is_default marks an untouched default and flips on set."""
    with load("ui_deps", tmp_path / "dst") as ui:
        assert ui.state().fields["project"].is_default is True
        ui.set("project", "demo")
        assert ui.state().fields["project"].is_default is False
        assert ui.state().fields["project"].value == "demo"


def test_hidden_excluded_from_the_answers_handed_to_copier(tmp_path: Path) -> None:
    """Hidden excluded: answers() carries visible fields only."""
    with load("ui_deps", tmp_path / "dst") as ui:
        assert "image" not in ui.answers()
        ui.set("use_docker", True)
        assert "image" in ui.answers()


def test_secrets_excluded_from_schema_and_serialised_state(tmp_path: Path) -> None:
    """Secrets excluded from dump: metadata survives, the value never leaves in a dump."""
    with load("ui_kinds", tmp_path / "dst") as ui:
        question = ui.schema().by_id("token")
        assert question.secret is True
        assert question.default_source is None
        assert "s3cret" not in repr(ui.schema())
        dumped = ui.state().to_dict()["fields"]["token"]
        assert dumped["secret"] is True
        assert dumped["value"] is None
        assert "s3cret" not in repr(ui.state())
        assert "s3cret" not in json.dumps(ui.state().to_dict())
        assert ui.answers()["token"] == "s3cret"


def test_serialisable_answers_round_trip_through_a_plain_dict(tmp_path: Path) -> None:
    """Serialisable answers: answers() is JSON-compatible and can be set straight back."""
    with load("ui_kinds", tmp_path / "dst") as ui:
        answers = ui.answers()
        assert json.loads(json.dumps(answers)) == answers
        for id, value in answers.items():
            ui.set(id, value)
        assert ui.answers() == answers


def test_preset_answers_are_seeded_and_marked(tmp_path: Path) -> None:
    """Pre-supplied answers: a value given as data is seeded, explicit and flagged preset."""
    ui = TemplateUI.from_template(
        str(FIXTURES / "ui_deps"), dst=tmp_path / "dst", data={"project": "given"}
    )
    try:
        field = ui.state().fields["project"]
        assert field.value == "given"
        assert field.preset is True
        assert field.is_default is False
    finally:
        ui.close()


def test_seed_from_answers_file_hides_template_internal_keys(tmp_path: Path) -> None:
    """Seed from answers file: recopy seeds from .copier-answers.yml, without _commit/_src_path."""
    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / ".copier-answers.yml").write_text(
        f"_commit: v1.0.0\n_src_path: {FIXTURES / 'ui_deps'}\nproject: seeded\nuse_docker: true\n"
    )
    ui = TemplateUI.from_template(None, dst=dst, operation="recopy")
    try:
        assert "_commit" not in ui.schema().ids()
        assert "_src_path" not in ui.schema().ids()
        state = ui.state()
        assert state.fields["project"].value == "seeded"
        assert state.fields["project"].is_default is False
        assert state.fields["image"].value == "seeded-image"
    finally:
        ui.close()


def test_determinism_same_template_and_answers_give_the_same_schema_and_state(
    tmp_path: Path,
) -> None:
    """Determinism: two loads with the same answers produce equal schema and field state."""
    dumps = []
    schemas = []
    states = []
    for run in range(2):
        with load("ui_deps", tmp_path / f"dst{run}") as ui:
            ui.set("use_docker", True)
            ui.set("project", "same")
            schemas.append(ui.schema())
            states.append(ui.state())
            dumps.append(json.dumps(ui.state().to_dict(), sort_keys=True))
    assert schemas[0] == schemas[1]
    assert states[0].fields == states[1].fields
    assert states[0].visible_ids == states[1].visible_ids
    assert dumps[0] == dumps[1]
