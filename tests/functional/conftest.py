"""Fixtures for the functional suite.

These tests run against the built wheels installed into a throwaway environment, so they
import only the public API of `copier_ui` and `copier_tui` and never touch the source tree.
Anything they need on disk they create in a temp directory.
"""

from pathlib import Path
import subprocess
import sys

import pytest

LOCAL_TEMPLATE = Path("/home/lab/workspace/private/copier-data-science")
TEMPLATE_URL = "gh:stellarshenson/copier-data-science"
TEMPLATE_TAG = "v1.3.18"


@pytest.fixture(scope="session")
def reference_template() -> tuple[str, str]:
    """The copier-data-science template as `(src, vcs_ref)`.

    The local clone is preferred when it is there; CI has no clone and fetches from GitHub.
    A working checkout need not carry the release tags, so it falls back to its HEAD.
    """
    if not (LOCAL_TEMPLATE / "copier.yml").is_file():
        return TEMPLATE_URL, TEMPLATE_TAG
    tag = subprocess.run(
        ["git", "-C", str(LOCAL_TEMPLATE), "rev-parse", "--verify", "--quiet", TEMPLATE_TAG],
        capture_output=True,
        check=False,
    )
    return str(LOCAL_TEMPLATE), TEMPLATE_TAG if tag.returncode == 0 else "HEAD"


@pytest.fixture(scope="session")
def console_script() -> str:
    """The `copier-tui` entry point installed beside the interpreter running the suite."""
    script = Path(sys.executable).parent / "copier-tui"
    assert script.is_file(), f"copier-tui console script not installed at {script}"
    return str(script)
