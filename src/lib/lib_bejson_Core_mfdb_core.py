"""
Library:        lib_bejson_Core_mfdb_core.py
Family:         Core
Description:    Multi-file database orchestrator managing manifests and entity synchronization.
Version:        2.3.0
Date:           2026-07-31
Author:         Elton Boehnen
Contact:        eltonboehnen@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  6e1a9c47-4d2f-4b83-a5c0-8f3b7e2d1a96

FEATURE (2026-07-31): Meta-GUID debug entity system. Every MFDB optionally
carries a meta-{uuid4} entity that logs every write operation with entity,
field, field_exists flag, row_index, success, duration_ms, pid, and notes.
Gated by Debug_Mode manifest header — zero overhead when off. Auto-trims at
Debug_Row_Cap rows. Debug_Reads flag adds read-path audit. Schema snapshot
on enable; mfdb_core_detect_schema_drift diffs live fields against snapshot.
mfdb_core_debug_summary and mfdb_core_get_failed_ops surface aggregated view.

FEATURE (2026-07-30): Step 5 (1.32 finalization) — ResilientPIDLock wired
around all 4 critical read-modify-write cycles.

FEATURE (2026-07-29): Federated Master/Slave node system.
mfdb_federation_push_config (Master→Slave atomic drop-zone push),
mfdb_federation_poll_dropzone (Slave polls its own dir for incoming configs),
and mfdb_federation_distill_logs (Slave truncates overflow rows and pushes
distilled metrics to Master's poll dir). Network_Role was already emitted on
manifest creation (2.0.1) — federation functions now wire the full protocol.
"""

# v1.21 adds Dynamic Recovery and Self-Healing.

