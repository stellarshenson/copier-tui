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
- `copier._main.confirm` - the name copier asks `Overwrite <path>?` through; replaced for the
  length of one run, because copier has no parameter for who answers
- `copier._main.unsafe_prompt` - the name copier prompts for a question through; replaced for
  the same run with one that raises for a question that would be asked and skips a hidden
  one, because that prompt reads the terminal
- `copier.run_copy` / `run_recopy` / `run_update` - the only public entry points
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any

from copier import Phase, run_copy, run_recopy, run_update
import copier._main as copier_main
from copier._main import Worker
from copier._types import MISSING
from copier._user_data import AnswersMap
from copier._user_data import Question as CopierQuestion
from jinja2 import TemplateSyntaxError, meta

from copier_ui.errors import CopierUIError, TemplateLoadError
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
        # data given under a name that is no question: no row holds it; a default, a `when`,
        # the choices and a validator read it
        self.extra: dict[str, Any] = {}

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
            # before the template is even fetched, as copier orders it: a dirty destination is
            # the reader's own uncommitted work, and telling them the template is missing when
            # the real answer is "commit first" sends them to look in the wrong place
            _check_updatable(worker, operation)
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

    def parse(self, id: str, value: Any, answers: Mapping[str, Any]) -> Any:
        """A supplied answer as copier hands it on to later questions: `Question.parse_answer`.

        A control gives back text and `--data` gives command-line text. copier parses each
        answer when its question's turn comes - the number out of `3`, the list out of
        `[docs, ci]` - and the questions after it read the parsed value. An answer that does
        not parse is given back as it is, and `validate` reports it on its own field.
        """
        if self._load_error(id) is not None:
            return value
        with Phase.use(Phase.PROMPT):
            try:
                return self._copier_question(id, answers).parse_answer(value)
            except Exception:  # noqa: BLE001 - what does not parse is its own field's to report
                return value

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
                return (_plain_message(_redact(str(error), self.questions(), answers)),)
        return ()

    def run(
        self,
        dst: Path,
        data: Mapping[str, Any],
        confirm: Callable[[str], bool] | None = None,
        **copier_kwargs: Any,
    ) -> None:
        """Dispatch to run_copy, run_recopy or run_update with the answers as data.

        `confirm` answers the yes/no question copier asks while it runs; without one copier
        asks on the terminal, as it always has. With one, a template question copier would
        prompt for ends the run with a `CopierUIError` naming it.
        """
        kwargs: dict[str, Any] = {
            "vcs_ref": self._worker.vcs_ref,
            "answers_file": self._worker.answers_file,
            **copier_kwargs,
        }
        with _questions_put_to(confirm):
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
        """Build a fresh copier Question bound to a render context for these answers.

        A default, a `when`, the choices and a validator read the sources copier's own `_ask`
        gives an expression: the answers, the data that is no question's answer, the keys of
        the answers file that are no question's name, the template's metadata (`_src_path`,
        `_commit`) and its external data. A default reads `init` and `last` under its own
        question's name, and neither holds a question's name here, so every default stays the
        template's own: an answers-file key that is a question's name reaches the form as an
        answer, on `update` and `recopy`. `from_template` takes no user defaults.
        """
        if details is None:
            details = self._worker.template.questions_data[id]
        self._worker.answers = AnswersMap(
            user=dict(answers),
            init=self.extra,
            last={
                key: value
                for key, value in self._worker.subproject.last_answers.items()
                if key not in self._worker.template.questions_data
            },
            metadata=self._worker.template.metadata,
            external=self._worker._external_data(),
        )
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
                placeholder = _or_blank(question.get_placeholder)
                validator_source = str(details.get("validator", ""))
                # copier's own prompt caption: the rendered help, or `var_name (type)`
                # when the template declares none. A drop-in must not show less than copier.
                label = _one_line(_or_blank(question.get_message)) or id
                help = _one_line(_or_blank(lambda: question.render_value(details.get("help", ""))))
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


