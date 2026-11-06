"""
Library:         lib_bejson_Writing_bks_plan.py
Family:          Writing
Module Purpose:  Plan projection and runner bridge: plan_from_book, plan_sync, and ingest of JobRunner output into the Book Document.
Architecture:    BKS-1 (BEJSON Book Standard) Writing family. Non-AI book organisation layer built on the frozen Core family (field-map cache, atomic write, validator, list validator). Contains no AI calls and no Flask code. Book Documents are BEJSON 104db; plans are the JobMaker 104a job schema.
Format_Scope:    104db (Book Document) | 104a (JobMaker plan)
Release_Version: 300
Version:         see VERSION below
Date:            2026-10-29
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   f9205b3a-0149-4748-9368-afeb1affc9e3
"""

import copy
import os
from typing import Callable, Dict, List, Optional, Union

import lib_bejson_Core_bejson_core as Core
import lib_bejson_Writing_bks_derive as Derive
import lib_bejson_Writing_bks_errors as Errors
import lib_bejson_Writing_bks_registry as Registry
import lib_bejson_Writing_bks_store as Store

VERSION = "1.0.0"

# The plan schema is JobMaker 2.8.0's, verbatim (amendment 0.2.0, section 7.1). Nothing is added or removed.
PLAN_SCHEMA_NAME = "Job Schema"
PLAN_SCHEMA_VERSION = "1.0"
PLAN_SCHEMA_DESCRIPTION = "Custom job schema for the NewAgent task creation and tracking system, managing individual task states and optional auditing. Each task carries its own task_context (embedded, chunked files), task_reference (path-only refs), and task_mandatory (marks a task as a required, built-in step for the job's Job_Type/Job_Subtype). Job_Type/Job_Subtype classify the job; Contextualize_Plan/Contextualize_Last control what each task is injected with at run time. Also reused unmodified as the Template payload shape."
PLAN_JOB_TYPE = "writing"
PLAN_JOB_SUBTYPE = "book"
JOBTASK_FIELDS = [
    {"name": "task_id", "type": "string"}, {"name": "task_order", "type": "integer"},
    {"name": "task_name", "type": "string"}, {"name": "task_description", "type": "string"},
    {"name": "task_completed", "type": "boolean"}, {"name": "audit_enabled", "type": "boolean"},
    {"name": "audit_passed", "type": "boolean"}, {"name": "audit_fail_reason", "type": "string"},
    {"name": "task_context", "type": "array"}, {"name": "task_reference", "type": "array"},
    {"name": "task_mandatory", "type": "boolean"},
]
PLAN_HEADER_TYPES = {
    "Format": str, "Format_Version": str, "Format_Creator": str, "Schema_Name": str, "Schema_Version": str,
    "Schema_Description": str, "Job_Goal": str, "Job_Type": str, "Job_Subtype": str, "Contextualize_Plan": bool,
    "Contextualize_Last": bool, "Job_Complete": bool, "Creation_Date": str, "Completion_Date": str, "Records_Type": list,
}
LANGUAGE_NAMES = {"en": "English", "es": "Spanish", "fr": "French", "de": "German", "it": "Italian", "pt": "Portuguese",
                  "nl": "Dutch", "ja": "Japanese", "zh": "Chinese", "ko": "Korean", "ru": "Russian"}

# Why: Job_Goal is the only place the model sees title, audience and language (amendment 7.4).
def bks_plan_job_goal(book: dict) -> str:
    B = Registry.F.Book
    lang = book[B.book_language_text]
    text = f'Write the book "{book[B.book_title_text]}"'
    if book[B.book_audience_text]:
        text += f" for {book[B.book_audience_text]}"
    text += f", in {LANGUAGE_NAMES.get(lang.split('-')[0].lower(), lang)} ({lang})."
    if book[B.book_goal_text]:
        text += f" Goal: {book[B.book_goal_text]}"
    return text

# Why: task_description = brief + derived lines for the model; it is never parsed back (amendment 7.5).
def bks_plan_task_description(chapter: dict, by_id: Dict[str, dict], target_words: Optional[int]) -> str:
    C = Registry.F.Chapter
    text = chapter[C.chapter_brief_text] or chapter[C.chapter_title_text]
    lines = []
    parent = by_id.get(chapter[C.chapter_parent_uuid_fk])
    if parent is not None and parent[C.chapter_kind_text] == "part":
        lines.append(f"Part: {parent[C.chapter_title_text]}")
    elif parent is not None and chapter[C.chapter_kind_text] == "section":
        lines.append(f"Section of: {parent[C.chapter_title_text]}")
    if target_words:
        lines.append(f"Target length: about {target_words} words.")
    return text + ("\n\n" + "\n".join(lines) if lines else "")

