"""
Library:        lib_bejson_AI_ai_keywords.py
Family:         AI
Description:    Provider-agnostic keyword trigger system for the AI family.
                Manages a BEJSON 104a keywords registry (ai_keywords.bejson),
                scans user messages for keyword hits with per-pair cooldowns,
                resolves context content from flat files or inline kb://
                knowledge-pool entries, and returns ready-to-inject text
                blocks.

                Modelled after NewAgent's triggers.bejson + scan_triggers() +
                build_keyword_section() but decoupled from NewAgent-specific
                paths, imports, and the NewAgent errors module.

                Schema (ai_keywords.bejson):
                  keyword         -- phrase to detect in the user message
                  context_path    -- relative file path inside situational_dir,
                                     OR "kb://<info_id>" to pull a single
                                     entry from ai_knowledge_pool.bejson
                  cooldown_seconds -- seconds before this (keyword, path) pair
                                     can fire again (0 = no cooldown)
                  enabled         -- boolean; false rows are never scanned

                Template generation:
                  ai_keywords_init()  creates ai_keywords.bejson with an
                  empty Values list so the caller can start adding rows.
                  ai_keywords_add_template() writes a starter .bejson in
                  situational_dir as well so the user has a full working
                  scaffold.

Version:        1.0.0
Date:           2026-08-12
Author:         Elton Boehnen
Contact:        boehnenelton2024@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
RELATIONAL_ID:  b2c3d4e5-f6a7-8901-bcde-f12345678901

Changelog:
  1.0.0 (2026-08-12) -- Initial creation. Provider-agnostic extraction of
        NewAgent's keyword trigger pattern into the AI family.
"""

# NOTE: New file.  No existing AI family files were modified.

import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

VERSION = "1.0.0"

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

# ── Schema ────────────────────────────────────────────────────────────────────

_KEYWORD_FIELDS = [
    {"name": "keyword",          "type": "string"},
    {"name": "context_path",     "type": "string"},
    {"name": "cooldown_seconds", "type": "integer"},
    {"name": "enabled",          "type": "boolean"},
]

_KNOWLEDGE_FIELDS = [
    {"name": "info_id",   "type": "string"},
    {"name": "content",   "type": "string"},
    {"name": "category",  "type": "string"},
    {"name": "is_active", "type": "boolean"},
]

# Template for a starter situational context file
_CONTEXT_TEMPLATE_FIELDS = [
    {"name": "section", "type": "string"},
    {"name": "content", "type": "string"},
]

_KEYWORDS_FILENAME  = "ai_keywords.bejson"
_KNOWLEDGE_FILENAME = "ai_knowledge_pool.bejson"

# Prefix used to reference a knowledge-pool entry by info_id instead of a file.
KB_PREFIX = "kb://"


# ── Init / template generation ────────────────────────────────────────────────

