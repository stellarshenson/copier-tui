"""copier-tui's argument layer: copier's subcommands, flags, help and errors.

Nothing here launches the app; the survey entry point is stubbed out so the tests observe
what the CLI parsed and what it would have handed to copier.
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
import re
import sys
from typing import Any

from copier._cli import CopierApp, CopierCopySubApp, CopierRecopySubApp, CopierUpdateSubApp
import pytest

from copier_tui import cli as cli_mod
from copier_tui.cli import CopierTuiApp, TuiCopySubApp, TuiRecopySubApp, TuiUpdateSubApp
from copier_tui.errors import EXIT_FAILURE, EXIT_OK, EXIT_UNSAFE

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FLOW = str(FIXTURES / "tui_flow")

_OPTION = re.compile(r"--[a-zA-Z][\w-]*")


class _Stream(io.StringIO):
    """A captured stream that can claim to be a terminal, as the tty check asks it."""

    def __init__(self, tty: bool) -> None:
        """Remember whether this stream should pass for a terminal."""
        super().__init__()
        self._tty = tty

    def isatty(self) -> bool:
        """What the tty check reads."""
        return self._tty


def run_cli(argv: list[str], tty: bool = False) -> tuple[Any, int, str]:
    """Run the copier-tui CLI without exiting, returning (subcommand, code, output)."""
    captured = _Stream(tty)
    stdin = sys.stdin
    sys.stdin = _Stream(tty)
    try:
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            instance, code = CopierTuiApp.run(argv, exit=False)
    finally:
        sys.stdin = stdin
    return instance, code, captured.getvalue()


def run_copier(argv: list[str]) -> str:
    """Run copier's own CLI without exiting, returning its output."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        CopierApp.run(argv, exit=False)
    return buffer.getvalue()


