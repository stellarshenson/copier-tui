"""Which of the two themes the app starts in, and how it finds out.

Textual switches its stylesheet between a light and a dark theme only on its own setting; it
never asks the terminal. The app asks before it starts, and these tests are the terminal.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import os
import pty
import sys
import termios
import threading
import time

import pytest

from copier_tui import background, theme
from copier_tui.background import _ask_terminal, parse_osc11, pick_theme
from copier_tui.theme import DARK, LIGHT, PALETTES, THEMES

DA1 = b"\x1b[?62;22c"
"""What a terminal answers to the device-attributes question."""

LIGHT_GROUND = b"\x1b]11;rgb:f5f5/f7f7/fafa\x1b\\"
DARK_GROUND = b"\x1b]11;rgb:1a1a/1f1f/2525\x07"
"""A light and a dark background as a terminal reports them, one closed by ST and one by BEL."""


@contextmanager
def terminal(*answers: bytes, delay: float = 0.0) -> Iterator[tuple[str, int]]:
    """A terminal that answers the app's questions with `answers`, after `delay` seconds.

    Yields the path the app opens and the descriptor the terminal's own side reads on. The
    terminal waits for the question before it answers, as a real one does.
    """
    master, slave = pty.openpty()

    def answer() -> None:
        asked = b""
        while b"\x1b[c" not in asked:
            asked += os.read(master, 64)
        time.sleep(delay)
        for part in answers:
            os.write(master, part)

    thread = threading.Thread(target=answer, daemon=True)
    thread.start()
    try:
        yield os.ttyname(slave), slave
    finally:
        thread.join(timeout=5)
        os.close(slave)
        os.close(master)


def unread(slave: int) -> bytes:
    """What the terminal sent that nothing has read: bytes an app would take for typing."""
    os.set_blocking(slave, False)
    try:
        return os.read(slave, 1024)
    except BlockingIOError:
        return b""


@pytest.mark.parametrize(
    ("reply", "dark"),
    [
        ("\x1b]11;rgb:1a1a/1f1f/2525\x1b\\", True),
        ("\x1b]11;rgb:f5f5/f7f7/fafa\x07", False),
        ("\x1b]11;rgb:ff/ff/ff\x07", False),
        ("\x1b]11;rgba:0000/0000/0000/ffff\x07", True),
        ("\x1b[?62;22c", None),
        ("", None),
    ],
)
def test_a_background_colour_is_read_as_light_or_dark(reply: str, dark: bool | None) -> None:
    """A terminal reports one to four hex digits a channel, closed by ST or by BEL."""
    assert parse_osc11(reply) is dark


@pytest.mark.parametrize(("ground", "dark"), [(LIGHT_GROUND, False), (DARK_GROUND, True)])
def test_the_terminal_is_asked_and_its_answer_is_read_whole(ground: bytes, dark: bool) -> None:
    """The answer is taken off the terminal entirely, so none of it is left to be typed."""
    with terminal(ground, DA1) as (device, slave):
        before = termios.tcgetattr(slave)
        assert _ask_terminal(timeout=5, device=device) is dark
        assert unread(slave) == b""
        assert termios.tcgetattr(slave) == before  # the line discipline is put back


def test_an_answer_that_arrives_late_is_still_read_whole() -> None:
    """A slow link delays the answer past any fixed wait; the app waits for the last one.

    Half a second is more than twice the fifth of a second a fixed wait would have given it.
    Read after that wait, the answer reached the survey as typing in its first field.
    """
    with terminal(LIGHT_GROUND, DA1, delay=0.5) as (device, slave):
        assert _ask_terminal(timeout=5, device=device) is False
        assert unread(slave) == b""


def test_a_terminal_that_does_not_know_the_question_is_not_waited_for() -> None:
    """A terminal with no background to report still answers the second question at once."""
    with terminal(DA1) as (device, slave):
        started = time.monotonic()
        assert _ask_terminal(timeout=5, device=device) is None
        assert time.monotonic() - started < 2
        assert unread(slave) == b""


def test_a_terminal_that_answers_nothing_is_given_up_on() -> None:
    """The wait ends, and the app starts in the default theme."""
    with terminal() as (device, _):
        started = time.monotonic()
        assert _ask_terminal(timeout=0.3, device=device) is None
        assert 0.3 <= time.monotonic() - started < 2


def test_no_terminal_is_no_answer() -> None:
    """A path that is not a terminal - a run with no controlling terminal - says nothing."""
    assert _ask_terminal(device="/nonexistent/tty") is None
    assert _ask_terminal(device=os.devnull) is None


def test_a_named_theme_is_taken_without_asking(monkeypatch: pytest.MonkeyPatch) -> None:
    """`TEXTUAL_THEME` naming one of the two themes decides, and the terminal is not asked."""
    monkeypatch.setattr(background, "_ask_terminal", lambda: pytest.fail("the terminal was asked"))
    monkeypatch.setenv("TEXTUAL_THEME", LIGHT)
    assert pick_theme() == LIGHT
    monkeypatch.setenv("TEXTUAL_THEME", DARK)
    assert pick_theme() == DARK


@pytest.mark.parametrize(
    ("answer", "colorfgbg", "expected"),
    [
        (False, "15;0", LIGHT),  # the terminal's own answer outranks the variable
        (True, "0;15", DARK),
        (None, "0;15", LIGHT),  # no answer: the variable decides
        (None, "15;0", DARK),
        (None, "15;default", DARK),  # a variable that does not say: dark
        (None, "", DARK),
    ],
)
def test_the_theme_follows_the_terminal_then_the_variable_then_dark(
    answer: bool | None, colorfgbg: str, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The order: the terminal's answer, `COLORFGBG`, then the dark theme."""
    monkeypatch.setenv("TEXTUAL_THEME", "textual-dark")  # not one of the two, so not a choice
    monkeypatch.setenv("COLORFGBG", colorfgbg)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(background, "_ask_terminal", lambda: answer)
    assert pick_theme() == expected


def test_a_run_with_no_keyboard_does_not_ask(monkeypatch: pytest.MonkeyPatch) -> None:
    """With stdin not a terminal there is nobody to answer, so nothing is written to it."""
    monkeypatch.delenv("TEXTUAL_THEME", raising=False)
    monkeypatch.delenv("COLORFGBG", raising=False)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(background, "_ask_terminal", lambda: pytest.fail("the terminal was asked"))
    assert pick_theme() == DARK


def test_each_theme_carries_every_role_as_a_variable() -> None:
    """The stylesheet names `$st-<role>`, so a role with no variable fails the parse."""
    for mode, palette in PALETTES.items():
        variables = THEMES[mode].variables
        for role, value in palette.items():
            assert variables[f"st-{role}"] == value
        assert THEMES[mode].dark is (mode == "dark")
        assert variables["scrollbar"] == palette["subtle"]
        assert variables["scrollbar-background"] == palette["chrome"]
        assert [variables[f"st-pulse-{step}"] for step in range(theme.PULSE_STEPS)] == list(
            theme.pulse_shades(mode)
        )
