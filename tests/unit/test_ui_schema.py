"""Schema criteria: loading, question kinds and fields, choices, order, dependencies."""

from __future__ import annotations

from pathlib import Path

import pytest
from ui_support import FIXTURES, git_template, load

from copier_ui import Choice, Kind, TemplateLoadError, TemplateUI

KIND_BY_ID = {
    "text": Kind.STRING,
    "flag": Kind.BOOL,
    "count": Kind.INTEGER,
    "ratio": Kind.FLOAT,
    "where": Kind.PATH,
    "config": Kind.STRUCTURED,
    "blob": Kind.STRUCTURED,
    "colour": Kind.CHOICE,
    "tags": Kind.MULTISELECT,
    "token": Kind.SECRET,
}


def test_load_local_accepts_a_directory_with_copier_yml(tmp_path: Path) -> None:
    """Load local: from_template takes a local template directory."""
    with load("ui_kinds", tmp_path / "dst") as ui:
        assert ui.schema().ids()[0] == "text"


def test_load_local_accepts_copier_yaml_spelling(tmp_path: Path) -> None:
    """Load local: the .yaml spelling of the config file is accepted too."""
    template = tmp_path / "tpl"
    template.mkdir()
    (template / "copier.yaml").write_text("only:\n  type: str\n  default: yes-please\n")
    ui = TemplateUI.from_template(template, dst=tmp_path / "dst")
    try:
        assert ui.schema().ids() == ("only",)
    finally:
        ui.close()


@pytest.mark.parametrize(("vcs_ref", "expected"), [("v1.0.0", "one"), ("v2.0.0", "two")])
def test_load_remote_resolves_vcs_ref_through_copier(
    tmp_path: Path, vcs_ref: str, expected: str
) -> None:
    """Load remote: a git source plus vcs_ref is fetched by copier at that ref."""
    src = git_template(tmp_path / "repo")
    ui = TemplateUI.from_template(str(src), vcs_ref=vcs_ref, dst=tmp_path / "dst")
    try:
        assert ui.state().fields["name"].value == expected
    finally:
        ui.close()


def test_load_remote_reports_an_unknown_ref_as_a_load_error(tmp_path: Path) -> None:
    """Load remote: a ref that does not exist raises TemplateLoadError."""
    src = git_template(tmp_path / "repo")
    with pytest.raises(TemplateLoadError):
        TemplateUI.from_template(str(src), vcs_ref="v9.9.9", dst=tmp_path / "dst")


@pytest.mark.parametrize(("id", "kind"), sorted(KIND_BY_ID.items()))
def test_question_kinds_map_each_copier_type_to_one_kind(
    tmp_path: Path, id: str, kind: Kind
) -> None:
    """Question kinds: every copier type and modifier resolves to exactly one Kind."""
    with load("ui_kinds", tmp_path / "dst") as ui:
        assert ui.schema().by_id(id).kind is kind


def test_question_kinds_choices_outrank_secret_but_keep_the_secret_flag(tmp_path: Path) -> None:
    """Question kinds: a secret question with choices is a choice that stays marked secret."""
    with load("ui_kinds", tmp_path / "dst") as ui:
        question = ui.schema().by_id("mode")
        assert question.kind is Kind.CHOICE
        assert question.secret is True


def test_question_fields_carry_the_declared_metadata(tmp_path: Path) -> None:
    """Question fields: id, kind, label, help, default, choices, when and validator are all on it."""
    with load("ui_deps", tmp_path / "dst") as ui:
        port = ui.schema().by_id("port")
        assert port.id == "port"
        assert port.kind is Kind.INTEGER
        assert port.label == "port (int)"
        assert port.default_source == 8080
        assert port.when_source == "{{ use_docker }}"
        assert "Port must be 1024 or above" in port.validator_source
        assert port.dependencies == ("use_docker",)
        assert port.secret is False
        assert port.multiselect is False
        assert port.choices_source is None
        project = ui.schema().by_id("project")
        assert project.help == "Project name"


