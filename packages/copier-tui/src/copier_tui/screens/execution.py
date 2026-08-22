"""The execution screen: the copier run, its progress and its verdict."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, ProgressBar, Static

from copier_tui.theme import MINT, ORANGE, ROSE, SURFACE_BG, TEXT_MUTED
from copier_tui.widgets import HeaderBar
from copier_ui import TemplateUI


class ExecutionScreen(Screen[bool]):
    """Runs copier in a worker thread and reports success or failure."""

    DEFAULT_CSS = f"""
    #exec-body {{
        width: 100%;
        height: 1fr;
        padding: 1;
    }}
    #exec-status {{
        color: {TEXT_MUTED};
        padding: 0 0 1 0;
    }}
    #exec-progress Bar {{
        width: 100%;
    }}
    #exec-progress Bar > .bar--bar {{
        color: {ORANGE};
        background: {SURFACE_BG};
    }}
    #exec-progress Bar > .bar--indeterminate {{
        color: {ORANGE};
        background: {SURFACE_BG};
    }}
    #exec-progress Bar > .bar--complete {{
        color: {MINT};
        background: {SURFACE_BG};
    }}
    """

    def __init__(self, ui: TemplateUI, dst: Path, copier_kwargs: dict[str, Any]) -> None:
        """Hold the template UI, the destination and copier's own flags."""
        super().__init__(id="execution-screen")
        self.ui = ui
        self.dst = dst
        self.copier_kwargs = copier_kwargs
        self._banner = Static(id="banner-box")
        self._done = False
        self._ok = False

    def compose(self) -> ComposeResult:
        """Header, the status line and the progress bar, the verdict banner, footer."""
        yield HeaderBar(f"render · {self.dst}")
        yield Vertical(
            Static(Text("rendering the template"), id="exec-status"),
            ProgressBar(total=None, show_percentage=False, show_eta=False, id="exec-progress"),
            id="exec-body",
        )
        yield self._banner
        yield Footer()

    def on_mount(self) -> None:
        """Start the render worker and the indeterminate progress bar."""
        self.run_worker(self._run_copier, thread=True, name="render")

    def on_key(self, event: events.Key) -> None:
        """Any key dismisses the verdict banner and ends the run."""
        if self._done:
            event.stop()
            self.dismiss(self._ok)

    def _run_copier(self) -> None:
        """Call TemplateUI.render off the UI thread; report back with call_from_thread.

        Not named `_render`: Widget._render is Textual's own, and shadowing it runs this
        on the UI thread during layout.
        """
        error: BaseException | None = None
        try:
            self.ui.render(self.dst, **self.copier_kwargs)
        except Exception as exc:  # noqa: BLE001 - any failure becomes the screen's verdict
            error = exc
        self.app.call_from_thread(self._finish, error)

    def _finish(self, error: BaseException | None) -> None:
        """Show the verdict banner: mint on success, rose with copier's message on failure."""
        self._done = True
        self._ok = error is None
        progress = self.query_one("#exec-progress", ProgressBar)
        progress.update(total=1, progress=1)
        status = self.query_one("#exec-status", Static)
        if error is None:
            status.update(Text(f"written to {self.dst}"))
            self._banner.update(Text(f"render complete\n{self.dst}\n\npress any key"))
            self._banner.styles.border = ("heavy", MINT)
        else:
            status.update(Text(_message(error)))
            self._banner.update(Text(f"render failed\n{_message(error)}\n\npress any key"))
            self._banner.styles.border = ("heavy", ROSE)
        self._banner.display = True
        self.set_focus(None)


def _message(error: BaseException) -> str:
    """copier's own message where there is one, the exception class otherwise."""
    return str(error) or type(error).__name__
