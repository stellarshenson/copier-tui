# copier-tui

Two packages that put a proper user interface in front of [copier](https://copier.readthedocs.io). `copier-ui` reads a template's question model and turns it into a deterministic, UI-neutral schema with state and validation. `copier-tui` is a terminal renderer built on that schema, letting the user move back and forth through the survey and only instantiate the template once they are ready.

> **Note**: Generated with copier-data-science template v1.2+
> For template documentation, visit [copier-data-science](https://github.com/stellarshenson/copier-data-science)

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

## Usage

`copier-tui` is a drop-in for the `copier` command. Same subcommands, same arguments, same flags, same short forms - swap the binary and the only thing that changes is the interface.

```bash
copier-tui copy gh:stellarshenson/copier-data-science ./my-project
copier-tui update
```

Flags keep copier's semantics rather than being re-implemented: values passed with `--data` are seeded and not asked for, and `--defaults` or `--quiet` skip the survey entirely and run headless.

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
| `bool` | checkbox / switch |
| `choice` | select |
| `multiselect` | multi-select |
| `secret` | password input |
| `integer` | numeric input |
| `path` | path input |

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

## Quick Start

```bash
make install
```

## Makefile Targets

- `make install` - Create environment and install package
- `make test` - Run tests
- `make lint` / `make format` - Check / fix code style
- `make upgrade` - Upgrade dependencies to latest versions
- `make build` - Build distributable wheel
- `make clean` - Remove compiled files, caches, logs and tmp
- `make .env` / `make .env.enc` - Decrypt / encrypt environment secrets
- `make help` - Show all available targets

## Best Practices

- **Layering**: nothing in `copier_ui/` may import Textual, Rich, or anything else that assumes a display; violations of that rule are the one thing worth failing a build over
- **Terminal UI**: `copier_tui/` is built with Textual and Rich and follows the workspace `text-user-interface` conventions - palette, header bar, 2D navigation, key bindings, execution screen
- **Documentation**: `docs/` holds the project's own documentation - acceptance criteria, design notes, defects
- **Logs**: runtime and job logs in `logs/` (gitignored), with a short `logs/README.md`
- **Temporary files**: `tmp/` for throwaway work (gitignored); never keep anything here

## Project Organization

```
├── Makefile           <- Makefile with convenience commands
├── README.md          <- The top-level README for developers
├── docs               <- Project documentation: acceptance criteria, design notes, defects
├── logs               <- Runtime and background-job logs (gitignored)
├── tmp                <- Throwaway scratch (gitignored)
├── pyproject.toml     <- Project configuration and dependencies
├── tests              <- Test files
└── src
    ├── copier_ui      <- UI-neutral abstraction over a copier survey
    │   └── __init__.py
    └── copier_tui     <- Terminal renderer built on copier_ui
        ├── __init__.py
        └── config.py      <- Configuration variables
```
