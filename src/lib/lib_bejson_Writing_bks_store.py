"""
Library:         lib_bejson_Writing_bks_store.py
Family:          Writing
Module Purpose:  Book Document access through the Field Map Cache: create, read rows, apply a chapter attempt, refresh derived values, and the one gated commit that atomically writes the file.
Architecture:    BKS-1 (BEJSON Book Standard) Writing family. Non-AI book organisation layer built on the frozen Core family (field-map cache, atomic write, validator, list validator). Contains no AI calls and no Flask code. Book Documents are BEJSON 104db; plans are the JobMaker 104a job schema.
Format_Scope:    104db (Book Document) | 104a (JobMaker plan)
Release_Version: 300
Version:         see VERSION below
Date:            2026-10-29
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   3347ab31-655c-428b-bbde-67960f2ff5d5
"""

import logging
import os
import re
from typing import Dict, List, Optional, Tuple

import lib_bejson_Core_bejson_core as Core
import lib_bejson_Writing_bks_derive as Derive
import lib_bejson_Writing_bks_errors as Errors
import lib_bejson_Writing_bks_gates as Gates
import lib_bejson_Writing_bks_registry as Registry

VERSION = "1.0.0"
_log = logging.getLogger("bks_store")

Tables = Dict[str, List[dict]]

# Why: a new Book Document starts from the registry Fields and no rows.
# Output: empty 104db document.
def bks_store_new_doc() -> dict:
    return Core.bejson_core_create_104db(list(Registry.BOOK_DOCUMENT_ENTITIES), Registry.bks_registry_book_document_fields(), [])

# Why: every read goes through the Field Map Cache; no positional index is ever used (BKS-1 / policy 6.2).
# Input: document and entity name. Output: list of {field name: value} for that entity's own fields.
def bks_store_rows(doc: dict, entity: str) -> List[dict]:
    fm = Core.bejson_core_get_field_map(doc)
    rtp_idx = fm[Registry.RECORD_TYPE_PARENT]
    own = [(fd.name, fm[fd.name]) for fd in Registry.bks_registry_fields(entity) if fd.name in fm]
    return [{n: row[i] for n, i in own} for row in doc.get("Values", []) if row and row[rtp_idx] == entity]

# Why: the editing helpers work on all entities at once, then write back in canonical order.
# Output: {entity: [row dicts]} for the four Book Document entities.
def bks_store_tables(doc: dict) -> Tables:
    return {e: bks_store_rows(doc, e) for e in Registry.BOOK_DOCUMENT_ENTITIES}

# Why: the single writer of Values. Rows are null-padded and grouped Book, Chapter, Generation, Export; chapters by order index.
# Input: document and tables. Effect: replaces doc["Values"] in place.
def bks_store_set_tables(doc: dict, tables: Tables) -> None:
    fm = Core.bejson_core_get_field_map(doc)
    width = len(doc["Fields"])
    values = []
    for entity in Registry.BOOK_DOCUMENT_ENTITIES:
        rows = tables.get(entity, [])
        if entity == "Chapter":
            rows = sorted(rows, key=lambda r: r[Registry.F.Chapter.chapter_order_index])
        for r in rows:
            line = [None] * width
            line[fm[Registry.RECORD_TYPE_PARENT]] = entity
            for name, val in r.items():
                line[fm[name]] = val
            values.append(line)
    doc["Values"] = values

# Why: most callers want the single Book row.
def bks_store_book(doc: dict) -> dict:
    rows = bks_store_rows(doc, "Book")
    if len(rows) != 1:
        raise Errors.BKSError(Errors.E_BKS_BOOK_COUNT, f"expected exactly 1 Book row, found {len(rows)}")
    return rows[0]

# Why: reading order of the outline (parts included).
def bks_store_chapters(doc: dict) -> List[dict]:
    return sorted(bks_store_rows(doc, "Chapter"), key=lambda r: r[Registry.F.Chapter.chapter_order_index])

# Why: nodes the model writes. Parts are structure only.
def bks_store_is_writable(chapter_row: dict) -> bool:
    return chapter_row[Registry.F.Chapter.chapter_kind_text] != "part"

