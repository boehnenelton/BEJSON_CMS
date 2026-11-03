"""
Library:         lib_bejson_AI_gemini_md_gate.py
Family:          AI
Module Purpose:  Boolean gate, settings and file discovery for the user's GEMINI.md policy file (default ~/.gemini/GEMINI.md): the gate is "enabled AND the file exists".
Architecture:    BEJSON 104a ScriptConfig file (gemini_md_gate.104a.bejson, Field Map Cache, atomic writes) in the AI config directory. No absolute paths: the file is found relative to the user's home directory, or via an optional gemini_md_path setting. Holds three hidden sync_* rows used by lib_bejson_AI_gemini_md_bubble to remember the bubble baseline.
Version:         1.0.0
Release_Version: 300
Date:            2026-10-29
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   8bdf7194-4bda-479a-912e-7eb29f5b2ba8
"""

import json
import logging
import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent
for _candidate in (_LIB_DIR, _LIB_DIR.parent / "Core"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from lib_bejson_Core_bejson_core import bejson_core_atomic_write, bejson_core_get_field_map  # noqa: E402

VERSION = "1.0.0"
RELATIONAL_ID = "8bdf7194-4bda-479a-912e-7eb29f5b2ba8"
_LOGGER = logging.getLogger("gemini_md.gate")

CONFIG_FILENAME = "gemini_md_gate.104a.bejson"
_COL_NAME, _COL_VALUE, _COL_DESC = "setting_name", "setting_value", "description"

# Public settings (name -> (default, description)).
SETTINGS = {
    "gemini_md_enabled": (False, "Boolean gate. true = the GEMINI.md file (when it exists) is injected into the Context Bubble."),
    "gemini_md_budget_pct": (40.0, "Percent of the bubble token budget taken off the top for GEMINI.md while it is active (1-90)."),
    "gemini_md_path": ("", "Optional override: path of the policy file. Empty = look in the home directory (see FILE_CANDIDATES)."),
}
# Hidden sync state written by lib_bejson_AI_gemini_md_bubble (JSON text values).
STATE_KEYS = ("sync_base_pcts", "sync_base_ranks", "sync_applied_pcts")
_STATE_DESC = "Internal: remembered Context Bubble baseline; do not edit."

# Looked up in order under the home directory; the first existing file wins (names compared case-insensitively).
FILE_CANDIDATES = (".gemini/GEMINI.md", ".gemini.md", "GEMINI.md")
MIN_PCT, MAX_PCT = 1.0, 90.0


# Builds the default config document.
def _default_document() -> dict:
    values = [[name, default, description] for name, (default, description) in SETTINGS.items()]
    values += [[key, "", _STATE_DESC] for key in STATE_KEYS]
    return {
        "Format": "BEJSON", "Format_Version": "104a", "Format_Creator": "Elton Boehnen", "Records_Type": ["ScriptConfig"],
        "Fields": [{"name": _COL_NAME, "type": "string"}, {"name": _COL_VALUE, "type": "any"}, {"name": _COL_DESC, "type": "string"}],
        "Values": values,
    }


# Reads the raw document, creating the default file when missing. Unreadable files are reported and replaced by defaults in memory only.
def _load_document(config_dir) -> dict:
    path = Path(config_dir) / CONFIG_FILENAME
    if not path.is_file():
        bejson_core_atomic_write(str(path), _default_document())
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        bejson_core_get_field_map(document)
        return document
    except (OSError, ValueError, TypeError, KeyError) as read_error:
        _LOGGER.error("%s unreadable (%s); using defaults for this call.", path, read_error)
        return _default_document()


# Returns one value from the document, or None when the row is absent.
def _read_row(document: dict, setting_name: str):
    field_map = bejson_core_get_field_map(document)
    for row in document.get("Values", []):
        if str(row[field_map[_COL_NAME]]).strip() == setting_name:
            return row[field_map[_COL_VALUE]]
    return None


# Coerces a value to bool (accepts real bools and the strings true/false/1/0/yes/no/on/off).
def _as_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "1", "yes", "on"):
        return True
    if isinstance(value, str) and value.strip().lower() in ("false", "0", "no", "off"):
        return False
    return default


# Returns the validated public settings as a dict.
def gemini_md_gate_settings(config_dir) -> dict:
    document = _load_document(config_dir)
    enabled = _as_bool(_read_row(document, "gemini_md_enabled"), False)
    try:
        budget_pct = float(_read_row(document, "gemini_md_budget_pct"))
    except (TypeError, ValueError):
        budget_pct = SETTINGS["gemini_md_budget_pct"][0]
    path_text = _read_row(document, "gemini_md_path")
    return {
        "gemini_md_enabled": enabled,
        "gemini_md_budget_pct": min(MAX_PCT, max(MIN_PCT, budget_pct)),
        "gemini_md_path": path_text.strip() if isinstance(path_text, str) else "",
    }


