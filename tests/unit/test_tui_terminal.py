"""The terminal the app holds, and what a template's own tasks can do to it.

Every assertion here is a regression. A render that let a task take the keyboard - by eating
the keystrokes meant for the form, or by putting the line discipline back to cooked - left the
last screen's "press any key to close" answering nothing, and no way out but another terminal.
The last test drives the whole application through a real pty, because that is the only place
the failure shows: headless there is no line discipline to wreck and no keyboard to steal.
"""

from __future__ import annotations

import asyncio
import fcntl
import os
from pathlib import Path
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import termios
import time
import tty
from typing import Any

import pytest
from textual.widgets import RichLog

from copier_tui import app as app_module
from copier_tui.app import SurveyApp
from copier_tui.errors import EXIT_CANCELLED, EXIT_FAILURE, EXIT_OK
from copier_tui.screens.execution import (
    ExecutionScreen,
    _children_without_stdin,
    _descendants,
    _terminal_mode_kept,
)
from copier_ui import TemplateUI

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
REFERENCE = Path("/home/lab/workspace/private/copier-data-science")

SET_ANY_EVENT_MOUSE = b"\x1b[?1003h"
"""What a terminal is told with to report every movement of the pointer, not just its clicks."""

FOCUS_IN = b"\x1b[I"
FOCUS_OUT = b"\x1b[O"
"""What a terminal says when its window gains and loses the focus."""

ARROW_DOWN = b"\x1b[B"
"""A key that genuinely moves the cursor, for the other side of the disarming rule."""

READS_STDIN = "import sys; d = sys.stdin.buffer.read(); print(f'read {len(d)}')"
"""A child that says how many bytes its stdin gave it: 0 when that stdin is /dev/null."""

LAUNCH = "from copier_tui.cli import main; main()"
"""The console script's entry point, for a child that has the package but not the script."""

ANSI = re.compile(rb"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[()][B0]|\x1b[=>]")
"""Enough of the escape vocabulary to leave the painted words behind."""

ROWS, COLS = 40, 120
"""The pty the driven app believes it is painting on."""


def test_the_render_starts_its_children_without_a_keyboard() -> None:
    """Exit: nothing copier starts inherits the keyboard the form is reading.

    A template's tasks are subprocesses holding this process's own descriptors, so under
    `--trust` a task that reads stdin eats the keystrokes meant for the app - after which
    "press any key to close" never fires again. The child gets /dev/null; this process's own
    descriptor 0 is never touched, because Textual's input thread is reading it and reads an
    end-of-file underneath it as fast as the machine allows.
    """
    before = os.fstat(0)
    with _children_without_stdin(lambda _child: None):
        starved = subprocess.run(
            [sys.executable, "-c", READS_STDIN], capture_output=True, check=True
        )
        assert starved.stdout.strip() == b"read 0", starved
        assert os.fstat(0).st_dev == before.st_dev
        chosen = subprocess.run(
            [sys.executable, "-c", READS_STDIN], input=b"kept", capture_output=True, check=True
        )
        assert chosen.stdout.strip() == b"read 4", chosen
    after = os.fstat(0)
    assert (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)
    # and the patch is not left behind: a child started afterwards inherits again
    inherited = subprocess.run(
        [sys.executable, "-c", READS_STDIN], input=b"back", capture_output=True, check=True
    )
    assert inherited.stdout.strip() == b"read 4", inherited


def test_a_task_that_cooks_the_terminal_does_not_leave_it_that_way() -> None:
    """Exit: the mode the driver set at startup survives the render, whoever changed it.

    Taking a task's stdin away does not put the terminal out of its reach: descriptor 1 still
    goes there, `/dev/tty` is one redirection away, and `stty sane` is one line of an ordinary
    post-generation hook. Cooked, the line discipline holds every keystroke until a newline,
    which is a form that has stopped answering keys.
    """
    master, slave = pty.openpty()
    try:
        tty.setraw(slave)  # what Textual's driver does to the terminal at startup
        raw = termios.tcgetattr(slave)
        with _terminal_mode_kept(slave):
            subprocess.run(["stty", "sane"], stdin=slave, check=True)
            assert termios.tcgetattr(slave) != raw, "the terminal was meant to be cooked here"
        assert termios.tcgetattr(slave) == raw
    finally:
        os.close(slave)
        os.close(master)


