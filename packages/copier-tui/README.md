# copier-tui

A terminal UI for [copier](https://copier.readthedocs.io). Same CLI, better survey.

`copier-tui` takes copier's exact command line and replaces the prompt sequence with a
[Textual](https://textual.textualize.io) interface you can move back and forth through, review,
and only then instantiate. Templates need no changes.

```bash
pip install copier-tui
copier-tui copy gh:stellarshenson/copier-data-science ./my-project
```

Built on [copier-ui](https://pypi.org/project/copier-ui/), which owns the survey semantics.

Full documentation at [github.com/stellarshenson/copier-tui](https://github.com/stellarshenson/copier-tui).