# Writes one setting or hidden state row (creating the row when absent) and returns nothing.
def _write_row(config_dir, name: str, value, description: str) -> None:
    document = _load_document(config_dir)
    field_map = bejson_core_get_field_map(document)
    for row in document["Values"]:
        if str(row[field_map[_COL_NAME]]).strip() == name:
            if row[field_map[_COL_VALUE]] == value:
                return
            row[field_map[_COL_VALUE]] = value
            break
    else:
        document["Values"].append([name, value, description])
    bejson_core_atomic_write(str(Path(config_dir) / CONFIG_FILENAME), document)


# Changes one public setting. Raises KeyError for an unknown name and ValueError for an invalid value. Returns the new settings dict.
def gemini_md_gate_set(config_dir, setting_name: str, value) -> dict:
    if setting_name not in SETTINGS:
        raise KeyError(setting_name)
    if setting_name == "gemini_md_enabled":
        if not isinstance(value, bool):
            raise ValueError("gemini_md_enabled must be true or false")
    elif setting_name == "gemini_md_budget_pct":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not MIN_PCT <= float(value) <= MAX_PCT:
            raise ValueError(f"gemini_md_budget_pct must be a number from {MIN_PCT:g} to {MAX_PCT:g}")
        value = float(value)
    elif not isinstance(value, str):
        raise ValueError("gemini_md_path must be text")
    _write_row(config_dir, setting_name, value, SETTINGS[setting_name][1])
    return gemini_md_gate_settings(config_dir)


# Reads a hidden sync_* state row as a dict (empty when absent or unreadable).
def gemini_md_gate_state_get(config_dir, state_key: str) -> dict:
    raw_text = _read_row(_load_document(config_dir), state_key)
    try:
        parsed = json.loads(raw_text) if isinstance(raw_text, str) and raw_text.strip() else {}
    except ValueError:
        parsed = {}
    return parsed if isinstance(parsed, dict) else {}


# Writes a hidden sync_* state row from a dict.
def gemini_md_gate_state_set(config_dir, state_key: str, state_value: dict) -> None:
    if state_key not in STATE_KEYS:
        raise KeyError(state_key)
    _write_row(config_dir, state_key, json.dumps(state_value, sort_keys=True), _STATE_DESC)


# Finds an existing file named like `relative_text` under `base_dir`, comparing each path part case-insensitively.
def _find_case_insensitive(base_dir: Path, relative_text: str):
    current = base_dir
    for part in relative_text.split("/"):
        try:
            match = next((entry for entry in current.iterdir() if entry.name.casefold() == part.casefold()), None)
        except OSError:
            return None
        if match is None:
            return None
        current = match
    return current if current.is_file() else None


# Returns the policy file Path (override setting first, then FILE_CANDIDATES under home_dir) or None. home_dir defaults to the user's home.
def gemini_md_gate_find_file(settings: dict, home_dir=None):
    override_text = settings.get("gemini_md_path", "")
    if override_text:
        override_path = Path(override_text).expanduser()
        return override_path if override_path.is_file() else None
    base_dir = Path(home_dir) if home_dir else Path.home()
    for candidate in FILE_CANDIDATES:
        found = _find_case_insensitive(base_dir, candidate)
        if found:
            return found
    return None


# Reads the file as UTF-8 text with whitespace trimmed; "" when unreadable.
def gemini_md_gate_read_text(file_path) -> str:
    try:
        return Path(file_path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError as read_error:
        _LOGGER.warning("Could not read %s: %s", file_path, read_error)
        return ""


# One call for the UI and the sync: gate result plus file facts. active = enabled AND file found AND not empty.
def gemini_md_gate_status(config_dir, home_dir=None) -> dict:
    settings = gemini_md_gate_settings(config_dir)
    found = gemini_md_gate_find_file(settings, home_dir)
    text = gemini_md_gate_read_text(found) if found else ""
    return {
        "enabled": settings["gemini_md_enabled"], "budget_pct": settings["gemini_md_budget_pct"],
        "path_override": settings["gemini_md_path"], "file_found": bool(found), "file_path": str(found) if found else "",
        "file_chars": len(text), "active": bool(settings["gemini_md_enabled"] and found and text),
        "looked_for": [] if settings["gemini_md_path"] else ["~/" + c for c in FILE_CANDIDATES],
    }
