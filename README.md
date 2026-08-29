# copier-tui

[![build](https://github.com/stellarshenson/copier-tui/actions/workflows/build.yml/badge.svg)](https://github.com/stellarshenson/copier-tui/actions/workflows/build.yml)
[![PyPI copier-tui](https://img.shields.io/pypi/v/copier-tui.svg?label=copier-tui&labelColor=1f4f66)](https://pypi.org/project/copier-tui/)
[![PyPI copier-ui](https://img.shields.io/pypi/v/copier-ui.svg?label=copier-ui&labelColor=2b4457)](https://pypi.org/project/copier-ui/)
[![Total PyPI downloads](https://static.pepy.tech/badge/copier-tui)](https://pepy.tech/project/copier-tui)
[![Python](https://img.shields.io/pypi/pyversions/copier-tui.svg)](https://pypi.org/project/copier-tui/)
[![Brought To You By KOLOMOLO](https://img.shields.io/badge/Brought%20To%20You%20By-KOLOMOLO-00ffff?style=flat)](https://kolomolo.com)

A drop-in wrapper for [copier](https://copier.readthedocs.io) with a terminal UI. Same command line, same templates, one screen instead of one question at a time. `copier-ui` is the UI-neutral half - it turns a template's questions into a schema with state and validation, and renders nothing.

![the survey screen](docs/assets/survey.svg)

## Features

- **One screen** - every question and every option on screen at once, nothing opens over the form
- **Back and forth** - change any answer at any point; dependent fields recalculate in place
- **Nothing written until confirmed** - the review screen is the last step before copier runs
- **Drop-in for `copier`** - same subcommands, arguments, flags and short forms
- **Every template works unchanged** - copier stays the engine, answers go in through its Python API
- **Conditional fields nest** - a `when` field appears under the answer that governs it
- **The run is accounted for** - the survey names where the template will land, and the render lists the files as they are written, and a banner at the end counts what was added, changed, deleted and left with a conflict to resolve
- **Reusable core** - `copier-ui` needs no terminal or event loop, so a web or HTTP frontend reuses it

## Installation

Python 3.11 or newer. `copier-tui` pulls in `copier-ui` and copier itself.

```bash
uv tool install copier-tui      # isolated, on PATH - recommended
pipx install copier-tui         # same idea without uv
pip install copier-tui          # into the current environment
pip install copier-ui           # the semantics layer alone, for your own frontend
```

## Usage

```bash
copier-tui copy gh:stellarshenson/copier-data-science ./my-project
copier-tui update
```

Flags keep copier's semantics rather than being re-implemented:

- `--data` values are seeded and not asked for
- `--defaults` and `-f` / `--force` skip the survey and run headless
- `--quiet` only suppresses status output in copier, so it keeps the TUI
- `--ask` turns asking back on under `--defaults`
- a template with Jinja extensions or tasks is refused before any screen opens unless `--trust` is given, with copier's own message and exit code

The review screen lists every answer, and is the last step before anything is written:

![the review screen](docs/assets/review.svg)

The render names each file as copier writes it, and closes on a banner counting what it did:

![the execution screen](docs/assets/execution.svg)

## Keys

| Key | What it does |
|-----|--------------|
| `up` / `down` | move between fields, stopping at the first and the last; inside a multiline editor they move its cursor and hand focus on at its first and last line |
| `left` / `right` | move along a question's options, taking the one they land on |
| `space` | cycle a choice forward, or tick the option under the cursor in a multiselect; a switch is left to the arrows |
| `enter` | confirm the screen; inside a multiline editor it breaks the line |
| `esc` | go back, or cancel - on the survey it arms first and quits on a second press |
| `ctrl+x` | quit from any screen; on a render still running it ends the run's tasks and leaves |
| `ctrl+q` | the same as `ctrl+x` |
| `ctrl+c` | left to the terminal, so it still copies |

The survey is driven from the keyboard alone and asks the terminal for no mouse reporting, so
selecting and copying text works the way it does anywhere else in the terminal.

## Architecture

Copier extensions are Jinja extensions, not pluggable questionnaire renderers, so there is no supported way to replace its prompt frontend. Answers passed to copier's Python API as data are never prompted for, which is the route this takes.

```
copier.yml
    │
    ▼
copier-ui  ─ normalised schema, dependency graph, validation, visibility, answer state
    │
    ├──▶ copier-tui     terminal renderer
    ├──▶ copier-webui   browser renderer (future)
    └──▶ copier-api     HTTP / headless interface (future)
    │
    ▼
copier.run_copy(src_path, dst_path, data=answers)
```

`copier-ui` owns semantics in three layers - copier adapter, UI model, state engine - and **must never require a terminal, browser, or event loop**. `copier-tui` owns presentation and maps kinds to widgets, nothing more:

| Question kind | Widget |
|---------------|--------|
| `string`, `path` | wrapping text field |
| `integer`, `float` | numeric input |
| `bool` | the two answers on the row |
| `choice` | every option on the row |
| `multiselect` | every option on the row, ticked or not |
| `structured`, any kind with `multiline: true` | multiline editor |
| `secret` | password input, whatever the kind - a secret is never put on screen in the clear |

```python
from copier_ui import TemplateUI

ui = TemplateUI.from_template("./template")
ui.set("database", "postgres")
ui.state().fields["postgres_host"].visible   # True
ui.validate()
ui.render("./output")
```

## Grouping

`copier.yml` has no notion of a section, so `copier-ui` never invents one - every template gets one untitled group. A template opts into headings with `_ui_groups`, an underscore-prefixed key copier carries through and ignores:

```yaml
_ui_groups:
  - title: Identity
    fields: [project_name, author_name]
  - title: Tooling and quality
    fields: [linter, testing_framework, github_actions]
```

Groups partition questions in declaration order and never reorder them. A malformed `_ui_groups`, or one naming a field that does not exist, loads as though it were absent rather than refusing the template.

## Development

```bash
make install          # uv workspace, both packages editable, bumps the patch version
make test             # unit tests
make test-functional  # builds both wheels, installs them into a clean venv, runs against them
make lint             # ruff
make build            # wheels and sdists for both packages
make publish          # twine upload, copier-ui first because copier-tui pins it exactly
```

Both packages share one version and are released together. `make install` bumps the patch number every time, including for a major change - that is deliberate.

## License

MIT. See [LICENSE](LICENSE).
