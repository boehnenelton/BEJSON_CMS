"""
Library:         lib_bejson_Diagrams_bejson_errors.py
Family:          Diagrams
Module Purpose:  Error registry for the Diagrams family (error codes 420-449).
Architecture:    MFDB provides multi-file database federation coordinating a 104a central manifest (104a.mfdb.bejson) with dense 104 entity tables, supporting atomic transaction locks and cross-disk relational foreign keys.
Version:         1.2.0
Release_Version: 300
Date:            2026-10-29
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   7b4a2e1d-8f9c-43e6-a0b5-9d3c1e2f8a74
Changelog:
  1.2.0 (2026-10-29) - Merged v3 Diagrammer error codes (436-449: validation failed, circular hierarchy,
          shape/connector/territory not found, duplicate ID, invalid coordinates, export/AI call/scaffold/
          parse failures, self-reference, and dangling parent/connector codes) and added DIAGRAMS_ERROR_CODES
          map and exception classes for 100% PY/TS/JS parity.
  1.1.0 (2026-09-25) - Added 435 for diagrams_ai_validate_plan_semantics().
"""

from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Diagrams (420-449)
# ---------------------------------------------------------------------------
E_DIAGRAMS_NOT_MFDB132_PACKAGE      = 420  # Doc failed mfdb_validator_is_mfdb132_package()
E_DIAGRAMS_MFDB132_INVALID          = 421  # Doc failed mfdb_validator_validate_mfdb132_package()
E_DIAGRAMS_MFDB_DATABASE_INVALID    = 422  # Unpacked manifest failed mfdb_validator_validate_database()
E_DIAGRAMS_MISSING_ENTITY           = 423  # Required Board/Connector/Territory entity absent from manifest
E_DIAGRAMS_MISSING_FIELD            = 424  # Required field absent from an entity's Fields[]
E_DIAGRAMS_FK_UNRESOLVED            = 425  # board_membership_fk / conn_from_fk / conn_to_fk / shape_parent_fk points nowhere
E_DIAGRAMS_INVALID_SIZE_CLASS       = 426  # shape_size_class not in the known SIZE_CLASS set
E_DIAGRAMS_INVALID_ROOT             = 427  # mfdb_root_dir has no 104a.mfdb.bejson at its root
E_DIAGRAMS_WRITE_FAILED             = 428  # Atomic write of the .mfdb132.bejson package failed
E_DIAGRAMS_IMPORT_FAILED            = 429  # Unchunk of an .mfdb132.bejson package failed
E_DIAGRAMS_NOT_A_DIAGRAM_PACKAGE    = 430  # Package is valid MFDB-132 but not tagged Diagram_Schema
E_DIAGRAMS_AI_EMPTY_PROMPT          = 431  # Prompt supplied to AI diagram generator was empty or whitespace
E_DIAGRAMS_AI_BAD_RESPONSE          = 432  # AI provider response could not be parsed as valid JSON plan
E_DIAGRAMS_AI_INVALID_PLAN          = 433  # AI generated plan failed structural/schema validation
E_DIAGRAMS_AI_PROVIDER_ERROR        = 434  # AI provider API call failed or timed out
E_DIAGRAMS_AI_SEMANTIC_INVALID      = 435  # Plan is structurally sound but fails post-reception semantic checks
E_DIAGRAMS_VALIDATION_FAILED        = 436  # General diagram model or database validation failure
E_DIAGRAMS_CIRCULAR_HIERARCHY       = 437  # Circular parent hierarchy detected in Board shape_parent_fk chain
E_DIAGRAMS_SHAPE_NOT_FOUND          = 438  # Referenced shape or Shape_<id> private entity not found
E_DIAGRAMS_CONNECTOR_NOT_FOUND      = 439  # Referenced connector record not found
E_DIAGRAMS_TERRITORY_NOT_FOUND      = 440  # Referenced territory record not found
E_DIAGRAMS_DUPLICATE_ID             = 441  # Duplicate shape_id, conn_id, or terr_id detected
E_DIAGRAMS_INVALID_COORDINATES      = 442  # Non-numeric or out-of-range spatial coordinates (cx, cy, size)
E_DIAGRAMS_EXPORT_FAILED            = 443  # Diagram package export or serialization failed
E_DIAGRAMS_AI_CALL_FAILED           = 444  # AI model invocation failed
E_DIAGRAMS_AI_SCAFFOLD_FAILED       = 445  # AI spatial layout scaffolding failed
E_DIAGRAMS_AI_PARSE_FAILED          = 446  # AI response XML/JSON parsing failed
E_DIAGRAMS_CONNECTOR_SELF_REFERENCE = 447  # Connector from_fk and to_fk reference the same shape_id
E_DIAGRAMS_AI_DANGLING_PARENT       = 448  # AI build plan shape references an unknown parentTempId
E_DIAGRAMS_AI_DANGLING_CONNECTOR    = 449  # AI build plan connector references an unknown endpoint tempId