def test_a_template_that_grabs_the_terminal_still_leaves_a_key_that_closes(tmp_path: Path) -> None:
    """Exit: a rude template renders, reports, and closes on one keystroke.

    The fixture's tasks do both halves of the failure - one reads stdin to end-of-file, one
    cooks the controlling terminal - and the app is driven through a real pty of its own. The
    key sent at the verdict is a bare `x`: no newline, which is exactly what a cooked terminal
    would insist on before handing anything over.
    """
    dst = tmp_path / "proj"
    child, master = _spawn("copy", "--trust", str(FIXTURES / "tui_rude"), str(dst))
    seen = bytearray()
    try:
        assert _wait_for(master, b"this template asks nothing", seen, 60), _screen(seen)
        os.write(master, b"\r")
        assert _wait_for(master, b"any other key closes", seen, 60), _screen(seen)
        os.write(master, b"x")
        assert _wait_for_exit(child, master, seen, 20) == 0, _screen(seen)
    finally:
        _reap(child, master)
    assert (dst / "README.md").is_file()


def test_the_render_never_asks_the_terminal_to_report_the_mouse(tmp_path: Path) -> None:
    """The terminal is never asked to report every movement of the pointer.

    The survey is driven from the keyboard throughout - the footer names every key it answers
    to - so a report per pointer twitch buys nothing, and asking for none leaves the terminal
    its own selection and copy.
    """
    dst = tmp_path / "proj"
    child, master = _spawn("copy", str(FIXTURES / "tui_flow"), str(dst))
    seen = bytearray()
    try:
        assert _wait_for(master, b"questionnaire", seen, 60), _screen(seen)
        assert SET_ANY_EVENT_MOUSE not in bytes(seen), "mouse motion reporting was turned on"
    finally:
        _reap(child, master)


def test_two_escapes_arriving_together_still_quit(tmp_path: Path) -> None:
    """Exit: the cancel does not care how fast the two presses are.

    Both bytes go out in one write, which is faster than any keyboard can deliver them and
    the case that failed: pressed in quick succession the second escape went missing and the
    survey sat there until a third press or an arrow key shook it loose.
    """
    dst = tmp_path / "proj"
    child, master = _spawn("copy", str(FIXTURES / "tui_flow"), str(dst))
    seen = bytearray()
    try:
        assert _wait_for(master, b"questionnaire", seen, 60), _screen(seen)
        os.write(master, b"\x1b\x1b")
        assert _wait_for_exit(child, master, seen, 20) == EXIT_CANCELLED, _screen(seen)
    finally:
        _reap(child, master)
    assert not dst.exists(), "a cancelled survey writes nothing"


def test_the_window_losing_focus_does_not_throw_away_the_first_escape(tmp_path: Path) -> None:
    """Exit: two escapes quit even when the terminal reports a focus change between them.

    This is the failure, and the terminal was never eating a keystroke. A terminal reports
    its window losing and regaining focus; Textual answers by putting the cursor back on the
    field that already had it, and the survey read that as the user moving and disarmed the
    cancel. So the first escape was thrown away, the second only armed it again, and what the
    user saw was the red warning and a screen that then ignored them for three seconds.

    The arrow at the end is the other half: a focus that genuinely moved must still disarm,
    or one stray key could discard a survey.
    """
    dst = tmp_path / "proj"
    child, master = _spawn("copy", str(FIXTURES / "tui_flow"), str(dst))
    seen = bytearray()
    try:
        assert _wait_for(master, b"questionnaire", seen, 60), _screen(seen)
        os.write(master, b"\x1b")
        os.write(master, FOCUS_OUT + FOCUS_IN)
        os.write(master, b"\x1b")
        assert _wait_for_exit(child, master, seen, 20) == EXIT_CANCELLED, _screen(seen)
    finally:
        _reap(child, master)
    assert not dst.exists(), "a cancelled survey writes nothing"


