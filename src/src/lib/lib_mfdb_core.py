"""
Library:      lib_mfdb_core.py
Family:       Core
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.0.1 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-18
Description:  Multi-file database orchestrator managing manifests and entity synchronization.
"""

# v1.21 adds Dynamic Recovery and Self-Healing.

import json
import os
import shutil
import tempfile
import zipfile
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from lib_bejson_core import (
    BEJSONCoreError,
    bejson_core_atomic_write,
    bejson_core_add_record,
    bejson_core_remove_record,
    bejson_core_update_field,
    bejson_core_load_file,
    bejson_core_get_record_count,
    bejson_core_filter_rows,
    bejson_core_sort_by_field,
    bejson_core_get_field_index,
)
from lib_mfdb_validator import (
    MFDBValidationError,
    mfdb_validator_validate_manifest,
    _load_json,
    _rows_as_dicts,
    _resolve_entity_path,
    E_MFDB_BIDIRECTIONAL_FAIL,
    E_MFDB_ENTITY_NOT_FOUND,
    E_MFDB_MANIFEST_NOT_FOUND,
)

try:
    from lib_bejson_errors import (
        E_MFDB_CORE_MANIFEST_NOT_FOUND,
        E_MFDB_CORE_ENTITY_NOT_FOUND,
        E_MFDB_CORE_WRITE_FAILED,
        E_MFDB_CORE_LOCK_FAILED,
        E_MFDB_CORE_INVALID_OPERATION,
        E_MFDB_CORE_INDEX_OUT_OF_BOUNDS,
        E_MFDB_CORE_JOIN_FAILED,
        E_MFDB_CORE_ARCHIVE_ERROR,
        E_MFDB_CORE_MOUNT_CONFLICT
    )
except ImportError as e:
    import logging
    logging.critical(f"[MFDB_CORE] FATAL: Error registry unreachable: {e}")
    raise SystemExit(1)


class MFDBCoreError(Exception):
    """Raised when an MFDB core operation fails."""
    def __init__(self, message: str, code: int):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_manifest_entries(manifest_path: str) -> list[dict]:
    doc = _load_json(manifest_path)
    return _rows_as_dicts(doc)


def _get_manifest_entry(manifest_path: str, entity_name: str) -> dict:
    entries = _get_manifest_entries(manifest_path)
    entry   = next((e for e in entries if e.get("entity_name") == entity_name), None)
    if entry is None:
        raise MFDBCoreError(
            f"Entity '{entity_name}' not found in manifest: {manifest_path}",
            E_MFDB_CORE_ENTITY_NOT_FOUND,
        )
    return entry



def _read_file_content(path: str) -> Optional[str]:
    """Reads file content, supporting .mfdb.zip archives."""
    p = Path(path)
    try:
        if p.is_file() and not path.lower().endswith(".zip"):
            return p.read_text(encoding="utf-8")
        
        # Check for zip path parts
        parts = p.parts
        for i, part in enumerate(parts):
            if part.lower().endswith(".zip"):
                zip_path = str(Path(*parts[:i+1]))
                inner_path = "/".join(parts[i+1:])
                if os.path.exists(zip_path):
                    with zipfile.ZipFile(zip_path, "r") as z:
                        if inner_path in z.namelist():
                            return z.read(inner_path).decode("utf-8")
                        elif not inner_path and "104a.mfdb.bejson" in z.namelist():
                             return z.read("104a.mfdb.bejson").decode("utf-8")
        
        if not p.exists():
            return None
            
        return p.read_text(encoding="utf-8")
    except Exception:
        return None

def _get_entity_path(manifest_path: str, entity_name: str) -> str:
    entry = _get_manifest_entry(manifest_path, entity_name)
    return _resolve_entity_path(manifest_path, entry["file_path"])


def _load_entity_doc(manifest_path: str, entity_name: str) -> dict:
    """Load and validate the raw BEJSON 104 doc for an entity."""
    entity_path = _get_entity_path(manifest_path, entity_name)
    content = _read_file_content(entity_path)
    if content is None:
        raise MFDBCoreError(
            f"Failed to read entity file: {entity_name} ({entity_path})",
            E_MFDB_CORE_ENTITY_NOT_FOUND
        )
    from lib_bejson_core import bejson_core_load_string
    doc = bejson_core_load_string(content)
    if doc is None:
        raise MFDBCoreError(
            f"Failed to load entity doc: {entity_name} ({entity_path})",
            E_MFDB_CORE_ENTITY_NOT_FOUND
        )
    return doc


