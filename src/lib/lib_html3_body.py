"""
Library:      lib_html3_body.py
Family:       HTML3
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      3.0.0 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-29
Description:  Core UI components refactored to BECSS (BEM + OKLCH) standards.
              Enhanced with Type Hints and Doctests.
"""

import html as html_mod
import uuid
from typing import List, Dict, Optional, Any

VERSION = "3.0.0"
SCRIPT_NAME = "lib_html3_body.py"
RELATIONAL_ID = "f4e20029-6b75-4b51-a664-75ac1c265c97"
ES5_SAFE = True 

def html_stats_bar(stats_list: List[Dict[str, Any]]) -> str:
    """
    BECSS Stats Bar component.
    
    >>> html_stats_bar([{"label": "CPU", "value": "12%"}])
    '<div class="c-stats-bar">...</div>'
    """
    if not stats_list: return ""
    items = ""
    for s in stats_list:
        label = html_mod.escape(str(s.get("label", "")))
        value = html_mod.escape(str(s.get("value", "")))
        items += f"""
        <div class="c-stats-bar__item">
            <div class="c-stats-bar__label">{label}</div>
            <div class="c-stats-bar__value">{value}</div>
        </div>"""
    return f'<div class="c-stats-bar">{items}</div>'

def html_card(title: str, body: str, variant: Optional[str] = None) -> str:
    """
    Standard BECSS Card component.
    
    >>> html_card("Hello", "<p>World</p>")
    '\\n    <div class="c-card">...</div>'
    """
    modifier = f" c-card--{variant}" if variant else ""
    return f"""
    <div class="c-card{modifier}">
        <h2 class="c-card__title">{html_mod.escape(title)}</h2>
        <div class="c-card__body">{body}</div>
    </div>"""

def html_brutal_card(title: str, content: str) -> str:
    """Modernized Brutalist Card using BECSS modifiers."""
    return html_card(title, content, variant="brutal")

def html_brutal_table(headers: List[str], rows: List[List[Any]], escape: bool = True) -> str:
    """BECSS Data Table."""
    h_html = "".join([f"<th>{html_mod.escape(h)}</th>" for h in headers])
    r_html = ""
    for row in rows:
        cells = []
        for v in row:
            val = str(v)
            if escape: val = html_mod.escape(val)
            cells.append(f"<td>{val}</td>")
        r_html += "<tr>" + "".join(cells) + "</tr>"
    return f'<div class="c-table-container"><table class="c-table"><thead><tr>{h_html}</tr></thead><tbody>{r_html}</tbody></table></div>'

def html_subtabs(tabs: List[Dict[str, Any]]) -> str:
    """BECSS Subtabs component."""
    if not tabs: return ""
    items = ""
    for t in tabs:
        active_class = " c-subtabs__btn--active" if t.get("active") else ""
        label = html_mod.escape(str(t.get("label", "")))
        tab_id = html_mod.escape(str(t.get("id", "")))
        items += f'<button class="c-subtabs__btn{active_class}" onclick="switchSubTab(\'{tab_id}\'); this.parentElement.querySelectorAll(\'.c-subtabs__btn\').forEach(function(b) {{ b.classList.remove(\'c-subtabs__btn--active\'); }}); this.classList.add(\'c-subtabs__btn--active\');">{label}</button>\n'
    return f'<div class="c-subtabs">{items}</div>'

def html_tab_content(tab_id: str, content: str, active: bool = False) -> str:
    """BECSS Tab content container."""
    style = "display: block;" if active else "display: none;"
    return f'<div id="{html_mod.escape(tab_id)}" class="c-tab-content" style="{style}">{content}</div>'

def html_description_list(props: List[Dict[str, str]]) -> str:
    """BECSS Description List component."""
    html_items = ""
    for p in props:
        term = html_mod.escape(p.get("term", ""))
        desc = html_mod.escape(p.get("description", ""))
        html_items += f"""
        <div class="c-dl__item">
            <dt class="c-dl__term">{term}</dt>
            <dd class="c-dl__desc">{desc}</dd>
        </div>"""
    return f'<dl class="c-dl">{html_items}</dl>'

