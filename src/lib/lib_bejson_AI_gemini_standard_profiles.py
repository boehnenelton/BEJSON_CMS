"""
Library:        lib_bejson_AI_gemini_standard_profiles.py
Family:         AI
Description:    AI Profile manager for the BEJSON ecosystem.
                Implements the canonical AI_Profile 104a schema using
                This_Case_Fields (no CrammedFieldNames). All reads and
                writes go through the Field Map Cache; positional
                look-ups are strictly prohibited.
Version:        4.0.0
Date:           2026-10-18
Author:         Elton Boehnen
Contact:        boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  e7681929-655b-4bd8-9995-f4a67a4bc582

Changelog:
  4.0.0 (2026-10-18) -- BREAKING (API only; no profile file needs migration).
          Removed the optional "Mode" field and its API (PROFILE_MODE_FIELD,
          gemini_profiles_get_mode(), gemini_profiles_set_mode(), the Mode=
          kwarg). A Mode hint needed a separate mode library AND parser
          library per profile. Replaced by three OPTIONAL string columns that
          make a profile self-contained:
            Parser_Language -- "python" | "javascript"
            Parser          -- source of parse(raw_text) -> JSON value
            Renderer        -- vanilla JS source of render(parsed, container)
          Contract names (parse / render) are fixed so every client agrees.
          All three are appended at the END of Fields on first use (positional
          integrity, existing rows null-padded, Field Map Cache rebuilt).
          A legacy "Mode" column in an existing file is tolerated (must still
          be "string") and ignored; it is never written.
          New API: gemini_profiles_get_parser/set_parser,
          gemini_profiles_get_renderer/set_renderer,
          gemini_profiles_validate_embedded() (list of problems),
          gemini_profiles_embedded_fingerprint() (SHA-256),
          gemini_profiles_load_embedded() (what a client calls on profile
          load: validate + fingerprint + approval status),
          gemini_profiles_run_parser() and gemini_profiles_build_sandbox()
          (both refuse unless the fingerprint is in the caller's approved set).
          gemini_profiles_validate() now also runs the static code checks, so a
          profile whose embedded code is malformed is invalid. Execution,
          validation rules and the browser sandbox live in
          lib_bejson_AI_profile_parser_runtime.
          Security note: embedded code is executable content. Profiles that
          were generated or imported must stay unapproved until a human has
          read the code and pinned its fingerprint.
  3.1.0 (2026-10-02) -- Added the OPTIONAL "Mode" profile field (string).
          Mode is a free-form hint a custom client may read to switch on a
          feature for that profile (e.g. "structured_output",
          "profile_generator"); the library assigns it no meaning and
          enforces no value list, and a client is free to ignore it.
          Completely optional: gemini_profiles_validate() accepts a profile
          with or without a Mode column, and a null/blank Mode is the same
          as no Mode. If a Mode column IS present it must be declared
          "string". The canonical PROFILE_FIELDS list and the required-
          field set are UNCHANGED, so every existing profile stays valid
          and no existing file needs migration. New: PROFILE_MODE_FIELD,
          OPTIONAL_PROFILE_FIELDS, gemini_profiles_get_mode(),
          gemini_profiles_set_mode(); gemini_profiles_create() accepts an
          optional Mode= kwarg (column is added only when a Mode is given).
          set_mode() appends the column at the END of Fields (positional
          integrity), null-pads existing rows, and drops the stale
          in-document field-map cache so the Field Map Cache is rebuilt.
          Also fixed: gemini_profiles_validate() now ignores the runtime-
          only _bejson_field_map cache key that Core injects into a doc
          after any field-map lookup (previously a profile that had been
          read via gemini_profiles_get_value() failed validation in
          memory, because 104 forbids custom top-level keys).
  3.0.0 (2026-09-04) -- Renamed from lib_bejson_AI_bejson_gemprofiles.py.
          Migrated all field names to This_Case convention
          (System_Instruction, Forbidden_Topics, Avatar_Source_Url,
          Max_Response_Tokens, Emotional_Expression_Enabled,
          Emotional_Expression_Intensity, Google_Search_Enabled,
          Code_Interpreter_Enabled, Ephemeral_Memory, Code_Parsing_Mode,
          Code_Parsing_Languages, Code_Parsing_Structure_Validation,
          Code_Parsing_Version_Control, Thinking_Supported).
          Eliminated legacy fallback positional constant _PROFILES_LEGACY.
          All operations now exclusively use bejson_core_get_field_map
          via the mandatory Field Map Cache.
  2.1.1 -- AI-family audit fix: added missing module-level VERSION var.
  2.1.0 -- Initial creation.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import sys
import os

# ── Sibling resolution ────────────────────────────────────────────────────────
_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_CORE_DIR = os.path.join(os.path.dirname(_LIB_DIR), "Core")
for _p in (_LIB_DIR, _CORE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib_bejson_Core_bejson_core import (
    bejson_core_get_field_index,
    bejson_core_get_field_map,
    bejson_core_atomic_write,
)
import lib_bejson_Core_bejson_validator
import lib_bejson_AI_profile_parser_runtime as _rt

VERSION = "4.0.0"

logger = logging.getLogger(__name__)

# ── Canonical This_Case field definitions ─────────────────────────────────────
# Field Map Cache is mandatory for all reads/writes; these definitions serve
# as the authoritative schema reference and are used when creating new docs.

PROFILE_FIELDS: List[Dict[str, str]] = [
    {"name": "Record_Type_Parent",             "type": "string"},
    {"name": "Name",                            "type": "string"},
    {"name": "Archetype",                       "type": "string"},
    {"name": "Persona",                         "type": "string"},
    {"name": "System_Instruction",              "type": "string"},
    {"name": "Forbidden_Topics",               "type": "array"},
    {"name": "Avatar_Type",                    "type": "string"},
    {"name": "Avatar_Source_Url",              "type": "string"},
    {"name": "Avatar_Data",                    "type": "string"},
    {"name": "Max_Response_Tokens",            "type": "integer"},
    {"name": "Creativity",                     "type": "number"},
    {"name": "Tone",                           "type": "array"},
    {"name": "Formality",                      "type": "string"},
    {"name": "Verbosity",                      "type": "string"},
    {"name": "Emotional_Expression_Enabled",   "type": "boolean"},
    {"name": "Emotional_Expression_Intensity", "type": "number"},
    {"name": "Google_Search_Enabled",          "type": "boolean"},
    {"name": "Code_Interpreter_Enabled",       "type": "boolean"},
    {"name": "Ephemeral_Memory",               "type": "boolean"},
    {"name": "Code_Parsing_Mode",              "type": "string"},
    {"name": "Code_Parsing_Languages",         "type": "array"},
    {"name": "Code_Parsing_Structure_Validation", "type": "boolean"},
    {"name": "Code_Parsing_Version_Control",   "type": "boolean"},
    {"name": "Thinking_Supported",             "type": "boolean"},
]

_REQUIRED_FIELD_NAMES = {f["name"] for f in PROFILE_FIELDS}

# ── Optional fields ───────────────────────────────────────────────────────────
# Optional fields are NOT part of PROFILE_FIELDS / the required set. A profile
# is valid with or without them; when present they are appended at the END of
# Fields and must be declared "string". Together they make a profile
# self-contained: the Parser turns raw model output into a value, the Renderer
# draws that value. Contract names are fixed (see the runtime library):
#   parse(raw_text) -> JSON value        render(parsed, container)
PROFILE_PARSER_LANGUAGE_FIELD = "Parser_Language"
PROFILE_PARSER_FIELD = "Parser"
PROFILE_RENDERER_FIELD = "Renderer"
# Pre-4.0.0 hint column. Tolerated when present in an old file, never written.
LEGACY_MODE_FIELD = "Mode"

OPTIONAL_PROFILE_FIELDS: List[Dict[str, str]] = [
    {"name": PROFILE_PARSER_LANGUAGE_FIELD, "type": "string"},
    {"name": PROFILE_PARSER_FIELD,          "type": "string"},
    {"name": PROFILE_RENDERER_FIELD,        "type": "string"},
]
_OPTIONAL_SPEC = {f["name"]: f for f in OPTIONAL_PROFILE_FIELDS}
_TOLERATED_STRING_FIELDS = OPTIONAL_PROFILE_FIELDS + [{"name": LEGACY_MODE_FIELD, "type": "string"}]


# ── Public API ────────────────────────────────────────────────────────────────

def gemini_profiles_validate(doc: Dict[str, Any]) -> bool:
    """
    Validates that *doc* conforms to the AI_Profile schema.
    Returns True only if:
      1. The document passes the Core BEJSON structural validator.
      2. Every canonical This_Case field name is present.
      3. Records_Type contains "AI_Profile".
      4. Any optional column present (Parser_Language, Parser, Renderer, or
         the legacy Mode) is declared "string". Missing columns and null/blank
         values are fine.
      5. Every record's embedded code passes the static checks in
         gemini_profiles_validate_embedded() (structure only -- nothing is
         executed, and no approval is needed to validate).
    """
    try:
        # _bejson_field_map is the Core Field Map Cache injected into the doc
        # at runtime by any get_value()/set_*() call -- it is not file
        # content, and a 104 doc may not carry custom top-level keys, so it
        # is excluded before structural validation.
        lib_bejson_Core_bejson_validator.bejson_validator_validate_string(
            json.dumps({k: v for k, v in doc.items() if k != "_bejson_field_map"})
        )
        fields = doc.get("Fields", [])
        field_names = {f["name"] for f in fields}
        missing = _REQUIRED_FIELD_NAMES - field_names
        if missing:
            logger.debug("Profile validation: missing fields: %s", missing)
            return False
        if "AI_Profile" not in doc.get("Records_Type", []):
            logger.debug("Profile validation: Records_Type does not contain AI_Profile")
            return False
        # Optional fields: absent is valid; present must have the right type.
        for opt in _TOLERATED_STRING_FIELDS:
            for f in fields:
                if f["name"] == opt["name"] and f.get("type") != opt["type"]:
                    logger.debug(
                        "Profile validation: optional field %s declared %s, expected %s",
                        opt["name"], f.get("type"), opt["type"],
                    )
                    return False
        for record_index in range(len(doc.get("Values", []))):
            problems = gemini_profiles_validate_embedded(doc, record_index)
            if problems:
                logger.debug("Profile validation: embedded code: %s", problems)
                return False
        return True
    except Exception as exc:
        logger.debug("Profile validation exception: %s", exc)
        return False


def gemini_profiles_create(
    name: str,
    archetype: str,
    persona: str,
    instruction: str,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Creates a new AI_Profile BEJSON document with This_Case fields.
    All optional parameters use keyword args keyed by This_Case field name.
    Parser_Language / Parser / Renderer (optional): given as non-blank strings
    they are validated and appended to the end of Fields; a profile created
    without them has no such columns at all. Raises ValueError if the embedded
    code fails static validation.
    """
    values = [
        "AI_Profile",
        name,
        archetype,
        persona,
        instruction,
        kwargs.get("Forbidden_Topics", []),
        kwargs.get("Avatar_Type", "Emoji"),
        kwargs.get("Avatar_Source_Url", ""),
        kwargs.get("Avatar_Data", "🤖"),
        kwargs.get("Max_Response_Tokens", 16384),
        kwargs.get("Creativity", 0.7),
        kwargs.get("Tone", ["Professional", "Helpful"]),
        kwargs.get("Formality", "Formal"),
        kwargs.get("Verbosity", "Balanced"),
        kwargs.get("Emotional_Expression_Enabled", False),
        kwargs.get("Emotional_Expression_Intensity", 0.0),
        kwargs.get("Google_Search_Enabled", True),
        kwargs.get("Code_Interpreter_Enabled", True),
        kwargs.get("Ephemeral_Memory", True),
        kwargs.get("Code_Parsing_Mode", "complete"),
        kwargs.get("Code_Parsing_Languages", []),
        kwargs.get("Code_Parsing_Structure_Validation", True),
        kwargs.get("Code_Parsing_Version_Control", False),
        kwargs.get("Thinking_Supported", True),
    ]

    doc = {
        "Format": "BEJSON",
        "Format_Version": "104",
        "Format_Creator": "Elton Boehnen",
        "Records_Type": ["AI_Profile"],
        # Copy so appending optional fields never mutates PROFILE_FIELDS.
        "Fields": [dict(f) for f in PROFILE_FIELDS],
        "Values": [values],
    }
    parser = kwargs.get(PROFILE_PARSER_FIELD)
    if parser is not None:
        if not gemini_profiles_set_parser(doc, kwargs.get(PROFILE_PARSER_LANGUAGE_FIELD), parser):
            raise ValueError("Parser rejected: " + "; ".join(
                _rt.runtime_validate_parser(kwargs.get(PROFILE_PARSER_LANGUAGE_FIELD), parser)))
    renderer = kwargs.get(PROFILE_RENDERER_FIELD)
    if renderer is not None:
        if not gemini_profiles_set_renderer(doc, renderer):
            raise ValueError("Renderer rejected: " + "; ".join(_rt.runtime_validate_renderer(renderer)))
    return doc


