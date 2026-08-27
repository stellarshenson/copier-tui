"""Kind to widget mapping, control round-trips and secret masking.

A Textual control needs a running app to hold a value, so the controls are read from a real
survey over the one-question-per-kind template.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input, TextArea

from copier_tui.app import SurveyApp
from copier_tui.inline import InlineOptions
from copier_tui.widgets import (
    WIDGET_BY_KIND,
    FieldRow,
    WrapInput,
    display_value,
    read_control,
)
from copier_ui import Choice, Kind, TemplateUI

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

WIDGET_FOR_QUESTION = [
    ("text", Kind.STRING, WrapInput),
    ("where", Kind.PATH, WrapInput),
    ("count", Kind.INTEGER, Input),
    ("ratio", Kind.FLOAT, Input),
    ("enabled", Kind.BOOL, InlineOptions),
    ("config", Kind.STRUCTURED, TextArea),
    ("flavour", Kind.CHOICE, InlineOptions),
    ("extras", Kind.MULTISELECT, InlineOptions),
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
        Kind.STRING: WrapInput,
        Kind.PATH: WrapInput,
        Kind.SECRET: Input,
        Kind.INTEGER: Input,
        Kind.FLOAT: Input,
        Kind.BOOL: InlineOptions,
        Kind.CHOICE: InlineOptions,
        Kind.MULTISELECT: InlineOptions,
        Kind.STRUCTURED: TextArea,
    }
    assert set(WIDGET_BY_KIND) == set(Kind)
    assert issubclass(WrapInput, TextArea)


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
    """integer and float get an Input restricted to their type.

    A string does not appear here: it is answered in a wrapping editor, which has no type
    restriction to assert because any character is a legal one.
    """
    assert control(survey, "count").type == "integer"
    assert control(survey, "ratio").type == "number"


async def test_secret_is_a_password_input(survey: SurveyApp) -> None:
    """A secret question is masked on screen; an ordinary string is written in the clear."""
    assert control(survey, "token").password is True
    assert control(survey, "text").text == "demo"


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
    assert control(survey, "text").text == "demo"
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
    """Moving along the options takes the one landed on, in copier's own terms."""
    question = survey.ui.schema().by_id("flavour")
    options = control(survey, "flavour")
    options.action_next()
    assert read_control(question, options) == "b"
    options.action_previous()
    assert read_control(question, options) == "a"


async def test_moving_stops_at_the_ends_instead_of_wrapping(survey: SurveyApp) -> None:
    """The first and last option are ends, not a ring - a run of keys cannot overshoot."""
    options = control(survey, "flavour")
    for _ in range(5):
        options.action_previous()
    assert options.value == "a"
    for _ in range(5):
        options.action_next()
    assert options.value == "b"


async def test_a_multiselect_reads_back_as_a_list(survey: SurveyApp) -> None:
    """Ticking options yields the chosen copier values in choice order."""
    question = survey.ui.schema().by_id("extras")
    options = control(survey, "extras")
    options.action_next()
    options.action_toggle()
    assert read_control(question, options) == ["y"]
    options.action_previous()
    options.action_toggle()
    assert read_control(question, options) == ["x", "y"]


async def test_a_boolean_is_offered_as_two_options(survey: SurveyApp) -> None:
    """A bool is a two-option question; both answers are named on the row."""
    options = control(survey, "enabled")
    assert [choice.label for choice in options.choices] == ["No", "Yes"]
    assert options.value is False
    options.action_next()
    assert options.value is True


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


STORAGE = [Choice(label=name, value=name) for name in ("none", "local", "s3", "azure", "gcs")]
"""Five options of a real template's making - they fit one line on a wide form and not on a
narrow one, which is the decision the row has to get right."""


class _OneRow(App[None]):
    """The smallest app that can give a control a real width."""

    def compose(self) -> ComposeResult:
        """Nothing but the options under test."""
        yield InlineOptions(STORAGE, "none", id="opts")


@asynccontextmanager
async def one_row(width: int) -> AsyncIterator[InlineOptions]:
    """The options mounted at a given terminal width, laid out and settled."""
    app = _OneRow()
    async with app.run_test(size=(width, 10)) as pilot:
        await pilot.pause()
        yield app.query_one("#opts", InlineOptions)


def lines(options: InlineOptions) -> int:
    """How many lines the options currently occupy."""
    return len(str(options.visual).splitlines())


async def test_options_are_never_painted_stacked_at_a_width_that_holds_them() -> None:
    """Every paint of a row wide enough for its options is one line, the first one included.

    Asserted over the paints rather than the result: the finished row reads the same either
    way, and what left the blank lines behind was a paint nobody was left looking at.
    """
    painted: list[int] = []
    original = InlineOptions._paint

    def record(self: InlineOptions) -> None:
        original(self)
        painted.append(lines(self))

    InlineOptions._paint = record
    try:
        async with one_row(120) as options:
            assert lines(options) == 1
    finally:
        InlineOptions._paint = original
    assert painted and max(painted) == 1, painted


async def test_options_stack_when_the_width_cannot_hold_them() -> None:
    """Narrow enough, they go one per line - an option that runs off the edge is an
    alternative the reader never learns about."""
    async with one_row(40) as options:
        assert lines(options) == len(STORAGE)
