"""
Library:      lib_brain_helper.py
Family:       AI
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.1.1 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-06-05
Description:  High-level API for querying the Workspace Brain MFDB and policy nodes.
REMEDIATED:   Purged transition stubs for Core and Env (Phase 1).
"""

import os
import sys
import logging
from typing import Any, Callable, Dict, List, Optional

# Resolve paths
HOME = os.environ.get("HOME", os.path.expanduser("~"))
from lib_bejson_env import resolve_path

VERSION = "2.1.0"
ADMIN_ROOT = resolve_path("{ADMIN_ROOT}")
BRAIN_MANIFEST = os.path.join(ADMIN_ROOT, "data/registry/104a.mfdb.bejson")

# Ensure Core is in path
CORE_DIR = os.path.join(ADMIN_ROOT, "libraries/Lib_PY/Core")
if CORE_DIR not in sys.path:
    sys.path.append(CORE_DIR)

from lib_mfdb_core import (
    mfdb_core_load_entity,
    mfdb_core_add_entity_record,
    mfdb_core_update_entity_record,
    mfdb_core_remove_entity_record
)

def brain_load_entity(entity_name: str) -> List[Dict[str, Any]]:
    """Loads all records for a specific entity from the Brain MFDB."""
    try:
        return mfdb_core_load_entity(BRAIN_MANIFEST, entity_name) or []
    except Exception as e:
        logging.error(f"[BrainHelper] Failed to load entity {entity_name}: {e}")
        return []

def brain_query_entity(entity_name: str, predicate: Callable[[Dict[str, Any]], bool]) -> List[Dict[str, Any]]:
    """Returns a list of records matching a specific filter function."""
    records = brain_load_entity(entity_name)
    return [r for r in records if predicate(r)]

def brain_get_record(entity_name: str, field: str, value: Any) -> Optional[Dict[str, Any]]:
    """Finds and returns a single record dict based on a field match."""
    records = brain_load_entity(entity_name)
    return next((r for r in records if r.get(field) == value), None)

def brain_add_record(entity_name: str, values: List[Any]) -> bool:
    """Adds a new record to an entity."""
    try:
        mfdb_core_add_entity_record(BRAIN_MANIFEST, entity_name, values)
        return True
    except Exception as e:
        logging.error(f"[BrainHelper] Add record failed: {e}")
        return False

def brain_update_record(entity_name: str, search_field: str, search_value: Any, update_field: str, new_value: Any) -> bool:
    """Updates a specific field in a record found by a search criterion."""
    try:
        records = brain_load_entity(entity_name)
        idx = next((i for i, r in enumerate(records) if r.get(search_field) == search_value), -1)
        if idx == -1:
            return False
        mfdb_core_update_entity_record(BRAIN_MANIFEST, entity_name, idx, update_field, new_value)
        return True
    except Exception as e:
        logging.error(f"[BrainHelper] Update record failed: {e}")
        return False

def brain_remove_record(entity_name: str, search_field: str, search_value: Any) -> bool:
    """Removes a record from an entity found by a search criterion."""
    try:
        records = brain_load_entity(entity_name)
        idx = next((i for i, r in enumerate(records) if r.get(search_field) == search_value), -1)
        if idx == -1:
            return False
        mfdb_core_remove_entity_record(BRAIN_MANIFEST, entity_name, idx)
        return True
    except Exception as e:
        logging.error(f"[BrainHelper] Remove record failed: {e}")
        return False

# --- Specialized Helpers ---

def brain_get_node(path: str) -> Optional[Dict[str, Any]]:
    """Specialized helper to retrieve a WorkspaceNode by its path."""
    return brain_get_record("WorkspaceNode", "path", path)

def brain_get_policy(title: str) -> Optional[Dict[str, Any]]:
    """Specialized helper to retrieve a Policy by its title."""
    return brain_get_record("Policy", "title", title)

def brain_get_html3(key: str) -> Optional[Dict[str, Any]]:
    """Specialized helper to retrieve a html3 entry by its key."""
    return brain_get_record("html3", "key", key)

if __name__ == "__main__":
    print("Brain Helper Library Loaded.")
