"""
Library:         lib_bejson_Core_bejson_104db_parser.py
Family:          Core
Module Purpose:  Parses and unpacks a BEJSON 104db project document (ProjectMeta + FileContent records in one file) back into a directory.
Architecture:    BEJSON 104db: ONE file holding 2+ entity types, with a Record_Type_Parent discriminator in column 0, per-field Record_Type_Parent ownership, and null-padding for non-applicable fields. A single-file format; it is not MFDB.
Format_Scope:    104db only (single file; NOT MFDB)
Glossary:        BEJSON 104, 104a and 104db are the three file formats (Format_Version). 104db = ONE file holding 2+ entity types
                 (Record_Type_Parent discriminator, null-padding). MFDB is NOT a format and NOT 104db: it is a layer made of one 104a manifest
                 (104a.mfdb.bejson) plus dense 104 entity files linked by Parent_Hierarchy. MFDB-132 = an MFDB packed into one Chunked-104a document.
Version:         1.0.3
Release_Version: 300
Date:            2026-10-06
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   62b60de4-244e-476a-aee1-2ee483fbbc8a
"""

import json
import re
import os
import base64
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from lib_bejson_Core_bejson_path_guard import bejson_safe_join
except ImportError:
    # Joins a base directory and a relative path and refuses results that leave the base (path-traversal guard for unpacking).
    def bejson_safe_join(base: str, rel: str) -> str:
        base_path = Path(base).resolve()
        target = (base_path / rel).resolve()
        if not str(target).startswith(str(base_path)):
            raise ValueError(f"Path traversal detected: {rel}")
        return str(target)

VERSION = "1.0.0"

# Mandatory 104db positional schema indexes based on the canonical spec:
# [0] Record_Type_Parent (string)
# [1] project_name (string, Record_Type_Parent: ProjectMeta)
# [2] version (string, Record_Type_Parent: ProjectMeta)
# [3] root_path (string, Record_Type_Parent: ProjectMeta)
# [4] file_path (string, Record_Type_Parent: FileContent)
# [5] file_name (string, Record_Type_Parent: FileContent)
# [6] content (string, Record_Type_Parent: FileContent)
# [7] is_binary (boolean, Record_Type_Parent: FileContent)
# [8] special_flag (string/optional, Record_Type_Parent: FileContent or ProjectMeta)

EXPECTED_104DB_FIELDS = [
    "Record_Type_Parent",
    "project_name",
    "version",
    "root_path",
    "file_path",
    "file_name",
    "content",
    "is_binary",
    "special_flag"
]


# Pulls the JSON text out of a larger text block (strips markdown fences / chatty preambles), e.g. an LLM reply that contains a 104db document.
def extract_raw_json(text: str) -> str:
    """Extracts raw JSON string from a text block, stripping markdown backticks or preambles."""
    text = text.strip()
    if "```json" in text:
        match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
    elif "```" in text:
        match = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
    
    # Try finding first '{' and last '}'
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end+1]
    return text


# Parses raw text/JSON into a BEJSON 104db document (a persisted _bejson_field_map key is discarded as untrusted) and checks it is valid 104db (Format_Version '104db', Record_Type_Parent discriminator, 2+ Records_Type). ONE file with several entities -- not an MFDB.
def parse_bejson_104db_doc(payload: str) -> Dict[str, Any]:
    """Parses raw text or JSON into a validated BEJSON 104db document structure."""
    json_str = extract_raw_json(payload)
    doc = json.loads(json_str)

    if not isinstance(doc, dict):
        raise ValueError("Decoded payload is not a valid JSON Object")
    doc.pop("_bejson_field_map", None)  # in-memory cache only; a parsed copy is untrusted

    if doc.get("Format") != "BEJSON":
        raise ValueError(f"Invalid Format: expected 'BEJSON', got '{doc.get('Format')}'")

    if doc.get("Format_Version") != "104db":
        raise ValueError(f"Invalid Format_Version: expected '104db', got '{doc.get('Format_Version')}'")

    records_type = doc.get("Records_Type", [])
    if "ProjectMeta" not in records_type or "FileContent" not in records_type:
        raise ValueError("Records_Type must include both 'ProjectMeta' and 'FileContent'")

    fields = doc.get("Fields", [])
    if not fields or fields[0].get("name") != "Record_Type_Parent":
        raise ValueError("Fields[0] must be 'Record_Type_Parent'")

    return doc


# Restores the files stored in a project-style 104db document (ProjectMeta rows + FileContent rows in the same file) to output_dir. Returns (project metadata, files written).
def unpack_bejson_104db_to_dir(doc: Dict[str, Any], output_dir: str) -> Tuple[Dict[str, Any], int]:
    """
    Unpacks a parsed BEJSON 104db document and restores all FileContent rows to output_dir.
    Returns (meta_dict, files_written_count).
    """
    out_root = Path(output_dir).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    fields = doc.get("Fields", [])
    field_map = {f["name"]: i for i, f in enumerate(fields)}

    # Field indexes
    rec_type_idx = field_map.get("Record_Type_Parent", 0)
    proj_name_idx = field_map.get("project_name", 1)
    version_idx = field_map.get("version", 2)
    root_path_idx = field_map.get("root_path", 3)
    file_path_idx = field_map.get("file_path", 4)
    file_name_idx = field_map.get("file_name", 5)
    content_idx = field_map.get("content", 6)
    is_binary_idx = field_map.get("is_binary", 7)
    special_flag_idx = field_map.get("special_flag", -1)

    project_meta = {}
    files_written = 0

    for row in doc.get("Values", []):
        if not row or len(row) <= rec_type_idx:
            continue

        rec_type = row[rec_type_idx]
        if rec_type == "ProjectMeta":
            project_meta = {
                "project_name": row[proj_name_idx] if proj_name_idx != -1 and proj_name_idx < len(row) else None,
                "version": row[version_idx] if version_idx != -1 and version_idx < len(row) else None,
                "root_path": row[root_path_idx] if root_path_idx != -1 and root_path_idx < len(row) else None,
                "special_flag": row[special_flag_idx] if special_flag_idx != -1 and special_flag_idx < len(row) else None,
            }
        elif rec_type == "FileContent":
            if file_path_idx == -1 or file_path_idx >= len(row) or not row[file_path_idx]:
                continue

            rel_path = str(row[file_path_idx])
            content = row[content_idx] if content_idx != -1 and content_idx < len(row) else ""
            is_bin = bool(row[is_binary_idx]) if is_binary_idx != -1 and is_binary_idx < len(row) and row[is_binary_idx] is not None else False
            special_flag = row[special_flag_idx] if special_flag_idx != -1 and special_flag_idx < len(row) else None

            target_path = Path(bejson_safe_join(str(out_root), rel_path))
            target_path.parent.mkdir(parents=True, exist_ok=True)

            if is_bin:
                target_path.write_bytes(base64.b64decode(content or ""))
            else:
                target_path.write_text(content or "", encoding="utf-8")

            files_written += 1

    return project_meta, files_written