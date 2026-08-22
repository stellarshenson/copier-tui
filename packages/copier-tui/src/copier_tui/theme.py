"""Duoptimum palette and shared CSS, per the text-user-interface conventions."""

from __future__ import annotations

CYAN = "#21a8e4"
CYAN_BRIGHT = "#46bcf0"
ORANGE = "#da8230"
AMBER = "#e6c660"
MINT = "#3fb950"
ROSE = "#ef4444"

SCREEN_BG = "#1a1f25"
CHROME_BG = "#2a313a"
SURFACE_BG = "#303841"
BORDER = "#404b54"

TEXT = "#c3c3c3"
TEXT_MUTED = "#a5a5a5"
TEXT_SUBTLE = "#7d8791"

MIN_WIDTH = 60
MIN_HEIGHT = 18

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
Input, TextArea, Select, SelectionList, OptionList {{
    background: {SURFACE_BG};
    color: {TEXT};
    border: tall {BORDER};
}}
Input:focus, TextArea:focus, Select:focus, SelectionList:focus, OptionList:focus {{
    border: tall {CYAN};
}}
Select > SelectCurrent {{
    background: {SURFACE_BG};
    border: tall {BORDER};
}}
Switch {{
    background: {SURFACE_BG};
    border: tall {BORDER};
}}
Switch:focus {{
    border: tall {CYAN};
}}
Switch.-on > .switch--slider {{
    color: {ORANGE};
}}
#resize-prompt, #warn-box, #banner-box {{
    layer: overlay;
    width: auto;
    height: auto;
    padding: 1 2;
    background: {CHROME_BG};
    color: {TEXT};
    border: heavy {ROSE};
}}
#warn-box, #banner-box {{
    display: none;
}}
"""
"""Screen background, chrome panels and the cyan focus ring, shared by every screen."""