@contextmanager
def _questions_put_to(confirm: Callable[[str], bool] | None) -> Iterator[None]:
    """Hand the yes/no question copier asks mid-run to `confirm` instead of the terminal.

    copier asks `Overwrite <path>?` whenever a file it rendered differs from the one already
    in the destination and `overwrite` is off, and it asks through questionary, which reads
    the terminal itself. A frontend drawing its own interface on that terminal is already
    reading it: the question is written where nobody sees it and the run waits for an answer
    that cannot arrive. copier decides everything else about the conflict - the skip patterns,
    `overwrite`, the answers file - and only the asking is replaced, with copier's own wording.

    copier's other prompt, the one that asks a question of the template, waits the same way and
    has no yes or no to hand over: the answers were the caller's to supply. It ends the run
    with the question's name, which is a failure the caller can show. A run told to take
    copier's defaults, which is every run `TemplateUI.render` starts, reaches that prompt only
    for a question named by `ask`. Without that, copier sends its hidden questions through
    the prompt as well and relies on it to skip one whose `when` is false and give back the
    default it was handed, so that much of the prompt is kept.
    """
    if confirm is None:
        yield
        return
    original = copier_main.confirm, copier_main.unsafe_prompt

    def ask(message: str, **_: Any) -> SimpleNamespace:
        return SimpleNamespace(unsafe_ask=lambda: confirm(message.strip()))

    def refuse(
        questions: list[dict[str, Any]], answers: Mapping[str, Any] | None = None, **_: Any
    ) -> dict[str, Any]:
        for question in questions:
            if question["when"](answers):
                raise CopierUIError(
                    f"copier asked for `{question['name']}` during the render, a question it "
                    "was given no answer to; the render was stopped because nothing there can "
                    "answer it"
                )
        return dict(answers or {})

    copier_main.confirm, copier_main.unsafe_prompt = ask, refuse
    try:
        yield
    finally:
        copier_main.confirm, copier_main.unsafe_prompt = original


def _check_updatable(worker: Worker, operation: Operation) -> None:
    """Refuse an update on the three grounds copier checks first, before a question is asked.

    Not a git repository, a repository with uncommitted work, and a destination that does not
    record which template and version it was rendered from. copier makes four further checks -
    a template that is not git-tracked, a version it cannot detect either side of, a
    downgrade - and those still fire at render: each one copied here is another verbatim copy
    of a copier string with nothing keeping the two in step. The third earns its copy because
    without it the loader goes on to fetch a template the destination never named, and the
    reader of an `update`, which takes no template, is told `Template not found`.

    copier makes them itself, but not until it runs - which for this front end is
    after the survey. A user who is told to commit their work only once they have answered
    thirty-seven questions has been made to do the work twice, and the second refusal is the
    one that arrives with a filled-in form to throw away. The wording is copier's own, so the
    two tools give the same answer to the same situation.
    """
    if operation != "update":
        return
    subproject = worker.subproject
    if subproject.vcs != "git":
        raise TemplateLoadError("Updating is only supported in git-tracked subprojects.")
    if subproject.is_dirty():
        raise TemplateLoadError(
            "Destination repository is dirty; cannot continue. "
            "Please commit or stash your local changes and retry."
        )
    if subproject.template is None or subproject.template.ref is None:
        raise TemplateLoadError(
            "Cannot update because cannot obtain old template references "
            f"from `{subproject.answers_relpath}`."
        )


_VALIDATION_PREFIX = re.compile(r"^Validation error for question '[^']*':\s*")
"""copier's own preamble in front of a template author's validation message.

Thirty-eight characters restating what the row already says - which field, and that something
is wrong with it - in front of the one sentence that says what. On a one-row status line and a
help line of two, the preamble is what fits and the answer is what is cut."""


def _plain_message(message: str) -> str:
    """A validation message without copier's preamble, or unchanged when it has none."""
    return _VALIDATION_PREFIX.sub("", message, count=1)


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


def _or_blank(caption: Callable[[], str]) -> str:
    """What `caption` renders, or nothing when it cannot be rendered yet.

    A help text and a placeholder are rendered once, at load, before any answer exists. One
    that calls a method on an answer, or does arithmetic on it, fails there. The row is then
    shown without it. Refused, it kept a project from being made that copier renders: copier
    prints no caption in a run it is handed the answers for.
    """
    try:
        return caption()
    except Exception:  # noqa: BLE001 - whatever a template's expression raises
        return ""


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
        # collapsed like every other display string this module hands out. A break inside a
        # label is a break no single-line chip can render, and it defeats the option row's
        # wrapper outright: the splitter does not treat it as a break, so the height counts
        # one line for text that paints as two and the options after it are cut off screen
        Choice(label=_one_line(str(choice.title)), value=choice.value)
        for choice in question._formatted_choices
    )
