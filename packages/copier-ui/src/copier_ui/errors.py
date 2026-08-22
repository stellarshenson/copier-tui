"""Exception hierarchy for copier_ui."""

from __future__ import annotations


class CopierUIError(Exception):
    """Base class for every copier_ui error."""


class TemplateLoadError(CopierUIError):
    """The template could not be fetched, or its configuration could not be read."""


class CircularDependencyError(TemplateLoadError):
    """Question expressions form a dependency cycle."""

    def __init__(self, cycle: tuple[str, ...]) -> None:
        """Record the ids taking part in the cycle."""
        super().__init__("Circular dependency between questions: " + " -> ".join(cycle))
        self.cycle = cycle


class UnknownFieldError(CopierUIError, KeyError):
    """A question id that is not in the schema."""


class RenderRefusedError(CopierUIError):
    """Rendering was refused because the state has validation errors."""

    def __init__(self, errors: dict[str, list[str]]) -> None:
        """Record the per-field error messages that blocked the render."""
        super().__init__("Invalid answers for: " + ", ".join(sorted(errors)))
        self.errors = errors
