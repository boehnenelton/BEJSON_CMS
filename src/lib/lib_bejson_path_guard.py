"""
Library:      lib_bejson_path_guard.py
Family:       Utility
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      1.0.0 OFFICIAL
Date:         2026-06-02
Description:  Secure path resolver and boundary protection logic.
REMEDIATED:   Implemented Phase 2 Path Guarding (Mitigates Path Traversal).
"""

import os
from pathlib import Path

def bejson_safe_join(base_dir: str, *paths: str) -> str:
    """
    Safely join paths and ensure the result is within the base_dir.
    Mitigates path traversal attacks (Phase 2).
    """
    base_path = Path(base_dir).resolve()
    target_path = base_path.joinpath(*paths).resolve()
    
    if not str(target_path).startswith(str(base_path)):
        raise ValueError(f"Path traversal detected: {target_path} is outside of {base_path}")
    
    return str(target_path)

def resolve_storage_path(path: str) -> str:
    """
    Standardized resolve_path utility for environment abstraction (Phase 1).
    Prioritizes $BEJSON_STORAGE_ROOT.
    """
    storage_root = os.environ.get("BEJSON_STORAGE_ROOT")
    if not storage_root:
        # Fallback to local home if storage root is unknown
        storage_root = os.path.expanduser("~")
        
    if not path:
        return storage_root

    # Standardize absolute paths from legacy hardcoding (if encountered)
    if path.startswith("/storage/emulated/0"):
        return path.replace("/storage/emulated/0", storage_root)
        
    return path

VERSION = "1.1.0"
