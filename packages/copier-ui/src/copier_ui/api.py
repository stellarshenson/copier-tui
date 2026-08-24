"""TemplateUI, the synchronous facade every frontend talks to."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from copier_ui.adapter import TemplateAdapter
from copier_ui.engine import compute_state, evaluation_order, validate_state, visible_answers
from copier_ui.errors import RenderRefusedError
from copier_ui.model import Operation, Schema, State


class TemplateUI:
    """A loaded template, its schema, its answers and its state."""

    def __init__(
        self,
        adapter: TemplateAdapter,
        schema: Schema,
        order: tuple[str, ...],
        dst: Path,
    ) -> None:
        """Hold the adapter, the schema and the evaluation order; start with no answers."""
        self._adapter = adapter
        self._schema = schema
        self._order = order
        self._dst = dst
        self._explicit: dict[str, Any] = {}
        self._preset: set[str] = set()
        self._extra: dict[str, Any] = {}
        self._state = compute_state(schema, order, {}, frozenset(), adapter.evaluate)

    @classmethod
    def from_template(
        cls,
        src: str | Path | None,
        *,
        dst: str | Path = ".",
        operation: Operation = "copy",
        vcs_ref: str | None = None,
        answers_file: str | Path | None = None,
        data: Mapping[str, Any] | None = None,
        unsafe: bool = False,
    ) -> TemplateUI:
        """Load a local path or git URL, seed answers, and compute the first state.

        A template declaring `_jinja_extensions` or `_tasks` is refused with a
        `TemplateLoadError` unless `unsafe` is true or the template is trusted in copier's own
        settings, matching what plain copier does before it imports anything.
        """
        adapter = TemplateAdapter.open(
            src,
            Path(dst),
            vcs_ref=vcs_ref,
            answers_file=None if answers_file is None else Path(answers_file),
            operation=operation,
            unsafe=unsafe,
        )
        try:
            schema = Schema(questions=adapter.questions(), groups=adapter.groups())
            ui = cls(adapter, schema, evaluation_order(schema), Path(dst))
            ids = schema.ids()
            if operation in ("update", "recopy"):
                for id, value in adapter.last_answers().items():
                    if id in ids:
                        ui._explicit[id] = value
            for id, value in (data or {}).items():
                if id in ids:
                    ui._explicit[id] = value
                    ui._preset.add(id)
                else:
                    ui._extra[id] = value
            ui._recompute()
        except Exception:
            adapter.close()
            raise
        return ui

    def schema(self) -> Schema:
        """The ordered questions."""
        return self._schema

    def set(self, id: str, value: Any) -> None:
        """Record an explicit answer and recompute; raises UnknownFieldError on an unknown id."""
        self._schema.by_id(id)
        self._explicit[id] = value
        self._recompute()

    def state(self) -> State:
        """The current field state."""
        return self._state

    def answers(self) -> dict[str, Any]:
        """Visible answers, JSON-compatible, ready to hand to copier as data."""
        return visible_answers(self._state)

    def validate(self) -> dict[str, list[str]]:
        """Per-field error messages; an empty dict means valid."""
        return validate_state(self._schema, self._state, self._adapter.validate)

    def check(self, id: str, value: Any) -> tuple[str, ...]:
        """What this field would say about a value, without accepting it.

        The answer stays untouched, so a UI can validate a keystroke at a time, warn before a
        value is committed, or ask what a field would object to - `check(id, "")` names what an
        empty answer costs. Empty means the value is acceptable.

        This is the only way to learn what a template's own rule requires: copier expresses a
        rule as a Jinja template that renders its complaint, so the complaint is the description,
        and it takes a value to produce one.
        """
        self._schema.by_id(id)
        return self._adapter.validate(id, value, self.answers())

    def render(self, dst: str | Path | None = None, **copier_kwargs: Any) -> None:
        """Run copier with the current answers; raises RenderRefusedError when invalid."""
        errors = self.validate()
        if errors:
            raise RenderRefusedError(errors)
        target = self._dst if dst is None else Path(dst)
        self._adapter.run(target, {**self._extra, **self.answers()}, **copier_kwargs)

    @property
    def template_name(self) -> str:
        """The template's short name, for a frontend that wants to say which one this is."""
        return self._adapter.source_name()

    def close(self) -> None:
        """Release the template's temporary clone."""
        self._adapter.close()

    def __enter__(self) -> Self:
        """Enter a context that closes the template on exit."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the template."""
        self.close()

    def _recompute(self) -> None:
        """Re-evaluate visibility, defaults and choices for every question in one pass."""
        self._state = compute_state(
            self._schema,
            self._order,
            self._explicit,
            self._preset,
            self._adapter.evaluate,
        )
