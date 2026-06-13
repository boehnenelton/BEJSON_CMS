"""
Library:      lib_bejson_env.py
Family:       Core
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.1.2 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-06-05
Description:  Environment and path resolution utility for the BEJSON ecosystem.
REMEDIATED:   Purged 'Brain-Container' and 'SC_ROOT'; implemented Admin/Lib roots (Phase 6.5).
REMEDIATED:   Removed hardcoded /storage/emulated/0 fallback (Audit Finding 10).
"""

import os
import sys
from pathlib import Path

def source_env(override_path: str = None) -> bool:
    """
    Mandatory Environment Sourcing (Section 54).
    Priority: 1. override_path, 2. ENV_FILE_PATH, 3. Android Storage, 4. Home
    """
    env_path = override_path or os.environ.get("ENV_FILE_PATH")
    search_paths = [
        Path(env_path) if env_path else None,
        Path("/storage/emulated/0/env_file.py"),
        Path.home() / "env_file.py"
    ]
    for p in search_paths:
        if p and p.exists():
            try:
                exec(p.read_text(), globals())
                return True
            except Exception:
                continue
    return False

def resolve_path(path_str: str) -> str:
    """
    Resolves system placeholders and absolute paths to environment-relative paths.
    Prioritizes environment variables (ADMIN_ROOT, BEJSON_LIB_ROOT, etc).
    """
    if not path_str:
        return path_str
    
    # Define standard roots with defaults
    home = os.environ.get("HOME", os.path.expanduser("~"))
    
    # Storage and Admin Roots
    # RE-ALIGNED: Fallback to HOME if storage root is unset to avoid hardcodes.
    storage_root = os.environ.get("BEJSON_STORAGE_ROOT", home)
    admin_root   = os.environ.get("ADMIN_ROOT", os.path.join(storage_root, "Admin"))
    
    # Library Root Resolution (Admin/libraries fallback to ~/libraries)
    lib_root = os.environ.get("BEJSON_LIB_ROOT")
    if not lib_root:
        candidate_admin = os.path.join(admin_root, "libraries")
        candidate_home  = os.path.join(home, "libraries")
        lib_root = candidate_admin if os.path.exists(candidate_admin) else candidate_home
    
    mappings = {
        "{BEJSON_LIB_ROOT}": lib_root,
        "{ADMIN_ROOT}": admin_root,
        "{INTERNAL_STORAGE}": storage_root,
        "{HOME}": home,
        # Legacy placeholder mapping
        "{SC_ROOT}": admin_root,
        "{BEC_ROOT}": admin_root,
        # Legacy absolute paths to be replaced
        "/storage/emulated/0": storage_root,
        "/data/data/com.termux/files/home": home
    }
    
    resolved = str(path_str)
    
    # Sort keys by length descending to avoid partial matches (e.g. {HOME}_STUFF)
    for placeholder in sorted(mappings.keys(), key=len, reverse=True):
        actual = mappings[placeholder]
        if actual:
            resolved = resolved.replace(placeholder, actual)
    
    # Handle home expansion
    resolved = os.path.expanduser(resolved)
    # Handle environment variables in path (e.g. $VAR)
    resolved = os.path.expandvars(resolved)
    
    return os.path.normpath(resolved)

def get_env_path(env_var: str, default: str) -> str:
    """Retrieves an environment variable and resolves it as a path."""
    val = os.getenv(env_var, default)
    return resolve_path(val)
