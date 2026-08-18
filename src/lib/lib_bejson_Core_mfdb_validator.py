"""
Library:        lib_bejson_Core_mfdb_validator.py
Family:         Core
Description:    Bidirectional path and manifest-entity relationship validator.
                Also owns MFDB-132-package validation (is/validate_mfdb132_package,
                detect_mfdb_in_chunk) — relocated here from
                lib_bejson_Core_bejson_chunking.py, which should only own
                packaging/IO, not validation logic. See CHANGELOG note dated
                2026-07-13.
Version:        2.2.0
Date:           2026-07-13
Author:         Elton Boehnen
Contact:        eltonboehnen@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  783f276c-7d6f-41d9-b10e-790e97442cac
"""

import json
import os
import zipfile
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from lib_bejson_Core_bejson_validator import (
    BEJSONValidationError,
    validate_bejson,
    ValidationResult
)

try:
    from lib_bejson_Core_bejson_path_guard import _bejson_mfdb_escapes_root
except ImportError as e:
    import logging
    logging.critical(f"[MFDB_VALIDATOR] FATAL: Path guard unreachable: {e}")
    raise SystemExit(1)

try:
    from lib_bejson_Core_bejson_errors import (
        E_MFDB_NOT_MANIFEST,
        E_MFDB_NOT_ENTITY_FILE,
        E_MFDB_MANIFEST_RECORDS_TYPE,
        E_MFDB_ENTITY_NOT_FOUND,
        E_MFDB_ENTITY_NAME_MISMATCH,
        E_MFDB_DUPLICATE_ENTRY,
        E_MFDB_NO_PARENT_HIERARCHY,
        E_MFDB_MANIFEST_NOT_FOUND,
        E_MFDB_BIDIRECTIONAL_FAIL,
        E_MFDB_FK_UNRESOLVED,
        E_MFDB_MISSING_REQUIRED_FIELD,
        E_MFDB_NULL_REQUIRED,
        E_MFDB_INVALID_ARCHIVE
    )
except ImportError as e:
    import logging
    logging.critical(f"[MFDB_VALIDATOR] FATAL: Error registry unreachable: {e}")
    raise SystemExit(1)

class MFDBValidationError(Exception):
    def __init__(self, message: str, code: int, context: dict = None):
        super().__init__(message)
        self.code = code
        self.context = context or {}

@dataclass
class MFDBValidationResult:
    valid: bool = True
    errors: List[str] = dc_field(default_factory=list)
    warnings: List[str] = dc_field(default_factory=list)
    findings: Dict[str, Any] = dc_field(default_factory=dict)
    
    def add_error(self, message: str, location: str = ""):
        self.valid = False
        entry = f"ERROR | Location: {location} | Message: {message}" if location else f"ERROR | Message: {message}"
        self.errors.append(entry)

    def add_warning(self, message: str, location: str = ""):
        entry = f"WARNING | Location: {location} | Message: {message}" if location else f"WARNING | Message: {message}"
        self.warnings.append(entry)

# Internal helpers
def _load_json(path: str) -> dict:
    p = Path(path)
    if p.is_file() and not path.lower().endswith(".zip"):
        return json.loads(p.read_text(encoding="utf-8"))
    if path.lower().endswith(".zip") and p.is_file():
        with zipfile.ZipFile(path, "r") as z:
            if "104a.mfdb.bejson" in z.namelist():
                return json.loads(z.read("104a.mfdb.bejson").decode("utf-8"))
            raise FileNotFoundError(f"104a.mfdb.bejson not found in archive: {path}")
    return json.loads(p.read_text(encoding="utf-8"))

def _rows_as_dicts(doc: dict) -> list[dict]:
    names = [f["name"] for f in doc["Fields"]]
    return [dict(zip(names, row)) for row in doc["Values"]]

def _resolve_entity_path(manifest_path: str, file_path_rel: str) -> str:
    if manifest_path.lower().endswith(".zip"):
        return os.path.join(manifest_path, file_path_rel)
    manifest_dir = os.path.dirname(os.path.abspath(manifest_path))
    return os.path.normpath(os.path.join(manifest_dir, file_path_rel))