# Why: the plan is a projection of the Book Document (amendment 7.3). Result is exactly what JobMaker writes.
# Input: Book Document; optional per-chapter context {chapter_uuid: {"context": [entries], "reference": [paths]}} and target words {chapter_uuid: int}.
# Output: plan dict (104a, JobTask). Not written to disk.
def bks_plan_from_book(doc: dict, *, context_by_chapter: Optional[Dict[str, dict]] = None,
                       target_words: Optional[Dict[str, int]] = None, creation_date: Optional[str] = None) -> dict:
    C = Registry.F.Chapter
    book = Store.bks_store_book(doc)
    chapters = Store.bks_store_chapters(doc)
    by_id = {c[C.chapter_uuid]: c for c in chapters}
    ctx_map, words_map = context_by_chapter or {}, target_words or {}
    values = []
    for n, ch in enumerate([c for c in chapters if Store.bks_store_is_writable(c)], start=1):
        uid = ch[C.chapter_uuid]
        extra = ctx_map.get(uid, {})
        done = ch[C.chapter_status_text] == "accepted"
        values.append([uid, n, ch[C.chapter_title_text], bks_plan_task_description(ch, by_id, words_map.get(uid)), done,
                       bool(ch[C.chapter_audit_enabled_flag]), ch[C.chapter_audit_passed_flag] is True,
                       ch[C.chapter_audit_fail_reason_text] or "", list(extra.get("context", [])),
                       list(extra.get("reference", [])), True])
    complete = bool(values) and all(v[4] for v in values)
    return {"Format": "BEJSON", "Format_Version": "104a", "Format_Creator": "Elton Boehnen",
            "Schema_Name": PLAN_SCHEMA_NAME, "Schema_Version": PLAN_SCHEMA_VERSION,
            "Schema_Description": PLAN_SCHEMA_DESCRIPTION, "Job_Goal": bks_plan_job_goal(book),
            "Job_Type": PLAN_JOB_TYPE, "Job_Subtype": PLAN_JOB_SUBTYPE, "Contextualize_Plan": True,
            "Contextualize_Last": True, "Job_Complete": complete,
            "Creation_Date": creation_date or Derive.bks_derive_now_utc()[:10],
            "Completion_Date": Derive.bks_derive_now_utc()[:10] if complete else "",
            "Records_Type": ["JobTask"], "Fields": [dict(f) for f in JOBTASK_FIELDS], "Values": values}

# Why: the Book Document always wins (W5); the plan's run-state columns are rewritten from it.
# Effect: updates task_completed, audit_passed, audit_fail_reason, Job_Complete and Completion_Date in place.
def bks_plan_sync(plan: dict, doc: dict) -> None:
    C = Registry.F.Chapter
    fm = Core.bejson_core_get_field_map(plan)
    state = {c[C.chapter_uuid]: c for c in Store.bks_store_chapters(doc)}
    for row in plan["Values"]:
        ch = state.get(row[fm["task_id"]])
        if ch is None:
            continue
        row[fm["task_completed"]] = ch[C.chapter_status_text] == "accepted"
        row[fm["audit_passed"]] = ch[C.chapter_audit_passed_flag] is True
        row[fm["audit_fail_reason"]] = ch[C.chapter_audit_fail_reason_text] or ""
    complete = bool(plan["Values"]) and all(r[fm["task_completed"]] for r in plan["Values"])
    plan["Job_Complete"] = complete
    plan["Completion_Date"] = (plan["Completion_Date"] or Derive.bks_derive_now_utc()[:10]) if complete else ""

GateSource = Union[None, dict, Callable[[dict], Optional[dict]]]

# Why: JobRunner never writes the Book Document. This reads its staged output (runs/<job slug>/<task id slug>.md), gates it, and records it (amendment 7.9).
# Input: Book Document, plan, runs directory for this job, gate rules (dict, or a callable chapter-row -> dict), provenance.
# Output: list of {"chapter_uuid", "title", "passed", "reason"} for each chapter examined. Caller then commits the doc and writes the synced plan.
def bks_plan_ingest_run(doc: dict, plan: dict, runs_dir: str, *, gate_rules: GateSource = None, provider: str = "jobrunner",
                        model: Optional[str] = None, author_uuid: Optional[str] = None, now: Optional[str] = None) -> List[dict]:
    C = Registry.F.Chapter
    fm = Core.bejson_core_get_field_map(plan)
    chapters = {c[C.chapter_uuid]: c for c in Store.bks_store_chapters(doc)}
    results = []
    for row in plan["Values"]:
        uid = row[fm["task_id"]]
        ch = chapters.get(uid)
        if ch is None or not row[fm["task_completed"]] or ch[C.chapter_status_text] == "accepted":
            continue
        path = os.path.join(runs_dir, Derive.bks_derive_runner_slug(uid) + ".md")
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
        rules = gate_rules(ch) if callable(gate_rules) else gate_rules
        passed, reason = Store.bks_store_apply_attempt(doc, uid, text, rules=rules, provider=provider, model=model,
                                                       author_uuid=author_uuid, now=now)
        results.append({"chapter_uuid": uid, "title": ch[C.chapter_title_text], "passed": passed, "reason": reason})
        chapters = {c[C.chapter_uuid]: c for c in Store.bks_store_chapters(doc)}
    bks_plan_sync(plan, doc)
    for r in results:
        if not r["passed"]:
            for prow in plan["Values"]:
                if prow[fm["task_id"]] == r["chapter_uuid"]:
                    prow[fm["task_completed"]] = False
    plan["Job_Complete"] = bool(plan["Values"]) and all(p[fm["task_completed"]] for p in plan["Values"])
    if not plan["Job_Complete"]:
        plan["Completion_Date"] = ""
    return results


# Why: JobMaker TypeScript 3.x still writes plans with an optional 12th column `test_cmd` and a `Target_File` header. Both are outside the standard; this reads such a plan into the standard form.
# Input: plan dict. Output: a new plan dict with those two removed. Refuses (E_BKS_PLAN_NOT_JOBTASK) when any test_cmd holds a command, because a book plan never runs shell commands.
def bks_plan_normalize_legacy(plan: dict) -> dict:
    out = copy.deepcopy(plan)
    out.pop("Target_File", None)
    names = [f.get("name") for f in out.get("Fields", [])]
    if "test_cmd" in names:
        idx = names.index("test_cmd")
        if any(str(r[idx] or "").strip() for r in out.get("Values", [])):
            raise Errors.BKSError(Errors.E_BKS_PLAN_NOT_JOBTASK, "test_cmd holds a command; book plans never run shell commands")
        del out["Fields"][idx]
        for r in out["Values"]:
            del r[idx]
    out.pop("_bejson_field_map", None)
    return out
