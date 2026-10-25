"""
Library:         lib_bejson_Core_bejson_core.py
Family:          Core
Module Purpose:  Format-level primitives: atomic write with PID lock, file/string loading, field-map cache, and document factories for 104, 104a and 104db.
Architecture:    Format-level BEJSON layer that works on any BEJSON document (104, 104a, 104db) through positional Fields/Values and the field-map cache. It does not orchestrate MFDB and is not specific to 104db.
Format_Scope:    104 | 104a | 104db (generic)
Glossary:        BEJSON 104, 104a and 104db are the three file formats (Format_Version). 104db = ONE file holding 2+ entity types
                 (Record_Type_Parent discriminator, null-padding). MFDB is NOT a format and NOT 104db: it is a layer made of one 104a manifest
                 (104a.mfdb.bejson) plus dense 104 entity files linked by Parent_Hierarchy. MFDB-132 = an MFDB packed into one Chunked-104a document.
Version:         2.0.10
Release_Version: 300
Date:            2026-10-11
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   c81fa829-42a8-4a0a-a9f3-a485c1dac3a8
"""

import json
import os
import sys
import time
import shutil
import tempfile
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

class BEJSONCoreError(Exception):
    """Raised when a BEJSON core operation fails."""
    # Exception type for core-layer failures (class BEJSONCoreError). `code` is an optional numeric error code.
    def __init__(self, message: str, code: int = None):
        super().__init__(message)
        self.code = code

