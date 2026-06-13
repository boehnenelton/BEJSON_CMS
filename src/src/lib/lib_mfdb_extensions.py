"""
Library:      lib_mfdb_extensions.py
Family:       CMS
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.0.1 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-18
Description:  Plugin architecture for extending MFDB core capabilities.
"""

import os
import shutil
import zipfile
from pathlib import Path
from typing import Any, Callable

from lib_bejson_core import (
    bejson_core_load_file,
    bejson_core_atomic_write,
)
from lib_mfdb_core import (
    MFDBCoreError,
    E_MFDB_CORE_ENTITY_NOT_FOUND,
    E_MFDB_CORE_WRITE_FAILED,
    _load_json,
    _write_manifest_doc,
    _resolve_entity_path,
    _get_entity_path,
)

# ---------------------------------------------------------------------------
# MIGRATIONS
# ---------------------------------------------------------------------------

def mfdb_ext_rename_entity(manifest_path: str, old_name: str, new_name: str) -> None:
    """
    Rename an entity in the manifest and update its entity file's Records_Type.
    Does not change the file path.
    """
    doc = _load_json(manifest_path)
    fn_list = [f["name"] for f in doc["Fields"]]
    en_idx = fn_list.index("entity_name")
    
    found = False
    for row in doc["Values"]:
        if row[en_idx] == old_name:
            row[en_idx] = new_name
            found = True
            break
            
    if not found:
        raise MFDBCoreError(f"Entity '{old_name}' not found.", E_MFDB_CORE_ENTITY_NOT_FOUND)
        
    # Update manifest
    _write_manifest_doc(doc, manifest_path)
    
    # Update entity file
    entity_path = _get_entity_path(manifest_path, new_name) # Note: we use new_name because manifest was updated
    edoc = bejson_core_load_file(entity_path)
    edoc["Records_Type"] = [new_name]
    bejson_core_atomic_write(entity_path, edoc)


def mfdb_ext_move_entity_file(manifest_path: str, entity_name: str, new_rel_path: str) -> None:
    """
    Move an entity file to a new relative path and update the manifest.
    Also updates the entity's Parent_Hierarchy to ensure it points back to the manifest.
    """
    manifest_dir = os.path.dirname(os.path.abspath(manifest_path))
    old_abs_path = _get_entity_path(manifest_path, entity_name)
    new_abs_path = os.path.normpath(os.path.join(manifest_dir, new_rel_path))
    
    if os.path.exists(new_abs_path):
        raise MFDBCoreError(f"Target path already exists: {new_abs_path}", E_MFDB_CORE_WRITE_FAILED)
        
    # 1. Create target directory
    os.makedirs(os.path.dirname(new_abs_path), exist_ok=True)
    
    # 2. Load and update Parent_Hierarchy
    edoc = bejson_core_load_file(old_abs_path)
    entity_dir = os.path.dirname(new_abs_path)
    rel_to_manifest = os.path.relpath(manifest_path, entity_dir)
    edoc["Parent_Hierarchy"] = rel_to_manifest
    
    # 3. Write to new location
    bejson_core_atomic_write(new_abs_path, edoc)
    
    # 4. Update manifest
    doc = _load_json(manifest_path)
    fn_list = [f["name"] for f in doc["Fields"]]
    en_idx = fn_list.index("entity_name")
    fp_idx = fn_list.index("file_path")
    
    for row in doc["Values"]:
        if row[en_idx] == entity_name:
            row[fp_idx] = new_rel_path
            break
    _write_manifest_doc(doc, manifest_path)
    
    # 5. Remove old file
    os.unlink(old_abs_path)


# ---------------------------------------------------------------------------
# INTEGRITY CHECKS
# ---------------------------------------------------------------------------