# Why: a new book is created with its full outline before any model call (BKS-1 W1).
# Input: book metadata and `nodes`: ordered dicts with title, brief, optional kind (default chapter), part (title), parent_uuid, uuid, audit (default True).
# Output: new Book Document dict (not yet written). Derived values and the hash are filled by bks_store_refresh_derived.
def bks_store_create_book(*, title: str, topic: str, booktype_slug: str, author_name: str, language: str, nodes: List[dict],
                          goal: Optional[str] = None, audience: Optional[str] = None, subtitle: Optional[str] = None,
                          summary: Optional[str] = None, tags: Optional[List[str]] = None, author_uuid: Optional[str] = None,
                          booktype_uuid: Optional[str] = None, category_uuid: Optional[str] = None,
                          category_name: Optional[str] = None, plan_uuid: Optional[str] = None,
                          book_uuid: Optional[str] = None, now: Optional[str] = None) -> dict:
    B, C = Registry.F.Book, Registry.F.Chapter
    stamp = now or Derive.bks_derive_now_utc()
    book_id = book_uuid or Derive.bks_derive_new_uuid()
    book = {B.book_uuid: book_id, B.book_title_text: title, B.book_subtitle_text: subtitle, B.book_topic_text: topic,
            B.book_goal_text: goal, B.book_booktype_uuid_fk: booktype_uuid, B.book_booktype_slug_text: booktype_slug,
            B.book_author_uuid_fk: author_uuid, B.book_author_name_text: author_name,
            B.book_category_uuid_fk: category_uuid, B.book_category_name_text: category_name,
            B.book_plan_uuid_fk: plan_uuid, B.book_language_text: language, B.book_audience_text: audience,
            B.book_summary_text: summary, B.book_cover_path_text: None, B.book_tags_list: list(tags) if tags else None,
            B.book_version_text: "0.1.0", B.book_status_text: "draft", B.book_chapter_count: 0, B.book_word_count: 0,
            B.book_content_sha256_text: None, B.book_schema_version_text: Registry.BKS_SCHEMA_VERSION,
            B.book_created_at: stamp, B.book_updated_at: stamp}
    chapters: List[dict] = []
    part_ids: Dict[str, str] = {}

    def _row(uid, kind, order, title_text, brief, parent, status, audit):
        return {C.chapter_uuid: uid, C.chapter_book_uuid_fk: book_id, C.chapter_parent_uuid_fk: parent,
                C.chapter_kind_text: kind, C.chapter_order_index: order, C.chapter_title_text: title_text,
                C.chapter_brief_text: brief, C.chapter_body_md: None, C.chapter_status_text: status,
                C.chapter_word_count: 0, C.chapter_audit_enabled_flag: audit, C.chapter_audit_passed_flag: None,
                C.chapter_audit_fail_reason_text: None, C.chapter_generation_uuid_fk: None,
                C.chapter_created_at: stamp, C.chapter_updated_at: stamp}

    for node in nodes:
        part_title = node.get("part")
        if part_title and part_title not in part_ids:
            pid = Derive.bks_derive_scoped_uuid(book_id, "part:" + part_title)
            part_ids[part_title] = pid
            chapters.append(_row(pid, "part", len(chapters) + 1, part_title, None, None, "accepted", False))
        kind = node.get("kind", "chapter")
        parent = node.get("parent_uuid") or (part_ids[part_title] if part_title and kind == "chapter" else None)
        chapters.append(_row(node.get("uuid") or Derive.bks_derive_new_uuid(), kind, len(chapters) + 1,
                             node["title"], node.get("brief"), parent, "planned", bool(node.get("audit", True))))
    doc = bks_store_new_doc()
    bks_store_set_tables(doc, {"Book": [book], "Chapter": chapters})
    bks_store_refresh_derived(doc, now=stamp)
    return doc

# Why: derived values are never trusted from callers (BKS-1 R-derived); they are recomputed from bodies on every commit.
# Effect: sets chapter word counts, book chapter/word counts, content hash and updated_at.
def bks_store_refresh_derived(doc: dict, now: Optional[str] = None) -> None:
    C, B = Registry.F.Chapter, Registry.F.Book
    tables = bks_store_tables(doc)
    book = tables["Book"][0]
    rows, total = [], 0
    for ch in tables["Chapter"]:
        body = Derive.bks_derive_normalize_body(ch[C.chapter_body_md])
        ch[C.chapter_body_md] = body
        ch[C.chapter_word_count] = Derive.bks_derive_count_words(body)
        rows.append((ch[C.chapter_order_index], ch[C.chapter_uuid], ch[C.chapter_parent_uuid_fk], ch[C.chapter_kind_text],
                     ch[C.chapter_title_text], body))
        if ch[C.chapter_kind_text] != "part":
            total += ch[C.chapter_word_count]
    book[B.book_chapter_count] = sum(1 for r in rows if r[3] != "part")
    book[B.book_word_count] = total
    book[B.book_content_sha256_text] = Derive.bks_derive_content_hash(book[B.book_title_text], rows)
    if now:
        book[B.book_updated_at] = now
    bks_store_set_tables(doc, tables)