def _write_entity_doc(doc: dict, entity_path: str) -> None:
    bejson_core_atomic_write(entity_path, doc)


def _write_manifest_doc(doc: dict, manifest_path: str) -> None:
    bejson_core_atomic_write(manifest_path, doc)


def _update_manifest_record_count(
    manifest_path: str, entity_name: str, count: int
) -> None:
    """Write a corrected record_count into the manifest for one entity."""
    doc        = _load_json(manifest_path)
    fn_list    = [f["name"] for f in doc["Fields"]]
    if "record_count" not in fn_list or "entity_name" not in fn_list:
        return
    rc_idx = fn_list.index("record_count")
    en_idx = fn_list.index("entity_name")
    for row in doc["Values"]:
        if row[en_idx] == entity_name:
            row[rc_idx] = count
            break
    _write_manifest_doc(doc, manifest_path)


def _calculate_file_hash(file_path: str) -> str:
    """Generate SHA-256 hash for archive integrity checks."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


# ---------------------------------------------------------------------------
# MFDBArchive (v1.2 Feature)
# ---------------------------------------------------------------------------

class MFDBArchive:
    """
    Handles .mfdb.zip packaging, virtual mounting, and atomic repacking.
    Standardized in MFDB v1.2 for portable transport.
    Enhanced for CoreEvolution with sticky mounting and validation safety.
    """

    @staticmethod
    def mount(archive_path: str, target_dir: str, force: bool = False, sticky: bool = True) -> str:
        """
        Extract an MFDB archive to a workspace and create a session lock.
        If sticky=True, it reuses existing valid extracted files.
        Returns the absolute path to the extracted manifest.
        """
        arc_p = Path(archive_path)
        if not arc_p.exists():
            raise MFDBCoreError(f"Archive not found: {archive_path}", E_MFDB_CORE_ARCHIVE_ERROR)

        target_p = Path(target_dir)
        lock_file = target_p / ".mfdb_lock"
        manifest_path = target_p / "104a.mfdb.bejson"

        # Sticky check: If valid files exist and hash matches, just return manifest
        if sticky and lock_file.exists() and manifest_path.exists():
            try:
                with open(lock_file, "r") as f:
                    lock_data = json.load(f)
                
                # Check if archive hash matches the one we mounted
                current_arc_hash = _calculate_file_hash(archive_path)
                if lock_data.get("original_hash") == current_arc_hash:
                    # Validate the database structure before trusting the sticky mount
                    from lib_mfdb_validator import mfdb_validator_validate_database
                    if mfdb_validator_validate_database(str(manifest_path)):
                        return str(manifest_path.absolute())
            except Exception:
                pass # Fall through to full re-extract if sticky fails

        if lock_file.exists() and not force:
            with open(lock_file, "r") as f:
                lock_data = json.load(f)
            if lock_data.get("pid") != os.getpid():
                raise MFDBCoreError(
                    f"Workspace {target_dir} is already locked by PID {lock_data.get('pid')}",
                    E_MFDB_CORE_MOUNT_CONFLICT
                )

        # Clear existing workspace if it was invalid or if we are forcing re-extract
        if target_p.exists():
            shutil.rmtree(target_dir)
        target_p.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(target_dir)

        if not manifest_path.exists():
            shutil.rmtree(target_dir)
            raise MFDBCoreError("Invalid MFDB Archive: 104a.mfdb.bejson missing.", E_MFDB_CORE_ARCHIVE_ERROR)

        # Create session lock with metadata
        lock_data = {
            "pid": os.getpid(),
            "mounted_at": datetime.now(timezone.utc).isoformat(),
            "original_hash": _calculate_file_hash(archive_path),
            "archive_path": str(arc_p.absolute())
        }
        with open(lock_file, "w") as f:
            json.dump(lock_data, f)

        return str(manifest_path.absolute())

    @staticmethod
    def commit(mount_dir: str, archive_path: Optional[str] = None, validate: bool = True) -> str:
        """
        Repack the workspace into a .mfdb.zip file atomically.
        Refuses to write if validation fails (if validate=True).
        """
        mount_p = Path(mount_dir)
        lock_file = mount_p / ".mfdb_lock"
        manifest_path = mount_p / "104a.mfdb.bejson"
        
        if not lock_file.exists():
            raise MFDBCoreError(f"No active mount session found in {mount_dir}", E_MFDB_CORE_INVALID_OPERATION)

        if validate:
            if not manifest_path.exists():
                raise MFDBCoreError("Commit rejected: Manifest missing in workspace.", E_MFDB_CORE_WRITE_FAILED)
            
            # Run full database validation before repacking
            from lib_mfdb_validator import mfdb_validator_validate_database
            try:
                mfdb_validator_validate_database(str(manifest_path))
            except Exception as e:
                raise MFDBCoreError(f"Commit rejected: Validation failed. {str(e)}", E_MFDB_CORE_WRITE_FAILED)

        with open(lock_file, "r") as f:
            lock_data = json.load(f)

        dest_path = archive_path or lock_data.get("archive_path")
        if not dest_path:
            raise MFDBCoreError("Destination archive path unknown.", E_MFDB_CORE_ARCHIVE_ERROR)

        # Create new archive in temp location
        fd, temp_arc = tempfile.mkstemp(suffix=".mfdb.zip")
        os.close(fd)

        try:
            with zipfile.ZipFile(temp_arc, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(mount_dir):
                    for file in files:
                        if file == ".mfdb_lock": continue
                        file_path = Path(root) / file
                        arc_name = file_path.relative_to(mount_dir)
                        zipf.write(file_path, arc_name)
            
            # Atomic swap
            shutil.move(temp_arc, dest_path)
            
            # Update lock with new hash to maintain sticky state
            lock_data["original_hash"] = _calculate_file_hash(dest_path)
            with open(lock_file, "w") as f:
                json.dump(lock_data, f)
                
        except Exception as e:
            if os.path.exists(temp_arc): os.remove(temp_arc)
            raise MFDBCoreError(f"Commit failed: {str(e)}", E_MFDB_CORE_WRITE_FAILED)

        return dest_path


    @staticmethod
    def resurrect_file(mount_dir: str, relative_path: str) -> bool:
        """
        Surgically extract a single file from the .mfdb.zip archive into the workspace.
        Used for recovery when an entity file is missing or corrupted.
        """
        mount_p = Path(mount_dir)
        lock_file = mount_p / ".mfdb_lock"
        if not lock_file.exists():
            return False

        with open(lock_file, "r") as f:
            lock_data = json.load(f)
        
        archive_path = lock_data.get("archive_path")
        if not archive_path or not os.path.exists(archive_path):
            return False

        try:
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                # Check if file exists in zip
                if relative_path in zip_ref.namelist():
                    zip_ref.extract(relative_path, mount_dir)
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def unmount(mount_dir: str, cleanup: bool = True):
        """Release the lock and optionally delete the workspace."""
        mount_p = Path(mount_dir)
        lock_file = mount_p / ".mfdb_lock"
        if lock_file.exists():
            os.remove(lock_file)
        if cleanup and mount_p.exists():
            shutil.rmtree(mount_dir)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def mfdb_core_discover(file_path: str) -> str:
    """
    Identify the MFDB role of any file.
    Returns one of: 'manifest', 'entity', 'archive', 'standalone'
    """
    p = Path(file_path)
    if not p.exists():
        raise MFDBCoreError(f"File not found: {file_path}", E_MFDB_CORE_MANIFEST_NOT_FOUND)

    if p.suffix == ".zip" and ".mfdb" in p.name:
        return "archive"

    try:
        doc = _load_json(file_path)
    except Exception:
        return "standalone"

    version  = doc.get("Format_Version", "")
    filename = p.name
    if version == "104a" and filename.endswith(".mfdb.bejson"):
        return "manifest"
    if version == "104" and doc.get("Parent_Hierarchy"):
        return "entity"
    return "standalone"


# ---------------------------------------------------------------------------
# Recovery & Repair (v1.21 Feature)
# ---------------------------------------------------------------------------

def mfdb_core_deep_verify(manifest_path: str) -> List[Dict[str, Any]]:
    """
    Performs a deep audit of the entire MFDB database.
    Checks for:
      - Positional integrity (field vs value length)
      - Type adherence (basic primitives)
      - Manifest-entity consistency (record counts)
      - Foreign key potential breakage (optional warnings)
    Returns a list of finding dicts.
    """
    findings = []
    manifest_doc = bejson_core_load_file(manifest_path)
    entries = _rows_as_dicts(manifest_doc)
    
    for entry in entries:
        entity_name = entry.get("entity_name")
        file_path_rel = entry.get("file_path")
        expected_count = entry.get("record_count")
        
        entity_path = _resolve_entity_path(manifest_path, file_path_rel)
        if not os.path.exists(entity_path):
            findings.append({"entity": entity_name, "error": "MISSING_FILE", "path": file_path_rel})
            continue
            
        try:
            entity_doc = bejson_core_load_file(entity_path)
            # 1. Check positional integrity
            fields = entity_doc.get("Fields", [])
            field_count = len(fields)
            values = entity_doc.get("Values", [])
            actual_count = len(values)
            
            if expected_count is not None and expected_count != actual_count:
                findings.append({
                    "entity": entity_name, 
                    "warning": "COUNT_MISMATCH", 
                    "expected": expected_count, 
                    "actual": actual_count
                })
            
            for i, row in enumerate(values):
                if len(row) != field_count:
                    findings.append({
                        "entity": entity_name, 
                        "error": "POSITIONAL_VIOLATION", 
                        "row": i, 
                        "expected": field_count, 
                        "actual": len(row)
                    })
                
                # 2. Basic Type verification
                for j, val in enumerate(row):
                    if val is None: continue
                    f_type = fields[j].get("type")
                    if f_type == "integer" and not isinstance(val, int):
                         findings.append({"entity": entity_name, "warning": "TYPE_MISMATCH", "row": i, "field": fields[j]["name"], "expected": "integer", "actual": type(val).__name__})
                    elif f_type == "number" and not isinstance(val, (int, float)):
                         findings.append({"entity": entity_name, "warning": "TYPE_MISMATCH", "row": i, "field": fields[j]["name"], "expected": "number", "actual": type(val).__name__})
                    elif f_type == "boolean" and not isinstance(val, bool):
                         findings.append({"entity": entity_name, "warning": "TYPE_MISMATCH", "row": i, "field": fields[j]["name"], "expected": "boolean", "actual": type(val).__name__})

        except Exception as e:
            findings.append({"entity": entity_name, "error": "CORRUPT_JSON", "message": str(e)})
            
    return findings


def mfdb_core_self_heal(manifest_path: str) -> Dict[str, Any]:
    """
    Attempts to fix common issues identified by deep_verify.
    Actions:
      - Resyncs record_count in manifest.
      - Padds short records with nulls (Positional Repair).
      - Removes invalid records if necessary (Extreme measure).
    Returns a report of actions taken.
    """
    report = {"actions": [], "remaining_errors": []}
    findings = mfdb_core_deep_verify(manifest_path)
    
    needs_manifest_sync = False
    
    for f in findings:
        entity = f.get("entity")
        if f.get("warning") == "COUNT_MISMATCH":
            _update_manifest_record_count(manifest_path, entity, f["actual"])
            report["actions"].append(f"Resynced record_count for {entity} to {f['actual']}")
        
        elif f.get("error") == "POSITIONAL_VIOLATION":
            # Attempt repair
            entity_path = _get_entity_path(manifest_path, entity)
            try:
                doc = bejson_core_load_file(entity_path)
                field_count = len(doc["Fields"])
                repaired = 0
                for i, row in enumerate(doc["Values"]):
                    if len(row) < field_count:
                        doc["Values"][i] = row + [None] * (field_count - len(row))
                        repaired += 1
                    elif len(row) > field_count:
                        doc["Values"][i] = row[:field_count]
                        repaired += 1
                if repaired > 0:
                    bejson_core_atomic_write(entity_path, doc)
                    report["actions"].append(f"Repaired {repaired} positional violations in {entity}")
            except Exception as e:
                report["remaining_errors"].append(f"Failed to repair {entity}: {str(e)}")
        
        elif f.get("error") == "MISSING_FILE":
            # Attempt resurrection
            mount_dir = os.path.dirname(os.path.abspath(manifest_path))
            if MFDBArchive.resurrect_file(mount_dir, f["path"]):
                report["actions"].append(f"Resurrected missing entity file: {f['path']}")
            else:
                report["remaining_errors"].append(f"Could not resurrect {entity}")
        
        elif f.get("error"):
            report["remaining_errors"].append(f"{entity}: {f['error']} - {f.get('message', '')}")

    return report


def _mfdb_core_repair_hierarchy(entity_path: str, new_hierarchy: str) -> bool:
    """Surgically update the Parent_Hierarchy header in a BEJSON 104 file."""
    try:
        doc = bejson_core_load_file(entity_path)
        doc["Parent_Hierarchy"] = new_hierarchy
        bejson_core_atomic_write(entity_path, doc)
        return True
    except Exception:
        return False


def mfdb_core_smart_repair(manifest_path: str, error: MFDBValidationError) -> bool:
    """
    Attempt to automatically repair the MFDB workspace based on a validation error.
    Supported:
      - E_MFDB_ENTITY_NOT_FOUND (33): Resurrects from archive.
      - E_MFDB_BIDIRECTIONAL_FAIL (38) / E_MFDB_MANIFEST_NOT_FOUND (37): Patches Parent_Hierarchy.
    """
    mount_dir = os.path.dirname(os.path.abspath(manifest_path))
    ctx = error.context

    if error.code == E_MFDB_ENTITY_NOT_FOUND or error.code == 33:
        rel_path = ctx.get("file_path_rel")
        if rel_path:
            return MFDBArchive.resurrect_file(mount_dir, rel_path)

    if error.code == E_MFDB_BIDIRECTIONAL_FAIL or error.code == E_MFDB_MANIFEST_NOT_FOUND:
        entity_path = ctx.get("actual_path")
        new_hierarchy = ctx.get("suggested_hierarchy")
        # If suggested_hierarchy is missing but we are in a mount_dir, 
        # assume standard v1.21 structure
        if not new_hierarchy and entity_path:
             new_hierarchy = "../104a.mfdb.bejson"

        if entity_path and new_hierarchy:
            return _mfdb_core_repair_hierarchy(entity_path, new_hierarchy)

    return False


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


def mfdb_core_load_manifest(manifest_path: str) -> list[dict]:
    """
    Validate and load the manifest.
    Returns all manifest records as a list of field-name-keyed dicts.
    """
    mfdb_validator_validate_manifest(manifest_path)
    return _get_manifest_entries(manifest_path)


def mfdb_core_load_entity(manifest_path: str, entity_name: str) -> list[dict]:
    """
    Load all records for a named entity.
    Returns a list of field-name-keyed dicts (dense - no null-padding).
    """
    doc = _load_entity_doc(manifest_path, entity_name)
    return _rows_as_dicts(doc)


def mfdb_core_get_entity_doc(manifest_path: str, entity_name: str) -> dict:
    """Return the raw BEJSON 104 document dict for a named entity."""
    return _load_entity_doc(manifest_path, entity_name)


def mfdb_core_get_stats(manifest_path: str) -> dict:
    """Return a summary statistics dict for the entire MFDB."""
    doc     = _load_json(manifest_path)
    entries = _rows_as_dicts(doc)

    entity_stats = []
    for entry in entries:
        resolved = _resolve_entity_path(manifest_path, entry["file_path"])
        if os.path.exists(resolved):
            edoc        = _load_json(resolved)
            rec_count   = len(edoc.get("Values", []))
            field_count = len(edoc.get("Fields", []))
        else:
            rec_count   = -1
            field_count = -1

        entity_stats.append({
            "entity_name":  entry["entity_name"],
            "file_path":    entry["file_path"],
            "record_count": rec_count,
            "field_count":  field_count,
            "primary_key":  entry.get("primary_key"),
        })

    return {
        "db_name":        doc.get("DB_Name", ""),
        "schema_version": doc.get("Schema_Version", ""),
        "entity_count":   len(entries),
        "entities":       entity_stats,
    }


# ---------------------------------------------------------------------------
# Query operations
# ---------------------------------------------------------------------------

def mfdb_core_query_entity(
    manifest_path: str,
    entity_name: str,
    predicate: Callable[[dict], bool],
) -> list[dict]:
    """Return all records from an entity for which predicate(record) is True."""
    records = mfdb_core_load_entity(manifest_path, entity_name)
    return [r for r in records if predicate(r)]


def mfdb_core_build_index(
    manifest_path: str,
    entity_name: str,
    field_name: str,
) -> dict:
    """Build an in-memory hash index on a field for fast lookups."""
    records = mfdb_core_load_entity(manifest_path, entity_name)
    return {r[field_name]: r for r in records if r.get(field_name) is not None}


def mfdb_core_join(
    manifest_path: str,
    from_entity:   str,
    to_entity:     str,
    from_fk:       str,
    to_pk:         str,
) -> list[dict]:
    """Cross-entity equi-join."""
    from_records = mfdb_core_load_entity(manifest_path, from_entity)
    to_index     = mfdb_core_build_index(manifest_path, to_entity, to_pk)

    results = []
    for record in from_records:
        fk_val = record.get(from_fk)
        target = to_index.get(fk_val, {})
        merged = dict(record)
        for k, v in target.items():
            merged[f"{to_entity}__{k}"] = v
        results.append(merged)

    return results


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

def mfdb_core_add_entity_record(
    manifest_path: str,
    entity_name:   str,
    values:        list,
    sync_count:    bool = True,
) -> dict:
    """Append a record to an entity file."""
    doc = _load_entity_doc(manifest_path, entity_name)
    if not bejson_core_add_record(doc, values):
        raise BEJSONCoreError(f"Failed to add record to {entity_name}")
        
    entity_path = _get_entity_path(manifest_path, entity_name)
    _write_entity_doc(doc, entity_path)
    if sync_count:
        _update_manifest_record_count(manifest_path, entity_name, len(doc["Values"]))
    return doc


def mfdb_core_remove_entity_record(
    manifest_path: str,
    entity_name:   str,
    record_index:  int,
    sync_count:    bool = True,
) -> dict:
    """Remove a record at record_index from an entity file."""
    doc = _load_entity_doc(manifest_path, entity_name)
    if not bejson_core_remove_record(doc, record_index):
        raise BEJSONCoreError(f"Failed to remove record {record_index} from {entity_name}")

    entity_path = _get_entity_path(manifest_path, entity_name)
    _write_entity_doc(doc, entity_path)
    if sync_count:
        _update_manifest_record_count(manifest_path, entity_name, len(doc["Values"]))
    return doc


def mfdb_core_update_entity_record(
    manifest_path: str,
    entity_name:   str,
    record_index:  int,
    field_name:    str,
    new_value:     Any,
) -> dict:
    """Update a single named field in a specific record of an entity file."""
    doc = _load_entity_doc(manifest_path, entity_name)
    if not isinstance(doc, dict):
        raise BEJSONCoreError(f"Malformed entity doc for {entity_name}")

    if not bejson_core_update_field(doc, record_index, field_name, new_value):
        raise BEJSONCoreError(f"Failed to update field '{field_name}' in {entity_name}")

    entity_path = _get_entity_path(manifest_path, entity_name)
    _write_entity_doc(doc, entity_path)
    return doc


# ---------------------------------------------------------------------------
# Manifest sync
# ---------------------------------------------------------------------------

def mfdb_core_sync_manifest_count(manifest_path: str, entity_name: str) -> int:
    """Re-count actual rows in an entity file and update the manifest."""
    entity_path = _get_entity_path(manifest_path, entity_name)
    edoc        = _load_json(entity_path)
    count       = len(edoc.get("Values", []))
    _update_manifest_record_count(manifest_path, entity_name, count)
    return count


def mfdb_core_sync_all_counts(manifest_path: str) -> dict:
    """Sync record_count for every entity listed in the manifest."""
    entries = _get_manifest_entries(manifest_path)
    results = {}
    for entry in entries:
        name = entry["entity_name"]
        results[name] = mfdb_core_sync_manifest_count(manifest_path, name)
    return results


# ---------------------------------------------------------------------------
# Database creation
# ---------------------------------------------------------------------------

def mfdb_core_create_entity_file(
    manifest_path:  str,
    entity_name:    str,
    fields:         list[dict],
    description:    str = "",
    primary_key:    str = "",
    schema_version: str = "1.0",
    file_path_rel:  str = "",
) -> str:
    """Create a new entity file and register it in an existing manifest."""
    manifest_dir = os.path.dirname(os.path.abspath(manifest_path))

    if not file_path_rel:
        file_path_rel = f"data/{entity_name.lower()}.bejson"

    resolved = os.path.normpath(os.path.join(manifest_dir, file_path_rel))
    os.makedirs(os.path.dirname(resolved), exist_ok=True)

    entity_dir         = os.path.dirname(resolved)
    rel_to_manifest    = os.path.relpath(manifest_path, entity_dir)

    entity_doc = {
        "Format":           "BEJSON",
        "Format_Version":   "104",
        "Format_Creator":   "Elton Boehnen",
        "Parent_Hierarchy": rel_to_manifest,
        "Records_Type":     [entity_name],
        "Fields":           fields,
        "Values":           [],
    }
    bejson_core_atomic_write(resolved, entity_doc)

    manifest_doc = _load_json(manifest_path)
    fn_list      = [f["name"] for f in manifest_doc["Fields"]]

    new_row = []
    for fn in fn_list:
        if   fn == "entity_name":    new_row.append(entity_name)
        elif fn == "file_path":      new_row.append(file_path_rel)
        elif fn == "description":    new_row.append(description or None)
        elif fn == "record_count":   new_row.append(0)
        elif fn == "schema_version": new_row.append(schema_version)
        elif fn == "primary_key":    new_row.append(primary_key or None)
        else:                        new_row.append(None)

    manifest_doc["Values"].append(new_row)
    _write_manifest_doc(manifest_doc, manifest_path)

    return resolved


def mfdb_core_create_database(
    root_dir:       str,
    db_name:        str,
    entities:       list[dict],
    db_description: str = "",
    schema_version: str = "1.0.0",
    author:         str = "Elton Boehnen",
    mfdb_version:   str = "1.3.1",
    network_role: str = "Master",
) -> str:
    """Create a new MFDB from scratch."""
    root = Path(root_dir)
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = str(root / "104a.mfdb.bejson")

    manifest_fields = [
        {"name": "entity_name",    "type": "string"},
        {"name": "file_path",      "type": "string"},
        {"name": "description",    "type": "string"},
        {"name": "record_count",   "type": "integer"},
        {"name": "schema_version", "type": "string"},
        {"name": "primary_key",    "type": "string"},
    ]

    manifest_values     = []
    entity_defs_to_file = []

    for entity in entities:
        name   = entity["name"]
        fp_rel = entity.get("file_path", f"data/{name.lower()}.bejson")
        desc   = entity.get("description", "")
        pk     = entity.get("primary_key", "")
        sv     = entity.get("schema_version", "1.0")
        fields = entity["fields"]

        manifest_values.append([name, fp_rel, desc or None, 0, sv, pk or None])
        entity_defs_to_file.append((name, fp_rel, fields))

    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest_doc = {
        "Format":          "BEJSON",
        "Format_Version":  "104a",
        "Format_Creator":  "Elton Boehnen",
        "MFDB_Version":    mfdb_version,
        "Network_Role": network_role,
        "DB_Name":         db_name,
        "DB_Description":  db_description,
        "Schema_Version":  schema_version,
        "Author":          author,
        "Created_At":      created_at,
        "Records_Type":    ["mfdb"],
        "Fields":          manifest_fields,
        "Values":          manifest_values,
    }

    bejson_core_atomic_write(manifest_path, manifest_doc)

    for entity_name, fp_rel, fields in entity_defs_to_file:
        resolved   = os.path.normpath(os.path.join(root_dir, fp_rel))
        entity_dir = os.path.dirname(resolved)
        os.makedirs(entity_dir, exist_ok=True)

        rel_to_manifest = os.path.relpath(manifest_path, entity_dir)

        entity_doc = {
            "Format":           "BEJSON",
            "Format_Version":   "104",
            "Format_Creator":   "Elton Boehnen",
            "Parent_Hierarchy": rel_to_manifest,
            "Records_Type":     [entity_name],
            "Fields":           fields,
            "Values":           [],
        }
        bejson_core_atomic_write(resolved, entity_doc)

    return manifest_path

def mfdb_core_resolve_path(path_str: str) -> str:
    """
    Hardening: Resolve system placeholders in paths using lib_bejson_env.
    Supports: {INTERNAL_STORAGE}, {ADMIN_ROOT}, {PROJECTS_ROOT}, 
             internal_storage, ~, and environment variables in ${VAR} format.
    """
    if not path_str:
        return path_str
    
    from lib_bejson_env import resolve_path
    return resolve_path(path_str)
