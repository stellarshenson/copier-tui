# Acceptance Criteria - copier-tui

Two packages: `copier-ui` normalises a copier template's questions into a UI-neutral schema with state, visibility and validation; `copier-tui` renders that schema in the terminal and calls copier once the user confirms. Scope here covers both; `copier-webui` and `copier-api` are out of scope.

## Contents

- [copier-ui](#copier-ui)
- [copier-tui](#copier-tui)

## copier-ui

UI-neutral core. Three layers - copier adapter (parses `copier.yml`), UI model (normalised questions), state engine (answers, dependencies, validation). Owns semantics only, never presentation.

- [ ] **Purity** - `copier_ui` imports nothing that assumes a display (textual, rich, prompt_toolkit, curses) and nothing that requires an event loop; enforced by an automated test over the package's import graph
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Sync API** - every public call is synchronous and returns; no coroutines, no background threads
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Load local** - `TemplateUI.from_template(path)` accepts a local template directory containing `copier.yml` or `copier.yaml`
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Load remote** - `from_template` accepts a git URL with optional `vcs_ref`, resolved through copier's own fetch
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Seed from answers file** - existing `.copier-answers.yml` in the destination seeds the answer state for the update flow; template-internal keys (`_commit`, `_src_path`) are not exposed as questions
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Question kinds** - each copier `type` maps to exactly one kind: `str` -> string, `bool` -> bool, `int` -> integer, `float` -> float, `path` -> path, `yaml`/`json` -> structured; a question with `choices` becomes choice, with `multiselect: true` becomes multiselect, with `secret: true` becomes secret
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Question fields** - normalised `Question` carries id, kind, label, help, default, choices, secret, multiselect, dependencies, visibility expression, validator
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Choice normalisation** - `choices` given as a list, a dict, or a list of single-key dicts all normalise to ordered `(label, value)` pairs; `copier.yml` order is preserved
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Declaration order** - `schema()` returns questions in `copier.yml` declaration order
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Dependency graph** - each question exposes the set of question ids referenced by its `when`, `default` and `choices` expressions
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Visibility** - `state().fields[id].visible` is the evaluated `when` expression against current answers; questions without `when` are always visible
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Recompute on set** - `ui.set(id, value)` re-evaluates visibility, computed defaults and choices for every dependent question in one pass
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Computed defaults** - a Jinja `default` is re-rendered whenever a dependency changes, unless the user has explicitly set that field
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Explicit vs default** - state distinguishes a value the user set from an unedited default; frontends read this, they do not infer it
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Validation returns** - `ui.validate()` returns per-field error messages and never raises for user-input problems
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Validator support** - copier's `validator` expression runs per field; a non-empty rendered result is the error message
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Type coercion** - a value that cannot be coerced to the question kind is a validation error, not an exception
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Hidden excluded** - hidden questions are excluded from validation and from the answers handed to copier
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Secrets excluded from dump** - `schema()` and any serialised state carry secret question metadata but never secret values
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Serialisable answers** - answers round-trip to and from a plain dict of JSON-compatible values
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Render** - `ui.render(dst)` calls `copier.run_copy` with `data=answers`, so no question is prompted interactively
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Determinism** - identical template and identical answers produce byte-identical `schema()` output and identical field state
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Edge: unknown type** - a `type` copier does not define surfaces as a load error naming the question id, not a crash
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Edge: circular dependency** - a dependency cycle among `when` / `default` expressions is detected at load and reported with the cycle members
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Edge: forward reference** - a `when` referencing a question declared later evaluates against that question's current default rather than failing
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Edge: empty template** - a `copier.yml` with no questions yields an empty schema and a valid state that renders
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Edge: missing copier.yml** - a path without a copier config raises a named load error before any state is built
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Edge: expression error** - a `when` or `default` that fails to render marks the field in error and leaves the rest of the state usable
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Edge: set unknown id** - `ui.set` on an id not in the schema raises a `KeyError`-style error naming the id
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Edge: set hidden field** - setting a currently hidden field is accepted and retained, so the value returns if the field becomes visible again
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Edge: render with invalid state** - `render` refuses when `validate()` reports errors, and names the offending fields
  - log: 2026-08-22 criterion added (v0.1.0)

### API

- `TemplateUI.from_template(src, vcs_ref=None, answers_file=None) -> TemplateUI`
- `TemplateUI.schema() -> Schema` - ordered questions, kinds, choices, help, dependencies
- `TemplateUI.set(id, value) -> None` - raises on unknown id
- `TemplateUI.state() -> State` - `state.fields[id]` carries `value`, `visible`, `enabled`, `is_default`, `errors`
- `TemplateUI.answers() -> dict` - visible fields only, JSON-compatible
- `TemplateUI.validate() -> dict[str, list[str]]` - empty dict means valid
- `TemplateUI.render(dst, **copier_kwargs) -> None` - refuses on validation errors

## copier-tui

Terminal renderer over `copier_ui`, built with Textual and Rich. Deliberately boring: maps kinds to widgets, holds no semantics of its own. Follows the workspace `text-user-interface` conventions for palette, header bar, 2D navigation, key bindings and the execution screen.

- [ ] **CLI drop-in** - `copier-tui` accepts exactly copier's own CLI syntax: same subcommands (`copy`, `update`, `recopy`), same arguments, same flags, same short forms; replacing `copier` with `copier-tui` in any command line changes the UI and nothing else
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Flag pass-through** - every copier flag is honoured with copier's semantics, not re-implemented: `--data/-d`, `--vcs-ref/-r`, `--answers-file/-a`, `--exclude/-x`, `--skip/-s`, `--overwrite/-w`, `--pretend/-n`, `--defaults`, `--trust`, `--conflict`, `--quiet/-q`
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Pre-supplied answers** - a value given with `--data` is seeded into state and its question is not asked, matching copier's behaviour
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Non-interactive flags stay non-interactive** - `--defaults` and `--quiet` skip the survey entirely and run headless, no TUI launched
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Update and recopy** - `update` and `recopy` open the survey seeded from the destination's `.copier-answers.yml`, then hand back to copier for the merge
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Help parity** - `copier-tui --help` and each subcommand's help list the same options as copier's, with copier's wording
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Edge: unknown flag** - a flag copier does not define is rejected with copier's own error text and exit code
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **No semantics** - `copier_tui` never parses `copier.yml`, evaluates a `when`, or computes a default; all of it comes from `copier_ui` state
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Widget mapping** - string -> text input, bool -> switch, choice -> select, multiselect -> multi-select, secret -> password input, integer/float -> numeric input, path -> path input, structured -> multiline editor
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **TUI conventions** - screens, palette, header bar, 2D navigation, prefix autocomplete, progress and popups follow the `text-user-interface` skill
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Field display** - each field shows its label, its help text, and whether the current value is an untouched default
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Defaults prefilled** - every field opens on its computed default; the user confirms rather than retypes
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Back and forward** - the user moves to the previous and next question freely, in any order, without losing entered answers
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Jump** - an overview lists all visible questions with their current values and jumps straight to a chosen one
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Hidden skipped** - fields whose state is not visible are neither displayed nor reachable by navigation
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Live revisibility** - changing an answer that reveals or hides dependent fields updates the visible set immediately, without restarting the survey
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Inline errors** - validation messages render next to the offending field
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Errors block finish only** - an invalid field blocks instantiation, never navigation away from that field
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Secrets masked** - secret fields are masked on screen and absent from any log line or crash dump
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Review screen** - a final screen lists every answer for confirmation before anything is written to disk
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Nothing written early** - no file is created in the destination until the user confirms on the review screen
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Execution screen** - instantiation runs on its own screen with progress and a final success or failure verdict
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Exit code** - the process exits 0 on a completed render, non-zero on a failed render or a user cancel
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Cancel anywhere** - quitting before confirmation leaves the destination untouched and says so
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Any template** - an unmodified third-party copier template runs through the TUI with no template-side changes
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Edge: no questions** - a template with no questions goes straight to the review screen
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Edge: destination not empty** - a non-empty destination warns before confirmation and lets the user abort
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Edge: template fetch fails** - a bad path, URL or ref reports the failure and exits before the survey opens
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Edge: copier run fails** - a failure during render shows copier's error on the execution screen and leaves partial output in place rather than deleting it
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Edge: load error mid-schema** - a question `copier_ui` could not load is displayed as a disabled field carrying its error, and blocks instantiation
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Edge: terminal too small** - below the minimum usable size the app shows a resize prompt instead of a broken layout
  - log: 2026-08-22 criterion added (v0.1.0)
- [ ] **Edge: not a tty** - launched without a terminal, the app exits with a clear message rather than a traceback
  - log: 2026-08-22 criterion added (v0.1.0)
