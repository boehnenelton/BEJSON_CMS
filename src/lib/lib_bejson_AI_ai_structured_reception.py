"""
Library:        lib_bejson_AI_ai_structured_reception.py
Family:         AI
Description:    "Structured-Reception" half of a matched instruction/
                 reception pair (see lib_bejson_AI_ai_structured_instruction.py,
                 which must be read alongside this file -- each function
                 here parses exactly what its same-named counterpart there
                 asked the model to produce; the two formats are not
                 independently documented). This library only detects and
                 parses; it does not decide what happens to the parsed
                 result. What a caller does with a parsed list of items, or
                 a rebuilt project, is entirely up to that caller -- that
                 line is deliberate, per the concept this pair was built
                 from: "the actions done with the parsed content are
                 outside the library scope."

                 structured_reception_parse_list() is the generic
                 counterpart to structured_instruction_list(): pulls
                 [ITEM]...[/ITEM]-style blocks (or whatever block_name was
                 used) out of raw model output into a list of dicts.
                 Best-effort by design -- a block missing a field, or a
                 field with irregular casing/spacing, is not treated as a
                 fatal error, only as that block being partially filled,
                 since smaller/free-tier models won't always follow the
                 format exactly.

                 structured_reception_rebuild_project() is the specific
                 counterpart to structured_instruction_chunker_project():
                 extracts a BEJSON 104db document from raw model output
                 (tolerating markdown code fences and stray text around it,
                 since even a model instructed to stay silent may not)
                 and rebuilds it to real files on disk. The actual
                 rebuild logic (locating the Record_Type_Parent-
                 discriminated ProjectMeta/FileContent rows, writing files,
                 touch-only for is_binary rows) is lifted directly from
                 CLI_Chunker.py's own run_unchunk() 104db branch, not
                 reinvented, so a project built by an LLM through this
                 pair unpacks exactly the same way a project chunked by
                 CLI_Chunker itself does.
Version:        1.0.0
Date:           2026-09-27
Author:         Elton Boehnen
Contact:        eltonboehnen@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  5f1c8e42-9a3d-4b76-8e2f-1c9a7d4e6b83
Release_Version: 300

Changelog:
  1.0.0 (2026-09-27) -- Initial creation. structured_reception_parse_list()
        is this pass's generic function; structured_reception_rebuild_project()
        is the second function this pass was asked to add, matching
        structured_instruction_chunker_project() and modeled directly on
        CLI_Chunker.py's run_unchunk().
"""

import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

_logger = logging.getLogger(__name__)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_CORE_DIR = os.path.join(os.path.dirname(_THIS_DIR), "Core")
if _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)

from lib_bejson_Core_bejson_validator import validate_bejson


# ── Generic: parse [ITEM]...[/ITEM] blocks back into dicts ──────────────────

def structured_reception_parse_list(raw_text: str, block_name: str = "ITEM") -> list:
    """
    Matching parser for structured_instruction_list(). Extracts every
    [block_name]...[/block_name] block from raw_text and, within each,
    every "field: value" line, returning a list of {field: value} dicts in
    the order the blocks appeared. A block need not contain every field a
    caller might expect -- missing fields are simply absent from that
    block's dict, not an error; the model not following instructions
    exactly is the expected failure mode here, not an exceptional one.
    """
    if not raw_text:
        return []

    block_pattern = re.compile(
        rf"\[{re.escape(block_name)}\]\s*(.*?)\s*\[/{re.escape(block_name)}\]",
        re.DOTALL | re.IGNORECASE,
    )
    line_pattern = re.compile(r"^\s*([A-Za-z0-9_ ]+?)\s*:\s*(.*)$")

    items = []
    for block_match in block_pattern.finditer(raw_text):
        block_body = block_match.group(1)
        item = {}
        for line in block_body.splitlines():
            line_match = line_pattern.match(line)
            if not line_match:
                continue
            key = line_match.group(1).strip().lower().replace(" ", "_")
            value = line_match.group(2).strip()
            if key:
                item[key] = value
        if item:
            items.append(item)

    return items


# ── Specific: extract + rebuild a BEJSON 104db project ──────────────────────

def _extract_json_object(raw_text: str) -> Optional[dict]:
    """
    Best-effort JSON extraction: strips markdown code fences if present,
    then finds the first balanced {...} block and parses it. Tolerates a
    model that didn't achieve the requested "silence" (stray preamble/
    commentary around the JSON) despite being instructed not to.
    """
    if not raw_text:
        return None

    text = raw_text.strip()

    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()

    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    return None
    return None


def structured_reception_rebuild_project(raw_text: str, destination: Optional[str] = None) -> dict:
    """
    Matching parser for structured_instruction_chunker_project(). Extracts
    a BEJSON 104db document from raw_text (tolerating code fences/stray
    text around it) and rebuilds it to real files on disk, following the
    exact same rules as CLI_Chunker.py's run_unchunk() 104db branch:
      - ProjectMeta row's project_name names the output folder (falls back
        to "RestoredProject" if no ProjectMeta row is present).
      - Each FileContent row writes file_path relative to that folder.
      - is_binary=true rows are touch()'d empty rather than fabricating
        binary content from a text field -- this schema has no encoding
        for binary bytes (no is_base64 field, unlike CLI_Chunker's
        separate MFDB-version path), so an empty placeholder is the
        correct, honest behavior, not a bug to work around here.
      - destination defaults to ./Restored_Projects/<project_name>/<UTC
        timestamp>/, matching CLI_Chunker's own default layout.

    Returns {"success": bool, "reason": str, "project_name": str|None,
             "output_dir": str|None, "file_count": int}.
    """
    doc = _extract_json_object(raw_text)
    if doc is None:
        return {"success": False, "reason": "No JSON object found in model output.",
                "project_name": None, "output_dir": None, "file_count": 0}

    res = validate_bejson(doc, is_file=False)
    if not res.valid:
        return {"success": False, "reason": f"Validation failed: {res.errors}",
                "project_name": None, "output_dir": None, "file_count": 0}

    if doc.get("Format_Version") != "104db":
        return {"success": False, "reason": f"Expected Format_Version '104db', got {doc.get('Format_Version')!r}.",
                "project_name": None, "output_dir": None, "file_count": 0}

    fields = [f["name"] for f in doc.get("Fields", [])]
    try:
        pname_idx = fields.index("project_name")
        fpath_idx = fields.index("file_path")
        cont_idx = fields.index("content")
        bin_idx = fields.index("is_binary")
    except ValueError as e:
        return {"success": False, "reason": f"Schema missing an expected field: {e}",
                "project_name": None, "output_dir": None, "file_count": 0}

    values = doc.get("Values", [])
    meta_rows = [r for r in values if r and r[0] == "ProjectMeta"]
    proj_name = meta_rows[0][pname_idx] if meta_rows else "RestoredProject"
    file_rows = [r for r in values if r and r[0] == "FileContent"]
    records = [(r[fpath_idx], r[cont_idx], r[bin_idx]) for r in file_rows]

    if destination:
        out_dir = Path(destination).resolve()
    else:
        ts_slug = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        out_dir = Path.cwd() / "Restored_Projects" / proj_name / ts_slug
    out_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for rel_path, content, binary in records:
        if not rel_path:
            continue
        target_file = out_dir / rel_path
        target_file.parent.mkdir(parents=True, exist_ok=True)
        if binary:
            target_file.touch()
        else:
            target_file.write_text(content or "", encoding="utf-8")
        written += 1

    return {"success": True, "reason": "Rebuilt.", "project_name": proj_name,
            "output_dir": str(out_dir), "file_count": written}
