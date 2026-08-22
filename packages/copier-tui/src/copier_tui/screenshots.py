"""Headless SVG screenshots of the survey, review and execution screens, into docs/assets.

Run as `python -m copier_tui.screenshots [template-path]`. The render is a `--pretend` run,
so nothing is written outside the throwaway destination.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import tempfile

from copier_tui.app import SurveyApp
from copier_ui import TemplateUI

SIZE = (110, 40)
OUT = Path("docs/assets")
DEFAULT_TEMPLATE = "../../copier-data-science"
REVEAL = ("python_version_choice", "other")


def _save(app: SurveyApp, name: str) -> None:
    """Write the current frame as an SVG under docs/assets."""
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.svg").write_text(app.export_screenshot(title=f"copier-tui {name}"))
    print(f"{OUT}/{name}.svg")


async def _capture(template: str, dst: Path) -> None:
    """Drive survey to review to execution, saving one SVG per screen."""
    with TemplateUI.from_template(template, dst=dst) as ui:
        if REVEAL[0] in ui.schema().ids():
            ui.set(*REVEAL)
        app = SurveyApp(ui, dst, {"pretend": True, "quiet": True, "unsafe": True})
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            _save(app, "survey")
            await pilot.press("enter")
            await pilot.pause()
            _save(app, "review")
            await pilot.press("enter")
            for _ in range(300):
                await pilot.pause(0.1)
                banner = app.screen.query("#banner-box")
                if banner and banner.first().display:
                    break
            _save(app, "execution")
            app.exit(0)


def main() -> None:
    """Capture the three screens over the given template, or copier-data-science."""
    template = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TEMPLATE
    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(_capture(template, Path(tmp) / "demo-proj"))


if __name__ == "__main__":
    main()
