"""The wheels are two independent distributions and `copier_ui` needs no display library."""

from importlib import metadata
import subprocess
import sys

from packaging.requirements import Requirement

# copier itself needs prompt_toolkit through questionary, so only the libraries copier_ui
# must never reach for are blocked here
SURVEY = """
import sys


class BlockDisplayLibraries:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in {"textual", "rich", "copier_tui"}:
            raise ImportError(f"{name} is not installed")
        return None


sys.meta_path.insert(0, BlockDisplayLibraries())

from pathlib import Path

from copier_ui import TemplateUI

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
with TemplateUI.from_template(src, dst=dst) as ui:
    ui.set("name", "functional")
    ui.render(dst, quiet=True)

assert (dst / "hello.txt").read_text() == "hello functional\\n", "template did not render"
"""


def requirement_names(distribution: str) -> set[str]:
    return {Requirement(line).name for line in metadata.requires(distribution) or []}


def test_copier_ui_requires_no_display_library():
    assert requirement_names("copier-ui").isdisjoint({"textual", "rich", "copier-tui"})


def test_copier_tui_pins_copier_ui():
    requires = metadata.requires("copier-tui") or []

    assert f"copier-ui=={metadata.version('copier-ui')}" in requires


def test_copier_ui_surveys_and_renders_with_display_libraries_blocked(tmp_path):
    src = tmp_path / "template"
    src.mkdir()
    (src / "copier.yml").write_text("name:\n  type: str\n  default: world\n")
    (src / "hello.txt.jinja").write_text("hello {{ name }}\n")
    script = tmp_path / "survey.py"
    script.write_text(SURVEY)

    result = subprocess.run(
        [sys.executable, str(script), str(src), str(tmp_path / "proj")],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )

    assert result.returncode == 0, result.stderr
