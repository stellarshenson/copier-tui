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


def test_an_answer_the_caller_sets_is_no_longer_a_preset(tmp_path: Path) -> None:
    """Preset: `set` replaces a --data answer, and what replaced it was asked for.

    A frontend leaves presets off its form. One it had to show - the template refused the
    value - must stay shown once the user has typed an acceptable answer into it.
    """
    with load("ui_deps", tmp_path / "dst", data={"project": "given"}) as ui:
        assert ui.state().fields["project"].preset is True
        ui.set("project", "typed")
        assert ui.state().fields["project"].preset is False


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


def test_a_typed_number_reaches_later_questions_as_a_number(tmp_path: Path) -> None:
    """Recompute: an answer is cast to its question's type before a later question reads it.

    A control gives back text, and `--data` gives copier's command line text. copier casts
    each answer before the next question sees it; passed on raw, `count == 3` was false for a
    typed 3 and `count * 2` was 33, so the survey hid a question copier went on to ask.
    """
    with load("ui_typed", tmp_path / "dst") as ui:
        ui.set("count", "3")
        assert "exact" in ui.state().visible_ids
        assert ui.state().fields["double"].value == 6

        ui.set("count", "4")
        assert "exact" not in ui.state().visible_ids
        assert ui.state().fields["double"].value == 8
        assert ui.state().fields["count"].value == "4", "the answer itself stays as typed"

        ui.set("limit", "7")
        assert ui.validate() == {}
        ui.set("limit", "2")
        assert ui.validate() == {"limit": ["limit is under count"]}


def test_a_boolean_given_as_text_reaches_later_questions_as_a_boolean(tmp_path: Path) -> None:
    """Recompute: `--data flag=false` is the text `false`, and text is true to an `if`."""
    with load("ui_typed", tmp_path / "dst", data={"flag": "false"}) as ui:
        assert "onflag" not in ui.state().visible_ids


def test_an_answer_that_does_not_cast_is_passed_on_as_typed(tmp_path: Path) -> None:
    """Recompute: text that is no number in a number field stays as typed and is reported."""
    with load("ui_typed", tmp_path / "dst") as ui:
        ui.set("count", "4x")
        assert "count" in ui.validate()
        assert ui.state().fields["count"].value == "4x"


def test_the_survey_and_copier_agree_on_what_a_typed_number_shows(tmp_path: Path) -> None:
    """Render: copier asks for nothing the survey did not show, so the run completes."""
    dst = tmp_path / "dst"
    with load("ui_typed", dst, data={"count": "3"}) as ui:
        assert ui.answers()["exact"] == "exact"
        ui.render(quiet=True, confirm=lambda question: True)
    assert (dst / "out.txt").read_text().strip() == "3 6"


def test_a_default_copier_has_parsed_is_not_parsed_again(tmp_path: Path) -> None:
    """Recompute: only a supplied answer is parsed; a default arrives parsed already.

    `release` is YAML whose default is the text 1.0 in quotes. Read once it is that text;
    read twice it is the number, `release == '1.0'` turns false, and the survey hid a
    question that copier went on to ask.
    """
    dst = tmp_path / "dst"
    with load("ui_parsed", dst) as ui:
        assert "notes" in ui.state().visible_ids
        ui.render(quiet=True, confirm=lambda question: True)
    assert "for one-point-oh" in (dst / "out.txt").read_text()


def test_a_question_reads_a_later_answer_as_it_was_given(tmp_path: Path) -> None:
    """Recompute: an answer is parsed for the questions declared after its own, not before.

    copier asks in declaration order, so `early` reads the typed `3` of `later` as text and
    `later != 3` holds. Parsed for `early` too, the survey hid it and copier asked for it.
    """
    dst = tmp_path / "dst"
    with load("ui_parsed", dst) as ui:
        assert "early" not in ui.state().visible_ids
        ui.set("later", "3")
        assert "early" in ui.state().visible_ids
        ui.render(quiet=True, confirm=lambda question: True)
    assert (dst / "out.txt").read_text().startswith("3 ")


def test_a_list_given_as_text_reaches_later_questions_as_a_list(tmp_path: Path) -> None:
    """Recompute: `-d 'extras=[docs, ci]'` is text, and copier reads a multiselect's text as a list."""
    with load("ui_parsed", tmp_path / "dst", data={"extras": "[docs, ci]"}) as ui:
        assert ui.state().fields["count_line"].value == "2 extras: docs+ci"


def test_a_question_that_left_the_form_counts_as_its_default(tmp_path: Path) -> None:
    """Recompute: a later question reads the default of a question that is no longer asked.

    copier is not handed the answer of a question that left the form, so it reads the
    default there. Read as the typed `mysql`, the survey hid `pg_schema` and copier asked
    for it. The typed answer is kept, and is the answer again once the question is back.
    """
    dst = tmp_path / "dst"
    with load("ui_supplied", dst) as ui:
        ui.set("db", "mysql")
        assert "pg_schema" not in ui.state().visible_ids
        ui.set("use_db", False)
        assert "db" not in ui.state().visible_ids
        assert ui.state().fields["db"].value == "mysql"
        assert "pg_schema" in ui.state().visible_ids
        ui.render(quiet=True, confirm=lambda question: True)
        assert (dst / "out.txt").read_text().split()[-1] == "public"

        ui.set("use_db", True)
        assert ui.answers()["db"] == "mysql"
        assert "pg_schema" not in ui.state().visible_ids


def test_data_that_is_no_questions_answer_is_read_by_every_expression(tmp_path: Path) -> None:
    """Recompute: a default, a `when` and a validator read data given under no question's name.

    copier hands such data to every expression. Evaluated without it, the default of `conf`
    was not a number: its row was refused with an error that no typed answer cleared.
    """
    with load("ui_sources", tmp_path / "dst", data={"seed": 5}) as ui:
        state = ui.state()
        assert state.fields["conf"].value == 5
        assert "gated" in state.visible_ids
        assert "conf" not in ui.validate()
        assert ui.check("capped", "4") == ()
        assert ui.check("capped", "9") == ("too big",)


def test_the_template_reference_and_external_data_are_read_as_copier_reads_them(
    tmp_path: Path,
) -> None:
    """Recompute: `_src_path` and `_external_data` reach an expression, as they do in copier."""
    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / "parent.yml").write_text("owner: abc\n")
    with load("ui_sources", dst, data={"seed": 5}) as ui:
        fields = ui.state().fields
        assert fields["origin"].value == str(FIXTURES / "ui_sources")
        assert fields["owner"].value == "abc"
        assert ui.validate() == {}


def test_an_answers_file_key_that_is_no_question_is_read_by_an_expression(tmp_path: Path) -> None:
    """Seed from answers file: an expression reads a key the template no longer asks.

    copier hands every key of the answers file to every expression. Only the keys that are
    question names reached the form, so the default of `new_count`, which reads the answer to
    a question an earlier template version asked, was not a number and its row was refused.
    """
    template = tmp_path / "tpl"
    template.mkdir()
    (template / "copier.yml").write_text('new_count:\n  type: int\n  default: "{{ old_count }}"\n')
    (template / "out.txt.jinja").write_text("{{ new_count }}\n")
    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / ".copier-answers.yml").write_text(f"_src_path: {template}\nold_count: 7\n")
    with TemplateUI.from_template(None, dst=dst, operation="recopy") as ui:
        assert ui.state().fields["new_count"].value == 7
        assert ui.validate() == {}
        ui.render(quiet=True, overwrite=True)
    assert (dst / "out.txt").read_text() == "7\n"
