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
FIELD_FOCUS_FG = "#e8e8e8"
"""The ground under anything the user types into, per band, and lifted again under focus.

Only typing surfaces get one: an option row says "pick me" with its chips, and a typing
ground there invites the reader to type into a widget that ignores every letter. The ground
carries the band as well, because a control spans the row and would otherwise paint over the
stripe - five text questions in a row merged into one lit block."""

OPTION_BG = "#363e49"
OPTION_FG = "#b8b8b8"
CURSOR_BG = "#5a6674"
CURSOR_FG = "#ffffff"
"""The three states an option can be in, each with its own ground and ink.

Every option carries a ground, not just the answer. A bare label among chips reads as prose,
and prose beside chips reads as another option - the question's own caption ended up looking
like one of its answers.

The states are read in one glance: the answer is a filled cyan chip, the option the cursor is
on is the brightest neutral, and the rest sit back a step while staying fully legible. Nothing
here is dimmed to the point of hiding, and all three clear the 4.5:1 contrast floor - the
options passed over are the alternatives the reader is deciding against, so they have to stay
readable to be worth showing at all."""

PICKED_BG = CYAN
PICKED_FG = "#10161c"
"""The chip under the option in force. Colour alone separated taken from passed-over only for
a reader who already knew which hue meant which; a filled chip needs no key."""

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
}}
FieldRow.row-alt > .field-head > Input,
FieldRow.row-alt > .field-head > TextArea {{
    background: {FIELD_ALT_BG};
}}
FieldRow:focus-within > .field-head > Input,
FieldRow:focus-within > .field-head > TextArea {{
    background: {FIELD_FOCUS_BG};
    color: {FIELD_FOCUS_FG};
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
