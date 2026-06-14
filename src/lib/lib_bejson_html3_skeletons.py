"""
Library:      lib_bejson_html3_skeletons.py
Family:       HTML3
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      3.0.1 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-29
Description:  Authoritative BECSS skeletal templates for HTML3.
              Implements Cascade Layers, OKLCH tokens, and BEM (c- prefix).
"""

import html as html_mod
import json

VERSION = "3.0.1"
SCRIPT_NAME = "lib_bejson_html3_skeletons.py"
RELATIONAL_ID = "c7d6b5a4-1f8a-4e8a-9d6c-5f4b5a6c7d8e"


# ═══════════════════════════════════════════════════════
# 1. AUTHORITATIVE DESIGN TOKENS (BECSS v2026)
# ═══════════════════════════════════════════════════════

COLOR = {
    "primary":         "#DE2626", # DE2626 Red fallback
    "primary_muted":   "rgba(222, 38, 38, 0.1)",
    "bg_page":         "#FFFFFF",
    "bg_alt":          "#F8F9FA",
    "bg_surface":      "#FFFFFF",
    "text_main":       "#1A1A1A",
    "text_muted":      "#6B7280",
    "border":          "#E5E7EB",
    "border_muted":    "#F3F4F6",
    "font_sans":       "'Inter', system-ui, -apple-system, sans-serif",
    "font_mono":       "'Roboto Mono', 'Source Code Pro', monospace",
    "sidebar_width":   "250px",
    "transition":      "all 0.2s ease",
    "shadow_sm":       "0 1px 3px rgba(0,0,0,0.05)",
    "radius":          "6px",
}

BRUTAL_COLOR = {
    "primary":         "#DE2626",
    "primary_muted":   "rgba(222, 38, 38, 0.2)",
    "bg_page":         "#FFFFFF",
    "bg_alt":          "#F3F4F6",
    "bg_surface":      "#FFFFFF",
    "text_main":       "#000000",
    "text_muted":      "#4B5563",
    "border":          "#000000",
    "border_muted":    "#000000",
    "font_sans":       "'Source Code Pro', monospace",
    "font_mono":       "'Source Code Pro', monospace",
    "sidebar_width":   "250px",
    "transition":      "0s",
    "shadow_sm":       "8px 8px 0px #000000",
    "radius":          "0px",
}

# ═══════════════════════════════════════════════════════
# 2. CORE STYLESHEET (Cascade Layers)
# ═══════════════════════════════════════════════════════

# Import component CSS
try:
    from lib_bejson_html3_component_css import COMPONENT_CSS
except ImportError:
    COMPONENT_CSS = ""

CSS_CORE_SKELETON = """
@layer reset, base, layout, components, interactive;

{COMPONENT_CSS}

@layer reset {{
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html {{ height: 100%; min-height: 100dvh; scroll-behavior: smooth; font-size: 16px; }}
    body {{
        margin: 0; padding: 0;
        background-color: var(--bg-page);
        color: var(--text-main);
        -webkit-font-smoothing: antialiased;
        padding-bottom: 60px;
        min-height: 100dvh;
    }}
}}

@layer base {{
    :root {{
        --primary: {primary};
        --primary-muted: {primary_muted};
        --bg-page: {bg_page};
        --bg-alt: {bg_alt};
        --bg-surface: {bg_surface};
        --text-main: {text_main};
        --text-muted: {text_muted};
        --border: {border};
        --border-muted: {border_muted};
        --font-sans: {font_sans};
        --font-mono: {font_mono};
        --sidebar-width: {sidebar_width};
        --transition: {transition};
        --shadow-sm: {shadow_sm};
        --radius: {radius};
    }}

    body {{ font-family: var(--font-sans); line-height: 1.6; }}
    
    h1, h2, h3, h4 {{ color: var(--text-main); line-height: 1.1; margin-bottom: 0.5rem; font-weight: 800; }}
    h1 {{ font-size: clamp(1.75rem, 4vw, 2.5rem); letter-spacing: -0.02em; }}
    h2 {{ font-size: 1.1rem; color: var(--primary); text-transform: uppercase; letter-spacing: 0.05em; }}

    a {{ color: var(--primary); text-decoration: none; transition: var(--transition); }}
    a:hover {{ text-decoration: underline; }}
    
    pre {{
        background: var(--bg-alt);
        padding: 16px;
        border-radius: var(--radius);
        overflow-x: auto;
        white-space: pre-wrap;
        word-break: break-all;
        border: 1px solid var(--border-muted);
        margin: 1rem 0;
    }}

    code {{
        font-family: var(--font-mono);
        background: var(--bg-alt);
        padding: 2px 4px;
        border-radius: 4px;
        word-break: break-word;
    }}
}}

@layer layout {{
    .c-header {{
        display: flex; align-items: center; width: 100%; height: 64px;
        padding: 0 24px; background: var(--bg-page); border-bottom: 1px solid var(--border);
        position: sticky; top: 0; z-index: 1000; gap: 16px;
    }}
    .c-header__logo {{ font-weight: 600; font-size: 1.25rem; }}
    .c-header__logo span {{ color: var(--primary); }}

    .c-breadcrumbs {{ padding: 8px 24px; border-bottom: 1px solid var(--border-muted); font-size: 0.875rem; color: var(--text-muted); }}
    .c-breadcrumbs a {{ color: var(--primary); }}

    .c-container {{
        display: grid; grid-template-columns: var(--sidebar-width) 1fr; gap: 24px;
        padding: 24px; min-height: calc(100vh - 120px);
        width: 100%;
    }}

    .c-main-content {{
        min-width: 0; /* CRITICAL: Prevents grid blowout from wide child content */
        max-width: 100%;
    }}

    .c-sidebar {{
        background-color: var(--bg-page);
        border-right: 1px solid var(--border);
        overflow-y: auto;
    }}

    .c-hamburger {{ display: none; }}

    .c-sidebar__top {{ flex: 1; overflow-y: auto; padding-bottom: 16px; }}
    .c-sidebar__bottom {{ padding: 16px; background: var(--bg-alt); border-top: 1px solid var(--border-muted); border-radius: var(--radius); }}
    
    .c-sidebar__link {{
        padding: 8px 12px; font-size: 0.9rem; border-radius: var(--radius); color: var(--text-main);
        transition: var(--transition); display: flex; align-items: center; gap: 10px; cursor: pointer;
    }}
    .c-sidebar__link:hover {{ background-color: var(--bg-alt); color: var(--primary); }}
    .c-sidebar__link--active {{ background-color: var(--bg-alt); color: var(--primary); font-weight: 600; }}

    .c-footer {{
        position: fixed; bottom: 0; left: 0; width: 100%;
        background-color: var(--bg-page); border-top: 1px solid var(--border);
        padding: 12px 24px; padding-bottom: calc(12px + env(safe-area-inset-bottom));
        text-align: center; font-size: 0.85rem; color: var(--text-muted); z-index: 900;
    }}

    @media (max-width: 1024px) {{
        .c-container {{ grid-template-columns: 1fr; }}
        .c-hamburger {{ display: flex; }}
        .c-sidebar {{ position: fixed; left: -300px; transition: left 0.3s ease; z-index: 1001; height: 100dvh; border-right: none; }}
        .c-sidebar--open {{ left: 0; }}
        .c-sidebar-overlay {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 1000; }}
        .c-sidebar-overlay--open {{ display: block; }}
    }}

    @media print {{
        .c-header, .c-sidebar, .c-footer, .c-sidebar-overlay, .c-hamburger, .c-breadcrumbs {{ display: none !important; }}
        .c-container {{ display: block; padding: 0; }}
        .c-main-content {{ width: 100%; }}
        .c-card {{ border: 1px solid #000 !important; box-shadow: none !important; break-inside: avoid; }}
        body {{ background: #fff !important; color: #000 !important; }}
    }}
}}
"""

