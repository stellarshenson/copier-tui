"""Kind to widget mapping, control round-trips and secret masking.

A Textual control needs a running app to hold a value, so the controls are read from a real
survey over the one-question-per-kind template.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from textual.widgets import Input, Select, SelectionList, Switch, TextArea

from copier_tui.app import SurveyApp
from copier_tui.widgets import (
    WIDGET_BY_KIND,
    ChoiceSelect,
    ChoiceSelectionList,
    FieldRow,
    display_value,
    read_control,
)
from copier_ui import Kind, TemplateUI

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

WIDGET_FOR_QUESTION = [
    ("text", Kind.STRING, Input),
    ("where", Kind.PATH, Input),
    ("count", Kind.INTEGER, Input),
    ("ratio", Kind.FLOAT, Input),
    ("enabled", Kind.BOOL, Switch),
    ("config", Kind.STRUCTURED, TextArea),
    ("flavour", Kind.CHOICE, ChoiceSelect),
    ("extras", Kind.MULTISELECT, ChoiceSelectionList),
    ("token", Kind.SECRET, Input),
]
"""One question of every kind, and the widget the README table gives it."""


@pytest.fixture(scope="module")
def kinds_ui(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TemplateUI]:
    """The one-question-per-kind template, loaded once without a display."""
    dst = tmp_path_factory.mktemp("kinds") / "out"
    with TemplateUI.from_template(str(FIXTURES / "tui_kinds"), dst=dst) as ui:
        yield ui


@pytest.fixture
async def survey(tmp_path: Path) -> AsyncIterator[SurveyApp]:
    """A running survey over the kinds template, with every control mounted."""
    dst = tmp_path / "out"
    with TemplateUI.from_template(str(FIXTURES / "tui_kinds"), dst=dst) as ui:
        app = SurveyApp(ui, dst, {})
        async with app.run_test(size=(100, 60)) as pilot:
            await pilot.pause()
            yield app


def row(app: SurveyApp, field_id: str) -> FieldRow:
    """The mounted row for one question."""
    return app.screen.query_one(f"#row-{field_id}", FieldRow)


def control(app: SurveyApp, field_id: str) -> Any:
    """The mounted control for one question."""
    return app.screen.query_one(f"#ctl-{field_id}")


def test_widget_by_kind_is_the_documented_table() -> None:
    """Every kind maps to the widget the README table names."""
    assert WIDGET_BY_KIND == {
        Kind.STRING: Input,
        Kind.PATH: Input,
        Kind.SECRET: Input,
        Kind.INTEGER: Input,
        Kind.FLOAT: Input,
        Kind.BOOL: Switch,
        Kind.CHOICE: ChoiceSelect,
        Kind.MULTISELECT: ChoiceSelectionList,
        Kind.STRUCTURED: TextArea,
    }
    assert set(WIDGET_BY_KIND) == set(Kind)
    assert issubclass(ChoiceSelect, Select)
    assert issubclass(ChoiceSelectionList, SelectionList)


def test_the_fixture_covers_every_kind(kinds_ui: TemplateUI) -> None:
    """The questions below really are one of each kind, as the table claims."""
    schema = kinds_ui.schema()
    for field_id, kind, _ in WIDGET_FOR_QUESTION:
        assert schema.by_id(field_id).kind is kind
    assert {kind for _, kind, _ in WIDGET_FOR_QUESTION} == set(Kind)


async def test_every_kind_gets_its_widget(survey: SurveyApp) -> None:
    """The survey shows each question through the widget its kind maps to."""
    for field_id, _, widget in WIDGET_FOR_QUESTION:
        assert isinstance(control(survey, field_id), widget), field_id


async def test_numeric_inputs_are_numeric(survey: SurveyApp) -> None:
    """integer and float get an Input restricted to their type; a string does not."""
    assert control(survey, "count").type == "integer"
    assert control(survey, "ratio").type == "number"
    assert control(survey, "text").type == "text"


async def test_secret_is_a_password_input(survey: SurveyApp) -> None:
    """A secret question is masked on screen; an ordinary string is not."""
    assert control(survey, "token").password is True
    assert control(survey, "text").password is False


async def test_a_secret_choice_stays_masked(survey: SurveyApp, kinds_ui: TemplateUI) -> None:
    """secret wins over choice: no select may put the value on screen in the clear."""
    question = kinds_ui.schema().by_id("secret_pick")
    assert question.secret and question.kind is Kind.CHOICE
    masked = control(survey, "secret_pick")
    assert isinstance(masked, Input)
    assert masked.password is True


async def test_multiline_string_is_an_editor(survey: SurveyApp) -> None:
    """A multiline question gets the editor, whatever its type says."""
    assert isinstance(control(survey, "notes"), TextArea)


async def test_controls_open_on_their_default(survey: SurveyApp) -> None:
    """Every field opens prefilled: the user confirms rather than retypes."""
    assert control(survey, "text").value == "demo"
    assert control(survey, "count").value == "3"
    assert control(survey, "ratio").value == "1.5"
    assert control(survey, "enabled").value is False
    assert control(survey, "notes").text == "line one"
    assert row(survey, "flavour").value == "a"


async def test_a_row_reads_back_what_its_control_holds(survey: SurveyApp) -> None:
    """FieldRow.value is the control's value, in copier's terms rather than the widget's."""
    for field_id, expected in [
        ("text", "demo"),
        ("count", "3"),
        ("enabled", False),
        ("config", "{}"),
        ("flavour", "a"),
        ("extras", []),
    ]:
        assert row(survey, field_id).value == expected, field_id


async def test_a_choice_reads_back_as_its_copier_value(survey: SurveyApp) -> None:
    """The select carries indices; reading it returns the copier value again."""
    question = survey.ui.schema().by_id("flavour")
    select = control(survey, "flavour")
    select.value = 1
    assert read_control(question, select) == "b"
    select.value = Select.NULL
    assert read_control(question, select) is None


async def test_a_multiselect_reads_back_as_a_list(survey: SurveyApp) -> None:
    """Selecting options yields the chosen copier values in choice order."""
    question = survey.ui.schema().by_id("extras")
    selection = control(survey, "extras")
    selection.select(1)
    assert read_control(question, selection) == ["y"]
    selection.select(0)
    assert read_control(question, selection) == ["x", "y"]


def test_display_value_masks_a_secret(kinds_ui: TemplateUI) -> None:
    """Review and overview lines never carry a secret value."""
    state = kinds_ui.state()
    assert state.fields["token"].value == "s3cret"
    assert display_value(state.fields["token"]) == "***"
    assert display_value(state.fields["text"]) == "demo"


def test_change_message_repr_omits_the_value() -> None:
    """A change message reaches the log; its value must not."""
    message = FieldRow.Changed("token", "s3cret")
    assert "s3cret" not in repr(message)
    assert "token" in repr(message)


def test_state_dump_omits_secret_values(kinds_ui: TemplateUI) -> None:
    """A serialised state - the kind of thing a crash dump carries - holds no secret."""
    assert "s3cret" not in repr(kinds_ui.state().to_dict())
    assert "s3cret" not in repr(kinds_ui.state().fields["token"])
