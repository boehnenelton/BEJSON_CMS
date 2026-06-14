"""
Library:      lib_html3_list_renderer.py
Family:       HTML3
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.1.1 OFFICIAL
              MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-06-05
Description:  Authoritative List / Tree / Sidebar renderer for BEJSON 104 documents.
REMEDIATED:   Purged transition stubs for Core (Phase 1).
RELATIONAL_ID: a1b2c3d4-e5f6-7890-ab12-cd34ef567890
"""

import json
import time
import os
import sys
from typing import Any, Dict, List, Optional

SCRIPT_NAME    = "lib_html3_list_renderer.py"
SCRIPT_VERSION = "2.1.1"
RELATIONAL_ID  = "a1b2c3d4-e5f6-7890-ab12-cd34ef567890"

LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if LIB_DIR not in sys.path:
    sys.path.append(LIB_DIR)

import lib_bejson_core as BEJSONCore

# --- Legacy Fallback Constants ---
_LIST_LEGACY = {
    "id": 0, "title": 1, "name": 1, "label": 1,
    "description": 2, "desc": 2,
    "parent_id": 3, "parent_id_fk": 3, "parent": 3,
    "url": 4, "href": 4, "link": 4,
    "action_url": 5, "action_label": 6
}

# ---------------------------------------------------------------------------
# BEJSON field resolution helpers
# ---------------------------------------------------------------------------

def _get_field_map(doc: dict) -> Dict[str, int]:
    """
    Returns {field_name_lower: index} for the Fields array.
    Uses bejson_core_get_field_map (cached). Keys are lowercased for
    case-insensitive lookup.
    """
    raw = BEJSONCore.bejson_core_get_field_map(doc)
    # Note: list_renderer historically uses lowercase keys internally
    return {k.lower(): v for k, v in raw.items()}


def _resolve_field(f_map: Dict[str, int], *candidates) -> int:
    """
    Returns the index of the first candidate name found in f_map, or -1.
    Supports FK-convention aliases: if candidate ends with _fk, also try
    without the suffix, and vice versa.
    Candidates are checked in order; first match wins.
    If no match in f_map, falls back to _LIST_LEGACY.
    """
    for name in candidates:
        name_l = name.lower()
        if name_l in f_map:
            return f_map[name_l]
        # Try FK variant: if looking for "parent_id", also try "parent_id_fk"
        fk_name = name_l + "_fk"
        if fk_name in f_map:
            return f_map[fk_name]
        # If the candidate already ends in _fk, also try without it
        if name_l.endswith("_fk"):
            base = name_l[:-3]
            if base in f_map:
                return f_map[base]
    
    # --- Safe Get Fallback (Migration Phase 5.3) ---
    for name in candidates:
        if name in _LIST_LEGACY:
            return _LIST_LEGACY[name]
            
    return -1


def _get(row: list, idx: int) -> Any:
    """Safe index access; returns None for -1 or out-of-bounds."""
    if idx < 0 or idx >= len(row):
        return None
    return row[idx]


# ---------------------------------------------------------------------------
# CSS + JS
# ---------------------------------------------------------------------------

