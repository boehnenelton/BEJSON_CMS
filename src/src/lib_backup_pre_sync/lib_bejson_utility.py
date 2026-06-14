"""
Library:      lib_bejson_utility.py
Family:       Utility
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.3.1 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-06-05
Description:  Cross-compatible chunking utilities for CLI_CHUNKER and MFDB_V5.
REMEDIATED:   Purged transition stubs for Core (Phase 1).
"""

import os
import sys
import json
import time
import base64
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Sibling Path Resolution
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_LIB_DIR = os.path.dirname(CURRENT_DIR)
CORE_DIR = os.path.join(PARENT_LIB_DIR, "Core")
if CORE_DIR not in sys.path:
    sys.path.append(CORE_DIR)

from lib_bejson_core import (
    bejson_core_atomic_write,
    bejson_core_get_field_map,
    bejson_core_create_104db
)

# ---------------------------------------------------------------------------
# Constants & Official Schemas
# ---------------------------------------------------------------------------

DEFAULT_EXTENSIONS = [".py", ".js", ".ts", ".html", ".css", ".md", ".json", ".sh", ".txt", ".bejson", ".tsx", ".jsx"]
DEFAULT_EXCLUDES = [".git", "__pycache__", "node_modules", "lib", "output", ".mfdb_lock", "dist", "build"]

# --- Legacy Fallback Constants (Phase 7.3.2) ---
_UTILITY_PY_LEGACY = {
    "ProjectMeta": {"project_name": 1, "version": 2, "root_path": 3},
    "FileContent": {"file_path": 4, "file_name": 5, "content": 6, "is_binary": 7},
    "MFDB_Entity": {"version": 0, "file_path": 1, "file_name": 2, "content": 3, "is_binary": 4, "is_base64": 5}
}

# Text Chunk Separators (Standardized)
SEP_START = "--- FILE: "
SEP_END = " ---"

# Official CLI_CHUNKER Schema (BEJSON 104db)
SCHEMA_CLI_CHUNKER = [
    {"name": "Record_Type_Parent", "type": "string"},
    {"name": "project_name", "type": "string", "Record_Type_Parent": "ProjectMeta"},
    {"name": "version", "type": "string", "Record_Type_Parent": "ProjectMeta"},
    {"name": "root_path", "type": "string", "Record_Type_Parent": "ProjectMeta"},
    {"name": "file_path", "type": "string", "Record_Type_Parent": "FileContent"},
    {"name": "file_name", "type": "string", "Record_Type_Parent": "FileContent"},
    {"name": "content", "type": "string", "Record_Type_Parent": "FileContent"},
    {"name": "is_binary", "type": "boolean", "Record_Type_Parent": "FileContent"}
]

