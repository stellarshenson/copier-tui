"""The execution screen: the copier run, its progress and its verdict."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import wraps
import os
from pathlib import Path
import signal
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

from copier_tui.paths import fit_path
from copier_tui.theme import MINT, ORANGE, ROSE, SURFACE_BG, TEXT_MUTED, TEXT_SUBTLE
from copier_tui.widgets import HEADER_PATH_FLOOR, HeaderBar
from copier_ui import TemplateUI

WATCH_INTERVAL = 0.2
"""How often the destination is re-walked while the render runs, in seconds."""

WATCH_LIMIT = 2000
"""Entries the walk stops at, so a template writing a huge tree cannot stall the screen."""

_SCROLL_KEYS = {
    "up": "scroll_up",
    "down": "scroll_down",
    "pageup": "page_up",
    "pagedown": "page_down",
    "home": "scroll_home",
    "end": "scroll_end",
}
"""Keys that read the file list rather than dismissing the screen it is on, and the log action
each one runs.

The action is called, not the key forwarded. Forwarding was the first attempt and it reached
nothing: Textual resolves a widget's ordinary bindings in `App._on_key`, after the event has
bubbled unhandled all the way up, and this screen stops the event before that - so six keys
went from closing the screen to doing nothing at all, which is worse. Nothing on this screen
holds the focus either, so even letting the event bubble would not have found the log."""


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
        text-wrap: nowrap;
        text-overflow: ellipsis;
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
        # enter and escape are deliberately NOT bound. `on_key` below closes a finished run
        # on any key, and it is not an action dispatch - which is the whole difference. Bound,
        # these two reached `action_close` from inside the dispatch that `dismiss` waits on,
        # and hung the app: the two keys this screen's own footer named, and the two a person
        # presses at "press any key to close", were the only two that did not work. Every
        # other key went through `on_key` and left correctly, which is why no test caught it.
        #
        # `Quit`, which is true both while the render runs - where it ends it - and once it
        # has finished, where the footer entry is dimmed but still reads. `Abandon` was tried
        # and offered to abandon a project that had just been written to disk.
        # Full reason for the priority and the `app.` prefix in `SurveyApp.BINDINGS`.
        Binding("ctrl+x", "app.quit_now", "Quit", priority=True),
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
        # copier removes a destination it created when the run fails, and leaves one it did
        # not. Which of the two happened decides whether anything survives an abandon, and it
        # can only be known before the render starts
        self._destination_existed = dst.exists()
        self._seen: set[str] = set()
        self._children: list[subprocess.Popen[Any]] = []
        # written on the UI thread by `abandon`, read on the render thread by `_note_child`
        # and `_terminal_mode_kept`. A plain bool on purpose: nothing here may block
        self._abandoned = False

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
            # wrapped, and at the box's own width: the failure reason lives here, and a
            # copier sentence - a Jinja error carrying a template path - is longer than any
            # supported width. Unwrapped it was cut at the right edge, and the arrow the
            # scrollbar invited was "any other key" and closed the screen. `min_width` is 78
            # by default, which at 60 columns folds the text past the box and cuts it again
            RichLog(id="exec-files", markup=False, wrap=True, min_width=0, auto_scroll=True),
            id="exec-body",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Start the render worker, and watch the destination fill up while it runs."""
        self.run_worker(self._run_copier, thread=True, name="render")
        self._watch = self.set_interval(WATCH_INTERVAL, self._show_new_files)

    @property
    def leaves_files_behind(self) -> bool:
        """Whether abandoning this render leaves anything on disk to go and look at.

        copier clears up a destination it created and leaves one it did not, so a run into a
        new directory is genuinely undone and a run into an existing project is not. Saying
        "partly written" for both was the first version of this message; saying it for a
        directory that no longer exists sends the reader looking for something that is not
        there, which is worse than the vagueness it replaced.
        """
        # `--no-cleanup` is copier's own flag and means "keep what you wrote when it fails",
        # which is exactly when this is asked. Ignoring it denied leftovers to the one user who
        # had explicitly asked for them
        # a dry run writes nothing at all, so whether the destination pre-existed says nothing
        # about what survives. Telling a user their live project was partly written after a
        # `--pretend` run points them at a backup restore for a directory copier never touched
        if self.pretend:
            return False
        return self._destination_existed or not self.copier_kwargs.get("cleanup_on_error", True)

    @property
    def finished(self) -> bool:
        """Whether the render has returned a verdict, so leaving is a close and not a cancel."""
        return self._done

    def on_key(self, event: events.Key) -> None:
        """Any key closes the finished run - except the ones that read the list of files.

        The log holds every path the render wrote and is taller than its box on any real
        template: 55 lines in 22 rows for the reference one, pinned at the bottom, with a
        scrollbar drawn to say so. Every key that would have scrolled it dismissed the screen
        instead, so the first two thirds of what had just been written to the reader's disk
        were unreachable. The exemption is handled here rather than as bindings, because a
        binding runs inside an action dispatch and that is what hung this screen before.
        """
        if not self._done:
            return
        action = _SCROLL_KEYS.get(event.key)
        if action is not None:
            event.stop()
            getattr(self.query_one("#exec-files", RichLog), f"action_{action}")()
            return
        event.stop()
        self.action_close()

    def action_close(self) -> None:
        """End the run once the verdict is in; idempotent, any key reaches it too.

        Reached from `on_key`, never from a key binding: `dismiss` waits for the screen to
        come off the stack, and an action runs inside the dispatch that has to return first.
        """
        if not self._done or self._closed:
            return
        self._closed = True
        self.dismiss(self._ok)

    def abandon(self) -> None:
        """End every child the render started, so a run with no verdict can still be left.

        The render is a thread, and a thread blocked in `subprocess.run` cannot be asked to
        stop - the app would sit waiting for it through its own shutdown. Ending the child is
        what unblocks the call: copier sees the task fail, raises, and the worker returns by
        the ordinary path with the ordinary cleanup. SIGKILL rather than SIGTERM, because a
        task that has already stopped answering is exactly the one being ended here.

        The whole tree goes, not the recorded process. copier runs a task written as a string
        through a shell, so what is recorded is `/bin/sh -c ...` and the work is its child:
        killing the shell alone left that grandchild running under init, writing into the
        destination the app had just reported abandoned, on a terminal the user believed they
        had got back.

        The tree is walked rather than signalled as a process group, because the group is not
        ours to move a task out of. A task is entitled to reach `/dev/tty` - cooking the line
        discipline is exactly what one of the fixtures does - and both ways of separating a
        child cost it that: a new session has no controlling terminal left to open, and a new
        process group is a background one, where the first read from the terminal takes SIGTTIN
        and stops the task where it stands. So the children stay where copier put them, and
        their descendants are found by asking the kernel who their parents are.
        """
        self._abandoned = True
        for child in self._children:
            self._end_tree(child)

    def _note_child(self, child: subprocess.Popen[Any]) -> None:
        """Record a child the render started, and end it at once if the run was abandoned.

        Abandoning has to outlast the keystroke. `abandon` used to sweep whatever list existed
        at that instant, and a render abandoned in its first moments has a list of copier's own
        finished `git` calls and nothing else - the task that will block has not been started
        yet. Nothing was killed, the app exited anyway, and then waited forever on a worker
        thread that went on to block in `subprocess.run`. Pressed within about half a second of
        the render appearing it wedged the process outright, which is the failure this key
        exists to prevent, moved half a second earlier.
        """
        self._children.append(child)
        if self._abandoned:
            self._end_tree(child)

    def _end_tree(self, child: subprocess.Popen[Any]) -> None:
        """SIGKILL one child and everything below it, deepest first."""
        if child.poll() is not None:
            return
        for pid in reversed(_descendants(child.pid)):
            _end(pid)
        _end(child.pid)

    def _run_copier(self) -> None:
        """Call TemplateUI.render off the UI thread; report back with call_from_thread.

        Not named `_render`: Widget._render is Textual's own, and shadowing it runs this
        on the UI thread during layout.
        """
        error: BaseException | None = None
        try:
            with (
                _children_without_stdin(self._note_child),
                _terminal_mode_kept(keep=lambda: not self._abandoned),
            ):
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
        # `.git` is pruned before it is entered, not filtered after: `rglob` walked every
        # object in it and the cap counted only the survivors, so on `update` of a real
        # repository the cap did nothing and the tick spent its time inside a tree it was
        # never going to list
        for top, dirs, files in os.walk(self.dst):
            dirs[:] = [d for d in dirs if d != ".git"]
            rel = Path(top).relative_to(self.dst)
            for name in dirs:
                found.append(str(rel / name) + "/")
            for name in files:
                found.append(str(rel / name))
            if len(found) >= WATCH_LIMIT:
                return found[:WATCH_LIMIT]
        return found

    def _finish(self, error: BaseException | None) -> None:
        """Put the verdict on the status line: mint on success, rose with the reason in the log.

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
        # a failure leaves the bar where it stopped. Filling it and painting it mint put the
        # largest, most saturated thing on the screen - "done, all good" - directly under a
        # one-line rose message saying the opposite
        if error is None:
            self.query_one("#exec-progress", ProgressBar).update(total=1, progress=1)
        else:
            # the class alone left it indeterminate, so a saturated rose band went on sweeping
            # the full width for ever on a screen that had already said the run failed and to
            # press a key. An endless loop reads as "still working"; in the failure colour on a
            # dead screen it reads as an alarm nobody can switch off
            # stopped where it was, not filled. The mint completion colour is reached only
            # by a run that succeeded, which is the whole point; a rose bar was tried and
            # could not paint - at `progress=0` the determinate render never reaches the
            # component the rule recolours - so the honest state is an empty track
            self.query_one("#exec-progress", ProgressBar).update(total=1, progress=0)
        status = self.query_one("#exec-status", Static)
        if error is None:
            # the path is cropped from the left to the room the row has: this line is one row
            # and at 60 columns it wrapped, so the second line was clipped and the verdict read
            # exactly `written to` with no destination at all
            room = self.size.width - len("written to ") - 2
            done = (
                "nothing written - this was a dry run"
                if self.pretend
                else f"written to {fit_path(self.dst, max(room, HEADER_PATH_FLOOR))}"
            )
            status.update(Text(done, style=MINT))
        else:
            # the reason goes in the log, which wraps nothing and scrolls; the status row is
            # one line with an ellipsis, and copier's sentences - a Jinja error with a
            # template path, a clone failure - ran off its edge at every supported width
            status.update(Text("failed - reason below", style=ROSE))
            self.query_one("#exec-files", RichLog).write(Text(_message(error), style=ROSE))
        self.query_one("#exec-verdict", Static).update(
            Text("arrows read the list  -  any other key closes")
        )
        self.set_focus(None)


@contextmanager
def _children_without_stdin(
    on_child: Callable[[subprocess.Popen[Any]], None],
) -> Iterator[None]:
    """Give everything the render starts a stdin of /dev/null, leaving this process's alone.

    `on_child` is told about every child the render begins, so a user who asks to
    leave mid-render has something to end - including a child started after they asked. A task
    blocked forever is a render with no verdict, and the screen has nothing to close; ending
    its children is what lets copier raise, the worker return, and the app shut down instead
    of waiting on a thread that will never come back.

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
        on_child(self)

    subprocess.Popen.__init__ = without_stdin
    try:
        yield
    finally:
        subprocess.Popen.__init__ = original


