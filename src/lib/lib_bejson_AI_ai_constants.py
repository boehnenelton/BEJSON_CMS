"""
Library:        lib_bejson_AI_ai_constants.py
Family:         AI
Description:    Provider-agnostic AI constants and configuration manager.
                Delivers a BEJSON 104a ai_constants.bejson template on
                first use, then loads effective values from it each call.
                Any script that needs context-bubble budgets, drip intervals,
                or observer toggles imports this instead of hard-coding values.

                Design goals:
                  - Zero provider coupling.  Works with Gemini, Groq,
                    OpenRouter, or any other prompter.
                  - Single source of truth.  All percentage/budget constants
                    live here; the bubble and keyword libraries read from here.
                  - Fully modular.  Each percentage slot can be set to 0 to
                    disable that section entirely.
                  - File-backed.  Caller supplies a config_dir; the file is
                    created with defaults on first run and loaded on all
                    subsequent runs.  defined_value overrides default_value
                    exactly as in NewAgent's constant_config.bejson.

                NOTE: This module deliberately does NOT import any provider
                library.  It only depends on the BEJSON Core family.

Version:        1.2.1
Date:           2026-09-21
Author:         Elton Boehnen
Contact:        boehnenelton2024@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
RELATIONAL_ID:  a1f2e3d4-b5c6-7890-abcd-ef1234567890
Release_Version: 300

Changelog:
  1.2.1 (2026-09-21) -- Added pct_staged_chunk (default 0.15) backing the
        chat client's Attach-tab Save button (see context_chunker.py).
        Nominal pct total is now 1.30 -- see the 1.2.0 note below, same
        trade-off, compounding.
  1.2.0 (2026-09-21) -- Added pct_imported_files (default 0.15) backing
        the chat client's new file-import-list-with-checkboxes feature
        (see lib_bejson_AI_ai_context_files.py). NOTE: the six original
        pct_* slots already summed to exactly 1.00 (0.20+0.20+0.30+0.15+
        0.10+0.05), which this file's own header comment says is the
        ceiling ("must sum <= 1.0"). Adding a 7th slot at 0.15 without
        reducing any existing one pushes the nominal total to 1.15.
        Flagging rather than silently rebalancing Elton's already-tuned
        percentages -- his call whether to trim the others or leave it
        (the sections aren't a strict partition of one buffer at the code
        level; each is independently sized as max_context_tokens * pct_key
        * chars_per_token, so exceeding 1.0 doesn't break anything
        mechanically, it just means the soft budget heuristic can, in the
        worst case, undersell how much total context a maximally-full
        turn actually uses).
  1.0.0 (2026-08-12) -- Initial creation. Modelled after NewAgent's
        constant_config.bejson + context_bubble.load_constants() but
        extracted into a standalone AI-family library so any project can
        use it without depending on the NewAgent family.
  1.1.0 (2026-09-11, audit V106-08) -- defined_value/default_value fields
        were declared type "any", which lib_bejson_Core_bejson_validator's
        VALID_FIELD_TYPES enforcement (added after this file was written)
        rejects outright -- the exact bug class already fixed for
        config.json (pkg084) and constant_config.bejson (pkg086), which
        this parked file was skipped by both times. Fields are now
        "string"; values are stringified on write (_to_str) and coerced
        back to the original Python type on read (_from_str, using each
        constant's _DEFAULT_CONSTANTS entry as the type template), same
        stringified-values pattern the other two files already use. None
        (unset defined_value) still round-trips as None, unstringified --
        matches constant_config.bejson's own existing convention.
"""

# NOTE: New file in the AI family.  No existing AI library files were modified.

import logging
import os
import sys
from pathlib import Path
from typing import Any

VERSION = "1.2.1"

logger = logging.getLogger(__name__)

