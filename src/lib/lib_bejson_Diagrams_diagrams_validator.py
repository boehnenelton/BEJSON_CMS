"""
Library:         lib_bejson_Diagrams_diagrams_validator.py
Family:          Diagrams
Module Purpose:  Validation and remediation algorithms for BEJSON Diagrammer MFDB directories, in-memory models, and 1.32 packages.
Architecture:    MFDB provides multi-file database federation coordinating a 104a central manifest (104a.mfdb.bejson) with dense 104 entity tables, supporting atomic transaction locks and cross-disk relational foreign keys.
Version:         1.2.0
Release_Version: 300
Date:            2026-10-29
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   5c8d3e2a-1f7b-40a9-b6c8-2e9f1a7d4b60
Changelog:
  1.2.0 (2026-10-29) - Merged v3 Diagrammer validator enhancements: duplicate shape_id detection,
          parent hierarchy cycle detection (E_DIAGRAMS_CIRCULAR_HIERARCHY), Shape_<id> private entity
          board_membership_fk verification, diagrams_validator_validate_diagram_database(),
          validate_diagram_model() / validateDiagramModel(), and remediate_diagram_model() /
          remediateDiagramModel(). DiagramValidationResult supports both attribute and dict subscript access.
  1.0.0 (2026-08-12) - Initial release.
"""

import json
import shutil
import tempfile
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Dict, List, Optional

from lib_bejson_Core_bejson_core import bejson_core_get_field_map
from lib_bejson_Core_bejson_validator import validate_bejson
from lib_bejson_Core_mfdb_validator import (
    mfdb_validator_is_mfdb132_package,
    mfdb_validator_validate_mfdb132_package,
    validate_mfdb_database,
)
from lib_bejson_Core_bejson_chunking import bejson_core_chunking_unchunk_chunked_104

from lib_bejson_Diagrams_diagrams_core import (
    DIAGRAM_SCHEMA_TAG,
    KNOWN_SIZE_CLASSES,
    BOARD_BASE_FIELDS,
    CONNECTOR_BASE_FIELDS,
    TERRITORY_BASE_FIELDS,
)
from lib_bejson_Diagrams_bejson_errors import (
    E_DIAGRAMS_NOT_MFDB132_PACKAGE,
    E_DIAGRAMS_MFDB132_INVALID,
    E_DIAGRAMS_MFDB_DATABASE_INVALID,
    E_DIAGRAMS_MISSING_ENTITY,
    E_DIAGRAMS_MISSING_FIELD,
    E_DIAGRAMS_FK_UNRESOLVED,
    E_DIAGRAMS_NOT_A_DIAGRAM_PACKAGE,
    E_DIAGRAMS_VALIDATION_FAILED,
    E_DIAGRAMS_CIRCULAR_HIERARCHY,
    E_DIAGRAMS_SHAPE_NOT_FOUND,
    E_DIAGRAMS_DUPLICATE_ID,
)


