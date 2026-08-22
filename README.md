# copier-tui

[![build](https://github.com/stellarshenson/copier-tui/actions/workflows/build.yml/badge.svg)](https://github.com/stellarshenson/copier-tui/actions/workflows/build.yml)
[![PyPI copier-tui](https://img.shields.io/pypi/v/copier-tui.svg?label=copier-tui)](https://pypi.org/project/copier-tui/)
[![PyPI copier-ui](https://img.shields.io/pypi/v/copier-ui.svg?label=copier-ui)](https://pypi.org/project/copier-ui/)
[![Python](https://img.shields.io/pypi/pyversions/copier-tui.svg)](https://pypi.org/project/copier-tui/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Brought To You By KOLOMOLO](https://img.shields.io/badge/Brought%20To%20You%20By-KOLOMOLO-00ffff?style=flat)](https://kolomolo.com)

Two packages that put a proper user interface in front of [copier](https://copier.readthedocs.io). `copier-ui` reads a template's question model and turns it into a deterministic, UI-neutral schema with state and validation. `copier-tui` is a terminal renderer built on that schema, letting the user move back and forth through the survey and only instantiate the template once they are ready.

## Why

Copier's questionnaire is driven by `copier.yml` and its own interaction layer. Copier extensions are Jinja extensions, not pluggable questionnaire renderers, so there is no supported way to replace the prompt frontend. The workable route is to treat copier as the template engine and supply answers through its Python API - answers passed as data are never prompted for interactively.

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

Every existing copier template gets the alternative UI without any change to the template.

## Screens

The whole survey is one screen. Every question is one row - a label gutter, the control, and a
single glyph marking a problem, an unavailable field or an untouched default. Help and validation
messages share the reserved line above the footer, so they cost no rows. The capture below is
[copier-data-science](https://github.com/stellarshenson/copier-data-science): 24 questions,
conditional fields included, in 24 rows.

![the survey screen](docs/assets/survey.svg)

Nothing is written until the review is confirmed. Review is stacked over the survey rather than
replacing it, so `esc` goes back to the form exactly as it was left - same scroll offset, same
focused field - and every dependent answer recalculates as soon as it is changed again.

![the review screen](docs/assets/review.svg)

Confirming hands the answers to copier and reports its verdict. A `--pretend` run says plainly
that nothing was written.

![the execution screen](docs/assets/execution.svg)

## Keys

| Key | What it does |
|-----|--------------|
| `up` / `down` | move between fields; inside an editor or an option list they move its cursor and hand focus on at the first and last line |
| `space` | open a choice list, toggle a switch, tick a multiselect option |
| `enter` | confirm the screen; inside an open menu it picks, inside a multiline editor it breaks the line |
| `esc` | go back, or cancel - on the survey it arms first and quits on a second press |
| `ctrl+p` | command palette |

## Usage

`copier-tui` is a drop-in for the `copier` command. Same subcommands, same arguments, same flags, same short forms - swap the binary and the only thing that changes is the interface.

```bash
copier-tui copy gh:stellarshenson/copier-data-science ./my-project
copier-tui update
```

Flags keep copier's semantics rather than being re-implemented: values passed with `--data` are
seeded and not asked for, and `--defaults` or `-f/--force` skip the survey entirely and run
headless. `--quiet` is not a non-interactive flag in copier - it only suppresses status output -
so it keeps the TUI, and `--ask` turns asking back on even under `--defaults`. A template
declaring Jinja extensions or tasks is refused before any screen opens unless `--trust` was given,
with copier's own message and copier's own exit code.

## Architecture

`copier-ui` owns semantics, each `copier-*ui` owns presentation. That split is the whole point - without it, every frontend re-implements `when` evaluation, computed defaults, choice resolution and validation.

Three layers inside `copier-ui`:

- **Copier adapter** - copier-specific parsing of `copier.yml` and template metadata
- **UI model** - normalised questions, pages, groups, fields; no copier internals leak past this line
- **State engine** - answers, dependency evaluation, visibility, validation

The hard rule: **`copier-ui` must never require a terminal, browser, or event loop**. That keeps it usable from tests, CI, HTTP services, IDE plugins and agents.

`copier-tui` is deliberately boring. It maps the normalised model to widgets and nothing more:

| Question kind | Widget |
|---------------|--------|
| `string` | text input |
| `path` | text input |
| `integer` | numeric input |
| `float` | numeric input |
| `bool` | switch |
| `choice` | select |
| `multiselect` | selection list |
| `structured` | multiline editor |
| `secret` | password input, whatever the kind |
| any kind with `multiline: true` | multiline editor |

A secret question always gets the masked input, even when it declares choices: no control may
put the value on screen in the clear.

Sketch of the `copier-ui` surface:

```python
from copier_ui import TemplateUI

ui = TemplateUI.from_template("./template")
schema = ui.schema()

ui.set("database", "postgres")
state = ui.state()
state.fields["postgres_host"].visible   # True

ui.validate()
ui.render("./output")
```

## Project Organization

```
├── Makefile                    <- install, test, test-functional, build, publish
├── README.md
├── pyproject.toml              <- uv workspace root (not published)
├── scripts/bump_version.py     <- lockstep patch bump for both packages
├── docs                        <- acceptance criteria, design notes, assets
├── packages
│   ├── copier-ui               <- published: UI-neutral survey abstraction
│   │   ├── pyproject.toml
│   │   └── src/copier_ui
│   └── copier-tui              <- published: Textual terminal renderer
│       ├── pyproject.toml
│       └── src/copier_tui
└── tests
    ├── unit                    <- run against the workspace
    └── functional              <- run against the built wheels in a throwaway venv
```

## Development

```bash
make install          # uv workspace, both packages editable, bumps the patch version
make test             # unit tests
make test-functional  # builds both wheels, installs them into a clean venv, runs against them
make lint             # ruff
make build            # wheels and sdists for both packages
make publish          # twine upload, copier-ui first because copier-tui pins it exactly
```

Both packages share one version and are released together. `make install` bumps the patch
number every time, including for a major change - that is deliberate, not an oversight.

## Licence

MIT. See [LICENSE](LICENSE).
