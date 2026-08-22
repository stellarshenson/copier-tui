<!-- @import /home/lab/workspace/.claude/CLAUDE.md -->

# Project-Specific Configuration

This file imports workspace-level configuration from `/home/lab/workspace/.claude/CLAUDE.md`.
All workspace rules apply. Project-specific rules below strengthen or extend them.

The workspace `/home/lab/workspace/.claude/` directory contains additional instruction files
(MERMAID.md, NOTEBOOK.md, DATASCIENCE.md, GIT.md, and others) referenced by CLAUDE.md.
Consult workspace CLAUDE.md and the .claude directory to discover all applicable standards.

## Mandatory Bans (Reinforced)

The following workspace rules are STRICTLY ENFORCED for this project:

- **No automatic git tags** - only create tags when user explicitly requests
- **No automatic version changes** - only modify version in package.json/pyproject.toml/etc. when user explicitly requests
- **No automatic publishing** - never run `make publish`, `npm publish`, `twine upload`, or similar without explicit user request
- **No manual package installs if Makefile exists** - use `make install` or equivalent Makefile targets, not direct `pip install`/`uv install`/`npm install`
- **No automatic git commits or pushes** - only when user explicitly requests

## Project Context

Two Python packages in one repository, published together to PyPI as `copier-ui` and `copier-tui`, laid out as a uv workspace under `packages/`:

- `copier_ui` - UI-neutral abstraction over a [copier](https://copier.readthedocs.io) template survey. Three layers: copier adapter (parses `copier.yml`), UI model (normalised questions, pages, groups, fields), state engine (answers, dependency evaluation, visibility, validation). Owns semantics, renders nothing
- `copier_tui` - terminal renderer built on `copier_ui`, using Textual and Rich. Maps question kinds to widgets and nothing more. Lets the user move back and forth through the survey and only instantiates the template on confirmation

Copier itself stays the template engine. Answers are supplied through `copier.run_copy(..., data=answers)`, so nothing is prompted interactively and every existing template works unchanged. `copier_webui` and `copier_api` are named in the design as future siblings; they are out of scope here.

Stack: Python 3.11+ (3.13 locally), uv workspace, ruff, pytest, Makefile-driven, GitHub Actions. Acceptance criteria live in `docs/acc-crit-copier-tui.md`. `copier-data-science` (`/home/lab/workspace/private/copier-data-science`, also on GitHub) is the reference template the functional tests run against - 37 questions, conditional `when`, computed `when: false` fields, Jinja defaults referencing other answers, choices, `type: json`.

Versioning: both packages share one version, bumped in lockstep by `scripts/bump_version.py`. `make install` bumps the patch every time, including for a major change - deliberate. `make publish` uploads both with twine, `copier-ui` first because `copier-tui` pins it exactly.

## Journal Rules (Project-Specific)

- **APPEND ONLY**: New journal entries MUST be appended at the end of the file, never inserted between existing entries
- Entries maintain strict chronological order by position - the last entry in the file is always the most recent work
- Never reorder, move, or insert entries out of sequence
- The Stellars **journal plugin** is the canonical tool for this file: create via `/journal:create`, append via `/journal:update`, archive via `/journal:archive`. The `journal:journal` skill auto-triggers on any mention of "journal" and runs `journal-tools check` after every write
- Direct edits to `JOURNAL.md` are a last resort - prefer the plugin so modus secundis format, continuous numbering and append-only order are enforced automatically

## Strengthened Rules

- **TUI work follows the `text-user-interface` skill** - every screen, palette choice, key binding, header bar, 2D navigation pattern, progress bar and popup in `copier_tui` comes from that skill's conventions. Read it before writing or modifying TUI code; do not invent local conventions
- **Layering is non-negotiable** - `copier_ui` must never import Textual, Rich, prompt_toolkit, curses, or anything else that assumes a display, and must never require an event loop. Everything it exposes is synchronous. A test enforces this over the import graph
- **`copier_tui` holds no semantics** - it never parses `copier.yml`, evaluates a `when`, or computes a default. Anything it displays comes from `copier_ui` state. Logic that both a TUI and a future web UI would need belongs in `copier_ui`
- **CLI is a drop-in for copier** - `copier-tui` accepts copier's exact CLI syntax: same subcommands, arguments, flags and short forms. Swapping `copier` for `copier-tui` changes the interface and nothing else. Flags keep copier's semantics rather than being re-implemented
- **Acceptance criteria are the gate** - `docs/acc-crit-copier-tui.md` is the canonical statement of done. Update it via the `acceptance-criteria` skill and validate with its `acc-crit.py check` after every edit
- **Modular and simple** - the Star Colonel's standing instruction for this project: small modules with one job each, no speculative abstraction, no framework where a function does. If a file is doing two things, split it; if a layer exists only for a future caller, delete it
- **Surgical changes** - the workspace rule applies with force here: this is a small codebase where an unrequested abstraction is immediately visible. No speculative layers for `copier_webui` or `copier_api` until those are actually being built