# Validation functions
def validate_mfdb_archive(archive_path: str) -> MFDBValidationResult:
    res = MFDBValidationResult()
    p = Path(archive_path)
    if not p.exists():
        res.add_error(f"Archive not found: {archive_path}", "File System")
        return res
    try:
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            if "104a.mfdb.bejson" not in zip_ref.namelist():
                res.add_error("Archive missing 104a.mfdb.bejson at root", "Zip Structure")
    except Exception as e:
        res.add_error(f"Invalid zip: {e}", "Zip Parser")
    return res

def validate_mfdb_manifest(manifest_path: str) -> MFDBValidationResult:
    res = MFDBValidationResult()
    p = Path(manifest_path)
    if not p.exists():
        res.add_error(f"Manifest not found: {manifest_path}", "File System")
        return res
    
    bej_res = validate_bejson(manifest_path, is_file=True)
    if not bej_res.valid:
        for err in bej_res.errors: res.add_error(err, "BEJSON Validation")
        return res

    doc = _load_json(manifest_path)
    if doc.get("Format_Version") != "104a" or doc.get("Records_Type") != ["mfdb"]:
        res.add_error("Invalid manifest format or records type", "Manifest")
        return res

    field_names = [f["name"] for f in doc.get("Fields", [])]
    for req in ("entity_name", "file_path"):
        if req not in field_names: res.add_error(f"Missing required field: {req}", "Fields")

    seen_names, seen_paths = set(), set()
    for i, entry in enumerate(_rows_as_dicts(doc)):
        en, fp = entry.get("entity_name"), entry.get("file_path")
        if not en or not fp: res.add_error(f"Record {i}: null entity_name or file_path", "Values")
        if en in seen_names: res.add_error(f"Duplicate entity: {en}", "Values")
        if fp in seen_paths: res.add_error(f"Duplicate path: {fp}", "Values")
        seen_names.add(en); seen_paths.add(fp)

        # NEW-08: reject file_path values that attempt to escape the MFDB root
        if fp and _bejson_mfdb_escapes_root(fp):
            res.add_error(
                f"Path traversal detected in file_path for entity '{en}': '{fp}'",
                "Values"
            )
            continue

        resolved = _resolve_entity_path(manifest_path, fp)
        if not os.path.exists(resolved): res.add_error(f"Entity file not found: {fp}", "File System")
    
    return res

def validate_mfdb_entity_file(entity_path: str, check_bidirectional: bool = True) -> MFDBValidationResult:
    res = MFDBValidationResult()
    p = Path(entity_path)
    if not p.exists():
        res.add_error(f"Entity file not found: {entity_path}", "File System")
        return res

    bej_res = validate_bejson(entity_path, is_file=True)
    if not bej_res.valid:
        for err in bej_res.errors: res.add_error(err, "BEJSON Validation")
        return res

    doc = _load_json(entity_path)
    if doc.get("Format_Version") != "104":
        res.add_error("Entity file must be 104", "Format_Version")
        return res

    ph = doc.get("Parent_Hierarchy")
    if not ph:
        res.add_error("Missing Parent_Hierarchy", "Structure")
        return res

    manifest_path = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(entity_path)), ph))
    if not os.path.exists(manifest_path):
        res.add_error(f"Manifest not found at {manifest_path}", "Parent_Hierarchy")
        return res

    return res

def validate_mfdb_database(manifest_path: str, strict_fk: bool = False) -> MFDBValidationResult:
    res = validate_mfdb_manifest(manifest_path)
    if not res.valid: return res
    
    doc = _load_json(manifest_path)
    for entry in _rows_as_dicts(doc):
        resolved = _resolve_entity_path(manifest_path, entry["file_path"])
        ent_res = validate_mfdb_entity_file(resolved)
        if not ent_res.valid:
            for err in ent_res.errors: res.add_error(err, f"Entity:{entry['entity_name']}")
    return res

# Compatibility wrappers
def mfdb_validator_validate_manifest(p):
    res = validate_mfdb_manifest(p)
    if not res.valid: raise MFDBValidationError(res.errors[0], E_MFDB_NOT_MANIFEST)
    return True