# ── Sibling resolution ────────────────────────────────────────────────────────

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_CORE_DIR = os.path.join(os.path.dirname(_LIB_DIR), "Core")
for _p in (_LIB_DIR, _CORE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib_bejson_Core_bejson_core import (
    bejson_core_create_104a,
    bejson_core_atomic_write,
    bejson_core_load_file,
    bejson_core_get_field_map,
)

# ── Schema definition ─────────────────────────────────────────────────────────

_CONSTANT_FIELDS = [
    {"name": "constant_name",  "type": "string"},
    {"name": "defined_value",  "type": "string"},
    {"name": "default_value",  "type": "string"},
    {"name": "description",    "type": "string"},
]

# (constant_name, default_value, description)
# defined_value is written as None; the effective value is default_value until
# the user edits defined_value directly in ai_constants.bejson.
_DEFAULT_CONSTANTS: list[tuple[str, Any, str]] = [
    # ── Budget ────────────────────────────────────────────────────────────────
    ("max_context_tokens",           8000,  "Total token budget for the assembled context bubble"),
    ("chars_per_token",              4,     "Chars-per-token estimate for all budget arithmetic"),
    # ── Percentage slots (must sum <= 1.0; set a slot to 0 to disable) ───────
    ("pct_persistent_policy",        0.20,  "Share of budget for the persistent system/policy block"),
    ("pct_active_tasks",             0.20,  "Share of budget for active-task context"),
    ("pct_keyword_triggers",         0.30,  "Share of budget for keyword-triggered context injections"),
    ("pct_knowledge_pool",           0.15,  "Share of budget for knowledge-pool drip entries"),
    ("pct_cwd_context",              0.10,  "Share of budget for working-directory context.bejson"),
    ("pct_env_file",                 0.05,  "Share of budget for live environment variable drip"),
    ("pct_imported_files",           0.15,  "Share of budget for the chat client's user-imported context files"),
    ("pct_staged_chunk",             0.15,  "Share of budget for the chat client's persistent saved-chunk context (Attach tab Save button)"),
    # ── Drip / scheduling ─────────────────────────────────────────────────────
    ("knowledge_drip_interval",      5,     "Turns between knowledge-pool injections (0 = every turn)"),
    ("env_drip_interval",            5,     "Turns between env-file drip injections (0 = every turn)"),
    ("global_default_cooldown",      300,   "Default keyword-trigger cooldown in seconds"),
    # ── Observer (auto-compression of variable sections) ─────────────────────
    ("observer_enabled",             False, "Enable automatic bubble compression when over budget"),
    ("observer_refinement_interval", 7,     "Turns between automatic Observer compression checks"),
]

# Ordered list of pct_* keys -- used by any budget-display tool.
PCT_KEYS: list[str] = [
    "pct_persistent_policy",
    "pct_active_tasks",
    "pct_keyword_triggers",
    "pct_knowledge_pool",
    "pct_cwd_context",
    "pct_env_file",
    "pct_imported_files",
    "pct_staged_chunk",
]

_CONSTANTS_FILENAME = "ai_constants.bejson"


def _to_str(value: Any) -> Any:
    """Stringifies a Python value for storage in a type='string' BEJSON
    field. None passes through unstringified (constant_config.bejson's
    own convention for an unset defined_value)."""
    if value is None:
        return None
    return str(value)


def _from_str(raw: Any, template: Any) -> Any:
    """Coerces a stored string back to the Python type of `template`
    (the constant's default value, which carries the canonical type).
    None passes through. Falls back to the raw string on a bad parse
    rather than raising, so a hand-edited file can't crash a load."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        return raw  # already the right type (e.g. read from a pre-1.1.0 file)
    try:
        if isinstance(template, bool):
            return raw.strip().lower() in ("true", "1", "yes")
        if isinstance(template, int):
            return int(raw)
        if isinstance(template, float):
            return float(raw)
    except (TypeError, ValueError):
        return raw
    return raw


# ── Public API ────────────────────────────────────────────────────────────────

def ai_constants_init(config_dir: Path) -> Path:
    """
    Ensures ai_constants.bejson exists in config_dir with all default rows.
    If the file already exists, any rows missing from _DEFAULT_CONSTANTS are
    backfilled (new constants added in a library update won't require a
    manual file edit).  Never overwrites an existing defined_value.

    Returns the path to the constants file.
    """
    config_dir = Path(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / _CONSTANTS_FILENAME

    if not path.exists():
        doc = _build_doc(_DEFAULT_CONSTANTS)
        if not bejson_core_atomic_write(str(path), doc):
            logger.error("[AIConstants] Atomic write failed: %s", path)
        return path

    _backfill(path)
    return path


def ai_constants_load(config_dir: Path) -> dict[str, Any]:
    """
    Returns a dict mapping every constant_name to its effective value
    (defined_value if set, else default_value).  Falls back to
    _DEFAULT_CONSTANTS if the file cannot be read.
    """
    result: dict[str, Any] = {name: default for name, default, _ in _DEFAULT_CONSTANTS}
    path = Path(config_dir) / _CONSTANTS_FILENAME
    if not path.exists():
        return result

    doc = bejson_core_load_file(str(path))
    if not isinstance(doc, dict):
        logger.warning("[AIConstants] Could not parse %s -- using defaults", path)
        return result

    fmap        = bejson_core_get_field_map(doc)
    name_idx    = fmap.get("constant_name",  0)
    defined_idx = fmap.get("defined_value",  1)
    default_idx = fmap.get("default_value",  2)

    defaults_by_name = {name: default for name, default, _ in _DEFAULT_CONSTANTS}

    for row in doc.get("Values", []):
        if len(row) <= max(name_idx, defined_idx, default_idx):
            continue
        name  = row[name_idx]
        template = defaults_by_name.get(name, row[default_idx])
        raw = row[defined_idx] if row[defined_idx] is not None else row[default_idx]
        result[name] = _from_str(raw, template)

    return result


def ai_constants_set(config_dir: Path, name: str, value: Any) -> bool:
    """
    Writes a constant's defined_value.  Returns True on success.
    Setting value to None restores the default on the next ai_constants_load().
    """
    path = Path(config_dir) / _CONSTANTS_FILENAME
    if not path.exists():
        ai_constants_init(config_dir)

    doc = bejson_core_load_file(str(path))
    if not isinstance(doc, dict):
        logger.error("[AIConstants] Cannot load %s for set()", path)
        return False

    fmap        = bejson_core_get_field_map(doc)
    name_idx    = fmap.get("constant_name", 0)
    defined_idx = fmap.get("defined_value", 1)

    for row in doc.get("Values", []):
        if len(row) > name_idx and row[name_idx] == name:
            row[defined_idx] = _to_str(value)
            return bejson_core_atomic_write(str(path), doc)

    logger.warning("[AIConstants] Unknown constant '%s' -- set() ignored", name)
    return False


def ai_constants_budget_chars(constants: dict[str, Any], pct_key: str) -> int:
    """
    Converts a percentage slot to a character budget.
        chars = max_context_tokens * pct * chars_per_token
    Returns 0 if the slot is 0% or missing.
    """
    return int(
        constants.get("max_context_tokens", 8000)
        * constants.get(pct_key, 0.0)
        * constants.get("chars_per_token", 4)
    )


def ai_constants_pct_sum(constants: dict[str, Any]) -> float:
    """
    Returns the sum of all pct_* slots.  Useful for a /budget display that
    warns the user when the total exceeds 1.0 (over-subscription).
    """
    return sum(constants.get(k, 0.0) for k in PCT_KEYS)


def ai_constants_get_defaults() -> dict[str, Any]:
    """Returns a plain dict of all defaults (no file I/O)."""
    return {name: default for name, default, _ in _DEFAULT_CONSTANTS}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_doc(constants: list[tuple[str, Any, str]]) -> dict:
    rows = [[name, None, _to_str(default), desc] for name, default, desc in constants]
    return bejson_core_create_104a("Constant", list(_CONSTANT_FIELDS), rows)


def _backfill(path: Path) -> None:
    """Appends any constant in _DEFAULT_CONSTANTS that's absent from the file.
    Never touches rows that already exist."""
    doc = bejson_core_load_file(str(path))
    if not isinstance(doc, dict):
        return

    fmap     = bejson_core_get_field_map(doc)
    name_idx = fmap.get("constant_name", 0)
    rows     = doc.get("Values", [])
    existing = {row[name_idx] for row in rows if len(row) > name_idx}

    missing = [(n, d, desc) for n, d, desc in _DEFAULT_CONSTANTS if n not in existing]
    if not missing:
        return

    for name, default, desc in missing:
        rows.append([name, None, _to_str(default), desc])

    doc["Values"] = rows
    if not bejson_core_atomic_write(str(path), doc):
        logger.error("[AIConstants] Atomic write failed during backfill: %s", path)
