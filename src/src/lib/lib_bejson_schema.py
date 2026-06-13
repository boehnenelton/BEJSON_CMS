"""
Library:      lib_bejson_schema.py
Family:       Core
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.1.2 OFFICIAL (Unified Schema Registry)
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-06-05
Description:  Unified registry for authoritative BEJSON schemas.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# ===========================================================================
# AUTHORITATIVE SCHEMA DEFINITIONS
# ===========================================================================

# 1. Project Management v1.4.0 (22 Fields)
# Aligns ProjectService with official tracking standards.
# FIX PY3: field names corrected from PascalCase to snake_case per BEJSON spec §14.7.
# NOTE: This is a breaking schema migration — any persisted data using old field names
#       (Project_ID, Project_Name, etc.) must be migrated before using this schema.
SCHEMA_PROJECT_v140 = [
    {"name": "record_type_parent",    "type": "string"},  # 0
    {"name": "project_id",            "type": "string"},  # 1
    {"name": "project_name",          "type": "string"},  # 2
    {"name": "project_path",          "type": "string"},  # 3
    {"name": "version",               "type": "string"},  # 4
    {"name": "created_at",            "type": "string"},  # 5
    {"name": "project_type",          "type": "string"},  # 6
    {"name": "is_active",             "type": "boolean"}, # 7
    {"name": "is_visible",            "type": "boolean"}, # 8
    {"name": "is_missing",            "type": "boolean"}, # 9
    {"name": "description",           "type": "string"},  # 10
    {"name": "tags",                  "type": "string"},  # 11
    {"name": "primary_agent",         "type": "string"},  # 12
    {"name": "last_sync",             "type": "string"},  # 13
    {"name": "file_count",            "type": "integer"}, # 14
    {"name": "total_size_kb",         "type": "number"},  # 15
    {"name": "git_enabled",           "type": "boolean"}, # 16
    {"name": "priority",              "type": "integer"}, # 17
    {"name": "category",              "type": "string"},  # 18
    {"name": "internal_notes",        "type": "string"},  # 19
    {"name": "is_archived",           "type": "boolean"}, # 20
    {"name": "is_reset_protected",    "type": "boolean"}, # 21
]

# 2. MFDB Chunker v5 Entity (6 Fields)
# Authoritative for project file contents.
SCHEMA_MFDB_ENTITY_v5 = [
    {"name": "version",   "type": "string"},
    {"name": "file_path", "type": "string"},
    {"name": "file_name", "type": "string"},
    {"name": "content",   "type": "string"},
    {"name": "is_binary", "type": "boolean"},
    {"name": "is_base64", "type": "boolean"},
]

# 3. MFDB Chunker v5 Manifest (9 Fields)
SCHEMA_MFDB_MANIFEST_v5 = [
    {"name": "entity_name",    "type": "string"},
    {"name": "file_path",      "type": "string"},
    {"name": "description",    "type": "string"},
    {"name": "record_count",   "type": "integer"},
    {"name": "schema_version", "type": "string"},
    {"name": "primary_key",    "type": "string"},
    {"name": "changelog",      "type": "string"},
    {"name": "chunked_at",     "type": "string"},
    {"name": "tags",           "type": "string"},
]

# 4. AI Model Registry v2.1.2 (Positional Integrity Fix)
# Defaulted to Gemini 2.5 Flash as per audit recommendation.
# RE-ALIGNED: Reverted to legacy indices to maintain backward compatibility.
SCHEMA_MODEL_REGISTRY = {
    "Format": "BEJSON",
    "Format_Version": "104a",
    "Format_Creator": "Elton Boehnen",
    "Records_Type": ["AI_Model"],
    "Fields": [
        {"name": "display_name",          "type": "string"},  # 0
        {"name": "model_id",              "type": "string"},  # 1
        {"name": "currently_active",      "type": "boolean"}, # 2
        {"name": "thinking_enabled",      "type": "boolean"}, # 3
        {"name": "google_search_enabled", "type": "boolean"}  # 4
    ],
    "Values": [
        ["Gemini 2.5 Flash", "gemini-2.5-flash", True, False, True],
        ["Gemini 2.0 Flash Thinking", "gemini-2.0-flash-thinking-preview", False, True, False],
        ["Gemini 3.1 Pro (Preview)", "gemini-3.1-pro-preview", False, False, True]
    ]
}

# ===========================================================================
# UTILITY FUNCTIONS
# ===========================================================================

def bejson_schema_extract(doc: Dict[str, Any]) -> Dict[str, Any]:
    schema = doc.copy()
    schema["Values"] = []
    return schema

def bejson_schema_validate_against(doc: Dict[str, Any], schema_fields: List[Dict[str, Any]]) -> bool:
    doc_fields = doc.get("Fields", [])
    if len(doc_fields) != len(schema_fields):
        return False
    for i, (df, sf) in enumerate(zip(doc_fields, schema_fields)):
        if df.get("name") != sf.get("name") or df.get("type") != sf.get("type"):
            return False
    return True


# 5. List Manager v1.0.0
# Authoritative for hierarchical list data used in JS Lister.
SCHEMA_LIST_MANAGER_v100 = [
    {"name": "id",          "type": "string"},  # Unique identifier
    {"name": "parent_id",   "type": "string"},  # Parent ID for hierarchy (null for root)
    {"name": "title",       "type": "string"},  # Item title
    {"name": "description", "type": "string"},  # Detailed description
]
