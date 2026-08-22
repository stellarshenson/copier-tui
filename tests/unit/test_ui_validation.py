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
