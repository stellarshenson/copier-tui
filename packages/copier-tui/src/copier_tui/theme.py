"""Duoptimum palette, the Textual theme and shared CSS, per the text-user-interface skill."""

from __future__ import annotations

from textual.theme import Theme

CYAN = "#21a8e4"
CYAN_BRIGHT = "#46bcf0"
ORANGE = "#da8230"
AMBER = "#e6c660"
MINT = "#3fb950"
ROSE = "#f2554f"

SCREEN_BG = "#1a1f25"
BASE_BG = "#252b32"
CHROME_BG = "#2a313a"
SURFACE_BG = "#303841"
BORDER = "#5f6b76"

PULSE_SHADES = ("#46bcf0", "#2f9fd8", "#1b7fae", "#12648b")
PULSE_CYCLE = (0, 1, 2, 3, 2, 1)
PULSE_INTERVAL = 0.35
"""The bar beside the focused question breathes through these shades and back.

Six steps at a third of a second is a little over two seconds a cycle - slow enough to read as
breathing rather than blinking, which is the difference between an indicator and an alarm. The
dimmest shade still carries the bar against the row, so the mark never disappears mid-cycle."""

ROW_BG = SCREEN_BG
ROW_ALT_BG = "#2a313a"
"""The two bands the form alternates between.

A form of thirty near-identical rows gives the eye nothing to count by, and a caption that
wraps onto a second line is indistinguishable from the next question starting. The step is
16-21 per channel: the smaller one the skill's base token gives survives a 256-colour
terminal intact and still could not be seen, so the band is worth nothing until it is wide
enough to read at a glance."""

FIELD_BG = "#39424d"
FIELD_ALT_BG = "#3f4854"
FIELD_FOCUS_BG = "#495362"
ANSWER_FG = "#e3d9a8"
ANSWER_FOCUS_FG = "#ffc857"
"""The ground under anything the user types into, per band, and lifted again under focus.

Only typing surfaces get one: an option row says "pick me" with its chips, and a typing
ground there invites the reader to type into a widget that ignores every letter. The ground
carries the band as well, because a control spans the row and would otherwise paint over the
stripe - five text questions in a row merged into one lit block.

An answer is written in pale yellow and the answer being edited in a warm one, so the values
carry a colour of their own rather than the reading grey of the captions around them: on a
form this long the question text and the answers to it are the two things most worth telling
apart at a glance. Both clear the contrast floor on the ground they sit on, 7.16:1 and
5.06:1."""

OPTION_BG = "#363e49"
OPTION_FG = "#b8b8b8"
CURSOR_BG = "#5a6674"
CURSOR_FG = "#ffffff"
CURSOR_PICKED_BG = "#1477b4"
CURSOR_PICKED_FG = "#ffffff"
"""The three states an option can be in, each with its own ground and ink.

Every option carries a ground, not just the answer. A bare label among chips reads as prose,
and prose beside chips reads as another option - the question's own caption ended up looking
like one of its answers.

Two questions are being answered at once and they are given separate channels, because they
can hold at the same time and regularly do - the cursor starts on the answer every time. The
shape says which option is chosen, filled against empty; the answer keeps its blue ground and
white ink whether or not the cursor is on it.

The cursor is carried by three cues at once, because no single one was enough. An underline
was close to invisible. A ground bright enough to read on its own cannot hold white text - the
blues that clear 4.5:1 with white stop well short of striking. And a coloured mark inside the
chip has only the chip to contrast against, where amber manages 2.91:1. So the mark sits
outside the chip on the dark row instead, where a bright cyan caret has the whole row band to
read against, and the chip beneath it steps one shade brighter and goes bold.

Nothing is dimmed to the point of hiding, and every state clears the 4.5:1 contrast floor -
the options passed over are the alternatives the reader is deciding against, so they have to
stay readable to be worth showing at all."""

PICKED_BG = "#0b6591"
PICKED_FG = "#ffffff"
"""The chip under the option in force.

Deeper than the brand cyan so the label can be light: white on `#21a8e4` measures 2.70:1 and
white on this 6.39:1, and an answer written in dark ink on a bright chip reads as struck out
rather than chosen. It is still the only hue on the row, so the answer is still the only
option that is not a neutral."""

TEXT = "#c3c3c3"
TEXT_MUTED = "#a5a5a5"
TEXT_SUBTLE = "#939da7"

MIN_WIDTH = 60
MIN_HEIGHT = 18

LABEL_WIDTH = 56
"""Columns the caption gutter holds, padding included.

56 is the measured optimum against the reference template at 100 columns: it is the widest
gutter at which every choice question still prints all of its options on the same row, and
widening it further starts pushing option lines off the screen while saving only one more
wrapped caption. A caption longer than the gutter wraps rather than being cut, because the
part a cut removes is usually the example that says what to write."""

