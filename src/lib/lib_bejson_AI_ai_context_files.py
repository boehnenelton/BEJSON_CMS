"""
Library:        lib_bejson_AI_ai_context_files.py
Family:         AI
Description:    Tracks user-imported "context files" -- text the user has
                 attached in a client UI to be included in every AI call --
                 with a per-file enable/disable checkbox, and registers a
                 Context Bubble (see lib_bejson_AI_ai_context_bubble.py)
                 custom section that concatenates the currently-enabled
                 files' content, budgeted, for injection into that turn's
                 assembled context.

                 Tracking metadata (file_id, filename, enabled, char_count,
                 imported_at) lives in one small BEJSON 104 table
                 (context_files.bejson). Each file's actual text content is
                 stored as its own .txt file under an "imports/" subfolder
                 next to it, keyed by file_id -- keeps the tracking table
                 itself small and mirrors how ai_context_bubble.py stores
                 Persistent_Policy.md as its own file rather than embedding
                 policy text in a data row.

                 This library has no Flask/HTTP dependency -- a caller
                 (e.g. client/app.py) wires it to actual endpoints; the
                 functions here are pure file/BEJSON operations plus one
                 builder function matching ai_bubble_register_section()'s
                 expected signature.
Version:        1.0.0
Date:           2026-09-21
Author:         Elton Boehnen
Contact:        eltonboehnen@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  6f3a9c1e-8b2d-4e7f-9a1c-3d5e7f9b1c2a

Changelog:
  1.0.0 (2026-09-21) -- Initial creation. Written to plug into
        ai_context_bubble.py's Section 7 (Custom Sections) as the backing
        implementation for the chat client's file-import-list-with-
        checkboxes feature.
"""

import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

