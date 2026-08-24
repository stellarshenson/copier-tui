"""Copier-facing layer.

This is the ONLY module in copier_ui or copier_tui allowed to import copier. Everything it
uses beyond `run_copy`, `run_recopy`, `run_update` and `Phase` is a copier internal that may
move between copier releases; copier 9.17.2 is the version this was written against. Nothing
outside this module may import `copier`.

Internals to use, all documented in docs/design-notes.md:

- `copier._main.Worker` - constructed, never run; owns the fetch, the Jinja env and the context
- `Worker.template.questions_data`, `Worker.template.local_abspath`, `Worker.jinja_env`
- `Worker.template.config_data` - every `_`-prefixed copier.yml key, underscore stripped;
  copier does not validate the set, so a key it does not know is carried through and
  ignored, which is what makes `_ui_groups` a legal opt-in rather than a fork
- `Worker.unsafe` and `Worker._check_unsafe(operation)` - the trust gate, config reads only,
  called before `jinja_env` because that access imports every `_jinja_extensions` entry
- `Worker.answers` (assign a fresh `copier._user_data.AnswersMap`) and `Worker._render_context()`
- `copier._user_data.Question` - built fresh per evaluation; `_formatted_choices` is cached
- `copier._types.MISSING` - the "no default" sentinel returned by `Question.get_default()`
- `copier._subproject.Subproject.last_answers` - the destination's answers file
- `copier.Phase.use(Phase.PROMPT)` - wraps every evaluation
- `copier.run_copy` / `run_recopy` / `run_update` - the only public entry points
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
import re
from typing import Any

from copier import Phase, run_copy, run_recopy, run_update
from copier._main import Worker
from copier._types import MISSING
from copier._user_data import AnswersMap
from copier._user_data import Question as CopierQuestion
from jinja2 import TemplateSyntaxError, meta

from copier_ui.errors import TemplateLoadError
from copier_ui.model import Choice, Evaluation, Group, Kind, Operation, Question

_KIND_BY_TYPE = {
    "str": Kind.STRING,
    "bool": Kind.BOOL,
    "int": Kind.INTEGER,
    "float": Kind.FLOAT,
    "path": Kind.PATH,
    "json": Kind.STRUCTURED,
    "yaml": Kind.STRUCTURED,
}


class TemplateAdapter:
    """Loads a copier template and evaluates its questions against an answer set."""

    def __init__(self, worker: Worker, operation: Operation) -> None:
        """Wrap a constructed but unrun copier Worker."""
        self._worker = worker
        self._operation = operation
        self._questions: tuple[Question, ...] | None = None

    @classmethod
    def open(
        cls,
        src: str | Path | None,
        dst: Path,
        *,
        vcs_ref: str | None = None,
        answers_file: Path | None = None,
        operation: Operation = "copy",
        unsafe: bool = False,
    ) -> TemplateAdapter:
        """Fetch the template, gate its unsafe features, and check it carries a copier config."""
        worker = Worker(
            src_path=None if src is None else str(src),
            dst_path=Path(dst),
            vcs_ref=vcs_ref,
            answers_file=answers_file,
            unsafe=unsafe,
        )
        adapter = cls(worker, operation)
        try:
            root = worker.template.local_abspath
            if not _config_paths(root):
                raise TemplateLoadError(f"No copier configuration file in {root}")
            worker._check_unsafe("update" if operation == "update" else "copy")
            _ = worker.jinja_env
            adapter.questions()
        except TemplateLoadError:
            worker._cleanup()
            raise
        except Exception as error:
            worker._cleanup()
            raise TemplateLoadError(str(error)) from error
        return adapter

    def source_name(self) -> str:
        """The template's short name: the last segment of wherever it came from.

        copier accepts a local path, a git URL and its own `gh:owner/repo` shorthand, and on an
        update it takes the source from the answers file rather than the command line, so the
        name is read back off the worker instead of the argument. A `.git` suffix is dropped
        because it names the transport, not the template.
        """
        source = self._worker.src_path or getattr(self._worker.template, "url", "") or ""
        tail = str(source).rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
        return tail.removesuffix(".git") or "template"

    def questions(self) -> tuple[Question, ...]:
        """Normalised questions in copier.yml declaration order."""
        if self._questions is None:
            self._questions = tuple(
                self._normalise(id, details)
                for id, details in self._worker.template.questions_data.items()
            )
        return self._questions

    def groups(self) -> tuple[Group, ...]:
        """The template's `_ui_groups`, or the single untitled group covering everything."""
        return _groups_of(self._worker.template.config_data.get("ui_groups"), self.questions())

    def last_answers(self) -> dict[str, Any]:
        """The destination's answers file, with every underscore-prefixed key dropped."""
        return {
            key: value
            for key, value in self._worker.subproject.last_answers.items()
            if not key.startswith("_")
        }

    def evaluate(self, id: str, answers: Mapping[str, Any]) -> Evaluation:
        """Resolve one question's visibility, default and choices against the given answers."""
        load_error = self._load_error(id)
        if load_error is not None:
            return Evaluation(
                visible=True, default=None, has_default=False, choices=(), error=load_error
            )
        details = dict(self._worker.template.questions_data[id], validator="")
        with Phase.use(Phase.PROMPT):
            try:
                question = self._copier_question(id, answers, details)
                visible = question.get_when()
                choices = _choices_of(question)
                default = question.get_default()
            except Exception as error:  # noqa: BLE001 - a failed expression is a value here
                return Evaluation(
                    visible=True,
                    default=None,
                    has_default=False,
                    choices=(),
                    error=_redact(str(error), self.questions(), answers),
                )
        if default is MISSING:
            return Evaluation(
                visible=visible, default=None, has_default=False, choices=choices, error=None
            )
        return Evaluation(
            visible=visible, default=default, has_default=True, choices=choices, error=None
        )

    def validate(self, id: str, value: Any, answers: Mapping[str, Any]) -> tuple[str, ...]:
        """Coerce and validate one value, returning messages instead of raising."""
        load_error = self._load_error(id)
        if load_error is not None:
            return (load_error,)
        with Phase.use(Phase.PROMPT):
            try:
                question = self._copier_question(id, answers)
                question.validate_answer(question.parse_answer(value))
            except Exception as error:  # noqa: BLE001 - user input problems are values
                return (_redact(str(error), self.questions(), answers),)
        return ()

    def run(self, dst: Path, data: Mapping[str, Any], **copier_kwargs: Any) -> None:
        """Dispatch to run_copy, run_recopy or run_update with the answers as data."""
        kwargs: dict[str, Any] = {
            "vcs_ref": self._worker.vcs_ref,
            "answers_file": self._worker.answers_file,
            **copier_kwargs,
        }
        if self._operation == "copy":
            run_copy(str(self._worker.template.url), dst, dict(data), **kwargs)
        elif self._operation == "recopy":
            run_recopy(dst, dict(data), **kwargs)
        else:
            run_update(dst, dict(data), **kwargs)

    def close(self) -> None:
        """Drop the template's temporary clone."""
        self._worker._cleanup()

    def _copier_question(
        self,
        id: str,
        answers: Mapping[str, Any],
        details: Mapping[str, Any] | None = None,
    ) -> CopierQuestion:
        """Build a fresh copier Question bound to a render context for these answers."""
        if details is None:
            details = self._worker.template.questions_data[id]
        self._worker.answers = AnswersMap(user=dict(answers))
        return CopierQuestion(
            var_name=id,
            answers=self._worker.answers,
            context=self._worker._render_context(),
            jinja_env=self._worker.jinja_env,
            settings=self._worker.settings,
            **details,
        )

    def _load_error(self, id: str) -> str | None:
        """The load error of a question, or None when it was normalised cleanly."""
        for question in self.questions():
            if question.id == id:
                return question.load_error
        return None

    def _normalise(self, id: str, details: Mapping[str, Any]) -> Question:
        """Turn one raw copier.yml question block into a model Question."""
        try:
            with Phase.use(Phase.PROMPT):
                question = self._copier_question(id, {}, details)
                kind = _kind_of(
                    question.get_type_name(),
                    choices=bool(question.choices),
                    multiselect=question.multiselect,
                    secret=question.secret,
                )
                multiline = question.get_multiline()
                placeholder = question.get_placeholder()
                validator_source = str(details.get("validator", ""))
                # copier's own prompt caption: the rendered help, or `var_name (type)`
                # when the template declares none. A drop-in must not show less than copier.
                label = _one_line(question.get_message()) or id
                help = _one_line(question.render_value(details.get("help", "")))
        except Exception as error:  # noqa: BLE001 - a broken question is reported, not raised
            return Question(
                id=id,
                kind=Kind.STRING,
                label=id,
                help="",
                secret=False,
                multiselect=False,
                multiline=False,
                placeholder="",
                default_source=None,
                choices_source=None,
                when_source=True,
                validator_source="",
                validated=False,
                constraints=(),
                condition_ids=(),
                dependencies=(),
                load_error=f"{id}: {error}",
            )
        return Question(
            id=id,
            kind=kind,
            label=label,
            help=help,
            secret=question.secret,
            multiselect=question.multiselect,
            multiline=multiline,
            placeholder=placeholder,
            default_source=None if question.secret else details.get("default"),
            choices_source=details.get("choices"),
            when_source=details.get("when", True),
            validator_source=validator_source,
            validated=bool(validator_source.strip()),
            constraints=_constraints_of(kind),
            condition_ids=tuple(
                dependency
                for dependency in self._dependencies(details.get("when"))
                if dependency != id
            ),
            dependencies=tuple(
                dependency
                for dependency in self._dependencies(
                    details.get("when"), details.get("default"), details.get("choices")
                )
                if dependency != id
            ),
            load_error=None,
        )

    def _dependencies(self, *sources: Any) -> tuple[str, ...]:
        """Question ids referenced by the given Jinja sources, via jinja2.meta over the AST."""
        ids = set(self._worker.template.questions_data)
        found: set[str] = set()
        for source in _templates(sources):
            try:
                ast = self._worker.jinja_env.parse(source)
            except TemplateSyntaxError:
                continue
            found |= meta.find_undeclared_variables(ast) & ids
        return tuple(sorted(found))