LABEL_LINES = 2
"""Lines a wrapped caption may take. Two covers every question in the reference template."""

HELP_LINES = 2
"""Lines the focused row gives its help. Two holds about 90 characters at this gutter."""

VALUE_LINES = 3
"""Lines a free-text answer may wrap onto before it scrolls.

The value column is what the gutter leaves, about 40 columns at 100, so a one-sentence
project description needs three of them. Three is what the reference template's longest
demo answer takes; a fourth would cost a row on every long field to catch an outlier."""
"""Cap on the label gutter, so every control on the form starts in the same column.

The survey gutter is a share of the terminal up to this; the review screen uses it flat.
Wide enough for most copier captions - a longer one is clipped and shown whole on the
survey's hint line, which is why a caption costs one column rather than one row.
"""

THEME = Theme(
    name="copier-tui",
    primary=CYAN,
    secondary=CYAN_BRIGHT,
    accent=ORANGE,
    warning=AMBER,
    error=ROSE,
    success=MINT,
    foreground=TEXT,
    background=SCREEN_BG,
    surface=SURFACE_BG,
    panel=CHROME_BG,
    dark=True,
    variables={
        "border": BORDER,
        "border-blurred": BORDER,
        "text-muted": TEXT_MUTED,
        "text-disabled": TEXT_SUBTLE,
        "footer-key-foreground": CYAN_BRIGHT,
        "footer-description-foreground": TEXT_MUTED,
        "input-selection-background": f"{CYAN} 35%",
    },
)
"""Registered on the app so Textual's own chrome - overlays, footer, cursors - uses the palette."""

HEADER_CSS = f"""
#app-header {{
    height: 1;
    background: {CHROME_BG};
    color: {TEXT};
}}
#hdr-title {{
    width: 1fr;
    padding: 0 1;
    color: {CYAN_BRIGHT};
    text-style: bold;
}}
#hdr-version {{
    width: auto;
    padding: 0 1;
    color: {TEXT_SUBTLE};
}}
"""
"""One-row header rules: #app-header, #hdr-title (width 1fr), #hdr-version (width auto)."""

BASE_CSS = f"""
Screen {{
    background: {SCREEN_BG};
    color: {TEXT};
    layers: base overlay;
    align: center middle;
}}
Footer {{
    background: {CHROME_BG};
    color: {TEXT_MUTED};
}}
Input, TextArea, SelectionList {{
    background: {SURFACE_BG};
    color: {TEXT};
    border: none;
    padding: 0 1;
}}
/* the form's own typing grounds. These live here rather than in FieldRow.DEFAULT_CSS
   because Textual ranks app CSS above a widget's default sheet whatever the specificity,
   so the generic rule above silently won and the row never got the ground it asked for. */
FieldRow > .field-head > Input,
FieldRow > .field-head > TextArea {{
    background: {FIELD_BG};
    color: {ANSWER_FG};
}}
FieldRow.row-alt > .field-head > Input,
FieldRow.row-alt > .field-head > TextArea {{
    background: {FIELD_ALT_BG};
}}
FieldRow:focus-within > .field-head > Input,
FieldRow:focus-within > .field-head > TextArea {{
    background: {FIELD_FOCUS_BG};
    color: {ANSWER_FOCUS_FG};
}}
FieldRow > .field-head > Input:disabled,
FieldRow > .field-head > TextArea:disabled {{
    background: transparent;
    color: {TEXT_SUBTLE};
}}
Select {{
    background: {SURFACE_BG};
    color: {TEXT};
    border: none;
    padding: 0;
}}
Input:focus, TextArea:focus, SelectionList:focus, Select:focus > SelectCurrent {{
    background: {SURFACE_BG};
    color: {CYAN_BRIGHT};
    text-style: bold;
}}
Select > SelectCurrent {{
    background: {SURFACE_BG};
    color: {TEXT};
    border: none;
    padding: 0 1;
}}
Select > SelectCurrent .down-arrow {{
    color: {TEXT_MUTED};
}}
Select > SelectOverlay {{
    background: {CHROME_BG};
    border: round {BORDER};
}}
Switch {{
    background: {SURFACE_BG};
    border: none;
    padding: 0;
    height: 1;
    width: 4;
}}
Switch > .switch--slider {{
    background: {SURFACE_BG};
    color: {BORDER};
}}
Switch.-on > .switch--slider {{
    color: {ORANGE};
}}
Switch:focus > .switch--slider {{
    background: {SURFACE_BG};
    color: {CYAN_BRIGHT};
}}
#resize-prompt {{
    layer: overlay;
    width: auto;
    height: auto;
    padding: 1 2;
    background: {CHROME_BG};
    color: {TEXT};
    border: heavy {ROSE};
}}
"""
"""Screen background, chrome panels and the flat compact controls, shared by every screen."""
