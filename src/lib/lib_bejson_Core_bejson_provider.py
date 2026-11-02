"""
Library:         lib_bejson_Core_bejson_provider.py
Family:          Core
Module Purpose:  Default-schema provider: a 104a paths schema and a single-file 104db Category/Note index schema, with load/save helpers.
Architecture:    Provides default schemas for BEJSON Pad. The index schema is a single-file BEJSON 104db document (Record_Type_Parent discriminator, null-padding); the paths schema is BEJSON 104a. No MFDB.
Format_Scope:    104a (paths schema) + 104db (Note/Category index); NOT MFDB
Glossary:        BEJSON 104, 104a and 104db are the three file formats (Format_Version). 104db = ONE file holding 2+ entity types
                 (Record_Type_Parent discriminator, null-padding). MFDB is NOT a format and NOT 104db: it is a layer made of one 104a manifest
                 (104a.mfdb.bejson) plus dense 104 entity files linked by Parent_Hierarchy. MFDB-132 = an MFDB packed into one Chunked-104a document.
Version:         2.1.4
Release_Version: 300
Date:            2026-10-06
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   0e221771-74b3-4e7d-ae65-94854d165ba9
"""

import os
import json
import datetime
from lib_bejson_Core_bejson_core import bejson_core_atomic_write, bejson_core_get_field_map

class BEJSONProvider:
    # Returns the default BEJSON 104a document for the paths store (file-level metadata + one record type).
    # BEJSON 104a document (file-level metadata + one record type).
    @staticmethod
    def get_paths_schema():
        return {"Format": "BEJSON", "Format_Version": "104a", "Format_Creator": "Elton Boehnen", "Schema_Version": "v1.0", "Application_Name": "BEJSON Pad", "Records_Type": ["PathEntry"], "Fields": [{"name": "path_id", "type": "string"}, {"name": "path_type", "type": "string"}, {"name": "path", "type": "string"}, {"name": "label", "type": "string"}, {"name": "created_at", "type": "string"}], "Values": []}

    # Returns the default 104db document for the Pad index: ONE file with two entities (Category, Note) using Record_Type_Parent and null-padding. Single-file format, not MFDB.
    # BEJSON 104db document: ONE file, two entities (Category, Note), Record_Type_Parent discriminator, null-padding. Not MFDB.
    @staticmethod
    def get_index_schema():
        return {"Format": "BEJSON", "Format_Version": "104db", "Format_Creator": "Elton Boehnen", "Records_Type": ["Category", "Note"], "Fields": [{"name": "Record_Type_Parent", "type": "string"}, {"name": "cat_id", "type": "string", "Record_Type_Parent": "Category"}, {"name": "cat_name", "type": "string", "Record_Type_Parent": "Category"}, {"name": "created_at_cat", "type": "string", "Record_Type_Parent": "Category"}, {"name": "note_id", "type": "string", "Record_Type_Parent": "Note"}, {"name": "note_name", "type": "string", "Record_Type_Parent": "Note"}, {"name": "cat_id_fk", "type": "string", "Record_Type_Parent": "Note"}, {"name": "file_path", "type": "string", "Record_Type_Parent": "Note"}, {"name": "created_at_note", "type": "string", "Record_Type_Parent": "Note"}, {"name": "updated_at", "type": "string", "Record_Type_Parent": "Note"}], "Values": []}

    # Loads a BEJSON file, or returns default_schema when the file does not exist. A persisted _bejson_field_map key is discarded (untrusted cache).
    @staticmethod
    def load_bejson(path, default_schema):
        if os.path.exists(path):
            with open(path, 'r') as f:
                doc = json.load(f)
            if isinstance(doc, dict): doc.pop("_bejson_field_map", None)  # in-memory cache only
            return doc
        return default_schema

    # Atomically saves a BEJSON document via bejson_core_atomic_write.
    @staticmethod
    def save_bejson(path, data):
        bejson_core_atomic_write(path, data)

    # Deprecated alias: delegates to bejson_core_get_field_map.
    @staticmethod
    def get_fields_map(db):
        """DEPRECATED: Delegates to bejson_core_get_field_map."""
        return bejson_core_get_field_map(db)

    # Current UTC time as an ISO-8601 string (YYYY-MM-DDTHH:MM:SSZ).
    @staticmethod
    def now_iso(): return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")