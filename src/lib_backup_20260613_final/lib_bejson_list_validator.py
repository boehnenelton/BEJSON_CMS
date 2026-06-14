"""
Library:      lib_bejson_list_validator.py
Family:       Core
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      1.1.1 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-21
Description:  Hierarchical list validator. Extends standard structural validator.
REMEDIATED:   Fixed attribute call to bejson_core_load_file via standard access.
"""

from typing import Any, Dict, List, Set
import lib_bejson_validator as StandardValidator
import lib_bejson_core as BEJSONCore

def validate_list(doc_path: str) -> Dict[str, Any]:
    # 1. Structural Validation (Sourced from Core)
    res = StandardValidator.validate_bejson(doc_path, is_file=True)
    if not res.valid:
        return {"is_valid": False, "errors": res.errors}

    # Use core library for direct loading
    doc = BEJSONCore.bejson_core_load_file(doc_path)
    
    # 2. BEJSON 104a Metadata Constraint
    if doc.get("Format_Version") != "104a":
        return {"is_valid": False, "errors": ["List Manager requires BEJSON 104a format."]}

    # 3. List Logic (Hierarchy & Integrity)
    fields = doc.get("Fields", [])
    values = doc.get("Values", [])
    
    f_map = {f["name"]: i for i, f in enumerate(fields)}
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
    print("Python List Validator v1.1.1 Loaded (Remediated).")