@pytest.fixture
def launched(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Capture what a subcommand would launch, instead of opening a survey."""
    call: dict[str, Any] = {}

    def fake_launch(self: Any, src: str | None, destination_path: str, operation: str) -> int:
        call.update(
            src=src,
            dst=destination_path,
            operation=operation,
            data=self.data,
            kwargs=self._copier_kwargs(),
        )
        return EXIT_OK

    monkeypatch.setattr(cli_mod._TuiSubcommand, "_launch", fake_launch)
    return call


def test_subcommands_are_copier_s() -> None:
    """copy, recopy, update and check-update are registered under copier's own names."""
    names = {
        attribute.removeprefix("_subcommand_")
        for attribute in dir(CopierTuiApp)
        if attribute.startswith("_subcommand_")
    }
    assert {"copy", "recopy", "update", "check-update"} <= names
    assert issubclass(TuiCopySubApp, CopierCopySubApp)
    assert issubclass(TuiRecopySubApp, CopierRecopySubApp)
    assert issubclass(TuiUpdateSubApp, CopierUpdateSubApp)


def test_copy_long_flags_reach_copier(launched: dict[str, Any]) -> None:
    """Every copy flag is accepted with copier's spelling and forwarded to run_copy."""
    _, code, _ = run_cli(
        [
            "copier-tui",
            "copy",
            "--data",
            "name=zed",
            "--vcs-ref",
            "v1",
            "--answers-file",
            ".answers.yml",
            "--exclude",
            "*.pyc",
            "--skip",
            "keep.txt",
            "--overwrite",
            "--pretend",
            "--trust",
            "--skip-tasks",
            "--prereleases",
            FLOW,
            "dst",
        ]
    )
    assert code == EXIT_OK
    assert (launched["src"], launched["dst"], launched["operation"]) == (FLOW, "dst", "copy")
    assert launched["data"] == {"name": "zed"}
    assert launched["kwargs"] == {
        "answers_file": ".answers.yml",
        "vcs_ref": "v1",
        "exclude": ["*.pyc"],
        "use_prereleases": True,
        "skip_if_exists": ["keep.txt"],
        "pretend": True,
        "quiet": False,
        "unsafe": True,
        "skip_tasks": True,
        "ask": [],
        "cleanup_on_error": True,
        "defaults": False,
        "overwrite": True,
    }


def test_copy_short_flags_mean_the_same(launched: dict[str, Any]) -> None:
    """copier's short forms parse to the same run_copy arguments as the long forms."""
    run_cli(
        [
            "copier-tui",
            "copy",
            "-d",
            "name=zed",
            "-r",
            "v1",
            "-a",
            ".answers.yml",
            "-x",
            "*.pyc",
            "-s",
            "keep.txt",
            "-w",
            "-n",
            "--trust",
            "-T",
            "-g",
            FLOW,
            "dst",
        ]
    )
    short = dict(launched)
    launched.clear()
    run_cli(
        [
            "copier-tui",
            "copy",
            "--data",
            "name=zed",
            "--vcs-ref",
            "v1",
            "--answers-file",
            ".answers.yml",
            "--exclude",
            "*.pyc",
            "--skip",
            "keep.txt",
            "--overwrite",
            "--pretend",
            "--trust",
            "--skip-tasks",
            "--prereleases",
            FLOW,
            "dst",
        ]
    )
    assert short == launched


def test_copy_force_means_defaults_and_overwrite(launched: dict[str, Any]) -> None:
    """--force is copier's shorthand, and it takes the headless path rather than the survey."""
    _, code, _ = run_cli(["copier-tui", "copy", "--force", "--pretend", FLOW, "dst"])
    assert launched == {}
    assert code == EXIT_OK


def test_update_flags_reach_copier(launched: dict[str, Any]) -> None:
    """update carries copier's own merge flags through to run_update."""
    _, code, _ = run_cli(
        ["copier-tui", "update", "--conflict", "rej", "--context-lines", "7", "-A", "dst"]
    )
    assert code == EXIT_OK
    assert (launched["src"], launched["dst"], launched["operation"]) == (None, "dst", "update")
    assert launched["kwargs"]["conflict"] == "rej"
    assert launched["kwargs"]["context_lines"] == 7
    assert launched["kwargs"]["skip_answered"] is True
    assert launched["kwargs"]["overwrite"] is True


def test_recopy_flags_reach_copier(launched: dict[str, Any]) -> None:
    """recopy takes the destination alone and forwards its flags to run_recopy."""
    _, code, _ = run_cli(["copier-tui", "recopy", "--overwrite", "--skip-answered", "dst"])
    assert code == EXIT_OK
    assert (launched["src"], launched["dst"], launched["operation"]) == (None, "dst", "recopy")
    assert launched["kwargs"]["overwrite"] is True
    assert launched["kwargs"]["skip_answered"] is True


def test_recopy_destination_defaults_to_cwd(launched: dict[str, Any]) -> None:
    """copier's own default destination, unchanged."""
    run_cli(["copier-tui", "recopy"])
    assert launched["dst"] == "."


@pytest.mark.parametrize("subcommand", ["copy", "recopy", "update", "check-update"])
def test_help_lists_copier_s_options(subcommand: str) -> None:
    """Each subcommand's help offers exactly the options copier's help offers."""
    _, code, tui_help = run_cli(["copier-tui", subcommand, "--help"])
    copier_help = run_copier(["copier", subcommand, "--help"])
    assert code == EXIT_OK
    assert set(_OPTION.findall(tui_help)) == set(_OPTION.findall(copier_help))


def test_root_help_lists_copier_s_subcommands() -> None:
    """copier-tui --help names the same subcommands as copier --help."""
    _, code, tui_help = run_cli(["copier-tui", "--help"])
    copier_help = run_copier(["copier", "--help"])
    assert code == EXIT_OK
    for subcommand in ("copy", "recopy", "update", "check-update"):
        assert subcommand in tui_help
    assert set(_OPTION.findall(tui_help)) == set(_OPTION.findall(copier_help))


def test_unknown_flag_is_rejected_with_copier_s_text() -> None:
    """A flag copier does not define fails the way copier fails."""
    _, code, output = run_cli(["copier-tui", "copy", "--nonsense", FLOW, "dst"])
    _, copier_code = CopierApp.run(["copier", "copy", "--nonsense", FLOW, "dst"], exit=False)
    assert code == copier_code == 2
    assert "Unknown switch --nonsense" in output


@pytest.mark.parametrize("flag", ["--defaults", "--force"])
def test_non_interactive_flags_never_build_an_app(
    flag: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--defaults and --force go straight to copier: no TemplateUI, no Textual app.

    They are handed to copier as they are, so the outcome is copier's own.
    """

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("the headless path must not touch the TUI")

    monkeypatch.setattr(cli_mod, "run_survey", forbidden)
    monkeypatch.setattr(cli_mod.TemplateUI, "from_template", forbidden)
    tui_dst = tmp_path / "tui"
    copier_dst = tmp_path / "copier"
    _, code, _ = run_cli(["copier-tui", "copy", flag, "--trust", FLOW, str(tui_dst)], tty=True)
    _, copier_code = CopierApp.run(
        ["copier", "copy", flag, "--trust", FLOW, str(copier_dst)], exit=False
    )
    assert code == copier_code


def test_quiet_alone_still_opens_the_survey(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--quiet suppresses copier's status output; it answers nothing, so it still asks."""
    opened: list[str] = []
    monkeypatch.setattr(cli_mod, "run_survey", lambda *a, **k: opened.append("yes") or EXIT_OK)
    _, code, _ = run_cli(
        ["copier-tui", "copy", "--quiet", "--trust", FLOW, str(tmp_path / "out")], tty=True
    )
    assert opened == ["yes"]
    assert code == EXIT_OK


def test_ask_hands_the_run_to_copier_s_own_prompting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--ask re-asks its questions at render time, so it takes copier's path, not the survey.

    copier tests the ask globs before the pre-supplied-answers short-circuit, so a question
    named by --ask is prompted for even though the survey already answered it - on the render
    worker, with Textual holding the terminal. The flag keeps copier's semantics instead.
    """
    monkeypatch.setattr(
        cli_mod, "run_survey", lambda *a, **k: pytest.fail("the survey must not open")
    )
    argv = ["copy", "--defaults", "--ask", "*", "--trust", FLOW]
    _, code, _ = run_cli(["copier-tui", *argv, str(tmp_path / "tui")], tty=True)
    _, copier_code = CopierApp.run(["copier", *argv, str(tmp_path / "copier")], exit=False)
    assert code == copier_code


def test_defaults_renders_headless(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--defaults completes the render without a survey."""
    monkeypatch.setattr(
        cli_mod, "run_survey", lambda *a, **k: pytest.fail("the survey must not open")
    )
    dst = tmp_path / "out"
    _, code, _ = run_cli(["copier-tui", "copy", "--defaults", "--trust", FLOW, str(dst)])
    assert code == EXIT_OK
    assert (dst / "name.txt").read_text().strip() == "demo"


def test_data_is_seeded_into_the_survey(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--data reaches TemplateUI as preset answers, which is what hides the question."""
    seen: dict[str, Any] = {}

    def fake_from_template(src: str, **kwargs: Any) -> Any:
        seen.update(src=src, **kwargs)
        return contextlib.nullcontext(None)

    monkeypatch.setattr(cli_mod.TemplateUI, "from_template", fake_from_template)
    monkeypatch.setattr(cli_mod, "run_survey", lambda ui, dst, kwargs: EXIT_OK)
    _, code, _ = run_cli(
        ["copier-tui", "copy", "-d", "name=zed", FLOW, str(tmp_path / "out")], tty=True
    )
    assert code == EXIT_OK
    assert seen["data"] == {"name": "zed"}
    assert seen["operation"] == "copy"


def test_without_a_terminal_it_says_so(tmp_path: Path) -> None:
    """No tty means one line of explanation and a failure code, not a traceback."""
    _, code, output = run_cli(["copier-tui", "copy", FLOW, str(tmp_path / "out")])
    assert code == EXIT_FAILURE
    assert "terminal" in output
    assert not (tmp_path / "out").exists()


def test_template_load_failure_exits_before_the_survey(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bad template path is reported and the survey never opens."""
    monkeypatch.setattr(
        cli_mod, "run_survey", lambda *a, **k: pytest.fail("the survey must not open")
    )
    _, code, output = run_cli(
        ["copier-tui", "copy", str(tmp_path / "nope"), str(tmp_path / "out")], tty=True
    )
    assert code == EXIT_FAILURE
    assert output.strip()


def test_an_untrusted_template_exits_with_copier_s_own_unsafe_code(tmp_path: Path) -> None:
    """A template refused for an unsafe feature exits 4, as copier's own run does."""
    template = tmp_path / "template"
    template.mkdir()
    (template / "copier.yml").write_text("_jinja_extensions: [jinja2_time.TimeExtension]\n")
    (template / "README.md.jinja").write_text("hello\n")
    argv = ["copy", str(template)]
    _, code, output = run_cli(["copier-tui", *argv, str(tmp_path / "tui")], tty=True)
    _, copier_code = CopierApp.run(["copier", *argv, str(tmp_path / "copier")], exit=False)
    assert code == copier_code == EXIT_UNSAFE
    assert "jinja_extensions" in output
