"""
Library:         lib_bejson_HTML_bejson_diagram_validator.py
Family:          HTML
Module Purpose:  Implements runtime functionality and logic for lib_bejson_HTML_bejson_diagram_validator.py.
Architecture:    MFDB provides multi-file database federation coordinating a 104a central manifest (104a.mfdb.bejson) with dense 104 entity tables, supporting atomic transaction locks and cross-disk relational foreign keys.
Version:         1.0.1
Release_Version: 300
Date:            2026-07-18
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   3e8b1c6f-9a4d-4e2c-b5f7-1d3a6c9e2b80
"""

import json
from pathlib import Path

import lib_bejson_HTML_bejson_diagram_core as _core

# DEAD CODE REMOVED (2026-07-18): E_DIAGRAM_RELATIONAL_ERROR (100) and
# E_DIAGRAM_INVALID_ANCHOR (101) were defined here but never raised or
# referenced anywhere in the codebase (verified via full-tree grep). The
# retired anchor system they described no longer exists. Logged in
# BEJSON/MFDB/data/library_changes.bejson.


class DiagramValidationError(ValueError):
    """Raised when a diagram fails structural validation. Carries the full
    list of issues found (not just the first one) via .issues."""
    def __init__(self, issues):
        self.issues = issues
        super().__init__(f"{len(issues)} diagram validation issue(s): " + "; ".join(issues))


def bejson_validator_diagram_validate_string(json_string: str) -> bool:
    """
    Validates a diagram JSON string under the CURRENT schema.

    Unlike the function this replaces, this actually checks structure:
    duplicate shape ids, dangling connector/parentId references, parentId
    cycles, self-loop connectors, duplicate connector pairs, unknown
    sizeClass/kind/flow enum values, and shape/territory overlap.

    Raises DiagramValidationError (with the full issue list on .issues) if
    anything is wrong, or NotADiagramError if the input isn't diagram-shaped
    at all. Returns True only if the diagram is actually clean — this
    function can no longer return True unconditionally.
    """
    data = json.loads(json_string)
    if not isinstance(data, dict) or not any(k in data for k in ("shapes", "connectors", "territories")):
        raise _core.NotADiagramError(
            "Input has none of 'shapes', 'connectors', or 'territories' — not diagram-shaped data."
        )
    diagram = _core._normalize(data)
    issues = _core.validate_diagram(diagram)
    if issues:
        raise DiagramValidationError(issues)
    return True


def bejson_validator_diagram_validate_file(file_path: str) -> bool:
    text = Path(file_path).read_text(encoding="utf-8")
    return bejson_validator_diagram_validate_string(text)


def bejson_validator_diagram_get_issues(json_string: str):
    """
    Non-raising variant: returns the list of issues (empty list = clean)
    instead of raising. Useful when the caller wants to report every
    problem at once rather than handling an exception.
    """
    data = json.loads(json_string)
    if not isinstance(data, dict) or not any(k in data for k in ("shapes", "connectors", "territories")):
        raise _core.NotADiagramError(
            "Input has none of 'shapes', 'connectors', or 'territories' — not diagram-shaped data."
        )
    diagram = _core._normalize(data)
    return _core.validate_diagram(diagram)