_CORE_CSS = """
<style>
.c-html3-list {
    font-family: 'Inter', 'Source Code Pro', monospace;
    color: #000;
    background: #fff;
    max-width: 100%;
    box-sizing: border-box;
}

/* BREADCRUMBS */
.c-html3-list__breadcrumbs {
    display: flex; gap: 8px; font-size: 0.7rem; color: #999;
    margin-bottom: 1rem; text-transform: uppercase; letter-spacing: 1px;
    min-height: 1.2rem; font-family: 'Source Code Pro', monospace;
}
.c-html3-list__breadcrumb-item::after { content: '>'; margin-left: 8px; color: #ccc; }
.c-html3-list__breadcrumb-item:last-child::after { content: ''; }
.c-html3-list__breadcrumb-item.active { color: #DE2626; font-weight: bold; }

/* TREE MODE */
.c-html3-list--tree {
    background: #fff; border: 1px solid #e0e0e0;
    border-radius: 4px; padding: 1.5rem;
}
.c-html3-list__tree { list-style: none; padding-left: 0; margin: 0; }
.c-html3-list__item { margin: 4px 0; position: relative; }
.c-html3-list__content {
    display: flex; align-items: flex-start; gap: 12px;
    padding: 10px 14px; background: #fafafa;
    border: 1px solid #e8e8e8; border-radius: 2px;
    transition: all 0.15s; cursor: pointer; position: relative;
}
.c-html3-list__content:hover { border-color: #DE2626; background: #fff5f5; }
.c-html3-list__content.is-selected {
    background: #DE2626 !important;
    border-color: #b01e1e !important;
    color: #fff !important;
}
.c-html3-list__content.is-selected * { color: #fff !important; }

/* ACTION HOOKS */
.c-html3-list__action {
    position: absolute; right: 10px; top: 50%;
    transform: translateY(-50%); opacity: 0; transition: opacity 0.15s;
}
.c-html3-list__content:hover .c-html3-list__action { opacity: 1; }
.c-html3-list__btn {
    background: #DE2626; color: #fff; border: none;
    padding: 4px 10px; border-radius: 2px;
    font-size: 0.65rem; font-weight: bold; cursor: pointer;
    text-transform: uppercase; text-decoration: none;
    font-family: 'Source Code Pro', monospace;
}
.c-html3-list__btn:hover { background: #000; color: #fff; }

.c-html3-list__toggle {
    width: 24px; color: #DE2626; font-weight: bold;
    text-align: center; font-family: 'Source Code Pro', monospace;
    flex-shrink: 0;
}
.c-html3-list__children {
    list-style: none; padding-left: 32px;
    border-left: 2px solid #e8e8e8; margin-left: 11px;
}
.c-html3-list__item-title {
    font-weight: 600; font-size: 0.88rem; color: #000;
}
.c-html3-list__item-desc {
    font-size: 0.75rem; color: #777; margin-top: 2px;
}

/* SIDEBAR */
.c-html3-list--sidebar {
    width: 100%; background: #fff;
    border-right: 1px solid #e8e8e8;
    height: 100%; display: flex; flex-direction: column;
}
.c-html3-list__nav-item {
    display: block; padding: 12px 20px; color: #555;
    text-decoration: none; border-left: 3px solid transparent;
    font-size: 0.82rem; transition: all 0.15s;
    text-transform: uppercase; letter-spacing: 1px; cursor: pointer;
    font-family: 'Inter', sans-serif;
}
.c-html3-list__nav-item:hover {
    background: #fafafa; color: #000; border-left-color: #DE2626;
}
.c-html3-list__nav-item.is-active {
    background: #fff5f5; color: #DE2626;
    border-left-color: #DE2626; font-weight: bold;
}
.c-html3-list__nav-sub { padding-left: 15px; background: #fafafa; }
</style>
"""

_CORE_JS = """
<script>
if (!window.html3_list_state) { window.html3_list_state = {}; }
if (!window.html3_list_data)  { window.html3_list_data  = {}; }

if (!window.html3_list_toggle) {
    window.html3_list_toggle = function(el, cid, itemId) {
        var item     = el.closest('.c-html3-list__item');
        var children = item.querySelector('.c-html3-list__children');
        var toggle   = item.querySelector('.c-html3-list__toggle');
        if (children) {
            var hidden = children.style.display === 'none';
            children.style.display = hidden ? 'block' : 'none';
            if (toggle) { toggle.textContent = hidden ? '[-]' : '[+]'; }
        }
        var listRoot = el.closest('.c-html3-list');
        listRoot.querySelectorAll('.c-html3-list__content').forEach(function(c) {
            c.classList.remove('is-selected');
        });
        el.classList.add('is-selected');
        if (window.html3_update_breadcrumbs) {
            window.html3_update_breadcrumbs(cid, itemId);
        }
    };
}

if (!window.html3_update_breadcrumbs) {
    window.html3_update_breadcrumbs = function(cid, itemId) {
        var bcContainer = document.querySelector('#' + cid + ' .c-html3-list__breadcrumbs');
        if (!bcContainer) { return; }
        var data = window.html3_list_data[cid];
        if (!data) { return; }
        var path = [];
        var curr = itemId;
        while (curr) {
            var found = null;
            for (var i = 0; i < data.length; i++) {
                if (data[i].id === curr) { found = data[i]; break; }
            }
            if (found) {
                path.unshift(found.title);
                curr = found.parent_id;
            } else {
                break;
            }
        }
        bcContainer.innerHTML = path.map(function(name, i) {
            var cls = 'c-html3-list__breadcrumb-item' + (i === path.length - 1 ? ' active' : '');
            return '<span class="' + cls + '">' + name + '</span>';
        }).join('');
    };
}
</script>
"""


