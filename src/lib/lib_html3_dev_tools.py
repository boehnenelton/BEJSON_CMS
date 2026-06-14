"""
Library:      lib_html3_dev_tools.py
Family:       HTML3
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      3.0.0 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-29
Description:  Developer tools and debugging components for HTML3.
"""

import json
import html as html_mod
from typing import Dict, Any

VERSION = "3.0.0"
SCRIPT_NAME = "lib_html3_dev_tools.py"
RELATIONAL_ID = "6f7a8b9c-0d1e-2f3a-4b5c-6d7e8f9a0b1c"

def html_debug_bar(metadata: Dict[str, Any]) -> str:
    """
    Generates a fixed debug bar for the bottom of the screen.
    """
    items = ""
    for k, v in metadata.items():
        items += f"""
        <div style="border-right: 1px solid rgba(255,255,255,0.1); padding: 0 12px;">
            <span style="opacity:0.5; font-size:0.6rem; text-transform:uppercase;">{k}</span><br>
            <span style="font-weight:700;">{v}</span>
        </div>"""
        
    return f"""
    <div id="html3-debug-bar" style="position:fixed; bottom:0; left:0; width:100%; height:40px; background:#000; color:#fff; font-family:var(--font-mono); font-size:0.7rem; display:flex; align-items:center; z-index:10000; border-top:1px solid var(--primary); padding:0 12px; box-shadow:0 -2px 10px rgba(0,0,0,0.5);">
        <div style="color:var(--primary); font-weight:900; margin-right:20px;">HTML3 // DEBUG</div>
        {items}
        <button onclick="this.parentElement.style.display='none'" style="margin-left:auto; background:none; border:none; color:#fff; cursor:pointer; font-size:1.2rem;">&times;</button>
    </div>"""

def html_bejson_inspector(doc: Dict[str, Any]) -> str:
    """
    Generates an interactive JSON inspector for a BEJSON document.
    """
    pretty = json.dumps(doc, indent=2)
    from lib_html3_body import html_code_box
    return f"""
    <div class="c-card" style="border-style:dashed;">
        <h3 class="c-card__title">BEJSON INSPECTOR</h3>
        {html_code_box("Raw Document", pretty)}
    </div>"""
