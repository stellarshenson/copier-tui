"""Validation criteria: returned messages, validators, coercion, hidden fields."""

from __future__ import annotations

from pathlib import Path

from ui_support import load


def test_validation_returns_an_empty_dict_for_a_valid_state(tmp_path: Path) -> None:
    """Validation returns: an empty dict means valid."""
    with load("ui_deps", tmp_path / "dst") as ui:
        assert ui.validate() == {}


def test_validation_returns_messages_instead_of_raising(tmp_path: Path) -> None:
    """Validation returns: a bad value is a returned message, never an exception."""
    with load("ui_kinds", tmp_path / "dst") as ui:
        ui.set("count", "not-a-number")
        errors = ui.validate()
        assert list(errors) == ["count"]
        assert errors["count"]


def test_validator_support_renders_the_expression_as_the_message(tmp_path: Path) -> None:
    """Validator support: a non-empty rendered validator becomes the field's error message."""
    with load("ui_deps", tmp_path / "dst") as ui:
        ui.set("use_docker", True)
        ui.set("port", 80)
        assert "Port must be 1024 or above" in ui.validate()["port"][0]
        ui.set("port", 8443)
        assert ui.validate() == {}


def test_type_coercion_failure_is_a_validation_error(tmp_path: Path) -> None:
    """Type coercion: an uncoercible value is reported, not raised."""
    with load("ui_kinds", tmp_path / "dst") as ui:
        ui.set("ratio", "wide")
        assert "ratio" in ui.validate()


def test_unknown_choice_value_is_a_validation_error(tmp_path: Path) -> None:
    """Type coercion: a value outside the declared choices is a message on that field."""
    with load("ui_kinds", tmp_path / "dst") as ui:
        ui.set("colour", "purple")
        assert "colour" in ui.validate()


def test_hidden_excluded_from_validation(tmp_path: Path) -> None:
    """Hidden excluded: an invalid value on a hidden field does not block anything."""
    with load("ui_deps", tmp_path / "dst") as ui:
        ui.set("use_docker", True)
        ui.set("port", 80)
        assert "port" in ui.validate()
        ui.set("use_docker", False)
        assert ui.validate() == {}


def test_secret_values_never_appear_in_reported_messages(tmp_path: Path) -> None:
    """Redaction: a secret answer is masked in the messages validation and evaluation return."""
    with load("ui_secret", tmp_path / "dst") as ui:
        ui.set("token", "SEKRET-9999")
        messages = ui.validate()["token"] + list(ui.state().fields["probe"].errors)
        assert len(messages) == 2
        assert all("SEKRET-9999" not in message for message in messages)
        assert all("***" in message for message in messages)


def test_a_question_says_whether_the_template_declares_a_rule_for_it(tmp_path: Path) -> None:
    """Discoverable validation: a UI can hint at a rule before the user has broken it."""
    with load("ui_deps", tmp_path / "dst") as ui:
        assert ui.schema().by_id("port").validated is True
        assert ui.schema().by_id("project").validated is False


def test_kind_constraints_are_stated_without_running_anything(tmp_path: Path) -> None:
    """Discoverable validation: what the kind requires is knowable from the declaration alone.

    The permitted set of a choice question is deliberately not here - choices are recomputed per
    answer set, so they live on the field state rather than on the immutable question.
    """
    with load("ui_kinds", tmp_path / "dst") as ui:
        assert ui.schema().by_id("count").constraints == ("a whole number",)
        assert ui.schema().by_id("ratio").constraints == ("a number",)
        assert ui.schema().by_id("where").constraints == ("a filesystem path",)
        assert ui.schema().by_id("config").constraints == ("valid JSON",)
        assert ui.schema().by_id("text").constraints == ()
        assert ui.schema().by_id("colour").constraints == ()


def test_check_reports_what_a_field_would_say_without_accepting_the_value(
    tmp_path: Path,
) -> None:
    """Discoverable validation: a candidate can be tried without becoming the answer.

    This is what lets a UI warn on the keystroke rather than on the confirm, and it is the only
    way to learn what a template's own rule wants: copier renders a rule into its complaint, so
    the complaint takes a value to exist.
    """
    with load("ui_deps", tmp_path / "dst") as ui:
        ui.set("use_docker", True)
        ui.set("port", 8080)
        assert ui.check("port", 8443) == ()
        assert "Port must be 1024 or above" in ui.check("port", 80)[0]
        assert ui.check("port", "not-a-number")
        assert ui.answers()["port"] == 8080
        assert ui.validate() == {}


def test_check_on_an_unknown_field_is_an_error_not_a_silent_pass(tmp_path: Path) -> None:
    """Discoverable validation: a typo in a field id must not read as "this value is fine"."""
    from copier_ui import UnknownFieldError

    with load("ui_deps", tmp_path / "dst") as ui:
        try:
            ui.check("nope", 1)
        except UnknownFieldError:
            return
        raise AssertionError("check accepted an unknown field id")
