"""
Library:        lib_bejson_Core_bejson_path_guard.py
Family:         Core
Description:    Secure path resolver and boundary protection logic.
Version:        1.0.0
Date:           2026-06-02
Author:         Elton Boehnen
Contact:        eltonboehnen@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  8d1b4d5d-97bf-4b8f-aa48-0af3386b503f
"""

import os
from pathlib import Path

def bejson_safe_join(base_dir: str, *paths: str) -> str:
    """
    Safely join paths and ensure the result is within the base_dir.
    Mitigates path traversal attacks (Phase 2).
    """
    base_path = Path(base_dir).resolve()
    # Handle environment variables in paths if any
    resolved_paths = [os.path.expandvars(p) for p in paths]
    target_path = base_path.joinpath(*resolved_paths).resolve()
    
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

def _bejson_mfdb_escapes_root(relative_path: str) -> bool:
    """
    Relative-depth path traversal check.  Normalizes separators then counts
    directory depth segment by segment.  Returns True (path is unsafe) if any
    '..' segment attempts to drop the depth below 0, indicating an escape
    above the MFDB root.

    Mirrors _escapesRoot in lib_bejson_Core_mfdb_validators.ts exactly
    (Remediation NEW-08).

    Args:
        relative_path: A relative path string, e.g. '../104a.mfdb.bejson'.

    Returns:
        True  — path escapes root (unsafe, reject).
        False — path stays within root (safe).
    """
    normalized = relative_path.replace("\\", "/")
    parts = normalized.split("/")
    depth = 0
    for part in parts:
        if part == "..":
            depth -= 1
            if depth < 0:
                return True
        elif part != "." and part != "":
            depth += 1
    return False


def safe_extract_zip(zf, dest_dir: str) -> None:
    """
    Extract every member of an open ZipFile into dest_dir, rejecting the
    whole archive if any member's name would resolve outside dest_dir
    (zip-slip: '../' segments, absolute paths, or symlink-style tricks
    encoded in the name). zipfile.ZipFile.extractall() does NOT do this
    check itself -- member names are used as-is to build the destination
    path, so a crafted archive can write anywhere the process can reach.
    Raises ValueError on the first unsafe member found, before extracting
    anything, so a malicious zip is rejected atomically rather than
    partially extracted.
    """
    dest_path = Path(dest_dir).resolve()
    for member in zf.infolist():
        # bejson_safe_join raises ValueError itself if the resolved path
        # escapes dest_dir -- let that propagate to the caller.
        bejson_safe_join(str(dest_path), member.filename)
    zf.extractall(dest_dir)


VERSION = "1.2.0"