def _bump_patch(version: str) -> str:
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version)
    return f"{m.group(1)}.{m.group(2)}.{int(m.group(3)) + 1}" if m else version

def _touch_book(book: dict, stamp: str) -> bool:
    B = Registry.F.Book
    dropped = False
    if book[B.book_status_text] in ("complete", "final"):
        book[B.book_version_text] = _bump_patch(book[B.book_version_text])
        book[B.book_status_text] = "draft"
        dropped = True
    book[B.book_updated_at] = stamp
    return dropped

def _find_chapter(tables: Tables, chapter_uuid: str) -> dict:
    C = Registry.F.Chapter
    for ch in tables["Chapter"]:
        if ch[C.chapter_uuid] == chapter_uuid:
            return ch
    raise Errors.BKSError(Errors.E_BKS_FK_DANGLING, f"chapter {chapter_uuid} not found")

def _generation_row(chapter_uuid: str, attempt: int, outcome: str, started: str, finished: str, *, provider, model,
                    author_uuid, prompt_sha256, temperature, max_tokens, input_tokens, output_tokens, error_code) -> dict:
    G = Registry.F.Generation
    return {G.generation_uuid: Derive.bks_derive_new_uuid(), G.generation_target_kind_text: "chapter",
            G.generation_target_uuid_fk: chapter_uuid, G.generation_provider_text: provider, G.generation_model_text: model,
            G.generation_author_uuid_fk: author_uuid, G.generation_prompt_sha256_text: prompt_sha256,
            G.generation_temperature_value: temperature, G.generation_max_tokens_count: max_tokens,
            G.generation_input_tokens_count: input_tokens, G.generation_output_tokens_count: output_tokens,
            G.generation_attempt_index: attempt, G.generation_outcome_text: outcome, G.generation_error_code: error_code,
            G.generation_started_at: started, G.generation_finished_at: finished}

def _next_attempt(tables: Tables, chapter_uuid: str) -> int:
    G = Registry.F.Generation
    return 1 + sum(1 for g in tables["Generation"] if g[G.generation_target_uuid_fk] == chapter_uuid)

