"""
Library:      lib_html3_bejson_renderer.py
Family:       HTML3
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      3.1.2 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-06-05
Description:  Auto-rendering pipeline for BEJSON documents into HTML3 components.
REMEDIATED:   Purged transition stubs for Core (Phase 1).
REMEDIATED:   Removed _HEURISTIC_LEGACY; standardized to key/value mapping (Phase 2).
"""

import html as html_mod
import os
import sys
import logging
from lib_html3_body import html_card, html_stats_bar, html_description_list
from lib_html3_tables import html_table
from lib_html3_charts import html_chart
from lib_bejson_to_html import bejson_to_html_viewer
from lib_html3_showcase import html_bento_grid

# --- Sibling Resolution ---
LIB_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_DIR = os.path.join(os.path.dirname(LIB_DIR), "Core")
if CORE_DIR not in sys.path: sys.path.insert(0, CORE_DIR)

from lib_bejson_core import bejson_core_get_field_map

VERSION = "3.1.2"
SCRIPT_NAME = "lib_html3_bejson_renderer.py"
RELATIONAL_ID = "d4e5f6g7-1h2i-3j4k-5l6m-7n8o9p0q1r2s"

def render_bejson(doc, title=None, hint=None):
    """
    Intelligent auto-renderer for BEJSON documents.
    :param doc: BEJSON dictionary.
    :param title: Optional title override.
    :param hint: Optional rendering hint ('table', 'chart', 'stats', 'bento', 'viewer').
    """
    if not isinstance(doc, dict):
        return f"<div class='c-card'>Invalid BEJSON document.</div>"

    # 1. Resolve Hint (Priority: param > header > heuristic)
    hint = hint or doc.get("Rendering_Hint")
    rt = doc.get("Records_Type", [])
    entity = rt[0] if rt else "Data"
    title = title or doc.get("DB_Name") or entity

    # 2. Heuristics if no hint provided
    if not hint:
        # 104a with few records -> Description List or Stats Bar
        if doc.get("Format_Version") == "104a":
            if len(doc.get("Values", [])) < 8:
                hint = "stats"
            else:
                hint = "table"
        # 104 with numeric fields -> Chart candidate
        elif doc.get("Format_Version") == "104":
            has_numeric = any(f.get("type") in ("number", "integer") for f in doc.get("Fields", []))
            if has_numeric and len(doc.get("Values", [])) > 2:
                hint = "chart"
            else:
                hint = "table"
        # 104db -> Multi-table Viewer
        elif doc.get("Format_Version") == "104db":
            hint = "viewer"
        else:
            hint = "table"

    # 3. Component Mapping
    try:
        if hint == "stats":
            # Convert values to stats_list format
            stats = []
            # Optimized Field Mapping (Phase 2: Standardized)
            fi = bejson_core_get_field_map(doc)

            # Priority 1: standard key/value
            # Priority 2: label/value (Bento compat)
            label_idx = fi.get("key", fi.get("label", -1))
            val_idx   = fi.get("value", -1)

            # Fail-safe: exactly 2 fields
            if label_idx == -1 or val_idx == -1:
                if len(doc.get("Fields", [])) == 2:
                    label_idx, val_idx = 0, 1
                else:
                    logging.warning(f"[Renderer] Missing standard fields for 'stats' hint in {title}")
                    return html_table(doc)

            for row in doc["Values"]:
                label = row[label_idx] if label_idx < len(row) else "Unknown"
                value = row[val_idx] if val_idx < len(row) else ""
                stats.append({"label": label, "value": value})
            return html_stats_bar(stats)

        elif hint == "chart":
            fields = doc["Fields"]
            labels_idx = -1
            data_idx = -1
            for i, f in enumerate(fields):
                if f["type"] == "string" and labels_idx == -1: labels_idx = i
                if f["type"] in ("number", "integer") and data_idx == -1: data_idx = i
            
            if labels_idx != -1 and data_idx != -1:
                labels = [row[labels_idx] for row in doc["Values"]]
                data = [row[data_idx] for row in doc["Values"]]
                return html_chart(title=title, labels=labels, data=data)
            return html_table(doc)

        elif hint == "bento":
            return html_bento_grid(doc)

        elif hint == "viewer":
            return bejson_to_html_viewer(doc)

        else: # Default: table
            return html_table(doc)

    except Exception as e:
        # XSS Remediation: Escape exception string
        return f"<div class='c-card'><h3 class='c-card__title'>Rendering Error</h3><div class='c-card__body'>{html_mod.escape(str(e))}</div></div>"