# Aliases for v3 Diagrammer compatibility
E_DIAGRAMS_HIERARCHY_CYCLE          = E_DIAGRAMS_CIRCULAR_HIERARCHY
E_DIAGRAMS_PARENT_NOT_FOUND         = E_DIAGRAMS_FK_UNRESOLVED
E_DIAGRAMS_CONNECTOR_DANGLING       = E_DIAGRAMS_FK_UNRESOLVED
E_DIAGRAMS_INVALID_NODE_ID          = E_DIAGRAMS_DUPLICATE_ID
E_DIAGRAMS_INVALID_SHAPE_KIND       = E_DIAGRAMS_VALIDATION_FAILED
E_DIAGRAMS_CONNECTOR_INVALID_FLOW   = E_DIAGRAMS_VALIDATION_FAILED
E_DIAGRAMS_TERRITORY_INVALID_KIND   = E_DIAGRAMS_VALIDATION_FAILED
E_DIAGRAMS_TERRITORY_INVALID_SIZE   = E_DIAGRAMS_VALIDATION_FAILED
E_DIAGRAMS_AI_EMPTY_RESPONSE        = E_DIAGRAMS_AI_BAD_RESPONSE
E_DIAGRAMS_AI_NO_VALID_KEYS         = E_DIAGRAMS_AI_PROVIDER_ERROR

DIAGRAMS_ERROR_CODES: Dict[str, int] = {
    "E_DIAGRAMS_NOT_MFDB132_PACKAGE":      E_DIAGRAMS_NOT_MFDB132_PACKAGE,
    "E_DIAGRAMS_MFDB132_INVALID":          E_DIAGRAMS_MFDB132_INVALID,
    "E_DIAGRAMS_MFDB_DATABASE_INVALID":    E_DIAGRAMS_MFDB_DATABASE_INVALID,
    "E_DIAGRAMS_MISSING_ENTITY":           E_DIAGRAMS_MISSING_ENTITY,
    "E_DIAGRAMS_MISSING_FIELD":            E_DIAGRAMS_MISSING_FIELD,
    "E_DIAGRAMS_FK_UNRESOLVED":            E_DIAGRAMS_FK_UNRESOLVED,
    "E_DIAGRAMS_INVALID_SIZE_CLASS":       E_DIAGRAMS_INVALID_SIZE_CLASS,
    "E_DIAGRAMS_INVALID_ROOT":             E_DIAGRAMS_INVALID_ROOT,
    "E_DIAGRAMS_WRITE_FAILED":             E_DIAGRAMS_WRITE_FAILED,
    "E_DIAGRAMS_IMPORT_FAILED":            E_DIAGRAMS_IMPORT_FAILED,
    "E_DIAGRAMS_NOT_A_DIAGRAM_PACKAGE":    E_DIAGRAMS_NOT_A_DIAGRAM_PACKAGE,
    "E_DIAGRAMS_AI_EMPTY_PROMPT":          E_DIAGRAMS_AI_EMPTY_PROMPT,
    "E_DIAGRAMS_AI_BAD_RESPONSE":          E_DIAGRAMS_AI_BAD_RESPONSE,
    "E_DIAGRAMS_AI_INVALID_PLAN":          E_DIAGRAMS_AI_INVALID_PLAN,
    "E_DIAGRAMS_AI_PROVIDER_ERROR":        E_DIAGRAMS_AI_PROVIDER_ERROR,
    "E_DIAGRAMS_AI_SEMANTIC_INVALID":      E_DIAGRAMS_AI_SEMANTIC_INVALID,
    "E_DIAGRAMS_VALIDATION_FAILED":        E_DIAGRAMS_VALIDATION_FAILED,
    "E_DIAGRAMS_CIRCULAR_HIERARCHY":       E_DIAGRAMS_CIRCULAR_HIERARCHY,
    "E_DIAGRAMS_SHAPE_NOT_FOUND":          E_DIAGRAMS_SHAPE_NOT_FOUND,
    "E_DIAGRAMS_CONNECTOR_NOT_FOUND":      E_DIAGRAMS_CONNECTOR_NOT_FOUND,
    "E_DIAGRAMS_TERRITORY_NOT_FOUND":      E_DIAGRAMS_TERRITORY_NOT_FOUND,
    "E_DIAGRAMS_DUPLICATE_ID":             E_DIAGRAMS_DUPLICATE_ID,
    "E_DIAGRAMS_INVALID_COORDINATES":      E_DIAGRAMS_INVALID_COORDINATES,
    "E_DIAGRAMS_EXPORT_FAILED":            E_DIAGRAMS_EXPORT_FAILED,
    "E_DIAGRAMS_AI_CALL_FAILED":           E_DIAGRAMS_AI_CALL_FAILED,
    "E_DIAGRAMS_AI_SCAFFOLD_FAILED":       E_DIAGRAMS_AI_SCAFFOLD_FAILED,
    "E_DIAGRAMS_AI_PARSE_FAILED":          E_DIAGRAMS_AI_PARSE_FAILED,
    "E_DIAGRAMS_CONNECTOR_SELF_REFERENCE": E_DIAGRAMS_CONNECTOR_SELF_REFERENCE,
    "E_DIAGRAMS_AI_DANGLING_PARENT":       E_DIAGRAMS_AI_DANGLING_PARENT,
    "E_DIAGRAMS_AI_DANGLING_CONNECTOR":    E_DIAGRAMS_AI_DANGLING_CONNECTOR,
}


class DiagramsError(Exception):
    def __init__(self, message: str, code: int = E_DIAGRAMS_VALIDATION_FAILED, context: Optional[Any] = None):
        super().__init__(message)
        self.code = code
        self.context = context if context is not None else {}


class AIBuildError(DiagramsError):
    def __init__(self, message: str, code: int = E_DIAGRAMS_AI_CALL_FAILED, context: Optional[Any] = None):
        super().__init__(message, code, context)