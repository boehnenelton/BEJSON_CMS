"""
Library:         lib_bejson_Writing_bks_validator.py
Family:          Writing
Module Purpose:  Conformance levels C1-C4 for Book Documents and the plan check P for JobMaker plans.
Architecture:    BKS-1 (BEJSON Book Standard) Writing family. Non-AI book organisation layer built on the frozen Core family (field-map cache, atomic write, validator, list validator). Contains no AI calls and no Flask code. Book Documents are BEJSON 104db; plans are the JobMaker 104a job schema.
Format_Scope:    104db (Book Document) | 104a (JobMaker plan)
Release_Version: 300
Version:         see VERSION below
Date:            2026-10-29
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   cab7879f-bc7a-4237-82db-12fe1de4f5ad
"""

from typing import Dict, List, NamedTuple, Optional

import lib_bejson_Core_bejson_core as Core
import lib_bejson_Core_bejson_list_validator as ListValidator
import lib_bejson_Core_bejson_validator as CoreValidator
import lib_bejson_Writing_bks_derive as Derive
import lib_bejson_Writing_bks_errors as E
import lib_bejson_Writing_bks_plan as Plan
import lib_bejson_Writing_bks_registry as Registry
import lib_bejson_Writing_bks_store as Store

VERSION = "1.0.0"

class BKSProblem(NamedTuple):
    code: int
    name: str
    message: str
    level: str
    location: str

class BKSResult:
    """Outcome of a check run. level_reached is the highest conformance level fully passed (0 = none)."""

    def __init__(self) -> None:
        self.problems: List[BKSProblem] = []
        self.warnings: List[str] = []
        self.level_reached = 0

    @property
    def ok(self) -> bool:
        return not self.problems

    def codes(self) -> List[int]:
        return [p.code for p in self.problems]

    def add(self, code: int, message: str, level: str, location: str = "") -> None:
        self.problems.append(BKSProblem(code, E.bks_errors_name_for(code), message, level, location))

def _suffix_rules(name: str, value: object, res: BKSResult, where: str) -> None:
    if value is None:
        return
    if isinstance(value, str) and value == "":
        res.add(E.E_BKS_EMPTY_STRING, f"{name} is an empty string (use null)", "C1", where)
        return
    if (name.endswith("_uuid") or name.endswith("_uuid_fk")) and not Derive.bks_derive_is_uuid(value):
        res.add(E.E_BKS_UUID_INVALID, f"{name} is not a canonical UUID: {value!r}", "C1", where)
    elif name.endswith("_at") and not Derive.bks_derive_is_timestamp(value):
        res.add(E.E_BKS_TIMESTAMP_INVALID, f"{name} is not a UTC timestamp: {value!r}", "C1", where)
    elif name.endswith("_path_text") and not Derive.bks_derive_is_relative_path(value):
        res.add(E.E_BKS_PATH_INVALID, f"{name} is not a relative path: {value!r}", "C1", where)

def _check_rows(entity: str, rows: List[dict], res: BKSResult) -> None:
    defs = Registry.bks_registry_fields(entity)
    for i, row in enumerate(rows):
        where = f"{entity}[{i}]"
        for fd in defs:
            val = row[fd.name]
            if val is None:
                if fd.required:
                    res.add(E.E_BKS_REQUIRED_NULL, f"{fd.name} is required", "C1", where)
                continue
            if fd.enum and val not in fd.enum:
                res.add(E.E_BKS_ENUM_INVALID, f"{fd.name}={val!r} not in {list(fd.enum)}", "C1", where)
            _suffix_rules(fd.name, val, res, where)

def _check_c1(doc: dict, res: BKSResult) -> Optional[Dict[str, List[dict]]]:
    core = CoreValidator.validate_bejson(doc, is_file=False)
    if not core.valid:
        for msg in core.errors[:5]:
            res.add(E.E_BKS_STRUCTURE, str(msg), "C1")
        return None
    expected = Registry.bks_registry_book_document_fields()
    if doc.get("Format_Version") != "104db" or doc.get("Records_Type") != list(Registry.BOOK_DOCUMENT_ENTITIES) or doc.get("Fields") != expected:
        have = [f.get("name") for f in doc.get("Fields", [])]
        want = [f["name"] for f in expected]
        diff = next((f"{h!r} != {w!r}" for h, w in zip(have, want) if h != w), f"{len(have)} fields, expected {len(want)}")
        res.add(E.E_BKS_SCHEMA_MISMATCH, f"Fields/Records_Type differ from the registry ({diff})", "C1")
        return None
    tables = Store.bks_store_tables(doc)
    if len(tables["Book"]) != 1:
        res.add(E.E_BKS_BOOK_COUNT, f"expected exactly 1 Book row, found {len(tables['Book'])}", "C1")
        return None
    version = tables["Book"][0][Registry.F.Book.book_schema_version_text]
    if not isinstance(version, str) or not version.startswith(Registry.BKS_SCHEMA_PREFIX):
        res.add(E.E_BKS_VERSION_UNSUPPORTED, f"unsupported schema version {version!r}", "C1")
    for entity in Registry.BOOK_DOCUMENT_ENTITIES:
        _check_rows(entity, tables[entity], res)
    return tables

