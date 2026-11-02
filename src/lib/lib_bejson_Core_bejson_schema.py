"""
Library:         lib_bejson_Core_bejson_schema.py
Family:          Core
Module Purpose:  Schema field-list registry (project v1.4.0, chunker v5 entity/manifest) plus schema extract and validate-against helpers.
Architecture:    Format-level BEJSON layer that works on any BEJSON document (104, 104a, 104db) through positional Fields/Values and the field-map cache. It does not orchestrate MFDB and is not specific to 104db.
Format_Scope:    104 | 104a | 104db (generic)
Glossary:        BEJSON 104, 104a and 104db are the three file formats (Format_Version). 104db = ONE file holding 2+ entity types
                 (Record_Type_Parent discriminator, null-padding). MFDB is NOT a format and NOT 104db: it is a layer made of one 104a manifest
                 (104a.mfdb.bejson) plus dense 104 entity files linked by Parent_Hierarchy. MFDB-132 = an MFDB packed into one Chunked-104a document.
Version:         2.3.4
Release_Version: 300
Date:            2026-10-02
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   afa11f6c-77ee-4163-b98e-64773e0b18aa
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# ===========================================================================
# AUTHORITATIVE SCHEMA DEFINITIONS
# ===========================================================================

# 1. Project Management v1.4.0 (22 Fields)
# Field list for ProjectService records (snake_case names per BEJSON spec §14.7).
# The lowercase 'record_type_parent' column is a snake_case discriminator. BEJSON 104db requires
# the exact name 'Record_Type_Parent' plus per-field Record_Type_Parent ownership, so this list is not
# a valid 104db Fields array by itself.
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
# Authoritative for project file contents. Entity-file field list: dense BEJSON 104, one entity per file,
# no Record_Type_Parent column (that discriminator exists only in 104db).
SCHEMA_MFDB_ENTITY_v5 = [
    {"name": "version",   "type": "string"},
    {"name": "file_path", "type": "string"},
    {"name": "file_name", "type": "string"},
    {"name": "content",   "type": "string"},
    {"name": "is_binary", "type": "boolean"},
    {"name": "is_base64", "type": "boolean"},
]

# 3. MFDB Chunker v5 Manifest (9 Fields)
# Row fields of the BEJSON 104a manifest (104a.mfdb.bejson) that registers the entity files.
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

# 4. AI Model Registry — Gemini v2.1.2
# Named SCHEMA_MODEL_REGISTRY_GEMINI to stay distinct from SCHEMA_MODEL_REGISTRY_OPENROUTER (openrouter.py).
SCHEMA_MODEL_REGISTRY_GEMINI = {
    "Format": "BEJSON",
    "Format_Version": "104a",
    "Format_Creator": "Elton Boehnen",
    "Records_Type": ["AI_Model"],
    "Fields": [
        {"name": "display_name",          "type": "string"},  # 0
        {"name": "model_id",              "type": "string"},  # 1
        {"name": "currently_active",      "type": "boolean"}, # 2
        {"name": "thinking_enabled",      "type": "boolean"}, # 3
        {"name": "google_search_enabled", "type": "boolean"}, # 4
        {"name": "flag",                  "type": "string"},  # 5 (unused; e.g. "paid")
        {"name": "service",               "type": "string"},  # 6 (unused; e.g. "image")
    ],
    "Values": [
        ["Gemini 3.6 Flash", "gemini-3.6-flash", True, True, True, "", ""],
        ["Gemini 3.1 Pro (Preview)", "gemini-3.1-pro-preview", False, True, True, "", ""],
        ["Gemini 3.1 Flash-Lite", "gemini-3.1-flash-lite", False, False, False, "", ""],
        ["Gemini 2.5 Flash", "gemini-2.5-flash", False, False, False, "", ""]
    ]
}

# ===========================================================================
# UTILITY FUNCTIONS
# ===========================================================================

# Returns a copy of a document's schema: all header keys and Fields, with Values emptied. Works for any BEJSON version.
def bejson_schema_extract(doc: Dict[str, Any]) -> Dict[str, Any]:
    schema = doc.copy()
    schema["Values"] = []
    return schema

# True when the document's Fields match schema_fields in count, names and types (order-sensitive).
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