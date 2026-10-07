"""Stellars-Tech palettes, the two Textual themes and the shared CSS, per the
text-user-interface skill.

There are two themes, `stellars-tech-dark` and `stellars-tech-light`. Textual switches its
CSS between a light and a dark theme only on its own setting and never asks the terminal, so
`background.pick_theme()` asks before the app starts and `apply()` registers both themes and
selects one. Every stylesheet colour is a `$st-<role>` variable, so the same rules serve both.
A Rich `Text` style is not CSS and cannot name a variable: it reads `color(app, role)`.

A role is a job, not a colour. `PALETTES` gives every role one value per theme, and the tests
hold each ink on each ground it is printed on to the same floor in both: 4.5:1 for text and
3:1 for a mark that is not text.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from textual.theme import Theme

if TYPE_CHECKING:
    from textual.app import App

_BASE: dict[str, dict[str, str]] = {
    "dark": {
        # the brand roles
        "screen": "#1a1f25",
        "chrome": "#2a313a",
        "surface": "#303841",
        "border": "#5f6b76",
        "text": "#c3c3c3",
        "muted": "#a5a5a5",
        "subtle": "#939da7",
        "cyan": "#21a8e4",
        "cyan-bright": "#46bcf0",
        "orange": "#da8230",
        "amber": "#e6c660",
        "mint": "#3fb950",
        "rose": "#f2554f",
        # an error message printed on a row, and the failure text in the banner and file list
        "error": "#f7847f",
        # the two bands, and each again on a conditional row
        "row": "#1a1f25",
        "row-alt": "#22282f",
        "row-cond": "#1a271f",
        "row-alt-cond": "#223029",
        # the ground under what the user types into, one per row ground
        "field": "#39424d",
        "field-alt": "#3f4854",
        "field-cond": "#394a47",
        "field-alt-cond": "#3f504e",
        "answer": "#dcdcdc",
        # an option passed over, and the option chosen
        "option": "#363e49",
        "option-ink": "#b8b8b8",
        "picked": "#0b6591",
        "picked-ink": "#ffffff",
    },
    "light": {
        "screen": "#f5f7fa",
        "chrome": "#eef1f5",
        "surface": "#ffffff",
        "border": "#7d8f9b",
        "text": "#1a3540",
        "muted": "#445d69",
        "subtle": "#576c76",
        "cyan": "#06709c",
        "cyan-bright": "#05607f",
        "orange": "#a45a18",
        "amber": "#996600",
        "mint": "#1a7d36",
        "rose": "#c04048",
        "error": "#9d343b",
        "row": "#f5f7fa",
        "row-alt": "#e8edf2",
        "row-cond": "#ebf9ee",
        "row-alt-cond": "#deefe6",
        "field": "#e3e7eb",
        "field-alt": "#d8dee4",
        "field-cond": "#dae9e0",
        "field-alt-cond": "#cee0d9",
        "answer": "#0b1f27",
        "option": "#dae1e9",
        "option-ink": "#33505c",
        "picked": "#4fb3e0",
        "picked-ink": "#06202d",
    },
}
"""Every role's colour in each theme, except the roles of the row under the cursor.

The brand roles are the Stellars-Tech palette, with these values moved off the brand token
because the token fails the floor where this app prints it as text. Dark: `subtle` is
`#939da7`, not `#7d8791`, and `border` is `#5f6b76`. Light: `muted`, `subtle`, `orange`,
`amber`, `mint` and `rose` are each a few parts darker than the token, and `border` is
`#7d8f9b`.

Rows. A form of thirty near-identical rows gives the eye nothing to count by, and a caption
that wraps onto a second line is indistinguishable from the next question starting, so the
form alternates two bands, `row` and `row-alt`. They are 1.12:1 apart in the dark theme and
1.10:1 in the light one: enough to separate two adjacent rows, and little enough that the
banding stays a rule under the questions.

