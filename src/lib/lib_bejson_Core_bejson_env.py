"""
Library:         lib_bejson_Core_bejson_env.py
Family:          Core
Module Purpose:  Environment-file sourcing and storage-path resolution.
Architecture:    Runtime or environment helper. It defines no BEJSON format rules.
Format_Scope:    None (not a format module)
Glossary:        BEJSON 104, 104a and 104db are the three file formats (Format_Version). 104db = ONE file holding 2+ entity types
                 (Record_Type_Parent discriminator, null-padding). MFDB is NOT a format and NOT 104db: it is a layer made of one 104a manifest
                 (104a.mfdb.bejson) plus dense 104 entity files linked by Parent_Hierarchy. MFDB-132 = an MFDB packed into one Chunked-104a document.
Version:         2.3.0
Release_Version: 300
Date:            2026-10-13
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   6e2a8c47-1b93-4d05-a7f8-3c9d51e0b624

Changelog:
  2.3.0 (2026-10-13) - ADDITIVE. New source_env_fill(): non-overwriting, once-per-process
        load of the secure store (secureenv_file.json / .env) so library key registries find
        their keys without every caller having to call source_env() first. source_env(),
        _load_env_file(), resolve_path() and get_env_path() are byte-for-byte unchanged.
        source_env_fill never overwrites an existing environment variable, never exec()s a
        file, never loads paths.json unless include_paths=True, and reports names/counts only.
"""

import logging
import os
import sys
import threading
from pathlib import Path

logger = logging.getLogger("lib_bejson_Core_bejson_env")

VERSION = "2.3.0"


# Applies one env file to the process environment. .json files are read as BEJSON 104a (Values rows -> os.environ); other files as KEY=VALUE lines.
def _load_env_file(p: Path) -> bool:
    """Applies one env file's contents to the process environment.
    .json files are parsed as BEJSON 104a (Values rows -> os.environ);
    .py files are exec()'d as before. Returns False on any failure."""
    try:
        if p.suffix == ".json":
            import json
            data = json.loads(p.read_text(encoding="utf-8"))
            for row in data.get("Values", []):
                if isinstance(row, list) and len(row) >= 2:
                    var_name, var_val = str(row[0]).strip(), str(row[1]).strip()
                    if var_name and var_val:
                        os.environ[var_name] = var_val
        else:
            exec(p.read_text(encoding="utf-8"), globals())
        return True
    except Exception:
        return False


# Mandatory environment sourcing: loads the env files from the standard locations (override_path first). Returns True if any file was applied.
def source_env(override_path: str = None) -> bool:
    """
    Mandatory Environment Sourcing (Global Operating Rules 4.5).
    Priority: 1. override_path/ENV_FILE_PATH, 2. secure credentials AND user
    paths (both sourced, not either/or), 3. transitory/legacy fallback.
    """
    env_path = override_path or os.environ.get("ENV_FILE_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return _load_env_file(p)

    secure_candidates = [
        Path("/storage/emulated/0/.env/secure/secureenv_file.py"),
        Path("/storage/emulated/0/.env/secure/secureenv_file.json"),
    ]
    user_candidates = [
        Path("/storage/emulated/0/.env/user/paths.py"),
        Path("/storage/emulated/0/.env/user/paths.json"),
    ]

    loaded_any = False
    for p in secure_candidates:
        if p.exists() and _load_env_file(p):
            loaded_any = True
            break
    for p in user_candidates:
        if p.exists() and _load_env_file(p):
            loaded_any = True
            break
    if loaded_any:
        return True

    # Fallback env-file locations, used only if neither mandatory tier exists.
    fallback_candidates = [
        Path("/storage/emulated/0/env_file.py"),
        Path("/storage/emulated/0/env_file.json"),
        Path.home() / "env_file.py",
    ]
    for p in fallback_candidates:
        if p.exists() and _load_env_file(p):
            return True
    return False

# Replaces placeholders ({INTERNAL_STORAGE}, {ADMIN_ROOT}, ...) and known absolute Android paths with the configured roots so no absolute path is hardcoded.
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
    # Fallback to HOME if storage root is unset to avoid hardcodes.
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
        "{HOME}": home
    }
    
    # Absolute Android/Termux paths mapped to the configured roots.
    # Only replaced when BEJSON_STORAGE_ROOT is explicitly set, so existing data paths are not redirected.
    if os.environ.get("BEJSON_STORAGE_ROOT"):
        mappings["/storage/emulated/0"] = storage_root
        mappings["/data/data/com.termux/files/home"] = home
    
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

