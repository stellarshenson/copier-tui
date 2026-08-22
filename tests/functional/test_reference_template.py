"""The reference template renders end to end through the installed `copier_ui`."""

from copier_ui import TemplateUI

ANSWERS = {
    "module_name": "widgets_lib",
    "author_name": "Functional Suite",
    "description": "reference template render",
    "github_actions": "Yes",
    "docker_support": "No",
    "git_init": "No",
}


def test_reference_template_renders(reference_template, tmp_path):
    src, ref = reference_template
    dst = tmp_path / "proj"

    with TemplateUI.from_template(src, vcs_ref=ref, dst=dst, unsafe=True) as ui:
        for question_id, value in ANSWERS.items():
            ui.set(question_id, value)
        assert ui.validate() == {}
        ui.render(dst, unsafe=True, quiet=True)

    assert (dst / "src" / "widgets_lib" / "dataset.py").is_file()
    assert (dst / "Makefile").is_file()
    # .github is rendered only for github_actions=Yes, docker/ only for docker_support=Yes
    assert (dst / ".github" / "workflows" / "tests.yml").is_file()
    assert not (dst / "docker").exists()


def test_conditional_question_follows_its_controlling_answer(reference_template, tmp_path):
    src, ref = reference_template

    with TemplateUI.from_template(src, vcs_ref=ref, dst=tmp_path / "proj", unsafe=True) as ui:
        assert "python_version_custom" not in ui.state().visible_ids
        ui.set("python_version_choice", "other")
        assert "python_version_custom" in ui.state().visible_ids