def mfdb_ext_verify_referential_integrity(manifest_path: str) -> dict:
    """
    Check all _fk fields across all entities to ensure they resolve to valid PKs.
    Returns a dict of orphans: { entity_name: { field_name: [invalid_values] } }
    """
    from lib_mfdb_core import mfdb_core_load_manifest, mfdb_core_load_entity, mfdb_core_build_index
    
    manifest = mfdb_core_load_manifest(manifest_path)
    pk_map = {} # entity_name -> {pk_value: True}
    
    # Build PK indexes
    for entry in manifest:
        name = entry["entity_name"]
        pk_field = entry.get("primary_key")
        if pk_field:
            try:
                pk_map[name] = mfdb_core_build_index(manifest_path, name, pk_field)
            except Exception:
                pk_map[name] = {}
                
    orphans = {}
    
    # Check FKs
    for entry in manifest:
        name = entry["entity_name"]
        records = mfdb_core_load_entity(manifest_path, name)
        if not records: continue
        
        entity_orphans = {}
        for field in records[0].keys():
            if field.endswith("_fk"):
                # Determine target entity
                # Convention: <entity_lower>_id_fk or <entity_lower>_fk
                target_entity = None
                for potential_target in pk_map.keys():
                    if potential_target.lower() in field.lower():
                        target_entity = potential_target
                        break
                
                if not target_entity: continue
                
                invalid_values = []
                for rec in records:
                    val = rec.get(field)
                    if val is not None and val not in pk_map[target_entity]:
                        invalid_values.append(val)
                
                if invalid_values:
                    entity_orphans[field] = list(set(invalid_values))
        
        if entity_orphans:
            orphans[name] = entity_orphans
            
    return orphans


# ---------------------------------------------------------------------------
# BUNDLING / BACKUP
# ---------------------------------------------------------------------------

def mfdb_ext_export_bundle(manifest_path: str, output_zip: str) -> None:
    """
    Create a ZIP bundle containing the manifest and all entity files.
    Preserves relative directory structure.
    """
    manifest_dir = os.path.dirname(os.path.abspath(manifest_path))
    manifest_name = os.path.basename(manifest_path)
    
    doc = _load_json(manifest_path)
    fn_list = [f["name"] for f in doc["Fields"]]
    fp_idx = fn_list.index("file_path")
    
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Add manifest
        zipf.write(manifest_path, manifest_name)
        
        # Add entity files
        for row in doc["Values"]:
            rel_path = row[fp_idx]
            abs_path = os.path.normpath(os.path.join(manifest_dir, rel_path))
            if os.path.exists(abs_path):
                zipf.write(abs_path, rel_path)


# ---------------------------------------------------------------------------
# TRANSFORMATIONS
# ---------------------------------------------------------------------------

def mfdb_ext_transform_entity(
    manifest_path: str, 
    entity_name: str, 
    transform_fn: Callable[[dict], dict]
) -> None:
    """
    Apply a transformation function to all records in an entity.
    The transform_fn receives a record dict and must return a modified record dict.
    """
    from lib_mfdb_core import mfdb_core_get_entity_doc
    from lib_mfdb_validator import _rows_as_dicts
    
    entity_path = _get_entity_path(manifest_path, entity_name)
    doc = bejson_core_load_file(entity_path)
    
    fields = doc["Fields"]
    field_names = [f["name"] for f in fields]
    
    new_values = []
    for row in doc["Values"]:
        record_dict = dict(zip(field_names, row))
        transformed = transform_fn(record_dict)
        
        # Convert back to list in correct order
        new_row = [transformed.get(name) for name in field_names]
        new_values.append(new_row)
        
    doc["Values"] = new_values
    bejson_core_atomic_write(entity_path, doc)


def mfdb_ext_chain_join(
    manifest_path: str,
    base_entity:   str,
    joins:         list[dict],
) -> list[dict]:
    """
    Perform a sequence of joins starting from a base entity.

    'joins' is a list of dicts:
        {
          "to_entity": str,
          "from_fk":   str, # field name in the CURRENT result set
          "to_pk":     str  # field name in the target entity
        }

    Example:
        mfdb_ext_chain_join(manifest_path, "Comment", [
            {"to_entity": "Post", "from_fk": "post_id_fk", "to_pk": "post_id"},
            {"to_entity": "User", "from_fk": "Post__user_id_fk", "to_pk": "user_id"}
        ])

    Returns a list of merged dicts with prefixed keys.
    """
    from lib_mfdb_core import mfdb_core_load_entity, mfdb_core_build_index

    # 1. Start with the base entity
    results = mfdb_core_load_entity(manifest_path, base_entity)
    current_prefix = "" # Base entity fields are not prefixed

    # 2. Iterate through joins
    for join in joins:
        to_entity = join["to_entity"]
        from_fk   = join["from_fk"]
        to_pk     = join["to_pk"]
        
        to_index = mfdb_core_build_index(manifest_path, to_entity, to_pk)
        
        new_results = []
        for record in results:
            fk_val = record.get(from_fk)
            target = to_index.get(fk_val, {})
            merged = dict(record)
            for k, v in target.items():
                # Prefix right-hand side fields
                merged[f"{to_entity}__{k}"] = v
            new_results.append(merged)
        
        results = new_results
        
    return results