def test_a_key_that_moves_the_cursor_still_disarms_the_cancel(tmp_path: Path) -> None:
    """Exit: an escape followed by a real move and another escape does NOT quit.

    The safety is what makes escape twice safe to offer at all - a survey is too costly to
    lose to one stray press - so the fix above must not buy the first escape a longer life
    than the next keystroke.
    """
    dst = tmp_path / "proj"
    child, master = _spawn("copy", str(FIXTURES / "tui_flow"), str(dst))
    seen = bytearray()
    try:
        assert _wait_for(master, b"questionnaire", seen, 60), _screen(seen)
        os.write(master, b"\x1b")
        os.write(master, ARROW_DOWN)
        os.write(master, b"\x1b")
        assert _wait_for_exit(child, master, seen, 4) is None, "a moved cursor left it armed"
    finally:
        _reap(child, master)


def test_a_render_that_never_finishes_can_still_be_left(tmp_path: Path) -> None:
    """Exit: ctrl+x ends a run that has no verdict to close.

    The fixture's task sleeps for ten minutes, which is a template hanging on a lock or a
    fetch with no timeout. The render is a thread and a thread blocked in `subprocess.run`
    cannot be asked to stop, so before this the screen sat there with a pulsing bar, no
    verdict, no key that did anything, and no way out but another terminal. An ordinary key
    is still ignored - it must not abort a render that is only slow.
    """
    dst = tmp_path / "proj"
    child, master = _spawn("copy", "--trust", str(FIXTURES / "tui_slow"), str(dst))
    seen = bytearray()
    try:
        assert _wait_for(master, b"review", seen, 60), _screen(seen)
        os.write(master, b"\r")
        assert _wait_for(master, b"rendering", seen, 60), _screen(seen)
        os.write(master, b"x")
        assert _wait_for_exit(child, master, seen, 3) is None, "a plain key aborted the render"
        os.write(master, b"\x18")
        # a failure, not a cancel: a cancel is the promise that nothing was written, and the
        # render has been writing into the destination for as long as it has been running
        assert _wait_for_exit(child, master, seen, 20) == EXIT_FAILURE, _screen(seen)
    finally:
        _reap(child, master)


def _alive(pid: int) -> bool:
    """Whether `pid` is still running, counting a zombie as gone.

    `os.kill(pid, 0)` answers the wrong question here: a killed process whose parent has just
    exited stays in the table as a zombie until something reaps it, and signal 0 succeeds on
    one. The state letter in /proc says what actually happened.
    """
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return stat[stat.rindex(")") + 1 :].split()[0] != "Z"


def _spawn(*args: str) -> tuple[int, int]:
    """Run the CLI on a pty of its own, and return the child's pid and the master descriptor.

    `pty.fork` rather than a plain Popen on an openpty pair: the child has to be a session
    leader whose controlling terminal is the new pty, or the fixture's `/dev/tty` reaches the
    terminal running the suite instead of the one under test.
    """
    child, master = pty.fork()
    if child == 0:  # pragma: no cover - a forked child, and it execs on the next line
        try:
            env = dict(os.environ, TERM="xterm-256color", COLUMNS=str(COLS), LINES=str(ROWS))
            os.execve(sys.executable, [sys.executable, "-c", LAUNCH, *args], env)
        finally:
            os._exit(127)
    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
    return child, master


def _settle(master: int, seen: bytearray, quiet: float = 0.3, cap: float = 5.0) -> None:
    """Read until the app has painted nothing for `quiet` seconds, or `cap` elapses."""
    deadline = time.monotonic() + cap
    while time.monotonic() < deadline:
        before = len(seen)
        _read(master, seen, quiet)
        if len(seen) == before:
            return


def _wait_for(master: int, marker: bytes, seen: bytearray, timeout: float) -> bool:
    """Read until the app has painted `marker`, or the time is up."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if marker in _plain(seen):
            return True
        if not _read(master, seen, 0.2):
            return marker in _plain(seen)
    return False


def _wait_for_exit(child: int, master: int, seen: bytearray, timeout: float) -> int | None:
    """The child's exit code, or None when it is still there when the time is up.

    Reading goes on while waiting: a pty whose output is nobody's business fills up, and a
    child blocked on painting its last frame never reaches its own exit.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        done, status = os.waitpid(child, os.WNOHANG)
        if done:
            return os.waitstatus_to_exitcode(status)
        _read(master, seen, 0.2)
    return None


