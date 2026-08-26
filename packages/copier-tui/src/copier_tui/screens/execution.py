"""The execution screen: the copier run, its progress and its verdict."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
import subprocess
import termios
from typing import Any, ClassVar

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, ProgressBar, RichLog, Static

from copier_tui.theme import MINT, ORANGE, ROSE, SURFACE_BG, TEXT_MUTED, TEXT_SUBTLE
from copier_tui.widgets import HeaderBar
from copier_ui import TemplateUI

WATCH_INTERVAL = 0.2
"""How often the destination is re-walked while the render runs, in seconds."""

WATCH_LIMIT = 2000
"""Entries the walk stops at, so a template writing a huge tree cannot stall the screen."""


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
    #exec-files {{
        width: 100%;
        height: 1fr;
        margin: 1 0 0 0;
        background: {SURFACE_BG};
        color: {TEXT_MUTED};
        scrollbar-size-vertical: 1;
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
        self._seen: set[str] = set()

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
            RichLog(id="exec-files", markup=False, wrap=False, auto_scroll=True),
            id="exec-body",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Start the render worker, and watch the destination fill up while it runs."""
        self.run_worker(self._run_copier, thread=True, name="render")
        self._watch = self.set_interval(WATCH_INTERVAL, self._show_new_files)

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
            with _children_without_stdin(), _terminal_mode_kept():
                self.ui.render(self.dst, **self.copier_kwargs)
        except Exception as exc:  # noqa: BLE001 - any failure becomes the screen's verdict
            error = exc
        self.app.call_from_thread(self._finish, error)

    def _show_new_files(self) -> None:
        """List whatever has appeared under the destination since the last look.

        copier writes the tree itself and reports nothing back, so the destination is the
        only account of what is happening; a bar that only pulses says the run is alive but
        not that it is doing anything. The walk is capped because a template is free to write
        a node_modules, and a screen that stalls listing one is worse than a short list.
        """
        log = self.query_one("#exec-files", RichLog)
        for path in sorted(self._written()):
            if path in self._seen:
                continue
            self._seen.add(path)
            log.write(path)

    def _written(self) -> list[str]:
        """The destination's contents as paths relative to it, directories included."""
        if not self.dst.is_dir():
            return []
        found: list[str] = []
        for path in self.dst.rglob("*"):
            if ".git" in path.parts:
                continue
            found.append(str(path.relative_to(self.dst)) + ("/" if path.is_dir() else ""))
            if len(found) >= WATCH_LIMIT:
                break
        return found

    def _finish(self, error: BaseException | None) -> None:
        """Put the verdict on the status line: mint on success, rose with copier's message.

        A dry run says so - it reports what copier would write, and writes nothing. There is
        no popup: the verdict belongs on the line that has been narrating the run, and the
        destination is named once, by the status line, never also by the header.
        """
        self._done = True
        self._ok = error is None
        self._watch.stop()
        self._show_new_files()
        if not self._seen:
            self.query_one("#exec-files", RichLog).write(
                "nothing written" if self.pretend else "no files"
            )
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


@contextmanager
def _children_without_stdin() -> Iterator[None]:
    """Give everything the render starts a stdin of /dev/null, leaving this process's alone.

    A template's tasks are ordinary subprocesses and copier hands them this process's own
    descriptors. Under `--trust` that means a task inherits the terminal Textual is holding
    in raw mode: anything it reads is a keystroke meant for the form, and a task that asks a
    question of its own leaves the terminal in whatever mode it chose.

    Pointing THIS process's descriptor 0 at /dev/null for the length of the render was the
    first cure and it was worse than the disease. Textual's input thread polls descriptor 0
    on a timeout and reads whatever it finds; with /dev/null underneath, every poll reports
    ready and every read returns end-of-file, so the thread spins as fast as the machine
    allows. A live run whose template was cloned over the network spun that loop 476,000
    times and came out deaf - the app ticked, painted nothing and answered no key, and
    "press any key to close" stood there forever. A driver's input descriptor is not ours to
    swap while it is being read.

    So the descriptor stays where it is and the children get their own. `Popen` is patched
    rather than copier's call site because copier passes no stdin at all, and because a
    caller that did ask for one keeps it. Descriptors 1 and 2 are left alone either way -
    Textual paints the screen through 1, and task chatter over the form is cosmetic where a
    stolen keyboard is terminal.
    """
    original = subprocess.Popen.__init__

    @wraps(original)
    def without_stdin(self: Any, *args: Any, **kwargs: Any) -> None:
        # stdin is Popen's fourth positional parameter; a caller passing it that way has
        # said what it wants, and setdefault would hand __init__ two of them
        if len(args) < 4 and "stdin" not in kwargs:
            kwargs["stdin"] = subprocess.DEVNULL
        original(self, *args, **kwargs)

    subprocess.Popen.__init__ = without_stdin
    try:
        yield
    finally:
        subprocess.Popen.__init__ = original


@contextmanager
def _terminal_mode_kept(fd: int = 0) -> Iterator[None]:
    """Put the terminal's mode back the way the driver set it, whatever the render did to it.

    Descriptors 1 and 2 are the render's to write on, and both still reach the terminal, so a
    task can reach the line discipline even with no stdin of its own - `stty sane </dev/tty`
    is one line of a post-generation hook, and every interactive program that exits badly
    leaves the same wreckage. Textual puts the terminal in raw mode once at startup and never
    asserts it again; cooked, the discipline holds each keystroke until a newline and echoes
    it, so the form goes deaf mid-run and "press any key to close" answers nothing.

    Restoring is unconditional rather than conditional on having spotted a change: one ioctl
    either way, and a comparison that had to be right is a comparison that can be wrong. The
    descriptor is the one Textual's driver reads - `fd` is a parameter so a test can hand this
    a pty of its own rather than the one the suite is running on.
    """
    try:
        mode = termios.tcgetattr(fd)
    except (termios.error, ValueError, OSError):
        # not a terminal at all: a test, a pipe, a CI runner. There is no mode to keep
        yield
        return
    try:
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, mode)


def _message(error: BaseException) -> str:
    """copier's own message where there is one, the exception class otherwise."""
    return str(error) or type(error).__name__
