"""
Library:      lib_html3_pagination.py
Family:       HTML3
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      3.0.0 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-29
Description:  Server-side pagination helpers for BECSS layouts.
"""

import html as html_mod

VERSION = "3.0.0"
SCRIPT_NAME = "lib_html3_pagination.py"
RELATIONAL_ID = "4f5a6b7c-8d9e-0a1b-c2d3-e4f5a6b7c8d9"

def html_server_pagination(current_page, total_pages, base_url, page_param="page"):
    """
    Generates BECSS pagination buttons for server-side paging.
    """
    def make_url(p):
        sep = "&" if "?" in base_url else "?"
        return f"{base_url}{sep}{page_param}={p}"

    prev_disabled = " disabled" if current_page <= 1 else ""
    next_disabled = " disabled" if current_page >= total_pages else ""
    
    prev_url = make_url(current_page - 1) if current_page > 1 else "#"
    next_url = make_url(current_page + 1) if current_page < total_pages else "#"

    return f"""
    <div class="c-pagination">
        <button class="c-pagination__btn"{prev_disabled} onclick="window.location.href='{prev_url}'">PREV</button>
        <span class="c-pagination__info">PAGE {current_page} / {total_pages}</span>
        <button class="c-pagination__btn"{next_disabled} onclick="window.location.href='{next_url}'">NEXT</button>
    </div>"""