Conditional rows. A question another answer decides whether to ask leans its ground green:
`row-cond` and `row-alt-cond`. A conditional ground is under 1.1:1 from the band it leans
from, so the lean is a hue and not a lightness.

Fields. Only what can be typed into has a field ground: an option row says "pick me" with
its chips, and a typing ground there invites typing into a widget that ignores every letter.
The ground carries the band and the green lean, because a control spans the row and a
neutral ground would cut the row's own ground in half across its widest part. An answer
already given is `answer`, a neutral a step stronger than the captions. In the dark theme a
field is lighter than its row; in the light theme it is a well a step darker.

Options. Every option carries a ground, not just the answer: a bare label among chips reads
as prose, and prose beside chips reads as another option. Hue says which option is chosen
and the filled shape says it a second time.

Errors. `rose` is the failure verdict and prints on the screen ground; it is also the border
of the failed banner, a mark. A message under a question prints on a row ground, and the
failure reason, the deleted and conflict counts and the conflicted paths print on the chrome
and surface grounds; `rose` fails the text floor on all of those, so they are `error`: at
least 4.5:1 on each.
"""

_CURRENT_ROW: dict[str, dict[str, str]] = {
    "dark": {
        "row-focus": "#303841",
        "row-cond-focus": "#2e3e39",
        "caption-focus": "#c3c3c3",
        "help-focus": "#a5a5a5",
        "error-focus": "#f7847f",
        "rail-focus": "#939da7",
        "bar": "#21a8e4",
        "field-focus": "#495362",
        "field-cond-focus": "#445658",
        "answer-focus": "#ffb866",
        "option-focus": "#444e5a",
        "option-focus-ink": "#c3c3c3",
        "picked-focus": "#0b6591",
        "picked-focus-ink": "#ffffff",
        "cursor": "#9aa4b0",
        "cursor-ink": "#1a1f25",
        "cursor-picked": "#5cc8f5",
        "cursor-picked-ink": "#1a1f25",
    },
    "light": {
        "row-focus": "#c8d4df",
        "row-cond-focus": "#bed6d3",
        "caption-focus": "#1a3540",
        "help-focus": "#445d69",
        "error-focus": "#9d343b",
        "rail-focus": "#576c76",
        "bar": "#06709c",
        "field-focus": "#ffffff",
        "field-cond-focus": "#ffffff",
        "answer-focus": "#a85c16",
        "option-focus": "#f5f7fa",
        "option-focus-ink": "#1a3540",
        "picked-focus": "#4fb3e0",
        "picked-focus-ink": "#06202d",
        "cursor": "#4f606d",
        "cursor-ink": "#ffffff",
        "cursor-picked": "#084d70",
        "cursor-picked-ink": "#ffffff",
    },
}
"""Everything drawn on the row under the cursor, as one dark row and one light row.

Each theme draws its current row from the OTHER set: the dark theme's current row is the
light one and the light theme's is the dark one. The current row is therefore the reverse of
the form around it - ground and ink both - and at least 9:1 from every band, where a row
that only lifted its ground stood 1.40:1 from them. That is what says where the cursor is,
because the row does not change size to say it.

One row, written once. Every ink in a set is measured on the grounds of the same set, so
the pairs hold whichever theme borrows them.

`row-focus` is one ground on either band, so walking the form does not make the current row
change shade. `row-cond-focus` is that ground leaned green, the same way and by about as
little as a conditional band leans, since the moment the reader is on the row is the moment
the fact matters most. The dark one is two parts darker than the flat lean `#30403b`, on
which the help measures 4.44:1.

The caption is `caption-focus`, the help under it `help-focus`, an error `error-focus` and
the tree connector `rail-focus`: each is the ink the other theme uses for the same job.

`field-focus` is the ground being typed into and `answer-focus` its orange ink, the one
hue-carrying text on the form. The dark `field-cond-focus` is darker than the flat lean
`#495b5c`, on which the orange measures 4.19:1.