def ai_keywords_init(config_dir: Path) -> Path:
    """
    Ensures ai_keywords.bejson exists in config_dir.  Creates an empty
    registry if missing.  Returns the path to the file.
    """
    config_dir = Path(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / _KEYWORDS_FILENAME

    if not path.exists():
        doc = bejson_core_create_104a("Trigger", list(_KEYWORD_FIELDS), [])
        if not bejson_core_atomic_write(str(path), doc):
            logger.error("[AIKeywords] Atomic write failed: %s", path)

    return path


def ai_keywords_add_row(
    config_dir: Path,
    keyword: str,
    context_path: str,
    cooldown_seconds: int = 300,
    enabled: bool = True,
) -> bool:
    """
    Appends a single trigger row to ai_keywords.bejson.  Returns True on
    success.  Does NOT deduplicate — two rows with the same (keyword,
    context_path) are allowed and will have independent cooldowns.
    """
    path = Path(config_dir) / _KEYWORDS_FILENAME
    if not path.exists():
        ai_keywords_init(config_dir)

    doc = bejson_core_load_file(str(path))
    if not isinstance(doc, dict):
        logger.error("[AIKeywords] Cannot load %s for add_row()", path)
        return False

    doc.setdefault("Values", []).append(
        [keyword, context_path, cooldown_seconds, enabled]
    )
    return bejson_core_atomic_write(str(path), doc)


def ai_keywords_add_template(
    situational_dir: Path,
    template_name: str,
    sections: Optional[list[tuple[str, str]]] = None,
) -> Path:
    """
    Writes a starter context.bejson in situational_dir named
    <template_name>.bejson.  Pass sections as [(section_title, content), ...]
    or leave None to get an empty scaffold.  Returns the file path.

    Wire this file to a keyword row with:
        context_path = "<template_name>.bejson"
    """
    situational_dir = Path(situational_dir)
    situational_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    if sections:
        rows = [[s, c] for s, c in sections]

    doc = bejson_core_create_104a("ContextSection", list(_CONTEXT_TEMPLATE_FIELDS), rows)
    target = situational_dir / f"{template_name}.bejson"
    if not bejson_core_atomic_write(str(target), doc):
        logger.error("[AIKeywords] Atomic write failed for template: %s", target)
    return target


def ai_keywords_init_knowledge_pool(config_dir: Path) -> Path:
    """
    Ensures ai_knowledge_pool.bejson exists.  Used when the caller wants
    inline kb:// references rather than separate files.
    """
    config_dir = Path(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / _KNOWLEDGE_FILENAME

    if not path.exists():
        doc = bejson_core_create_104a("KnowledgeEntry", list(_KNOWLEDGE_FIELDS), [])
        if not bejson_core_atomic_write(str(path), doc):
            logger.error("[AIKeywords] Atomic write failed for knowledge pool: %s", path)

    return path


def ai_keywords_add_knowledge_entry(
    config_dir: Path,
    info_id: str,
    content: str,
    category: str = "general",
    is_active: bool = True,
) -> bool:
    """
    Appends an entry to ai_knowledge_pool.bejson.  Reference it from a
    keyword row with context_path = "kb://<info_id>".
    """
    path = Path(config_dir) / _KNOWLEDGE_FILENAME
    if not path.exists():
        ai_keywords_init_knowledge_pool(config_dir)

    doc = bejson_core_load_file(str(path))
    if not isinstance(doc, dict):
        logger.error("[AIKeywords] Cannot load knowledge pool at %s", path)
        return False

    doc.setdefault("Values", []).append([info_id, content, category, is_active])
    return bejson_core_atomic_write(str(path), doc)


# ── Scanning ──────────────────────────────────────────────────────────────────

def ai_keywords_scan(
    user_msg: str,
    config_dir: Path,
    cooldown_state: dict[str, float],
    global_default_cooldown: int = 300,
    now_ts: Optional[float] = None,
) -> list[dict]:
    """
    Scans user_msg against every enabled row in ai_keywords.bejson.
    Returns a list of matched dicts: {"keyword": str, "context_path": str}.

    cooldown_state is mutated in-place — pass the same dict across turns
    so cooldowns persist within a session.  Key format: "<kw>::<path>".

    global_default_cooldown is used when a row's cooldown_seconds is None.
    Setting a row's cooldown_seconds to 0 disables cooldown for that pair.
    """
    path = Path(config_dir) / _KEYWORDS_FILENAME
    if not path.exists():
        return []

    doc = bejson_core_load_file(str(path))
    if not isinstance(doc, dict):
        return []

    fmap       = bejson_core_get_field_map(doc)
    kw_idx     = fmap.get("keyword",          0)
    path_idx   = fmap.get("context_path",     1)
    cd_idx     = fmap.get("cooldown_seconds", 2)
    en_idx     = fmap.get("enabled",          3)

    now     = now_ts if now_ts is not None else time.time()
    msg_low = user_msg.lower()
    matches = []

    for row in doc.get("Values", []):
        if len(row) <= max(kw_idx, path_idx):
            continue
        # Skip disabled rows
        if en_idx < len(row) and row[en_idx] is False:
            continue

        keyword = row[kw_idx] or ""
        if not keyword or keyword.lower() not in msg_low:
            continue

        ctx_path = row[path_idx] or ""
        cooldown = (
            row[cd_idx] if cd_idx < len(row) and row[cd_idx] is not None
            else global_default_cooldown
        )

        # Cooldown key is (keyword, context_path) — independent per row.
        cd_key = f"{keyword}::{ctx_path}"
        last   = cooldown_state.get(cd_key, 0.0)
        if cooldown > 0 and (now - last) < cooldown:
            continue

        cooldown_state[cd_key] = now
        matches.append({"keyword": keyword, "context_path": ctx_path})

    return matches


# ── Content resolution ────────────────────────────────────────────────────────

def ai_keywords_build_section(
    matches: list[dict],
    situational_dir: Path,
    budget_chars: int,
    knowledge_pool_path: Optional[Path] = None,
) -> tuple[str, int]:
    """
    Resolves each match to text and assembles a single injected block,
    capped to budget_chars.

    context_path resolution order:
      1. Starts with "kb://<info_id>"  → look up in knowledge pool by info_id
      2. Otherwise                     → read file from situational_dir/<context_path>

    Returns (assembled_text, chars_used).  Returns ("", 0) when nothing fits
    or matches is empty.
    """
    if not matches or budget_chars <= 0:
        return "", 0

    parts: list[str] = []
    used = 0

    for m in matches:
        ctx_path = m.get("context_path", "")
        keyword  = m.get("keyword", "")

        if ctx_path.startswith(KB_PREFIX):
            info_id = ctx_path[len(KB_PREFIX):]
            content = _lookup_kb_entry(knowledge_pool_path, info_id) if knowledge_pool_path else None
            if content is None:
                continue
        else:
            fpath = Path(situational_dir) / ctx_path
            if not fpath.exists():
                logger.warning("[AIKeywords] Context file not found: %s", fpath)
                continue
            try:
                # Plain text or .bejson — read raw; let the bubble render it.
                content = fpath.read_text("utf-8", errors="replace")
            except Exception as exc:
                logger.warning("[AIKeywords] Could not read %s: %s", fpath, exc)
                continue

        block = f"[{keyword}]\n{content}"
        if used + len(block) > budget_chars:
            remaining = budget_chars - used
            if remaining > 0:
                parts.append(block[:remaining])
                used = budget_chars
            break
        parts.append(block)
        used += len(block)

    return "\n\n".join(parts), used


# ── Internal helpers ──────────────────────────────────────────────────────────

def _lookup_kb_entry(knowledge_path: Path, info_id: str) -> Optional[str]:
    """
    Fetches a single entry's content from ai_knowledge_pool.bejson by
    info_id.  Returns None if the pool is missing, the ID is not found, or
    the entry is marked inactive.
    """
    if not knowledge_path or not Path(knowledge_path).exists():
        return None

    doc = bejson_core_load_file(str(knowledge_path))
    if not isinstance(doc, dict):
        return None

    fmap       = bejson_core_get_field_map(doc)
    id_idx     = fmap.get("info_id",   0)
    content_idx = fmap.get("content",  1)
    active_idx  = fmap.get("is_active", 3)

    for row in doc.get("Values", []):
        if len(row) <= max(id_idx, content_idx, active_idx):
            continue
        if row[id_idx] == info_id:
            return row[content_idx] if row[active_idx] else None

    return None
