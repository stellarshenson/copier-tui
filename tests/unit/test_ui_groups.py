"""Grouping criteria: the optional `_ui_groups` key, and the nesting every template gets."""

from __future__ import annotations

from pathlib import Path

from ui_support import load


def test_a_template_naming_no_groups_still_has_one_covering_every_question(
    tmp_path: Path,
) -> None:
    """Groups: no `_ui_groups` means one untitled group holding the whole survey."""
    with load("ui_kinds", tmp_path / "dst") as ui:
        schema = ui.schema()
        assert len(schema.groups) == 1
        group = schema.groups[0]
        assert group.title == ""
        assert group.declared is False
        assert group.ids == schema.ids()


def test_declared_groups_carry_their_titles_and_members(tmp_path: Path) -> None:
    """Groups: `_ui_groups` names each run of questions, in declaration order."""
    with load("ui_groups", tmp_path / "dst") as ui:
        groups = ui.schema().groups
        assert [(group.title, group.ids) for group in groups] == [
            ("Identity", ("project", "author")),
            ("Tooling and quality", ("linter", "tests")),
        ]
        assert all(group.declared for group in groups)


def test_a_question_no_group_claims_falls_into_an_untitled_run(tmp_path: Path) -> None:
    """Groups: grouping some questions leaves the rest ungrouped rather than hidden."""
    with load("ui_groups_partial", tmp_path / "dst") as ui:
        groups = ui.schema().groups
        assert [(group.title, group.declared, group.ids) for group in groups] == [
            ("", False, ("project",)),
            ("Tooling and quality", True, ("linter",)),
            ("", False, ("licence",)),
            ("Tooling and quality", True, ("tests",)),
        ]


def test_a_group_naming_a_field_the_template_does_not_have_is_ignored(tmp_path: Path) -> None:
    """Groups: a member that is not a question of this template never reaches the schema."""
    with load("ui_groups_partial", tmp_path / "dst") as ui:
        members = [id for group in ui.schema().groups for id in group.ids]
        assert "nonexistent" not in members
        assert members == list(ui.schema().ids())


def test_a_malformed_groups_key_loads_as_though_it_were_absent(tmp_path: Path) -> None:
    """Groups: a heading is decoration, so getting it wrong must not refuse the template."""
    with load("ui_groups_broken", tmp_path / "dst") as ui:
        schema = ui.schema()
        assert schema.ids() == ("project", "linter")
        assert len(schema.groups) == 1
        assert schema.groups[0].declared is False
        assert schema.groups[0].ids == schema.ids()


def test_groups_always_partition_the_schema_without_reordering_it(tmp_path: Path) -> None:
    """Groups: walking the groups yields every question once, in copier.yml order."""
    for fixture in ("ui_kinds", "ui_groups", "ui_groups_partial", "ui_groups_broken"):
        with load(fixture, tmp_path / fixture) as ui:
            schema = ui.schema()
            walked = tuple(id for group in schema.groups for id in group.ids)
            assert walked == schema.ids(), fixture


def test_a_conditional_question_names_the_answer_that_governs_it(tmp_path: Path) -> None:
    """Nesting: `condition_ids` is what a `when` reads, so a UI can nest without Jinja."""
    with load("ui_deps", tmp_path / "dst") as ui:
        schema = ui.schema()
        assert schema.by_id("image").condition_ids == ("use_docker",)
        assert schema.by_id("port").condition_ids == ("use_docker",)
        assert schema.by_id("project").condition_ids == ()


def test_a_default_referring_to_another_answer_is_not_a_condition(tmp_path: Path) -> None:
    """Nesting: only visibility nests; a templated default or choice is a plain dependency."""
    with load("ui_deps", tmp_path / "dst") as ui:
        flavour = ui.schema().by_id("flavour")
        assert flavour.dependencies == ("project",)
        assert flavour.condition_ids == ()


def test_a_template_naming_groups_still_renders_through_copier(tmp_path: Path) -> None:
    """Groups: `_ui_groups` is inert to copier, so declaring it costs the template nothing."""
    dst = tmp_path / "dst"
    with load("ui_groups", dst) as ui:
        ui.set("project", "grouped")
        ui.render(quiet=True)
    assert (dst / "README.md").read_text().strip() == "grouped"