def _redact(message: str, questions: tuple[Question, ...], answers: Mapping[str, Any]) -> str:
    """Replace every secret answer's string form in a message with three asterisks."""
    for question in questions:
        if question.secret:
            secret = str(answers.get(question.id, ""))
            if secret:
                message = message.replace(secret, "***")
    return message


def _config_paths(root: Path) -> list[Path]:
    """The template's copier.yml / copier.yaml files, matching copier's own glob."""
    return [
        path
        for path in root.glob("copier.*")
        if path.is_file() and re.match(r"\.ya?ml", path.suffix, re.IGNORECASE)
    ]


def _templates(source: Any) -> Iterator[str]:
    """Every string inside a raw copier.yml value, however deeply nested."""
    if isinstance(source, str):
        yield source
    elif isinstance(source, Mapping):
        for key, value in source.items():
            yield from _templates(key)
            yield from _templates(value)
    elif isinstance(source, (list, tuple)):
        for item in source:
            yield from _templates(item)


def _groups_of(raw: Any, questions: tuple[Question, ...]) -> tuple[Group, ...]:
    """Partition the questions into groups, in declaration order, never reordering them.

    copier.yml has no group of its own, so this reads the optional `_ui_groups` key - a list of
    `{title, fields}` blocks - which copier carries through its config untouched. A template
    that declares none, which is nearly all of them, gets one untitled group holding every
    question, so a frontend has exactly one code path either way.
    """
    titles = _group_titles(raw, {question.id for question in questions})
    runs: list[tuple[str, bool, list[str]]] = []
    for question in questions:
        title = titles.get(question.id, "")
        declared = question.id in titles
        if runs and runs[-1][0] == title and runs[-1][1] == declared:
            runs[-1][2].append(question.id)
        else:
            runs.append((title, declared, [question.id]))
    return tuple(
        Group(title=title, ids=tuple(ids), declared=declared) for title, declared, ids in runs
    )


