"""The terminal the app holds, and what a template's own tasks can do to it.

Every assertion here is a regression. A render that let a task take the keyboard - by eating
the keystrokes meant for the form, or by putting the line discipline back to cooked - left the
last screen's "press any key to close" answering nothing, and no way out but another terminal.
The last test drives the whole application through a real pty, because that is the only place
the failure shows: headless there is no line discipline to wreck and no keyboard to steal.
"""

from __future__ import annotations

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

from copier_tui.errors import EXIT_CANCELLED
from copier_tui.screens.execution import _children_without_stdin, _terminal_mode_kept

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

SET_ANY_EVENT_MOUSE = b"\x1b[?1003h"
"""What a terminal is told with to report every movement of the pointer, not just its clicks."""

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
    with _children_without_stdin():
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
        assert _wait_for(master, b"press any key to close", seen, 60), _screen(seen)
        os.write(master, b"x")
        assert _wait_for_exit(child, master, seen, 20) == 0, _screen(seen)
    finally:
        _reap(child, master)
    assert (dst / "README.md").is_file()


def test_the_render_never_asks_the_terminal_to_report_the_mouse(tmp_path: Path) -> None:
    """Exit: nothing the pointer does can reach the keyboard the form is reading.

    A bare escape byte is ambiguous until the next byte arrives, so Textual holds it back to
    see what follows. Any-event mouse reporting means the terminal is emitting a sequence
    every time the pointer twitches, and one of those arriving behind a second escape becomes
    its introducer: the escape is consumed as part of the report and the two-press cancel
    never lands. The survey is keyboard-driven, so the reports are simply never asked for.
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