# ── Optional string column helpers (Field Map Cache only) ─────────────────────

def _get_optional_string(profile: Dict[str, Any], field_name: str, record_index: int) -> Optional[str]:
    value = gemini_profiles_get_value(profile, field_name, record_index)
    if isinstance(value, str) and value.strip():
        return value
    return None


def _set_optional_string(
    profile: Dict[str, Any], field_name: str, value: Optional[str], record_index: int
) -> bool:
    """Stores *value* (None/blank clears). Appends the column at the END of
    Fields when it is missing and something is being stored; clearing a
    column that does not exist adds nothing."""
    values = profile.get("Values", [])
    if record_index >= len(values):
        logger.warning("%s: record %d out of range", field_name, record_index)
        return False
    clean = value if isinstance(value, str) and value.strip() else None
    fm = gemini_profiles_get_field_map(profile)
    if field_name not in fm:
        if clean is None:
            return True
        profile.setdefault("Fields", []).append(dict(_OPTIONAL_SPEC[field_name]))
        for row in values:
            row.append(None)
        # The Core field-map cache is injected into the doc; Fields just
        # changed, so drop the stale copy and rebuild it.
        profile.pop("_bejson_field_map", None)
        bejson_core_get_field_map(profile)
    return gemini_profiles_update_value(profile, field_name, clean, record_index)