Options on the current row have chips of their own, because the resting chip belongs to the
other polarity: `option-focus` for an option passed over and `picked-focus` for one chosen.
Under the cursor the chip takes the strongest ground of the row and the ink turns over, on
the answer (`cursor-picked`) and on an alternative (`cursor`) alike: dark with light ink on
the light row, bright with dark ink on the dark row. `cursor` is at least 3:1 from
`option-focus` and `cursor-picked` at least 3:1 from `picked-focus`, the floor for telling
two surfaces apart, and nothing else marks the option the cursor is on.
"""

_OTHER = {"dark": "light", "light": "dark"}

PALETTES: dict[str, dict[str, str]] = {
    mode: {**_BASE[mode], **_CURRENT_ROW[_OTHER[mode]]} for mode in _BASE
}
"""Every role's colour in each theme: the theme's own, and the other theme's current row."""

_PULSE_ENDS = {"dark": ("#46bcf0", "#2b8eba"), "light": ("#044a63", "#257e9d")}
"""The two ends of the bar's breath on a dark current row and on a light one: the strong
end, then the weak one.

The weak end is the one closest to the row's ground. It is the closest shade that still
clears 3:1 on both grounds of its row, the floor for a mark that is not text: 3.21:1 and
3.05:1 on the dark row, 3.06:1 and 3.02:1 on the light one. The cosine spacing dwells at
the ends, so a weak end under the floor leaves the bar below it for about a fifth of every
cycle."""

PULSE_STEPS = 17
"""Shades from one end of the breath to the other, both ends included."""


def _mix(start: str, end: str, share: float) -> str:
    """The colour `share` of the way from `start` to `end`, channel by channel."""
    pairs = ((int(start[i : i + 2], 16), int(end[i : i + 2], 16)) for i in (1, 3, 5))
    return "#" + "".join(f"{round(a + (b - a) * share):02x}" for a, b in pairs)


def pulse_shades(mode: str) -> tuple[str, ...]:
    """The bar's ramp in the theme `mode`, strong end first, spaced on a cosine.

    The cosine is why the bar eases through the turnarounds instead of reversing on the
    spot. No step moves a channel more than 10 of 255, so it reads as a breath rather than
    a sequence of shades.
    """
    # the bar is drawn on the current row, which is the other theme's
    strong, weak = _PULSE_ENDS[_OTHER[mode]]
    last = PULSE_STEPS - 1
    return tuple(
        _mix(strong, weak, (1 - math.cos(math.pi * step / last)) / 2)
        for step in range(PULSE_STEPS)
    )


PULSE_CYCLE = (*range(PULSE_STEPS), *range(PULSE_STEPS - 2, 0, -1))
"""The order the bar visits its shades in: down the ramp and back, each end once."""

PULSE_INTERVAL = 0.06
"""Seconds between two steps of the bar beside the current question.

32 phases at 17 a second, so the cycle takes about two seconds."""

MIN_WIDTH = 60
MIN_HEIGHT = 18

LABEL_WIDTH = 56
"""Columns the caption gutter holds, padding included.

56 is the measured optimum against the reference template at 100 columns: it is the widest
gutter at which every choice question still prints all of its options on the same row, and
widening it further starts pushing option lines off the screen while saving only one more
wrapped caption. A caption longer than the gutter wraps rather than being cut, because the
part a cut removes is usually the example that says what to write."""

LABEL_LINES = 3
"""Lines a wrapped caption may take.

Three, not two. Two was sized against a gutter fixed at `LABEL_WIDTH`, and the gutter is a
share of the row now - so at 80 columns two of the reference template's questions lost the end
of their sentence, at 70 four did and at 60 seven, with no ellipsis and nowhere else to read
them. Three covers every one of them at every supported width, and costs a row only on the
captions that need it, since a row is `height: auto`."""

