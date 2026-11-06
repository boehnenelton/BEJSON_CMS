"""
Library:        lib_bejson_AI_brain_helper.py
Family:         AI
Description:    High-level API for querying the Workspace Brain MFDB and policy nodes.
Version:        2.1.2
Date:           2026-08-13
Author:         Elton Boehnen
Contact:        eltonboehnen@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  9a1c7e35-4d8b-4f26-b1e0-6c3a8d2f7b90

Changelog:
  2.1.2 - AI-family audit fix: module-level VERSION var had drifted to
          "2.1.0" while this header said 2.1.1. Re-synced.
"""

import os
import sys
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Resolve paths
HOME = os.environ.get("HOME", os.path.expanduser("~"))

# FIX (LIB-AI-H1): `from lib_bejson_Core_bejson_env import resolve_path`
# used to run here, BEFORE Core was added to sys.path below - so it only
# ever worked if Core happened to already be importable some other way,
# and the sys.path.append fix-up a few lines down never got a chance to
# run before the failure. Worse, that fix-up computed CORE_DIR from
# ADMIN_ROOT, which itself came from calling resolve_path() - a circular
# dependency (need Core importable to get ADMIN_ROOT, need ADMIN_ROOT to
# know where Core is). Broken by bootstrapping off this file's own
# location instead: Lib_PY/AI and Lib_PY/Core are siblings under Lib_PY,
# which needs nothing from Core or ADMIN_ROOT to compute.
_CORE_DIR = str(Path(__file__).resolve().parent.parent / "Core")
if _CORE_DIR not in sys.path:
    sys.path.append(_CORE_DIR)

from lib_bejson_Core_bejson_env import resolve_path

VERSION = "2.1.2"
ADMIN_ROOT = resolve_path("{ADMIN_ROOT}")
BRAIN_MANIFEST = os.path.join(ADMIN_ROOT, "data/registry/104a.mfdb.bejson")

# Ensure Core is in path (kept in case ADMIN_ROOT points at a different
# libraries checkout than this file's own location)
CORE_DIR = os.path.join(ADMIN_ROOT, "libraries/Lib_PY/Core")
if CORE_DIR not in sys.path:
    sys.path.append(CORE_DIR)

from lib_bejson_Core_mfdb_core import (
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