def mfdb_validator_validate_database(p, strict_fk=False):
    res = validate_mfdb_database(p, strict_fk=strict_fk)
    if not res.valid: raise MFDBValidationError(res.errors[0], E_MFDB_NOT_MANIFEST)
    return True

# ── MFDB 1.32 chunked-package validation ───────────────────────────────────────
# Relocated from lib_bejson_Core_bejson_chunking.py (2026-07-13). The chunking
# library still owns create_mfdb132_package/unchunk_mfdb132_package (packaging
# and IO), but calls back into these functions for the actual validation —
# validation logic belongs in the validator family, not the chunker.

MFDB_MANIFEST_FILENAME = "104a.mfdb.bejson"

def mfdb_validator_is_mfdb132_package(doc: Dict[str, Any]) -> bool:
    """
    Discovery check: True if a document represents a packaged MFDB 1.32
    database (tagged via bejson_core_chunking_create_mfdb132_package) rather
    than a plain project chunk.
    """
    return (
        doc.get("Format_Version") == "104a"
        and doc.get("Schema_Name") == "MFDB-132"
        and doc.get("Package_Format") == "MFDB-Chunked-104a"
        and bool(doc.get("MFDB_Version"))
        and bool(doc.get("DB_Name"))
    )

def mfdb_validator_validate_mfdb132_package(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Level 1 validation for a chunked MFDB 1.32 package:
    - Must pass mfdb_validator_is_mfdb132_package()
    - Records_Type must be exactly ["MFDB-132"]
    - The manifest (104a.mfdb.bejson) must be present among the chunked files
      at Relative_Path == "104a.mfdb.bejson" (root of the package)

    This mirrors — but does not replace — validate_mfdb_database() above,
    which should still be run against the unchunked output.

    Returns {"valid": bool, "errors": [...], "warnings": [...]}.
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not mfdb_validator_is_mfdb132_package(doc):
        errors.append("Document is not a recognized MFDB-132 package "
                       "(missing/incorrect Schema_Name/Package_Format/MFDB_Version/DB_Name).")
        return {"valid": False, "errors": errors, "warnings": warnings}

    if doc.get("Records_Type") != ["MFDB-132"]:
        errors.append("Records_Type must be exactly ['MFDB-132'] for an MFDB-132 package.")

    fields = doc.get("Fields", [])
    fm = {f["name"]: i for i, f in enumerate(fields)}
    manifest_found = False
    for row in doc.get("Values", []):
        if row[fm.get("Relative_Path", -1)] == MFDB_MANIFEST_FILENAME:
            manifest_found = True
            break

    if not manifest_found:
        errors.append(f"Chunked package does not contain the MFDB manifest "
                       f"({MFDB_MANIFEST_FILENAME}) — not a complete MFDB package.")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

def _mfdb_validator_find_row_by_relpath(doc: Dict[str, Any], rel_path: str) -> Optional[List[Any]]:
    fields = doc.get("Fields", [])
    fm = {f["name"]: i for i, f in enumerate(fields)}
    rel_idx = fm.get("Relative_Path")
    if rel_idx is None:
        return None
    for row in doc.get("Values", []):
        if row[rel_idx] == rel_path:
            return row
    return None

def mfdb_validator_detect_mfdb_in_chunk(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Scans any Chunked-104a document for an embedded, valid MFDB database
    (manifest at Relative_Path == '104a.mfdb.bejson' + its entity files).
    Does NOT require MFDB_Version/DB_Name/Package_Format headers on the
    chunk itself — only that a genuine manifest+entities are present inside
    the chunked file set. This is the Level-1/Level-2 MFDB validation logic,
    re-targeted to operate on chunk rows instead of files on disk.

    Returns:
    {
      "mfdb_detected": bool,   # a manifest row was found and parses as 104a
      "valid": bool,           # manifest + every listed entity check out
      "db_name": str | None,
      "mfdb_version": str | None,
      "entities": [
        {"entity_name": str, "file_path": str, "found_in_chunk": bool,
         "valid": bool, "errors": [str]}
      ],
      "errors": [str],         # manifest-level (Level 1) errors
      "warnings": [str],
    }
    """
    result: Dict[str, Any] = {
        "mfdb_detected": False,
        "valid": False,
        "db_name": None,
        "mfdb_version": None,
        "entities": [],
        "errors": [],
        "warnings": [],
    }

    fields = doc.get("Fields", [])
    fm = {f["name"]: i for i, f in enumerate(fields)}
    required = ("Relative_Path", "File_Content", "Is_Binary")
    if any(k not in fm for k in required):
        result["errors"].append("Chunk document is missing required Chunked-104 fields.")
        return result

    manifest_row = _mfdb_validator_find_row_by_relpath(doc, MFDB_MANIFEST_FILENAME)
    if manifest_row is None:
        result["errors"].append(f"No manifest ({MFDB_MANIFEST_FILENAME}) found in chunk — no MFDB present.")
        return result

    if manifest_row[fm["Is_Binary"]]:
        result["errors"].append("Manifest row is flagged Is_Binary — its content was never stored, cannot validate.")
        return result

    try:
        manifest_doc = json.loads(manifest_row[fm["File_Content"]])
    except Exception as e:
        result["errors"].append(f"Manifest content is not valid JSON: {e}")
        return result

    # ── Level 1: Manifest checks ──
    result["mfdb_detected"] = True
    result["db_name"] = manifest_doc.get("DB_Name")
    result["mfdb_version"] = manifest_doc.get("MFDB_Version")

    if manifest_doc.get("Format_Version") != "104a":
        result["errors"].append("Manifest Format_Version must be '104a'.")
    if manifest_doc.get("Records_Type") != ["mfdb"]:
        result["errors"].append("Manifest Records_Type must be exactly ['mfdb'].")

    manifest_fm = {f["name"]: i for i, f in enumerate(manifest_doc.get("Fields", []))}
    if "entity_name" not in manifest_fm or "file_path" not in manifest_fm:
        result["errors"].append("Manifest Fields must include 'entity_name' and 'file_path'.")
        return result

    seen_entity_names = set()
    seen_file_paths = set()

    # ── Level 2: Per-entity checks ──
    for entity_row in manifest_doc.get("Values", []):
        entity_name = entity_row[manifest_fm["entity_name"]]
        file_path = entity_row[manifest_fm["file_path"]]
        entity_result: Dict[str, Any] = {
            "entity_name": entity_name,
            "file_path": file_path,
            "found_in_chunk": False,
            "valid": False,
            "errors": [],
        }

        if not entity_name or not file_path:
            entity_result["errors"].append("entity_name/file_path must not be null.")
        if entity_name in seen_entity_names:
            entity_result["errors"].append(f"Duplicate entity_name '{entity_name}' in manifest.")
        if file_path in seen_file_paths:
            entity_result["errors"].append(f"Duplicate file_path '{file_path}' in manifest.")
        seen_entity_names.add(entity_name)
        seen_file_paths.add(file_path)

        entity_chunk_row = _mfdb_validator_find_row_by_relpath(doc, file_path)
        if entity_chunk_row is None:
            entity_result["errors"].append(f"Entity file '{file_path}' listed in manifest was not found in chunk.")
            result["entities"].append(entity_result)
            continue

        entity_result["found_in_chunk"] = True
        if entity_chunk_row[fm["Is_Binary"]]:
            entity_result["errors"].append("Entity row is flagged Is_Binary — content was never stored, cannot validate.")
            result["entities"].append(entity_result)
            continue

        try:
            entity_doc = json.loads(entity_chunk_row[fm["File_Content"]])
        except Exception as e:
            entity_result["errors"].append(f"Entity file content is not valid JSON: {e}")
            result["entities"].append(entity_result)
            continue

        if entity_doc.get("Format_Version") != "104":
            entity_result["errors"].append("Entity Format_Version must be '104'.")
        if entity_doc.get("Records_Type") != [entity_name]:
            entity_result["errors"].append(f"Entity Records_Type must be exactly ['{entity_name}'].")
        if "Parent_Hierarchy" not in entity_doc:
            entity_result["errors"].append("Entity is missing mandatory 'Parent_Hierarchy' key.")

        entity_result["valid"] = len(entity_result["errors"]) == 0
        result["entities"].append(entity_result)

    result["valid"] = (
        len(result["errors"]) == 0
        and all(e["valid"] for e in result["entities"])
    )
    return result