def gemini_profiles_get_parser(
    profile: Dict[str, Any], record_index: int = 0
) -> Optional[Dict[str, str]]:
    """Returns {"language": "python"|"javascript", "code": <source>} or None
    when the profile has no (valid-language) Parser. Never raises."""
    code = _get_optional_string(profile, PROFILE_PARSER_FIELD, record_index)
    if code is None:
        return None
    language = _rt.runtime_normalize_language(
        _get_optional_string(profile, PROFILE_PARSER_LANGUAGE_FIELD, record_index))
    if language is None:
        return None
    return {"language": language, "code": code}


def gemini_profiles_set_parser(
    profile: Dict[str, Any], language: Optional[str], code: Optional[str], record_index: int = 0
) -> bool:
    """
    Sets the embedded parser, or clears it when *code* is None/blank (both
    Parser and Parser_Language are cleared). The code must pass static
    validation for *language*; otherwise nothing is written, the problems are
    logged, and False is returned.
    """
    if code is None or (isinstance(code, str) and not code.strip()):
        ok = _set_optional_string(profile, PROFILE_PARSER_FIELD, None, record_index)
        return _set_optional_string(profile, PROFILE_PARSER_LANGUAGE_FIELD, None, record_index) and ok
    lang = _rt.runtime_normalize_language(language)
    problems = _rt.runtime_validate_parser(lang or language, code)
    if problems:
        logger.warning("gemini_profiles_set_parser rejected: %s", "; ".join(problems))
        return False
    ok = _set_optional_string(profile, PROFILE_PARSER_LANGUAGE_FIELD, lang, record_index)
    return _set_optional_string(profile, PROFILE_PARSER_FIELD, code, record_index) and ok


