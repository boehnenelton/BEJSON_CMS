"""
Library:      lib_bejson_provider.py
Family:       Core
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.1.1 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-06-05
Description:  Data provider interface for abstracted BEJSON storage access.
REMEDIATED:   Purged transition stubs for Core (Phase 1).
"""

import os
import json
import datetime
from lib_bejson_core import bejson_core_atomic_write, bejson_core_get_field_map

class BEJSONProvider:
    @staticmethod
    def get_paths_schema():
        return {"Format": "BEJSON", "Format_Version": "104a", "Format_Creator": "Elton Boehnen", "Schema_Version": "v1.0", "Application_Name": "BEJSON Pad", "Records_Type": ["PathEntry"], "Fields": [{"name": "path_id", "type": "string"}, {"name": "path_type", "type": "string"}, {"name": "path", "type": "string"}, {"name": "label", "type": "string"}, {"name": "created_at", "type": "string"}], "Values": []}

    @staticmethod
    def get_index_schema():
        return {"Format": "BEJSON", "Format_Version": "104db", "Format_Creator": "Elton Boehnen", "Records_Type": ["Category", "Note"], "Fields": [{"name": "Record_Type_Parent", "type": "string"}, {"name": "cat_id", "type": "string", "Record_Type_Parent": "Category"}, {"name": "cat_name", "type": "string", "Record_Type_Parent": "Category"}, {"name": "created_at_cat", "type": "string", "Record_Type_Parent": "Category"}, {"name": "note_id", "type": "string", "Record_Type_Parent": "Note"}, {"name": "note_name", "type": "string", "Record_Type_Parent": "Note"}, {"name": "cat_id_fk", "type": "string", "Record_Type_Parent": "Note"}, {"name": "file_path", "type": "string", "Record_Type_Parent": "Note"}, {"name": "created_at_note", "type": "string", "Record_Type_Parent": "Note"}, {"name": "updated_at", "type": "string", "Record_Type_Parent": "Note"}], "Values": []}

    @staticmethod
    def load_bejson(path, default_schema):
        if os.path.exists(path):
            with open(path, 'r') as f: return json.load(f)
        return default_schema

    @staticmethod
    def save_bejson(path, data):
        # FIX: Transitioned to atomic write for consistency and safety
        bejson_core_atomic_write(path, data)

    @staticmethod
    def get_fields_map(db):
        """DEPRECATED: Delegates to bejson_core_get_field_map."""
        return bejson_core_get_field_map(db)

    @staticmethod
    def now_iso(): return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
