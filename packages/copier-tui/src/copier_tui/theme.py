"""Duoptimum palette, the Textual theme and shared CSS, per the text-user-interface skill."""

from __future__ import annotations

from textual.theme import Theme

CYAN = "#21a8e4"
CYAN_BRIGHT = "#46bcf0"
ORANGE = "#da8230"
AMBER = "#e6c660"
MINT = "#3fb950"
ROSE = "#f2554f"
ERROR_FG = "#f6736d"

"""The failure colour, and the lighter rose an error takes as body text.

`ROSE` is the theme's error token and the render's failure verdict, both of which sit on the
screen ground. An error message sits on a ROW ground, and on the alternate band `ROSE` measures
4.38:1 - under the floor this palette is asserted against, and it only started landing there
when errors began printing on rows the cursor is not on. `ERROR_FG` clears 4.99:1 on all six
row grounds and is still unmistakably rose."""

SCREEN_BG = "#1a1f25"
BASE_BG = "#252b32"
CHROME_BG = "#2a313a"
SURFACE_BG = "#303841"
BORDER = "#5f6b76"

PULSE_SHADES = (
    "#46bcf0",
    "#46bbef",
    "#44b9ed",
    "#43b6e9",
    "#40b2e4",
    "#3dadde",
    "#3aa7d8",
    "#36a1d0",
    "#329ac8",
    "#2e93c1",
    "#2a8db9",
    "#2787b3",
    "#2482ad",
    "#217ea8",
    "#207ba4",
    "#1e79a2",
    "#1e78a1",
)
PULSE_CYCLE = (
    0,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    15,
    14,
    13,
    12,
    11,
    10,
    9,
    8,
    7,
    6,
    5,
    4,
    3,
    2,
    1,
)
PULSE_INTERVAL = 0.06
"""The bar beside the focused question breathes down this ramp and back.

32 phases at 17 a second, so the cycle takes about two seconds and no step moves a channel
more than 10 of 255 - a breath rather than a sequence of shades, which is what four shades a
third of a second apart actually looked like. The phases are spaced on a cosine, so the bar
eases through the turnarounds instead of reversing on the spot, and that easing is why the
ramp holds fewer colours than phases - it dwells at the two ends. The dimmest shade still
carries the bar against the row, so the mark never disappears mid-cycle - and that is now a
measured claim rather than an assertion. The ramp used to reach `#12648b`, which is 2.50:1 on
the focused ground and 2.34:1 on a conditional one: four shades of seventeen fell under the
3:1 floor for a graphical indicator, and the cosine spacing dwells at the ends, so the mark
spent about a fifth of every cycle below it. The dark end is `#1e78a1`, the darkest that
clears 3:1 on both grounds - the cycle keeps its shape and loses a little amplitude."""

ROW_BG = SCREEN_BG
ROW_ALT_BG = "#22282f"
ROW_FOCUS_BG = "#1a202d"
"""The two bands the form alternates between, and the one ground under the cursor.

The focused row leans about eight parts of blue away from the first band and nothing else. It
is deliberately almost nothing: the row already carries a breathing bar, a blank line above
and below, and a lit caption, so a fourth cue loud enough to notice on its own would be the
fourth thing shouting. This one is only meant to be there when the reader looks for where
they are, and it stays far enough from the other band that a focused row is never mistaken
for a banded one.

One ground, not one per band. The plate under the cursor used to inherit the banding, so
walking the form with the arrows made the lifted row flicker between two shades - the one
thing on screen the reader is watching, changing colour on every press for a reason that has
nothing to do with the question they landed on. The row the cursor is on now looks the same
wherever it is, and the banding goes on doing its counting job around it.

A form of thirty near-identical rows gives the eye nothing to count by, and a caption that
wraps onto a second line is indistinguishable from the next question starting. The step is
8-10 per channel. It was 16-21, which read as two different surfaces rather than one form
counted in twos - the banding stopped being a rule under the questions and became a thing to
look at. Half of it still separates two adjacent rows at a glance, which is the whole job."""

ROW_COND_BG = "#1a271f"
ROW_ALT_COND_BG = "#223029"
ROW_COND_FOCUS_BG = "#1a2827"
"""Each band again, for a question another answer decides whether to ask, and the one ground
such a question gets under the cursor.

Green rather than more blue, because the cursor already owns the blue lean and two tints of
the same hue a few parts apart are one tint the reader cannot place. Green is raised 8 and
blue dropped 6, so the lean is a hue and not a brightness - the ground gains under half a
percent of luminance, and a caption on it still measures 8.80:1 and 6.87:1.

The same 8 and 6 lean the typing ground on a conditional row - `FIELD_COND_BG` and
`FIELD_ALT_COND_BG` beside the grounds below - since a control spans the row and a ground
that stayed neutral would cut the tint in half across the widest part of the question.

A conditional row indents its caption as well, because a tint this small is not worth
carrying a meaning on its own.

The tint survives the cursor. `ROW_COND_FOCUS_BG` is the focused ground leaned by the same 8
and 6, so a conditional question keeps saying it is conditional at the moment the reader is
actually reading it - which is the moment the fact matters most, since that is when they are
about to answer the thing that governs it. It is the only ground the cursor's plate takes,
and the plate is otherwise the same on every row.
"""

