"""
Library:         lib_bejson_AI_brain_store.py
Family:          AI
Module Purpose:  Single writer of the Brain memory database: categories and memories, user and AI write rules, proposals, atomic batches, startup recovery.
Architecture:    BEJSON MFDB (brain_mfdb/: 104a manifest + BrainCategory and BrainMemory 104 entity files) driven through Core. One project lock (brain_state/brain.lock, outside brain_mfdb/) covers every write. A batch is copied to brain_state/txn/, applied, deep-verified and restored on failure; an interrupted batch is undone at the next open. The AI is an untrusted writer: capped priority, never pinned, user-owned memories change only through proposed revisions, nothing is hard-deleted.
Version:         1.1.0
Release_Version: 300
Date:            2026-10-24
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   a78870e1-472f-4fc9-b1b1-d1708b802608
"""

import hashlib
import json
import logging
import os
import shutil
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import lib_bejson_AI_brain_core_bridge  # noqa: F401  (puts Core on sys.path)
from lib_bejson_Core_mfdb_core import (
    mfdb_core_add_entity_record, mfdb_core_create_database, mfdb_core_deep_verify,
    mfdb_core_get_entity_doc, mfdb_core_sync_all_counts, mfdb_core_update_entity_record_bulk,
)
from lib_bejson_Core_bejson_core import ResilientPIDLock, bejson_core_atomic_write, bejson_core_get_field_map

import lib_bejson_AI_brain_audit as audit
from lib_bejson_AI_brain_errors import (
    BrainError, E_BRAIN_CATEGORY_EXISTS, E_BRAIN_CATEGORY_NOT_FOUND, E_BRAIN_CATEGORY_PROTECTED,
    E_BRAIN_CORRUPT, E_BRAIN_LIMIT_EXCEEDED, E_BRAIN_LOCK_TIMEOUT, E_BRAIN_MEMORY_INVALID,
    E_BRAIN_MEMORY_NOT_FOUND, E_BRAIN_NOT_INITIALIZED, E_BRAIN_PROPOSAL_NOT_FOUND, E_BRAIN_WRITE_FORBIDDEN,
)
from lib_bejson_AI_brain_config import brain_config_load
from lib_bejson_AI_brain_schema_registry import (
    CatF, MemF, ENTITY_CATEGORY, ENTITY_MEMORY, ENTITY_ORDER, SCHEMA_VERSION, SYSTEM_CATEGORIES, DB_NAME,
    STATUS_ACTIVE, STATUS_ARCHIVED, STATUS_PROPOSED, STATUS_REJECTED,
    ORIGIN_AI, ORIGIN_SYSTEM, ORIGIN_USER, KEYWORD_SEPARATOR,
    schema_registry_entities, schema_registry_join_keywords, schema_registry_split_keywords,
)

VERSION = "1.1.0"
RELATIONAL_ID = "89760ee8-7a87-4569-a8fe-e6a1a2ecdd7e"

ACTOR_USER = "user"
ACTOR_AI = "ai"
DB_DIRNAME = "brain_mfdb"
STATE_DIRNAME = "brain_state"
SNAPSHOT_DIRNAME = "snapshots"
MANIFEST_FILENAME = "104a.mfdb.bejson"
AI_ALLOWED_OPS = frozenset({"category_create", "memory_add", "memory_update", "memory_archive"})

_LOGGER = logging.getLogger("brain.store")