def html_badge(text: str, variant: str = "") -> str:
    """BECSS Badge component."""
    modifier = f" c-badge--{variant}" if variant else ""
    return f'<span class="c-badge{modifier}">{html_mod.escape(text.upper())}</span>'

def html_card_grid(content: str) -> str:
    """BECSS Card Grid container."""
    return f'<div class="c-card-grid">{content}</div>'

def html_code_box(title: str, content: str, copy_id: Optional[str] = None) -> str:
    """BECSS Code Box with integrated clipboard logic."""
    if not copy_id:
        copy_id = f"code_{uuid.uuid4().hex[:12]}"
        
    return f"""
    <div class="c-code-box">
        <div class="c-code-box__header">
            <div class="c-code-box__title">FILE // {html_mod.escape(title)}</div>
            <button class="c-code-box__copy" onclick="bejsonCopy('{copy_id}', this)">COPY</button>
        </div>
        <pre id="{copy_id}" class="c-code-box__pre"><code class="c-code-box__code">{html_mod.escape(content)}</code></pre>
    </div>
    """

def html_toast_system() -> str:
    """Returns the container for toast notifications."""
    return '<div class="c-toast-container" id="toast-container"></div>'

def html_progress_bar(label: str, value: float, max_val: float = 100, unit: str = "%") -> str:
    """BECSS Progress Bar."""
    percent = (value / max_val) * 100
    return f"""
    <div class="c-progress-container">
        <div class="c-progress-label">
            <span>{html_mod.escape(label)}</span>
            <span>{value}/{max_val}{unit}</span>
        </div>
        <div class="c-progress-bar">
            <div class="c-progress-fill" style="width: {percent}%;"></div>
        </div>
    </div>"""

def html_empty_state(title: str = "No Data", text: str = "There's nothing to show here yet.", icon: str = "∅") -> str:
    """BECSS Empty State placeholder."""
    return f"""
    <div class="c-empty-state">
        <div class="c-empty-state__icon">{icon}</div>
        <div class="c-empty-state__title">{html_mod.escape(title)}</div>
        <div class="c-empty-state__text">{html_mod.escape(text)}</div>
    </div>"""

def html_accordion(items: List[Dict[str, str]]) -> str:
    """BECSS Accordion component."""
    id_prefix = f"acc_{uuid.uuid4().hex[:8]}"
    html = '<div class="c-accordion">'
    for i, item in enumerate(items):
        cid = f"{id_prefix}_{i}"
        html += f"""
        <div class="c-accordion__item">
            <div class="c-accordion__header" onclick="var c=document.getElementById('{cid}'); var s=c.style.display==='block'; c.style.display=s?'none':'block'; this.querySelector('.c-accordion__icon').style.transform=s?'rotate(0)':'rotate(90deg)';">
                <span>{html_mod.escape(item['title'])}</span>
                <span class="c-accordion__icon">❯</span>
            </div>
            <div class="c-accordion__content" id="{cid}">
                {item['content']}
            </div>
        </div>"""
    html += '</div>'
    return html

def html_breadcrumbs(links: List[Dict[str, str]]) -> str:
    """BECSS Breadcrumbs."""
    items = ""
    for i, link in enumerate(links):
        is_last = (i == len(links) - 1)
        label = html_mod.escape(link['label'])
        if is_last:
            items += f'<li class="c-breadcrumbs__item">{label}</li>'
        else:
            items += f"""
            <li class="c-breadcrumbs__item">
                <a href="{link['url']}">{label}</a>
                <span class="c-breadcrumbs__separator">/</span>
            </li>"""
    return f'<ul class="c-breadcrumbs">{items}</ul>'

def html_key_value_table(data: Dict[str, Any]) -> str:
    """BECSS Key-Value property table."""
    rows = ""
    for k, v in data.items():
        rows += f'<tr><th style="width:30%;">{html_mod.escape(str(k))}</th><td>{html_mod.escape(str(v))}</td></tr>'
    return f'<div class="c-table-container"><table class="c-table">{rows}</table></div>'
