"""
Library:         lib_bejson_Diagrams_diagrams_core.py
Family:          Diagrams
Module Purpose:  Core packaging, model serialization, and schema constants for the Diagrams family.
Architecture:    MFDB provides multi-file database federation coordinating a 104a central manifest (104a.mfdb.bejson) with dense 104 entity tables, supporting atomic transaction locks and cross-disk relational foreign keys.
Version:         1.2.0
Release_Version: 300
Date:            2026-10-29
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   4d9e2a1c-8b7f-4c56-9a0d-3f8e1b2a7c50
Changelog:
  1.2.0 (2026-10-29) - Merged v3 Diagrammer updates: added KNOWN_FLOW_VALUES, in-memory DiagramModel
          MFDB-132 packaging/extraction (diagrams_core_create_mfdb132_package_from_model /
          createMfdb132PackageFromModel and diagrams_core_extract_diagram_model_from_mfdb132 /
          extractDiagramModelFromMfdb132) aligned to Core O(1) field-map cache, SHA-256 File_Hash,
          Parent_Hierarchy normalization, and Diagram_Schema tagging.
  1.0.0 (2026-08-12) - Initial release.
"""

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lib_bejson_Core_bejson_core import (
    bejson_core_atomic_write,
    bejson_core_get_field_map,
    bejson_core_get_field_index,
)
from lib_bejson_Core_mfdb_core import (
    MFDBCoreError,
    mfdb_core_create_database,
)
from lib_bejson_Core_bejson_chunking import (
    CHUNKED_104_FIELDS,
    MFDB_MANIFEST_FILENAME,
    MFDB_CHUNK_SCHEMA_VERSION,
    bejson_core_chunking_create_mfdb132_package,
    bejson_core_chunking_unchunk_mfdb132_package,
    bejson_core_chunking_get_timestamp,
    bejson_core_chunking_hash_file_bytes,
)

from lib_bejson_Diagrams_bejson_errors import (
    DiagramsError,
    E_DIAGRAMS_INVALID_ROOT,
    E_DIAGRAMS_WRITE_FAILED,
    E_DIAGRAMS_IMPORT_FAILED,
    E_DIAGRAMS_VALIDATION_FAILED,
)


# ---------------------------------------------------------------------------
# Canonical diagram entity schema — the standard every diagram app in the
# ecosystem should start from. Callers may append caller-specific fields
# (e.g. a shape's own private entity, which is app-owned and not defined
# here) but Board/Connector/Territory's own base fields should not drift
# between apps without a matching version bump here.
# ---------------------------------------------------------------------------

BOARD_BASE_FIELDS: List[Dict[str, str]] = [
    {"name": "shape_id",          "type": "string"},
    {"name": "shape_entity_name", "type": "string"},
    {"name": "shape_cx",          "type": "number"},
    {"name": "shape_cy",          "type": "number"},
    {"name": "shape_size_class",  "type": "string"},
    {"name": "shape_kind",        "type": "string"},
    {"name": "shape_parent_fk",   "type": "string"},
    {"name": "shape_collapsed",   "type": "boolean"},
]

CONNECTOR_BASE_FIELDS: List[Dict[str, str]] = [
    {"name": "conn_id",       "type": "string"},
    {"name": "conn_from_fk",  "type": "string"},
    {"name": "conn_to_fk",    "type": "string"},
    {"name": "conn_flow",     "type": "string"},
]

TERRITORY_BASE_FIELDS: List[Dict[str, str]] = [
    {"name": "terr_id",    "type": "string"},
    {"name": "terr_kind",  "type": "string"},
    {"name": "terr_cx",    "type": "number"},
    {"name": "terr_cy",    "type": "number"},
    {"name": "terr_size",  "type": "number"},
    {"name": "terr_label", "type": "string"},
    {"name": "terr_color", "type": "string"},
]

# Base fields every shape's own private entity carries in addition to any
# caller-added custom fields. board_membership_fk is the required foreign
# key pointing back to Board.shape_id.
SHAPE_BASE_FIELDS: List[Dict[str, str]] = [
    {"name": "board_membership_fk", "type": "string"},
    {"name": "shape_label",         "type": "string"},
    {"name": "shape_color",         "type": "string"},
    {"name": "shape_font_color",    "type": "string"},
    {"name": "shape_text",          "type": "string"},
]

KNOWN_SIZE_CLASSES = frozenset({"small", "medium", "large", "huge"})
KNOWN_SHAPE_KINDS  = frozenset({"rect", "circle"})
KNOWN_FLOW_VALUES  = frozenset({"forward", "backward", "bidirectional", "none"})