def gemini_profiles_get_renderer(profile: Dict[str, Any], record_index: int = 0) -> Optional[str]:
    """Returns the embedded Renderer source, or None. Never raises."""
    return _get_optional_string(profile, PROFILE_RENDERER_FIELD, record_index)


def gemini_profiles_set_renderer(
    profile: Dict[str, Any], code: Optional[str], record_index: int = 0
) -> bool:
    """Sets (or clears, when None/blank) the embedded Renderer. Rejected with
    False -- and nothing written -- if it fails static validation."""
    if code is None or (isinstance(code, str) and not code.strip()):
        return _set_optional_string(profile, PROFILE_RENDERER_FIELD, None, record_index)
    problems = _rt.runtime_validate_renderer(code)
    if problems:
        logger.warning("gemini_profiles_set_renderer rejected: %s", "; ".join(problems))
        return False
    return _set_optional_string(profile, PROFILE_RENDERER_FIELD, code, record_index)


# ── Embedded code: validate / fingerprint / load / run / sandbox ──────────────

def gemini_profiles_validate_embedded(
    profile: Dict[str, Any], record_index: int = 0, syntax_check_js: bool = False
) -> List[str]:
    """
    Static problems with the profile's embedded code (empty list = fine, which
    includes "no embedded code"). Nothing is executed. A Parser without a
    usable Parser_Language is a problem. syntax_check_js=True additionally
    runs `node --check` on JavaScript when node is installed.
    """
    problems: List[str] = []
    code = _get_optional_string(profile, PROFILE_PARSER_FIELD, record_index)
    lang_raw = _get_optional_string(profile, PROFILE_PARSER_LANGUAGE_FIELD, record_index)
    if code is not None:
        problems.extend(_rt.runtime_validate_parser(lang_raw, code))
        if (not problems and syntax_check_js
                and _rt.runtime_normalize_language(lang_raw) == "javascript"):
            err = _rt.runtime_javascript_syntax_error(code)
            if err:
                problems.append(f"JavaScript parser: {err}")
    elif lang_raw is not None:
        problems.append("Parser_Language is set but Parser is empty")
    renderer = _get_optional_string(profile, PROFILE_RENDERER_FIELD, record_index)
    if renderer is not None:
        problems.extend(_rt.runtime_validate_renderer(renderer))
        if not problems and syntax_check_js:
            err = _rt.runtime_javascript_syntax_error(renderer)
            if err:
                problems.append(f"Renderer: {err}")
    return problems


