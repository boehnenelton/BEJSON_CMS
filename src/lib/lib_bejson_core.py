"""
Library:      lib_bejson_core.py
Family:       Core
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.0.3 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-06-05
Description:  Low-level atomic operations and data structure management.
REMEDIATED:   Implemented ResilientPIDLock (Policy Sec. 48).
REMEDIATED:   Internal metadata stripping in atomic write (Audit Finding 13).
"""

import json
import os
import sys
import time
import shutil
import tempfile
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

class BEJSONCoreError(Exception):
    """Raised when a BEJSON core operation fails."""
    def __init__(self, message: str, code: int = None):
        super().__init__(message)
        self.code = code

class ResilientPIDLock:
    def __init__(self, target_path: Union[str, Path], timeout_seconds: int = 10):
        self.target    = Path(target_path)
        self.lock_dir  = Path(f"{target_path}.lockdir")
        self.meta_file = self.lock_dir / "lock_meta.json"
        self.timeout   = timeout_seconds

    def acquire(self) -> bool:
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            try:
                self.lock_dir.mkdir(exist_ok=False)
                self.meta_file.write_text(json.dumps({
                    "pid":       os.getpid(),
                    "timestamp": int(time.time())
                }))
                return True
            except FileExistsError:
                if self.meta_file.exists():
                    try:
                        meta      = json.loads(self.meta_file.read_text())
                        owner_pid = meta.get("pid")
                        if owner_pid:
                            os.kill(owner_pid, 0)  # Signal 0: check if alive
                    except (ProcessLookupError, OSError):
                        # Owner is dead — safely reclaim
                        self.release()
                        continue
                    except Exception:
                        pass
                time.sleep(0.1)
        return False

    def release(self):
        if self.meta_file.exists():
            try:
                self.meta_file.unlink()
            except OSError:
                pass
        try:
            self.lock_dir.rmdir()
        except OSError:
            pass

    def __enter__(self):
        if not self.acquire():
            raise OSError(53, "Mutex lock timeout expired (E_MFDB_CORE_LOCK_FAILED)")
        return self

    def __exit__(self, *_):
        self.release()

from lib_bejson_env import resolve_path

def bejson_core_load_file(path: str) -> Optional[dict]:
    """Loads a BEJSON file and returns the dictionary."""
    path = resolve_path(path)
    if not path:
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"[BEJSON_CORE] Failed to load {path}: {e}")
        return None

def bejson_core_atomic_write(path: str, data: dict) -> bool:
    """Writes a BEJSON file atomically using a temp file and sync."""
    target_dir = os.path.dirname(os.path.abspath(path))
    os.makedirs(target_dir, exist_ok=True)

    # RE-ALIGNED: Strip internal metadata keys (starting with _) before write
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

def bejson_core_get_field_map(doc: dict) -> Dict[str, int]:
    """
    Returns a mapping of field name to index.
    Utilizes both in-document caching and a global cache for performance.
    """
    # High-performance in-document cache check
    if "_bejson_field_map" in doc:
        return doc["_bejson_field_map"]

    fields = doc.get("Fields", [])
    if not fields:
        return {}
    
    # Create a unique key for this field structure for the global cache
    field_names = tuple(f["name"] for f in fields)
    cache_key = (doc.get("Format_Version"), field_names)
    
    if cache_key in _FIELD_MAP_CACHE:
        field_map = _FIELD_MAP_CACHE[cache_key]
    else:
        # Build and update global cache
        field_map = {f["name"]: i for i, f in enumerate(fields)}
        _FIELD_MAP_CACHE[cache_key] = field_map
    
    # Inject into document for subsequent O(1) lookups
    try:
        doc["_bejson_field_map"] = field_map
    except Exception:
        pass # In case doc is immutable or not a dict
        
    return field_map

def bejson_core_get_field_index(doc: dict, field_name: str) -> int:
    """Returns the positional index of a field name using the cache."""
    field_map = bejson_core_get_field_map(doc)
    return field_map.get(field_name, -1)

def bejson_core_create_104(record_type: str, fields: list, values: list) -> dict:
    return {
        "Format": "BEJSON",
        "Format_Version": "104",
        "Format_Creator": "Elton Boehnen",
        "Records_Type": [record_type],
        "Fields": fields,
        "Values": values
    }

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

def bejson_core_create_104db(record_types: list, fields: list, values: list) -> dict:
    return {
        "Format": "BEJSON",
        "Format_Version": "104db",
        "Format_Creator": "Elton Boehnen",
        "Records_Type": record_types,
        "Fields": fields,
        "Values": values
    }

# --- Missing Functions for MFDB and Parser Compatibility ---

def bejson_core_load_string(content: str) -> Optional[dict]:
    try:
        return json.loads(content)
    except Exception as e:
        logging.error(f"[BEJSON_CORE] Failed to load JSON string: {e}")
        return None

def bejson_core_get_record_count(doc: dict) -> int:
    return len(doc.get("Values", []))

def bejson_core_add_record(doc: dict, record: list) -> bool:
    if len(record) != len(doc.get("Fields", [])):
        return False
    doc.setdefault("Values", []).append(record)
    return True

def bejson_core_remove_record(doc: dict, index: int) -> bool:
    values = doc.get("Values", [])
    if 0 <= index < len(values):
        values.pop(index)
        return True
    return False

def bejson_core_update_field(doc: dict, row_index: int, field_name: str, value: Any) -> bool:
    idx = bejson_core_get_field_index(doc, field_name)
    if idx == -1: return False
    values = doc.get("Values", [])
    if 0 <= row_index < len(values):
        values[row_index][idx] = value
        return True
    return False

def bejson_core_filter_rows(doc: dict, field_name: str, value: Any) -> list:
    idx = bejson_core_get_field_index(doc, field_name)
    if idx == -1: return []
    return [row for row in doc.get("Values", []) if row[idx] == value]

def bejson_core_sort_by_field(doc: dict, field_name: str, reverse: bool = False) -> None:
    idx = bejson_core_get_field_index(doc, field_name)
    if idx == -1: return
    doc["Values"].sort(key=lambda x: x[idx] if x[idx] is not None else "", reverse=reverse)

def bejson_core_is_valid(doc: dict) -> bool:
    # Simplified validity check
    required = ["Format", "Format_Version", "Format_Creator", "Records_Type", "Fields", "Values"]
    return all(k in doc for k in required)

def bejson_core_get_version(doc: dict) -> str:
    return doc.get("Format_Version", "unknown")

def bejson_core_get_stats(doc: dict) -> dict:
    return {
        "record_count": bejson_core_get_record_count(doc),
        "field_count": len(doc.get("Fields", [])),
        "version": bejson_core_get_version(doc)
    }