# Tag written onto every MFDB-132 package produced by this family so
# lib_bejson_Diagrams_diagrams_validator.py can recognize it as a diagram
# package (as opposed to some other, non-diagram MFDB-132 package).
DIAGRAM_SCHEMA_TAG = "BEJSON-Diagram-1"


# ---------------------------------------------------------------------------
# Database creation
# ---------------------------------------------------------------------------

def diagrams_core_create_database(root_dir: str, db_name: str,
                                   extra_entities: Optional[List[dict]] = None) -> str:
    """
    Creates a fresh diagram MFDB root with the standard Board/Connector/
    Territory entities. extra_entities (e.g. a shape's own private entity)
    are appended as-is to the entity list handed to mfdb_core_create_database.
    Returns the manifest path.
    """
    entities = [
        {"name": "Board",     "fields": BOARD_BASE_FIELDS,     "primary_key": "shape_id"},
        {"name": "Connector", "fields": CONNECTOR_BASE_FIELDS, "primary_key": "conn_id"},
        {"name": "Territory", "fields": TERRITORY_BASE_FIELDS, "primary_key": "terr_id"},
    ]
    if extra_entities:
        entities.extend(extra_entities)
    return mfdb_core_create_database(root_dir=root_dir, db_name=db_name, entities=entities)


# ---------------------------------------------------------------------------
# Single-file MFDB-132 export / import (replaces zipped 1.31 export)
# ---------------------------------------------------------------------------