class ResilientPIDLock:
    # Cross-process (and cross-thread) mutex for one file. The lock is the directory <path>.lockdir (an atomic mkdir); lock_meta.json inside it records {pid, timestamp, token}.
    # Ownership: each acquire() mints a unique token; release() removes the lock only if this handle still owns it, so a handle that never acquired (or lost its lock) can never delete another owner's lock.
    # Stale recovery: a lock is reclaimed only when its owner PID is dead (or the dir never received metadata for _INIT_GRACE seconds). Reclaim is serialised by a guard dir, re-validated under the guard, and done with an atomic rename -- never rmdir/unlink on a lock that may be live.
    # Lock-dir layout and meta fields pid/timestamp are unchanged, so handles from older library copies interoperate (they ignore `token`).
    _INIT_GRACE = 2.0     # seconds a lockdir may exist without lock_meta.json before it counts as abandoned (owner crashed between mkdir and the meta write)
    _GUARD_STALE = 30.0   # seconds before a reclaim-guard dir left by a crashed reclaimer is discarded
    _POLL = 0.1           # seconds between acquire attempts while waiting

    # Creates the lock handle for target_path: lock directory <path>.lockdir, metadata file lock_meta.json, timeout in seconds. Does not take the lock until acquire()/with.
    def __init__(self, target_path: Union[str, Path], timeout_seconds: int = 10):
        self.target    = Path(target_path)
        self.lock_dir  = Path(f"{target_path}.lockdir")
        self.meta_file = self.lock_dir / "lock_meta.json"
        self.timeout   = timeout_seconds
        self._guard_dir = Path(f"{target_path}.lockdir.reclaim")
        self._token     = None   # set while this handle owns the lock
        self._owner_pid = None   # PID that acquired it (a forked child must not release the parent's lock)

    # True when `pid` is a live process. PermissionError means the process exists (owned by another user), so it counts as alive.
    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)  # Signal 0: existence check only
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    # Reads lock_meta.json. Returns the dict, or None when it is missing, mid-replace, unreadable or not a JSON object. Never raises.
    def _read_meta(self) -> Optional[dict]:
        try:
            meta = json.loads(self.meta_file.read_text())
        except (OSError, ValueError):
            return None
        return meta if isinstance(meta, dict) else None

    # Decides whether the current lock holder is dead. Returns an identity tuple describing exactly what was judged (so it can be re-checked under the reclaim guard), or None when the lock is live, gone or too young to judge.
    def _judge_stale(self) -> Optional[tuple]:
        meta = self._read_meta()
        if meta is not None:
            pid = meta.get("pid")
            if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
                if self._pid_alive(pid):
                    return None
                return ("dead", pid, meta.get("token"), meta.get("timestamp"))
        # No usable metadata: a freshly created lockdir is still being initialised; only an old one is abandoned.
        try:
            mtime_ns = self.lock_dir.stat().st_mtime_ns
        except OSError:
            return None  # lock vanished: the caller simply retries mkdir
        if time.time() - mtime_ns / 1e9 > self._INIT_GRACE:
            return ("abandoned", mtime_ns)
        return None

    # Atomically moves a directory aside under a unique sibling name and deletes it. Returns False if the source was already gone (another process won).
    def _discard(self, path: Path) -> bool:
        trash = Path(f"{path}.{uuid.uuid4().hex}.trash")
        try:
            os.rename(path, trash)
        except OSError:
            return False
        shutil.rmtree(trash, ignore_errors=True)
        return True

    # Removes a lock judged stale. Only one reclaimer runs at a time (guard dir); under the guard the judgement is repeated and the lock is removed only if the SAME dead owner is still in place. Returns True if the stale lock was removed.
    def _reclaim_stale(self, judged: tuple) -> bool:
        try:
            self._guard_dir.mkdir(exist_ok=False)
        except FileExistsError:
            try:
                if time.time() - self._guard_dir.stat().st_mtime > self._GUARD_STALE:
                    self._discard(self._guard_dir)  # reclaimer crashed while holding the guard
            except OSError:
                pass
            return False
        except OSError:
            return False
        try:
            if self._judge_stale() != judged:
                return False  # owner changed or came back to life since we looked
            return self._discard(self.lock_dir)
        finally:
            try:
                self._guard_dir.rmdir()
            except OSError:
                pass

    # One attempt to take the lock: atomic mkdir, then lock_meta.json written atomically (temp file + rename) so readers never see partial JSON. Returns False if the lock is held.
    def _try_create(self) -> bool:
        try:
            self.lock_dir.mkdir(exist_ok=False)
        except FileExistsError:
            return False
        token = uuid.uuid4().hex
        tmp   = self.lock_dir / f".meta-{token}.tmp"
        try:
            tmp.write_text(json.dumps({
                "pid":       os.getpid(),
                "timestamp": int(time.time()),
                "token":     token,
            }))
            os.replace(tmp, self.meta_file)
        except BaseException:
            self._discard(self.lock_dir)  # we created this dir a moment ago; do not leave a metadata-less lock behind
            raise
        self._token     = token
        self._owner_pid = os.getpid()
        return True

    # Takes the PID-lock. Waits up to `timeout` seconds (always at least one attempt); returns False on timeout. Reclaims the lock only from a dead owner (see _reclaim_stale).
    def acquire(self) -> bool:
        deadline = time.monotonic() + self.timeout
        while True:
            if self._try_create():
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            judged = self._judge_stale()
            if judged is not None and self._reclaim_stale(judged):
                continue  # stale lock removed: retry mkdir immediately
            time.sleep(min(self._POLL, remaining))

    # Releases the lock if (and only if) this handle owns it. Safe to call when the lock is already gone, was never acquired, or was lost; it never removes a lock owned by someone else.
    def release(self):
        token, self._token = self._token, None
        if token is None or self._owner_pid != os.getpid():
            return
        meta = self._read_meta()
        if meta is None or meta.get("token") != token:
            logging.warning("[BEJSON_CORE] Lock %s is no longer owned by this handle; not releasing", self.lock_dir)
            return
        self._discard(self.lock_dir)

    # Context-manager entry: acquires the lock or raises OSError(53) (E_MFDB_CORE_LOCK_FAILED code) on timeout. Used for writes to any BEJSON file, MFDB or not.
    def __enter__(self):
        if not self.acquire():
            raise OSError(53, "Mutex lock timeout expired (E_MFDB_CORE_LOCK_FAILED)")
        return self

    # Context-manager exit: always releases the lock.
    def __exit__(self, *_):
        self.release()

from lib_bejson_Core_bejson_env import resolve_path

