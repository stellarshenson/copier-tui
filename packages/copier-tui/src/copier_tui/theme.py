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
CHROME_BG = "#2a313a"
SURFACE_BG = "#303841"
BORDER = "#5f6b76"

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