def test_the_label_is_copiers_own_caption_not_the_variable_name(tmp_path: Path) -> None:
    """Label: the question's help, so a UI shows what copier's own prompt shows.

    A variable name is not a question. `port` declares no help, so it falls back to copier's
    own `var_name (type)` form rather than to the bare identifier.
    """
    with load("ui_deps", tmp_path / "dst") as ui:
        assert ui.schema().by_id("project").label == "Project name"
        assert ui.schema().by_id("port").label == "port (int)"


def test_a_templated_help_string_never_reaches_the_ui_as_raw_jinja(tmp_path: Path) -> None:
    """Help: copier renders help through Jinja, so no UI ever prints the braces.

    The schema is normalised once, before any answer exists, so a help string referencing
    another answer renders that reference empty rather than live. That is the cost of one
    screen instead of a prompt sequence; the alternative is recomputing every caption on
    every keystroke. What must never happen is the template source reaching the screen.
    """
    template = tmp_path / "tpl"
    template.mkdir()
    (template / "copier.yml").write_text(
        "name:\n  type: str\n  default: demo\n"
        "where:\n  type: str\n  default: /opt\n  help: Where {{ name }} will be installed\n"
    )
    ui = TemplateUI.from_template(template, dst=tmp_path / "dst")
    try:
        where = ui.schema().by_id("where")
        assert "{{" not in where.help and "}}" not in where.help
        assert where.help.startswith("Where")
        assert where.label == where.help
    finally:
        ui.close()


@pytest.mark.parametrize(
    ("id", "expected"),
    [
        ("colour", (Choice("red", "red"), Choice("green", "green"))),
        ("shade", (Choice("Light shade", "light"), Choice("Dark shade", "dark"))),
        ("size", (Choice("Small", "s"), Choice("Large", "l"))),
    ],
)
def test_choice_normalisation_keeps_copier_yml_order(
    tmp_path: Path, id: str, expected: tuple[Choice, ...]
) -> None:
    """Choice normalisation: bare list, label/value dict and pair list all give ordered pairs."""
    with load("ui_kinds", tmp_path / "dst") as ui:
        assert ui.state().fields[id].choices == expected


def test_choice_normalisation_rejects_a_list_of_single_key_dicts(tmp_path: Path) -> None:
    """Choice normalisation: copier 9.17.2 has no single-key-dict form, so it is a field error.

    The acceptance criterion lists this shape, but copier itself refuses it - `copier.run_copy`
    on the same template raises the identical message - so copier_ui reports it per field
    instead of inventing a syntax copier would not render.
    """
    template = tmp_path / "tpl"
    template.mkdir()
    (template / "copier.yml").write_text(
        "size:\n  type: str\n  default: s\n  choices:\n    - Small: s\n    - Large: l\n"
    )
    ui = TemplateUI.from_template(template, dst=tmp_path / "dst")
    try:
        field = ui.state().fields["size"]
        assert field.choices == ()
        assert field.enabled is False
        assert "Small" in field.errors[0]
    finally:
        ui.close()


def test_declaration_order_is_copier_yml_order(tmp_path: Path) -> None:
    """Declaration order: schema() returns questions in copier.yml order, not sorted."""
    source = (FIXTURES / "ui_kinds" / "copier.yml").read_text()
    declared = tuple(
        line.rstrip(":")
        for line in source.splitlines()
        if line and not line[0].isspace() and line.endswith(":") and not line.startswith("_")
    )
    with load("ui_kinds", tmp_path / "dst") as ui:
        assert ui.schema().ids() == declared


def test_dependency_graph_lists_ids_from_when_default_and_choices(tmp_path: Path) -> None:
    """Dependency graph: each question exposes the ids its expressions reference."""
    with load("ui_deps", tmp_path / "dst") as ui:
        assert ui.schema().by_id("image").dependencies == ("project", "use_docker")
        assert ui.schema().by_id("flavour").dependencies == ("project",)
        assert ui.schema().by_id("project").dependencies == ()