HELP_LINES = 2
"""Lines the current row gives its help. Two holds about 90 characters at this gutter."""


def _theme(mode: str) -> Theme:
    """The Textual theme for one palette, carrying every role as a `$st-<role>` variable."""
    palette = PALETTES[mode]
    pulse = {f"st-pulse-{step}": shade for step, shade in enumerate(pulse_shades(mode))}
    return Theme(
        name=f"stellars-tech-{mode}",
        primary=palette["cyan"],
        secondary=palette["cyan-bright"],
        accent=palette["orange"],
        warning=palette["amber"],
        error=palette["rose"],
        success=palette["mint"],
        foreground=palette["text"],
        background=palette["screen"],
        surface=palette["surface"],
        panel=palette["chrome"],
        dark=mode == "dark",
        variables={
            # Textual's own chrome - overlays, footer, cursors - takes the palette too
            "border": palette["border"],
            "border-blurred": palette["border"],
            "text-muted": palette["muted"],
            "text-disabled": palette["subtle"],
            "footer-key-foreground": palette["cyan-bright"],
            "footer-description-foreground": palette["muted"],
            # left to Textual, the thumb and its track are derived from the primary and the
            # background and come out 2.06:1 dark and 1.72:1 light
            "scrollbar": palette["subtle"],
            "scrollbar-background": palette["chrome"],
            # prefixed so that no role shadows a Textual built-in ($surface, $border, $text)
            **{f"st-{role}": value for role, value in palette.items()},
            **pulse,
        },
    )


THEMES = {mode: _theme(mode) for mode in PALETTES}
"""Both themes, by mode. `apply()` registers the pair and selects one."""

DARK = THEMES["dark"].name
LIGHT = THEMES["light"].name


def apply(app: App, name: str) -> None:
    """Register both themes on `app` and select `name`.

    Call it in `__init__`, after `super().__init__()`. The stylesheet is parsed before
    `on_mount`, and a `$st-*` variable that is not defined by then fails the parse.

    Textual takes its starting theme from `TEXTUAL_THEME`, so with that variable naming one
    of the two the app is already set to `name` before the theme by that name exists.
    Assigning the same name again changes nothing, Textual does not recompute anything, and
    the stylesheet has no `$st-*` variable at all. The other theme is selected first so that
    selecting `name` is a change.
    """
    for theme in THEMES.values():
        app.register_theme(theme)
    if app.theme == name:
        app.theme = LIGHT if name == DARK else DARK
    app.theme = name


def color(app: App, role: str) -> str:
    """The hex a role has in the theme `app` is showing, for a Rich `Text` style."""
    return app.theme_variables[f"st-{role}"]


HEADER_CSS = """
#app-header {
    height: 1;
    background: $st-chrome;
    color: $st-text;
}
#hdr-title {
    width: 1fr;
    height: 1;
    padding: 0 1;
    /* the base ink only: the project and the field position carry the bright accent as
       segment styles, so a cell-wide colour here would flatten the two apart from the rest */
    color: $st-text;
    /* the bar is one row, so a title that wraps loses every line but the first - and the
       first ends at the last space it fitted, which took the whole destination off the
       review screen at 80 columns and left a dangling separator. Crop, never wrap. */
    text-wrap: nowrap;
    text-overflow: ellipsis;
}
#hdr-version {
    width: auto;
    padding: 0 1;
    color: $st-subtle;
}
"""
"""One-row header rules: #app-header, #hdr-title (width 1fr), #hdr-version (width auto)."""

