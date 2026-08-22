"""copier's own command line, subclassed.

plumbum collects subcommands and switches across the MRO and lets a child class override a
parent's subcommand of the same name, so every flag, short form, help string and error message
below is copier's, inherited rather than restated. Only `main` is overridden, and only to open
the survey instead of copier's prompt sequence. `check-update` is inherited untouched.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from copier import VcsRef
from copier._cli import (
    CopierApp,
    CopierCopySubApp,
    CopierRecopySubApp,
    CopierUpdateSubApp,
)
from copier._tools import try_enum
from plumbum import colors

from copier_tui import __version__
from copier_tui.app import run_survey
from copier_tui.errors import EXIT_FAILURE, NotATerminalError
from copier_ui import CopierUIError, Operation, TemplateUI


class CopierTuiApp(CopierApp):
    """The copier-tui CLI application."""

    PROGNAME = "copier-tui"
    VERSION = __version__


class _TuiSubcommand:
    """Shared launch path for the subcommands that open a survey."""

    def _headless(self) -> bool:
        """True when copier's own non-interactive flags were given: --defaults, --force, --quiet."""
        return bool(self.defaults or self.quiet or getattr(self, "force", False))

    def _copier_kwargs(self) -> dict[str, Any]:
        """The subcommand's flags, as keyword arguments for copier's run_* function."""
        return {
            "answers_file": self.answers_file,
            "vcs_ref": try_enum(VcsRef, self.vcs_ref),
            "exclude": self.exclude,
            "use_prereleases": self.prereleases,
            "skip_if_exists": self.skip,
            "pretend": self.pretend,
            "quiet": self.quiet,
            "unsafe": self.unsafe,
            "skip_tasks": self.skip_tasks,
            "ask": self.ask,
        }

    def _launch(self, src: str | None, destination_path: str, operation: Operation) -> int:
        """Check for a tty, load the template, run the survey; report load failures and exit."""
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            message = "copier-tui needs a terminal; use --defaults or --quiet to run headless"
            print(colors.red | str(NotATerminalError(message)), file=sys.stderr)
            return EXIT_FAILURE
        dst = Path(destination_path)
        try:
            ui = TemplateUI.from_template(
                src,
                vcs_ref=self.vcs_ref,
                answers_file=self.answers_file,
                dst=dst,
                data=self.data,
                operation=operation,
            )
        except CopierUIError as error:
            print(colors.red | str(error), file=sys.stderr)
            return EXIT_FAILURE
        with ui:
            return run_survey(ui, dst, self._copier_kwargs())


@CopierTuiApp.subcommand("copy")
class TuiCopySubApp(CopierCopySubApp, _TuiSubcommand):
    """The `copier-tui copy` subcommand."""

    def _copier_kwargs(self) -> dict[str, Any]:
        """copier's own `copy` arguments, as `copier copy` assembles them."""
        return {
            **super()._copier_kwargs(),
            "cleanup_on_error": self.cleanup_on_error,
            "defaults": self.force or self.defaults,
            "overwrite": self.force or self.overwrite,
        }

    def main(self, template_src: str, destination_path: str) -> int:
        """Survey the template, then copy it; headless flags fall through to copier."""
        if self._headless():
            return super().main(template_src, destination_path)
        return self._launch(template_src, destination_path, "copy")


@CopierTuiApp.subcommand("recopy")
class TuiRecopySubApp(CopierRecopySubApp, _TuiSubcommand):
    """The `copier-tui recopy` subcommand."""

    def _copier_kwargs(self) -> dict[str, Any]:
        """copier's own `recopy` arguments, as `copier recopy` assembles them."""
        return {
            **super()._copier_kwargs(),
            "defaults": self.force or self.defaults,
            "overwrite": self.force or self.overwrite,
            "skip_answered": self.skip_answered,
        }

    def main(self, destination_path: str = ".") -> int:
        """Survey seeded from the destination's answers file, then recopy."""
        if self._headless():
            return super().main(destination_path)
        return self._launch(None, destination_path, "recopy")


@CopierTuiApp.subcommand("update")
class TuiUpdateSubApp(CopierUpdateSubApp, _TuiSubcommand):
    """The `copier-tui update` subcommand."""

    def _copier_kwargs(self) -> dict[str, Any]:
        """copier's own `update` arguments, as `copier update` assembles them."""
        return {
            **super()._copier_kwargs(),
            "defaults": self.defaults,
            "overwrite": True,
            "conflict": self.conflict,
            "context_lines": self.context_lines,
            "skip_answered": self.skip_answered,
        }

    def main(self, destination_path: str = ".") -> int:
        """Survey seeded from the destination's answers file, then update."""
        if self._headless():
            return super().main(destination_path)
        return self._launch(None, destination_path, "update")


def main() -> None:
    """Console script entry point."""
    CopierTuiApp.run()