def _read(master: int, seen: bytearray, timeout: float) -> bool:
    """Take whatever the app has painted since the last look; False once the pty has closed."""
    if not select.select([master], [], [], timeout)[0]:
        return True
    try:
        chunk = os.read(master, 65536)
    except OSError:  # the child exited and took its end of the pty with it
        return False
    seen += chunk
    return bool(chunk)


def _reap(child: int, master: int) -> None:
    """Leave nothing behind, including after a failed assertion."""
    try:
        os.kill(child, signal.SIGKILL)
        os.waitpid(child, 0)
    except (ProcessLookupError, ChildProcessError):
        pass
    os.close(master)


def _plain(seen: bytearray) -> bytes:
    """What was painted, with the escape codes that placed it taken out."""
    return ANSI.sub(b"", bytes(seen))


def _screen(seen: bytearray) -> str:
    """The tail of the painted screen, for a failing assertion to show what happened.

    Blank lines go: most of a painted frame is the ground between the words, and a failure
    report that is nine tenths whitespace says nothing about which screen it stopped on.
    """
    painted = _plain(seen).decode(errors="replace").splitlines()
    return "\n".join(line.rstrip() for line in painted if line.strip())[-3000:]


def test_a_dead_arrow_at_the_end_of_the_form_still_disarms_the_cancel(tmp_path: Path) -> None:
    """Exit: escape, an arrow with nowhere to go, escape - the survey is NOT discarded.

    The ends of the form stopped rolling round, and disarming was a side effect of the focus
    moving, so at the last field `down` moved nothing, raised no focus event and left the
    cancel armed. That is the one place a held arrow key comes to rest, and the cost of the
    second escape there is every answer given.
    """
    child, master = _spawn("copy", "--trust", str(FIXTURES / "tui_kinds"), str(tmp_path / "out"))
    seen = bytearray()
    try:
        assert _wait_for(master, b"questionnaire", seen, 20.0)
        for _ in range(30):  # walk to the last field, where `down` has nowhere left to go
            os.write(master, ARROW_DOWN)
            time.sleep(0.02)
        _read(master, seen, 1.0)
        os.write(master, b"\x1b")
        _read(master, seen, 0.6)
        os.write(master, ARROW_DOWN)
        _read(master, seen, 0.6)
        os.write(master, b"\x1b")
        assert _wait_for_exit(child, master, seen, 4.0) is None, (
            "an arrow between two escapes must disarm the cancel, even at the end of the form"
        )
    finally:
        _reap(child, master)


def test_abandoning_a_render_ends_a_task_and_not_just_its_shell(tmp_path: Path) -> None:
    """Abandon reaches the work, not only the process copier handed back.

    copier runs a task written as a string through a shell, so the recorded process is
    `/bin/sh -c ...` and the work can be its child. Killing the shell alone left that
    grandchild running under init, still writing into the destination the app had just
    reported abandoned.

    `abandon` is called directly rather than driven through a pty, because a pty would hide
    the defect: `pty.fork` makes the app a session leader, so the kernel SIGHUPs its whole
    foreground group on exit and tidies the orphan away. A user's shell does no such thing.
    """
    screen = ExecutionScreen.__new__(ExecutionScreen)
    screen._children = []
    screen._abandoned = False
    marker = tmp_path / "task.pid"
    with _children_without_stdin(screen._note_child):
        subprocess.Popen(  # a shell is the case under test
            f'python3 -c \'import os,time; open("{marker}","w").write(str(os.getpid()));'
            " time.sleep(600)' & wait",
            shell=True,
        )
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline and not marker.exists():
        time.sleep(0.05)
    assert marker.exists(), "the task never started, so there is nothing to orphan"
    task = int(marker.read_text())
    assert _alive(task)

    screen.abandon()

    for _ in range(100):
        if not _alive(task):
            break
        time.sleep(0.05)
    else:
        os.kill(task, signal.SIGKILL)
        raise AssertionError(f"the task {task} outlived the render that started it")


