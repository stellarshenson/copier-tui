"""Render criteria: copier is called with the answers, and refuses an invalid state."""

from __future__ import annotations

from pathlib import Path

import copier._main as copier_main
import pytest
from ui_support import FIXTURES, load

from copier_ui import CopierUIError, RenderRefusedError
from copier_ui.engine import supplied_answers


def test_render_hands_the_answers_to_copier_as_data(tmp_path: Path) -> None:
    """Render: run_copy receives data=answers, so nothing is prompted and the answer lands."""
    dst = tmp_path / "dst"
    with load("ui_deps", dst) as ui:
        ui.set("project", "written")
        ui.render(quiet=True)
    assert (dst / "out.txt").read_text().strip() == "written"


def test_render_accepts_an_explicit_destination_and_copier_kwargs(tmp_path: Path) -> None:
    """Render: the destination argument and copier keyword arguments both reach copier."""
    dst = tmp_path / "elsewhere"
    with load("ui_deps", tmp_path / "dst") as ui:
        ui.render(dst, quiet=True, pretend=True)
    assert not dst.exists()


def test_render_refuses_an_invalid_state_and_names_the_fields(tmp_path: Path) -> None:
    """Edge: render with an invalid state - refused, offending fields named, nothing written."""
    dst = tmp_path / "dst"
    with load("ui_deps", dst) as ui:
        ui.set("use_docker", True)
        ui.set("port", 80)
        with pytest.raises(RenderRefusedError) as caught:
            ui.render(quiet=True)
    assert list(caught.value.errors) == ["port"]
    assert "port" in str(caught.value)
    assert not dst.exists()


@pytest.mark.parametrize(("reply", "left"), [(True, "written"), (False, "mine")])
def test_a_file_that_differs_is_asked_about_through_the_caller(
    tmp_path: Path, reply: bool, left: str
) -> None:
    """Render: copier's `Overwrite <path>?` goes to `confirm`, and its answer is the answer.

    copier asks through questionary, which reads the terminal itself. A frontend that draws
    on that terminal is already reading it: the question was written where nobody could see
    it, and the render waited on an answer that could not arrive.
    """
    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / "out.txt").write_text("mine\n")
    asked: list[str] = []

    def confirm(question: str) -> bool:
        asked.append(question)
        return reply

    with load("ui_deps", dst) as ui:
        ui.set("project", "written")
        ui.render(quiet=True, confirm=confirm)
    assert asked == ["Overwrite out.txt?"]
    assert (dst / "out.txt").read_text().strip() == left


def test_copiers_own_question_is_back_in_place_after_the_render(tmp_path: Path) -> None:
    """Render: the question is routed for one run only, a failed run included.

    The route is a name replaced inside copier, and this process may go on to call copier
    without a frontend - a name left replaced would send that run's question to a screen
    that has closed.
    """
    before = copier_main.confirm
    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / "out.txt").write_text("mine\n")

    def confirm(question: str) -> bool:
        raise RuntimeError(question)

    with load("ui_deps", dst) as ui, pytest.raises(RuntimeError, match="Overwrite out.txt"):
        ui.render(quiet=True, confirm=confirm)
    assert copier_main.confirm is before


def test_a_question_copier_asks_mid_run_stops_the_render_and_is_named(tmp_path: Path) -> None:
    """Render: with a frontend answering, copier's own question prompt ends the run by name.

    copier's question prompt runs on the terminal. A frontend drawing there cannot let that
    prompt run: it reads the keys the frontend reads, behind the screen, and the render waited
    on it with no key that left. A render takes copier's defaults, so copier prompts only for
    a question named by `ask`, whatever the data holds.
    """
    before = copier_main.unsafe_prompt
    with load("ui_deps", tmp_path / "dst") as ui, pytest.raises(CopierUIError, match="`project`"):
        ui.render(quiet=True, confirm=lambda question: True, ask=("project",))
    assert copier_main.unsafe_prompt is before