def _check_c2(tables: Dict[str, List[dict]], res: BKSResult) -> None:
    B, C, G, X = Registry.F.Book, Registry.F.Chapter, Registry.F.Generation, Registry.F.Export
    book = tables["Book"][0]
    book_id = book[B.book_uuid]
    chapters, gens = tables["Chapter"], tables["Generation"]
    start = len(res.problems)
    for entity in Registry.BOOK_DOCUMENT_ENTITIES:
        pk = Registry.bks_registry_primary_key(entity)
        seen = set()
        for row in tables[entity]:
            if row[pk] in seen:
                res.add(E.E_BKS_PK_DUPLICATE, f"duplicate {pk}: {row[pk]}", "C2", entity)
            seen.add(row[pk])
    chapter_ids = {c[C.chapter_uuid]: c for c in chapters}
    gen_ids = {g[G.generation_uuid]: g for g in gens}
    for c in chapters:
        if c[C.chapter_book_uuid_fk] != book_id:
            res.add(E.E_BKS_FK_DANGLING, f"chapter {c[C.chapter_uuid]} points at another book", "C2")
        parent = c[C.chapter_parent_uuid_fk]
        if parent is not None and parent not in chapter_ids:
            res.add(E.E_BKS_FK_DANGLING, f"chapter {c[C.chapter_uuid]} parent {parent} not found", "C2")
        gfk = c[C.chapter_generation_uuid_fk]
        if gfk is not None and gfk not in gen_ids:
            res.add(E.E_BKS_FK_DANGLING, f"chapter {c[C.chapter_uuid]} generation {gfk} not found", "C2")
    for g in gens:
        if g[G.generation_target_kind_text] == "chapter" and g[G.generation_target_uuid_fk] not in chapter_ids:
            res.add(E.E_BKS_FK_DANGLING, f"generation {g[G.generation_uuid]} targets a missing chapter", "C2")
    for x in tables["Export"]:
        if x[X.export_book_uuid_fk] != book_id:
            res.add(E.E_BKS_FK_DANGLING, f"export {x[X.export_uuid]} points at another book", "C2")
    if len(res.problems) == start:
        projection = Core.bejson_core_create_104a("ListItem", [{"name": "id", "type": "string"}, {"name": "parent_id", "type": "string"}],
                                                   [[c[C.chapter_uuid], c[C.chapter_parent_uuid_fk]] for c in chapters])
        tree = ListValidator.validate_list(projection)
        if not tree["is_valid"]:
            res.add(E.E_BKS_OUTLINE_INVALID, "; ".join(str(e) for e in tree["errors"]), "C2")
    orders = [c[C.chapter_order_index] for c in chapters]
    if sorted(orders) != list(range(1, len(chapters) + 1)):
        res.add(E.E_BKS_ORDER_INVALID, f"chapter_order_index must be 1..{len(chapters)} without gaps or repeats", "C2")
    for c in chapters:
        kind, parent = c[C.chapter_kind_text], chapter_ids.get(c[C.chapter_parent_uuid_fk])
        parent_kind = parent[C.chapter_kind_text] if parent else None
        ok = (kind in ("part", "front", "back") and parent is None) or (kind == "chapter" and parent_kind in (None, "part")) or (kind == "section" and parent_kind == "chapter")
        if not ok and (c[C.chapter_parent_uuid_fk] is None or parent is not None):
            res.add(E.E_BKS_PARENT_KIND, f"{kind} '{c[C.chapter_title_text]}' has an invalid parent ({parent_kind})", "C2")
    for c in chapters:
        body = c[C.chapter_body_md]
        if c[C.chapter_word_count] != Derive.bks_derive_count_words(body):
            res.add(E.E_BKS_DERIVED_MISMATCH, f"word_count of '{c[C.chapter_title_text]}' is {c[C.chapter_word_count]}, body has {Derive.bks_derive_count_words(body)}", "C2")
    writable = [c for c in chapters if c[C.chapter_kind_text] != "part"]
    if book[B.book_chapter_count] != len(writable):
        res.add(E.E_BKS_DERIVED_MISMATCH, f"book_chapter_count {book[B.book_chapter_count]} != {len(writable)}", "C2")
    if book[B.book_word_count] != sum(c[C.chapter_word_count] for c in writable):
        res.add(E.E_BKS_DERIVED_MISMATCH, "book_word_count differs from the sum of chapter word counts", "C2")