import json
import os
import shutil
import tempfile
import time
import uuid
import zipfile
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from lib_bejson_Core_bejson_core import (
    BEJSONCoreError,
    ResilientPIDLock,
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
from lib_bejson_Core_mfdb_validator import (
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
    from lib_bejson_Core_bejson_errors import (
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
    from lib_bejson_Core_bejson_core import bejson_core_load_string
    doc = bejson_core_load_string(content)
    if doc is None:
        raise MFDBCoreError(
            f"Failed to load entity doc: {entity_name} ({entity_path})",
            E_MFDB_CORE_ENTITY_NOT_FOUND
        )
    return doc

def _write_entity_doc(doc: dict, entity_path: str) -> None:
    if not bejson_core_atomic_write(entity_path, doc):
        raise MFDBCoreError(f"Failed to write entity doc to {entity_path}", E_MFDB_CORE_WRITE_FAILED)

def _write_manifest_doc(doc: dict, manifest_path: str) -> None:
    if not bejson_core_atomic_write(manifest_path, doc):
        raise MFDBCoreError(f"Failed to write manifest doc to {manifest_path}", E_MFDB_CORE_WRITE_FAILED)

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
                    from lib_bejson_Core_mfdb_validator import mfdb_validator_validate_database
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
            # Secure extraction loop to mitigate Zip Slip.
            from lib_bejson_Core_bejson_path_guard import bejson_safe_join
            for member in zip_ref.namelist():
                # Skip directories as safe_join/open will handle them
                if member.endswith('/'): continue
                
                # Boundary check via safe_join
                try:
                    safe_path = bejson_safe_join(target_dir, member)
                    # Ensure parent directory exists
                    os.makedirs(os.path.dirname(safe_path), exist_ok=True)
                    with zip_ref.open(member) as source, open(safe_path, "wb") as target:
                        shutil.copyfileobj(source, target)
                except ValueError as e:
                    logging.error(f"[MFDB_CORE] Security Alert: {e}")
                    raise MFDBCoreError(f"Secure extraction failed: {e}", E_MFDB_CORE_ARCHIVE_ERROR)

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
            from lib_bejson_Core_mfdb_validator import mfdb_validator_validate_database
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
        try:
            if f.get("warning") == "COUNT_MISMATCH":
                # FIX (N1): was f["actual"] - direct bracket access while
                # every other field in this loop uses .get(). A malformed
                # deep_verify() finding missing "actual" (or a race between
                # verify and heal) raised an unhandled KeyError that aborted
                # the whole self-heal pass mid-loop, leaving already-healed
                # findings healed but everything after silently unprocessed.
                # Now: skip this one finding and keep going, same as any
                # other per-finding failure below.
                actual = f.get("actual")
                if actual is None:
                    report["remaining_errors"].append(
                        f"Skipped COUNT_MISMATCH heal for {entity}: finding has no 'actual' value"
                    )
                    continue
                _update_manifest_record_count(manifest_path, entity, actual)
                report["actions"].append(f"Resynced record_count for {entity} to {actual}")

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
                fpath = f.get("path")
                if fpath is None:
                    report["remaining_errors"].append(f"Skipped resurrection for {entity}: finding has no 'path' value")
                    continue
                if MFDBArchive.resurrect_file(mount_dir, fpath):
                    report["actions"].append(f"Resurrected missing entity file: {fpath}")
                else:
                    report["remaining_errors"].append(f"Could not resurrect {entity}")

            elif f.get("error"):
                report["remaining_errors"].append(f"{entity}: {f.get('error')} - {f.get('message', '')}")
        except Exception as e:
            # FIX (N1, extended): any other unexpected shape of a single
            # finding can no longer abort the batch either - captured and
            # reported like any other heal failure, and the loop continues.
            report["remaining_errors"].append(f"Unexpected error healing finding for {entity}: {e}")

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
    doc = _load_json(manifest_path)
    if not isinstance(doc, dict):
        raise MFDBCoreError(f"Failed to load manifest: {manifest_path} (not a dict)", E_MFDB_CORE_MANIFEST_NOT_FOUND)
    return _rows_as_dicts(doc)

def mfdb_core_load_entity(manifest_path: str, entity_name: str) -> list[dict]:
    """
    Load all records for a named entity.
    Returns a list of field-name-keyed dicts (dense - no null-padding).
    When Debug_Reads is enabled, logs a READ entry to the meta entity.
    """
    _t0 = time.monotonic()
    doc = _load_entity_doc(manifest_path, entity_name)
    if not isinstance(doc, dict):
        raise MFDBCoreError(f"Failed to load entity: {entity_name} (not a dict)", E_MFDB_CORE_ENTITY_NOT_FOUND)
    result = _rows_as_dicts(doc)
    _mfdb_meta_log(
        manifest_path, "READ", entity_name,
        field_name=None, field_exists=None,
        row_index=None, success=True,
        duration_ms=int((time.monotonic() - _t0) * 1000),
        notes=f"rows_returned={len(result)}",
        reads_only=True,
    )
    return result

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
    """Append a record to an entity file. Lock held for the full read-modify-write cycle."""
    _t0 = time.monotonic()
    _success = False
    entity_path = _get_entity_path(manifest_path, entity_name)
    try:
        with ResilientPIDLock(entity_path, timeout_seconds=10):
            doc = _load_entity_doc(manifest_path, entity_name)
            if not bejson_core_add_record(doc, values):
                raise BEJSONCoreError(f"Failed to add record to {entity_name}")
            _write_entity_doc(doc, entity_path)
            if sync_count:
                _update_manifest_record_count(manifest_path, entity_name, len(doc["Values"]))
        _success = True
        return doc
    finally:
        _mfdb_meta_log(
            manifest_path, "ADD", entity_name,
            field_name=None, field_exists=None,
            row_index=None, success=_success,
            duration_ms=int((time.monotonic() - _t0) * 1000),
            notes="" if _success else "add_record returned False",
        )

def mfdb_core_remove_entity_record(
    manifest_path: str,
    entity_name:   str,
    record_index:  int,
    sync_count:    bool = True,
) -> dict:
    """Remove a record at record_index from an entity file. Lock held for the full read-modify-write cycle."""
    _t0 = time.monotonic()
    _success = False
    entity_path = _get_entity_path(manifest_path, entity_name)
    try:
        with ResilientPIDLock(entity_path, timeout_seconds=10):
            doc = _load_entity_doc(manifest_path, entity_name)
            if not bejson_core_remove_record(doc, record_index):
                raise BEJSONCoreError(f"Failed to remove record {record_index} from {entity_name}")
            _write_entity_doc(doc, entity_path)
            if sync_count:
                _update_manifest_record_count(manifest_path, entity_name, len(doc["Values"]))
        _success = True
        return doc
    finally:
        _mfdb_meta_log(
            manifest_path, "REMOVE", entity_name,
            field_name=None, field_exists=None,
            row_index=record_index, success=_success,
            duration_ms=int((time.monotonic() - _t0) * 1000),
            notes="",
        )

def mfdb_core_update_entity_record(
    manifest_path: str,
    entity_name:   str,
    record_index:  int,
    field_name:    str,
    new_value:     Any,
) -> dict:
    """Update a single named field in a specific record. Lock held for the full read-modify-write cycle."""
    _t0 = time.monotonic()
    _success = False
    _field_exists = None
    entity_path = _get_entity_path(manifest_path, entity_name)
    try:
        with ResilientPIDLock(entity_path, timeout_seconds=10):
            doc = _load_entity_doc(manifest_path, entity_name)
            if not isinstance(doc, dict):
                raise BEJSONCoreError(f"Malformed entity doc for {entity_name}")
            _field_exists = any(f["name"] == field_name for f in doc.get("Fields", []))
            if not bejson_core_update_field(doc, record_index, field_name, new_value):
                raise BEJSONCoreError(f"Failed to update field '{field_name}' in {entity_name}")
            _write_entity_doc(doc, entity_path)
        _success = True
        return doc
    finally:
        _mfdb_meta_log(
            manifest_path, "UPDATE", entity_name,
            field_name=field_name, field_exists=_field_exists,
            row_index=record_index, success=_success,
            duration_ms=int((time.monotonic() - _t0) * 1000),
            notes="" if _field_exists else f"SCHEMA DRIFT: field '{field_name}' not in Fields[]",
        )

def mfdb_core_update_entity_record_bulk(
    manifest_path: str,
    entity_name:   str,
    record_index:  int,
    updates:       Dict[str, Any],
) -> dict:
    """Update multiple named fields in a specific record. Lock held for the full read-modify-write cycle."""
    _t0 = time.monotonic()
    _success = False
    _missing_fields: list = []
    entity_path = _get_entity_path(manifest_path, entity_name)
    try:
        with ResilientPIDLock(entity_path, timeout_seconds=10):
            doc = _load_entity_doc(manifest_path, entity_name)
            if not isinstance(doc, dict):
                raise BEJSONCoreError(f"Malformed entity doc for {entity_name}")
            _known = {f["name"] for f in doc.get("Fields", [])}
            _missing_fields = [k for k in updates if k not in _known]
            for field_name, new_value in updates.items():
                if not bejson_core_update_field(doc, record_index, field_name, new_value):
                    raise BEJSONCoreError(f"Failed to update field '{field_name}' in {entity_name}")
            _write_entity_doc(doc, entity_path)
        _success = True
        return doc
    finally:
        _notes = (f"SCHEMA DRIFT: unknown fields {_missing_fields}" if _missing_fields else "")
        _mfdb_meta_log(
            manifest_path, "UPDATE_BULK", entity_name,
            field_name=",".join(updates.keys()),
            field_exists=(len(_missing_fields) == 0),
            row_index=record_index, success=_success,
            duration_ms=int((time.monotonic() - _t0) * 1000),
            notes=_notes,
        )

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
    mfdb_version:   str = "1.31",
    network_role:   str = "Master",
    debug_mode:     bool = False,
    debug_row_cap:  int  = 500,
    debug_reads:    bool = False,
) -> str:
    """
    Create a new MFDB from scratch.
    debug_mode=True auto-creates a meta-{uuid} entity and activates write/read
    audit logging. Zero overhead when False.
    """
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

    if debug_mode:
        mfdb_core_enable_debug(manifest_path, row_cap=debug_row_cap, debug_reads=debug_reads)

    return manifest_path

def mfdb_core_resolve_path(path_str: str) -> str:
    """
    Hardening: Resolve system placeholders in paths using lib_bejson_Core_bejson_env.
    Supports: {INTERNAL_STORAGE}, {ADMIN_ROOT}, {PROJECTS_ROOT}, 
             internal_storage, ~, and environment variables in ${VAR} format.
    """
    if not path_str:
        return path_str
    
    from lib_bejson_Core_bejson_env import resolve_path
    return resolve_path(path_str)


# ── Federated Master / Slave node system ───────────────────────────────────────
# Network_Role ("Master" | "Slave") is already emitted on manifest creation
# (mfdb_core_create_database). This block wires the full runtime protocol:
#   - ConnectedSlave entity schema + creator (Master side)
#   - mfdb_federation_push_config   — Master atomically drops a 104a doc into
#                                      a Slave's local dropzone directory
#   - mfdb_federation_poll_dropzone — Slave polls its own dropzone for incoming
#                                      Master configs
#   - mfdb_federation_distill_logs  — Slave truncates overflow entity rows and
#                                      pushes a distilled summary to Master

CONNECTED_SLAVE_SCHEMA: List[Dict[str, str]] = [
    {"name": "slave_id",           "type": "string"},
    {"name": "label",              "type": "string"},
    {"name": "url",                "type": "string"},
    {"name": "role",               "type": "string"},
    {"name": "status",             "type": "string"},
    {"name": "supported_entities", "type": "array"},
]


def mfdb_core_create_connected_slave_entity(manifest_path: str) -> str:
    """
    Register a ConnectedSlave entity in the Master manifest and create its
    entity file. Raises if the node is not a Master (Network_Role check).
    Returns the created entity file path.
    """
    manifest_doc = _load_json(manifest_path)
    role = manifest_doc.get("Network_Role", "")
    if role != "Master":
        raise ValueError(
            "ConnectedSlave entity may only be created on a Master node "
            f"(Network_Role='Master'). Got: '{role}'"
        )
    return mfdb_core_create_entity_file(
        manifest_path=manifest_path,
        entity_name="ConnectedSlave",
        fields=CONNECTED_SLAVE_SCHEMA,
        description="Registry of Slave nodes connected to this Master.",
        primary_key="slave_id",
    )


def mfdb_federation_push_config(config_doc: dict, slave_target_path: str) -> bool:
    """
    Master → Slave atomic drop-zone push.
    Writes config_doc as a BEJSON 104a document to slave_target_path using a
    same-directory temp file + OS rename — guards against partial reads on the
    Slave side if it polls mid-write.
    """
    dest = os.path.abspath(slave_target_path)
    dest_dir = os.path.dirname(dest)
    os.makedirs(dest_dir, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=dest_dir, suffix=".tmp")
    os.close(fd)
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(config_doc, f, indent=2)
        os.rename(temp_path, dest)
        return True
    except Exception as e:
        logging.error(f"[MFDB_FEDERATION] push_config failed: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return False


def mfdb_federation_poll_dropzone(
    dropzone_dir: str,
    callback: Callable[[str, dict], None],
    poll_interval: float = 2.0,
    timeout: float = 60.0,
) -> int:
    """
    Slave: poll a local dropzone directory for incoming BEJSON 104a config docs
    pushed by the Master. Each .bejson file found is parsed, passed to callback,
    then removed. Runs until timeout seconds elapse.
    Returns the count of configs processed.
    """
    dropzone_p = Path(dropzone_dir)
    dropzone_p.mkdir(parents=True, exist_ok=True)

    processed = 0
    deadline  = time.time() + timeout

    while time.time() < deadline:
        for fpath in sorted(dropzone_p.glob("*.bejson")):
            try:
                doc = json.loads(fpath.read_text(encoding="utf-8"))
                callback(str(fpath), doc)
                fpath.unlink()
                processed += 1
            except Exception as e:
                logging.warning(f"[MFDB_FEDERATION] poll_dropzone skipped {fpath}: {e}")
        time.sleep(poll_interval)

    return processed


def mfdb_federation_distill_logs(
    slave_manifest_path: str,
    entity_name: str,
    master_poll_dir: str,
    max_rows: int = 100,
) -> bool:
    """
    Slave → Master one-way push (log distillation).
    Reads the entity file, extracts rows above max_rows (oldest overflow),
    pushes a distilled summary doc to master_poll_dir via an atomic rename,
    then truncates the local entity file back to max_rows.
    Returns True on success, False if nothing to distill or on error.
    """
    try:
        entity_path = _resolve_entity_path(slave_manifest_path, entity_name)
        doc  = _load_json(entity_path)
        rows = doc.get("Values", [])

        if len(rows) <= max_rows:
            return True  # Nothing to distill

        overflow = rows[:-max_rows]
        kept     = rows[-max_rows:]

        # Push distilled summary to Master's poll dir
        master_poll_p = Path(master_poll_dir)
        master_poll_p.mkdir(parents=True, exist_ok=True)

        ts      = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest    = str(master_poll_p / f"distilled_{entity_name}_{ts}.bejson")

        summary_doc = {
            "Format":             "BEJSON",
            "Format_Version":     "104a",
            "Format_Creator":     "Elton Boehnen",
            "Distill_Source":     entity_name,
            "Distill_Timestamp":  datetime.now(timezone.utc).isoformat(),
            "Records_Type":       ["DistilledLog"],
            "Fields":             doc.get("Fields", []),
            "Values":             overflow,
        }

        if not mfdb_federation_push_config(summary_doc, dest):
            return False

        # Truncate local entity to max_rows
        doc["Values"] = kept
        bejson_core_atomic_write(entity_path, doc)

        # Update record count in manifest
        manifest_doc = _load_json(slave_manifest_path)
        fields = manifest_doc.get("Fields", [])
        fm     = {f["name"]: i for i, f in enumerate(fields)}
        for row in manifest_doc.get("Values", []):
            if row[fm.get("entity_name", 0)] == entity_name and "record_count" in fm:
                row[fm["record_count"]] = len(kept)
                break
        bejson_core_atomic_write(slave_manifest_path, manifest_doc)

        return True

    except Exception as e:
        logging.error(f"[MFDB_FEDERATION] distill_logs failed: {e}")
        return False


# ── Meta-GUID Debug Entity System ──────────────────────────────────────────────
# Auto-created per MFDB when debug_mode=True. Named meta-{uuid4} to guarantee
# no collision with any user-defined entity. Gated entirely by Debug_Mode header
# on the manifest — zero overhead when off. _mfdb_meta_log() is a direct writer
# that bypasses the normal write functions to prevent infinite recursion.

META_DEBUG_FIELDS: List[Dict[str, str]] = [
    {"name": "timestamp",     "type": "string"},   # ISO 8601 UTC
    {"name": "operation",     "type": "string"},   # ADD|REMOVE|UPDATE|UPDATE_BULK|READ|SCHEMA_SNAPSHOT|ERROR
    {"name": "target_entity", "type": "string"},   # which entity was targeted
    {"name": "field_name",    "type": "string"},   # field targeted (UPDATE only, else null)
    {"name": "field_exists",  "type": "boolean"},  # was the field in Fields[]? (UPDATE only)
    {"name": "row_index",     "type": "integer"},  # record index (REMOVE/UPDATE only, else null)
    {"name": "success",       "type": "boolean"},  # did the operation succeed?
    {"name": "duration_ms",   "type": "integer"},  # wall-clock ms
    {"name": "pid",           "type": "integer"},  # process ID
    {"name": "notes",         "type": "string"},   # extra context, drift warnings, etc.
]


def _mfdb_debug_is_enabled(manifest_path: str) -> bool:
    """Return True if Debug_Mode is 'true' in the manifest headers."""
    try:
        doc = _load_json(manifest_path)
        return str(doc.get("Debug_Mode", "false")).lower() == "true"
    except Exception:
        return False


def _mfdb_debug_reads_enabled(manifest_path: str) -> bool:
    """Return True if Debug_Reads is also 'true' (separate flag for read audit)."""
    try:
        doc = _load_json(manifest_path)
        return str(doc.get("Debug_Reads", "false")).lower() == "true"
    except Exception:
        return False


def _mfdb_debug_get_meta_entity_name(manifest_path: str) -> Optional[str]:
    """Return the meta entity name from the manifest header, or None."""
    try:
        doc = _load_json(manifest_path)
        name = doc.get("Debug_Meta_Entity", "")
        return name if name else None
    except Exception:
        return None


def _mfdb_meta_log(
    manifest_path: str,
    operation:     str,
    target_entity: str,
    field_name:    Optional[str],
    field_exists:  Optional[bool],
    row_index:     Optional[int],
    success:       bool,
    duration_ms:   int,
    notes:         str,
    reads_only:    bool = False,
) -> None:
    """
    Direct writer for the meta debug entity. Bypasses all normal write
    functions to prevent recursion. Silently no-ops when debug is off,
    or when reads_only=True and Debug_Reads is off.
    Acquires its own ResilientPIDLock on the meta entity file.
    """
    try:
        if not _mfdb_debug_is_enabled(manifest_path):
            return
        if reads_only and not _mfdb_debug_reads_enabled(manifest_path):
            return

        meta_name = _mfdb_debug_get_meta_entity_name(manifest_path)
        if not meta_name:
            return

        meta_path = _get_entity_path(manifest_path, meta_name)
        row = [
            datetime.now(timezone.utc).isoformat(),
            operation,
            target_entity,
            field_name,
            field_exists,
            row_index,
            success,
            duration_ms,
            os.getpid(),
            notes or "",
        ]

        with ResilientPIDLock(meta_path, timeout_seconds=5):
            doc = _load_json(meta_path)
            doc.setdefault("Values", []).append(row)
            bejson_core_atomic_write(meta_path, doc)

        # Auto-trim if over cap
        _mfdb_meta_auto_trim(manifest_path, meta_name, meta_path)

    except Exception as e:
        logging.debug(f"[MFDB_DEBUG] meta log write failed (non-fatal): {e}")


def _mfdb_meta_auto_trim(manifest_path: str, meta_name: str, meta_path: str) -> None:
    """Trim meta entity to Debug_Row_Cap rows when exceeded. Oldest rows removed first."""
    try:
        cap_str = _load_json(manifest_path).get("Debug_Row_Cap", "500")
        cap = int(cap_str)
        doc = _load_json(meta_path)
        rows = doc.get("Values", [])
        if len(rows) > cap:
            doc["Values"] = rows[-cap:]
            bejson_core_atomic_write(meta_path, doc)
            _update_manifest_record_count(manifest_path, meta_name, len(doc["Values"]))
    except Exception:
        pass


def _mfdb_debug_schema_snapshot(manifest_path: str, meta_name: str) -> None:
    """
    Log a SCHEMA_SNAPSHOT entry for every registered entity.
    Called once on enable_debug(). Used by detect_schema_drift() as the
    baseline to diff against.
    """
    try:
        entries = _get_manifest_entries(manifest_path)
        for entry in entries:
            ename = entry.get("entity_name", "")
            if not ename or ename == meta_name:
                continue
            try:
                edoc   = _load_json(_get_entity_path(manifest_path, ename))
                fields = [f["name"] for f in edoc.get("Fields", [])]
                _mfdb_meta_log(
                    manifest_path, "SCHEMA_SNAPSHOT", ename,
                    field_name=",".join(fields),
                    field_exists=True,
                    row_index=None, success=True,
                    duration_ms=0,
                    notes=f"field_count={len(fields)}",
                )
            except Exception:
                pass
    except Exception as e:
        logging.debug(f"[MFDB_DEBUG] schema snapshot failed: {e}")


# ── Public Debug API ───────────────────────────────────────────────────────────

def mfdb_core_enable_debug(
    manifest_path:  str,
    row_cap:        int  = 500,
    debug_reads:    bool = False,
) -> str:
    """
    Activate the debug system on an existing MFDB.
    Creates a meta-{uuid4} entity, writes Debug_Mode/Debug_Meta_Entity/
    Debug_Row_Cap/Debug_Reads headers to the manifest, then logs an initial
    SCHEMA_SNAPSHOT of all registered entities as the drift baseline.
    Returns the meta entity name.
    """
    doc = _load_json(manifest_path)

    # Reuse existing meta entity if already present
    existing = doc.get("Debug_Meta_Entity", "")
    if existing:
        meta_name = existing
    else:
        meta_name = f"meta-{uuid.uuid4()}"

    doc["Debug_Mode"]        = "true"
    doc["Debug_Meta_Entity"] = meta_name
    doc["Debug_Row_Cap"]     = str(row_cap)
    doc["Debug_Reads"]       = "true" if debug_reads else "false"
    bejson_core_atomic_write(manifest_path, doc)

    # Create meta entity file if it doesn't exist
    meta_fp_rel  = f"data/{meta_name}.bejson"
    manifest_dir = os.path.dirname(os.path.abspath(manifest_path))
    meta_abs     = os.path.join(manifest_dir, meta_fp_rel)

    if not os.path.exists(meta_abs):
        os.makedirs(os.path.dirname(meta_abs), exist_ok=True)
        rel_to_manifest = os.path.relpath(manifest_path, os.path.dirname(meta_abs))
        meta_doc = {
            "Format":           "BEJSON",
            "Format_Version":   "104",
            "Format_Creator":   "Elton Boehnen",
            "Parent_Hierarchy": rel_to_manifest,
            "Records_Type":     [meta_name],
            "Fields":           META_DEBUG_FIELDS,
            "Values":           [],
        }
        bejson_core_atomic_write(meta_abs, meta_doc)

        # Register in manifest if not already there
        entries = _get_manifest_entries(manifest_path)
        if not any(e.get("entity_name") == meta_name for e in entries):
            doc2 = _load_json(manifest_path)
            doc2.setdefault("Values", []).append(
                [meta_name, meta_fp_rel, "Debug audit log (auto-generated)", 0, "1.0", None]
            )
            bejson_core_atomic_write(manifest_path, doc2)

    # Initial schema snapshot as drift baseline
    _mfdb_debug_schema_snapshot(manifest_path, meta_name)
    return meta_name


def mfdb_core_disable_debug(manifest_path: str) -> None:
    """Set Debug_Mode=false. Meta entity and its data are preserved."""
    doc = _load_json(manifest_path)
    doc["Debug_Mode"] = "false"
    bejson_core_atomic_write(manifest_path, doc)


def mfdb_core_get_debug_log(manifest_path: str) -> List[Dict[str, Any]]:
    """
    Return all meta entity rows as list-of-dicts keyed by META_DEBUG_FIELDS.
    Returns empty list when debug is off or meta entity missing.
    """
    meta_name = _mfdb_debug_get_meta_entity_name(manifest_path)
    if not meta_name:
        return []
    try:
        doc   = _load_json(_get_entity_path(manifest_path, meta_name))
        fm    = {f["name"]: i for i, f in enumerate(doc.get("Fields", META_DEBUG_FIELDS))}
        return [
            {field: row[idx] for field, idx in fm.items()}
            for row in doc.get("Values", [])
        ]
    except Exception:
        return []


def mfdb_core_get_failed_ops(manifest_path: str) -> List[Dict[str, Any]]:
    """
    Return only failed (success=False) operations from the debug log,
    sorted by timestamp ascending. Useful for post-mortem review.
    """
    all_rows = mfdb_core_get_debug_log(manifest_path)
    return sorted(
        [r for r in all_rows if r.get("success") is False],
        key=lambda r: r.get("timestamp", ""),
    )


def mfdb_core_clear_debug_log(manifest_path: str) -> int:
    """
    Wipe all rows from the meta entity. Schema is preserved.
    Returns the number of rows deleted.
    """
    meta_name = _mfdb_debug_get_meta_entity_name(manifest_path)
    if not meta_name:
        return 0
    try:
        meta_path = _get_entity_path(manifest_path, meta_name)
        with ResilientPIDLock(meta_path, timeout_seconds=10):
            doc  = _load_json(meta_path)
            deleted = len(doc.get("Values", []))
            doc["Values"] = []
            bejson_core_atomic_write(meta_path, doc)
        _update_manifest_record_count(manifest_path, meta_name, 0)
        return deleted
    except Exception:
        return 0


def mfdb_core_debug_summary(manifest_path: str) -> Dict[str, Any]:
    """
    Aggregate view of the debug log:
      - total_ops           int
      - unique_entities     list[str]
      - failed_ops          int
      - schema_drift_hits   int   (field_exists=False count)
      - top_3_slowest       list[dict]   (op, entity, duration_ms)
      - reads_logged        int
      - writes_logged       int
      - ops_by_type         dict[str, int]
    Returns empty dict when debug is off.
    """
    if not _mfdb_debug_is_enabled(manifest_path):
        return {}

    rows = mfdb_core_get_debug_log(manifest_path)
    if not rows:
        return {"total_ops": 0}

    write_ops = {"ADD", "REMOVE", "UPDATE", "UPDATE_BULK"}

    ops_by_type: Dict[str, int] = {}
    for r in rows:
        ops_by_type[r["operation"]] = ops_by_type.get(r["operation"], 0) + 1

    return {
        "total_ops":         len(rows),
        "unique_entities":   sorted({r["target_entity"] for r in rows}),
        "failed_ops":        sum(1 for r in rows if r.get("success") is False),
        "schema_drift_hits": sum(1 for r in rows if r.get("field_exists") is False),
        "top_3_slowest":     sorted(
            [{"op": r["operation"], "entity": r["target_entity"], "duration_ms": r["duration_ms"]}
             for r in rows],
            key=lambda x: x["duration_ms"], reverse=True
        )[:3],
        "reads_logged":      sum(1 for r in rows if r["operation"] == "READ"),
        "writes_logged":     sum(1 for r in rows if r["operation"] in write_ops),
        "ops_by_type":       ops_by_type,
    }


def mfdb_core_detect_schema_drift(manifest_path: str) -> Dict[str, Dict[str, Any]]:
    """
    Compare each entity's live Fields[] against the SCHEMA_SNAPSHOT baseline
    stored in the debug log when enable_debug() was called.

    Returns a dict keyed by entity_name:
      {
        "entity_name": {
          "added_fields":   [str],   # in live schema, not in snapshot
          "removed_fields": [str],   # in snapshot, not in live schema
          "drifted":        bool,
        }
      }
    Returns empty dict when debug is off or no snapshot exists.
    """
    if not _mfdb_debug_is_enabled(manifest_path):
        return {}

    rows = mfdb_core_get_debug_log(manifest_path)
    # Find the most recent SCHEMA_SNAPSHOT entry per entity
    snapshots: Dict[str, set] = {}
    for r in rows:
        if r["operation"] == "SCHEMA_SNAPSHOT" and r.get("field_name"):
            snap_fields = set(r["field_name"].split(",")) if r["field_name"] else set()
            snapshots[r["target_entity"]] = snap_fields

    if not snapshots:
        return {}

    report: Dict[str, Dict[str, Any]] = {}
    for ename, snap_fields in snapshots.items():
        try:
            edoc        = _load_json(_get_entity_path(manifest_path, ename))
            live_fields = {f["name"] for f in edoc.get("Fields", [])}
            added       = sorted(live_fields - snap_fields)
            removed     = sorted(snap_fields - live_fields)
            report[ename] = {
                "added_fields":   added,
                "removed_fields": removed,
                "drifted":        bool(added or removed),
            }
        except Exception:
            pass

    return report