# ---------------------------------------------------------------------------
# Core class
# ---------------------------------------------------------------------------

class HTML3_List_Renderer:
    """
    Multi-mode BEJSON 104 list renderer.
    Modes: TREE (default), SIDEBAR.

    Expected BEJSON 104 field names (all resolved via FK-convention aware lookup):
      - id           : unique row identifier
      - title        : display label
      - description  : optional subtitle / detail text
      - parent_id    : parent row id (or parent_id_fk per BEJSON FK convention)
      - url          : optional navigation href
      - action_url   : optional action button href
      - action_label : label for action button (default: "RUN")
    """

    def __init__(self):
        pass

    # -----------------------------------------------------------------------
    # Field-map aware hierarchy builder
    # -----------------------------------------------------------------------

    def _build_hierarchy(self, doc: dict):
        """
        Converts a flat BEJSON 104 Values array into a tree structure.

        Returns: (roots, item_map, raw_items)
          roots     — list of top-level item dicts
          item_map  — {id: item_dict}
          raw_items — flat list of all item dicts (for JSON serialization)
        """
        f_map = _get_field_map(doc)

        # Resolve each semantic field using FK-convention aware lookup
        id_idx         = _resolve_field(f_map, "id")
        title_idx      = _resolve_field(f_map, "title", "name", "label")
        desc_idx       = _resolve_field(f_map, "description", "desc")
        pid_idx        = _resolve_field(f_map, "parent_id", "parent_id_fk", "parent")
        url_idx        = _resolve_field(f_map, "url", "href", "link")
        act_url_idx    = _resolve_field(f_map, "action_url")
        act_label_idx  = _resolve_field(f_map, "action_label")

        item_map = {}
        raw_items = []
        roots = []

        for row in doc.get("Values", []):
            if not row:
                continue
            item = {
                "id":           _get(row, id_idx),
                "title":        _get(row, title_idx) or "(untitled)",
                "description":  _get(row, desc_idx),
                "parent_id":    _get(row, pid_idx),
                "url":          _get(row, url_idx),
                "action_url":   _get(row, act_url_idx),
                "action_label": _get(row, act_label_idx) or "RUN",
                "children":     [],
            }
            raw_items.append(item)
            if item["id"] is not None:
                item_map[item["id"]] = item

        # Build parent-child relationships
        for item in raw_items:
            pid = item["parent_id"]
            if pid and pid in item_map:
                item_map[pid]["children"].append(item)
            else:
                roots.append(item)

        return roots, item_map, raw_items

    # -----------------------------------------------------------------------
    # Public render entry point
    # -----------------------------------------------------------------------

    def render(self, doc_or_path, mode: str = "TREE", **kwargs) -> str:
        """
        Render a BEJSON 104 document as an HTML list.

        Args:
            doc_or_path: BEJSON dict or file path string.
            mode:        "TREE" (default) or "SIDEBAR".
            kwargs:
                cid         — container id (auto-generated if omitted)
                title       — header label
                on_click    — JS function name called with (id) on selection
        """
        if isinstance(doc_or_path, str):
            if not _HAS_CORE:
                return "<p>Error: lib_bejson_core not available.</p>"
            doc = BEJSONCore.bejson_core_load_file(doc_or_path)
            if not doc:
                return "<p>Error: could not load BEJSON file.</p>"
        else:
            doc = doc_or_path

        roots, item_map, raw_items = self._build_hierarchy(doc)
        cid      = kwargs.get("cid") or ("lst_" + str(int(time.time() * 1000)))
        title    = kwargs.get("title", "")
        on_click = kwargs.get("on_click", None)

        if mode == "SIDEBAR":
            return self._render_sidebar(roots, cid, title, on_click)
        return self._render_tree(roots, raw_items, cid, title, on_click)

    # -----------------------------------------------------------------------
    # TREE renderer
    # -----------------------------------------------------------------------

    def _render_tree(self, roots, raw_items, cid, title, on_click):
        def build_node(item):
            has_children = bool(item["children"])
            toggle = "[-]" if has_children else "[o]"

            if item["action_url"]:
                action_html = (
                    '<div class="c-html3-list__action">'
                    '<a href="' + str(item["action_url"]) + '" class="c-html3-list__btn">'
                    + str(item["action_label"]) +
                    '</a></div>'
                )
            else:
                action_html = ""

            safe_id = str(item["id"]).replace("'", "\\'")
            click_handler = "window.html3_list_toggle(this, '" + cid + "', '" + safe_id + "');"
            if on_click:
                click_handler += " " + on_click + "('" + safe_id + "');"

            html = '<li class="c-html3-list__item">'
            html += '<div class="c-html3-list__content" onclick="' + click_handler + '">'
            html += '<div class="c-html3-list__toggle">' + toggle + '</div>'
            html += '<div class="c-html3-list__item-info">'
            html += '<div class="c-html3-list__item-title">' + str(item["title"]) + '</div>'
            if item["description"]:
                html += '<div class="c-html3-list__item-desc">' + str(item["description"]) + '</div>'
            html += '</div>'
            html += action_html
            html += '</div>'
            if has_children:
                html += '<ul class="c-html3-list__children">'
                for child in sorted(item["children"], key=lambda x: str(x["title"])):
                    html += build_node(child)
                html += '</ul>'
            html += '</li>'
            return html

        nodes_html = "".join(build_node(r) for r in sorted(roots, key=lambda x: str(x["title"])))

        data_json = json.dumps([
            {"id": it["id"], "title": it["title"], "parent_id": it["parent_id"]}
            for it in raw_items
        ])

        tree_header = (
            '<div style="display:flex;align-items:center;justify-content:space-between;'
            'margin-bottom:1rem;border-bottom:1px solid #e8e8e8;padding-bottom:0.8rem;">'
            '<div style="color:#DE2626;font-weight:bold;letter-spacing:2px;'
            'text-transform:uppercase;font-family:\'Source Code Pro\',monospace;">'
            + title +
            '</div>'
            '<div style="font-size:0.65rem;color:#aaa;font-family:\'Source Code Pro\',monospace;">'
            + SCRIPT_VERSION +
            '</div>'
            '</div>'
        )

        return (
            _CORE_CSS + _CORE_JS +
            '<div id="' + cid + '" class="c-html3-list c-html3-list--tree">'
            '<div class="c-html3-list__breadcrumbs">SELECT NODE TO VIEW PATH</div>'
            + tree_header +
            '<ul class="c-html3-list__tree">' + nodes_html + '</ul>'
            '<script>'
            'if (!window.html3_list_data) { window.html3_list_data = {}; }'
            "window.html3_list_data['" + cid + "'] = " + data_json + ";"
            '</script>'
            '</div>'
        )

    # -----------------------------------------------------------------------
    # SIDEBAR renderer
    # -----------------------------------------------------------------------

    def _render_sidebar(self, roots, cid, title, on_click=None):
        def build_nav(item, level=0):
            indent    = level * 15
            href      = item["url"] if item["url"] else "#"
            safe_id   = str(item["id"]).replace("'", "\\'")

            click_attr = ""
            if on_click:
                click_attr = 'onclick="' + on_click + "('" + safe_id + "'); return false;\""

            html = (
                '<a href="' + href + '" ' + click_attr +
                ' class="c-html3-list__nav-item"'
                ' style="padding-left:' + str(20 + indent) + 'px;">'
                + str(item["title"]) + '</a>'
            )
            if item["children"]:
                html += '<div class="c-html3-list__nav-sub">'
                for child in sorted(item["children"], key=lambda x: str(x["title"])):
                    html += build_nav(child, level + 1)
                html += '</div>'
            return html

        nav_html = "".join(build_nav(r) for r in sorted(roots, key=lambda x: str(x["title"])))

        sidebar_title = (
            '<div style="padding:20px;border-bottom:1px solid #e8e8e8;'
            'color:#DE2626;font-weight:bold;font-size:0.9rem;'
            'letter-spacing:2px;text-transform:uppercase;'
            'font-family:\'Source Code Pro\',monospace;">'
            + title + '</div>'
        )

        return (
            _CORE_CSS +
            '<div id="' + cid + '" class="c-html3-list c-html3-list--sidebar">'
            + sidebar_title +
            '<div style="flex:1;overflow-y:auto;">' + nav_html + '</div>'
            '</div>'
        )


if __name__ == "__main__":
    print(SCRIPT_NAME, SCRIPT_VERSION, "loaded.")
