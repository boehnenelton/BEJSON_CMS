"""
Library:         lib_bejson_Core_bejson_static_backend.py
Family:          Core
Module Purpose:  Flat-file dataset resolver: loads a plain BEJSON file or, given a 104a.mfdb.bejson manifest, the MFDB's entity files.
Architecture:    Read-side backend that accepts either a standalone BEJSON file or an MFDB manifest (104a.mfdb.bejson) and resolves its entity files. It performs no 104db handling.
Format_Scope:    Reads standalone BEJSON files and MFDB manifests (detected by the filename 104a.mfdb.bejson)
Glossary:        BEJSON 104, 104a and 104db are the three file formats (Format_Version). 104db = ONE file holding 2+ entity types
                 (Record_Type_Parent discriminator, null-padding). MFDB is NOT a format and NOT 104db: it is a layer made of one 104a manifest
                 (104a.mfdb.bejson) plus dense 104 entity files linked by Parent_Hierarchy. MFDB-132 = an MFDB packed into one Chunked-104a document.
Version:         2.1.4
Release_Version: 300
Date:            2026-10-06
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   09f40ba6-9cbf-4922-a465-f3ffa512a12f
"""

import os
import json
import datetime

class BEJSONBackend:
    # Sets the root path (default is the {ADMIN_ROOT} placeholder).
    def __init__(self, root_path=None):
        # Default root is the {ADMIN_ROOT} placeholder
        self.root = root_path or "{ADMIN_ROOT}"

    # Reads a JSON file; None if it does not exist. A persisted _bejson_field_map key is discarded (untrusted cache).
    def _load_json(self, path):
        if not os.path.exists(path): return None
        with open(path, 'r') as f:
            doc = json.load(f)
        if isinstance(doc, dict): doc.pop("_bejson_field_map", None)  # in-memory cache only
        return doc

    # Loads source_path. If it is an MFDB manifest (file name 104a.mfdb.bejson) returns all entity files via _load_mfdb; otherwise returns the single BEJSON document. 104db files are treated as ordinary single documents.
    def resolve_dataset(self, source_path):
        data = self._load_json(source_path)
        if not data: return {}
        # Only a 104a.mfdb.bejson manifest is treated as an MFDB; any other file is a standalone BEJSON document.
        is_mfdb = os.path.basename(source_path) == "104a.mfdb.bejson"
        if is_mfdb:
            return self._load_mfdb(source_path, data)
        else:
            name = os.path.splitext(os.path.basename(source_path))[0]
            return {
                name: {
                    "fields": data.get("Fields", []),
                    "values": data.get("Values", []),
                    "metadata": {"Format": data.get("Format"), "Version": data.get("Format_Version"), "Path": source_path}
                }
            }

    # Reads each entity listed in the MFDB manifest (file_path relative to the manifest directory) and returns {entity_name: document}.
    def _load_mfdb(self, manifest_path, manifest_data):
        mfdb_root = os.path.dirname(manifest_path)
        entities = {}
        headers = [f['name'] for f in manifest_data['Fields']]
        
        try:
            idx_name = headers.index("entity_name")
            idx_path = headers.index("file_path")
        except ValueError:
            # Fallback for older non-standard manifests if they exist
            try:
                idx_name = headers.index("Entity_Name")
                idx_path = headers.index("Entity_File_Path")
            except ValueError:
                print(f"Error: Invalid MFDB Manifest structure at {manifest_path}")
                return {}

        for row in manifest_data['Values']:
            e_name = row[idx_name]
            e_rel_path = row[idx_path]
            e_abs_path = os.path.join(mfdb_root, e_rel_path)
            e_data = self._load_json(e_abs_path)
            if e_data:
                entities[e_name] = {
                    "fields": e_data.get("Fields", []),
                    "values": e_data.get("Values", []),
                    "metadata": {"Entity_Name": e_name, "Path": e_abs_path, "Parent_MFDB": manifest_path}
                }
        return entities

    # Flattens the resolved dataset(s) into text context blocks for read-only use.
    def get_static_context(self, source_path):
        datasets = self.resolve_dataset(source_path)
        contexts = []
        for name, data in datasets.items():
            contexts.append({
                "page_title": name.replace("_", " ").title(),
                "file_name": f"{name.lower()}.html",
                "headers": [f['name'] for f in data['fields']],
                "rows": data['values'],
                "metadata": data['metadata']
            })
        return contexts

if __name__ == "__main__":
    backend = BEJSONBackend()
    print("Backend Library Loaded.")