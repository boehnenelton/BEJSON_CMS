"""
Library:         lib_bejson_Core_bejson_list_validator.py
Family:          Core
Module Purpose:  Validates list/hierarchy-shaped documents (id/parent_id) on 104 or 104a; the caller loads the document (often an MFDB entity file).
Architecture:    Format-level BEJSON layer that works on any BEJSON document (104, 104a, 104db) through positional Fields/Values and the field-map cache. It does not orchestrate MFDB and is not specific to 104db.
Format_Scope:    104 | 104a | 104db (generic)
Glossary:        BEJSON 104, 104a and 104db are the three file formats (Format_Version). 104db = ONE file holding 2+ entity types
                 (Record_Type_Parent discriminator, null-padding). MFDB is NOT a format and NOT 104db: it is a layer made of one 104a manifest
                 (104a.mfdb.bejson) plus dense 104 entity files linked by Parent_Hierarchy. MFDB-132 = an MFDB packed into one Chunked-104a document.
Version:         1.3.5
Release_Version: 300
Date:            2026-10-02
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   bd20ddfc-900f-46b7-9a46-71d772e44b03
"""

from typing import Any, Dict
import lib_bejson_Core_bejson_validator as StandardValidator
import lib_bejson_Core_bejson_core as BEJSONCore

# Validates a list/hierarchy-shaped document (id / parent_id style rows) that is already loaded: format version must be 104 or 104a, required id fields present, parent references resolve, no cycles. The caller loads the document -- for an MFDB it is an entity file (104). Returns a result dict (valid, errors).
def validate_list(doc_data: dict) -> Dict[str, Any]:
    """
    doc_data: an already-loaded BEJSON document dict (e.g. from
    BEJSONCore.bejson_core_load_file() or MFDBCore.mfdb_core_get_entity_doc()).
    This function performs no file I/O; the caller (typically MFDBCore) loads the document.
    """
    # 1. Structural Validation (Sourced from Core) -- validate_bejson() accepts a dict directly
    # (is_file=False), so no file path is needed.
    res = StandardValidator.validate_bejson(doc_data, is_file=False)
    if not res.valid:
        return {"is_valid": False, "errors": res.errors}

    doc = doc_data

    # 2. BEJSON Format Version Constraint
    # Accepts both "104a" (standalone list documents) and "104" (MFDBCore entity docs, which carry
    # Parent_Hierarchy instead of being manifests themselves). MFDBCore.mfdb_core_get_entity_doc()
    # returns entity docs as Format_Version "104"; the hierarchy check below only needs id/parent_id,
    # not which of the two list-shaped formats the doc uses.
    if doc.get("Format_Version") not in ("104a", "104"):
        return {"is_valid": False, "errors": ["List Manager requires BEJSON 104 or 104a format."]}

    # 3. List Logic (Hierarchy & Integrity)
    values = doc.get("Values", [])
    # Field map from the BEJSONCore cache
    f_map = BEJSONCore.bejson_core_get_field_map(doc)
    if "id" not in f_map or "parent_id" not in f_map:
        return {"is_valid": False, "errors": ["Missing core list fields: id, parent_id"]}
        
    id_idx = f_map["id"]
    pid_idx = f_map["parent_id"]
    
    ids = set()
    parent_refs = {}
    
    for i, row in enumerate(values):
        uid = row[id_idx]
        pid = row[pid_idx]
        if uid in ids:
            return {"is_valid": False, "errors": [f"Duplicate ID detected: {uid}"]}
        ids.add(uid)
        if pid: parent_refs[uid] = pid

    for uid, pid in parent_refs.items():
        if pid not in ids:
            return {"is_valid": False, "errors": [f"Orphan detected: {uid} -> {pid}"]}
        path = {uid}
        curr = pid
        while curr:
            if curr in path:
                return {"is_valid": False, "errors": [f"Circular dependency: {uid}"]}
            path.add(curr)
            curr = parent_refs.get(curr)

    return {"is_valid": True, "errors": [], "stats": {"item_count": len(ids)}}

if __name__ == "__main__":
    print("Python List Validator v1.3.0 Loaded (I/O decoupled, error branch fixed).")