# Official MFDB_V5 Entity Schema (BEJSON 104)
SCHEMA_MFDB_ENTITY = [
    {"name": "version",   "type": "string"},
    {"name": "file_path", "type": "string"},
    {"name": "file_name", "type": "string"},
    {"name": "content",   "type": "string"},
    {"name": "is_binary", "type": "boolean"},
    {"name": "is_base64", "type": "boolean"},
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_row_template(fields: List[Dict], rtp: str = None) -> Dict[str, int]:
    """Internal helper to build a field map for record creation."""
    return {f["name"]: i for i, f in enumerate(fields) if rtp is None or f.get("Record_Type_Parent") == rtp or f.get("name") == "Record_Type_Parent"}

# ---------------------------------------------------------------------------
# Cross-Format Generators
# ---------------------------------------------------------------------------

def bejson_utility_create_cli_chunk(target_dir: str, project_name: str, version: str) -> dict:
    """Generates a BEJSON 104db document compatible with Cli_Chunker."""
    target_path = Path(target_dir).resolve()
    values = []
    
    # Dynamic Field Mapping for Creation (Phase 7.3.4)
    fm = {f["name"]: i for i, f in enumerate(SCHEMA_CLI_CHUNKER)}
    f_count = len(SCHEMA_CLI_CHUNKER)

    # Meta record
    meta_row = [None] * f_count
    meta_row[fm["Record_Type_Parent"]] = "ProjectMeta"
    meta_row[fm["project_name"]]       = project_name
    meta_row[fm["version"]]            = version
    meta_row[fm["root_path"]]          = str(target_path)
    values.append(meta_row)
    
    for root, dirs, files in os.walk(target_path):
        dirs[:] = [d for d in dirs if d not in DEFAULT_EXCLUDES]
        for file in files:
            f_path = Path(root) / file
            if f_path.suffix.lower() in DEFAULT_EXTENSIONS:
                try:
                    rel_path = f_path.relative_to(target_path)
                    content, binary, _ = bejson_utility_encode_file(f_path, use_base64=False)
                    
                    file_row = [None] * f_count
                    file_row[fm["Record_Type_Parent"]] = "FileContent"
                    file_row[fm["file_path"]]          = str(rel_path)
                    file_row[fm["file_name"]]          = file
                    file_row[fm["content"]]            = content
                    file_row[fm["is_binary"]]          = binary
                    values.append(file_row)
                except Exception: continue
                
    return bejson_core_create_104db(["ProjectMeta", "FileContent"], SCHEMA_CLI_CHUNKER, values)

def bejson_utility_create_mfdb_version(target_dir: str, version: str, use_base64: bool = True) -> list:
    """
    Generates a list of values for an MFDB v5 Entity file (BEJSON 104).
    """
    target_path = Path(target_dir).resolve()
    rows = []
    
    fm = {f["name"]: i for i, f in enumerate(SCHEMA_MFDB_ENTITY)}
    f_count = len(SCHEMA_MFDB_ENTITY)
    
    for root, dirs, files in os.walk(target_path):
        dirs[:] = [d for d in dirs if d not in DEFAULT_EXCLUDES]
        for file in files:
            f_path = Path(root) / file
            if f_path.suffix.lower() in DEFAULT_EXTENSIONS:
                try:
                    rel_path = f_path.relative_to(target_path)
                    content, binary, b64 = bejson_utility_encode_file(f_path, use_base64=use_base64)
                    
                    row = [None] * f_count
                    row[fm["version"]]   = version
                    row[fm["file_path"]] = str(rel_path)
                    row[fm["file_name"]] = file
                    row[fm["content"]]   = content
                    row[fm["is_binary"]] = binary
                    row[fm["is_base64"]] = b64
                    rows.append(row)
                except Exception: continue
                
    return rows

# ---------------------------------------------------------------------------
# Text Chunking Logic (Non-Regex Implementation)
# ---------------------------------------------------------------------------

def bejson_utility_chunk_to_text(target_dir: str) -> str:
    """Concatenates files into a single text block with separators."""
    target_path = Path(target_dir).resolve()
    output = []
    
    for root, dirs, files in os.walk(target_path):
        dirs[:] = [d for d in dirs if d not in DEFAULT_EXCLUDES]
        for file in files:
            f_path = Path(root) / file
            if f_path.suffix.lower() in DEFAULT_EXTENSIONS and not bejson_utility_is_binary(f_path):
                try:
                    rel_path = f_path.relative_to(target_path)
                    content = f_path.read_text(encoding="utf-8")
                    output.append(f"{SEP_START}{rel_path}{SEP_END}")
                    output.append(content)
                    output.append("\n")
                except Exception: continue
                
    return "\n".join(output)

def bejson_utility_unchunk_from_text(text: str, output_dir: str) -> int:
    """Restores files from a text block using strictly string splitting."""
    count = 0
    out_root = Path(output_dir).resolve()
    
    # Split by the start separator
    parts = text.split(SEP_START)
    
    for part in parts:
        if not part.strip(): continue
        
        # Each part starts with: filename --- content
        if SEP_END in part:
            header, content = part.split(SEP_END, 1)
            rel_path = header.strip()
            
            if rel_path:
                target_file = out_root / rel_path
                target_file.parent.mkdir(parents=True, exist_ok=True)
                target_file.write_text(content.lstrip("\n"), encoding="utf-8")
                count += 1
                
    return count

# ---------------------------------------------------------------------------
# Lifecycle Utilities (Standard JSON Module)
# ---------------------------------------------------------------------------

def bejson_utility_parse_json(text: str) -> Any:
    """Robust JSON parsing using strictly the json module."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Best practice: try to find the actual JSON object in a dirty string
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end+1])
        raise

def bejson_utility_save_chunk(path: str, doc: dict) -> bool:
    """Standardized atomic write for all chunking operations."""
    return BEJSONCore.bejson_core_atomic_write(path, doc)

def bejson_utility_get_timestamp() -> str:
    """ISO 8601 UTC timestamp for manifest consistency."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