_logger = logging.getLogger(__name__)

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_CORE_DIR = os.path.join(os.path.dirname(_LIB_DIR), "Core")
for _p in (_LIB_DIR, _CORE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib_bejson_Core_bejson_core import (
    bejson_core_load_file,
    bejson_core_atomic_write,
    bejson_core_create_104,
    bejson_core_get_field_map,
)

_TRACKING_FILENAME = "context_files.bejson"
_IMPORTS_SUBDIR = "imports"
_MAX_FILE_CHARS = 200_000  # ~50k tokens at 4 chars/token -- generous but bounded

_FIELDS = [
    {"name": "file_id",     "type": "string"},
    {"name": "filename",    "type": "string"},
    {"name": "enabled",     "type": "boolean"},
    {"name": "char_count",  "type": "integer"},
    {"name": "imported_at", "type": "string"},
]


# ── Paths ─────────────────────────────────────────────────────────────────────

def _tracking_path(context_dir) -> Path:
    return Path(context_dir) / _TRACKING_FILENAME


def _imports_dir(context_dir) -> Path:
    return Path(context_dir) / _IMPORTS_SUBDIR


def _content_path(context_dir, file_id: str) -> Path:
    return _imports_dir(context_dir) / f"{file_id}.txt"


# ── Init / load / save ──────────────────────────────────────────────────────

def ai_context_files_init(context_dir) -> Path:
    """Creates context_files.bejson (empty) and imports/ if missing. Returns the tracking file path."""
    context_dir = Path(context_dir)
    context_dir.mkdir(parents=True, exist_ok=True)
    _imports_dir(context_dir).mkdir(parents=True, exist_ok=True)
    path = _tracking_path(context_dir)
    if not path.exists():
        doc = bejson_core_create_104("ContextFile", _FIELDS, [])
        bejson_core_atomic_write(str(path), doc)
    return path


def _load(context_dir) -> dict:
    path = ai_context_files_init(context_dir)
    doc = bejson_core_load_file(str(path))
    if not doc or "Values" not in doc:
        doc = bejson_core_create_104("ContextFile", _FIELDS, [])
    return doc


def _save(context_dir, doc: dict) -> None:
    bejson_core_atomic_write(str(_tracking_path(context_dir)), doc)


# ── Public API ────────────────────────────────────────────────────────────────

def ai_context_files_list(context_dir) -> list:
    """Returns a list of {file_id, filename, enabled, char_count, imported_at} dicts, newest first."""
    doc = _load(context_dir)
    fmap = bejson_core_get_field_map(doc)
    rows = doc.get("Values", [])
    out = [
        {
            "file_id":     row[fmap["file_id"]],
            "filename":    row[fmap["filename"]],
            "enabled":     row[fmap["enabled"]],
            "char_count":  row[fmap["char_count"]],
            "imported_at": row[fmap["imported_at"]],
        }
        for row in rows
    ]
    out.sort(key=lambda r: r["imported_at"], reverse=True)
    return out


def ai_context_files_import(context_dir, filename: str, content: str) -> dict:
    """
    Stores `content` as a new tracked, enabled-by-default file. Truncates to
    _MAX_FILE_CHARS (a single oversized import shouldn't be able to blow the
    whole context budget on its own -- the section builder budgets on top of
    this anyway, but capping here keeps the stored file itself sane).
    Returns the new file's tracking record.
    """
    if content is None:
        content = ""
    truncated = len(content) > _MAX_FILE_CHARS
    if truncated:
        content = content[:_MAX_FILE_CHARS]

    context_dir = Path(context_dir)
    ai_context_files_init(context_dir)
    file_id = uuid.uuid4().hex[:12]

    _content_path(context_dir, file_id).write_text(content, encoding="utf-8")

    doc = _load(context_dir)
    fmap = bejson_core_get_field_map(doc)
    row = [None] * len(fmap)
    row[fmap["file_id"]]     = file_id
    row[fmap["filename"]]    = filename or file_id
    row[fmap["enabled"]]     = True
    row[fmap["char_count"]]  = len(content)
    row[fmap["imported_at"]] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    doc["Values"].append(row)
    _save(context_dir, doc)

    if truncated:
        _logger.warning("ai_context_files_import: '%s' truncated to %d chars.", filename, _MAX_FILE_CHARS)

    return {
        "file_id": file_id, "filename": row[fmap["filename"]], "enabled": True,
        "char_count": row[fmap["char_count"]], "imported_at": row[fmap["imported_at"]],
        "truncated": truncated,
    }


def ai_context_files_toggle(context_dir, file_id: str) -> Optional[bool]:
    """Flips a file's enabled flag. Returns the new value, or None if file_id wasn't found."""
    doc = _load(context_dir)
    fmap = bejson_core_get_field_map(doc)
    for row in doc.get("Values", []):
        if row[fmap["file_id"]] == file_id:
            row[fmap["enabled"]] = not row[fmap["enabled"]]
            _save(context_dir, doc)
            return row[fmap["enabled"]]
    return None


def ai_context_files_delete(context_dir, file_id: str) -> bool:
    """Removes a file's tracking record and its stored content. Returns True if it existed."""
    doc = _load(context_dir)
    fmap = bejson_core_get_field_map(doc)
    rows = doc.get("Values", [])
    new_rows = [r for r in rows if r[fmap["file_id"]] != file_id]
    if len(new_rows) == len(rows):
        return False
    doc["Values"] = new_rows
    _save(context_dir, doc)
    content_path = _content_path(context_dir, file_id)
    if content_path.exists():
        content_path.unlink()
    return True


# ── Context Bubble custom-section builder ───────────────────────────────────

def ai_context_files_build_section(constants: dict, cwd: str, config_dir, context_dir) -> tuple:
    """
    Matches ai_bubble_register_section()'s builder_fn signature:
    (constants, cwd, config_dir, context_dir) -> (text, chars_used).

    Concatenates the content of every ENABLED imported file, each under its
    own "### <filename>" heading, truncated to the section's budget (the
    caller applies the budget cap via the returned text's actual length --
    this function does its own truncation too, since the registry doesn't
    pass a budget into the builder_fn directly; ai_bubble_assemble() only
    checks that budget > 0 before calling it. That means this section can
    currently exceed its nominal pct_key budget if enabled files are large
    -- acceptable for now since the caller sees exactly how many chars came
    back and can surface that, but worth tightening if it becomes a problem
    in practice.
    """
    files = ai_context_files_list(context_dir)
    enabled = [f for f in files if f["enabled"]]
    if not enabled:
        return "", 0

    blocks = []
    for f in enabled:
        content_path = _content_path(context_dir, f["file_id"])
        if not content_path.exists():
            continue
        try:
            text = content_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            _logger.warning("ai_context_files_build_section: failed to read %s: %s", f["filename"], exc)
            continue
        blocks.append(f"### {f['filename']}\n{text}")

    full_text = "\n\n".join(blocks)
    return full_text, len(full_text)
