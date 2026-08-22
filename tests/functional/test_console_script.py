"""The `copier-tui` console script, driven as a subprocess against the installed wheels."""

import subprocess


def run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [script, *args], capture_output=True, text=True, timeout=300, check=False
    )


def test_help_lists_copier_subcommands(console_script):
    result = run(console_script, "--help")

    assert result.returncode == 0
    for subcommand in ("copy", "update", "recopy", "check-update"):
        assert subcommand in result.stdout


def test_defaults_renders_without_a_tui(console_script, reference_template, tmp_path):
    src, ref = reference_template
    dst = tmp_path / "proj"

    # stdout is a pipe here: without --defaults falling through to copier the TUI path
    # would refuse for want of a terminal and return 1
    result = run(
        console_script,
        "copy",
        "--defaults",
        "--trust",
        "--vcs-ref",
        ref,
        "--data",
        "git_init=No",
        src,
        str(dst),
    )

    assert result.returncode == 0, result.stderr
    assert (dst / "Makefile").is_file()


def test_unknown_flag_is_refused(console_script):
    # plumbum rejects the switch before any argument is read, in copier's own wording
    result = run(console_script, "copy", "--no-such-flag")

    assert result.returncode == 2
    assert "Unknown switch --no-such-flag" in result.stdout
