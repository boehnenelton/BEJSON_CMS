"""
Library:      lib_bejson_to_html.py
Family:       HTML3
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      3.0.0 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-29
Description:  Core transformer for converting BEJSON data into BECSS HTML3 components.
"""

import json
import html as html_mod
from datetime import datetime

# Import components
from lib_html3_body import html_card, html_brutal_table, html_subtabs, html_tab_content

def bejson_to_html_viewer(bejson_doc):
    """
    Converts a BEJSON document into a high-density BECSS HTML viewer.
    :param bejson_doc: The parsed BEJSON dictionary.
    :return: HTML string with tab-switching or multi-table layout.
    """
    fmt = bejson_doc.get("Format_Version", "104")
    record_types = bejson_doc.get("Records_Type", [])
    fields = bejson_doc.get("Fields", [])
    values = bejson_doc.get("Values", [])
    
    rt_idx = -1
    for i, f in enumerate(fields):
        if f.get("name") == "Record_Type_Parent":
            rt_idx = i
            break
            
    tabs = []
    tab_contents = []
    
    for i, rt in enumerate(record_types):
        rt_headers = []
        rt_field_indices = []
        
        for j, f in enumerate(fields):
            fname = f.get("name")
            fparent = f.get("Record_Type_Parent")
            
            if fname == "Record_Type_Parent": continue
            
            if not fparent or fparent == rt:
                rt_headers.append(fname)
                rt_field_indices.append(j)
        
        rt_rows = []
        for row in values:
            if rt_idx >= 0:
                if row[rt_idx] == rt:
                    rt_rows.append([row[idx] for idx in rt_field_indices])
            else:
                if i == 0:
                    rt_rows.append([row[idx] for idx in rt_field_indices])

        if rt_rows:
            table_html = html_brutal_table(rt_headers, rt_rows)
        else:
            table_html = "<p class='u-text-muted u-fs-small' style='padding:24px;'>No records found for this type.</p>"
            
        tab_id = f"tab_{rt.lower().replace(' ', '_')}"
        tabs.append({"label": rt, "id": tab_id, "active": (i == 0)})
        tab_contents.append(html_tab_content(tab_id, table_html, active=(i == 0)))

    if len(record_types) > 1:
        switcher = html_subtabs(tabs)
        content_stack = "".join(tab_contents)
        return f"{switcher}<div class='c-card' style='margin-top:-2px; border-top-left-radius:0;'>{content_stack}</div>"
    else:
        title = record_types[0] if record_types else "RECORDS"
        return html_card(title, tab_contents[0] if tab_contents else "")

def bejson_schema_viewer(bejson_doc):
    """
    Standard viewer specifically for the Schema definition (Fields).
    """
    fields = bejson_doc.get("Fields", [])
    headers = ["Name", "Type", "Scope"]
    rows = []
    for f in fields:
        rows.append([
            f.get("name", "?"),
            f.get("type", "string"),
            f.get("Record_Type_Parent", "COMMON")
        ])
    
    return html_card("SCHEMA DEFINITION", html_brutal_table(headers, rows))