def _check_c3(tables: Dict[str, List[dict]], res: BKSResult) -> None:
    B, C, G = Registry.F.Book, Registry.F.Chapter, Registry.F.Generation
    book = tables["Book"][0]
    gens = {g[G.generation_uuid]: g for g in tables["Generation"]}
    for c in tables["Chapter"]:
        kind, status, body, title = c[C.chapter_kind_text], c[C.chapter_status_text], c[C.chapter_body_md], c[C.chapter_title_text]
        if kind == "part":
            if body is not None or status != "accepted":
                res.add(E.E_BKS_STATUS_INCONSISTENT, f"part '{title}' must be accepted with no body", "C3")
            continue
        if status == "planned" and body is not None:
            res.add(E.E_BKS_STATUS_INCONSISTENT, f"'{title}' is planned but has a body", "C3")
        if status in ("drafted", "accepted", "rejected") and body is None:
            res.add(E.E_BKS_STATUS_INCONSISTENT, f"'{title}' is {status} but has no body", "C3")
        if status == "rejected" and (c[C.chapter_audit_passed_flag] is not False or c[C.chapter_audit_fail_reason_text] is None):
            res.add(E.E_BKS_STATUS_INCONSISTENT, f"rejected '{title}' needs audit_passed=false and a reason", "C3")
        if status == "accepted":
            if c[C.chapter_audit_enabled_flag] and c[C.chapter_audit_passed_flag] is not True:
                res.add(E.E_BKS_GATE_NOT_PASSED, f"accepted '{title}' has audit enabled but the gate did not pass", "C3")
            gen = gens.get(c[C.chapter_generation_uuid_fk])
            if gen is None or gen[G.generation_outcome_text] != "accepted" or gen[G.generation_target_uuid_fk] != c[C.chapter_uuid]:
                res.add(E.E_BKS_PROVENANCE_MISSING, f"accepted '{title}' has no matching accepted Generation", "C3")
    status = book[B.book_status_text]
    if status in ("complete", "final") and any(c[C.chapter_kind_text] != "part" and c[C.chapter_status_text] != "accepted" for c in tables["Chapter"]):
        res.add(E.E_BKS_STATUS_INCONSISTENT, f"book is {status} but a chapter is not accepted", "C3")
    rows = [(c[C.chapter_order_index], c[C.chapter_uuid], c[C.chapter_parent_uuid_fk], c[C.chapter_kind_text], c[C.chapter_title_text],
             c[C.chapter_body_md]) for c in tables["Chapter"]]
    expected = Derive.bks_derive_content_hash(book[B.book_title_text], rows)
    stored = book[B.book_content_sha256_text]
    if (stored is None and status == "final") or (stored is not None and stored != expected):
        res.add(E.E_BKS_HASH_MISMATCH, "book_content_sha256_text does not match the content", "C3")

def _check_c4(tables: Dict[str, List[dict]], res: BKSResult) -> None:
    B, X = Registry.F.Book, Registry.F.Export
    book = tables["Book"][0]
    for x in tables["Export"]:
        if book[B.book_status_text] not in ("complete", "final", "archived"):
            res.add(E.E_BKS_EXPORT_NOT_ALLOWED, f"export {x[X.export_uuid]} exists but the book is {book[B.book_status_text]}", "C4")
        if x[X.export_source_content_sha256_text] != book[B.book_content_sha256_text]:
            res.add(E.E_BKS_EXPORT_STALE, f"export {x[X.export_uuid]} was rendered from older content", "C4")

# Why: one entry point for Book Document conformance (BKS-1 section 11). Levels stack: C2 only runs when C1 passed, and so on.
# Input: loaded document and the highest level to check (1-4). Output: BKSResult; level_reached is the highest level passed.
def bks_validate_book(doc: dict, level: int = 4) -> BKSResult:
    res = BKSResult()
    tables = _check_c1(doc, res)
    if tables is None or res.problems:
        return res
    res.level_reached = 1
    for lvl, check in ((2, _check_c2), (3, _check_c3), (4, _check_c4)):
        if level < lvl:
            break
        check(tables, res)
        if res.problems:
            return res
        res.level_reached = lvl
    return res