@contextmanager
def _terminal_mode_kept(fd: int = 0, keep: Callable[[], bool] = lambda: True) -> Iterator[None]:
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
        # not when the app is on its way out. The mode captured here is Textual's raw mode,
        # and on an abandoned render the driver has already put the terminal back to cooked by
        # the time this unwinds - writing raw over that left the user's shell with no echo, no
        # line editing and no ctrl+C. While the app is running the restore is unconditional,
        # which is the point: a comparison that had to be right is a comparison that can be
        # wrong. Whether the app is still running is not a comparison, it is a fact it knows.
        if keep():
            termios.tcsetattr(fd, termios.TCSANOW, mode)


def _message(error: BaseException) -> str:
    """copier's own message where there is one, the exception class otherwise."""
    return str(error) or type(error).__name__


def _descendants(pid: int) -> list[int]:
    """Every process below `pid`, parents before children, read from /proc.

    /proc is the only place this can be asked without a dependency, and it is read once per
    abandon rather than watched. A process that appears after the walk is not covered - the
    render is being ended, so nothing is starting more work, and the alternative is a loop
    that cannot say when it is finished.
    """
    children: dict[int, list[int]] = {}
    try:
        entries = list(Path("/proc").iterdir())
    except OSError:
        # no /proc: macOS, the BSDs. This ran inside the abandon key, so the FileNotFoundError
        # propagated into Textual's action dispatch and crashed the app mid-render - restoring
        # the exact wedge the key exists to prevent. Without the walk the recorded child is
        # still ended; only a grandchild under a shell survives, which is degraded, not stuck
        return []
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            # the comm field is parenthesised and may itself contain spaces and brackets, so
            # the fields after it are counted from the last close bracket, never from a split
            stat = (entry / "stat").read_text(encoding="utf-8", errors="replace")
            parent = int(stat[stat.rindex(")") + 1 :].split()[1])
        except (OSError, ValueError, IndexError):
            continue  # the process ended while its own file was being read
        children.setdefault(parent, []).append(int(entry.name))

    found: list[int] = []
    queue = list(children.get(pid, ()))
    while queue:
        current = queue.pop(0)
        found.append(current)
        queue.extend(children.get(current, ()))
    return found


def _end(pid: int) -> None:
    """SIGKILL one process, indifferent to it having gone already."""
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