def gemini_profiles_embedded_fingerprint(
    profile: Dict[str, Any], record_index: int = 0
) -> Optional[str]:
    """SHA-256 over (language, parser, renderer), or None when the record has
    no embedded code. Pin this in an approved set to allow the code to run;
    editing any of the three changes it."""
    parser = gemini_profiles_get_parser(profile, record_index)
    renderer = gemini_profiles_get_renderer(profile, record_index)
    if parser is None and renderer is None:
        return None
    return _rt.runtime_fingerprint(
        parser["language"] if parser else None, parser["code"] if parser else None, renderer)


def gemini_profiles_load_embedded(
    profile: Dict[str, Any],
    approved_fingerprints: Iterable[str] = (),
    record_index: int = 0,
    syntax_check_js: bool = True,
) -> Dict[str, Any]:
    """
    What a client calls when a profile is loaded. Validates the embedded code
    and reports its approval status; executes nothing.
    Returns {"success": bool, "has_embedded": bool, "parser": {...}|None,
             "renderer": str|None, "fingerprint": str|None,
             "approved": bool, "errors": [str]}.
    success is False when validation found problems; approved is True only
    when the fingerprint is in *approved_fingerprints*.
    """
    errors = gemini_profiles_validate_embedded(profile, record_index, syntax_check_js)
    fingerprint = gemini_profiles_embedded_fingerprint(profile, record_index)
    return {
        "success": not errors,
        "has_embedded": fingerprint is not None,
        "parser": gemini_profiles_get_parser(profile, record_index),
        "renderer": gemini_profiles_get_renderer(profile, record_index),
        "fingerprint": fingerprint,
        "approved": fingerprint is not None and fingerprint in set(approved_fingerprints),
        "errors": errors,
    }


