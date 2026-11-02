"""
Library:         lib_bejson_AI_brain_keywords.py
Family:          AI
Module Purpose:  Keyword recall for the Brain: matches the user's message against memory keywords and returns the best entries.
Architecture:    In-memory index built from active, unpinned memories (their keywords plus their category's default keywords), cached against the store generation and the memory file's mtime. Reads only the user's message (never the AI's reply). Score = priority x confidence + bonus x distinct matches. Same cooldown-state idea as lib_bejson_AI_ai_keywords (a dict the caller keeps across turns).
Version:         1.0.0
Release_Version: 300
Date:            2026-10-25
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   8ece3c8b-a0ac-4d00-88cd-2c0b4de5b9e9
"""

import logging
import re

import lib_bejson_AI_brain_core_bridge  # noqa: F401
from lib_bejson_AI_brain_schema_registry import (
    CatF, MemF, ENTITY_MEMORY, STATUS_ACTIVE, ORIGIN_AI, schema_registry_split_keywords,
)
from lib_bejson_AI_brain_store import BrainStore

VERSION = "1.0.0"
RELATIONAL_ID = "8ece3c8b-a0ac-4d00-88cd-2c0b4de5b9e9"
_LOGGER = logging.getLogger("brain.keywords")

# Generic words that would match almost every message; dropped from the index.
STOPLIST = frozenset({
    "this", "that", "with", "from", "have", "about", "there", "their", "what", "when", "which", "would",
    "could", "should", "other", "please", "thing", "things", "something", "anything", "everything", "make",
    "need", "want", "like", "just", "some", "more", "very", "will", "your", "mine", "been", "does",
})


# Cache key: store generation plus the memory file's mtime (so another process's write also invalidates).
def _cache_key(store: BrainStore) -> tuple:
    entity = store.db_dir / "data" / (ENTITY_MEMORY.lower() + ".bejson")
    try:
        stamp = entity.stat().st_mtime_ns
    except OSError:
        stamp = 0
    return (store.generation, stamp)


# Builds (or returns the cached) recall index: a list of entry dicts with a "keywords" tuple.
def brain_keywords_build_index(store: BrainStore) -> list[dict]:
    key = _cache_key(store)
    cached = getattr(store, "_brain_keyword_index", None)
    if cached is not None and cached[0] == key:
        return cached[1]
    cats = {c[CatF.ID]: c for c in store.categories()}
    entries = []
    for mem in store.memories(status=STATUS_ACTIVE):
        cat = cats.get(mem[MemF.CATEGORY_FK])
        if cat is None or mem[MemF.PINNED]:
            continue
        words = set(schema_registry_split_keywords(mem[MemF.KEYWORDS])) | set(schema_registry_split_keywords(cat[CatF.KEYWORDS]))
        words = {w for w in words if w not in STOPLIST}
        if not words:
            continue
        entries.append({
            "id": mem[MemF.ID], "title": mem[MemF.TITLE], "content": mem[MemF.CONTENT], "origin": mem[MemF.ORIGIN],
            "category": cat[CatF.NAME], "priority": mem[MemF.PRIORITY], "confidence": mem[MemF.CONFIDENCE],
            "keywords": tuple(sorted(words)),
            "patterns": tuple((w, re.compile(r"(?<!\w)" + re.escape(w) + r"(?!\w)")) for w in sorted(words)),
        })
    store._brain_keyword_index = (key, entries)
    return entries


# Returns up to recall_max_entries entries matching the user's message, best first. cooldown_state maps memory id -> last turn shown.
def brain_keywords_recall(store: BrainStore, user_msg: str, turn: int = 0, cooldown_state: dict | None = None) -> list[dict]:
    if not user_msg or not user_msg.strip():
        return []
    message = user_msg.casefold()
    bonus = int(store.limits["recall_match_bonus"])
    cooldown = int(store.limits["recall_cooldown_turns"])
    limit = int(store.limits["recall_max_entries"])
    cap = int(store.limits["recall_max_entry_chars"])
    scored = []
    for entry in brain_keywords_build_index(store):
        hits = [word for word, pattern in entry["patterns"] if pattern.search(message)]
        if not hits:
            continue
        if cooldown and cooldown_state is not None and turn - cooldown_state.get(entry["id"], -10**9) <= cooldown:
            continue
        score = entry["priority"] * entry["confidence"] + bonus * len(hits)
        scored.append((score, entry["title"].casefold(), entry, hits))
    scored.sort(key=lambda item: (-item[0], item[1]))
    result = []
    for score, _, entry, hits in scored[:limit]:
        text = entry["content"]
        if len(text) > cap:
            text = text[:cap - 1].rstrip() + "…"
        result.append({"id": entry["id"], "title": entry["title"], "content": text, "origin": entry["origin"],
                       "category": entry["category"], "matched": hits, "score": round(score, 2)})
        if cooldown_state is not None:
            cooldown_state[entry["id"]] = turn
    return result
