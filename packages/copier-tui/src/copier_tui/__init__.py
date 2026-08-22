"""Terminal renderer for a copier template survey."""

from importlib.metadata import version
import os

# WSL leaves COLORTERM unset, and the dark slates downsample to xterm teal without it.
os.environ.setdefault("COLORTERM", "truecolor")

__version__ = version("copier-tui")

__all__ = ["__version__"]