# sha256 over the Values of every entity, in registry order. Independent of file formatting, so it identifies a database *state*.
def brain_store_hash_manifest(manifest_path: str) -> str:
    digest = hashlib.sha256()
    for entity in ENTITY_ORDER:
        doc = mfdb_core_get_entity_doc(manifest_path, entity)
        digest.update(entity.encode("utf-8"))
        digest.update(json.dumps(doc.get("Values", []), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    return digest.hexdigest()


# Current UTC time at second precision.
def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


# Strips whitespace from a string value; leaves anything else alone (boundary-layer sanitisation, policy 6.2).
def _clean(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


class BrainStore:
    # One Brain database rooted at root_dir (brain_mfdb/, brain_state/, snapshots/ live directly under it).
    def __init__(self, root_dir: str | Path, config_dir: str | Path | None = None,
                 limits: dict | None = None, clock: Callable[[], datetime] | None = None):
        self.root = Path(root_dir).resolve()
        self.config_dir = Path(config_dir).resolve() if config_dir else self.root / "config"
        self.db_dir = self.root / DB_DIRNAME
        self.manifest = self.db_dir / MANIFEST_FILENAME
        self.state_dir = self.root / STATE_DIRNAME
        self.txn_dir = self.state_dir / "txn"
        self.staging_dir = self.state_dir / "staging"
        self.snapshot_dir = self.root / SNAPSHOT_DIRNAME
        self.lock_path = self.state_dir / "brain.lock"
        self._clock = clock or _utc_now
        self.limits = dict(limits) if limits is not None else brain_config_load(self.config_dir)
        self._thread_lock = threading.RLock()
        self._depth = 0
        self.generation = 0                      # bumped whenever on-disk content may have changed; caches key on it
        self.crash_hook: Callable[[str], None] | None = None   # test seam: called at named points of risky operations
        self.recovery_notices: list[str] = []
        if self.is_initialized() or self.state_dir.exists():
            self.recover()

    # ---- basics -------------------------------------------------------------------------------------------------

    def now(self) -> datetime:
        return self._clock()

    def now_text(self) -> str:
        return self.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    def is_initialized(self) -> bool:
        return self.manifest.is_file()

    def _require_init(self) -> None:
        if not self.is_initialized():
            raise BrainError(E_BRAIN_NOT_INITIALIZED, "Brain database is not initialised; run init first.", {"root": str(self.root)})

    def _crash(self, point: str) -> None:
        if self.crash_hook is not None:
            self.crash_hook(point)

    def clear_caches(self) -> None:
        self.generation += 1

    # Project lock: re-entrant inside one thread, mutual exclusion between threads and processes. Lives outside brain_mfdb/ so snapshots never contain it.
    @contextmanager
    def locked(self):
        with self._thread_lock:
            lock = None
            if self._depth == 0:
                self.state_dir.mkdir(parents=True, exist_ok=True)
                lock = ResilientPIDLock(str(self.lock_path), timeout_seconds=int(self.limits["lock_timeout_seconds"]))
                if not lock.acquire():
                    raise BrainError(E_BRAIN_LOCK_TIMEOUT, "Timed out waiting for the Brain lock.", {"lock": str(self.lock_path)})
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
                if lock is not None:
                    lock.release()

    # ---- reading ------------------------------------------------------------------------------------------------

    def _rows(self, entity: str) -> list[dict]:
        doc = mfdb_core_get_entity_doc(str(self.manifest), entity)
        fmap = bejson_core_get_field_map(doc)
        return [{name: _clean(values[index]) for name, index in fmap.items()} for values in doc["Values"]]

    def content_hash(self) -> str:
        self._require_init()
        return brain_store_hash_manifest(str(self.manifest))

    def categories(self, include_archived: bool = False) -> list[dict]:
        self._require_init()
        return [r for r in self._rows(ENTITY_CATEGORY) if include_archived or r[CatF.STATUS] != STATUS_ARCHIVED]

    def memories(self, category: str | None = None, status: str | None = None, text: str | None = None,
                 include_archived: bool = False) -> list[dict]:
        self._require_init()
        category_id = self._find_category(category)[CatF.ID] if category else None
        needle = text.casefold() if text else None
        result = []
        for row in self._rows(ENTITY_MEMORY):
            if status:
                if row[MemF.STATUS] != status:
                    continue
            elif not include_archived and row[MemF.STATUS] in (STATUS_ARCHIVED, STATUS_REJECTED):
                continue
            if category_id and row[MemF.CATEGORY_FK] != category_id:
                continue
            if needle and needle not in f"{row[MemF.TITLE]} {row[MemF.CONTENT]} {row[MemF.KEYWORDS]}".casefold():
                continue
            result.append(row)
        return result

    def get_memory(self, memory_id: str) -> dict:
        self._require_init()
        for row in self._rows(ENTITY_MEMORY):
            if row[MemF.ID] == memory_id:
                return row
        raise BrainError(E_BRAIN_MEMORY_NOT_FOUND, f"No memory with id {memory_id}.", {"id": memory_id})

    def proposals(self) -> dict:
        self._require_init()
        by_id = {r[MemF.ID]: r for r in self._rows(ENTITY_MEMORY)}
        memories = []
        for row in by_id.values():
            if row[MemF.STATUS] == STATUS_PROPOSED:
                entry = dict(row)
                target = by_id.get(row[MemF.SUPERSEDES_FK]) if row[MemF.SUPERSEDES_FK] else None
                entry["supersedes"] = dict(target) if target else None
                memories.append(entry)
        cats = [r for r in self._rows(ENTITY_CATEGORY) if r[CatF.STATUS] == STATUS_PROPOSED]
        return {"categories": cats, "memories": memories}

    def verify(self) -> list[dict]:
        self._require_init()
        return mfdb_core_deep_verify(str(self.manifest))

    def status(self) -> dict:
        self._require_init()
        from lib_bejson_AI_brain_snapshots import snapshots_list
        mems = self._rows(ENTITY_MEMORY)
        cats = self._rows(ENTITY_CATEGORY)
        snaps = snapshots_list(self)
        return {
            "root": str(self.root), "schema_version": SCHEMA_VERSION,
            "categories": sum(1 for c in cats if c[CatF.STATUS] == STATUS_ACTIVE),
            "memories_active": sum(1 for m in mems if m[MemF.STATUS] == STATUS_ACTIVE),
            "memories_pinned": sum(1 for m in mems if m[MemF.STATUS] == STATUS_ACTIVE and m[MemF.PINNED]),
            "proposals": sum(1 for m in mems if m[MemF.STATUS] == STATUS_PROPOSED) + sum(1 for c in cats if c[CatF.STATUS] == STATUS_PROPOSED),
            "write_policy": self.limits["write_policy"], "memory_mode": self.limits["memory_mode"],
            "snapshots": len(snaps), "last_snapshot": snaps[0]["created_at"] if snaps else None,
            "content_hash": self.content_hash(), "recovery_notices": list(self.recovery_notices),
        }

    # ---- writing primitives (only this module may touch the entity files) --------------------------------------

    def _insert(self, entity: str, row: dict) -> None:
        doc = mfdb_core_get_entity_doc(str(self.manifest), entity)
        values = [None] * len(doc["Fields"])
        for name, index in bejson_core_get_field_map(doc).items():
            values[index] = row.get(name)
        mfdb_core_add_entity_record(str(self.manifest), entity, values)

    def _update(self, entity: str, key_field: str, key: str, updates: dict) -> None:
        for index, row in enumerate(self._rows(entity)):
            if row[key_field] == key:
                mfdb_core_update_entity_record_bulk(str(self.manifest), entity, index, updates)
                return
        raise BrainError(E_BRAIN_CORRUPT, f"Row vanished during update: {key}")

    # ---- init ---------------------------------------------------------------------------------------------------

    # Creates the database, seeds the system categories and takes the baseline snapshot. Returns False when it already exists.
    def init(self) -> bool:
        with self.locked():
            if self.is_initialized():
                return False
            self.state_dir.mkdir(parents=True, exist_ok=True)
            mfdb_core_create_database(str(self.db_dir), DB_NAME, schema_registry_entities(),
                                      db_description="Brain memory store", schema_version=SCHEMA_VERSION)
            stamp = self.now_text()
            for spec in SYSTEM_CATEGORIES:
                self._insert(ENTITY_CATEGORY, {
                    CatF.ID: str(uuid.uuid4()), CatF.NAME: spec["name"], CatF.DESCRIPTION: spec["description"],
                    CatF.KEYWORDS: "", CatF.STATUS: STATUS_ACTIVE, CatF.ORIGIN: ORIGIN_SYSTEM,
                    CatF.PROTECTED: bool(spec["protected"]), CatF.CREATED_AT: stamp, CatF.UPDATED_AT: stamp,
                })
            mfdb_core_sync_all_counts(str(self.manifest))
            self.clear_caches()
            from lib_bejson_AI_brain_snapshots import snapshots_create
            snapshots_create(self, "default", "baseline")
            audit.brain_audit_append(self.state_dir, self.now(), ACTOR_USER, "init", "", True, "database created", int(self.limits["audit_max_rows"]))
            return True

    # ---- validation helpers -------------------------------------------------------------------------------------

    def _check_text(self, value: Any, what: str, max_chars: int, single_line: bool) -> str:
        if not isinstance(value, str) or not value.strip():
            raise BrainError(E_BRAIN_MEMORY_INVALID, f"{what} must be non-empty text.", {"field": what})
        text = value.strip()
        if len(text) > max_chars:
            raise BrainError(E_BRAIN_MEMORY_INVALID, f"{what} is {len(text)} characters; the limit is {max_chars}.", {"field": what})
        if "\x00" in text or (single_line and ("\n" in text or "\r" in text)):
            raise BrainError(E_BRAIN_MEMORY_INVALID, f"{what} contains forbidden characters.", {"field": what})
        return text

    def _check_keywords(self, raw: Any) -> list[str]:
        if raw is None:
            return []
        items = raw.replace(",", KEYWORD_SEPARATOR).split(KEYWORD_SEPARATOR) if isinstance(raw, str) else list(raw)
        low, high = int(self.limits["keyword_min_chars"]), int(self.limits["keyword_max_chars"])
        seen, result = set(), []
        for item in items:
            word = str(item).strip().casefold()
            if not word:
                continue
            if not low <= len(word) <= high or KEYWORD_SEPARATOR in word or "\n" in word:
                raise BrainError(E_BRAIN_MEMORY_INVALID, f"Keyword '{word}' must be {low}-{high} characters.", {"keyword": word})
            if word not in seen:
                seen.add(word)
                result.append(word)
        if len(result) > int(self.limits["max_keywords"]):
            raise BrainError(E_BRAIN_LIMIT_EXCEEDED, f"At most {self.limits['max_keywords']} keywords per memory.", {"count": len(result)})
        return result

    @staticmethod
    def _check_priority(value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
            raise BrainError(E_BRAIN_MEMORY_INVALID, "Priority must be an integer from 0 to 100.", {"value": value})
        return value

    @staticmethod
    def _check_confidence(value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise BrainError(E_BRAIN_MEMORY_INVALID, "Confidence must be a number from 0 to 1.", {"value": value})
        return float(value)

    def _find_category(self, ref: str, include_archived: bool = False) -> dict:
        rows = self._rows(ENTITY_CATEGORY)
        for row in rows:
            if row[CatF.ID] == ref and (include_archived or row[CatF.STATUS] != STATUS_ARCHIVED):
                return row
        wanted = str(ref).strip().casefold()
        for row in rows:
            if row[CatF.NAME].casefold() == wanted and row[CatF.STATUS] != STATUS_ARCHIVED:
                return row
        raise BrainError(E_BRAIN_CATEGORY_NOT_FOUND, f"No category '{ref}'.", {"category": ref})

    def _live_memory(self, memory_id: str) -> dict:
        row = self.get_memory(memory_id)
        if row[MemF.STATUS] == STATUS_REJECTED:
            raise BrainError(E_BRAIN_MEMORY_NOT_FOUND, f"Memory {memory_id} was rejected.", {"id": memory_id})
        return row

    def _count_memories(self) -> int:
        return sum(1 for r in self._rows(ENTITY_MEMORY) if r[MemF.STATUS] in (STATUS_ACTIVE, STATUS_PROPOSED))

    # ---- operations ---------------------------------------------------------------------------------------------

    def _ai_applies_directly(self, priority: int) -> bool:
        """write_policy open: every AI write applies; auto: only priority <= auto_max_priority; review: none."""
        policy = self.limits["write_policy"]
        return policy == "open" or (policy == "auto" and priority <= int(self.limits["auto_max_priority"]))

    def _op_category_create(self, op: dict, actor: str) -> dict:
        name = self._check_text(op.get("name"), "Category name", int(self.limits["max_category_name_chars"]), True)
        description = self._check_text(op.get("description") or name, "Category description", int(self.limits["max_content_chars"]), False)
        keywords = self._check_keywords(op.get("keywords"))
        rows = self._rows(ENTITY_CATEGORY)
        live = [r for r in rows if r[CatF.STATUS] != STATUS_ARCHIVED]
        if any(r[CatF.NAME].casefold() == name.casefold() for r in live):
            raise BrainError(E_BRAIN_CATEGORY_EXISTS, f"Category '{name}' already exists.", {"name": name})
        if len(live) >= int(self.limits["max_categories"]):
            raise BrainError(E_BRAIN_LIMIT_EXCEEDED, f"At most {self.limits['max_categories']} categories.", {"count": len(live)})
        status = STATUS_ACTIVE
        if actor == ACTOR_AI and self.limits["write_policy"] != "open":
            status = STATUS_PROPOSED
            if sum(1 for r in live if r[CatF.STATUS] == STATUS_PROPOSED and r[CatF.ORIGIN] == ORIGIN_AI) >= int(self.limits["max_ai_proposed_categories"]):
                raise BrainError(E_BRAIN_LIMIT_EXCEEDED, "Too many AI category proposals are waiting for review.")
        stamp = self.now_text()
        new_id = str(uuid.uuid4())
        self._insert(ENTITY_CATEGORY, {
            CatF.ID: new_id, CatF.NAME: name, CatF.DESCRIPTION: description,
            CatF.KEYWORDS: schema_registry_join_keywords(keywords), CatF.STATUS: status,
            CatF.ORIGIN: ORIGIN_AI if actor == ACTOR_AI else ORIGIN_USER, CatF.PROTECTED: False,
            CatF.CREATED_AT: stamp, CatF.UPDATED_AT: stamp,
        })
        return {"op": "category_create", "id": new_id, "status": status}

    def _op_category_archive(self, op: dict, actor: str) -> dict:
        row = self._find_category(op.get("id") or op.get("category"))
        if row[CatF.PROTECTED]:
            raise BrainError(E_BRAIN_CATEGORY_PROTECTED, f"Category '{row[CatF.NAME]}' is protected.", {"id": row[CatF.ID]})
        if any(m[MemF.CATEGORY_FK] == row[CatF.ID] and m[MemF.STATUS] in (STATUS_ACTIVE, STATUS_PROPOSED) for m in self._rows(ENTITY_MEMORY)):
            raise BrainError(E_BRAIN_MEMORY_INVALID, f"Category '{row[CatF.NAME]}' still has memories; archive or move them first.", {"id": row[CatF.ID]})
        self._update(ENTITY_CATEGORY, CatF.ID, row[CatF.ID], {CatF.STATUS: STATUS_ARCHIVED, CatF.UPDATED_AT: self.now_text()})
        return {"op": "category_archive", "id": row[CatF.ID], "status": STATUS_ARCHIVED}

    def _memory_fields(self, source: dict, actor: str, defaults: dict) -> dict:
        # Validated memory field values from an op payload; unspecified ones come from `defaults`.
        values = dict(defaults)
        if "title" in source:
            values[MemF.TITLE] = self._check_text(source["title"], "Title", int(self.limits["max_title_chars"]), True)
        if "content" in source:
            values[MemF.CONTENT] = self._check_text(source["content"], "Content", int(self.limits["max_content_chars"]), False)
        if "keywords" in source:
            values[MemF.KEYWORDS] = schema_registry_join_keywords(self._check_keywords(source["keywords"]))
        if "priority" in source:
            values[MemF.PRIORITY] = self._check_priority(source["priority"])
        if "confidence" in source:
            values[MemF.CONFIDENCE] = self._check_confidence(source["confidence"])
        if actor == ACTOR_AI:
            values[MemF.PRIORITY] = min(values[MemF.PRIORITY], int(self.limits["ai_max_priority"]))
        return values

    def _op_memory_add(self, op: dict, actor: str) -> dict:
        category = self._find_category(op.get("category") or "General")
        if actor == ACTOR_AI and category[CatF.STATUS] == STATUS_PROPOSED and category[CatF.ORIGIN] != ORIGIN_AI:
            raise BrainError(E_BRAIN_WRITE_FORBIDDEN, "AI cannot add to that category.")
        if category[CatF.STATUS] not in (STATUS_ACTIVE, STATUS_PROPOSED):
            raise BrainError(E_BRAIN_CATEGORY_NOT_FOUND, f"Category '{category[CatF.NAME]}' is not available.")
        defaults = {MemF.PRIORITY: 30 if actor == ACTOR_AI else 50, MemF.CONFIDENCE: 0.7 if actor == ACTOR_AI else 1.0,
                    MemF.KEYWORDS: category[CatF.KEYWORDS] or ""}
        if "title" not in op or "content" not in op:
            raise BrainError(E_BRAIN_MEMORY_INVALID, "A memory needs a title and content.")
        values = self._memory_fields(op, actor, defaults)
        title = values[MemF.TITLE]
        for row in self._rows(ENTITY_MEMORY):
            if row[MemF.CATEGORY_FK] == category[CatF.ID] and row[MemF.STATUS] in (STATUS_ACTIVE, STATUS_PROPOSED) \
                    and row[MemF.SUPERSEDES_FK] is None and row[MemF.TITLE].casefold() == title.casefold():
                if actor == ACTOR_AI:
                    patch = {k: op[k] for k in ("title", "content", "keywords", "priority", "confidence") if k in op}
                    return self._op_memory_update({"id": row[MemF.ID], "fields": patch}, actor)
                raise BrainError(E_BRAIN_MEMORY_INVALID, f"A memory titled '{title}' already exists in this category.", {"id": row[MemF.ID]})
        if self._count_memories() >= int(self.limits["max_memories"]):
            raise BrainError(E_BRAIN_LIMIT_EXCEEDED, f"At most {self.limits['max_memories']} memories.")
        pinned = bool(op.get("pinned", False)) and actor == ACTOR_USER
        status = STATUS_ACTIVE
        if actor == ACTOR_AI:
            auto = self._ai_applies_directly(values[MemF.PRIORITY]) and category[CatF.STATUS] == STATUS_ACTIVE
            status = STATUS_ACTIVE if auto else STATUS_PROPOSED
        stamp = self.now_text()
        new_id = str(uuid.uuid4())
        self._insert(ENTITY_MEMORY, {
            MemF.ID: new_id, MemF.CATEGORY_FK: category[CatF.ID], MemF.TITLE: title, MemF.CONTENT: values[MemF.CONTENT],
            MemF.KEYWORDS: values[MemF.KEYWORDS], MemF.PRIORITY: values[MemF.PRIORITY], MemF.CONFIDENCE: values[MemF.CONFIDENCE],
            MemF.STATUS: status, MemF.ORIGIN: ORIGIN_AI if actor == ACTOR_AI else ORIGIN_USER, MemF.PINNED: pinned,
            MemF.LOCKED: False, MemF.SUPERSEDES_FK: None, MemF.CREATED_AT: stamp, MemF.UPDATED_AT: stamp, MemF.LAST_RECALLED_AT: None,
        })
        return {"op": "memory_add", "id": new_id, "status": status}

    def _op_memory_update(self, op: dict, actor: str) -> dict:
        target = self._live_memory(op.get("id"))
        if target[MemF.STATUS] == STATUS_ARCHIVED and actor == ACTOR_AI:
            raise BrainError(E_BRAIN_MEMORY_NOT_FOUND, f"Memory {target[MemF.ID]} is archived.")
        fields = dict(op.get("fields") or {})
        defaults = {MemF.TITLE: target[MemF.TITLE], MemF.CONTENT: target[MemF.CONTENT], MemF.KEYWORDS: target[MemF.KEYWORDS],
                    MemF.PRIORITY: target[MemF.PRIORITY], MemF.CONFIDENCE: target[MemF.CONFIDENCE]}
        values = self._memory_fields(fields, actor, defaults)
        if "category" in fields:
            category = self._find_category(fields["category"])
            values[MemF.CATEGORY_FK] = category[CatF.ID]
        stamp = self.now_text()
        if actor == ACTOR_USER:
            updates = {k: v for k, v in values.items()}
            updates[MemF.ORIGIN] = ORIGIN_USER
            updates[MemF.LOCKED] = bool(fields.get("locked", True))
            if "pinned" in fields:
                updates[MemF.PINNED] = bool(fields["pinned"])
            if fields.get("status") in (STATUS_ACTIVE, STATUS_ARCHIVED):
                updates[MemF.STATUS] = fields["status"]
            updates[MemF.UPDATED_AT] = stamp
            self._update(ENTITY_MEMORY, MemF.ID, target[MemF.ID], updates)
            return {"op": "memory_update", "id": target[MemF.ID], "status": updates.get(MemF.STATUS, target[MemF.STATUS])}
        # AI writer
        in_place_ok = (target[MemF.ORIGIN] == ORIGIN_AI and not target[MemF.LOCKED] and not target[MemF.PINNED]
                       and target[MemF.SUPERSEDES_FK] is None)
        if target[MemF.STATUS] == STATUS_PROPOSED and in_place_ok:
            self._update(ENTITY_MEMORY, MemF.ID, target[MemF.ID], {**values, MemF.UPDATED_AT: stamp})
            return {"op": "memory_update", "id": target[MemF.ID], "status": STATUS_PROPOSED}
        auto = self._ai_applies_directly(values[MemF.PRIORITY])
        if in_place_ok and auto and target[MemF.STATUS] == STATUS_ACTIVE:
            self._update(ENTITY_MEMORY, MemF.ID, target[MemF.ID], {**values, MemF.UPDATED_AT: stamp})
            return {"op": "memory_update", "id": target[MemF.ID], "status": STATUS_ACTIVE}
        # Revision proposal: a separate proposed row that points at the target.
        for row in self._rows(ENTITY_MEMORY):
            if row[MemF.SUPERSEDES_FK] == target[MemF.ID] and row[MemF.STATUS] == STATUS_PROPOSED:
                self._update(ENTITY_MEMORY, MemF.ID, row[MemF.ID], {**values, MemF.UPDATED_AT: stamp})
                return {"op": "memory_update", "id": row[MemF.ID], "status": STATUS_PROPOSED, "revision_of": target[MemF.ID]}
        if self._count_memories() >= int(self.limits["max_memories"]):
            raise BrainError(E_BRAIN_LIMIT_EXCEEDED, f"At most {self.limits['max_memories']} memories.")
        new_id = str(uuid.uuid4())
        self._insert(ENTITY_MEMORY, {
            MemF.ID: new_id, MemF.CATEGORY_FK: values.get(MemF.CATEGORY_FK, target[MemF.CATEGORY_FK]), MemF.TITLE: values[MemF.TITLE],
            MemF.CONTENT: values[MemF.CONTENT], MemF.KEYWORDS: values[MemF.KEYWORDS], MemF.PRIORITY: values[MemF.PRIORITY],
            MemF.CONFIDENCE: values[MemF.CONFIDENCE], MemF.STATUS: STATUS_PROPOSED, MemF.ORIGIN: ORIGIN_AI, MemF.PINNED: False,
            MemF.LOCKED: False, MemF.SUPERSEDES_FK: target[MemF.ID], MemF.CREATED_AT: stamp, MemF.UPDATED_AT: stamp,
            MemF.LAST_RECALLED_AT: None,
        })
        return {"op": "memory_update", "id": new_id, "status": STATUS_PROPOSED, "revision_of": target[MemF.ID]}

    def _op_memory_archive(self, op: dict, actor: str) -> dict:
        target = self._live_memory(op.get("id"))
        if actor == ACTOR_AI and (target[MemF.ORIGIN] != ORIGIN_AI or target[MemF.LOCKED] or target[MemF.PINNED]):
            raise BrainError(E_BRAIN_WRITE_FORBIDDEN, "AI cannot archive a memory the user owns, locked or pinned.", {"id": target[MemF.ID]})
        stamp = self.now_text()
        self._update(ENTITY_MEMORY, MemF.ID, target[MemF.ID], {MemF.STATUS: STATUS_ARCHIVED, MemF.UPDATED_AT: stamp})
        for row in self._rows(ENTITY_MEMORY):
            if row[MemF.SUPERSEDES_FK] == target[MemF.ID] and row[MemF.STATUS] == STATUS_PROPOSED:
                self._update(ENTITY_MEMORY, MemF.ID, row[MemF.ID], {MemF.STATUS: STATUS_REJECTED, MemF.UPDATED_AT: stamp})
        return {"op": "memory_archive", "id": target[MemF.ID], "status": STATUS_ARCHIVED}

    def _op_memory_pin(self, op: dict, actor: str) -> dict:
        target = self._live_memory(op.get("id"))
        pinned = bool(op.get("pinned", True))
        self._update(ENTITY_MEMORY, MemF.ID, target[MemF.ID], {MemF.PINNED: pinned, MemF.UPDATED_AT: self.now_text()})
        return {"op": "memory_pin", "id": target[MemF.ID], "pinned": pinned}

    def _op_proposal_approve(self, op: dict, actor: str) -> dict:
        proposal_id = op.get("id")
        stamp = self.now_text()
        for cat in self._rows(ENTITY_CATEGORY):
            if cat[CatF.ID] == proposal_id and cat[CatF.STATUS] == STATUS_PROPOSED:
                self._update(ENTITY_CATEGORY, CatF.ID, proposal_id, {CatF.STATUS: STATUS_ACTIVE, CatF.UPDATED_AT: stamp})
                return {"op": "proposal_approve", "id": proposal_id, "status": STATUS_ACTIVE, "kind": "category"}
        row = next((r for r in self._rows(ENTITY_MEMORY) if r[MemF.ID] == proposal_id and r[MemF.STATUS] == STATUS_PROPOSED), None)
        if row is None:
            raise BrainError(E_BRAIN_PROPOSAL_NOT_FOUND, f"No pending proposal {proposal_id}.", {"id": proposal_id})
        category = self._find_category(row[MemF.CATEGORY_FK])
        if category[CatF.STATUS] != STATUS_ACTIVE:
            raise BrainError(E_BRAIN_MEMORY_INVALID, f"Approve the category '{category[CatF.NAME]}' first.", {"category": category[CatF.ID]})
        if row[MemF.SUPERSEDES_FK]:
            target = self._live_memory(row[MemF.SUPERSEDES_FK])
            self._update(ENTITY_MEMORY, MemF.ID, target[MemF.ID], {
                MemF.CATEGORY_FK: row[MemF.CATEGORY_FK], MemF.TITLE: row[MemF.TITLE], MemF.CONTENT: row[MemF.CONTENT],
                MemF.KEYWORDS: row[MemF.KEYWORDS], MemF.PRIORITY: row[MemF.PRIORITY], MemF.CONFIDENCE: row[MemF.CONFIDENCE],
                MemF.UPDATED_AT: stamp})
            self._update(ENTITY_MEMORY, MemF.ID, proposal_id, {MemF.STATUS: STATUS_ARCHIVED, MemF.UPDATED_AT: stamp})
            return {"op": "proposal_approve", "id": target[MemF.ID], "status": STATUS_ACTIVE, "kind": "revision"}
        self._update(ENTITY_MEMORY, MemF.ID, proposal_id, {MemF.STATUS: STATUS_ACTIVE, MemF.UPDATED_AT: stamp})
        return {"op": "proposal_approve", "id": proposal_id, "status": STATUS_ACTIVE, "kind": "memory"}

    def _op_proposal_reject(self, op: dict, actor: str) -> dict:
        proposal_id = op.get("id")
        stamp = self.now_text()
        for cat in self._rows(ENTITY_CATEGORY):
            if cat[CatF.ID] == proposal_id and cat[CatF.STATUS] == STATUS_PROPOSED:
                self._update(ENTITY_CATEGORY, CatF.ID, proposal_id, {CatF.STATUS: STATUS_ARCHIVED, CatF.UPDATED_AT: stamp})
                for mem in self._rows(ENTITY_MEMORY):
                    if mem[MemF.CATEGORY_FK] == proposal_id and mem[MemF.STATUS] == STATUS_PROPOSED:
                        self._update(ENTITY_MEMORY, MemF.ID, mem[MemF.ID], {MemF.STATUS: STATUS_REJECTED, MemF.UPDATED_AT: stamp})
                return {"op": "proposal_reject", "id": proposal_id, "status": STATUS_ARCHIVED, "kind": "category"}
        row = next((r for r in self._rows(ENTITY_MEMORY) if r[MemF.ID] == proposal_id and r[MemF.STATUS] == STATUS_PROPOSED), None)
        if row is None:
            raise BrainError(E_BRAIN_PROPOSAL_NOT_FOUND, f"No pending proposal {proposal_id}.", {"id": proposal_id})
        self._update(ENTITY_MEMORY, MemF.ID, proposal_id, {MemF.STATUS: STATUS_REJECTED, MemF.UPDATED_AT: stamp})
        return {"op": "proposal_reject", "id": proposal_id, "status": STATUS_REJECTED, "kind": "memory"}

    _OPS = {
        "category_create": "_op_category_create", "category_archive": "_op_category_archive",
        "memory_add": "_op_memory_add", "memory_update": "_op_memory_update", "memory_archive": "_op_memory_archive",
        "memory_pin": "_op_memory_pin", "proposal_approve": "_op_proposal_approve", "proposal_reject": "_op_proposal_reject",
    }

    # ---- batch transaction --------------------------------------------------------------------------------------

    # Applies ops in order as one all-or-nothing transaction. Returns one result dict per op.
    def apply_batch(self, ops: list[dict], actor: str = ACTOR_USER) -> list[dict]:
        self._require_init()
        if actor not in (ACTOR_USER, ACTOR_AI):
            raise BrainError(E_BRAIN_WRITE_FORBIDDEN, f"Unknown actor '{actor}'.")
        if not ops:
            return []
        for op in ops:
            if op.get("op") not in self._OPS:
                raise BrainError(E_BRAIN_MEMORY_INVALID, f"Unknown operation '{op.get('op')}'.", {"op": op.get("op")})
            if actor == ACTOR_AI and op["op"] not in AI_ALLOWED_OPS:
                raise BrainError(E_BRAIN_WRITE_FORBIDDEN, f"AI may not run '{op['op']}'.", {"op": op["op"]})
        if actor == ACTOR_AI:
            if len(ops) > int(self.limits["max_commands_per_batch"]):
                raise BrainError(E_BRAIN_LIMIT_EXCEEDED, f"At most {self.limits['max_commands_per_batch']} commands per batch.")
            if audit.brain_audit_count_ai_writes(self.state_dir, self.now()) + len(ops) > int(self.limits["max_ai_writes_per_hour"]):
                raise BrainError(E_BRAIN_LIMIT_EXCEEDED, f"AI write limit of {self.limits['max_ai_writes_per_hour']} per hour reached.")
        from lib_bejson_AI_brain_snapshots import snapshots_create_if_changed, snapshots_maintain
        with self.locked():
            snapshots_create_if_changed(self, "default", f"before {actor} batch of {len(ops)}")
            pre_dir = self.txn_dir / "pre"
            if self.txn_dir.exists():
                shutil.rmtree(self.txn_dir)
            self.txn_dir.mkdir(parents=True)
            shutil.copytree(self.db_dir, pre_dir)
            self._crash("after_txn_copy")
            bejson_core_atomic_write(str(self.txn_dir / "state.json"), {"state": "applying", "actor": actor, "ops": len(ops)})
            results: list[dict] = []
            try:
                for op in ops:
                    results.append(getattr(self, self._OPS[op["op"]])(op, actor))
                    self._crash("mid_apply")
                mfdb_core_sync_all_counts(str(self.manifest))
                findings = [f for f in mfdb_core_deep_verify(str(self.manifest)) if "error" in f]
                if findings:
                    raise BrainError(E_BRAIN_CORRUPT, "Verification failed after applying the batch.", {"findings": findings})
            except Exception as exc:
                self._restore_from_txn()
                self.clear_caches()
                err = exc if isinstance(exc, BrainError) else BrainError(E_BRAIN_CORRUPT, f"Unexpected failure: {exc}")
                for op in ops:
                    audit.brain_audit_append(self.state_dir, self.now(), actor, f"write-failed:{op['op']}", str(op.get("id", "")),
                                             False, err.name, int(self.limits["audit_max_rows"]))
                if err is exc:
                    raise
                raise err from exc
            shutil.rmtree(self.txn_dir, ignore_errors=True)
            self.clear_caches()
            for op, res in zip(ops, results):
                audit.brain_audit_append(self.state_dir, self.now(), actor, f"write:{op['op']}", str(res.get("id", "")),
                                         True, str(res.get("status", "")), int(self.limits["audit_max_rows"]))
            snapshots_maintain(self)
            return results

    # Convenience single-operation wrapper.
    def apply(self, op: dict, actor: str = ACTOR_USER) -> dict:
        return self.apply_batch([op], actor)[0]

    # ---- restore / recovery -------------------------------------------------------------------------------------

    def _restore_from_txn(self) -> None:
        pre_dir = self.txn_dir / "pre"
        if pre_dir.is_dir():
            if self.db_dir.exists():
                shutil.rmtree(self.db_dir)
            os.replace(pre_dir, self.db_dir)
        shutil.rmtree(self.txn_dir, ignore_errors=True)

    # Replaces brain_mfdb/ with new_dir by two renames; recover() finishes or undoes the swap after a crash between them.
    def swap_in_directory(self, new_dir: Path) -> None:
        old_dir = self.db_dir.with_name(DB_DIRNAME + ".old")
        if old_dir.exists():
            shutil.rmtree(old_dir)
        os.replace(self.db_dir, old_dir)
        self._crash("swap_between_renames")
        os.replace(new_dir, self.db_dir)
        self._crash("swap_after_renames")
        shutil.rmtree(old_dir, ignore_errors=True)
        self.clear_caches()

    # Startup recovery: undo an interrupted batch, finish or undo an interrupted swap, drop stale staging. Returns notices.
    def recover(self) -> list[str]:
        notices: list[str] = []
        with self.locked():
            if self.txn_dir.exists():
                state_file = self.txn_dir / "state.json"
                if state_file.is_file() and (self.txn_dir / "pre").is_dir():
                    self._restore_from_txn()
                    notices.append("An interrupted write was undone; the database is back to its state before that write.")
                else:
                    shutil.rmtree(self.txn_dir, ignore_errors=True)
                    notices.append("Discarded an incomplete write preparation (the database was untouched).")
            old_dir = self.db_dir.with_name(DB_DIRNAME + ".old")
            if old_dir.exists():
                if not self.db_dir.exists():
                    os.replace(old_dir, self.db_dir)
                    notices.append("An interrupted rollback was undone; the database is unchanged.")
                else:
                    shutil.rmtree(old_dir, ignore_errors=True)
                    notices.append("Finished an interrupted rollback cleanup.")
            if self.staging_dir.exists():
                shutil.rmtree(self.staging_dir, ignore_errors=True)
            if notices:
                self.clear_caches()
                for note in notices:
                    _LOGGER.warning("Brain recovery: %s", note)
                    audit.brain_audit_append(self.state_dir, self.now(), ACTOR_USER, "recovery", "", True, note, int(self.limits["audit_max_rows"]))
        self.recovery_notices.extend(notices)
        return notices
