"""State algorithms: evaluation order, state computation, validation, answer extraction.

Pure functions over the model. Evaluation arrives as callables, so this module needs neither
copier nor a template on disk.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
import heapq
from typing import Any

from copier_ui.errors import CircularDependencyError
from copier_ui.model import Evaluator, FieldState, FieldValidator, Schema, State


def evaluation_order(schema: Schema) -> tuple[str, ...]:
    """Topological order of the dependency graph, ties broken by declaration order."""
    ids = schema.ids()
    index = {id: position for position, id in enumerate(ids)}
    deps = {q.id: tuple(d for d in q.dependencies if d in index) for q in schema.questions}
    dependents: dict[str, list[str]] = {id: [] for id in ids}
    pending = {}
    for id, sources in deps.items():
        unique = set(sources)
        pending[id] = len(unique)
        for source in unique:
            dependents[source].append(id)

    ready = [index[id] for id, count in pending.items() if count == 0]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        id = ids[heapq.heappop(ready)]
        order.append(id)
        for dependent in dependents[id]:
            pending[dependent] -= 1
            if pending[dependent] == 0:
                heapq.heappush(ready, index[dependent])

    if len(order) < len(ids):
        stuck = {id for id in ids if pending[id] > 0}
        raise CircularDependencyError(_find_cycle(ids, deps, stuck))
    return tuple(order)


def _find_cycle(
    ids: Sequence[str],
    deps: Mapping[str, Sequence[str]],
    stuck: AbstractSet[str],
) -> tuple[str, ...]:
    """Walk the unresolved questions until one repeats, and return that cycle."""
    path: list[str] = []
    seen: dict[str, int] = {}
    id = next(candidate for candidate in ids if candidate in stuck)
    while id not in seen:
        seen[id] = len(path)
        path.append(id)
        id = next(dep for dep in deps[id] if dep in stuck)
    return tuple(path[seen[id] :])


def compute_state(
    schema: Schema,
    order: Sequence[str],
    explicit: Mapping[str, Any],
    preset: AbstractSet[str],
    evaluate: Evaluator,
) -> State:
    """Evaluate every question once, threading each resolved value into the next evaluation."""
    answers: dict[str, Any] = {}
    resolved: dict[str, FieldState] = {}
    for id in order:
        question = schema.by_id(id)
        evaluation = evaluate(id, answers)
        if id in explicit:
            value = explicit[id]
            is_default = False
        else:
            value = evaluation.default if evaluation.has_default else None
            is_default = True
        answers[id] = value
        resolved[id] = FieldState(
            id=id,
            value=value,
            visible=evaluation.visible,
            enabled=question.load_error is None and evaluation.error is None,
            is_default=is_default,
            preset=id in preset,
            secret=question.secret,
            choices=evaluation.choices,
            errors=() if evaluation.error is None else (evaluation.error,),
        )

    fields = {id: resolved[id] for id in schema.ids()}
    return State(
        fields=fields,
        visible_ids=tuple(id for id, field in fields.items() if field.visible),
    )


def validate_state(
    schema: Schema,
    state: State,
    validate_field: FieldValidator,
) -> dict[str, list[str]]:
    """Per-field error messages for visible fields; an empty dict means valid."""
    answers = {id: field.value for id, field in state.fields.items()}
    errors: dict[str, list[str]] = {}
    for id in state.visible_ids:
        field = state.fields[id]
        if not field.enabled:
            errors[id] = list(field.errors)
            continue
        messages = list(field.errors) + list(validate_field(id, field.value, answers))
        if messages:
            errors[id] = messages
    return errors


def visible_answers(state: State) -> dict[str, Any]:
    """Answers of visible fields only, JSON-compatible."""
    return {id: state.fields[id].value for id in state.visible_ids}