# The field-map cache lives in memory only. It is never read back from disk or from a string.
FIELD_MAP_CACHE_KEY = "_bejson_field_map"

class _FieldMap(dict):
    """Provenance marker for engine-built field maps. A map that arrived via json.load/json.loads is a
    plain dict and is never trusted; only instances built by get_field_map pass the freshness guard."""
    __slots__ = ()

# Security: removes a persisted _bejson_field_map key from a freshly loaded document and logs a warning. The field-map cache is an in-memory artifact only; a copy that arrives from a file or string is untrusted (it could point field lookups at the wrong column). Called by load_file and load_string.
# Format-agnostic: applies to 104, 104a, 104db and MFDB manifest/entity files.
def bejson_core_strip_persisted_cache(doc: Any) -> Any:
    """Discards a persisted field-map cache from a freshly loaded document (untrusted input)."""
    if isinstance(doc, dict) and doc.pop(FIELD_MAP_CACHE_KEY, None) is not None:
        logging.warning("[BEJSON_CORE] Discarded persisted %s (untrusted cache)", FIELD_MAP_CACHE_KEY)
    return doc

# Loads a BEJSON file (any version: 104, 104a, 104db, or an MFDB manifest/entity file) into a dict. Resolves path placeholders first. Returns None if missing or unparseable.
# Does not validate -- use bejson_validator for that. A persisted _bejson_field_map key in the file is discarded (untrusted cache).
def bejson_core_load_file(path: str) -> Optional[dict]:
    """Loads a BEJSON file and returns the dictionary."""
    path = resolve_path(path)
    if not path:
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return bejson_core_strip_persisted_cache(json.load(f))
    except Exception as e:
        logging.error(f"[BEJSON_CORE] Failed to load {path}: {e}")
        return None