def _plan_cell_problem(ctx: object, ref: object) -> Optional[str]:
    if not isinstance(ctx, list):
        return "task_context is not an array"
    for entry in ctx:
        if not isinstance(entry, dict) or not isinstance(entry.get("ref"), str) or not isinstance(entry.get("text_based"), bool) or not isinstance(entry.get("chunks"), list):
            return "task_context entry must be {ref:string, text_based:boolean, chunks:array}"
        if any(not isinstance(ch, dict) or not isinstance(ch.get("chunk_content"), str) for ch in entry["chunks"]):
            return "task_context chunk must be an object with string chunk_content"
    if not isinstance(ref, list) or any(not isinstance(r, str) for r in ref):
        return "task_reference must be an array of path strings"
    return None

# Why: a plan is the JobMaker job schema exactly (amendment 0.2.0, section 7.10). It deliberately does not run Core stage 0, because JobMaker types two columns as array inside a 104a document.
# Input: loaded plan dict and, optionally, the paired Book Document for the link check. Output: BKSResult (level_reached 1 = plan conforms).
def bks_validate_plan(plan: dict, book_doc: Optional[dict] = None) -> BKSResult:
    res = BKSResult()
    P = Plan
    if plan.get("Records_Type") != ["JobTask"] or plan.get("Fields") != P.JOBTASK_FIELDS:
        res.add(E.E_BKS_PLAN_NOT_JOBTASK, "Records_Type must be [\"JobTask\"] with exactly the 11 JobMaker task fields", "P")
        return res
    keys = {k for k in plan if not k.startswith("_")}
    if keys != set(P.PLAN_HEADER_TYPES) | {"Fields", "Values"}:
        res.add(E.E_BKS_PLAN_HEADER, f"unexpected or missing headers: {sorted(keys ^ (set(P.PLAN_HEADER_TYPES) | {'Fields', 'Values'}))}", "P")
        return res
    for key, typ in P.PLAN_HEADER_TYPES.items():
        if not isinstance(plan[key], typ):
            res.add(E.E_BKS_PLAN_HEADER, f"header {key} has the wrong type", "P")
    if plan.get("Format_Version") != "104a" or plan.get("Schema_Name") != P.PLAN_SCHEMA_NAME:
        res.add(E.E_BKS_PLAN_HEADER, "Format_Version must be 104a and Schema_Name 'Job Schema'", "P")
    if plan.get("Job_Type") != P.PLAN_JOB_TYPE or plan.get("Job_Subtype") != P.PLAN_JOB_SUBTYPE:
        res.add(E.E_BKS_PLAN_HEADER, "Job_Type must be 'writing' and Job_Subtype 'book'", "P")
    if not str(plan.get("Job_Goal") or "").strip():
        res.add(E.E_BKS_PLAN_HEADER, "Job_Goal is empty", "P")
    if res.problems:
        return res
    fm = Core.bejson_core_get_field_map(plan)
    rows = [{n: r[i] for n, i in fm.items()} for r in plan["Values"]]
    seen = set()
    for i, r in enumerate(rows):
        where = f"task[{i}]"
        if not Derive.bks_derive_is_uuid(r["task_id"]):
            res.add(E.E_BKS_UUID_INVALID, f"task_id {r['task_id']!r} is not a UUID", "P", where)
        if r["task_id"] in seen:
            res.add(E.E_BKS_PK_DUPLICATE, f"duplicate task_id {r['task_id']}", "P", where)
        seen.add(r["task_id"])
        if not str(r["task_description"]).split("\n\n")[0].strip():
            res.add(E.E_BKS_EMPTY_STRING, "task brief (first paragraph of task_description) is empty", "P", where)
        problem = _plan_cell_problem(r["task_context"], r["task_reference"])
        if problem:
            res.add(E.E_BKS_PLAN_CELL_SHAPE, problem, "P", where)
        for entry in (r["task_context"] if isinstance(r["task_context"], list) else []):
            if isinstance(entry, dict) and isinstance(entry.get("ref"), str) and not Derive.bks_derive_is_relative_path(entry["ref"]):
                res.warnings.append(f"{where}: absolute context ref {entry['ref']!r}")
    if sorted(r["task_order"] for r in rows) != list(range(1, len(rows) + 1)):
        res.add(E.E_BKS_ORDER_INVALID, "task_order must be 1..N without gaps or repeats", "P")
    if plan["Job_Complete"] != (bool(rows) and all(r["task_completed"] for r in rows)):
        res.add(E.E_BKS_PLAN_HEADER, "Job_Complete disagrees with task_completed", "P")
    if book_doc is not None and not res.problems:
        C = Registry.F.Chapter
        want = [c[C.chapter_uuid] for c in Store.bks_store_chapters(book_doc) if Store.bks_store_is_writable(c)]
        have = [r["task_id"] for r in sorted(rows, key=lambda r: r["task_order"])]
        if want != have:
            res.add(E.E_BKS_PLAN_LINK, "plan task ids/order differ from the writable chapters of the Book Document", "P")
    if not res.problems:
        res.level_reached = 1
    return res


