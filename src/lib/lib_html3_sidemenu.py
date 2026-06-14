"""
Library:      lib_html3_sidemenu.py
Family:       HTML3
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      3.0.0 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-29
Description:  Navigation and sidebar component manager for web apps.
              Refactored to BECSS standards.
"""

import html as html_mod

VERSION = "3.0.0"
SCRIPT_NAME = "lib_html3_sidemenu.py"
RELATIONAL_ID = "6a4e3d2b-1f7c-4e8a-9d6c-2f4b5a6c7d8e"

def _sidebar_html(nav_links, title="Menu"):
    """
    Build sidebar + overlay HTML based on BECSS standards.
    Returns (header, sidebar, overlay) tuple.
    """
    if not nav_links:
        return "", "", ""
        
    def safe_label(l):
        l_str = str(l)
        if "&" in l_str or "&#" in l_str or any(ord(c) > 127 for c in l_str):
            return l_str
        return html_mod.escape(l_str)

    links = "".join(f'<a href="{html_mod.escape(str(h))}" class="c-sidebar__link"><span>❯</span> {safe_label(l)}</a>\n' for l, h in nav_links)
    
    header = f"""
<header class="c-header" role="banner">
    <button class="c-hamburger" onclick="document.querySelector('.c-sidebar').classList.toggle('c-sidebar--open');document.querySelector('.c-sidebar-overlay').classList.toggle('c-sidebar-overlay--open'); var expanded = this.getAttribute('aria-expanded') === 'true'; this.setAttribute('aria-expanded', !expanded);" aria-label="Toggle navigation" aria-expanded="false" style="background:none; border:none; cursor:pointer; display:flex; flex-direction:column; gap:4px; padding:4px;">
        <span style="display:block; width:24px; height:2px; background:var(--text-main);"></span>
        <span style="display:block; width:24px; height:2px; background:var(--text-main);"></span>
        <span style="display:block; width:24px; height:2px; background:var(--text-main);"></span>
    </button>
    <div class="c-header__logo">{html_mod.escape(str(title))}</div>
</header>"""

    sidebar = f"""
<aside class="c-sidebar" role="navigation" aria-label="Main navigation">
    <div class="c-sidebar__top">
        <nav class="c-sidebar__links">
            {links}
        </nav>
    </div>
</aside>"""
    
    overlay = f"""<div class="c-sidebar-overlay" onclick="document.querySelector('.c-sidebar').classList.remove('c-sidebar--open');document.querySelector('.c-sidebar-overlay').classList.remove('c-sidebar-overlay--open')"></div>"""
    
    return header, sidebar, overlay

def html_navbar(links, dark=False):
    """
    [DEPRECATED] Standalone navbar overlay.
    """
    link_html = "".join(f'<a href="{html_mod.escape(str(h))}" class="c-sidebar__link">{html_mod.escape(str(l))}</a>\n' for l, h in links)
    return f"""
<button class="c-hamburger" onclick="document.querySelector('.c-sidebar-overlay').classList.toggle('c-sidebar-overlay--open')" style="background:none; border:none; cursor:pointer; display:flex; flex-direction:column; gap:4px; padding:4px;">
    <span style="display:block; width:24px; height:2px; background:var(--text-main);"></span>
    <span style="display:block; width:24px; height:2px; background:var(--text-main);"></span>
    <span style="display:block; width:24px; height:2px; background:var(--text-main);"></span>
</button>
<div class="c-sidebar-overlay" onclick="if(event.target===this)this.classList.remove('c-sidebar-overlay--open')">
    <div class="c-sidebar" style="position:fixed; left:0; top:0; height:100%; width:250px; background:var(--bg-page); border-right:1px solid var(--border);">
        {link_html}
    </div>
</div>"""
