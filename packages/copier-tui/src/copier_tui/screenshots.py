"""Headless SVG screenshots of the survey, review and execution screens, into docs/assets.

Run as `python -m copier_tui.screenshots [template-path]`. The render is a `--pretend` run,
so nothing is written outside the throwaway destination.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import tempfile

from textual.pilot import Pilot

from copier_tui.app import SurveyApp
from copier_ui import TemplateUI

SIZE = (110, 40)
OUT = Path("docs/assets")
DEFAULT_TEMPLATE = "../../copier-data-science"
REVEAL = ("python_version_choice", "other")
REVEALED = "python_version_custom"


def _save(app: SurveyApp, name: str, out: Path) -> None:
    """Write the current frame as an SVG under docs/assets."""
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{name}.svg").write_text(app.export_screenshot(title=f"copier-tui {name}"))
    print(f"{out}/{name}.svg")


async def _capture(template: str, dst: Path, out: Path) -> None:
    """Drive survey to review to execution, saving one SVG per screen."""
    with TemplateUI.from_template(template, dst=dst, unsafe=True) as ui:
        if REVEAL[0] in ui.schema().ids():
            ui.set(*REVEAL)
        app = SurveyApp(ui, dst, {"pretend": True, "quiet": True, "unsafe": True})
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            revealed = app.screen.query(f"#ctl-{REVEALED}")
            if revealed:
                revealed.first().focus()
                await pilot.pause()
            _save(app, "survey", out)
            await pilot.press("enter")
            await pilot.pause()
            _save(app, "review", out)
            await pilot.press("enter")
            await _await_verdict(pilot, app)
            _save(app, "execution", out)
            app.exit(0)


async def _await_verdict(pilot: Pilot[int], app: SurveyApp) -> None:
    """Wait for the execution screen to report its verdict before capturing it."""
    for _ in range(300):
        await pilot.pause(0.1)
        verdict = app.screen.query("#exec-verdict")
        if verdict and str(verdict.first().visual).strip():
            return
    raise RuntimeError("the render never reported a verdict")


def main() -> None:
    """Capture the three screens over the given template, or copier-data-science.

    The run happens from inside a throwaway directory with a relative destination, so the
    header bar in the captures reads `demo-proj` rather than a temp path nobody will have.
    """
    template = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TEMPLATE).resolve()
    out = OUT.resolve()
    home = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            asyncio.run(_capture(str(template), Path("demo-proj"), out))
        finally:
            os.chdir(home)


if __name__ == "__main__":
    main()
