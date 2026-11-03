"""
Library:         lib_bejson_AI_brain_config.py
Family:          AI
Module Purpose:  Loads Brain limits and policy settings from config/brain_limits.104a.bejson, creating the file with defaults when absent.
Architecture:    BEJSON 104a ScriptConfig (setting_name, setting_value, description). Unknown names are ignored; a bad value type falls back to the default and is logged. Atomic writes through Core.
Version:         1.2.0
Release_Version: 300
Date:            2026-10-25
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   e675e6ee-0cfd-4b81-a5fd-5c29644dbb22
"""

import json
import logging
from pathlib import Path

import lib_bejson_AI_brain_core_bridge  # noqa: F401  (puts Core on sys.path)
from lib_bejson_Core_bejson_core import bejson_core_atomic_write, bejson_core_get_field_map
from lib_bejson_AI_brain_errors import BrainError, E_BRAIN_CORRUPT

VERSION = "1.2.0"
RELATIONAL_ID = "0de306c0-fec0-430e-a12f-a58531c0abcf"
CONFIG_FILENAME = "brain_limits.104a.bejson"

_LOGGER = logging.getLogger("brain.config")
_COL_NAME, _COL_VALUE, _COL_DESC = "setting_name", "setting_value", "description"

# name -> (default, description)
DEFAULTS = {
    "max_categories": (32, "Maximum non-archived categories."),
    "max_ai_proposed_categories": (8, "Maximum categories the AI may have waiting for approval."),
    "max_memories": (2000, "Maximum non-archived memories."),
    "max_title_chars": (80, "Memory title length cap."),
    "max_content_chars": (2000, "Memory content length cap."),
    "max_category_name_chars": (40, "Category name length cap."),
    "max_keywords": (8, "Keywords per memory."),
    "keyword_min_chars": (4, "Shortest allowed keyword."),
    "keyword_max_chars": (32, "Longest allowed keyword."),
    "max_commands_per_batch": (10, "AI commands per batch."),
    "max_batches_per_turn": (1, "AI batches per chat turn."),
    "max_ai_writes_per_hour": (20, "AI write operations per rolling hour."),
    "max_xml_block_bytes": (16384, "Largest AI command block accepted."),
    "ai_max_priority": (60, "Highest priority an AI-written memory can have."),
    "auto_max_priority": (40, "Highest priority an AI memory may have and still apply without review (policy auto)."),
    "write_policy": ("open", "open = AI memory writes (new notes, edits to its own unlocked notes, new categories) apply directly at any allowed priority and can be edited or archived in the client; auto = only new low-priority notes apply directly; review = every AI write waits for approval."),
    "memory_mode": ("inline", "inline | pass | off."),
    "snapshot_default_keep": (5, "Default-tier snapshots kept besides the baseline."),
    "snapshot_daily_keep": (7, "Daily snapshots kept."),
    "snapshot_monthly_keep": (1, "Monthly snapshots kept."),
    "audit_max_rows": (2000, "Audit log rows kept."),
    "lock_timeout_seconds": (10, "Seconds to wait for the project lock."),
    "recall_max_entries": (5, "Memories injected per turn by keyword recall."),
    "recall_max_entry_chars": (1200, "Characters kept per recalled memory."),
    "recall_match_bonus": (15, "Score added per distinct keyword matched."),
    "recall_cooldown_turns": (0, "Turns a recalled memory is skipped afterwards. 0 = off (recall reads only the user's message, so repeats are intended)."),
}

_ENUMS = {"write_policy": ("open", "auto", "review"), "memory_mode": ("inline", "pass", "off")}


# Builds the default config document.
def _default_document() -> dict:
    return {
        "Format": "BEJSON",
        "Format_Version": "104a",
        "Format_Creator": "Elton Boehnen",
        "Records_Type": ["ScriptConfig"],
        "Fields": [
            {"name": _COL_NAME, "type": "string"},
            {"name": _COL_VALUE, "type": "any"},
            {"name": _COL_DESC, "type": "string"},
        ],
        "Values": [[name, default, description] for name, (default, description) in DEFAULTS.items()],
    }


# Returns the merged settings dict. Creates the file when missing. Raises BrainError(E_BRAIN_CORRUPT) when the file is unreadable.
def brain_config_load(config_dir: str | Path) -> dict:
    path = Path(config_dir) / CONFIG_FILENAME
    settings = {name: default for name, (default, _) in DEFAULTS.items()}
    if not path.is_file():
        bejson_core_atomic_write(str(path), _default_document())
        return settings
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        fmap = bejson_core_get_field_map(doc)
        name_idx, value_idx = fmap[_COL_NAME], fmap[_COL_VALUE]
        rows = doc["Values"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise BrainError(E_BRAIN_CORRUPT, f"Config file unreadable: {exc}", {"path": str(path)}) from exc
    for row in rows:
        name = str(row[name_idx]).strip()
        if name not in DEFAULTS:
            continue
        value = row[value_idx]
        default = DEFAULTS[name][0]
        if name in _ENUMS:
            if value in _ENUMS[name]:
                settings[name] = value
            else:
                _LOGGER.warning("Config %s=%r is not one of %s; using %r", name, value, _ENUMS[name], default)
        elif isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            settings[name] = value
        else:
            _LOGGER.warning("Config %s=%r is not a non-negative integer; using %r", name, value, default)
    return settings


# Changes one setting in the file (creating it first when missing). Returns the new settings dict.
def brain_config_set(config_dir: str | Path, name: str, value) -> dict:
    if name not in DEFAULTS:
        raise BrainError(E_BRAIN_CORRUPT, f"Unknown setting: {name}")
    brain_config_load(config_dir)
    path = Path(config_dir) / CONFIG_FILENAME
    doc = json.loads(path.read_text(encoding="utf-8"))
    fmap = bejson_core_get_field_map(doc)
    name_idx, value_idx = fmap[_COL_NAME], fmap[_COL_VALUE]
    for row in doc["Values"]:
        if row[name_idx] == name:
            row[value_idx] = value
            break
    else:
        doc["Values"].append([name, value, DEFAULTS[name][1]])
    bejson_core_atomic_write(str(path), doc)
    return brain_config_load(config_dir)