# Reads an environment variable (or default) and resolves it through resolve_path.
def get_env_path(env_var: str, default: str) -> str:
    """Retrieves an environment variable and resolves it as a path."""
    val = os.getenv(env_var, default)
    return resolve_path(val)


# --- source_env_fill (2.3.0, additive) --------------------------------------
_FILL_LOCK = threading.Lock()
_FILL_REPORTS: dict = {}
_FILL_MAX_BYTES = 2 * 1024 * 1024


def _fill_pairs(p: Path) -> dict:
    """{NAME: value} from one env file. .json = BEJSON 104a Values rows [name, value]
    (same reading as _load_env_file); a plain JSON object is flattened one level;
    anything else is KEY=VALUE lines. Never exec()s. {} on any failure."""
    import json
    out: dict = {}
    try:
        if not p.is_file() or p.stat().st_size > _FILL_MAX_BYTES:
            return out
        text = p.read_text(encoding="utf-8")
        if p.suffix == ".json":
            data = json.loads(text)
            if isinstance(data, dict) and "Values" in data:
                for row in data.get("Values", []):
                    if isinstance(row, list) and len(row) >= 2:
                        k, v = str(row[0]).strip(), str(row[1]).strip()
                        if k and v and row[1] is not None:
                            out[k] = v
            elif isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, (str, int, float)) and not isinstance(v, bool) and str(v).strip():
                        out[str(k).strip()] = str(v).strip()
        elif p.suffix != ".py":
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.lower().startswith("export "):
                    line = line[7:].strip()
                if "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() and v.strip().strip("\"'"):
                        out[k.strip()] = v.strip().strip("\"'")
    except Exception as e:
        logger.warning("source_env_fill: could not read %s: %s", p.name, type(e).__name__)
        return {}
    return {k: v for k, v in out.items() if k.replace("_", "a").isalnum() and not k[0].isdigit()}


# Loads the secure store into os.environ WITHOUT overwriting anything already set. Safe to call repeatedly (cached per key).
def source_env_fill(include_paths: bool = False, force: bool = False) -> dict:
    """
    Non-overwriting companion to source_env(). Real environment variables always win
    (secure-credentials-first ordering); the store only fills gaps. Cached per process,
    so library key registries can call it on every load() for free.

    Secure store candidates: $SECUREENV_FILE, then the same standard locations source_env()
    uses (.json first, plus ~/.env/secure/secureenv_file.json). .py files are NOT exec()'d here.
    include_paths=True also fills from the user paths store ($BEJSON_PATHS_FILE or the standard
    paths.json); default False because paths change how resolve_path() behaves.

    Returns a report of NAMES and counts only: {found, files, loaded, kept_existing, names}.
    Values are never logged or returned.
    """
    cache_key = bool(include_paths)
    with _FILL_LOCK:
        if cache_key in _FILL_REPORTS and not force:
            return dict(_FILL_REPORTS[cache_key])

    secure = [os.environ.get("SECUREENV_FILE"),
              "/storage/emulated/0/.env/secure/secureenv_file.json",
              os.path.join(os.path.expanduser("~"), ".env", "secure", "secureenv_file.json")]
    paths = [os.environ.get("BEJSON_PATHS_FILE"),
             "/storage/emulated/0/.env/user/paths.json",
             os.path.join(os.path.expanduser("~"), ".env", "user", "paths.json")]
    tiers = [secure] + ([paths] if include_paths else [])

    report = {"found": False, "files": [], "loaded": 0, "kept_existing": 0, "names": []}
    names = set()
    for tier in tiers:
        for cand in tier:
            if not cand:
                continue
            p = Path(os.path.expanduser(str(cand)))
            if not p.is_file():
                continue
            pairs = _fill_pairs(p)
            report["found"] = True
            report["files"].append(p.name)
            for k, v in pairs.items():
                if os.environ.get(k, "").strip():
                    report["kept_existing"] += 1
                else:
                    os.environ[k] = v
                    report["loaded"] += 1
                names.add(k)
            break  # first existing candidate per tier wins
    report["names"] = sorted(names)
    logger.info("source_env_fill: found=%s loaded=%d kept_existing=%d",
                report["found"], report["loaded"], report["kept_existing"])
    with _FILL_LOCK:
        _FILL_REPORTS[cache_key] = report
    return dict(report)
