"""Errors and exit codes for the terminal frontend."""

from __future__ import annotations

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_CANCELLED = 2


class TuiError(Exception):
    """Base class for every copier_tui error."""


class NotATerminalError(TuiError):
    """Launched without a terminal on stdin or stdout."""
