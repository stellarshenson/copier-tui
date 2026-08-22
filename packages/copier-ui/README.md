# copier-ui

UI-neutral abstraction over a [copier](https://copier.readthedocs.io) template survey.

`copier-ui` reads a template's questions and turns them into a normalised schema with a
dependency graph, visibility state and validation. It owns semantics and renders nothing, so
the same core drives a terminal UI, a web UI, an HTTP API or a test.

It never imports a display library and never requires an event loop.

```python
from copier_ui import TemplateUI

# unsafe=True is copier's own trust gate: this template declares Jinja extensions and tasks,
# and copier_ui refuses to load such a template before importing anything unless you say so
ui = TemplateUI.from_template("gh:stellarshenson/copier-data-science", unsafe=True)
ui.set("dataset_storage", "s3")
ui.state().fields["s3_bucket"].visible   # True
ui.render("./my-project")
```

Part of the [copier-tui](https://github.com/stellarshenson/copier-tui) project.