class DiagramValidationError(Exception):
    def __init__(self, message: str, code: int, context: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.context = context or {}


@dataclass
class DiagramValidationResult:
    valid: bool = True
    errors: List[str] = dc_field(default_factory=list)
    warnings: List[str] = dc_field(default_factory=list)

    def add_error(self, message: str, location: str = ""):
        self.valid = False
        self.errors.append(f"ERROR | Location: {location} | Message: {message}" if location else f"ERROR | Message: {message}")

    def add_warning(self, message: str, location: str = ""):
        self.warnings.append(f"WARNING | Location: {location} | Message: {message}" if location else f"WARNING | Message: {message}")

    def to_dict(self) -> Dict[str, Any]:
        return {"valid": self.valid, "errors": list(self.errors), "warnings": list(self.warnings)}

    def __getitem__(self, key: str) -> Any:
        if key == "valid":
            return self.valid
        if key == "errors":
            return self.errors
        if key == "warnings":
            return self.warnings
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


def _docs_by_entity(manifest_path: str) -> Dict[str, Dict[str, Any]]:
    """Loads manifest + every entity file it lists, keyed by entity_name."""
    manifest_doc = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    fm = bejson_core_get_field_map(manifest_doc)
    manifest_dir = Path(manifest_path).parent
    out: Dict[str, Dict[str, Any]] = {}
    for row in manifest_doc.get("Values", []):
        entity_name = row[fm["entity_name"]]
        file_path = row[fm["file_path"]]
        entity_path = (manifest_dir / file_path).resolve()
        if entity_path.is_file():
            out[entity_name] = json.loads(entity_path.read_text(encoding="utf-8"))
    return out


def _rows_as_dicts(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    fm = bejson_core_get_field_map(doc)
    names_by_index = {i: n for n, i in fm.items()}
    return [
        {names_by_index[i]: v for i, v in enumerate(row) if i in names_by_index}
        for row in doc.get("Values", [])
    ]


def _check_required_fields(doc: Dict[str, Any], required: List[Dict[str, str]],
                            entity_label: str, result: DiagramValidationResult) -> None:
    have = set(bejson_core_get_field_map(doc).keys())
    for f in required:
        if f["name"] not in have:
            result.add_error(f"Entity '{entity_label}' missing required field '{f['name']}'", entity_label)


def _validate_diagram_entities_map(entities: Dict[str, Dict[str, Any]], result: DiagramValidationResult,
                                    check_shape_entities: bool = False) -> None:
    """Shared Stage 2 diagram-specific relational & structural validation."""
    for entity_name, required_fields in (
        ("Board", BOARD_BASE_FIELDS),
        ("Connector", CONNECTOR_BASE_FIELDS),
        ("Territory", TERRITORY_BASE_FIELDS),
    ):
        if entity_name not in entities or entities[entity_name] is None:
            result.add_error(f"Diagram is missing required entity '{entity_name}'", "Structure")
            continue
        _check_required_fields(entities[entity_name], required_fields, entity_name, result)

    if not result.valid:
        return  # Entity/field structure is broken — FK/value checks would cascade-fail.

    board_rows = _rows_as_dicts(entities["Board"])
    shape_ids: set = set()
    parent_map: Dict[str, str] = {}

    for r in board_rows:
        sid = str(r.get("shape_id") or "")
        if sid:
            if sid in shape_ids:
                result.add_error(f"Duplicate shape_id '{sid}' in Board registry.", f"Board:{sid}")
            shape_ids.add(sid)

        sc = r.get("shape_size_class")
        if sc and sc not in KNOWN_SIZE_CLASSES:
            result.add_warning(f"shape_size_class '{sc}' not in known set {sorted(KNOWN_SIZE_CLASSES)}", f"Board:{sid}")

        pfk = r.get("shape_parent_fk")
        if pfk and sid:
            parent_map[sid] = str(pfk)

        ename = r.get("shape_entity_name")
        if ename and (check_shape_entities or ename in entities):
            shape_doc = entities.get(str(ename))
            if not shape_doc:
                result.add_error(f"Shape entity '{ename}' for shape_id '{sid}' is missing.", f"Board:{sid}")
            else:
                s_fm = bejson_core_get_field_map(shape_doc)
                bmfk_idx = s_fm.get("board_membership_fk")
                if bmfk_idx is None:
                    result.add_error(f"Shape entity '{ename}' missing required board_membership_fk.", str(ename))
                else:
                    s_vals = shape_doc.get("Values") or []
                    if not s_vals or str(s_vals[0][bmfk_idx]) != sid:
                        result.add_error(
                            f"Shape entity '{ename}' board_membership_fk does not match Board shape_id '{sid}'.",
                            str(ename),
                        )

    # Parent hierarchy existence check
    for sid, pfk in parent_map.items():
        if pfk not in shape_ids:
            result.add_error(f"shape_parent_fk '{pfk}' does not resolve to any Board.shape_id", f"Board:{sid}")

    # Parent hierarchy cycle detection
    for start_id in parent_map.keys():
        curr = start_id
        visited = {curr}
        while curr in parent_map:
            curr = parent_map[curr]
            if curr in visited:
                result.add_error(f"Circular parent hierarchy detected involving shape '{curr}'.", f"Board:{start_id}")
                break
            visited.add(curr)

    # Connector FK checks
    for r in _rows_as_dicts(entities["Connector"]):
        for fk_field in ("conn_from_fk", "conn_to_fk"):
            fk = r.get(fk_field)
            if fk and str(fk) not in shape_ids:
                result.add_error(f"{fk_field} '{fk}' does not resolve to any Board.shape_id", f"Connector:{r.get('conn_id')}")


def _validate_diagram_structure(manifest_path: str, result: DiagramValidationResult) -> None:
    """Stage 2: diagram-specific structural rules against an unpacked MFDB root."""
    entities = _docs_by_entity(manifest_path)
    _validate_diagram_entities_map(entities, result, check_shape_entities=False)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def diagrams_validator_validate_database_dir(manifest_path: str) -> DiagramValidationResult:
    """
    Validates a live, unpacked diagram MFDB root (not a package). Stage 1 =
    validate_mfdb_database(); Stage 2 = diagram structural rules. Use this
    to sanity-check a diagram directory before ever packaging it.
    """
    result = DiagramValidationResult()
    core_res = validate_mfdb_database(manifest_path)
    if not core_res.valid:
        for e in core_res.errors:
            result.add_error(e, "MFDB Database (Stage 1)")
        return result
    for w in core_res.warnings:
        result.add_warning(w, "MFDB Database (Stage 1)")

    _validate_diagram_structure(manifest_path, result)
    return result


def diagrams_validator_validate_diagram_database(manifest_path: str) -> DiagramValidationResult:
    """
    v3 Diagrammer entry point: validates a complete MFDB Diagram database.
    Returns a DiagramValidationResult (which supports both .valid/.errors/.warnings
    and dict subscripting res['valid'], res['errors'], res['warnings']).
    """
    return diagrams_validator_validate_database_dir(manifest_path)


def diagrams_validator_validate_package(doc: Dict[str, Any]) -> DiagramValidationResult:
    """
    Validates a single-file MFDB-132 diagram package doc. Must clear
    Stage 1 (MFDB-132 structural validation, then full MFDB database
    validation against the unchunked contents) before Stage 2 (diagram
    structural rules) is even attempted.
    """
    result = DiagramValidationResult()

    if not mfdb_validator_is_mfdb132_package(doc):
        result.add_error("Document is not a recognized MFDB-132 package.", "Stage 1: MFDB-132")
        return result

    pkg_check = mfdb_validator_validate_mfdb132_package(doc)
    if not pkg_check["valid"]:
        for e in pkg_check["errors"]:
            result.add_error(e, "Stage 1: MFDB-132")
        return result

    if doc.get("Diagram_Schema") != DIAGRAM_SCHEMA_TAG:
        result.add_error(
            f"Package is valid MFDB-132 but is not tagged as a diagram (Diagram_Schema != '{DIAGRAM_SCHEMA_TAG}').",
            "Stage 1: Diagram Tag",
        )
        return result

    scratch_dir = tempfile.mkdtemp(prefix="diagrams_validate_")
    try:
        count = bejson_core_chunking_unchunk_chunked_104(doc, scratch_dir)
        manifest_path = str(Path(scratch_dir) / "104a.mfdb.bejson")
        if count == 0 or not Path(manifest_path).is_file():
            result.add_error("Package unchunked but manifest is missing.", "Stage 1: MFDB Database")
            return result

        db_res = validate_mfdb_database(manifest_path)
        if not db_res.valid:
            for e in db_res.errors:
                result.add_error(e, "Stage 1: MFDB Database")
            return result
        for w in db_res.warnings:
            result.add_warning(w, "MFDB Database (Stage 1)")

        _validate_diagram_structure(manifest_path, result)
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)

    return result


def validate_diagram_model(model: Dict[str, Any]) -> DiagramValidationResult:
    """
    Validates an in-memory DiagramModel dict ({manifest, boardDoc, connectorDoc, territoryDoc, shapeDocs})
    using Core's validate_bejson() and Stage 2 Diagrammer relational rules.
    """
    result = DiagramValidationResult()
    if not isinstance(model, dict):
        result.add_error("DiagramModel must be a dictionary.", "Model")
        return result

    manifest = model.get("manifest")
    board_doc = model.get("boardDoc")
    connector_doc = model.get("connectorDoc")
    territory_doc = model.get("territoryDoc")
    shape_docs = model.get("shapeDocs") or {}

    if not manifest or not validate_bejson(manifest):
        result.add_error("Manifest is missing or fails Core BEJSON validation.", "Manifest")
    if not board_doc or not validate_bejson(board_doc):
        result.add_error("Board entity is missing or fails Core BEJSON validation.", "Board")
    if connector_doc is not None and not validate_bejson(connector_doc):
        result.add_error("Connector entity fails Core BEJSON validation.", "Connector")
    if territory_doc is not None and not validate_bejson(territory_doc):
        result.add_error("Territory entity fails Core BEJSON validation.", "Territory")

    if not result.valid:
        return result

    entities: Dict[str, Dict[str, Any]] = {
        "Board": board_doc,
        "Connector": connector_doc or {
            "Format": "BEJSON", "Format_Version": "104", "Format_Creator": "Elton Boehnen",
            "Records_Type": ["Connector"], "Fields": CONNECTOR_BASE_FIELDS, "Values": [],
        },
        "Territory": territory_doc or {
            "Format": "BEJSON", "Format_Version": "104", "Format_Creator": "Elton Boehnen",
            "Records_Type": ["Territory"], "Fields": TERRITORY_BASE_FIELDS, "Values": [],
        },
    }
    for ename, sdoc in shape_docs.items():
        entities[str(ename)] = sdoc

    _validate_diagram_entities_map(entities, result, check_shape_entities=True)
    return result


def remediate_diagram_model(model: Dict[str, Any]) -> Dict[str, Any]:
    """
    Auto-remediates an in-memory DiagramModel by deduplicating shape_id rows,
    clearing unresolved shape_parent_fk links, and filtering dangling connectors
    via Core's O(1) Field-Map Cache.
    """
    board_doc = model.get("boardDoc") if isinstance(model, dict) else None
    if not board_doc or not board_doc.get("Values"):
        return model

    b_fm = bejson_core_get_field_map(board_doc)
    shape_id_idx = b_fm.get("shape_id")
    parent_fk_idx = b_fm.get("shape_parent_fk")
    if shape_id_idx is None:
        return model

    valid_shape_ids: set = set()
    seen_shape_ids: set = set()
    filtered_board_rows: list = []

    for row in board_doc.get("Values", []):
        sid = str(row[shape_id_idx] or "")
        if not sid or sid in seen_shape_ids:
            continue
        seen_shape_ids.add(sid)
        valid_shape_ids.add(sid)
        filtered_board_rows.append(row)

    board_doc["Values"] = filtered_board_rows

    if parent_fk_idx is not None:
        for row in board_doc["Values"]:
            pid = str(row[parent_fk_idx]) if row[parent_fk_idx] else None
            if pid and pid not in valid_shape_ids:
                row[parent_fk_idx] = None

    conn_doc = model.get("connectorDoc")
    if conn_doc and conn_doc.get("Values"):
        c_fm = bejson_core_get_field_map(conn_doc)
        from_idx = c_fm.get("conn_from_fk")
        to_idx = c_fm.get("conn_to_fk")
        if from_idx is not None and to_idx is not None:
            conn_doc["Values"] = [
                row for row in conn_doc["Values"]
                if str(row[from_idx] or "") in valid_shape_ids and str(row[to_idx] or "") in valid_shape_ids
            ]

    return model


# CamelCase aliases for v3 parity
validateDiagramModel = validate_diagram_model
remediateDiagramModel = remediate_diagram_model