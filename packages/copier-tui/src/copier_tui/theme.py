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

LABEL_WIDTH = 26
"""Width of the label gutter, so every control on the form starts in the same column."""

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
