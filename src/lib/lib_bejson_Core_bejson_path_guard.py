"""
Library:        lib_bejson_Core_bejson_path_guard.py
Family:         Core
Description:    Secure path resolver and boundary protection logic.
Version:        1.2.0
Date:           2026-08-07
CHANGE (2026-08-07): Fixed a sibling-directory bypass in bejson_safe_join()
(found while fixing LIB-CH-H1, which delegates to this same helper). The
`str(target_path).startswith(str(base_path))` check is a raw string
prefix test: base_dir="/x/out" is a startswith-match for a resolved
target of "/x/out_evil/secret" -- no traversal needed, just a
similarly-named sibling. Replaced with Path.is_relative_to() (falls
back to a manual parents walk on Python <3.9, though policy floors at
3.10 so that branch is defensive only), which requires an exact
directory-boundary match, not a string prefix.
RELATIONAL_ID:  31305b9a-7172-4600-b45e-50355ec0b1c5
Release_Version: 300

CMS-PROJECT MERGE NOTE (2026-08-22): the upstream version of this file no
longer includes safe_extract_zip() -- it was removed there. This CMS
project (BEJSON_CMS-V18_28) has 4 real call sites depending on it
(BEJSON_CMS_Content.py x2, cms-manage.py x2 including the live restore
path, lib_mfdb_chunker_v6.py), so it's been preserved below rather than
dropped. It delegates to bejson_safe_join(), so it automatically inherits
this version's sibling-directory-bypass fix. If a future upstream sync
re-adds safe_extract_zip() with its own changes, reconcile rather than
overwrite -- don't lose this note.
"""

import os
from pathlib import Path

def bejson_safe_join(base_dir: str, *paths: str) -> str:
    """
    Safely join paths and ensure the result is within the base_dir.
    Mitigates path traversal attacks (Phase 2), including sibling-directory
    prefix bypasses (Phase 3, LIB-CH-H1 follow-up).
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

    Preserved from the pre-upstream-sync version of this file (see module
    docstring merge note) -- now benefits from the sibling-directory-bypass
    fix in bejson_safe_join() above, since it delegates to it.
    """
    dest_path = Path(dest_dir).resolve()
    for member in zf.infolist():
        # bejson_safe_join raises ValueError itself if the resolved path
        # escapes dest_dir -- let that propagate to the caller.
        bejson_safe_join(str(dest_path), member.filename)
    zf.extractall(dest_dir)


VERSION = "1.2.0"