CSS_CORE = CSS_CORE_SKELETON.replace("{COMPONENT_CSS}", COMPONENT_CSS)

# Brutal Theme Refinement
CSS_BRUTAL = CSS_CORE_SKELETON.replace("{COMPONENT_CSS}", COMPONENT_CSS) + """
@layer components {{
    .c-card {{ border: 4px solid var(--border); border-radius: 0; box-shadow: var(--shadow-sm); }}
    .c-button {{ border-radius: 0; border: 2px solid var(--text-main); font-weight: 900; }}
    .c-input {{ border-radius: 0; border: 2px solid var(--border); }}
    .c-table {{ border: 2px solid var(--border); }}
    .c-table th {{ border-bottom: 4px solid var(--border); background: var(--primary); color: white; }}
    .c-stats-bar {{ border: 4px solid var(--border); border-radius: 0; }}
}}
"""

# ═══════════════════════════════════════════════════════
# 3. HTML STRUCTURE (BECSS Standard Layout)
# ═══════════════════════════════════════════════════════

HTML_SKELETON = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{title}}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Roboto+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>{{css}}</style>
</head>
<body>
    <header class="c-header">
        <div class="c-hamburger" onclick="document.querySelector('.c-sidebar').classList.add('c-sidebar--open');document.querySelector('.c-sidebar-overlay').classList.add('c-sidebar-overlay--open');" style="cursor:pointer; display:flex; flex-direction:column; gap:4px; padding:4px;">
            <span style="display:block; width:24px; height:2px; background:var(--text-main);"></span>
            <span style="display:block; width:24px; height:2px; background:var(--text-main);"></span>
            <span style="display:block; width:24px; height:2px; background:var(--text-main);"></span>
        </div>
        <div class="c-header__logo">BEJSON <span>LIBRARIES</span></div>
    </header>

    <div class="c-breadcrumbs">{{breadcrumbs}}</div>

    <div class="c-sidebar-overlay" onclick="this.classList.remove('c-sidebar-overlay--open');document.querySelector('.c-sidebar').classList.remove('c-sidebar--open');"></div>

    <div class="c-container">
        <aside class="c-sidebar">
            <div class="c-sidebar__top">
                <nav class="c-sidebar__links">
                    {{nav_items}}
                </nav>
            </div>
            <div class="c-sidebar__bottom">
                SYSTEM // <span>ONLINE</span><br>
                {{status_extra}}
            </div>
        </aside>

        <main class="c-main-content">
            {{content}}
        </main>
    </div>

    <footer class="c-footer">
        &copy; 2026 ELTON BOEHNEN | 
        <a href="https://github.com/boehnenelton">GITHUB</a> | 
        <a href="https://boehnenelton2024.pages.dev">PORTFOLIO</a>
    </footer>

    <script>
        window.switchSubTab = function(tabId) {{
            document.querySelectorAll(".tab-content").forEach(function(c) {{ c.style.display = "none"; }});
            const target = document.getElementById(tabId);
            if (target) target.style.display = "block";
        }};
    </script>
</body>
</html>"""

HTML_SKELETON_BRUTAL = HTML_SKELETON