FIELD_BG = "#39424d"
FIELD_ALT_BG = "#3f4854"
FIELD_FOCUS_BG = "#495362"
FIELD_COND_BG = "#394a47"
FIELD_ALT_COND_BG = "#3f504e"
FIELD_COND_FOCUS_BG = "#445658"
ANSWER_FG = "#dcdcdc"
ANSWER_FOCUS_FG = "#ffb866"
"""The ground under anything the user types into, per band, and lifted again under focus.

Only typing surfaces get one: an option row says "pick me" with its chips, and a typing
ground there invites the reader to type into a widget that ignores every letter. The ground
carries the band as well, because a control spans the row and would otherwise paint over the
stripe - five text questions in a row merged into one lit block.

An answer already given is written in a plain grey brighter than the captions around it, and
the answer being edited in orange: on a form this long the question text and the answers to
it are the two things most worth telling apart at a glance, and only one cell is being typed
into at a time. The grey stays neutral because a tint on thirty settled answers reads as a
warning about all of them; the orange is as saturated as the focused ground allows, since a
hue that far from yellow cannot go deeper and still clear the floor on it. 7.43:1 and
4.56:1 on their grounds.

`FIELD_COND_FOCUS_BG` is the one ground that does not take the flat 8-green/6-blue lean the
conditional rule states. That value is `#495b5c`, and the orange answer measures 4.19:1 on it -
under the floor, on the single most important text in the app, on the row it is being typed
into. This one is darkened instead, to 4.53:1, which costs about two percent of luminance and
keeps the lean reading green. The contrast test asserts every one of these pairs, so the
exception cannot quietly become the rule again."""

OPTION_BG = "#363e49"
OPTION_FG = "#b8b8b8"
CURSOR_BG = "#9aa4b0"
CURSOR_FG = SCREEN_BG
CURSOR_PICKED_BG = "#5cc8f5"
CURSOR_PICKED_FG = SCREEN_BG
"""The three states an option can be in, each with its own ground and ink.

Every option carries a ground, not just the answer. A bare label among chips reads as prose,
and prose beside chips reads as another option - the question's own caption ended up looking
like one of its answers.

Two questions are being answered at once and they are given separate channels, because they
can hold at the same time and regularly do - the cursor starts on the answer every time. Hue
says which option is chosen, cyan against neutral, and the shape says it a second time, filled
against empty. Inversion says where the cursor is: under it the ground goes bright and the ink
goes dark, on the answer and on an alternative alike.

Inverting is what the earlier reading of this got wrong. A ground bright enough to read on its
own cannot hold white text - true, and the conclusion drawn from it was to keep the ground
dim, which left the cursor's chip one shade off the chosen chip at 1.32:1 and the reader
unable to say where the cursor was. The conclusion that follows from it is to turn the ink
over instead. These grounds clear 3:1 against the chips they must be told apart from - 3.36:1
on the answer and 4.28:1 on an alternative - and carry dark ink at better than 6.5:1.

The mark still sits outside the chip on the dark row rather than inside it, because a coloured
mark inside has only the chip to contrast against, where amber managed 2.91:1.

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

LABEL_LINES = 3
"""Lines a wrapped caption may take.

Three, not two. Two was sized against a gutter fixed at `LABEL_WIDTH`, and the gutter is a
share of the row now - so at 80 columns two of the reference template's questions lost the end
of their sentence, at 70 four did and at 60 seven, with no ellipsis and nowhere else to read
them. Three covers every one of them at every supported width, and costs a row only on the
captions that need it, since a row is `height: auto`."""

HELP_LINES = 2
"""Lines the focused row gives its help. Two holds about 90 characters at this gutter."""

VALUE_LINES = 3
"""Lines a free-text answer may wrap onto before it scrolls.

The value column is what the gutter leaves, about 40 columns at 100, so a one-sentence
project description needs three of them. Three is what the reference template's longest
demo answer takes; a fourth would cost a row on every long field to catch an outlier."""


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
    height: 1;
    padding: 0 1;
    color: {CYAN_BRIGHT};
    text-style: bold;
    /* the bar is one row, so a title that wraps loses every line but the first - and the
       first ends at the last space it fitted, which took the whole destination off the
       review screen at 80 columns and left a dangling separator. Crop, never wrap. */
    text-wrap: nowrap;
    text-overflow: ellipsis;
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
    align: center middle;
}}
Footer {{
    background: {CHROME_BG};
    color: {TEXT_MUTED};
}}
Input, TextArea {{
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
FieldRow.row-cond > .field-head > Input,
FieldRow.row-cond > .field-head > TextArea {{
    background: {FIELD_COND_BG};
}}
FieldRow.row-alt.row-cond > .field-head > Input,
FieldRow.row-alt.row-cond > .field-head > TextArea {{
    background: {FIELD_ALT_COND_BG};
}}
FieldRow:focus-within > .field-head > Input,
FieldRow:focus-within > .field-head > TextArea {{
    background: {FIELD_FOCUS_BG};
    color: {ANSWER_FOCUS_FG};
}}
/* the typing ground follows the plate: one colour under the cursor whatever band the row is
   in, and the conditional lean carried through so a green row stays green while it is read.
   Only the conditional case needs restating - `.row-cond` matches as strongly as
   `:focus-within` and is written first, so it would otherwise keep its unfocused ground. The
   banded case falls through correctly on source order; the rule restating it was measured and
   found to change nothing. */
FieldRow.row-cond:focus-within > .field-head > Input,
FieldRow.row-cond:focus-within > .field-head > TextArea {{
    background: {FIELD_COND_FOCUS_BG};
}}
FieldRow > .field-head > Input:disabled,
FieldRow > .field-head > TextArea:disabled {{
    background: transparent;
    color: {TEXT_SUBTLE};
}}
Input:focus, TextArea:focus {{
    background: {SURFACE_BG};
    color: {CYAN_BRIGHT};
    text-style: bold;
}}
#resize-prompt {{
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
    color: {AMBER};
    text-wrap: nowrap;
    text-overflow: ellipsis;
}}
"""
"""Screen background, chrome panels and the flat compact controls, shared by every screen."""