def _gate(
    profile: Dict[str, Any], approved_fingerprints: Iterable[str], record_index: int
) -> Optional[Dict[str, Any]]:
    """Returns a refusal dict when the embedded code may not run, else None."""
    loaded = gemini_profiles_load_embedded(
        profile, approved_fingerprints, record_index, syntax_check_js=False)
    if not loaded["has_embedded"]:
        return {"success": False, "reason": "profile has no embedded parser/renderer", "fingerprint": None}
    if not loaded["success"]:
        return {"success": False, "reason": "; ".join(loaded["errors"]), "fingerprint": loaded["fingerprint"]}
    if not loaded["approved"]:
        return {"success": False, "reason": "embedded code is not approved",
                "fingerprint": loaded["fingerprint"]}
    return None


def gemini_profiles_run_parser(
    profile: Dict[str, Any],
    raw_text: str,
    approved_fingerprints: Iterable[str],
    record_index: int = 0,
    timeout: float = _rt.DEFAULT_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """
    Runs the profile's embedded parser on *raw_text* (python: isolated
    subprocess; javascript: node vm subprocess). Refuses unless the profile's
    fingerprint is in *approved_fingerprints*.
    Returns {"success": bool, "result": <json value>, "reason": str, "fingerprint": str|None}.
    """
    refusal = _gate(profile, approved_fingerprints, record_index)
    if refusal:
        return refusal
    parser = gemini_profiles_get_parser(profile, record_index)
    fingerprint = gemini_profiles_embedded_fingerprint(profile, record_index)
    if parser is None:
        return {"success": False, "reason": "profile has no embedded parser", "fingerprint": fingerprint}
    outcome = _rt.runtime_run_parser(parser["language"], parser["code"], raw_text, timeout)
    outcome["fingerprint"] = fingerprint
    return outcome


def gemini_profiles_build_sandbox(
    profile: Dict[str, Any],
    approved_fingerprints: Iterable[str],
    record_index: int = 0,
) -> Dict[str, Any]:
    """
    Builds the sandbox iframe srcdoc for the profile's Parser (if JavaScript)
    and Renderer. Refuses unless approved. Returns {"success": bool,
    "srcdoc": str, "iframe_attributes": 'sandbox="allow-scripts"',
    "reason": str, "fingerprint": str|None}. The caller must create the
    iframe with exactly those attributes; message protocol is documented on
    lib_bejson_AI_profile_parser_runtime.sandbox_build_srcdoc().
    """
    refusal = _gate(profile, approved_fingerprints, record_index)
    if refusal:
        refusal.update({"srcdoc": "", "iframe_attributes": _rt.SANDBOX_IFRAME_ATTRIBUTES})
        return refusal
    parser = gemini_profiles_get_parser(profile, record_index)
    fingerprint = gemini_profiles_embedded_fingerprint(profile, record_index)
    try:
        srcdoc = _rt.sandbox_build_srcdoc(
            parser["language"] if parser else None,
            parser["code"] if parser else None,
            gemini_profiles_get_renderer(profile, record_index),
        )
    except ValueError as exc:
        return {"success": False, "reason": str(exc), "srcdoc": "",
                "iframe_attributes": _rt.SANDBOX_IFRAME_ATTRIBUTES, "fingerprint": fingerprint}
    return {"success": True, "reason": "", "srcdoc": srcdoc,
            "iframe_attributes": _rt.SANDBOX_IFRAME_ATTRIBUTES, "fingerprint": fingerprint}


def gemini_profiles_save(profile: Dict[str, Any], path: str) -> None:
    """
    Atomically writes *profile* to *path* via bejson_core_atomic_write
    (.tmp → os.replace()) to prevent truncation on crash or OOM kill.

    Raises IOError if the write fails.
    """
    if not bejson_core_atomic_write(path, profile):
        raise IOError(f"Atomic write failed for profile: {path}")
    logger.debug("Profile saved: %s", path)


def gemini_profiles_get_field_map(profile: Dict[str, Any]) -> Dict[str, int]:
    """
    Returns the mandatory Field Map Cache (name → index) for *profile*.
    All field reads/writes must go through this map; positional lookups
    are strictly prohibited.
    """
    return bejson_core_get_field_map(profile)


def gemini_profiles_get_value(
    profile: Dict[str, Any], field_name: str, record_index: int = 0
) -> Any:
    """Queries a specific field value from *profile* via Field Map Cache."""
    fm = gemini_profiles_get_field_map(profile)
    idx = fm.get(field_name, -1)
    values = profile.get("Values", [])
    if idx != -1 and record_index < len(values) and idx < len(values[record_index]):
        return values[record_index][idx]
    return None


def gemini_profiles_update_value(
    profile: Dict[str, Any],
    field_name: str,
    new_value: Any,
    record_index: int = 0,
) -> bool:
    """
    Updates *field_name* in *profile* via Field Map Cache.
    Returns True on success, False if the field or record was not found.
    """
    fm = gemini_profiles_get_field_map(profile)
    idx = fm.get(field_name, -1)
    values = profile.get("Values", [])
    if idx != -1 and record_index < len(values) and idx < len(values[record_index]):
        values[record_index][idx] = new_value
        return True
    logger.warning(
        "gemini_profiles_update_value: field '%s' not found or out of range", field_name
    )
    return False


def gemini_profiles_query_by_name(
    profiles_dir: str, profile_name: str
) -> Optional[Dict[str, Any]]:
    """
    Scans *profiles_dir* for a .bejson file whose 'Name' field matches
    *profile_name* (case-sensitive). Returns the parsed document, or None.
    """
    path = Path(profiles_dir)
    for file in path.glob("*.bejson"):
        try:
            with open(file, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
            if gemini_profiles_get_value(doc, "Name") == profile_name:
                return doc
        except Exception as exc:
            logger.debug("gemini_profiles_query_by_name: skipping %s — %s", file, exc)
    return None


def gemini_profiles_load_config(config_path: str) -> Dict[str, Any]:
    """
    Loads and returns the Profile_Config BEJSON document at *config_path*.
    Returns an empty dict on failure.
    """
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logger.warning("gemini_profiles_load_config: could not load %s — %s", config_path, exc)
        return {}


def gemini_profiles_get_config_value(
    config_doc: Dict[str, Any], key: str
) -> Optional[str]:
    """
    Reads a value from the Profile_Config document by Config_Key via Field
    Map Cache. Returns None if the key is not found.
    """
    fm = bejson_core_get_field_map(config_doc)
    key_idx = fm.get("Config_Key", -1)
    val_idx = fm.get("Config_Value", -1)
    if key_idx == -1 or val_idx == -1:
        return None
    for row in config_doc.get("Values", []):
        if len(row) > max(key_idx, val_idx) and row[key_idx] == key:
            return row[val_idx]
    return None


def gemini_profiles_get_selected(config_path: str) -> str:
    """
    Convenience wrapper: returns the currently selected profile name from
    the Profile_Config file, defaulting to 'default' on any error.
    """
    doc = gemini_profiles_load_config(config_path)
    return gemini_profiles_get_config_value(doc, "Selected_Profile") or "default"


def gemini_profiles_is_enabled(config_path: str) -> bool:
    """
    Convenience wrapper: returns True if Profiles_Enabled is 'true' in
    the Profile_Config file.
    """
    doc = gemini_profiles_load_config(config_path)
    val = gemini_profiles_get_config_value(doc, "Profiles_Enabled") or "false"
    return val.strip().lower() == "true"
