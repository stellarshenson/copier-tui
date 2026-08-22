"""Bump the shared patch version of both published packages.

Both packages are released in lockstep, so one patch number covers the pair - a major
change bumps the patch too, which is deliberate. `copier-tui` pins `copier-ui` exactly,
so the pin moves with the version.
"""

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "packages" / "copier-ui" / "pyproject.toml"
TUI = ROOT / "packages" / "copier-tui" / "pyproject.toml"
VERSION_RE = re.compile(r'^version = "(\d+)\.(\d+)\.(\d+)"$', re.MULTILINE)


def read_version(path: Path) -> tuple[int, int, int]:
    match = VERSION_RE.search(path.read_text())
    if match is None:
        sys.exit(f"no version found in {path}")
    return int(match[1]), int(match[2]), int(match[3])


def write_version(path: Path, version: str) -> None:
    text = VERSION_RE.sub(f'version = "{version}"', path.read_text(), count=1)
    path.write_text(text)


def main() -> None:
    ui_version = read_version(UI)
    if ui_version != read_version(TUI):
        sys.exit("packages are out of lockstep - align their versions before bumping")

    major, minor, patch = ui_version
    version = f"{major}.{minor}.{patch + 1}"

    write_version(UI, version)
    write_version(TUI, version)

    # keep the exact pin in copier-tui aligned with the new copier-ui version
    text = TUI.read_text()
    TUI.write_text(re.sub(r'"copier-ui==\d+\.\d+\.\d+"', f'"copier-ui=={version}"', text))

    print(f"New version: {version}")


if __name__ == "__main__":
    main()
