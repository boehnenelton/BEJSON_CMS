"""
Library:      lib_html3_version.py
Family:       HTML3
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      3.0.0 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-29
Description:  Version manifest for the HTML3 library family.
"""

VERSION = "3.0.0"

LIBRARY_MANIFEST = {
    "lib_html3_animations":     "3.0.0",
    "lib_html3_body":           "3.0.0",
    "lib_html3_charts":         "3.0.0",
    "lib_html3_feed_templates": "3.0.0",
    "lib_html3_flask":          "3.0.0",
    "lib_html3_metrics":        "3.0.0",
    "lib_html3_page_templates": "3.0.0",
    "lib_html3_showcase":       "3.0.0",
    "lib_html3_sidemenu":       "3.0.0",
    "lib_html3_tables":         "3.0.0",
    "lib_html3_widgets":        "3.0.0",
    "lib_bejson_html3_skeletons": "3.0.0",
}

def get_version():
    return VERSION

def get_manifest():
    return LIBRARY_MANIFEST.copy()
