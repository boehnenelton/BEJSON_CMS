"""
Library:        lib_bejson_AI_ai_call_log.py
Family:         AI
Description:    Shared BEJSON 104a append-log feed for all cli_test AI CLI
                 tools (groq_cli, openrouter_cli, provocative_cli,
                 gemini_cli, menu_cli). One row per call: timestamp,
                 service, message, response, uuid.
Version:        1.0.0
Date:           2026-08-15
Author:         Elton Boehnen
Contact:        eltonboehnen@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  980751d8-7f68-4b0a-acd2-84ea2e272f8c
"""

import os
import sys
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

LIB_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_DIR = os.path.join(os.path.dirname(LIB_DIR), "Core")
if CORE_DIR not in sys.path:
    sys.path.append(CORE_DIR)

from lib_bejson_Core_bejson_core import bejson_core_load_file, bejson_core_atomic_write, bejson_core_get_field_map

VERSION = "1.0.0"

SCHEMA_CALL_LOG = {
    "Format": "BEJSON",
    "Format_Version": "104a",
    "Format_Creator": "Elton Boehnen",
    "Schema_Name": "AICallLog",
    "Records_Type": ["AICall"],
    "Fields": [
        {"name": "timestamp", "type": "string"},
        {"name": "service", "type": "string"},
        {"name": "message", "type": "string"},
        {"name": "response", "type": "string"},
        {"name": "uuid", "type": "string"}
    ],
    "Values": []
}


def _default_log_path() -> Path:
    """
    Per the Global Operating Rules, non-portable/exported/backed-up data
    defaults to $ScriptData/<script_name>/. This feed is shared across
    every CLI tool in the project, so it lives under $ScriptData/cli_test/
    rather than a per-tool subfolder. Falls back to <project_root>/logs/
    if ScriptData isn't set (e.g. this sandbox, or a non-Android run).
    """
    script_data = os.environ.get("ScriptData")
    if script_data:
        return Path(script_data) / "cli_test" / "ai_call_log.104a.bejson"
    project_root = Path(__file__).resolve().parent.parent.parent
    return project_root / "dev" / "logs" / "ai_call_log.104a.bejson"


LOG_PATH = _default_log_path()


def log_ai_call(service: str, message: str, response: str, *, log_path: Optional[Path] = None) -> str:
    """
    Appends one row to the shared call-log feed. Returns the row's uuid.
    Best-effort: logging failures never raise -- a broken log must not
    break a chat session. Not safe for concurrent writers (last-write-wins,
    same caveat as the rest of this project's BEJSON usage); fine for a
    single interactive CLI process.
    """
    path = log_path or LOG_PATH
    entry_uuid = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        os.makedirs(path.parent, exist_ok=True)
        if path.exists():
            doc = bejson_core_load_file(str(path))
            if not doc or "Fields" not in doc:
                doc = dict(SCHEMA_CALL_LOG)
                doc["Values"] = []
        else:
            doc = dict(SCHEMA_CALL_LOG)
            doc["Values"] = []

        fmap = bejson_core_get_field_map(doc)
        row = [""] * len(doc["Fields"])
        row[fmap.get("timestamp", 0)] = timestamp
        row[fmap.get("service", 1)] = service
        row[fmap.get("message", 2)] = message
        row[fmap.get("response", 3)] = response
        row[fmap.get("uuid", 4)] = entry_uuid

        doc["Values"].append(row)
        bejson_core_atomic_write(str(path), doc)
    except Exception as e:
        # Logging is best-effort -- print a warning, never raise into the
        # caller's chat loop.
        print(f"[!] Warning: failed to write call log at {path}: {e}", file=sys.stderr)

    return entry_uuid