def _booktype_rules(rows: List[dict], res: BKSResult) -> None:
    T = Registry.F.BookType
    kinds = ("front", "chapter", "section", "back")
    for i, r in enumerate(rows):
        where = f"BookType[{i}]"
        lo, dflt, hi = r[T.booktype_min_chapters_count], r[T.booktype_default_chapters_count], r[T.booktype_max_chapters_count]
        if not (isinstance(lo, int) and isinstance(dflt, int) and isinstance(hi, int) and 1 <= lo <= dflt <= hi):
            res.add(E.E_BKS_BOOKTYPE_LIMITS, f"chapter limits must satisfy 1 <= min <= default <= max (got {lo}/{dflt}/{hi})", "L", where)
        if (r[T.booktype_min_words_per_chapter_count] or 0) < 0:
            res.add(E.E_BKS_BOOKTYPE_LIMITS, "min words per chapter cannot be negative", "L", where)
        for key in (T.booktype_required_sections_list, T.booktype_default_exports_list):
            if r[key] is not None and (not isinstance(r[key], list) or any(not isinstance(x, str) or not x.strip() for x in r[key])):
                res.add(E.E_BKS_BOOKTYPE_LIMITS, f"{key} must be a list of non-empty strings", "L", where)
        for fmt in (r[T.booktype_default_exports_list] or []):
            if fmt not in Registry.ENUMS["export_format_text"]:
                res.add(E.E_BKS_ENUM_INVALID, f"default export {fmt!r} is not an export format", "L", where)
        for j, item in enumerate(r[T.booktype_outline_template_list] or []):
            ok = isinstance(item, dict) and isinstance(item.get("title"), str) and item["title"].strip() and item.get("kind", "chapter") in kinds
            if not ok:
                res.add(E.E_BKS_BOOKTYPE_LIMITS, f"outline template item {j} needs a title and a kind in {list(kinds)}", "L", where)
        version = r[T.booktype_schema_version_text]
        if not isinstance(version, str) or not version.startswith(Registry.BKS_SCHEMA_PREFIX):
            res.add(E.E_BKS_VERSION_UNSUPPORTED, f"unsupported schema version {version!r}", "L", where)

# Why: library entity files (BookType today) are BEJSON 104 with the registry columns and no Record_Type_Parent (BKS-1 6, 6.3).
# Input: loaded document and its entity name. Output: BKSResult (level_reached 1 = conforms).
def bks_validate_library_doc(doc: dict, entity: str) -> BKSResult:
    res = BKSResult()
    core = CoreValidator.validate_bejson(doc, is_file=False)
    if not core.valid:
        for msg in core.errors[:5]:
            res.add(E.E_BKS_STRUCTURE, str(msg), "L")
        return res
    expected = [{"name": fd.name, "type": fd.type} for fd in Registry.bks_registry_fields(entity)]
    if doc.get("Format_Version") != "104" or doc.get("Records_Type") != [entity] or doc.get("Fields") != expected:
        res.add(E.E_BKS_SCHEMA_MISMATCH, f"{entity} file must be BEJSON 104 with Records_Type [\"{entity}\"] and the registry columns", "L")
        return res
    fm = Core.bejson_core_get_field_map(doc)
    rows = [{fd.name: r[fm[fd.name]] for fd in Registry.bks_registry_fields(entity)} for r in doc["Values"]]
    _check_rows(entity, rows, res)
    if entity == "BookType" and not res.problems:
        _booktype_rules(rows, res)
    if not res.problems:
        res.level_reached = 1
    return res

def bks_validate_booktype(doc: dict) -> BKSResult:
    return bks_validate_library_doc(doc, "BookType")
