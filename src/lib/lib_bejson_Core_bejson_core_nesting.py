"""
Library:         lib_bejson_Core_bejson_core_nesting.py
Family:          Core
Module Purpose:  Nested-104 detection, validation, field-map cache, safe mutation (append-only schema, null-padding) and dotted-path queries.
Architecture:    Nested BEJSON 104: a cell of a parent 104 document holds a complete embedded 104 document; the physical cell coordinate (NestAddress) is the implicit foreign key. It is neither 104db nor MFDB.
Format_Scope:    Nested 104 (NOT 104db, NOT MFDB)
Glossary:        BEJSON 104, 104a and 104db are the three file formats (Format_Version). 104db = ONE file holding 2+ entity types
                 (Record_Type_Parent discriminator, null-padding). MFDB is NOT a format and NOT 104db: it is a layer made of one 104a manifest
                 (104a.mfdb.bejson) plus dense 104 entity files linked by Parent_Hierarchy. MFDB-132 = an MFDB packed into one Chunked-104a document.
Version:         0.6.0
Release_Version: 300
Date:            2026-10-16
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   9154d111-5fc1-484b-9347-af74b76959fb
Changelog:
  0.6.0 (2026-10-16) - Merged lib_bejson_Core_bejson_nesting_query into this module (QueryMatch, bejson_nesting_query, bejson_nesting_get_path, bejson_nesting_query_summary); query module removed, no alias.
          Nested-cell validation now delegates to Core validate_bejson; field maps use Core bejson_core_get_field_map (key _bejson_field_map replaces the private _nesting_field_map). Local _build_field_map removed.
          Fixed: the no-RELATIONAL_ID fingerprint hashed only Fields, so two different documents with the same schema shared NestMap cache entries (stale scan results) and same-schema nesting looked circular; it now hashes Fields + Values.
  0.5.1 (2026-10-16) - Error codes now imported from lib_bejson_Core_bejson_errors (nesting errors file removed).
          No code, API, error-code (130-139) or output change.
  0.5.0 (2026-10-14) - Moved from the Core_Nesting family into Core (was lib_bejson_CoreNesting_bejson_core_nesting.py, 0.4.5). Renamed to lib_bejson_Core_bejson_core_nesting.py;
          same-directory imports updated. No code, API, error-code (130-139) or output change.
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

from lib_bejson_Core_bejson_errors import (
    E_NESTING_INVALID_CELL,
    E_NESTING_NOT_BEJSON,
    E_NESTING_DEPTH_EXCEEDED,
    E_NESTING_CACHE_MISS,
    E_NESTING_SCHEMA_MISMATCH,
    E_NESTING_CIRCULAR_REF,
    E_NESTING_VALIDATION_FAILED,
    E_NESTING_FIELD_MAP_FAILED,
    E_NESTING_QUERY_INVALID_PATH,
    E_NESTING_QUERY_EMPTY_PATH,
)
from lib_bejson_Core_bejson_core import FIELD_MAP_CACHE_KEY, bejson_core_get_field_map
from lib_bejson_Core_bejson_validator import validate_bejson

VERSION          = "0.6.0"
NESTING_MAX_DEPTH = 16
_VALID_VERSION   = "104"  # 104 ONLY — other formats are out of scope

_MANDATORY_KEYS = frozenset(
    ("Format", "Format_Version", "Format_Creator", "Records_Type", "Fields", "Values")
)


# ---------------------------------------------------------------------------
# NestAddress — canonical 4-tuple memory address for the NestMap.
# (parent_fingerprint, row, col, depth)
# Same content embedded at two different locations = two different addresses.
# No content-based deduplication — location IS identity.
# ---------------------------------------------------------------------------
class NestAddress(NamedTuple):
    parent_fingerprint: str
    row:                int
    col:                int
    depth:              int


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class NestedCell:
    """
    One cell containing a detected and parsed nested BEJSON 104 doc.
    `doc` is a live reference — mutations applied via bejson_nesting_mutate()
    are written back into the parent Values cell automatically.
    `warnings` carries standardization notices (e.g. Records_Type mismatch).
    """
    row:        int
    col:        int
    field_name: str
    depth:      int
    doc:        dict
    is_valid:   bool
    errors:     List[str]          = field(default_factory=list)
    warnings:   List[str]          = field(default_factory=list)
    children:   List["NestedCell"] = field(default_factory=list)

    # NestedCell property: rebuilds the NestAddress (parent fingerprint, row, column, depth) this cell is cached under.
    @property
    def address(self) -> NestAddress:
        """Convenience — reconstruct the address this cell was cached under."""
        # depth is part of address; parent_fingerprint must be supplied
        # externally for full address reconstruction, so this is a partial helper.
        return NestAddress("", self.row, self.col, self.depth)


@dataclass
class NestingResult:
    """Returned by bejson_nesting_scan()."""
    scanned_cells:   int              = 0
    nested_found:    int              = 0
    nested_valid:    int              = 0
    nested_invalid:  int              = 0
    max_depth_seen:  int              = 0
    schema_errors:   int              = 0   # column uniformity violations
    cells:           List[NestedCell] = field(default_factory=list)
    errors:          List[str]        = field(default_factory=list)
    warnings:        List[str]        = field(default_factory=list)


# ---------------------------------------------------------------------------
# NestMap — global address-keyed cache
# Key:   NestAddress(parent_fingerprint, row, col, depth)
# Value: NestedCell
# ---------------------------------------------------------------------------
_NEST_MAP: Dict[NestAddress, NestedCell] = {}


# Returns the cached NestedCell for a (parent_fingerprint, row, col, depth) address, or None.
def bejson_nesting_cache_get(
    parent_fingerprint: str, row: int, col: int, depth: int
) -> Optional[NestedCell]:
    """O(1) NestMap lookup by full 4-tuple address. Returns None on miss."""
    return _NEST_MAP.get(NestAddress(parent_fingerprint, row, col, depth))


# Stores a NestedCell in the NestMap cache under its address.
def bejson_nesting_cache_put(
    parent_fingerprint: str, row: int, col: int, depth: int, cell: NestedCell
) -> None:
    """Insert or overwrite a NestMap entry at the given address."""
    _NEST_MAP[NestAddress(parent_fingerprint, row, col, depth)] = cell


# Clears NestMap entries -- all of them, or only those of one parent_fingerprint. Returns the number removed.
def bejson_nesting_cache_clear(parent_fingerprint: Optional[str] = None) -> int:
    """
    Clear NestMap entries. If parent_fingerprint supplied, clear only that
    doc's entries. Returns number of entries removed.
    """
    global _NEST_MAP
    if parent_fingerprint is None:
        removed_count = len(_NEST_MAP)
        _NEST_MAP = {}
        return removed_count
    matching_keys = [k for k in _NEST_MAP if k.parent_fingerprint == parent_fingerprint]
    for matching_key in matching_keys:
        del _NEST_MAP[matching_key]
    return len(matching_keys)


# Diagnostic snapshot of the NestMap cache (entry counts).
def bejson_nesting_cache_stats() -> dict:
    """Diagnostic snapshot of NestMap state."""
    return {
        "total_entries": len(_NEST_MAP),
        "unique_parents": len({k.parent_fingerprint for k in _NEST_MAP}),
        "depth_spread":  sorted({k.depth for k in _NEST_MAP}),
    }


# Returns every cached NestedCell for one parent document and column (all rows).
def bejson_nesting_cache_lookup(
    parent_fingerprint: str, col: int
) -> List[NestedCell]:
    """
    Return all cached NestedCells for a given parent doc and column index,
    across all rows and depths. Useful for column-level inspection.
    """
    return [
        cached_cell for cache_key, cached_cell in _NEST_MAP.items()
        if cache_key.parent_fingerprint == parent_fingerprint and cache_key.col == col
    ]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Stable identity of a parent document: its RELATIONAL_ID if present, else a hash of the Fields array.
def _doc_fingerprint(doc: dict) -> str:
    """RELATIONAL_ID preferred; fallback to a stable hash of Fields AND Values (content, not just schema)."""
    relational_id_value = doc.get("RELATIONAL_ID") or doc.get("relational_id")
    if relational_id_value:
        return str(relational_id_value)
    content_repr = json.dumps([doc.get("Fields", []), doc.get("Values", [])], sort_keys=True, ensure_ascii=False)
    return "hash:" + hashlib.sha256(content_repr.encode("utf-8")).hexdigest()[:32]


# Fast pre-filter: True for a string cell whose trimmed text starts with { and ends with }, so it might hold an embedded document.
def _is_candidate(value: Any) -> bool:
    """Fast pre-filter: string that trims to {…}."""
    if not isinstance(value, str):
        return False
    trimmed_value = value.strip()
    return trimmed_value.startswith("{") and trimmed_value.endswith("}")


# json.loads of a candidate cell; returns the dict or None if it is not valid JSON object text.
def _parse_cell(raw_cell_text: str) -> Optional[dict]:
    try:
        parsed_value = json.loads(raw_cell_text)
        return parsed_value if isinstance(parsed_value, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


# Canonical string form of a Fields array, used for fingerprints and the field-map cache.
def _fields_signature(doc: dict) -> str:
    """
    Canonical string representation of a doc's Fields array.
    Used for column-schema uniformity comparison.
    Two docs are schema-compatible iff their signatures match.
    """
    return json.dumps(doc.get("Fields", []), sort_keys=True)


# Check that an embedded document is a BEJSON 104 document (rules come from the Core validator) (nested cells must be 104; not 104a, not 104db, not an MFDB manifest). Returns (ok, error list).
def _quick_validate_104(doc: Any) -> Tuple[bool, List[str]]:
    """
    Validates doc strictly as BEJSON 104.
    Returns (is_valid, errors).
    - Non-BEJSON or non-104 → (False, [])  — out of scope, skip silently.
    - BEJSON 104 with violations → (False, [error strings]).
    - Valid BEJSON 104 → (True, []).
    """
    if not isinstance(doc, dict):
        return False, [f"E{E_NESTING_NOT_BEJSON}: not a dict"]

    # Missing mandatory keys → not BEJSON, skip silently
    if _MANDATORY_KEYS - doc.keys():
        return False, []

    # Not BEJSON format → skip silently
    if doc.get("Format") != "BEJSON":
        return False, []

    # Not 104 → out of scope, skip silently
    if doc.get("Format_Version") != _VALID_VERSION:
        return False, []

    # From here: it IS a BEJSON 104 doc. Core's validator is the single source of the rules.
    core_result = validate_bejson(doc)
    validation_errors = [f"E{E_NESTING_VALIDATION_FAILED}: {message}" for message in core_result.errors]
    return len(validation_errors) == 0, validation_errors


# Convention check: the nested document's single Records_Type name should relate to the parent field's name. Returns a warning string or None (convention, not a hard error).
def _check_records_type_convention(
    nested_doc: dict, parent_field_name: str
) -> Optional[str]:
    """
    Returns a warning string if Records_Type doesn't match the PascalCase
    of the parent field name. Returns None if convention is met.
    """
    records_type_value = nested_doc.get("Records_Type", [])
    if not records_type_value:
        return None
    expected_records_type = parent_field_name[0].upper() + parent_field_name[1:] if parent_field_name else ""
    if records_type_value[0] != expected_records_type:
        return (
            f"W: Records_Type '{records_type_value[0]}' in nested doc at col '{parent_field_name}' "
            f"should be '{expected_records_type}' by convention"
        )
    return None


# ---------------------------------------------------------------------------
# Core recursive walk
# ---------------------------------------------------------------------------

# Recursive scan of one cell: if it holds an embedded 104 document, records a NestedCell with its NestAddress and descends into that document's cells, up to the maximum depth (16).
def _walk_cell(
    value:               Any,
    row:                 int,
    col:                 int,
    field_name:          str,
    depth:               int,
    seen_fingerprints:   frozenset,
    parent_fingerprint:  str,
    parent_doc:          dict,
    col_schemas:         Dict[int, str],   # col → Fields signature, enforced per column
) -> Optional[NestedCell]:
    """
    Recursively inspect one cell value for a nested BEJSON 104 doc.
    col_schemas is shared across all rows for a given parent doc scan —
    the first valid nested doc found in a column registers its Fields
    signature; all subsequent ones in the same column must match.
    """
    if depth > NESTING_MAX_DEPTH:
        logging.warning(f"[NESTING] depth cap {NESTING_MAX_DEPTH} hit at row={row} col={col}")
        return None

    if not _is_candidate(value):
        return None

    # Full address includes depth
    cached_cell = bejson_nesting_cache_get(parent_fingerprint, row, col, depth)
    if cached_cell is not None:
        return cached_cell

    parsed_doc = _parse_cell(value)
    if parsed_doc is None:
        return None

    is_valid, cell_errors = _quick_validate_104(parsed_doc)

    # Empty errors + not valid = not a 104 doc → skip silently
    if not is_valid and not cell_errors:
        return None

    cell_warnings: List[str] = []

    # Column schema uniformity check (only on valid docs)
    if is_valid:
        fields_signature = _fields_signature(parsed_doc)
        if col not in col_schemas:
            col_schemas[col] = fields_signature   # first valid doc in this column sets the contract
        elif col_schemas[col] != fields_signature:
            cell_errors.append(
                f"E{E_NESTING_SCHEMA_MISMATCH}: nested doc at row={row} col={col} "
                f"has different Fields schema than other docs in this column"
            )
            is_valid = False

    # Field map injected eagerly on first encounter during scan — O(1) for all subsequent consumers of this cell
    if is_valid:
        bejson_core_get_field_map(parsed_doc)  # Core field-map cache, stored on the doc under FIELD_MAP_CACHE_KEY

    # Records_Type convention check
    if is_valid:
        convention_warning = _check_records_type_convention(parsed_doc, field_name)
        if convention_warning:
            cell_warnings.append(convention_warning)

    nested_fingerprint = _doc_fingerprint(parsed_doc)

    # Circular reference guard
    if nested_fingerprint in seen_fingerprints:
        circular_cell = NestedCell(
            row=row, col=col, field_name=field_name, depth=depth,
            doc=parsed_doc, is_valid=False, warnings=cell_warnings,
            errors=[f"E{E_NESTING_CIRCULAR_REF}: circular reference at depth {depth}"],
        )
        bejson_nesting_cache_put(parent_fingerprint, row, col, depth, circular_cell)
        return circular_cell

    resolved_cell = NestedCell(
        row=row, col=col, field_name=field_name, depth=depth,
        doc=parsed_doc, is_valid=is_valid, errors=cell_errors, warnings=cell_warnings,
    )

    # Recurse into this nested doc's own Values
    if is_valid:
        child_seen_fingerprints = seen_fingerprints | {nested_fingerprint}
        child_col_schemas: Dict[int, str] = {}   # each nesting level has its own col contracts
        # Core field map for O(1) idx→name lookup (avoids a per-cell array read)
        child_field_map: Dict[str, int] = bejson_core_get_field_map(parsed_doc)
        child_field_name_by_index: Dict[int, str] = {
            column_index: field_name_str for field_name_str, column_index in child_field_map.items()
        }
        child_values = parsed_doc.get("Values", [])
        for child_row_index, child_row in enumerate(child_values):
            for child_col_index, child_cell_value in enumerate(child_row):
                child_field_name = child_field_name_by_index.get(child_col_index, f"col_{child_col_index}")
                child_cell = _walk_cell(
                    value=child_cell_value, row=child_row_index, col=child_col_index, field_name=child_field_name,
                    depth=depth + 1, seen_fingerprints=child_seen_fingerprints,
                    parent_fingerprint=nested_fingerprint, parent_doc=parsed_doc,
                    col_schemas=child_col_schemas,
                )
                if child_cell is not None:
                    resolved_cell.children.append(child_cell)

    bejson_nesting_cache_put(parent_fingerprint, row, col, depth, resolved_cell)
    return resolved_cell


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Entry point. Call AFTER the parent passes normal 104 validation. Walks every cell of the parent, finds embedded 104 documents and returns a NestingResult (cells tree, depths, warnings). Uses the NestMap cache when use_cache is True.
# Nested BEJSON is 104-inside-104 via a cell; it is not 104db and not MFDB.
def bejson_nesting_scan(doc: dict, use_cache: bool = True) -> NestingResult:
    """
    Entry point. Call AFTER normal Core 104 validation passes.

    Walks doc.Values for embedded BEJSON 104 docs. Enforces:
      - Per-column schema uniformity (E134 on violation)
      - Full BEJSON 104 validity on each nested doc (E136 on violation)
      - Depth safety ceiling (NESTING_MAX_DEPTH = 16)
      - Circular reference detection (E135)

    Args:
        doc:       A loaded, pre-validated BEJSON 104 document (dict).
        use_cache: Skip NestMap reads if False (still writes on new finds).

    Returns:
        NestingResult
    """
    result = NestingResult()

    if not isinstance(doc, dict):
        result.errors.append(f"E{E_NESTING_NOT_BEJSON}: doc must be a dict")
        return result

    fields_list = doc.get("Fields", [])
    values_list = doc.get("Values", [])

    if not isinstance(fields_list, list) or not isinstance(values_list, list):
        result.errors.append(f"E{E_NESTING_VALIDATION_FAILED}: Fields/Values malformed")
        return result

    document_fingerprint = _doc_fingerprint(doc)
    root_seen_fingerprints  = frozenset({document_fingerprint})
    col_schemas: Dict[int, str] = {}  # column → Fields signature contract

    for row_index, row in enumerate(values_list):
        if not isinstance(row, list):
            continue
        for col_index, cell_value in enumerate(row):
            result.scanned_cells += 1
            if not _is_candidate(cell_value):
                continue

            resolved_field_name = fields_list[col_index]["name"] if col_index < len(fields_list) else f"col_{col_index}"

            if use_cache:
                cached_hit = bejson_nesting_cache_get(document_fingerprint, row_index, col_index, 1)
                if cached_hit is not None:
                    result.nested_found += 1
                    result.nested_valid   += 1 if cached_hit.is_valid else 0
                    result.nested_invalid += 0 if cached_hit.is_valid else 1
                    result.max_depth_seen = max(result.max_depth_seen, cached_hit.depth)
                    result.schema_errors  += sum(
                        1 for error_message in cached_hit.errors if f"E{E_NESTING_SCHEMA_MISMATCH}" in error_message
                    )
                    result.cells.append(cached_hit)
                    continue

            nested_cell = _walk_cell(
                value=cell_value, row=row_index, col=col_index, field_name=resolved_field_name,
                depth=1, seen_fingerprints=root_seen_fingerprints,
                parent_fingerprint=document_fingerprint, parent_doc=doc,
                col_schemas=col_schemas,
            )
            if nested_cell is None:
                continue

            result.nested_found   += 1
            result.nested_valid   += 1 if nested_cell.is_valid else 0
            result.nested_invalid += 0 if nested_cell.is_valid else 1
            result.max_depth_seen  = max(result.max_depth_seen, nested_cell.depth)
            result.schema_errors  += sum(
                1 for error_message in nested_cell.errors if f"E{E_NESTING_SCHEMA_MISMATCH}" in error_message
            )
            for warning_message in nested_cell.warnings:
                result.warnings.append(warning_message)
            result.cells.append(nested_cell)

    return result


# Safely updates a value inside a nested document located by a NestedCell and writes the re-serialized nested document back into the parent cell. Append-only schema: it will not change Fields of the nested doc.
def bejson_nesting_mutate(
    parent_doc:  dict,
    nested_cell: NestedCell,
    mutation_fn: Callable[[dict], None],
) -> None:
    """
    Apply mutation_fn to nested_cell.doc in-place, then serialize the result
    back into parent_doc.Values[nested_cell.row][nested_cell.col].

    Schema field additions (appending to Fields) are safe — existing Value
    rows in the nested doc are automatically null-padded to maintain
    positional integrity.

    Schema field removals or reorders are NOT permitted and will raise
    ValueError. This is a hard rule: removals are breaking changes.

    Args:
        parent_doc:  The root or parent BEJSON 104 doc containing this cell.
        nested_cell: The NestedCell returned from scan (holds live doc ref).
        mutation_fn: Callable that receives and mutates the nested doc dict.

    Raises:
        ValueError: If cell address is out of bounds, or mutation attempts
                    a field removal/reorder.
    """
    row = nested_cell.row
    col = nested_cell.col

    parent_values = parent_doc.get("Values", [])
    if row >= len(parent_values) or col >= len(parent_values[row]):
        raise ValueError(
            f"E{E_NESTING_INVALID_CELL}: address row={row} col={col} out of bounds"
        )

    doc = nested_cell.doc
    fields_before: List[dict] = [field_def.copy() for field_def in doc.get("Fields", [])]
    fields_count_before = len(fields_before)

    # Apply the mutation
    mutation_fn(doc)

    fields_after: List[dict] = doc.get("Fields", [])
    fields_count_after = len(fields_after)

    # Guard: no removals
    if fields_count_after < fields_count_before:
        raise ValueError(
            f"E{E_NESTING_SCHEMA_MISMATCH}: mutation removed fields — "
            f"field removal is a breaking change and is not permitted"
        )

    # Guard: no reorders (first fields_count_before fields must be unchanged)
    for field_index, (field_before, field_after) in enumerate(zip(fields_before, fields_after)):
        if field_before.get("name") != field_after.get("name") or field_before.get("type") != field_after.get("type"):
            raise ValueError(
                f"E{E_NESTING_SCHEMA_MISMATCH}: mutation reordered or retyped field at "
                f"index {field_index} — only append-only additions are permitted"
            )

    # Auto null-pad existing rows if Fields grew
    if fields_count_after > fields_count_before:
        fields_added_count = fields_count_after - fields_count_before
        for value_row in doc.get("Values", []):
            if isinstance(value_row, list):
                value_row.extend([None] * fields_added_count)

    # Strip internal cache artifact before serializing
    doc.pop(FIELD_MAP_CACHE_KEY, None)

    # Write back into parent cell
    parent_doc["Values"][row][col] = json.dumps(doc, ensure_ascii=False)


# Field-name -> column map for a NestedCell's embedded document (Core field-map cache).
def bejson_nesting_get_field_map(nested_cell: NestedCell) -> Dict[str, int]:
    """
    Field-name→col-index map for a NestedCell's doc, via the Core field-map cache
    (bejson_core_get_field_map; freshness-guarded, stored under FIELD_MAP_CACHE_KEY).
    """
    return bejson_core_get_field_map(nested_cell.doc)


# Depth-first flat list of every NestedCell in a NestingResult.
def bejson_nesting_flatten(result: NestingResult) -> List[NestedCell]:
    """Depth-first flat list of every NestedCell across the full result tree."""
    flattened_cells: List[NestedCell] = []
    # Inner helper of flatten: appends cells and recurses into their children.
    def _collect(cells: List[NestedCell]) -> None:
        for cell_item in cells:
            flattened_cells.append(cell_item)
            _collect(cell_item.children)
    _collect(result.cells)
    return flattened_cells


# All NestedCells found in one parent column (across rows).
def bejson_nesting_get_column(
    result: NestingResult, col: int
) -> List[NestedCell]:
    """
    Return all top-level NestedCells for a specific column index.
    Depth-1 entries only — does not recurse into children.
    """
    return [cell_item for cell_item in result.cells if cell_item.col == col]


# Human-readable summary string of a NestingResult (counts, depths, warnings).
def bejson_nesting_summary(result: NestingResult) -> str:
    """Human-readable summary of a NestingResult."""
    summary_lines = [
        "BEJSON Core_Nesting Scan Summary",
        f"  Cells scanned    : {result.scanned_cells}",
        f"  Nested found     : {result.nested_found}",
        f"  Valid nested     : {result.nested_valid}",
        f"  Invalid nested   : {result.nested_invalid}",
        f"  Max depth seen   : {result.max_depth_seen}",
        f"  Schema errors    : {result.schema_errors}",
    ]
    if result.errors:
        summary_lines.append("  Scan errors:")
        for error_message in result.errors:
            summary_lines.append(f"    - {error_message}")
    if result.warnings:
        summary_lines.append("  Warnings:")
        for warning_message in result.warnings:
            summary_lines.append(f"    ~ {warning_message}")
    for cell_item in bejson_nesting_flatten(result):
        status_label = "VALID" if cell_item.is_valid else "INVALID"
        indent = "  " + ("  " * (cell_item.depth - 1))
        summary_lines.append(
            f"{indent}[{status_label}] row={cell_item.row} col={cell_item.col} "
            f"field='{cell_item.field_name}' depth={cell_item.depth}"
        )
        for error_message in cell_item.errors:
            summary_lines.append(f"{indent}  ! {error_message}")
        for warning_message in cell_item.warnings:
            summary_lines.append(f"{indent}  ~ {warning_message}")
    return "\n".join(summary_lines)


# ---------------------------------------------------------------------------
# Dotted-path queries over nested 104 documents (e.g. player_inventory[*].item_id)
# Merged in from the former lib_bejson_Core_bejson_nesting_query module.
# ---------------------------------------------------------------------------

_SEGMENT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(\[(\*|\d+)\])?$")


@dataclass
class QueryMatch:
    """One matched cell at the end of a resolved path."""
    path:         str
    value:        Any
    field_chain:  List[str] = field(default_factory=list)
    row_chain:    List[int] = field(default_factory=list)
    col_chain:    List[int] = field(default_factory=list)


# Parses a dotted path such as player_inventory[*].item_id into (field_name, selector) steps.
def _parse_path(path: str) -> List[Tuple[str, Optional[Any]]]:
    """
    Parses a dotted path string into (field_name, selector) tuples.
    selector is '*' , an int, or None (treated as '*' by the walker).
    Raises ValueError with an E138/E139-prefixed message on bad grammar.
    """
    if not path or not path.strip():
        raise ValueError(f"E{E_NESTING_QUERY_EMPTY_PATH}: path is empty")

    parsed_segments = []
    for raw_segment in path.strip().split("."):
        segment_match = _SEGMENT_RE.match(raw_segment)
        if not segment_match:
            raise ValueError(
                f"E{E_NESTING_QUERY_INVALID_PATH}: bad segment '{raw_segment}' in path '{path}'"
            )
        segment_field_name, _, selector_text = segment_match.groups()
        if selector_text is None:
            selector: Optional[Any] = None
        elif selector_text == "*":
            selector = "*"
        else:
            selector = int(selector_text)
        parsed_segments.append((segment_field_name, selector))
    return parsed_segments


# Recursive walk of a nested-104 document along parsed path steps, collecting QueryMatch results.
def _query_walk(
    doc: dict,
    segments: List[Tuple[str, Optional[Any]]],
    segment_index: int,
    full_path: str,
    field_chain: List[str],
    row_chain: List[int],
    col_chain: List[int],
    match_value: Any,
    results: List[QueryMatch],
) -> None:
    if not isinstance(doc, dict):
        return

    field_name, selector = segments[segment_index]
    field_map = bejson_core_get_field_map(doc)
    if field_name not in field_map:
        return  # dead branch — field not present at this level, not an error

    col = field_map[field_name]
    values = doc.get("Values", [])
    is_last_segment = segment_index == len(segments) - 1

    row_indices = range(len(values)) if selector in (None, "*") else [selector]

    for row_index in row_indices:
        if row_index < 0 or row_index >= len(values):
            continue
        row = values[row_index]
        if not isinstance(row, list) or col >= len(row):
            continue
        cell_value = row[col]

        if is_last_segment:
            if match_value is None or cell_value == match_value:
                results.append(
                    QueryMatch(
                        path=full_path,
                        value=cell_value,
                        field_chain=field_chain + [field_name],
                        row_chain=row_chain + [row_index],
                        col_chain=col_chain + [col],
                    )
                )
            continue

        if not _is_candidate(cell_value):
            continue
        nested_doc = _parse_cell(cell_value)
        if nested_doc is None:
            continue

        _query_walk(
            nested_doc, segments, segment_index + 1, full_path,
            field_chain + [field_name], row_chain + [row_index], col_chain + [col],
            match_value, results,
        )


# Finds values in a nested 104 document by dotted path (selectors: [*], [n], optional match_value filter). Returns a list of QueryMatch.
def bejson_nesting_query(
    doc: dict, path: str, match_value: Any = None
) -> List[QueryMatch]:
    """
    Resolve a dotted path through doc and its nested BEJSON 104 cells.

    Args:
        doc:         Root or already-nested BEJSON 104 document (dict).
        path:        Dotted path, e.g. "player_inventory[*].item_id".
        match_value: If provided, only cells equal to this value are
                     returned. If None, every cell reached by the path
                     is returned unfiltered.

    Returns:
        List[QueryMatch] — empty list if nothing matched (never raises
        for missing data; only raises ValueError on malformed path syntax).
    """
    parsed_segments = _parse_path(path)  # raises ValueError on bad grammar
    match_results: List[QueryMatch] = []
    _query_walk(doc, parsed_segments, 0, path, [], [], [], match_value, match_results)
    return match_results


# Safe-get convenience: first value at a path, or default.
def bejson_nesting_get_path(doc: dict, path: str, default: Any = None) -> Any:
    """
    Safe-Get convenience wrapper (Section 9 standard): returns the value of
    the FIRST match for path, or `default` if the path resolves to nothing
    or is malformed. Never raises.
    """
    try:
        matches = bejson_nesting_query(doc, path)
    except ValueError:
        return default
    return matches[0].value if matches else default


# Human-readable summary of a query result list.
def bejson_nesting_query_summary(matches: List[QueryMatch]) -> str:
    """Human-readable summary of a query() result list."""
    if not matches:
        return "BEJSON Core_Nesting Query Summary\n  0 matches"
    summary_lines = [f"BEJSON Core_Nesting Query Summary — {len(matches)} match(es)"]
    for query_match in matches:
        chain_text = " -> ".join(
            f"{chain_field_name}[row={chain_row},col={chain_col}]"
            for chain_field_name, chain_row, chain_col in zip(
                query_match.field_chain, query_match.row_chain, query_match.col_chain
            )
        )
        summary_lines.append(f"  {chain_text} = {query_match.value!r}")
    return "\n".join(summary_lines)