def diagrams_core_export_package(mfdb_root_dir: str, db_name: str,
                                  package_version: Optional[str] = None,
                                  prior_package_doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Chunks a diagram's MFDB root (manifest + every entity file) into a single
    MFDB-132 Chunked-104a document, then tags it Diagram_Schema so the
    Diagrams validator can recognize it as diagram data specifically (not
    just any MFDB-132 package). Does not validate — call
    lib_bejson_Diagrams_diagrams_validator.diagrams_validator_validate_package()
    on the result, or use diagrams_core_write_package_file() which validates
    before writing.
    """
    root_path = Path(mfdb_root_dir)
    if not (root_path / MFDB_MANIFEST_FILENAME).is_file():
        raise DiagramsError(
            f"No {MFDB_MANIFEST_FILENAME} found at root of {mfdb_root_dir} — "
            "not a valid diagram MFDB root.",
            E_DIAGRAMS_INVALID_ROOT,
        )
    doc = bejson_core_chunking_create_mfdb132_package(
        mfdb_root_dir=mfdb_root_dir,
        db_name=db_name,
        package_version=package_version,
        prior_package_doc=prior_package_doc,
    )
    doc["Diagram_Schema"] = DIAGRAM_SCHEMA_TAG
    return doc


def diagrams_core_write_package_file(mfdb_root_dir: str, db_name: str, dest_path: str,
                                      package_version: Optional[str] = None,
                                      prior_package_doc: Optional[Dict[str, Any]] = None,
                                      validate: bool = True) -> str:
    """
    Builds the single-file MFDB-132 package for a diagram and atomically
    writes it to dest_path (a single .mfdb132.bejson document — the whole
    diagram, one file). Validates (MFDB-132 structure -> unpacked MFDB
    database -> diagram-specific rules) before writing unless validate=False.
    Returns dest_path.
    """
    doc = diagrams_core_export_package(mfdb_root_dir, db_name, package_version, prior_package_doc)

    if validate:
        from lib_bejson_Diagrams_diagrams_validator import diagrams_validator_validate_package
        result = diagrams_validator_validate_package(doc)
        if not result.valid:
            raise DiagramsError(
                f"Refusing to write diagram package: {result.errors[0] if result.errors else 'validation failed'}",
                E_DIAGRAMS_WRITE_FAILED,
                {"errors": result.errors, "warnings": result.warnings},
            )

    if not bejson_core_atomic_write(dest_path, doc):
        raise DiagramsError(f"Atomic write failed for {dest_path}", E_DIAGRAMS_WRITE_FAILED)

    return dest_path


def diagrams_core_import_package_file(src_path: str, output_dir: str,
                                       validate: bool = True) -> Tuple[int, Dict[str, Any]]:
    """
    Loads a single-file .mfdb132.bejson diagram package and unchunks it back
    to a standard MFDB root (manifest + data/*.bejson entity files) under
    output_dir. Validates (structure -> database -> diagram rules) before
    unchunking unless validate=False. Returns (files_written, validation_dict).
    """
    p = Path(src_path)
    if not p.is_file():
        raise DiagramsError(f"Package file not found: {src_path}", E_DIAGRAMS_IMPORT_FAILED)

    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise DiagramsError(f"Package is not valid JSON: {e}", E_DIAGRAMS_IMPORT_FAILED)

    if validate:
        from lib_bejson_Diagrams_diagrams_validator import diagrams_validator_validate_package
        result = diagrams_validator_validate_package(doc)
        if not result.valid:
            raise DiagramsError(
                f"Refusing to import diagram package: {result.errors[0] if result.errors else 'validation failed'}",
                E_DIAGRAMS_IMPORT_FAILED,
                {"errors": result.errors, "warnings": result.warnings},
            )

    count, package_validation = bejson_core_chunking_unchunk_mfdb132_package(doc, output_dir)
    if not package_validation.get("valid", False):
        raise DiagramsError(
            f"Import unchunked but failed post-restore validation: {package_validation.get('errors')}",
            E_DIAGRAMS_IMPORT_FAILED,
            package_validation,
        )
    return count, package_validation


# ---------------------------------------------------------------------------
# In-Memory DiagramModel MFDB-132 Packaging & Extraction (v3 Diagrammer)
# ---------------------------------------------------------------------------

def _clean_doc_for_json(doc: Dict[str, Any], ensure_parent_hierarchy: bool = False) -> Dict[str, Any]:
    cleaned = {k: v for k, v in doc.items() if not str(k).startswith("_")}
    if ensure_parent_hierarchy and "Parent_Hierarchy" not in cleaned:
        cleaned["Parent_Hierarchy"] = "../104a.mfdb.bejson"
    return cleaned


def _make_chunk_row(file_name: str, rel_path: str, doc: Dict[str, Any],
                    file_version: str = "1.0.0", is_entity: bool = True) -> list:
    clean_doc = _clean_doc_for_json(doc, ensure_parent_hierarchy=is_entity)
    content = json.dumps(clean_doc, indent=2)
    file_hash = bejson_core_chunking_hash_file_bytes(content.encode("utf-8"))
    return [
        file_name,
        ".bejson",
        content,
        file_version,
        file_hash,
        rel_path,
        False,
        False,
    ]


def diagrams_core_create_mfdb132_package_from_model(model: Dict[str, Any], db_name: str) -> Dict[str, Any]:
    """
    Creates a single-file MFDB-132 package document from an in-memory DiagramModel dict
    ({manifest, boardDoc, connectorDoc, territoryDoc, shapeDocs}).
    """
    from lib_bejson_Diagrams_diagrams_validator import validate_diagram_model
    val_result = validate_diagram_model(model)
    if not val_result.valid:
        msgs = "; ".join(val_result.errors)
        raise DiagramsError(f"Diagram validation failed: {msgs}", E_DIAGRAMS_VALIDATION_FAILED, val_result.errors)

    manifest = model["manifest"]
    board_doc = model["boardDoc"]
    connector_doc = model.get("connectorDoc") or {
        "Format": "BEJSON", "Format_Version": "104", "Format_Creator": "Elton Boehnen",
        "Parent_Hierarchy": "../104a.mfdb.bejson",
        "Records_Type": ["Connector"], "Fields": copy.deepcopy(CONNECTOR_BASE_FIELDS), "Values": [],
    }
    territory_doc = model.get("territoryDoc") or {
        "Format": "BEJSON", "Format_Version": "104", "Format_Creator": "Elton Boehnen",
        "Parent_Hierarchy": "../104a.mfdb.bejson",
        "Records_Type": ["Territory"], "Fields": copy.deepcopy(TERRITORY_BASE_FIELDS), "Values": [],
    }
    shape_docs = model.get("shapeDocs") or {}

    values: List[list] = [
        _make_chunk_row("104a.mfdb.bejson", "104a.mfdb.bejson", manifest, file_version="1.32", is_entity=False),
        _make_chunk_row("board.bejson", "data/board.bejson", board_doc),
        _make_chunk_row("connector.bejson", "data/connector.bejson", connector_doc),
        _make_chunk_row("territory.bejson", "data/territory.bejson", territory_doc),
    ]

    for entity_name, shape_doc in shape_docs.items():
        fname = f"{entity_name.lower()}.bejson"
        values.append(_make_chunk_row(fname, f"data/{fname}", shape_doc))

    return {
        "Format": "BEJSON",
        "Format_Version": "104a",
        "Format_Creator": "Elton Boehnen",
        "Schema_Name": "MFDB-132",
        "Schema_Version": MFDB_CHUNK_SCHEMA_VERSION,
        "Schema_Description": "MFDB 1.32 single-file diagram package.",
        "Chunk_Date": bejson_core_chunking_get_timestamp(),
        "Session_Is_Mounted": False,
        "Mount_Path": "",
        "Package_Version": "1",
        "MFDB_Version": str(manifest.get("MFDB_Version", "1.32")),
        "DB_Name": db_name,
        "Package_Format": "MFDB-Chunked-104a",
        "Diagram_Schema": DIAGRAM_SCHEMA_TAG,
        "Records_Type": ["MFDB-132"],
        "Fields": copy.deepcopy(CHUNKED_104_FIELDS),
        "Values": values,
    }


def diagrams_core_extract_diagram_model_from_mfdb132(chunk_doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts an in-memory DiagramModel dict from a single-file MFDB-132 package document
    using Core's O(1) Field-Map Cache.
    """
    fm = bejson_core_get_field_map(chunk_doc)
    rel_idx = fm.get("Relative_Path")
    content_idx = fm.get("File_Content")
    if rel_idx is None or content_idx is None:
        raise DiagramsError(
            "Corrupted MFDB-132 diagram package: missing Relative_Path or File_Content field.",
            E_DIAGRAMS_IMPORT_FAILED,
        )

    manifest: Optional[Dict[str, Any]] = None
    board_doc: Optional[Dict[str, Any]] = None
    connector_doc: Optional[Dict[str, Any]] = None
    territory_doc: Optional[Dict[str, Any]] = None
    shape_docs: Dict[str, Dict[str, Any]] = {}

    for row in chunk_doc.get("Values", []):
        rel_path = str(row[rel_idx] or "")
        content = str(row[content_idx] or "")
        if not rel_path or not content:
            continue
        doc = json.loads(content)
        if rel_path == "104a.mfdb.bejson":
            manifest = doc
        elif "board.bejson" in rel_path:
            board_doc = doc
        elif "connector.bejson" in rel_path:
            connector_doc = doc
        elif "territory.bejson" in rel_path:
            territory_doc = doc
        elif doc.get("Records_Type") and str(doc["Records_Type"][0]).startswith("Shape_"):
            shape_docs[str(doc["Records_Type"][0])] = doc

    if not manifest or not board_doc:
        raise DiagramsError(
            "Corrupted or incomplete MFDB-132 diagram package: manifest or board missing.",
            E_DIAGRAMS_IMPORT_FAILED,
        )

    model: Dict[str, Any] = {
        "manifest": manifest,
        "boardDoc": board_doc,
        "connectorDoc": connector_doc or {
            "Format": "BEJSON", "Format_Version": "104", "Format_Creator": "Elton Boehnen",
            "Parent_Hierarchy": "../104a.mfdb.bejson",
            "Records_Type": ["Connector"], "Fields": copy.deepcopy(CONNECTOR_BASE_FIELDS), "Values": [],
        },
        "territoryDoc": territory_doc or {
            "Format": "BEJSON", "Format_Version": "104", "Format_Creator": "Elton Boehnen",
            "Parent_Hierarchy": "../104a.mfdb.bejson",
            "Records_Type": ["Territory"], "Fields": copy.deepcopy(TERRITORY_BASE_FIELDS), "Values": [],
        },
        "shapeDocs": shape_docs,
    }

    from lib_bejson_Diagrams_diagrams_validator import validate_diagram_model
    val_result = validate_diagram_model(model)
    if not val_result.valid:
        msgs = "; ".join(val_result.errors)
        raise DiagramsError(f"Imported package validation failed: {msgs}", E_DIAGRAMS_VALIDATION_FAILED, val_result.errors)

    return model


# CamelCase aliases for v3 parity
createMfdb132PackageFromModel = diagrams_core_create_mfdb132_package_from_model
extractDiagramModelFromMfdb132 = diagrams_core_extract_diagram_model_from_mfdb132


# ---------------------------------------------------------------------------
# Field-Map-Cache-backed row lookup helper (Core Mandate: field names, not
# positional indices, everywhere outside the low-level Core library itself).
# ---------------------------------------------------------------------------

def diagrams_core_find_row_by_field(doc: Dict[str, Any], field_name: str, value: Any) -> Optional[list]:
    """Returns the first row in doc['Values'] whose field_name column == value, via the Field Map Cache."""
    idx = bejson_core_get_field_index(doc, field_name)
    if idx < 0:
        return None
    for row in doc.get("Values", []):
        if row[idx] == value:
            return row
    return None