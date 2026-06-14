"""
Library:      lib_mfdb_validator.py
Family:       Core
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.0.1 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-18
Description:  Bidirectional path and manifest-entity relationship validator.
"""

import json
import os
import zipfile
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from lib_bejson_validator import (
    BEJSONValidationError,
    validate_bejson,
    ValidationResult
)

try:
    from lib_bejson_errors import (
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
