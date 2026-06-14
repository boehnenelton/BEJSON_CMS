"""
Library:      lib_bejson_validator_diagram.py
Family:       HTML3
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      3.0.0 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-29
Description:  Structural integrity checker and high-fidelity BECSS diagram exporter.
"""

import json
import os
from pathlib import Path
from datetime import datetime
import lib_bejson_validator as CoreValidator

# Reuse template logic from diagram_html for consistency
from lib_bejson_diagram_html import BECSS_DIAGRAM_TEMPLATE

def bejson_validator_diagram_validate_string(json_string):
    """Validates a BEJSON string as a valid Diagrammer structure."""
    CoreValidator.bejson_validator_validate_string(json_string)
    return True

def bejson_diagram_export_html(json_string, output_path, title="BEJSON Diagram"):
    """
    Generates a high-fidelity standalone BECSS HTML diagram viewer.
    """
    doc = json.loads(json_string)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Dynamic ViewBox Calculation
    fields = doc["Fields"]
    fi = {}
    for i, f in enumerate(fields):
        key = f["name"] + "_" + f.get("Record_Type_Parent", "common")
        fi[key] = i
        
    shapes = [v for v in doc["Values"] if v[0] == "Shape"]
    
    if shapes:
        def get_val(r, name):
            idx = fi.get(f"{name}_Shape")
            if idx is None: idx = fi.get(f"{name}_common")
            return r[idx] if idx is not None and idx < len(r) else 0

        min_x = min(get_val(r, "x") or get_val(r, "s_x") or 0 for r in shapes)
        min_y = min(get_val(r, "y") or get_val(r, "s_y") or 0 for r in shapes)
        max_x = max((get_val(r, "x") or get_val(r, "s_x") or 0) + (get_val(r, "w") or get_val(r, "s_w") or 150) for r in shapes)
        max_y = max((get_val(r, "y") or get_val(r, "s_y") or 0) + (get_val(r, "h") or get_val(r, "s_h") or 60) for r in shapes)
        
        padding = 100
        viewbox = f"{min_x - padding} {min_y - padding} {max_x - min_x + padding*2} {max_y - min_y + padding*2}"
    else:
        viewbox = "0 0 1440 720"
    
    final_html = BECSS_DIAGRAM_TEMPLATE.replace("{{TITLE}}", title) \
                                 .replace("{{DIAGRAM_DATA}}", json_string.strip()) \
                                 .replace("{{ACCENT_COLOR}}", "oklch(65% 0.2 25)") \
                                 .replace("{{BG_COLOR}}", "oklch(5% 0 0)") \
                                 .replace("{{TIMESTAMP}}", timestamp) \
                                 .replace("{{SUBTITLE}}", "Structural logic map generated via BEJSON 104db") \
                                 .replace("{{MODE}}", "DIAGRAM") \
                                 .replace("{{VIEWBOX}}", viewbox)
                               
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(final_html)
    return True

def bejson_validator_diagram_validate_file(file_path):
    text = Path(file_path).read_text(encoding="utf-8")
    return bejson_validator_diagram_validate_string(text)