BASE_CSS = """
Screen {
    background: $st-screen;
    color: $st-text;
    align: center middle;
}
Footer {
    background: $st-chrome;
    color: $st-muted;
}
Input, TextArea {
    background: $st-surface;
    color: $st-text;
    border: none;
    padding: 0 1;
}
/* the form's own typing grounds. These live here rather than in FieldRow.DEFAULT_CSS
   because Textual ranks app CSS above a widget's default sheet whatever the specificity,
   so the generic rule above silently won and the row never got the ground it asked for. */
FieldRow > .field-head > Input,
FieldRow > .field-head > TextArea {
    background: $st-field;
    color: $st-answer;
}
FieldRow.row-alt > .field-head > Input,
FieldRow.row-alt > .field-head > TextArea {
    background: $st-field-alt;
}
FieldRow.row-cond > .field-head > Input,
FieldRow.row-cond > .field-head > TextArea {
    background: $st-field-cond;
}
FieldRow.row-alt.row-cond > .field-head > Input,
FieldRow.row-alt.row-cond > .field-head > TextArea {
    background: $st-field-alt-cond;
}
FieldRow:focus-within > .field-head > Input,
FieldRow:focus-within > .field-head > TextArea {
    background: $st-field-focus;
    color: $st-answer-focus;
}
/* the typing ground follows the row: one colour under the cursor whatever band the row is
   in, and the conditional lean carried through so a green row stays green while it is read.
   Only the conditional case needs restating - `.row-cond` matches as strongly as
   `:focus-within` and is written first, so it would otherwise keep its unfocused ground. The
   banded case falls through correctly on source order; the rule restating it was measured and
   found to change nothing. */
FieldRow.row-cond:focus-within > .field-head > Input,
FieldRow.row-cond:focus-within > .field-head > TextArea {
    background: $st-field-cond-focus;
}
/* the caret and a selection are drawn on the field being typed into, and that field is on
   the row under the cursor, whose colours are the other theme's. Textual colours both from
   the theme's own foreground and background, which on that field is light on light in one
   theme and dark on dark in the other. The caret is a block in the answer's own ink; a
   selection is the pair the cursor's chip uses. */
FieldRow > .field-head > TextArea > .text-area--cursor,
FieldRow > .field-head > Input > .input--cursor {
    background: $st-answer-focus;
    color: $st-field-focus;
}
FieldRow > .field-head > TextArea > .text-area--selection,
FieldRow > .field-head > Input > .input--selection {
    background: $st-cursor;
    color: $st-cursor-ink;
}
FieldRow > .field-head > Input:disabled,
FieldRow > .field-head > TextArea:disabled {
    background: transparent;
    color: $st-subtle;
}
Input:focus, TextArea:focus {
    background: $st-surface;
    color: $st-cyan-bright;
    text-style: bold;
}
#resize-prompt {
    /* a strip above the footer, not a box in the middle. Centred it covered six rows of the
       form to say the terminal was one row too short - at its most expensive in exactly the
       case that summoned it. It stays non-modal: the form above it still works. */
    /* NOT on a layer, and not docked either - `SurveyApp._check_size` mounts it before the
       Footer so it is a row of the layout, and the form gives one up. Every earlier placement
       kept it over the screen and each one covered something: six rows of the form, then the
       footer where the keys are named, then the row above it - which carries the sentence
       saying a second escape discards every answer, and the one saying an existing project is
       about to be written into. Both bottom rows are load-bearing; there was never a row to
       take.

       Ink, not a fill. Filled amber across the whole width it was the loudest thing on screen
       and the least urgent - both real warnings are ink, so a fill outranked them, and this
       one is permanent where the cancel warning lives three seconds. */
    width: 100%;
    height: 1;
    padding: 0 1;
    text-align: center;
    /* amber, not rose: rose is this app's failure colour and a heavy rose border read as a
       crash dialog, where a terminal narrower than the form is an advisory the reader fixes by
       dragging an edge. The colour is carried by the strip itself and NOT by a border - a
       border is inside the declared height, so `height: 1` with one left the content box zero
       rows and the message was never drawn at all. Two amber lines saying nothing, over the
       footer they covered. */
    color: $st-amber;
    text-wrap: nowrap;
    text-overflow: ellipsis;
}
"""
"""Screen background, chrome panels and the flat compact controls, shared by every screen."""
