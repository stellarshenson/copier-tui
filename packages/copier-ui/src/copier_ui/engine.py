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
from copier_ui.model import Evaluator, FieldState, FieldValidator, Parser, Schema, State


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


def _read_by(
    id: str, position: Mapping[str, int], given: Mapping[str, Any], parsed: Mapping[str, Any]
) -> dict[str, Any]:
    """The answers one question's expressions read, each as copier hands it over.

    copier asks in declaration order and parses an answer when its own question's turn comes.
    So a question reads the answers of the questions declared before it parsed, and the
    answer of a question declared after it - which it can reach only as supplied data - as
    that answer was given. `given` and `parsed` hold a default where no answer is passed on.
    """
    return {
        other: parsed[other] if position[other] < position[id] else given[other] for other in given
    }


def compute_state(
    schema: Schema,
    order: Sequence[str],
    explicit: Mapping[str, Any],
    preset: AbstractSet[str],
    evaluate: Evaluator,
    parse: Parser,
) -> State:
    """Evaluate every question once, threading each resolved value into the next evaluation.

    What a later question reads of an earlier one is what copier will have for it. An answer
    that is passed on to copier is parsed once, by `parse`: a control gives back text, and a
    typed `3` has to be the number 3 to a later `when`. Where no answer is passed on - nobody
    gave one, or the question has left the form - copier works the default out, so the
    default is what is read, whatever was typed before the question left.
    """
    position = {id: at for at, id in enumerate(schema.ids())}
    given: dict[str, Any] = {}
    parsed: dict[str, Any] = {}
    resolved: dict[str, FieldState] = {}
    for id in order:
        question = schema.by_id(id)
        answers = _read_by(id, position, given, parsed)
        evaluation = evaluate(id, answers)
        default = evaluation.default if evaluation.has_default else None
        field = FieldState(
            id=id,
            value=explicit.get(id, default),
            visible=evaluation.visible,
            enabled=question.load_error is None and evaluation.error is None,
            is_default=id not in explicit and evaluation.has_default,
            preset=id in preset,
            secret=question.secret,
            choices=evaluation.choices,
            errors=() if evaluation.error is None else (evaluation.error,),
        )
        resolved[id] = field
        if _passed_on(field):
            given[id] = field.value
            parsed[id] = parse(id, field.value, answers)
        else:
            given[id] = parsed[id] = default

    fields = {id: resolved[id] for id in schema.ids()}
    return State(
        fields=fields,
        visible_ids=tuple(id for id, field in fields.items() if field.visible),
        given=given,
        parsed=parsed,
    )


def _passed_on(field: FieldState) -> bool:
    """Whether copier is handed this field's answer.

    An answer somebody gave, on a question that is asked - or given as data, which copier
    takes for a question it never asks as well. A default is not handed over: copier works
    it out itself, and handed back as an answer it would be parsed a second time. A question
    with no default is not at a default, so one that is asked and was left blank is handed
    over as no value: copier has nothing to work out there.
    """
    return not field.is_default and (field.visible or field.preset)


def supplied_answers(state: State) -> dict[str, Any]:
    """The answers to hand to copier as data: the ones that were given, as they were given."""
    return {id: field.value for id, field in state.fields.items() if _passed_on(field)}


def answers_read_by(schema: Schema, state: State, id: str) -> dict[str, Any]:
    """The answers one question's validator reads, in the state as it stands."""
    position = {other: at for at, other in enumerate(schema.ids())}
    return _read_by(id, position, state.given, state.parsed)


def validate_state(
    schema: Schema,
    state: State,
    validate_field: FieldValidator,
) -> dict[str, list[str]]:
    """Per-field error messages for visible fields; an empty dict means valid."""
    errors: dict[str, list[str]] = {}
    for id in state.visible_ids:
        field = state.fields[id]
        if not field.enabled:
            errors[id] = list(field.errors)
            continue
        answers = answers_read_by(schema, state, id)
        messages = list(field.errors) + list(validate_field(id, field.value, answers))
        if messages:
            errors[id] = messages
    return errors


def visible_answers(state: State) -> dict[str, Any]:
    """Answers of visible fields only, JSON-compatible."""
    return {id: state.fields[id].value for id in state.visible_ids}