@pytest.mark.parametrize(
    ("key", "name"),
    [(b"\r", "enter"), (b"\x1b", "escape"), (b"x", "a letter"), (b"\x18", "ctrl+x")],
)
def test_every_key_closes_a_finished_render(key: bytes, name: str, tmp_path: Path) -> None:
    """Exit: the verdict line's promise holds, including for the two keys it used to fail.

    `enter` and `escape` were bound to the close action, and an action runs inside the dispatch
    that `dismiss` waits on - so the two keys the footer named, and the two a person actually
    presses at that prompt, were the only two that hung. Every other key arrived through
    `on_key`, which is not a dispatch, and worked. The one close test sent a bare `x`.
    """
    child, master = _spawn("copy", "--trust", str(FIXTURES / "tui_flow"), str(tmp_path / "out"))
    seen = bytearray()
    try:
        assert _wait_for(master, b"questionnaire", seen, 60), _screen(seen)
        os.write(master, b"\r")  # survey hands over to review
        _read(master, seen, 1.0)
        os.write(master, b"\r")  # review confirms, the render starts
        assert _wait_for(master, b"any other key closes", seen, 60), _screen(seen)
        # let the paint finish before the key goes out. A single read returns on the first
        # byte, which during a paint is immediately, so it settled nothing - both the escape
        # case and ctrl+x were seen to flake under a loaded full-suite run. This reads until
        # the app has been quiet for a moment. A key that genuinely fails to close the run
        # still fails this as a hang; only the race with the paint is removed.
        _settle(master, seen)
        os.write(master, key)
        assert _wait_for_exit(child, master, seen, 15) == 0, f"{name} did not close the run"
    finally:
        _reap(child, master)


def test_a_render_abandoned_the_instant_it_starts_still_leaves(tmp_path: Path) -> None:
    """Exit: the key works before the task that would block has even been started.

    Abandoning used to sweep whatever children existed at that instant. A render abandoned in
    its first moments has a list of copier's own finished `git` calls and nothing else, so
    nothing was killed, the app exited anyway, and then waited forever on a worker thread that
    went on to block. The key that exists to prevent a wedge caused one, half a second earlier.
    """
    child, master = _spawn("copy", "--trust", str(FIXTURES / "tui_slow"), str(tmp_path / "out"))
    seen = bytearray()
    try:
        assert _wait_for(master, b"review", seen, 60), _screen(seen)
        os.write(master, b"\r")  # confirm; the render begins
        _read(master, seen, 0.05)  # no settling time on purpose - that is the case
        os.write(master, b"\x18")
        assert _wait_for_exit(child, master, seen, 20) == EXIT_FAILURE, _screen(seen)
        # and it says what it left behind. copier removes a destination it created, so for a
        # fresh one the honest answer is that nothing survived - the first version of this
        # message said "partly written" either way and sent the reader to a directory that
        # was no longer there
        assert b"abandoned mid-render" in _plain(seen), _screen(seen)
        assert b"nothing was left in" in _plain(seen), _screen(seen)
    finally:
        _reap(child, master)


def test_an_abandoned_render_hands_the_terminal_back_cooked(tmp_path: Path) -> None:
    """Exit: the shell that ran this still echoes, edits lines and answers ctrl+C.

    The render captures Textual's raw mode and restores it when it unwinds. On an abandoned
    run the driver has already put the terminal back to cooked by then, so that restore wrote
    raw over it and handed the user a shell with no echo, no line editing and no ctrl+C.
    """
    child, master = _spawn("copy", "--trust", str(FIXTURES / "tui_slow"), str(tmp_path / "out"))
    seen = bytearray()
    try:
        assert _wait_for(master, b"review", seen, 60), _screen(seen)
        os.write(master, b"\r")
        assert _wait_for(master, b"rendering", seen, 60), _screen(seen)
        os.write(master, b"\x18")
        assert _wait_for_exit(child, master, seen, 20) == EXIT_FAILURE, _screen(seen)
        flags = termios.tcgetattr(master)[3]
        assert flags & termios.ECHO, "the terminal was handed back with echo off"
        assert flags & termios.ICANON, "the terminal was handed back with line editing off"
        assert flags & termios.ISIG, "the terminal was handed back deaf to ctrl+C"
    finally:
        _reap(child, master)


