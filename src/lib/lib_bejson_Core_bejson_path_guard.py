"""
Library:         lib_bejson_Core_bejson_path_guard.py
Family:          Core
Module Purpose:  Path-traversal guard and storage-path resolution; includes the check that an MFDB entity's Parent_Hierarchy cannot escape the MFDB root, plus safe_extract_zip() for zip-slip-safe archive extraction.
Architecture:    Path security helper. Only _bejson_mfdb_escapes_root relates to MFDB (it validates the relative Parent_Hierarchy path of an entity file); nothing here is 104db-specific.
Format_Scope:    None, except _bejson_mfdb_escapes_root (MFDB Parent_Hierarchy containment)
Glossary:        BEJSON 104, 104a and 104db are the three file formats (Format_Version). 104db = ONE file holding 2+ entity types
                 (Record_Type_Parent discriminator, null-padding). MFDB is NOT a format and NOT 104db: it is a layer made of one 104a manifest
                 (104a.mfdb.bejson) plus dense 104 entity files linked by Parent_Hierarchy. MFDB-132 = an MFDB packed into one Chunked-104a document.
Version:         1.3.0
Release_Version: 300
Date:            2026-10-02
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   826ad8d2-8944-4492-9507-9ae7473fdef9
"""

import os
from pathlib import Path

# Joins paths under base_dir and raises if the resolved result is outside it (blocks .. traversal and sibling-prefix tricks).
def bejson_safe_join(base_dir: str, *paths: str) -> str:
    """
    Safely join paths and ensure the result is within the base_dir.
    Blocks path traversal, including sibling-directory prefix bypasses.
    """
    base_path = Path(base_dir).resolve()
    # Handle environment variables in paths if any
    resolved_paths = [os.path.expandvars(p) for p in paths]
    target_path = base_path.joinpath(*resolved_paths).resolve()

    is_inside = target_path == base_path
    if not is_inside:
        try:
            is_inside = target_path.is_relative_to(base_path)
        except AttributeError:
            is_inside = base_path in target_path.parents

    if not is_inside:
        raise ValueError(f"Path traversal detected: {target_path} is outside of {base_path}")

    return str(target_path)


# Resolves a path through the environment layer (placeholders, storage root) so callers stay free of absolute paths.
def resolve_storage_path(path: str) -> str:
    """
    Standardized resolve_path utility for environment abstraction.
    Prioritizes $BEJSON_STORAGE_ROOT.
    """
    storage_root = os.environ.get("BEJSON_STORAGE_ROOT")
    if not storage_root:
        # Fallback to local home if storage root is unknown
        storage_root = os.path.expanduser("~")
        
    if not path:
        return storage_root

    # Map absolute Android storage paths onto the configured storage root
    if path.startswith("/storage/emulated/0"):
        return path.replace("/storage/emulated/0", storage_root)
        
    return path

# MFDB check: True if a relative path (an entity's Parent_Hierarchy or file_path) would climb above the MFDB root. Normalizes separators and counts depth. This is the only MFDB-aware function in this module.
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


# Extracts every member of an open ZipFile into dest_dir after validating all paths with bejson_safe_join.
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
    partially extracted. Uses bejson_safe_join()'s sibling-directory-safe
    boundary check (v1.1.0+) rather than a raw prefix test.
    """
    dest_path = Path(dest_dir).resolve()
    for member in zf.infolist():
        # bejson_safe_join raises ValueError itself if the resolved path
        # escapes dest_dir -- let that propagate to the caller.
        bejson_safe_join(str(dest_path), member.filename)
    zf.extractall(dest_dir)


VERSION = "1.3.0"
