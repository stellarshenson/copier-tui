"""Frozen data model shared by every copier_ui layer and by any frontend."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from copier_ui.errors import UnknownFieldError

Operation = Literal["copy", "update", "recopy"]


class Kind(StrEnum):
    """The widget-selecting kind of a question."""

    STRING = "string"
    BOOL = "bool"
    INTEGER = "integer"
    FLOAT = "float"
    PATH = "path"
    STRUCTURED = "structured"
    CHOICE = "choice"
    MULTISELECT = "multiselect"
    SECRET = "secret"


@dataclass(frozen=True, slots=True)
class Choice:
    """One selectable option, in copier.yml order."""

    label: str
    value: Any


@dataclass(frozen=True, slots=True)
class Question:
    """One normalised question: declared data only, independent of any answer."""

    id: str
    kind: Kind
    label: str
    help: str
    secret: bool
    multiselect: bool
    multiline: bool
    placeholder: str
    default_source: Any
    choices_source: Any
    when_source: str | bool
    validator_source: str
    dependencies: tuple[str, ...]
    load_error: str | None


@dataclass(frozen=True, slots=True)
class Schema:
    """The template's questions in copier.yml declaration order."""

    questions: tuple[Question, ...]

    def ids(self) -> tuple[str, ...]:
        """Question ids in declaration order."""
        return tuple(question.id for question in self.questions)

    def by_id(self, id: str) -> Question:
        """Look a question up, raising UnknownFieldError when it is absent."""
        for question in self.questions:
            if question.id == id:
                return question
        raise UnknownFieldError(id)


@dataclass(frozen=True, slots=True)
class Evaluation:
    """One question resolved against one answer set."""

    visible: bool
    default: Any
    has_default: bool
    choices: tuple[Choice, ...]
    error: str | None


@dataclass(frozen=True, slots=True)
class FieldState:
    """One question's live state."""

    id: str
    value: Any
    visible: bool
    enabled: bool
    is_default: bool
    preset: bool
    secret: bool
    choices: tuple[Choice, ...]
    errors: tuple[str, ...]

    def __repr__(self) -> str:
        """Render the state, masking the value of a secret field."""
        value = "'***'" if self.secret else repr(self.value)
        return (
            f"FieldState(id={self.id!r}, value={value}, visible={self.visible}, "
            f"enabled={self.enabled}, is_default={self.is_default}, preset={self.preset}, "
            f"secret={self.secret}, choices={self.choices!r}, errors={self.errors!r})"
        )


@dataclass(frozen=True, slots=True)
class State:
    """The whole survey's live state."""

    fields: Mapping[str, FieldState]
    visible_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """JSON-compatible dump with secret values replaced by None."""
        return {
            "fields": {
                id: {
                    "value": None if field.secret else field.value,
                    "visible": field.visible,
                    "enabled": field.enabled,
                    "is_default": field.is_default,
                    "preset": field.preset,
                    "secret": field.secret,
                    "choices": [
                        {"label": choice.label, "value": choice.value} for choice in field.choices
                    ],
                    "errors": list(field.errors),
                }
                for id, field in self.fields.items()
            },
            "visible_ids": list(self.visible_ids),
        }


Evaluator = Callable[[str, Mapping[str, Any]], Evaluation]
FieldValidator = Callable[[str, Any, Mapping[str, Any]], tuple[str, ...]]