# Writes a BEJSON document atomically (temp file, fsync, rename). Format-agnostic: works for 104, 104a, 104db and MFDB manifest/entity files.
# Keys that start with '_' are in-memory metadata (e.g. cached field map) and are stripped before writing.
def bejson_core_atomic_write(path: str, data: dict) -> bool:
    """Writes a BEJSON file atomically using a temp file and sync."""
    target_dir = os.path.dirname(os.path.abspath(path))
    os.makedirs(target_dir, exist_ok=True)

    # Strip internal metadata keys (starting with _) before write
    clean_data = {k: v for k, v in data.items() if not k.startswith("_")}

    fd, tmp_path = tempfile.mkstemp(dir=target_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(clean_data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
        return True
    except Exception as e:
        logging.error(f"[BEJSON_CORE] Atomic write failed for {path}: {e}")
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return False

# Simple directory-based lock for a file path (<path>.lock). Returns True when acquired within `timeout`. Lighter than ResilientPIDLock (no stale-PID recovery).
def bejson_core_acquire_lock(file_path: str, timeout: int = 10) -> bool:
    """Acquire a simple directory-based lock."""
    lock_path = file_path + ".lock"
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            os.mkdir(lock_path)
            return True
        except FileExistsError:
            time.sleep(0.1)
    return False

# Releases the simple directory lock taken by bejson_core_acquire_lock.
def bejson_core_release_lock(file_path: str) -> None:
    """Release the simple directory-based lock."""
    lock_path = file_path + ".lock"
    try:
        os.rmdir(lock_path)
    except OSError:
        pass

# Global Field Map Cache
# Key: tuple of field names (sorted or as-is)
# Value: dict of {name: index}
_FIELD_MAP_CACHE: Dict[tuple, Dict[str, int]] = {}

# Name of a Fields entry (the dict's 'name', or str() of a non-dict entry). Used by the freshness guard.
def _field_name(field_def: Any) -> Any:
    return field_def.get("name") if isinstance(field_def, dict) else str(field_def)

# O(1) guard for an in-document field-map cache. Trusts the cache only if (a) it is a _FieldMap instance built by this engine (anything that came from json.load is a plain dict and is rejected), (b) its size equals len(Fields), and (c) the first, middle and last field names resolve to 0, len//2 and len-1.
# Catches append, pop, list replacement and swapped indices without scanning Fields. Duplicate field names fail the size check, which forces a safe rebuild. In-place edits that keep size and the three probe entries are not detected (blast radius: that one document).
def bejson_core_field_map_is_fresh(cached_map: Any, fields: Any) -> bool:
    """
    O(1) freshness guard for an in-document cache.
    Accepts the cache only if its size equals len(Fields) and the first, middle and last
    field names resolve to 0, len//2 and len-1. Catches append, pop, list replacement and
    swapped indices without scanning Fields. Duplicate field names always fail (size
    mismatch), which forces a safe rebuild instead of a silent wrong index.
    """
    if type(cached_map) is not _FieldMap or not isinstance(fields, list):
        return False  # only engine-built maps are trusted; parsed/forged plain dicts are rebuilt
    count = len(fields)
    if len(cached_map) != count:
        return False
    if count == 0:
        return True
    last = count - 1
    mid = count // 2
    return (cached_map.get(_field_name(fields[0])) == 0
            and cached_map.get(_field_name(fields[last])) == last
            and cached_map.get(_field_name(fields[mid])) == mid)

# Returns {field_name: column_index} for a BEJSON document, built once from Fields and cached on the document and in a global cache. All field access should go through this (no hardcoded positions).
# Works for 104, 104a, and 104db. In a 104db document, column 0 is the Record_Type_Parent discriminator.
# The in-document cache is trusted only when it was built by this engine and is still fresh (bejson_core_field_map_is_fresh);
# otherwise it is rebuilt from Fields. Each document receives its own copy of the shared map, so one caller's edits cannot affect other documents.
def bejson_core_get_field_map(doc: dict) -> Dict[str, int]:
    """
    Returns a mapping of field name to index.
    The in-document cache is reused only after the O(1) freshness guard passes; a stale or
    forged map is discarded and rebuilt. The global cache is never handed out: each document
    receives its own copy (one O(F) copy on first access), so a caller mutating the returned
    map cannot corrupt other documents that share the same schema. Repeat calls stay O(1).
    """
    fields = doc.get("Fields", [])
    cached_map = doc.get(FIELD_MAP_CACHE_KEY)
    if cached_map is not None:
        if bejson_core_field_map_is_fresh(cached_map, fields):
            return cached_map
        doc.pop(FIELD_MAP_CACHE_KEY, None)  # stale or poisoned: discard

    if not fields or not isinstance(fields, list):
        return {}

    field_names = tuple(_field_name(f) for f in fields)
    cache_key = (doc.get("Format_Version"), field_names)

    shared_map = _FIELD_MAP_CACHE.get(cache_key)
    if shared_map is None:
        shared_map = {name: i for i, name in enumerate(field_names)}
        _FIELD_MAP_CACHE[cache_key] = shared_map

    field_map = _FieldMap(shared_map)
    try:
        doc[FIELD_MAP_CACHE_KEY] = field_map
    except Exception:
        pass  # In case doc is immutable or not a dict

    return field_map

# Column index of one field name via the field-map cache; -1 if the field does not exist.
def bejson_core_get_field_index(doc: dict, field_name: str) -> int:
    """Returns the positional index of a field name using the freshness-guarded cache."""
    return bejson_core_get_field_map(doc).get(field_name, -1)

# Factory: new BEJSON 104 document -- exactly ONE record type, strict (no custom top-level keys). Also the format of every MFDB entity file (the caller adds Parent_Hierarchy).
def bejson_core_create_104(record_type: str, fields: list, values: list) -> dict:
    return {
        "Format": "BEJSON",
        "Format_Version": "104",
        "Format_Creator": "Elton Boehnen",
        "Records_Type": [record_type],
        "Fields": fields,
        "Values": values
    }

# Factory: new BEJSON 104a document -- one record type plus optional custom top-level header keys (**custom), PascalCase recommended. Also the format of the MFDB manifest.
def bejson_core_create_104a(record_type: str, fields: list, values: list, **custom) -> dict:
    doc = {
        "Format": "BEJSON",
        "Format_Version": "104a",
        "Format_Creator": "Elton Boehnen",
        "Records_Type": [record_type],
        "Fields": fields,
        "Values": values
    }
    doc.update(custom)
    return doc

# Factory: new BEJSON 104db document -- ONE file holding 2+ record types. record_types lists the entities; fields must include Record_Type_Parent first and per-field Record_Type_Parent ownership; unrelated cells are null-padded.
# This is the single-file multi-entity format. It is not MFDB.
def bejson_core_create_104db(record_types: list, fields: list, values: list) -> dict:
    return {
        "Format": "BEJSON",
        "Format_Version": "104db",
        "Format_Creator": "Elton Boehnen",
        "Records_Type": record_types,
        "Fields": fields,
        "Values": values
    }

# --- Format-level helpers used by mfdb_core and the 104db parser (they work on any BEJSON document) ---

# Parses a JSON string into a dict (any BEJSON version). Logs and returns None on error. No BEJSON validation.
# A persisted _bejson_field_map key in the text is discarded (untrusted cache).
def bejson_core_load_string(content: str) -> Optional[dict]:
    try:
        return bejson_core_strip_persisted_cache(json.loads(content))
    except Exception as e:
        logging.error(f"[BEJSON_CORE] Failed to load JSON string: {e}")
        return None

# Number of rows in Values.
def bejson_core_get_record_count(doc: dict) -> int:
    return len(doc.get("Values", []))

# Appends a row if its length equals the field count; returns False otherwise. For 104db documents the caller must supply the correct Record_Type_Parent in column 0 and null-pad.
def bejson_core_add_record(doc: dict, record: list) -> bool:
    if len(record) != len(doc.get("Fields", [])):
        return False
    doc.setdefault("Values", []).append(record)
    return True

# Removes the row at `index`; False when out of range.
def bejson_core_remove_record(doc: dict, index: int) -> bool:
    values = doc.get("Values", [])
    if 0 <= index < len(values):
        values.pop(index)
        return True
    return False

# Sets one cell by (row_index, field_name) using the field map. False if the field or row does not exist.
def bejson_core_update_field(doc: dict, row_index: int, field_name: str, value: Any) -> bool:
    idx = bejson_core_get_field_index(doc, field_name)
    if idx == -1: return False
    values = doc.get("Values", [])
    if 0 <= row_index < len(values):
        values[row_index][idx] = value
        return True
    return False

# Returns the rows where field_name equals value. Empty list if the field is unknown.
def bejson_core_filter_rows(doc: dict, field_name: str, value: Any) -> list:
    idx = bejson_core_get_field_index(doc, field_name)
    if idx == -1: return []
    return [row for row in doc.get("Values", []) if row[idx] == value]

# Sorts Values in place by one field (None sorts as empty string).
def bejson_core_sort_by_field(doc: dict, field_name: str, reverse: bool = False) -> None:
    idx = bejson_core_get_field_index(doc, field_name)
    if idx == -1: return
    doc["Values"].sort(key=lambda x: x[idx] if x[idx] is not None else "", reverse=reverse)

# Cheap presence check: all six mandatory top-level keys exist. This is NOT full validation -- use bejson_validator_* for the 104/104a/104db rules.
def bejson_core_is_valid(doc: dict) -> bool:
    # Simplified validity check
    required = ["Format", "Format_Version", "Format_Creator", "Records_Type", "Fields", "Values"]
    return all(k in doc for k in required)

# Returns Format_Version ('104', '104a' or '104db'), or 'unknown'. MFDB has no Format_Version of its own (its manifest is 104a).
def bejson_core_get_version(doc: dict) -> str:
    return doc.get("Format_Version", "unknown")

# Returns {record_count, field_count, version} for a document.
def bejson_core_get_stats(doc: dict) -> dict:
    return {
        "record_count": bejson_core_get_record_count(doc),
        "field_count": len(doc.get("Fields", [])),
        "version": bejson_core_get_version(doc)
    }