def _group_titles(raw: Any, ids: set[str]) -> dict[str, str]:
    """Map question id to group title, dropping anything the key got wrong.

    A group heading is decoration: a template that misspells a field, names one it does not
    have, or writes the whole key as the wrong shape must still load and still render. So every
    malformed part is skipped rather than raised, and the questions it would have covered fall
    back to being ungrouped. The first group to claim a field keeps it.
    """
    if not isinstance(raw, list):
        return {}
    titles: dict[str, str] = {}
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        title = _one_line(entry.get("title"))
        fields = entry.get("fields")
        if not title or not isinstance(fields, list):
            continue
        for field in fields:
            if isinstance(field, str) and field in ids and field not in titles:
                titles[field] = title
    return titles


_KIND_CONSTRAINT = {
    Kind.INTEGER: "a whole number",
    Kind.FLOAT: "a number",
    Kind.PATH: "a filesystem path",
    Kind.STRUCTURED: "valid JSON",
}
"""What a kind requires of a value, phrased for a person. A UI can say this before the user has
typed anything; copier itself refuses the value at parse time."""


def _constraints_of(kind: Kind) -> tuple[str, ...]:
    """The rules a question declares, without running its validator.

    copier has no field types beyond the kinds - no email, no IP address, no pattern. A template
    that wants one writes a validator, and the only honest description of a validator is the
    message it produces, which takes a value to produce; `Question.validated` marks that such a
    rule exists and `TemplateUI.check` asks it what it wants.

    The permitted set of a choice question is deliberately absent: choices are recomputed per
    answer set, so they belong to `FieldState.choices` and not to the immutable declaration.
    """
    constraint = _KIND_CONSTRAINT.get(kind)
    return () if constraint is None else (constraint,)


def _one_line(text: Any) -> str:
    """Collapse a rendered template string to the single line a label or hint can hold."""
    return " ".join(str(text or "").split())


def _kind_of(type_name: str, *, choices: bool, multiselect: bool, secret: bool) -> Kind:
    """Map a copier type name plus its modifiers to exactly one Kind."""
    if multiselect:
        return Kind.MULTISELECT
    if choices:
        return Kind.CHOICE
    if secret:
        return Kind.SECRET
    return _KIND_BY_TYPE[type_name]


def _choices_of(question: CopierQuestion) -> tuple[Choice, ...]:
    """Render copier's formatted choices into ordered label/value pairs."""
    if not question.choices:
        return ()
    return tuple(
        Choice(label=str(choice.title), value=choice.value)
        for choice in question._formatted_choices
    )
