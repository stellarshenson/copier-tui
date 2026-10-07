"""The terminal's background, asked for before the app starts, and the theme it calls for.

Textual switches its stylesheet between a light and a dark theme only on its own setting and
never asks the terminal. `pick_theme()` asks, and it runs before `App.run()`, because Textual
owns the terminal afterwards. The palettes and the themes themselves are in `theme`.
"""

from __future__ import annotations

import os
import re
import select
import sys

from copier_tui.theme import DARK, LIGHT

_OSC11_QUERY = b"\033]11;?\033\\"
_DA1_QUERY = b"\033[c"
_DA1_REPLY = re.compile(rb"\033\[\?[\d;]*c")
_TERMINAL_WAIT = 1.0
"""Seconds to wait for the terminal's last answer before going on without one."""


def parse_osc11(reply: str) -> bool | None:
    """True for a dark background, False for a light one, None when `reply` holds no colour.

    A terminal answers `ESC ] 11 ; rgb:RRRR/GGGG/BBBB` with one to four hex digits a channel.
    """
    found = re.search(r"rgba?:([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})", reply)
    if not found:
        return None
    red, green, blue = (int(h, 16) / (16 ** len(h) - 1) for h in found.groups())
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue < 0.5


def _ask_terminal(timeout: float = _TERMINAL_WAIT, device: str = "/dev/tty") -> bool | None:
    """Ask the terminal at `device` for its background colour: True dark, False light.

    None when there is no terminal, or it does not say.

    Two questions are sent, the background colour and then the device attributes, and the
    reading stops at the answer to the second. Every terminal answers the second, in order,
    so its answer arriving means nothing more is on the way. A fixed wait is not enough here:
    an answer that arrives after the wait reaches the app as typing, and the first control of
    a survey is a text field, so `]11;rgb:1a1a/1f1f/2525` was written into the first answer.
    The second question also ends the wait at once on a terminal that does not know the
    first.
    """
    try:
        import termios
        import tty

        fd = os.open(device, os.O_RDWR | os.O_NOCTTY)
    except (ImportError, OSError):
        return None
    try:
        saved = termios.tcgetattr(fd)
    except termios.error:
        os.close(fd)
        return None
    try:
        tty.setraw(fd)
        os.write(fd, _OSC11_QUERY + _DA1_QUERY)
        reply = b""
        while not _DA1_REPLY.search(reply) and select.select([fd], [], [], timeout)[0]:
            reply += os.read(fd, 64)
        return parse_osc11(reply.decode(errors="replace"))
    except OSError:
        return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        os.close(fd)


def _colorfgbg() -> bool | None:
    """True for a dark background from `COLORFGBG`, None when the variable does not say.

    rxvt and Konsole export it as `fg;bg` in ANSI colour numbers; 0 to 6 and 8 are dark.
    """
    ground = os.environ.get("COLORFGBG", "").split(";")[-1]
    return int(ground) in (0, 1, 2, 3, 4, 5, 6, 8) if ground.isdigit() else None


def pick_theme() -> str:
    """The name of the theme to start with.

    In order: `TEXTUAL_THEME` naming one of the two, the terminal's own answer, `COLORFGBG`,
    then dark. It must run before `App.run()`, because Textual owns the terminal afterwards.
    """
    wanted = os.environ.get("TEXTUAL_THEME", "")
    if wanted in (DARK, LIGHT):
        return wanted
    dark = _ask_terminal() if sys.stdin.isatty() else None
    if dark is None:
        dark = _colorfgbg()
    return LIGHT if dark is False else DARK
