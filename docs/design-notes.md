# Design Notes - copier-ui and copier-tui

Module map, public signatures and copier API notes for the two packages. This document is the
implementation contract: the names and signatures below are fixed, the bodies are not.
Acceptance criteria live in [acc-crit-copier-tui.md](acc-crit-copier-tui.md).

## Contents

- [Dependency graph](#dependency-graph)
- [copier API notes](#copier-api-notes)
- [copier_ui.errors](#copier_uierrors)
- [copier_ui.model](#copier_uimodel)
- [copier_ui.adapter](#copier_uiadapter)
- [copier_ui.engine](#copier_uiengine)
- [copier_ui.api](#copier_uiapi)
- [copier_tui.errors](#copier_tuierrors)
- [copier_tui.theme](#copier_tuitheme)
- [copier_tui.widgets](#copier_tuiwidgets)
- [copier_tui.screens](#copier_tuiscreens)
- [copier_tui.app](#copier_tuiapp)
- [copier_tui.cli](#copier_tuicli)
- [Decisions and deviations](#decisions-and-deviations)

## Dependency graph

One direction only. No module imports a module below it in this list.

```
copier_tui.cli  ->  copier_tui.app  ->  copier_tui.screens  ->  copier_tui.widgets  ->  copier_tui.theme
                                                                        |
                                                                        v
                                                             copier_ui.api  ->  copier_ui.engine
                                                                   |                   |
                                                                   v                   v
                                                             copier_ui.adapter  ->  copier_ui.model
                                                                   |                   |
                                                                   v                   v
                                                                 copier             copier_ui.errors
```

- `copier_ui.engine` never imports `copier_ui.adapter` - it receives evaluation as the callables
  `Evaluator` and `FieldValidator`, both declared in `model`
- `copier_ui.adapter` is the only module in either package that imports `copier`
- nothing in `copier_ui` imports `copier_tui`, textual, rich, prompt_toolkit or curses
- `copier_tui.cli` imports `copier._cli` classes to subclass them - see the CLI section

## copier API notes

copier 9.17.2 marks everything except six names as internal: `copier.__init__.__getattr__` calls
`deprecate_member_as_internal` for any access outside `run_copy`, `run_recopy`, `run_update`,
`Phase`, `Settings`, `VcsRef`, `load_settings`. Import internals from the underscore modules
(`copier._main`, `copier._user_data`, `copier._template`), never from the deprecated shims
(`copier.main`, `copier.user_data`), which emit a `DeprecationWarning` per attribute access.

Stable - public, safe to call directly:

- `copier.run_copy(src_path, dst_path=".", data=None, *, answers_file, vcs_ref, settings, exclude, use_prereleases, skip_if_exists, cleanup_on_error, defaults, user_defaults, overwrite, pretend, quiet, unsafe, skip_tasks, ask) -> Worker`
- `copier.run_recopy(dst_path=".", data=None, *, ... , skip_answered, ...) -> Worker` - no `src_path`
- `copier.run_update(dst_path=".", data=None, *, ... , conflict, context_lines, skip_answered, ...) -> Worker`
- `copier.Phase` - context manager `Phase.use(Phase.PROMPT)`; `_render_context` exposes it as `_copier_phase`
- `copier.VcsRef.CURRENT` - the `:current:` sentinel accepted by `vcs_ref`
- answers supplied in `data` are never prompted for: `Worker._ask` sees them in `AnswersMap.init`,
  parses, validates and continues. This is the whole mechanism the project rests on

Unstable - internals the adapter uses, each one a single call site so a copier upgrade is a
one-file fix:

- `copier._main.Worker(src_path=..., dst_path=..., vcs_ref=..., answers_file=...)` - constructed but
  never run. Used purely as the loader: it owns template fetch, the Jinja environment and the
  render context. Pydantic dataclass with `extra="forbid"`
- `Worker.template` -> `copier._template.Template` - clones a git URL into a temp dir on first
  access to `local_abspath`; `Worker._cleanup()` removes it
- `Template.questions_data: dict[str, dict]` - raw question blocks in `copier.yml` declaration
  order (Python dicts preserve insertion order, and copier's YAML loader is ordered)
- `Template.local_abspath: Path` - resolved template root, after cloning
- `Worker.jinja_env: SandboxedEnvironment` - template `envops` and `_jinja_extensions` applied.
  Also the parser for dependency extraction
- `Worker._render_context() -> dict` - the Jinja context: combined answers plus `_copier_conf`
  (with `src_path`, `dst_path`, `answers_file`), `_folder_name`, `_copier_python`, `_copier_phase`.
  Must be rebuilt after every answer change - it snapshots `Worker.answers.combined`
- `Worker.answers: AnswersMap` - assign a fresh `AnswersMap(user=<current answers>)` before each
  `_render_context()` call
- `copier._user_data.Question(var_name=..., answers=..., context=..., jinja_env=..., **details)` -
  copier's own question object. Build a fresh one per evaluation: `_formatted_choices` is a
  `cached_property` and would freeze templated choices otherwise
- `Question.get_when() -> bool`, `.get_default() -> Any`, `._formatted_choices -> Sequence[Choice]`,
  `.parse_answer(value)`, `.validate_answer(value)`, `.get_type_name() -> str`,
  `.get_multiline() -> bool`, `.get_placeholder() -> str`
- `copier._types.MISSING` - the sentinel `get_default()` returns when there is no default
- `copier._subproject.Subproject(local_abspath=..., answers_relpath=...).last_answers` - the
  destination's `.copier-answers.yml`, private keys already filtered except `_src_path`/`_commit`
- `questionary.prompts.common.Choice` - what `_formatted_choices` yields: `title` (the label, a
  str), `value`, `disabled` (a rendered validator message; non-empty means the option is refused)
- `copier.errors.InvalidTypeError`, `UserMessageError`, `ConfigFileError`, `UnsafeTemplateError`,
  `ExtensionNotFoundError`

Behaviours worth knowing:

- **No copier.yml is not an error in copier** - `Template._raw_config` returns `{}` when the glob
  `copier.*` filtered to `.yml`/`.yaml` finds nothing. The adapter reproduces that glob and raises
  `TemplateLoadError` itself, otherwise a typo'd path would yield an empty survey
- **Type defaulting** - an omitted `type` becomes the Python type name of the literal default, or
  `yaml`. `type` itself may be templated; `get_type_name()` renders it and raises `InvalidTypeError`
  for anything outside `bool|float|int|json|str|yaml|path`
- **Simplified questions** - `filter_config` rewrites a non-dict question body into `{"default": v}`
- **`secret: true` requires a default** - enforced by a pydantic validator on copier's `Question`
- **Choice extended syntax** - a dict-shaped choice value carries `value` and an optional
  `validator`; a non-empty rendered validator disables the choice. `parse_answer` raises for a
  disabled or unknown choice, which is how the adapter reports it as a validation message
- **`when: false`** - a computed field. copier hides it and recomputes its default from the
  template, so the adapter reports it invisible and the answers handed to copier omit it, leaving
  copier to compute it. This is what makes `project_name`, `python_version_number` and
  `cookiecutter` in copier-data-science work unchanged
- **Settings** - `Worker.settings` defaults to `SettingsModel.from_file()`, which reads the user's
  copier settings. Left at the default, so `settings.defaults` and trust behave as under copier
- **Local templates get cloned too** - any git-tracked template, local path included, is cloned
  into a temp dir on first `local_abspath` access, so `close()` is not optional
- **Jinja extensions load eagerly** - the first `Worker.jinja_env` access imports every
  `_jinja_extensions` entry and raises `ExtensionNotFoundError` when one is missing. Loading
  copier-data-science needs `jinja2-time` installed; the adapter reports it as `TemplateLoadError`

Verified against copier-data-science on copier 9.17.2: 41 questions in declaration order,
`project_name` defaulting to `demo-proj` from `_copier_conf.dst_path.name`, `repo_name` recomputing
to `my_proj` when `project_name` changes, `dependency_file` choices growing `environment.yml` when
`environment_manager` flips to `conda`, `python_version_custom` becoming visible when
`python_version_choice` is `other`, `cookiecutter` (`type: json`, `when: false`) resolving to `{}`,
a bad choice raising `ValueError` from `parse_answer`, and `jinja2.meta.find_undeclared_variables`
over `jinja_env.parse(...)` returning exactly the referenced question ids.

## copier_ui.errors

Exception hierarchy. No dependencies.

- `CopierUIError(Exception)` - base
- `TemplateLoadError(CopierUIError)` - template missing, unfetchable, or its config unreadable
- `CircularDependencyError(TemplateLoadError)` - field `cycle: tuple[str, ...]`
- `UnknownFieldError(CopierUIError, KeyError)` - a question id not in the schema
- `RenderRefusedError(CopierUIError)` - field `errors: dict[str, list[str]]`

## copier_ui.model

Frozen dataclasses and the two callable types. Imports only `errors` and the stdlib.

- `Kind(StrEnum)` - `STRING BOOL INTEGER FLOAT PATH STRUCTURED CHOICE MULTISELECT SECRET`
- `Operation = Literal["copy", "update", "recopy"]`
- `Evaluator = Callable[[str, Mapping[str, Any]], Evaluation]`
- `FieldValidator = Callable[[str, Any, Mapping[str, Any]], tuple[str, ...]]`

`Choice` - one selectable option, `copier.yml` order preserved.

- `label: str`
- `value: Any`

`Question` - one normalised question. Declared data only; nothing here depends on answers.

- `id: str`
- `kind: Kind`
- `label: str` - the question id; copier has no separate label
- `help: str` - raw `help` text, `""` when absent
- `secret: bool`
- `multiselect: bool`
- `multiline: bool`
- `placeholder: str`
- `default_source: Any` - raw `default` as declared, `None` for a secret question
- `choices_source: Any` - raw `choices` as declared: list, dict or Jinja string
- `when_source: str | bool` - raw `when`, `True` when absent
- `validator_source: str` - raw `validator`, `""` when absent
- `dependencies: tuple[str, ...]` - question ids referenced by `when`, `default` and `choices`, sorted
- `load_error: str | None` - the question could not be built; it is visible, disabled and blocking

`Schema` - the ordered question set.

- `questions: tuple[Question, ...]` - `copier.yml` declaration order
- `ids() -> tuple[str, ...]`
- `by_id(id: str) -> Question` - raises `UnknownFieldError`

`Evaluation` - one question resolved against one answer set. Produced by the adapter.

- `visible: bool`
- `default: Any` - rendered and cast; `None` when copier reports `MISSING`
- `has_default: bool`
- `choices: tuple[Choice, ...]`
- `error: str | None` - the `when`, `default` or `choices` expression failed to render

`FieldState` - one question's live state.

- `id: str`
- `value: Any`
- `visible: bool`
- `enabled: bool` - `False` when the question carries a load error or its expressions failed
- `is_default: bool` - the value is the computed default, not one the user set
- `preset: bool` - supplied through `data`, so the frontend must not ask for it
- `secret: bool`
- `choices: tuple[Choice, ...]`
- `errors: tuple[str, ...]`
- `__repr__` renders `value` as `'***'` when `secret`

`State` - the whole survey's live state.

- `fields: Mapping[str, FieldState]` - declaration order
- `visible_ids: tuple[str, ...]` - declaration order, visible only
- `to_dict() -> dict[str, Any]` - JSON-compatible; secret values replaced with `None`

## copier_ui.adapter

The only module that imports copier. Owns template fetch, question normalisation, expression
evaluation and the copier run. Its module docstring says so.

- `TemplateAdapter.open(src: str | Path | None, dst: Path, *, vcs_ref: str | None = None, answers_file: Path | None = None, operation: Operation = "copy") -> TemplateAdapter` - raises `TemplateLoadError`
- `TemplateAdapter.questions() -> tuple[Question, ...]` - declaration order, computed once
- `TemplateAdapter.last_answers() -> dict[str, Any]` - the destination answers file, every
  `_`-prefixed key dropped
- `TemplateAdapter.evaluate(id: str, answers: Mapping[str, Any]) -> Evaluation` - satisfies `Evaluator`
- `TemplateAdapter.validate(id: str, value: Any, answers: Mapping[str, Any]) -> tuple[str, ...]` -
  coercion and `validator` in one pass; returns messages, never raises for user input. Satisfies
  `FieldValidator`
- `TemplateAdapter.run(dst: Path, data: Mapping[str, Any], **copier_kwargs: Any) -> None` -
  dispatches on `operation` to `run_copy` / `run_recopy` / `run_update`
- `TemplateAdapter.close() -> None` - drops the temp clone

Rules:

- every evaluation runs inside `Phase.use(Phase.PROMPT)`, matching copier's own prompt phase
- `evaluate` builds a fresh `AnswersMap(user=dict(answers))` and a fresh `copier` `Question`, so
  templated `default`, `when` and `choices` see the current answers and nothing is cached
- `AnswersMap.init` and `.last` stay empty during evaluation: the adapter reports the template's
  own computed default, and prior answers reach the engine as explicit values instead
- a question that cannot be built at all becomes a `Question` with `load_error` set and every
  other field at its neutral value
- a `when`, `default` or `choices` that fails to render yields `Evaluation(visible=True,
  error=<message>)`, leaving the rest of the state usable

## copier_ui.engine

Pure state algorithms over `model`. No copier, no I/O. Evaluation arrives as callables.

- `evaluation_order(schema: Schema) -> tuple[str, ...]` - topological order of the dependency graph,
  ties broken by declaration order; raises `CircularDependencyError` naming the cycle members.
  Evaluating in this order is what makes a forward reference resolve against the referenced
  question's current default
- `compute_state(schema: Schema, order: Sequence[str], explicit: Mapping[str, Any], preset: AbstractSet[str], evaluate: Evaluator) -> State` -
  one pass in `order`, threading each resolved value into the answer map the next `evaluate` sees.
  A value in `explicit` wins over the computed default and sets `is_default=False`. Hidden fields
  keep their value in the answer map so dependents can read them
- `validate_state(schema: Schema, state: State, validate_field: FieldValidator) -> dict[str, list[str]]` -
  visible fields only; merges each field's own `errors` with the validator's messages; empty dict
  means valid
- `visible_answers(state: State) -> dict[str, Any]` - visible fields only, JSON-compatible

## copier_ui.api

The facade. Holds the adapter, the schema, the explicit answers and the preset ids; recomputes
after every `set`.

- `TemplateUI.from_template(src: str | Path | None, vcs_ref: str | None = None, answers_file: str | Path | None = None, *, dst: str | Path = ".", data: Mapping[str, Any] | None = None, operation: Operation = "copy") -> TemplateUI`
- `TemplateUI.schema() -> Schema`
- `TemplateUI.set(id: str, value: Any) -> None` - raises `UnknownFieldError`; accepted for a hidden
  field and retained
- `TemplateUI.state() -> State`
- `TemplateUI.answers() -> dict[str, Any]`
- `TemplateUI.validate() -> dict[str, list[str]]`
- `TemplateUI.render(dst: str | Path | None = None, **copier_kwargs: Any) -> None` - raises
  `RenderRefusedError` when `validate()` is non-empty; passes `answers()` as `data`
- `TemplateUI.close() -> None`, `__enter__`, `__exit__`

Seeding at load, in increasing precedence: the destination answers file (for `update` and
`recopy`), then `data`. Both land in the explicit answers; only `data` ids are marked `preset`.

## copier_tui.errors

Errors and exit codes for the terminal frontend.

- `TuiError(Exception)` - base
- `NotATerminalError(TuiError)` - stdin or stdout is not a tty
- `EXIT_OK = 0`, `EXIT_FAILURE = 1`, `EXIT_CANCELLED = 2`

## copier_tui.theme

Palette and shared CSS from the `text-user-interface` skill. Constants only, no widgets.

- colour constants: `CYAN`, `CYAN_BRIGHT`, `ORANGE`, `AMBER`, `MINT`, `ROSE`, `SCREEN_BG`,
  `CHROME_BG`, `SURFACE_BG`, `BORDER`, `TEXT`, `TEXT_MUTED`, `TEXT_SUBTLE`
- `HEADER_CSS: str` - the shared one-row header rules
- `BASE_CSS: str` - screen, chrome and focus-ring rules common to every screen
- `MIN_WIDTH: int`, `MIN_HEIGHT: int` - below either, the app shows the resize prompt

## copier_tui.widgets

Kind to widget mapping and the field row. Holds no semantics: label, help, value, choices, error
and default-ness all arrive from `copier_ui` state.

- `WIDGET_BY_KIND: Mapping[Kind, type[Widget]]` - string/path -> `Input`, secret -> `Input`
  (`password=True`), bool -> `Switch`, integer/float -> `Input` (numeric), choice -> `Select`,
  multiselect -> `SelectionList`, structured -> `TextArea`
- `control_for(question: Question, field: FieldState) -> Widget` - the control alone, prefilled
- `read_control(question: Question, control: Widget) -> Any` - the control's current value
- `HeaderBar(Horizontal)` - app name left, version right; `__init__(context: str = "")`
- `FieldRow(Vertical)` - label, help, control, error line, default marker
  - `__init__(question: Question, field: FieldState)`
  - `update(field: FieldState) -> None`
  - `value: Any` - property reading the control
  - `FieldRow.Changed(Message)` - fields `field_id: str`, `value: Any`

## copier_tui.screens

One screen per module, re-exported from `screens/__init__.py`.

`screens/survey.py` - the whole visible survey as one scrolling form, which is what makes free
back-and-forward navigation and live revisibility fall out for nothing.

- `SurveyScreen(Screen[bool])` - `__init__(ui: TemplateUI)`; returns `True` to advance to review,
  `False` on cancel. Rebuilds rows from `ui.state()` after every `FieldRow.Changed`; skips fields
  that are not `visible` or are `preset`; renders `errors` inline without blocking navigation
- `JumpScreen(ModalScreen[str | None])` - `__init__(state: State, schema: Schema)`; the overview of
  visible questions and their current values, returns the chosen field id

`screens/review.py`

- `ReviewScreen(Screen[bool])` - `__init__(ui: TemplateUI, dst: Path)`; every answer listed, a
  warning when `dst` exists and is not empty, confirm or back. Nothing is written before it returns

`screens/execution.py`

- `ExecutionScreen(Screen[bool])` - `__init__(ui: TemplateUI, dst: Path, copier_kwargs: dict[str, Any])`;
  runs `ui.render` in a thread, indeterminate progress until it returns, then the verdict banner.
  Returns success. On failure it shows copier's message and leaves partial output alone

## copier_tui.app

The Textual application and the survey entry point.

- `SurveyApp(App[int])` - `__init__(ui: TemplateUI, dst: Path, copier_kwargs: dict[str, Any])`;
  drives survey -> review -> execution, shows the resize prompt below `MIN_WIDTH`/`MIN_HEIGHT`,
  and returns one of the exit codes
- `run_survey(ui: TemplateUI, dst: Path, copier_kwargs: dict[str, Any]) -> int`

## copier_tui.cli

copier's own CLI, subclassed. plumbum collects subcommands across the MRO and lets a child class
override a parent's subcommand of the same name, so every switch, its short form, its help text
and its error handling are inherited rather than restated. Unknown flags and `--help` are copier's,
unchanged.

- `CopierTuiApp(copier._cli.CopierApp)` - `PROGNAME = "copier-tui"`, `VERSION` from the
  `copier-tui` distribution
- `TuiCopySubApp(copier._cli.CopierCopySubApp)` - registered as `copy`
- `TuiRecopySubApp(copier._cli.CopierRecopySubApp)` - registered as `recopy`
- `TuiUpdateSubApp(copier._cli.CopierUpdateSubApp)` - registered as `update`
- `main() -> None` - the `copier-tui` console script

Each subcommand's `main` is the only override:

1. `--defaults`, `--force` or `--quiet` present -> `return super().main(...)`, which is copier's own
   headless path with copier's exact semantics. No TUI, no `copier_ui`
2. stdin or stdout is not a tty -> print the `NotATerminalError` message, return `EXIT_FAILURE`
3. otherwise open a `TemplateUI` for the subcommand's operation, and on a load failure print the
   message and return `EXIT_FAILURE` before any screen opens; then `run_survey(...)`

`check-update` is inherited untouched - it never asks a question.

The remaining flags are not interpreted by `copier_tui`: each subcommand collects them into the
`copier_kwargs` dict it hands to `TemplateUI.render`, which forwards them to the matching `run_*`
function.

## Decisions and deviations

- **`from_template` takes `dst` and `operation`.** The criteria list
  `from_template(src, vcs_ref=None, answers_file=None)`; that call still works. `dst` is not
  optional in practice - `_copier_conf.dst_path` is in the render context and copier-data-science's
  first question defaults to `{{ _copier_conf.dst_path.name }}`. `operation` decides answers-file
  seeding and which `run_*` executes, and `src=None` resolves the template from the destination's
  answers file, as copier does for `update` and `recopy`
- **Kind precedence follows copier, not the criteria's reading order** - multiselect, then choice,
  then secret, then the base type; copier's own `get_questionary_structure` resolves it that way.
  `Question.secret` stays a separate flag, so a secret choice question is still masked
- **`Question` carries declared sources, not computed values.** `default_source` and `choices_source`
  are the raw `copier.yml` entries; the rendered default and the resolved choices are per-answer
  data and live in `Evaluation` / `FieldState`. A schema that changed with the answers could not be
  deterministic
- **`help` is not rendered.** copier renders `help` through Jinja; the adapter passes the declared
  text through. No template in scope templates its help, and rendering it would put help into
  `Evaluation` and re-render it on every keystroke. Revisit only if a real template needs it
- **Secret defaults never enter the schema.** `default_source` is `None` for a secret question, so
  no dump can leak it; the value still reaches the widget through `Evaluation.default`
- **A load error makes a field visible and disabled**, so it reaches validation and blocks the
  render rather than disappearing with the hidden fields
- **The engine takes callables, not the adapter.** `Evaluator` and `FieldValidator` keep the graph
  one-directional and let the engine be tested with a fake evaluator and no template on disk