# Why: the single path that records one model attempt: stage text, run the gate, record a Generation, and set the chapter state (BKS-1 W2).
# Input: doc, chapter uuid, raw body, gate rules (None = no gate) and provenance fields.
# Output: (passed, reason). The caller then calls bks_store_commit. An accepted body is never overwritten by a failed attempt.
def bks_store_apply_attempt(doc: dict, chapter_uuid: str, body_md: Optional[str], *, rules: Optional[dict] = None,
                            provider: Optional[str] = None, model: Optional[str] = None, author_uuid: Optional[str] = None,
                            prompt_sha256: Optional[str] = None, temperature: Optional[float] = None,
                            max_tokens: Optional[int] = None, input_tokens: Optional[int] = None,
                            output_tokens: Optional[int] = None, started_at: Optional[str] = None,
                            now: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    C = Registry.F.Chapter
    stamp = now or Derive.bks_derive_now_utc()
    tables = bks_store_tables(doc)
    ch = _find_chapter(tables, chapter_uuid)
    if ch[C.chapter_kind_text] == "part":
        raise Errors.BKSError(Errors.E_BKS_STATUS_INCONSISTENT, "a part is structure only and cannot be written")
    attempt = _next_attempt(tables, chapter_uuid)
    prov = dict(provider=provider, model=model, author_uuid=author_uuid, prompt_sha256=prompt_sha256,
                temperature=temperature, max_tokens=max_tokens, input_tokens=input_tokens, output_tokens=output_tokens)
    body = Derive.bks_derive_normalize_body(body_md)
    if not body:
        tables["Generation"].append(_generation_row(chapter_uuid, attempt, "failed", started_at or stamp, stamp, error_code=None, **prov))
        bks_store_set_tables(doc, tables)
        return False, "empty response"
    ok, reason = Gates.bks_gates_evaluate(body, rules if ch[C.chapter_audit_enabled_flag] else None)
    gen = _generation_row(chapter_uuid, attempt, "accepted" if ok else "rejected", started_at or stamp, stamp, error_code=None, **prov)
    tables["Generation"].append(gen)
    if ok:
        ch[C.chapter_body_md] = body
        ch[C.chapter_status_text] = "accepted"
        ch[C.chapter_audit_passed_flag] = True if ch[C.chapter_audit_enabled_flag] else None
        ch[C.chapter_audit_fail_reason_text] = None
        ch[C.chapter_generation_uuid_fk] = gen[Registry.F.Generation.generation_uuid]
        ch[C.chapter_updated_at] = stamp
        if _touch_book(tables["Book"][0], stamp):
            tables["Export"] = []  # a draft may not carry Export rows; the files on disk are now stale
    elif ch[C.chapter_status_text] != "accepted":
        ch[C.chapter_body_md] = body
        ch[C.chapter_status_text] = "rejected"
        ch[C.chapter_audit_passed_flag] = False
        ch[C.chapter_audit_fail_reason_text] = reason
        ch[C.chapter_generation_uuid_fk] = None
        ch[C.chapter_updated_at] = stamp
    bks_store_set_tables(doc, tables)
    bks_store_refresh_derived(doc)
    return ok, reason

# Why: a provider error (no text) is still history; the chapter is left exactly as it was.
# Input: outcome is "failed" (default) or "cancelled". Effect: appends a Generation row with that outcome and the error code.
def bks_store_apply_failure(doc: dict, chapter_uuid: str, *, error_code: Optional[int] = None, provider: Optional[str] = None,
                            model: Optional[str] = None, author_uuid: Optional[str] = None, now: Optional[str] = None,
                            outcome: str = "failed") -> None:
    stamp = now or Derive.bks_derive_now_utc()
    tables = bks_store_tables(doc)
    _find_chapter(tables, chapter_uuid)
    tables["Generation"].append(_generation_row(chapter_uuid, _next_attempt(tables, chapter_uuid), outcome, stamp, stamp,
        provider=provider, model=model, author_uuid=author_uuid, prompt_sha256=None, temperature=None, max_tokens=None,
        input_tokens=None, output_tokens=None, error_code=error_code))
    bks_store_set_tables(doc, tables)

# Why: "complete" is only true when every writable node is accepted (BKS-1 C3).
def bks_store_mark_complete(doc: dict, now: Optional[str] = None) -> None:
    C, B = Registry.F.Chapter, Registry.F.Book
    tables = bks_store_tables(doc)
    pending = [c[C.chapter_title_text] for c in tables["Chapter"] if bks_store_is_writable(c) and c[C.chapter_status_text] != "accepted"]
    if pending:
        raise Errors.BKSError(Errors.E_BKS_STATUS_INCONSISTENT, f"cannot complete: not accepted: {pending}")
    tables["Book"][0][B.book_status_text] = "complete"
    tables["Book"][0][B.book_updated_at] = now or Derive.bks_derive_now_utc()
    bks_store_set_tables(doc, tables)

# Why: final locks the content hash that exports must match (BKS-1 W7).
def bks_store_finalize(doc: dict, now: Optional[str] = None) -> None:
    B = Registry.F.Book
    tables = bks_store_tables(doc)
    if tables["Book"][0][B.book_status_text] != "complete":
        raise Errors.BKSError(Errors.E_BKS_STATUS_INCONSISTENT, "only a complete book can be finalised")
    tables["Book"][0][B.book_status_text] = "final"
    tables["Book"][0][B.book_updated_at] = now or Derive.bks_derive_now_utc()
    bks_store_set_tables(doc, tables)
    bks_store_refresh_derived(doc)

# Why: reading a book never validates implicitly; callers choose a level.
# Output: document dict or None when the file is missing or unparseable.
def bks_store_load(path: str) -> Optional[dict]:
    return Core.bejson_core_load_file(path)

# Why: the one write path (BKS-1 W3/W8): recompute derived values, validate, then atomic replace under a lock. A document that fails is never written.
# Input: path, document, minimum level (3 by default; 4 is enforced automatically when Export rows exist).
# Output: the validation result. Raises BKSError with the first problem's code when refused.
def bks_store_commit(path: str, doc: dict, *, level: int = 3, now: Optional[str] = None):
    import lib_bejson_Writing_bks_validator as Validator
    bks_store_refresh_derived(doc, now=now)
    needed = 4 if bks_store_rows(doc, "Export") else level
    result = Validator.bks_validate_book(doc, level=needed)
    if result.level_reached < needed:
        first = result.problems[0]
        raise Errors.BKSError(first.code, first.message)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if not Core.bejson_core_acquire_lock(path):
        raise Errors.BKSError(Errors.E_BKS_STRUCTURE, f"could not lock {path}")
    try:
        if not Core.bejson_core_atomic_write(path, doc):
            raise Errors.BKSError(Errors.E_BKS_STRUCTURE, f"atomic write failed for {path}")
    finally:
        Core.bejson_core_release_lock(path)
    _log.info("committed %s (level %d)", path, result.level_reached)
    return result