def test_a_value_given_as_data_for_a_question_never_asked_reaches_copier(tmp_path: Path) -> None:
    """Render: `-d ver=9` for a `when: false` question is written, as copier writes it.

    copier takes a data answer for a question it never asks. Only the answers of visible
    questions were passed on, so the 9 stayed in the survey and the project got the default.
    """
    dst = tmp_path / "dst"
    with load("ui_supplied", dst, data={"ver": "9"}) as ui:
        ui.render(quiet=True, confirm=lambda question: True)
    assert (dst / "out.txt").read_text().split()[:2] == ["demo", "9"]


def test_an_untouched_default_is_left_for_copier_to_work_out(tmp_path: Path) -> None:
    """Render: a default nobody changed is not passed on as an answer.

    `release` defaults to the text 3.10. Passed to copier as data it was read a second time
    and became the number 3.1, and `legacy`, hidden in the survey, was asked for by copier.
    """
    dst = tmp_path / "dst"
    with load("ui_supplied", dst) as ui:
        assert "legacy" not in ui.state().visible_ids
        ui.render(quiet=True, confirm=lambda question: True)
    assert (dst / "out.txt").read_text().split()[2] == "3.10"


def test_an_answer_that_was_given_is_still_passed_on(tmp_path: Path) -> None:
    """Render: what the user answered on a visible question is the answer copier gets."""
    dst = tmp_path / "dst"
    with load("ui_supplied", dst) as ui:
        ui.set("name", "typed")
        ui.set("release", "'3.11'")
        ui.render(quiet=True, confirm=lambda question: True)
    assert (dst / "out.txt").read_text().split() == ["typed", "1", "3.11", "public"]


def test_a_blank_answer_to_a_question_with_no_default_is_passed_on(tmp_path: Path) -> None:
    """Render: a question that has no default and was left blank renders, with no value.

    copier has no default to work out for it, and told to take its defaults it stops with
    `Question "remark" is required`. Its own prompt records a blank there as no value, so
    that is what it is handed. A blank on a `str` or `int` question is refused on its row.
    """
    dst = tmp_path / "dst"
    with load("ui_supplied", dst) as ui:
        assert ui.state().fields["remark"].value is None
        assert ui.validate() == {}
        ui.render(quiet=True, confirm=lambda question: True)
    assert (dst / "out.txt").read_text().split() == ["demo", "1", "3.10", "public"]


def test_a_default_the_form_works_out_as_nothing_is_still_left_to_copier(tmp_path: Path) -> None:
    """Render: a question that has a default is not handed over because its value is None.

    `conf` defaults to `seed`, a name that is no question, and with no data giving it the
    default is nothing. Having a value of None was taken to mean having no default, so the
    None was handed over as an answer, and where copier worked the default out as a list it
    replaced the list.
    """
    with load("ui_seeded", tmp_path / "blank") as ui:
        assert ui.state().fields["conf"].value is None
        assert supplied_answers(ui.state()) == {}
    dst = tmp_path / "dst"
    with load("ui_seeded", dst, data={"seed": "[1, 2]"}) as ui:
        ui.render(quiet=True, confirm=lambda question: True)
    assert (dst / "out.txt").read_text().strip() == "[1, 2]|x"


def test_data_that_is_no_questions_answer_renders_what_copier_renders(tmp_path: Path) -> None:
    """Render: with `-d seed=5` the project holds what plain copier writes from that data.

    `seed` is no question, and a default, a `when` and a validator of the template read it.
    The survey kept such data for the render alone and evaluated without it, so the row of
    `conf` was refused and nothing was rendered.
    """
    written = []
    for name in ("form", "plain"):
        dst = tmp_path / name
        dst.mkdir()
        (dst / "parent.yml").write_text("owner: abc\n")
        written.append(dst / "out.txt")
    with load("ui_sources", tmp_path / "form", data={"seed": 5}) as ui:
        ui.render(quiet=True, confirm=lambda question: True)
    copier_main.run_copy(
        str(FIXTURES / "ui_sources"), tmp_path / "plain", {"seed": 5}, defaults=True, quiet=True
    )
    assert written[0].read_text() == written[1].read_text() == "5|d|2|abc\n"
