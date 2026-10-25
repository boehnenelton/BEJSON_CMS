"""
Library:         lib_bejson_Core_bejson_validator.py
Family:          Core
Module Purpose:  Structural validator for BEJSON 104, 104a and 104db (mandatory keys, Records_Type, Fields, Values, version-specific rules). MFDB rules live in the mfdb_validator module.
Architecture:    Format-level BEJSON layer that works on any BEJSON document (104, 104a, 104db) through positional Fields/Values and the field-map cache. It does not orchestrate MFDB and is not specific to 104db.
Format_Scope:    104 | 104a | 104db (generic)
Glossary:        BEJSON 104, 104a and 104db are the three file formats (Format_Version). 104db = ONE file holding 2+ entity types
                 (Record_Type_Parent discriminator, null-padding). MFDB is NOT a format and NOT 104db: it is a layer made of one 104a manifest
                 (104a.mfdb.bejson) plus dense 104 entity files linked by Parent_Hierarchy. MFDB-132 = an MFDB packed into one Chunked-104a document.
Version:         2.2.7
Release_Version: 300
Date:            2026-10-16
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   21d67eaf-89ea-4f3e-b5fb-0c2e9395dd4a
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Set, Union

try:
    from lib_bejson_Core_bejson_errors import (
        E_INVALID_JSON,
        E_MISSING_MANDATORY_KEY,
        E_INVALID_FORMAT,
        E_INVALID_VERSION,
        E_INVALID_RECORDS_TYPE,
        E_INVALID_FIELDS,
        E_TYPE_MISMATCH,
        E_RECORD_LENGTH_MISMATCH,
        E_RESERVED_KEY_COLLISION,
        E_INVALID_RECORD_TYPE_PARENT,
        E_FILE_NOT_FOUND
    )
except ImportError as e:
    import logging
    logging.critical(f"[VALIDATOR] FATAL: Error registry unreachable: {e}")
    raise SystemExit(1)

VALID_VERSIONS = {"104", "104a", "104db"}
VALID_FIELD_TYPES = {"string", "integer", "number", "boolean", "array", "object"}
MANDATORY_KEYS = ("Format", "Format_Version", "Format_Creator", "Records_Type", "Fields", "Values")
IN_MEMORY_ONLY_KEYS = frozenset({"_nesting_field_map"})  # other in-memory caches (never persisted)
FIELD_MAP_CACHE_KEY = "_bejson_field_map"  # in-memory only; legitimate on dict input, forbidden in files/strings

@dataclass
class ValidationResult:
    valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    current_file: str = ""

    # Records a validation error and marks the result invalid.
    def add_error(self, message: str):
        self.valid = False
        self.errors.append(message)

    # Records a non-fatal warning; the result stays valid.
    def add_warning(self, message: str):
        self.warnings.append(message)

    # Property alias for .valid so both result.valid and result.is_valid work.
    @property
    def is_valid(self) -> bool:
        """Alias for .valid, so both result.valid and result.is_valid work."""
        return self.valid

class BEJSONValidationError(Exception):
    # Exception for validation failures (BEJSONValidationError); `code` is the numeric E_* code.
    def __init__(self, message: str, code: int):
        super().__init__(message)
        self.code = code

# Step 1: parses the input (JSON string, dict, or file path when is_file=True) and records a syntax error in `res` if it is not valid JSON.
def bejson_validator_check_json_syntax(input_, res: ValidationResult, is_file=False):
    if is_file:
        path = Path(input_)
        if not path.exists(): raise BEJSONValidationError(f"File not found: {input_}", E_FILE_NOT_FOUND)
        text = path.read_text(encoding="utf-8")
        res.current_file = str(path)
    else: text = input_
    if isinstance(text, dict): return text
    try: return json.loads(text)
    except Exception as e: raise BEJSONValidationError(f"Invalid JSON: {e}", E_INVALID_JSON)

# Step 2: all six mandatory top-level keys must exist (Format, Format_Version, Format_Creator, Records_Type, Fields, Values),
# Format must be 'BEJSON' and Format_Creator must be 'Elton Boehnen'. Returns the Format_Version ('104', '104a' or '104db'). The same six keys apply to every version (and to MFDB manifest/entity files, which are 104a/104).
def bejson_validator_check_mandatory_keys(doc):
    for key in MANDATORY_KEYS:
        if key not in doc: raise BEJSONValidationError(f"Missing key: {key}", E_MISSING_MANDATORY_KEY)
    if doc["Format"] != "BEJSON": raise BEJSONValidationError("Invalid Format", E_INVALID_FORMAT)
    if doc["Format_Creator"] != "Elton Boehnen":
        raise BEJSONValidationError("Invalid Format_Creator: Must be 'Elton Boehnen'", E_INVALID_FORMAT)
    version = doc.get("Format_Version", "")
    if version not in VALID_VERSIONS: raise BEJSONValidationError(f"Invalid version: {version}", E_INVALID_VERSION)
    return version

# Step 3: Records_Type must be a list. 104 and 104a require exactly ONE type; 104db requires TWO or more. (An MFDB manifest is 104a, so its Records_Type is the single entry ["mfdb"].)
def bejson_validator_check_records_type(doc, version):
    rt = doc["Records_Type"]
    if not isinstance(rt, list):
        raise BEJSONValidationError("Records_Type must be a list", E_INVALID_RECORDS_TYPE)
    count = len(rt)
    if version in ("104", "104a"):
        if count != 1:
            raise BEJSONValidationError(f"BEJSON {version} must have exactly 1 record type. Found {count}.", E_INVALID_RECORDS_TYPE)
    elif version == "104db":
        if count < 2:
            raise BEJSONValidationError("104db requires 2+ types", E_INVALID_RECORDS_TYPE)

# Step 4 (104db only; no-op for 104/104a): the first field must be named Record_Type_Parent and every row's column-0 value must be one of Records_Type. This discriminator exists only in 104db -- MFDB entity files do not have it.
def bejson_validator_check_record_type_parent(doc, version):
    if version != "104db": return True
    fields = doc["Fields"]
    if not fields or fields[0].get("name") != "Record_Type_Parent":
        raise BEJSONValidationError("104db first field must be 'Record_Type_Parent'", E_INVALID_RECORD_TYPE_PARENT)
    valid_types = set(doc["Records_Type"])
    for i, record in enumerate(doc["Values"]):
        if not record: continue
        rtp = record[0]
        if rtp not in valid_types:
            raise BEJSONValidationError(f"Invalid Record_Type_Parent '{rtp}' at row {i}", E_INVALID_RECORD_TYPE_PARENT)
    return True

# Step 5: every field needs a name and a lowercase type from VALID_FIELD_TYPES. 104a forbids array/object types. In 104db every field except Record_Type_Parent must carry a Record_Type_Parent property naming the entity that owns it. Returns the field count.
def bejson_validator_check_fields_structure(doc, version):
    fields = doc["Fields"]
    for i, f in enumerate(fields):
        fname = f.get("name")
        ftype = f.get("type")
        if not fname or not ftype:
            raise BEJSONValidationError(f"Field {i} missing name or type", E_INVALID_FIELDS)
        if ftype not in VALID_FIELD_TYPES:
            raise BEJSONValidationError(
                f"Field '{fname}' (index {i}) has invalid type '{ftype}'. "
                f"Must be exactly one of {sorted(VALID_FIELD_TYPES)} (lowercase).",
                E_INVALID_FIELDS,
            )
        if version == "104a" and ftype in ("array", "object"):
            raise BEJSONValidationError(
                f"104a forbids complex type '{ftype}'. "
                "Use Format_Version \"104\" for schemas requiring array or object fields.",
                E_INVALID_FIELDS,
            )
        if version == "104db" and fname != "Record_Type_Parent" and "Record_Type_Parent" not in f:
            raise BEJSONValidationError(f"Field '{fname}' missing Record_Type_Parent in 104db", E_INVALID_RECORD_TYPE_PARENT)
    return len(fields)

# Step 6: every row must have exactly one cell per field and each non-null cell must match its field type (string, integer, number, boolean, array, object; bool is not accepted as integer/number). null is always allowed -- in 104db it is the null-padding for fields owned by other entities.
def bejson_validator_check_values(doc, version, fields_count):
    fields = doc["Fields"]
    for i, record in enumerate(doc["Values"]):
        if len(record) != fields_count:
            raise BEJSONValidationError(f"Length mismatch at row {i}", E_RECORD_LENGTH_MISMATCH)
        for j, val in enumerate(record):
            ftype = fields[j].get("type")
            if val is None: continue
            
            # Full type validation including array/object
            if ftype == "string" and not isinstance(val, str):
                 raise BEJSONValidationError(f"Type mismatch at row {i}, col {j} ({fields[j]['name']}): expected string", E_TYPE_MISMATCH)
            elif ftype == "integer" and (not isinstance(val, int) or isinstance(val, bool)):
                 raise BEJSONValidationError(f"Type mismatch at row {i}, col {j} ({fields[j]['name']}): expected integer", E_TYPE_MISMATCH)
            elif ftype == "number" and (not isinstance(val, (int, float)) or isinstance(val, bool)):
                 # bool is a subclass of int in Python, so True/False pass isinstance(int,float).
                 # Explicitly exclude bool — BEJSON "number" means a numeric value, not a boolean.
                 raise BEJSONValidationError(f"Type mismatch at row {i}, col {j} ({fields[j]['name']}): expected number, got bool", E_TYPE_MISMATCH)
            elif ftype == "boolean" and not isinstance(val, bool):
                 raise BEJSONValidationError(f"Type mismatch at row {i}, col {j} ({fields[j]['name']}): expected boolean", E_TYPE_MISMATCH)
            elif ftype == "array" and not isinstance(val, list):
                 raise BEJSONValidationError(f"Type mismatch at row {i}, col {j} ({fields[j]['name']}): expected array", E_TYPE_MISMATCH)
            elif ftype == "object" and not isinstance(val, dict):
                 raise BEJSONValidationError(f"Type mismatch at row {i}, col {j} ({fields[j]['name']}): expected object", E_TYPE_MISMATCH)

# Rejects a document whose Fields contain the same name twice (E_INVALID_FIELDS). Applies to 104, 104a and 104db; duplicate names would make field-map lookups ambiguous (the map keeps only the last index).
def bejson_validator_check_field_names_unique(doc):
    seen = set()
    for i, f in enumerate(doc["Fields"]):
        fname = f.get("name")
        if fname in seen:
            raise BEJSONValidationError(f"Duplicate field name '{fname}' at index {i}", E_INVALID_FIELDS)
        seen.add(fname)

# Handles the reserved in-memory key _bejson_field_map. A document loaded from a file or JSON string must NOT contain it (E_RESERVED_KEY_COLLISION): it is an in-memory cache only. A dict passed in memory may carry it, but it must match Fields exactly (whole-map check; validation is not a hot path), otherwise it is rejected as stale or forged.
def bejson_validator_check_field_map_cache(doc, persisted):
    """The field-map cache is an in-memory artifact. A persisted copy is hostile or stale; an
    in-memory copy must agree with Fields (O(1) probe) or downstream lookups read wrong columns."""
    if FIELD_MAP_CACHE_KEY not in doc: return
    if persisted:
        raise BEJSONValidationError(
            f"Reserved key '{FIELD_MAP_CACHE_KEY}' must not be persisted (in-memory cache only)", E_RESERVED_KEY_COLLISION)
    cached, fields = doc[FIELD_MAP_CACHE_KEY], doc["Fields"]
    # Validation is not a hot path: verify the whole map, not just a probe.
    expected = {(f.get("name") if isinstance(f, dict) else str(f)): i for i, f in enumerate(fields)}
    ok = isinstance(cached, dict) and dict(cached) == expected and len(expected) == len(fields)
    if not ok:
        raise BEJSONValidationError(f"In-memory '{FIELD_MAP_CACHE_KEY}' does not match Fields (stale or forged)", E_RESERVED_KEY_COLLISION)

# Step 7: custom top-level keys (the reserved in-memory key _bejson_field_map is skipped here and handled by check_field_map_cache). 104 and 104db forbid them (only the six mandatory keys plus Parent_Hierarchy are allowed). 104a allows custom headers (file-level metadata, PascalCase recommended). MFDB manifests use this 104a allowance for MFDB_Version, DB_Name, etc.
def bejson_validator_check_custom_headers(doc, version, persisted=True):
    mandatory_set = set(MANDATORY_KEYS)
    for key in doc:
        if key in mandatory_set or key == "Parent_Hierarchy" or key == FIELD_MAP_CACHE_KEY: continue
        # '_' prefix is reserved for in-memory caches: persisted input never carries one; in-memory input only the known ones.
        if isinstance(key, str) and key.startswith("_"):
            if persisted or key not in IN_MEMORY_ONLY_KEYS:
                raise BEJSONValidationError(f"Reserved key collision: '{key}' uses the reserved '_' prefix", E_RESERVED_KEY_COLLISION)
            continue
        if version in ("104", "104db"):
            raise BEJSONValidationError(f"Custom key '{key}' forbidden in {version}", E_RESERVED_KEY_COLLISION)
        # 104a: Custom headers allowed, no strict PascalCase enforcement
        # 104a custom headers carry file-level metadata only; PascalCase is recommended, not enforced.
        # 104 and 104db forbid custom top-level keys (rejected above); Parent_Hierarchy is the built-in exception.

# Runs all steps for a document, string or file and returns a ValidationResult (valid, errors, warnings). Handles 104, 104a and 104db. It validates BEJSON structure only; MFDB rules (manifest/entity relationship, Parent_Hierarchy, record_count) are in mfdb_validator.
# Also rejects duplicate field names (E_INVALID_FIELDS) and, for file or string input, a persisted _bejson_field_map key (E_RESERVED_KEY_COLLISION). An in-memory dict may carry the cache only if it matches Fields exactly.
def validate_bejson(input_data: Union[str, dict], is_file: bool = False) -> ValidationResult:
    """Thread-safe validation. Returns a ValidationResult object."""
    res = ValidationResult()
    try:
        doc = bejson_validator_check_json_syntax(input_data, res, is_file=is_file)
        version = bejson_validator_check_mandatory_keys(doc)
        persisted = is_file or not isinstance(input_data, dict)
        bejson_validator_check_custom_headers(doc, version, persisted)
        bejson_validator_check_records_type(doc, version)
        bejson_validator_check_record_type_parent(doc, version)
        fields_count = bejson_validator_check_fields_structure(doc, version)
        bejson_validator_check_field_names_unique(doc)
        bejson_validator_check_field_map_cache(doc, persisted)
        bejson_validator_check_values(doc, version, fields_count)
    except BEJSONValidationError as e:
        res.add_error(str(e))
    except Exception as e:
        res.add_error(f"Unexpected validation error: {e}")
    return res

# Runs validate_bejson and returns a human-readable report string.
def bejson_validator_get_report(input_data, is_file: bool = False) -> str:
    """Return a human-readable validation report string."""
    res = validate_bejson(input_data, is_file=is_file)
    lines = ["BEJSON Validation Report"]
    lines.append("  File: " + (res.current_file or "<string>"))
    lines.append("  Valid: " + str(res.valid))
    if res.errors:
        lines.append("  Errors:")
        for e in res.errors:
            lines.append("    - " + e)
    if res.warnings:
        lines.append("  Warnings:")
        for w in res.warnings:
            lines.append("    - " + w)
    return "\n".join(lines)

# Validates a JSON string; raises BEJSONValidationError on the first error, returns the result otherwise.
# String/file validation wrappers that raise BEJSONValidationError on the first error
def bejson_validator_validate_string(json_string):
    res = validate_bejson(json_string)
    if not res.valid:
        raise BEJSONValidationError(res.errors[0], E_INVALID_FORMAT)
    return True

# Validates a BEJSON file on disk; raises BEJSONValidationError on the first error.
def bejson_validator_validate_file(file_path):
    res = validate_bejson(file_path, is_file=True)
    if not res.valid:
        raise BEJSONValidationError(res.errors[0], E_INVALID_FORMAT)
    return True