@pytest.mark.skipif(not REFERENCE.is_dir(), reason="the reference template is not checked out")
async def test_the_list_of_written_files_can_be_read_before_the_screen_is_left(
    tmp_path: Path,
) -> None:
    """The scroll keys move the log; every other key still closes the run.

    The log holds every path the render wrote and is taller than its box on any real template.
    Every key used to dismiss the screen, so the entries above the fold were unreachable with a
    scrollbar drawn beside them saying otherwise. The first fix forwarded the key to the log,
    which reaches nothing - Textual resolves a widget's ordinary bindings only after the event
    has bubbled unhandled to the App, and this screen stops it first - so six keys went from
    closing the screen to doing nothing at all. The log's actions are called directly now.

    It takes the reference template because a fixture writing two files has nothing to scroll,
    which is exactly why the first version of this test passed against the broken fix.
    """
    dst = tmp_path / "proj"
    with TemplateUI.from_template(str(REFERENCE), dst=dst, unsafe=True) as ui:
        app = SurveyApp(ui, dst, {"unsafe": True, "quiet": True})
        async with app.run_test(size=(90, 16)) as pilot:
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("enter")
            for _ in range(300):
                await pilot.pause()
                screen = app.screen
                if isinstance(screen, ExecutionScreen) and screen.finished:
                    break
                await asyncio.sleep(0.1)
            log = app.screen.query_one("#exec-files", RichLog)
            assert log.max_scroll_y > 0, "the log did not overflow, so nothing is being tested"

            start = log.scroll_offset.y
            await pilot.press("up")
            await pilot.pause()
            assert log.scroll_offset.y < start, "up did not move the log"

            await pilot.press("home")
            await pilot.pause()
            assert log.scroll_offset.y == 0, "home did not reach the top"
            assert app.return_value is None, "a scroll key closed the screen"

            await pilot.press("j")
            await pilot.pause()
            assert app.return_value is not None, "a plain key no longer closes the run"


def test_the_descendant_walk_gives_up_quietly_where_there_is_no_proc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Off Linux there is no /proc, and the failure used to land inside the abandon key.

    `_descendants` ran from `abandon`, which runs from the quit action, so a `FileNotFoundError`
    propagated into Textual's dispatch: the app crashed mid-render, the child was never killed
    and the worker stayed blocked - restoring the exact wedge the key exists to prevent. Losing
    the walk costs a grandchild under a shell; losing the app costs the whole run.
    """
    original = Path.iterdir

    def no_proc(self: Path) -> Any:
        if str(self) == "/proc":
            raise FileNotFoundError(2, "No such file or directory", "/proc")
        return original(self)

    monkeypatch.setattr(Path, "iterdir", no_proc)
    assert _descendants(os.getpid()) == []


def test_the_survey_clears_the_terminal_state_the_last_program_left(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Startup: the scroll region and origin mode are reset before the first frame.

    A full-screen program that exits without restoring them leaves every line another
    program addresses afterwards offset by a row, and a screen redrawn by differences never
    corrects itself - the lines it believes unchanged are the ones in the wrong place. Seen
    launching the survey from another terminal program's menu: a caption drawn on the row
    below its own answer, and the same caption left standing two rows up.
    """
    written: list[str] = []
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "write", written.append)
    monkeypatch.setattr(sys.stdout, "flush", lambda: None)
    monkeypatch.setattr(app_module.SurveyApp, "run", lambda self, **kwargs: EXIT_OK)

    with TemplateUI.from_template(str(FIXTURES / "tui_flow"), dst=tmp_path / "out") as ui:
        app_module.run_survey(ui, tmp_path / "out", {})

    # the bytes, not the constant: compared symbolically this test stays green through any
    # edit to it, including one that drops the cursor save and sends the prompt to row 1
    assert "".join(written) == "\x1b7\x1b[r\x1b[?6l\x1b8"
    assert "".join(written) == app_module.TERMINAL_RESET


def test_a_piped_run_writes_no_escape_sequence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Startup: nothing is emitted where there is no terminal to put back.

    The sequences are meaningless to a pipe and would land in whatever is reading it, which
    is how a reset ends up inside a captured log or a test's own output.
    """
    written: list[str] = []
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    monkeypatch.setattr(sys.stdout, "write", written.append)
    monkeypatch.setattr(app_module.SurveyApp, "run", lambda self, **kwargs: EXIT_OK)

    with TemplateUI.from_template(str(FIXTURES / "tui_flow"), dst=tmp_path / "out") as ui:
        app_module.run_survey(ui, tmp_path / "out", {})

    assert written == []
