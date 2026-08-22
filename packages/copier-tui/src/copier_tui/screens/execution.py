"""The execution screen: the copier run, its progress and its verdict."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, ProgressBar, Static

from copier_tui.theme import MINT, ORANGE, ROSE, SURFACE_BG, TEXT_MUTED, TEXT_SUBTLE
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
        height: 1;
        color: {TEXT_MUTED};
    }}
    #exec-verdict {{
        height: 1;
        color: {TEXT_SUBTLE};
    }}
    #exec-progress {{
        width: 100%;
    }}
    #exec-progress Bar {{
        width: 1fr;
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

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("enter", "close", "Close", priority=True),
        Binding("escape", "close", "Close", priority=True, show=False),
    ]

    def __init__(self, ui: TemplateUI, dst: Path, copier_kwargs: dict[str, Any]) -> None:
        """Hold the template UI, the destination and copier's own flags."""
        super().__init__(id="execution-screen")
        self.ui = ui
        self.dst = dst
        self.copier_kwargs = copier_kwargs
        self.pretend = bool(copier_kwargs.get("pretend"))
        self._done = False
        self._closed = False
        self._ok = False

    def compose(self) -> ComposeResult:
        """Header, the status line and the progress bar, the verdict line, footer.

        The destination is named once, by the status line that narrates the run: the header
        says which run it is, and repeating the path three times said nothing extra.
        """
        verb = "checking" if self.pretend else "rendering"
        yield HeaderBar("dry run" if self.pretend else "render")
        yield Vertical(
            Static(Text(f"{verb} the template"), id="exec-status"),
            ProgressBar(total=None, show_percentage=False, show_eta=False, id="exec-progress"),
            Static(id="exec-verdict"),
            id="exec-body",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Start the render worker and the indeterminate progress bar."""
        self.run_worker(self._run_copier, thread=True, name="render")

    def on_key(self, event: events.Key) -> None:
        """Any key closes the finished run, not just the bound ones."""
        if self._done:
            event.stop()
            self.action_close()

    def action_close(self) -> None:
        """End the run once the verdict is in; idempotent, any key reaches it too."""
        if not self._done or self._closed:
            return
        self._closed = True
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
        """Put the verdict on the status line: mint on success, rose with copier's message.

        A dry run says so - it reports what copier would write, and writes nothing. There is
        no popup: the verdict belongs on the line that has been narrating the run, and the
        destination is named once, by the status line, never also by the header.
        """
        self._done = True
        self._ok = error is None
        self.query_one("#exec-progress", ProgressBar).update(total=1, progress=1)
        status = self.query_one("#exec-status", Static)
        if error is None:
            done = (
                "nothing written - this was a dry run"
                if self.pretend
                else f"written to {self.dst}"
            )
            status.update(Text(done, style=MINT))
        else:
            status.update(Text(f"failed - {_message(error)}", style=ROSE))
        self.query_one("#exec-verdict", Static).update(Text("press any key to close"))
        self.set_focus(None)


def _message(error: BaseException) -> str:
    """copier's own message where there is one, the exception class otherwise."""
    return str(error) or type(error).__name__
