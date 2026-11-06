#!/usr/bin/env python3
"""
Library:         lib_bejson_CMS_bks_blog_jobs.py
Family:          CMS / Writing
Module Purpose:  Integrates the BKS-1 Standardized Book & Job System
                 (lib_bejson_Writing_bks_*) and CLI_AI 48 AI Dispatch
                 (lib_bejson_AI_ai_writing.py) into BEJSON_CMS.
                 Provides:
                   1. 4-Part Blog Post BookTypes & JobMaker 104a Templates
                   2. 104db Job Registry (registry.bejson) & CMS Job Linkage
                   3. AI Plan Generation -> BKS-1 Book Document (104db) + JobMaker Plan (104a)
                   4. Sequential 4-Part Execution with Contextualize_Plan & Contextualize_Last
                   5. Automatic 4-Part Post Merging (Markdown + MD_To_HTML CMS Article)
                   6. Approve & Overwrite Target CMS Post (PageRecord + pages_db/<uuid>.json)
Format_Scope:    104db (Book Document, Job Registry, Page Content) | 104a (Job Plan, CMS Links) | 104 (BookType)
Release_Version: 300
Version:         1.0.0
Date:            2026-11-02
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   d17a4e83-9c20-4b65-8f12-6e3a5c7b90d4
"""

import json
import logging
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

VERSION = "1.0.0"

logger = logging.getLogger("lib_bejson_CMS_bks_blog_jobs")

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import lib_bejson_Core_bejson_core as Core
import lib_bejson_CMS_cms_core as CMSCore
from lib_bejson_CMS_md2html import convert_markdown_to_cms_article
import lib_bejson_Writing_bks_booktypes as BookTypes
import lib_bejson_Writing_bks_derive as Derive
import lib_bejson_Writing_bks_export as Export
import lib_bejson_Writing_bks_gates as Gates
import lib_bejson_Writing_bks_plan as Plan
import lib_bejson_Writing_bks_registry as Registry
import lib_bejson_Writing_bks_render as Render
import lib_bejson_Writing_bks_store as Store
import lib_bejson_Writing_bks_validator as Validator
from lib_bejson_AI_ai_writing import (
    ai_writing_generate_chapter,
    ai_writing_generate_outline_plan,
    ai_writing_get_providers_and_models,
)

# -----------------------------------------------------------------------------
# BLOG POST 4-PART BOOKTYPE DEFINITIONS (BKS-1 Conformant)
# -----------------------------------------------------------------------------

_BLOG_BOOKTYPES = [
    {
        "slug": "blog_post_4part",
        "name": "4-Part Technical Blog Post",
        "description": "Standard 4-part technical blog post: Foundations, Architecture, Implementation, and Verification.",
        "family": "technical",
        "plan_instruction": (
            "Produce a book title, a subtitle and an ordered outline of {chapter_count} chapters for a 4-part technical blog post. "
            "Each chapter represents one of the 4 parts, with a clear title (no numbering) and a 2-4 sentence brief detailing what "
            "that part must cover and how it transitions to the next part."
        ),
        "chapter_identity": (
            "You are a senior systems architect writing a rigorous, high-signal 4-part technical blog post for Elton Boehnen's BEJSON CMS. "
            "Define technical terms inline on first use, include concrete tables and runnable code blocks, and maintain zero filler."
        ),
        "outline": [
            {
                "title": "Foundations, Context & Problem Statement",
                "brief": "Establish the core engineering problem, architectural motivation, and foundational concepts. Define key terminology inline.",
                "kind": "chapter",
            },
            {
                "title": "Core Architecture, Schema & Structural Invariants",
                "brief": "Dissect the underlying data structures, schema contracts, state machines, and architectural invariants.",
                "kind": "chapter",
            },
            {
                "title": "Implementation Mechanics & Code Walkthrough",
                "brief": "Walk through concrete, production-grade implementation patterns, code signatures, and execution flows.",
                "kind": "chapter",
            },
            {
                "title": "Verification, Edge Cases & Operational Takeaways",
                "brief": "Examine verification gates, failure modes, performance characteristics, and key engineering takeaways.",
                "kind": "chapter",
            },
        ],
        "required_sections": None,
        "min_chapters": 4,
        "default_chapters": 4,
        "max_chapters": 4,
        "min_words": 150,
        "audit_profile": "standard",
        "default_exports": ["md", "html"],
    },
    {
        "slug": "technical_deep_dive_4part",
        "name": "4-Part Engineering Deep Dive",
        "description": "Deep-dive architectural dissection across 4 parts: Context, Data Model, Runtime Engine, and Benchmarks.",
        "family": "analysis",
        "plan_instruction": (
            "Produce a book title, a subtitle and an ordered outline of {chapter_count} chapters for a 4-part engineering deep dive. "
            "Each chapter has a title (no numbering) and a 2-4 sentence brief saying what it must dissect and how it connects to the previous part."
        ),
        "chapter_identity": (
            "You are a principal systems engineer authoring a forensic 4-part architectural deep dive. "
            "Ground explanations in real data layouts, deterministic state transitions, and empirical verification."
        ),
        "outline": [
            {
                "title": "Architectural Context & System Boundaries",
                "brief": "Map the system topology, design constraints, and why conventional approaches fall short.",
                "kind": "chapter",
            },
            {
                "title": "Data Model, Memory Layout & Schema Contracts",
                "brief": "Analyze the exact schema definitions, field maps, and persistence invariants.",
                "kind": "chapter",
            },
            {
                "title": "Runtime Execution Pipeline & Concurrency",
                "brief": "Trace the step-by-step execution lifecycle, atomic file operations, and lock boundaries.",
                "kind": "chapter",
            },
            {
                "title": "Adversarial Testing, Edge Cases & Synthesis",
                "brief": "Evaluate edge-case resilience, invariant enforcement suites, and production conclusions.",
                "kind": "chapter",
            },
        ],
        "required_sections": None,
        "min_chapters": 4,
        "default_chapters": 4,
        "max_chapters": 4,
        "min_words": 150,
        "audit_profile": "standard",
        "default_exports": ["md", "html"],
    },
    {
        "slug": "tutorial_guide_4part",
        "name": "4-Part Practical Tutorial & Guide",
        "description": "Hands-on 4-part developer guide: Setup, Core Build, Integration, and Verification.",
        "family": "technical",
        "plan_instruction": (
            "Produce a book title, a subtitle and an ordered outline of {chapter_count} chapters for a 4-part practical developer tutorial. "
            "Each chapter has a title (no numbering) and a 2-4 sentence brief describing the hands-on steps covered."
        ),
        "chapter_identity": (
            "You are a senior practitioner writing an actionable, copy-pasteable 4-part developer tutorial. "
            "Provide clear commands, configuration snippets, and verification checks at every step."
        ),
        "outline": [
            {
                "title": "Prerequisites, Environment & Bootstrapping",
                "brief": "Configure the directory structure, environment dependencies, and initial bootstrap config.",
                "kind": "chapter",
            },
            {
                "title": "Building the Core Module & Data Layer",
                "brief": "Implement the primary data store, field map lookups, and core domain functions.",
                "kind": "chapter",
            },
            {
                "title": "CLI & Web Interface Integration",
                "brief": "Wire the core logic into CLI flags and web endpoints with input validation.",
                "kind": "chapter",
            },
            {
                "title": "End-to-End Verification & Deployment Checklist",
                "brief": "Run automated smoke tests, inspect output artifacts, and finalize deployment.",
                "kind": "chapter",
            },
        ],
        "required_sections": None,
        "min_chapters": 4,
        "default_chapters": 4,
        "max_chapters": 4,
        "min_words": 120,
        "audit_profile": "standard",
        "default_exports": ["md", "html"],
    },
]

# 104db Job Registry Schema fields (per job-workflow-manager skill)
_JOB_REGISTRY_FIELDS = [
    {"name": "Record_Type_Parent", "type": "string"},
    {"name": "entry_id", "type": "string", "Record_Type_Parent": "JobRegistryEntry"},
    {"name": "entry_name", "type": "string", "Record_Type_Parent": "JobRegistryEntry"},
    {"name": "entry_slug", "type": "string", "Record_Type_Parent": "JobRegistryEntry"},
    {"name": "entry_type", "type": "string", "Record_Type_Parent": "JobRegistryEntry"},
    {"name": "file_path", "type": "string", "Record_Type_Parent": "JobRegistryEntry"},
    {"name": "created_date", "type": "string", "Record_Type_Parent": "JobRegistryEntry"},
    {"name": "modified_date", "type": "string", "Record_Type_Parent": "JobRegistryEntry"},
]

# 104a CMS Job Linkage Schema (tracks target_page_uuid to overwrite on approve)
_CMS_JOB_LINK_FIELDS = [
    {"name": "job_slug", "type": "string"},
    {"name": "book_uuid", "type": "string"},
    {"name": "booktype_slug", "type": "string"},
    {"name": "target_page_uuid", "type": "string"},
    {"name": "category", "type": "string"},
    {"name": "author", "type": "string"},
    {"name": "page_type", "type": "string"},
    {"name": "provider", "type": "string"},
    {"name": "model_id", "type": "string"},
    {"name": "approval_status", "type": "string"},
    {"name": "merged_md_path", "type": "string"},
    {"name": "merged_html_path", "type": "string"},
    {"name": "approved_at", "type": "string"},
]


_DEFAULT_CMS_ROOT = _SCRIPT_DIR.parent.parent


def _resolve_cms_root(cms_root: Optional[Any] = None) -> Path:
    if cms_root is None:
        return _DEFAULT_CMS_ROOT.resolve()
    return Path(cms_root).resolve()


def _get_bks_paths(cms_root: Optional[Any] = None) -> Dict[str, Path]:
    root_path = _resolve_cms_root(cms_root)
    base = root_path / "storage" / "mfdb" / "bks_jobs"
    return {
        "root": base,
        "book_types": base / "book_types",
        "templates": base / "templates",
        "books": base / "books",
        "jobs": base / "jobs",
        "merged": base / "merged",
        "exports": base / "exports",
        "registry": base / "registry.bejson",
        "cms_links": base / "cms_job_links.104a.bejson",
        "manifest": root_path / "storage" / "mfdb" / "site_master" / "104a.mfdb.bejson",
        "pages_db": root_path / "storage" / "mfdb" / "pages_db",
    }


def _build_blog_booktype_row(spec: dict) -> dict:
    T = Registry.F.BookType
    slug = spec["slug"]
    return {
        T.booktype_uuid: str(uuid.uuid5(BookTypes.BOOKTYPE_NAMESPACE, slug)),
        T.booktype_slug_text: slug,
        T.booktype_name_text: spec["name"],
        T.booktype_description_text: spec["description"],
        T.booktype_family_text: spec["family"],
        T.booktype_plan_instruction_text: spec["plan_instruction"],
        T.booktype_chapter_identity_text: spec["chapter_identity"],
        T.booktype_outline_template_list: spec["outline"],
        T.booktype_required_sections_list: spec["required_sections"],
        T.booktype_min_chapters_count: spec["min_chapters"],
        T.booktype_max_chapters_count: spec["max_chapters"],
        T.booktype_default_chapters_count: spec["default_chapters"],
        T.booktype_min_words_per_chapter_count: spec["min_words"],
        T.booktype_audit_profile_text: spec["audit_profile"],
        T.booktype_default_exports_list: spec["default_exports"],
        T.booktype_is_builtin_flag: True,
        T.booktype_schema_version_text: Registry.BKS_SCHEMA_VERSION,
        T.booktype_created_at: BookTypes.BUILTIN_STAMP,
        T.booktype_updated_at: BookTypes.BUILTIN_STAMP,
    }


def _load_or_init_registry(registry_path: Path) -> dict:
    if registry_path.exists():
        doc = Core.bejson_core_load_file(str(registry_path))
        if doc and doc.get("Fields") and "Values" in doc:
            return doc
    doc = {
        "Format": "BEJSON",
        "Format_Version": "104db",
        "Format_Creator": "Elton Boehnen",
        "Records_Type": ["JobRegistryEntry"],
        "Fields": [dict(f) for f in _JOB_REGISTRY_FIELDS],
        "Values": [],
    }
    Core.bejson_core_atomic_write(str(registry_path), doc)
    return doc


def _upsert_registry_entry(
    registry_path: Path,
    *,
    entry_name: str,
    entry_slug: str,
    entry_type: str,
    file_path: str,
) -> str:
    doc = _load_or_init_registry(registry_path)
    fm = Core.bejson_core_get_field_map(doc)
    today = Derive.bks_derive_now_utc()[:10]

    for row in doc.get("Values", []):
        if row[fm["entry_slug"]] == entry_slug and row[fm["entry_type"]] == entry_type:
            row[fm["entry_name"]] = entry_name
            row[fm["file_path"]] = file_path
            row[fm["modified_date"]] = today
            Core.bejson_core_atomic_write(str(registry_path), doc)
            return str(row[fm["entry_id"]])

    new_id = str(uuid.uuid5(BookTypes.BOOKTYPE_NAMESPACE, f"{entry_type}:{entry_slug}"))
    new_row = [None] * len(doc["Fields"])
    if "Record_Type_Parent" in fm:
        new_row[fm["Record_Type_Parent"]] = "JobRegistryEntry"
    new_row[fm["entry_id"]] = new_id
    new_row[fm["entry_name"]] = entry_name
    new_row[fm["entry_slug"]] = entry_slug
    new_row[fm["entry_type"]] = entry_type
    new_row[fm["file_path"]] = file_path
    new_row[fm["created_date"]] = today
    new_row[fm["modified_date"]] = today
    doc["Values"].append(new_row)
    Core.bejson_core_atomic_write(str(registry_path), doc)
    return new_id


def _load_or_init_cms_links(links_path: Path) -> dict:
    if links_path.exists():
        doc = Core.bejson_core_load_file(str(links_path))
        if doc and doc.get("Fields") and "Values" in doc:
            return doc
    doc = Core.bejson_core_create_104a("CMSJobLink", [dict(f) for f in _CMS_JOB_LINK_FIELDS], [])
    Core.bejson_core_atomic_write(str(links_path), doc)
    return doc


def _upsert_cms_link(links_path: Path, link_data: Dict[str, Any]) -> None:
    doc = _load_or_init_cms_links(links_path)
    fm = Core.bejson_core_get_field_map(doc)
    job_slug = link_data["job_slug"]

    for row in doc.get("Values", []):
        if row[fm["job_slug"]] == job_slug:
            for k, v in link_data.items():
                if k in fm:
                    row[fm[k]] = v
            Core.bejson_core_atomic_write(str(links_path), doc)
            return

    new_row = [link_data.get(f["name"]) for f in doc["Fields"]]
    doc["Values"].append(new_row)
    Core.bejson_core_atomic_write(str(links_path), doc)


def _get_cms_link(links_path: Path, job_slug: str) -> Dict[str, Any]:
    doc = _load_or_init_cms_links(links_path)
    fm = Core.bejson_core_get_field_map(doc)
    for row in doc.get("Values", []):
        if row[fm["job_slug"]] == job_slug:
            return {f["name"]: row[fm[f["name"]]] for f in doc["Fields"]}
    return {}


def _get_all_cms_links(links_path: Path) -> Dict[str, Dict[str, Any]]:
    doc = _load_or_init_cms_links(links_path)
    fm = Core.bejson_core_get_field_map(doc)
    out = {}
    for row in doc.get("Values", []):
        slug = row[fm["job_slug"]]
        if slug:
            out[slug] = {f["name"]: row[fm[f["name"]]] for f in doc["Fields"]}
    return out


def cms_bks_bootstrap(cms_root: Optional[Any] = None) -> Dict[str, Any]:
    """
    Seed BKS-1 built-in BookTypes, 4-Part Blog Post BookTypes, and 104a JobMaker
    Blog Post Job Templates into storage/mfdb/bks_jobs/.
    """
    paths = _get_bks_paths(cms_root)
    for key in ("root", "book_types", "templates", "books", "jobs", "merged", "exports"):
        paths[key].mkdir(parents=True, exist_ok=True)

    # 1. Seed 9 BKS-1 standard BookTypes
    BookTypes.bks_booktypes_write_builtin(str(paths["book_types"]), overwrite=False)

    # 2. Seed 3 4-Part Blog Post BookTypes & corresponding 104a Job Templates
    T = Registry.F.BookType
    for spec in _BLOG_BOOKTYPES:
        bt_row = _build_blog_booktype_row(spec)
        bt_path = paths["book_types"] / f"{spec['slug']}{BookTypes.BOOKTYPE_FILE_SUFFIX}"
        if not bt_path.exists():
            Core.bejson_core_atomic_write(str(bt_path), BookTypes.bks_booktypes_doc(bt_row))

        # Project a canonical 104a JobMaker Template from this 4-part BookType
        tpl_path = paths["templates"] / f"{spec['slug']}.bejson"
        if not tpl_path.exists():
            sample_book = BookTypes.bks_booktypes_new_book(
                bt_row,
                chapter_count=4,
                title=f"Template: {spec['name']}",
                topic=spec["description"],
                author_name="boehnenelton2024",
                language="en",
                goal=spec["description"],
            )
            tpl_plan = Plan.bks_plan_from_book(
                sample_book,
                target_words={
                    c[Registry.F.Chapter.chapter_uuid]: bt_row[T.booktype_min_words_per_chapter_count]
                    for c in Store.bks_store_chapters(sample_book)
                },
            )
            Core.bejson_core_atomic_write(str(tpl_path), tpl_plan)

        _upsert_registry_entry(
            paths["registry"],
            entry_name=spec["name"],
            entry_slug=spec["slug"],
            entry_type="template",
            file_path=f"templates/{spec['slug']}.bejson",
        )

    _load_or_init_cms_links(paths["cms_links"])
    return {
        "ok": True,
        "root": str(paths["root"]),
        "book_types_dir": str(paths["book_types"]),
        "templates_dir": str(paths["templates"]),
        "books_dir": str(paths["books"]),
        "jobs_dir": str(paths["jobs"]),
        "merged_dir": str(paths["merged"]),
    }


def cms_bks_list_templates(cms_root: Optional[Any] = None) -> List[Dict[str, Any]]:
    """List all BookTypes and 4-Part Blog Post Job Templates."""
    cms_bks_bootstrap(cms_root)
    paths = _get_bks_paths(cms_root)
    T = Registry.F.BookType
    bt_map = BookTypes.bks_booktypes_list(str(paths["book_types"]))

    priority_slugs = ["blog_post_4part", "technical_deep_dive_4part", "tutorial_guide_4part"]
    ordered_slugs = [s for s in priority_slugs if s in bt_map] + [
        s for s in sorted(bt_map.keys()) if s not in priority_slugs
    ]

    result = []
    for slug in ordered_slugs:
        row = bt_map[slug]
        result.append({
            "slug": slug,
            "type_id": slug,
            "name": row[T.booktype_name_text],
            "display_name": row[T.booktype_name_text],
            "description": row[T.booktype_description_text],
            "family": row[T.booktype_family_text],
            "default_chapters": row[T.booktype_default_chapters_count],
            "default_chapter_count": row[T.booktype_default_chapters_count],
            "min_chapters": row[T.booktype_min_chapters_count],
            "max_chapters": row[T.booktype_max_chapters_count],
            "min_words_per_chapter": row[T.booktype_min_words_per_chapter_count],
            "target_words_per_chapter": row[T.booktype_min_words_per_chapter_count],
            "audit_profile": row[T.booktype_audit_profile_text],
            "is_blog_4part": slug in priority_slugs,
            "outline_template": row[T.booktype_outline_template_list] or [],
        })
    return result


def cms_bks_list_jobs(cms_root: Optional[Any] = None) -> List[Dict[str, Any]]:
    """List all created BKS-1 Book / Blog Post Jobs with chapter progress & target post info."""
    cms_bks_bootstrap(cms_root)
    paths = _get_bks_paths(cms_root)
    links_map = _get_all_cms_links(paths["cms_links"])

    B = Registry.F.Book
    C = Registry.F.Chapter
    jobs_list: List[Dict[str, Any]] = []

    for bfile in sorted(paths["books"].glob("*.bks.bejson"), key=lambda p: p.stat().st_mtime, reverse=True):
        job_slug = bfile.name[:-len(".bks.bejson")]
        try:
            doc = Store.bks_store_load(str(bfile))
            book = Store.bks_store_book(doc)
            chapters = [c for c in Store.bks_store_chapters(doc) if Store.bks_store_is_writable(c)]
            accepted_count = sum(1 for c in chapters if c[C.chapter_status_text] == "accepted")
            drafted_count = sum(1 for c in chapters if bool(c.get(C.chapter_body_md)))
            link = links_map.get(job_slug, {})
            merged_md_file = paths["merged"] / f"{job_slug}.md"
            jobs_list.append({
                "job_slug": job_slug,
                "job_name": book[B.book_title_text],
                "book_uuid": book[B.book_uuid],
                "title": book[B.book_title_text],
                "topic": book[B.book_topic_text],
                "booktype_slug": book[B.book_booktype_slug_text],
                "book_type_id": book[B.book_booktype_slug_text],
                "status": book[B.book_status_text],
                "word_count": book[B.book_word_count],
                "chapter_count": len(chapters),
                "accepted_count": accepted_count,
                "accepted_parts": accepted_count,
                "drafted_count": drafted_count,
                "target_page_uuid": link.get("target_page_uuid") or "",
                "category": link.get("category") or book.get(B.book_category_name_text) or "Uncategorized",
                "author": link.get("author") or book.get(B.book_author_name_text) or "boehnenelton2024",
                "page_type": link.get("page_type") or "blog",
                "provider": link.get("provider") or "geminirest",
                "model_id": link.get("model_id") or "",
                "approval_status": link.get("approval_status") or "pending",
                "approved_at": link.get("approved_at") or "",
                "has_merged_post": merged_md_file.exists(),
                "updated_at": book[B.book_updated_at],
            })
        except Exception as err:
            logger.warning("Failed to load BKS job %s: %s", bfile.name, err)

    return jobs_list


def cms_bks_get_job_detail(cms_root_or_slug: Any, job_slug: Optional[str] = None) -> Dict[str, Any]:
    """Load full BKS-1 Book Document, 104a Job Plan, chapters, and merged post preview."""
    if job_slug is None:
        cms_root = None
        job_slug = str(cms_root_or_slug)
    else:
        cms_root = cms_root_or_slug
    cms_bks_bootstrap(cms_root)
    paths = _get_bks_paths(cms_root)
    book_path = paths["books"] / f"{job_slug}.bks.bejson"
    plan_path = paths["jobs"] / f"{job_slug}.bejson"
    if not book_path.exists():
        return {"ok": False, "error": f"Job '{job_slug}' not found"}

    B = Registry.F.Book
    C = Registry.F.Chapter
    T = Registry.F.BookType
    doc = Store.bks_store_load(str(book_path))
    book = Store.bks_store_book(doc)
    chapters = [c for c in Store.bks_store_chapters(doc) if Store.bks_store_is_writable(c)]
    plan_doc = Core.bejson_core_load_file(str(plan_path)) if plan_path.exists() else Plan.bks_plan_from_book(doc)
    link = _get_cms_link(paths["cms_links"], job_slug)

    bt_map = BookTypes.bks_booktypes_list(str(paths["book_types"]))
    bt_row = bt_map.get(book[B.book_booktype_slug_text]) or bt_map.get("blog_post_4part")
    target_w = bt_row[T.booktype_min_words_per_chapter_count] if bt_row else 150

    merged_md = ""
    merged_html = ""
    merged_md_file = paths["merged"] / f"{job_slug}.md"
    merged_html_file = paths["merged"] / f"{job_slug}.html"
    if merged_md_file.exists():
        merged_md = merged_md_file.read_text(encoding="utf-8")
    if merged_html_file.exists():
        merged_html = merged_html_file.read_text(encoding="utf-8")

    parts_data = []
    for idx, ch in enumerate(chapters, start=1):
        parts_data.append({
            "index": idx,
            "part_number": idx,
            "chapter_uuid": ch[C.chapter_uuid],
            "title": ch[C.chapter_title_text],
            "brief": ch[C.chapter_brief_text] or "",
            "body_md": ch[C.chapter_body_md] or "",
            "status": ch[C.chapter_status_text],
            "word_count": ch[C.chapter_word_count],
            "actual_words": ch[C.chapter_word_count],
            "target_words": target_w,
            "audit_enabled": bool(ch[C.chapter_audit_enabled_flag]),
            "audit_passed": ch[C.chapter_audit_passed_flag],
            "audit_fail_reason": ch[C.chapter_audit_fail_reason_text] or "",
            "gate_report": ch[C.chapter_audit_fail_reason_text] or "",
        })

    book_summary = {
        "book_uuid": book[B.book_uuid],
        "title": book[B.book_title_text],
        "subtitle": book[B.book_subtitle_text] or "",
        "topic": book[B.book_topic_text],
        "thesis": book[B.book_topic_text],
        "goal": book[B.book_goal_text] or "",
        "booktype_slug": book[B.book_booktype_slug_text],
        "book_type_id": book[B.book_booktype_slug_text],
        "status": book[B.book_status_text],
        "word_count": book[B.book_word_count],
    }
    link_summary = dict(link)
    link_summary.setdefault("target_page_uuid", link.get("target_page_uuid") or "")
    link_summary.setdefault("category_name", link.get("category") or book.get(B.book_category_name_text) or "Uncategorized")
    link_summary.setdefault("author_name", link.get("author") or book.get(B.book_author_name_text) or "boehnenelton2024")

    return {
        "ok": True,
        "job_slug": job_slug,
        "book_path": str(book_path),
        "plan_path": str(plan_path),
        "book_uuid": book[B.book_uuid],
        "title": book[B.book_title_text],
        "subtitle": book[B.book_subtitle_text] or "",
        "topic": book[B.book_topic_text],
        "goal": book[B.book_goal_text] or "",
        "booktype_slug": book[B.book_booktype_slug_text],
        "book_type_id": book[B.book_booktype_slug_text],
        "status": book[B.book_status_text],
        "word_count": book[B.book_word_count],
        "content_sha256": book[B.book_content_sha256_text] or "",
        "target_page_uuid": link.get("target_page_uuid") or "",
        "category": link.get("category") or book.get(B.book_category_name_text) or "Uncategorized",
        "author": link.get("author") or book.get(B.book_author_name_text) or "boehnenelton2024",
        "page_type": link.get("page_type") or "blog",
        "provider": link.get("provider") or "geminirest",
        "model_id": link.get("model_id") or "",
        "approval_status": link.get("approval_status") or "pending",
        "approved_at": link.get("approved_at") or "",
        "book": book_summary,
        "link": link_summary,
        "parts": parts_data,
        "chapters": parts_data,
        "plan": plan_doc,
        "merged_markdown": merged_md,
        "merged_md": merged_md,
        "merged_html": merged_html,
    }


def cms_bks_create_blog_job(
    cms_root: Optional[Any] = None,
    *,
    topic: str = "",
    title: Optional[str] = None,
    target_page_uuid: Optional[str] = None,
    booktype_slug: Optional[str] = None,
    book_type_id: Optional[str] = None,
    chapter_count: int = 4,
    category: Optional[str] = None,
    category_name: Optional[str] = None,
    author: Optional[str] = None,
    author_name: Optional[str] = None,
    template_key: Optional[str] = None,
    page_type: str = "blog",
    provider: str = "geminirest",
    model_id: Optional[str] = None,
    author_system_instruction: Optional[str] = None,
    context_text: str = "",
    use_ai_plan: bool = True,
    custom_nodes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Create a new BKS-1 Standardized Book Document (books/<slug>.bks.bejson) and
    JobMaker 104a Plan (jobs/<slug>.bejson) for a 4-part blog post, linked to
    an optional target_page_uuid to overwrite upon approval.
    """
    cms_bks_bootstrap(cms_root)
    paths = _get_bks_paths(cms_root)
    T = Registry.F.BookType
    C = Registry.F.Chapter

    resolved_bt_slug = (booktype_slug or book_type_id or "blog_post_4part").strip()
    resolved_category = (category or category_name or "Uncategorized").strip()
    resolved_author = (author or author_name or "boehnenelton2024").strip()
    resolved_topic = (topic or title or "Untitled Blog Post").strip()

    bt_map = BookTypes.bks_booktypes_list(str(paths["book_types"]))
    bt_row = bt_map.get(resolved_bt_slug) or bt_map.get("blog_post_4part")
    if not bt_row:
        raise ValueError(f"BookType '{resolved_bt_slug}' not found")

    actual_count = max(bt_row[T.booktype_min_chapters_count], min(chapter_count, bt_row[T.booktype_max_chapters_count]))

    plan_res = None
    if custom_nodes and len(custom_nodes) > 0:
        nodes = custom_nodes
        resolved_title = (title or resolved_topic).strip()
        resolved_subtitle = None
    elif use_ai_plan:
        plan_res = ai_writing_generate_outline_plan(
            resolved_topic,
            bt_row,
            chapter_count=actual_count,
            provider=provider,
            model_id=model_id,
            system_instruction=author_system_instruction,
            context_text=context_text,
        )
        nodes = plan_res["nodes"]
        resolved_title = (title or plan_res.get("title") or resolved_topic).strip()
        resolved_subtitle = plan_res.get("subtitle")
    else:
        nodes = BookTypes.bks_booktypes_outline_nodes(bt_row, actual_count)
        resolved_title = (title or resolved_topic).strip()
        resolved_subtitle = None

    base_slug = Derive.bks_derive_slugify(resolved_title, fallback="blog-post-job")
    job_slug = base_slug
    counter = 2
    while (paths["books"] / f"{job_slug}.bks.bejson").exists():
        job_slug = f"{base_slug}-{counter}"
        counter += 1

    book_doc = BookTypes.bks_booktypes_new_book(
        bt_row,
        chapter_count=len(nodes),
        nodes=nodes,
        title=resolved_title,
        subtitle=resolved_subtitle,
        topic=resolved_topic,
        goal=f"Author a comprehensive {len(nodes)}-part technical publication on: {resolved_topic}",
        author_name=resolved_author,
        category_name=resolved_category,
        language="en",
        audience="software engineers and systems architects",
    )

    book_path = paths["books"] / f"{job_slug}.bks.bejson"
    Store.bks_store_commit(str(book_path), book_doc, level=3)

    target_words_map = {
        c[C.chapter_uuid]: bt_row[T.booktype_min_words_per_chapter_count]
        for c in Store.bks_store_chapters(book_doc)
        if Store.bks_store_is_writable(c)
    }
    plan_doc = Plan.bks_plan_from_book(book_doc, target_words=target_words_map)
    plan_val = Validator.bks_validate_plan(plan_doc, book_doc)
    if not plan_val.ok:
        raise ValueError(f"Generated plan failed BKS-1 P validation: {plan_val.problems}")

    plan_path = paths["jobs"] / f"{job_slug}.bejson"
    Core.bejson_core_atomic_write(str(plan_path), plan_doc)

    _upsert_registry_entry(
        paths["registry"],
        entry_name=resolved_title,
        entry_slug=job_slug,
        entry_type="schema",
        file_path=f"jobs/{job_slug}.bejson",
    )
    book_row = Store.bks_store_book(book_doc)
    _upsert_cms_link(
        paths["cms_links"],
        {
            "job_slug": job_slug,
            "book_uuid": book_row[Registry.F.Book.book_uuid],
            "booktype_slug": bt_row[T.booktype_slug_text],
            "target_page_uuid": (target_page_uuid or "").strip(),
            "category": resolved_category,
            "author": resolved_author,
            "page_type": page_type or "blog",
            "provider": provider or "geminirest",
            "model_id": model_id or "",
            "approval_status": "pending",
            "merged_md_path": f"merged/{job_slug}.md",
            "merged_html_path": f"merged/{job_slug}.html",
            "approved_at": "",
        },
    )

    detail = cms_bks_get_job_detail(cms_root, job_slug)
    detail["ai_plan_generated"] = bool(plan_res.get("ai_generated")) if plan_res else False
    detail["ai_plan_error"] = plan_res.get("error") if plan_res else None
    return detail


def cms_bks_update_job_metadata_and_plan(
    cms_root_or_slug: Any,
    job_slug: Optional[str] = None,
    *,
    title: Optional[str] = None,
    topic: Optional[str] = None,
    target_page_uuid: Optional[str] = None,
    category: Optional[str] = None,
    category_name: Optional[str] = None,
    author: Optional[str] = None,
    author_name: Optional[str] = None,
    template_key: Optional[str] = None,
    page_type: Optional[str] = None,
    provider: Optional[str] = None,
    model_id: Optional[str] = None,
    parts_updates: Optional[List[Dict[str, Any]]] = None,
    parts: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Update chapter titles/briefs/bodies or target post settings on an existing BKS-1 job."""
    if job_slug is None:
        cms_root = None
        job_slug = str(cms_root_or_slug)
    else:
        cms_root = cms_root_or_slug
    paths = _get_bks_paths(cms_root)
    book_path = paths["books"] / f"{job_slug}.bks.bejson"
    plan_path = paths["jobs"] / f"{job_slug}.bejson"
    if not book_path.exists():
        return {"ok": False, "error": f"Job '{job_slug}' not found"}

    B = Registry.F.Book
    C = Registry.F.Chapter
    doc = Store.bks_store_load(str(book_path))
    tables = Store.bks_store_tables(doc)
    book_row = tables["Book"][0]

    resolved_cat = category if category is not None else category_name
    resolved_auth = author if author is not None else author_name
    resolved_parts = parts_updates if parts_updates is not None else parts

    if title and title.strip():
        book_row[B.book_title_text] = title.strip()
    if topic and topic.strip():
        book_row[B.book_topic_text] = topic.strip()
    if resolved_cat and resolved_cat.strip():
        book_row[B.book_category_name_text] = resolved_cat.strip()
    if resolved_auth and resolved_auth.strip():
        book_row[B.book_author_name_text] = resolved_auth.strip()

    if resolved_parts:
        updates_by_uuid = {
            u["chapter_uuid"]: u for u in resolved_parts if isinstance(u, dict) and u.get("chapter_uuid")
        }
        updates_by_idx = {
            int(u.get("index") or u.get("part_number") or (idx + 1)): u
            for idx, u in enumerate(resolved_parts)
            if isinstance(u, dict)
        }
        writable_idx = 0
        for ch in tables["Chapter"]:
            if not Store.bks_store_is_writable(ch):
                continue
            writable_idx += 1
            uid = ch[C.chapter_uuid]
            upd = updates_by_uuid.get(uid) or updates_by_idx.get(writable_idx)
            if upd:
                if upd.get("title") and str(upd["title"]).strip():
                    ch[C.chapter_title_text] = str(upd["title"]).strip()
                if "brief" in upd:
                    brief_val = str(upd["brief"] or "").strip()
                    ch[C.chapter_brief_text] = brief_val if brief_val else None
                if "body_md" in upd and upd["body_md"] is not None:
                    body_val = str(upd["body_md"]).strip()
                    if body_val and body_val != (ch.get(C.chapter_body_md) or "").strip():
                        ch[C.chapter_body_md] = body_val

    Store.bks_store_set_tables(doc, tables)
    Store.bks_store_commit(str(book_path), doc, level=3)

    bt_map = BookTypes.bks_booktypes_list(str(paths["book_types"]))
    bt_row = bt_map.get(book_row[B.book_booktype_slug_text]) or bt_map.get("blog_post_4part")
    min_w = bt_row[Registry.F.BookType.booktype_min_words_per_chapter_count] if bt_row else 150
    target_words_map = {
        c[C.chapter_uuid]: min_w
        for c in Store.bks_store_chapters(doc)
        if Store.bks_store_is_writable(c)
    }
    plan_doc = Plan.bks_plan_from_book(doc, target_words=target_words_map)
    Core.bejson_core_atomic_write(str(plan_path), plan_doc)

    link = _get_cms_link(paths["cms_links"], job_slug)
    if target_page_uuid is not None:
        link["target_page_uuid"] = target_page_uuid.strip()
    if resolved_cat is not None:
        link["category"] = resolved_cat.strip()
    if resolved_auth is not None:
        link["author"] = resolved_auth.strip()
    if page_type is not None:
        link["page_type"] = page_type.strip()
    if provider is not None:
        link["provider"] = provider.strip()
    if model_id is not None:
        link["model_id"] = model_id.strip()
    link["job_slug"] = job_slug
    _upsert_cms_link(paths["cms_links"], link)

    return cms_bks_get_job_detail(cms_root, job_slug)


def cms_bks_merge_parts(cms_root_or_slug: Any, job_slug: Optional[str] = None) -> Dict[str, Any]:
    """
    Merge all drafted/accepted chapters of the BKS-1 Book Document into a single
    unified 4-part Markdown post and compile it into a <article class="bejson-cms-article">
    HTML document via lib_bejson_CMS_md2html.
    """
    if job_slug is None:
        cms_root = None
        job_slug = str(cms_root_or_slug)
    else:
        cms_root = cms_root_or_slug
    paths = _get_bks_paths(cms_root)
    book_path = paths["books"] / f"{job_slug}.bks.bejson"
    if not book_path.exists():
        return {"ok": False, "error": f"Job '{job_slug}' not found"}

    B = Registry.F.Book
    C = Registry.F.Chapter
    doc = Store.bks_store_load(str(book_path))
    book = Store.bks_store_book(doc)
    chapters = [c for c in Store.bks_store_chapters(doc) if Store.bks_store_is_writable(c)]

    book_title = book[B.book_title_text]
    md_sections: List[str] = [f"# {book_title}"]
    if book.get(B.book_subtitle_text):
        md_sections.append(f"*{book[B.book_subtitle_text]}*")

    drafted_count = 0
    accepted_count = 0
    for idx, ch in enumerate(chapters, start=1):
        if ch[C.chapter_status_text] == "accepted":
            accepted_count += 1
        body = (ch.get(C.chapter_body_md) or "").strip()
        if not body:
            continue
        drafted_count += 1
        ch_title = ch[C.chapter_title_text]
        stripped_body = Render.bks_render_strip_duplicate_heading(body, ch_title).strip()
        md_sections.append(f"## {ch_title}\n\n{stripped_body}")

    merged_md = "\n\n".join(md_sections).strip() + "\n"
    parsed_article = convert_markdown_to_cms_article(merged_md, book_title)
    merged_html = f'<article class="bejson-cms-article">\n{parsed_article["html_body"]}\n</article>'

    merged_md_path = paths["merged"] / f"{job_slug}.md"
    merged_html_path = paths["merged"] / f"{job_slug}.html"
    paths["merged"].mkdir(parents=True, exist_ok=True)
    merged_md_path.write_text(merged_md, encoding="utf-8")
    merged_html_path.write_text(merged_html, encoding="utf-8")

    return {
        "ok": True,
        "job_slug": job_slug,
        "title": book_title,
        "merged_markdown": merged_md,
        "merged_md": merged_md,
        "merged_html": merged_html,
        "merged_md_path": str(merged_md_path),
        "merged_html_path": str(merged_html_path),
        "word_count": Derive.bks_derive_count_words(merged_md),
        "drafted_count": drafted_count,
        "accepted_count": accepted_count,
        "total_parts": len(chapters),
    }


def cms_bks_execute_part(
    cms_root_or_slug: Any,
    job_slug_or_part: Optional[Any] = None,
    part_index: Optional[int] = None,
    *,
    chapter_uuid: Optional[str] = None,
    provider: Optional[str] = None,
    model_id: Optional[str] = None,
    author_name: Optional[str] = None,
    author_system_instruction: Optional[str] = None,
    extra_context: str = "",
    custom_instructions: str = "",
    custom_body_md: Optional[str] = None,
    min_words_override: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Execute 1 task/part of a BKS-1 Blog Post Job using CLI_AI 48's ai_dispatch_call()
    (or record a manual body edit when custom_body_md is passed), evaluate BKS-1 gates,
    commit the Book Document, sync the 104a Job Plan, and update the merged 4-part post!
    """
    if isinstance(cms_root_or_slug, Path) or (
        isinstance(cms_root_or_slug, str) and os.path.sep in cms_root_or_slug
    ):
        cms_root = cms_root_or_slug
        job_slug = str(job_slug_or_part)
    else:
        cms_root = None
        job_slug = str(cms_root_or_slug)
        if isinstance(job_slug_or_part, int) and part_index is None:
            part_index = job_slug_or_part

    paths = _get_bks_paths(cms_root)
    book_path = paths["books"] / f"{job_slug}.bks.bejson"
    plan_path = paths["jobs"] / f"{job_slug}.bejson"
    if not book_path.exists():
        return {"ok": False, "error": f"Job '{job_slug}' not found"}

    B = Registry.F.Book
    C = Registry.F.Chapter
    doc = Store.bks_store_load(str(book_path))
    book = Store.bks_store_book(doc)
    chapters = [c for c in Store.bks_store_chapters(doc) if Store.bks_store_is_writable(c)]
    link = _get_cms_link(paths["cms_links"], job_slug)

    target_uid = chapter_uuid
    if not target_uid and part_index is not None:
        idx0 = max(0, min(int(part_index) - 1, len(chapters) - 1))
        if chapters:
            target_uid = chapters[idx0][C.chapter_uuid]
    if not target_uid:
        next_ch = next((c for c in chapters if c[C.chapter_status_text] != "accepted"), None)
        if not next_ch:
            next_ch = chapters[0] if chapters else None
        if not next_ch:
            return {"ok": False, "error": "No writable chapters in book document"}
        target_uid = next_ch[C.chapter_uuid]

    bt_map = BookTypes.bks_booktypes_list(str(paths["book_types"]))
    bt_row = bt_map.get(book[B.book_booktype_slug_text]) or bt_map.get("blog_post_4part")
    active_provider = (provider or link.get("provider") or "geminirest").strip()
    active_model = (model_id if model_id is not None else (link.get("model_id") or "")).strip() or None
    combined_context = "\n\n".join(x for x in [extra_context, custom_instructions] if x).strip()

    if custom_body_md is not None and custom_body_md.strip():
        gate_rules = BookTypes.bks_booktypes_gate_rules(bt_row) if bt_row else None
        if gate_rules and min_words_override is not None:
            gate_rules = dict(gate_rules)
            gate_rules["min_words"] = int(min_words_override)
        passed, reason = Store.bks_store_apply_attempt(
            doc,
            target_uid,
            custom_body_md.strip(),
            rules=gate_rules,
            provider="manual_editor",
            model="user",
        )
        gen_result = {
            "ok": True,
            "passed": passed,
            "accepted": passed,
            "reason": reason,
            "provider": "manual_editor",
            "model_id": "user",
            "chapter_uuid": target_uid,
        }
    else:
        gen_result = ai_writing_generate_chapter(
            doc,
            target_uid,
            bt_row,
            provider=active_provider,
            model_id=active_model,
            author_system_instruction=author_system_instruction,
            extra_context=combined_context,
            min_words_override=min_words_override,
        )
        gen_result["accepted"] = bool(gen_result.get("passed"))

    updated_chapters = [c for c in Store.bks_store_chapters(doc) if Store.bks_store_is_writable(c)]
    if updated_chapters and all(c[C.chapter_status_text] == "accepted" for c in updated_chapters):
        try:
            Store.bks_store_mark_complete(doc)
        except Exception:
            pass

    Store.bks_store_commit(str(book_path), doc, level=3)

    if plan_path.exists():
        plan_doc = Core.bejson_core_load_file(str(plan_path))
    else:
        plan_doc = Plan.bks_plan_from_book(doc)
    Plan.bks_plan_sync(plan_doc, doc)
    Core.bejson_core_atomic_write(str(plan_path), plan_doc)

    _upsert_registry_entry(
        paths["registry"],
        entry_name=book[B.book_title_text],
        entry_slug=job_slug,
        entry_type="schema",
        file_path=f"jobs/{job_slug}.bejson",
    )

    merge_res = cms_bks_merge_parts(cms_root, job_slug)
    detail = cms_bks_get_job_detail(cms_root, job_slug)
    detail["step_result"] = gen_result
    detail["merge_result"] = merge_res
    detail["merged"] = merge_res
    detail["detail"] = dict(detail)
    return detail


def cms_bks_execute_all_parts(
    cms_root_or_slug: Any,
    job_slug: Optional[str] = None,
    *,
    provider: Optional[str] = None,
    model_id: Optional[str] = None,
    author_name: Optional[str] = None,
    author_system_instruction: Optional[str] = None,
    extra_context: str = "",
    force_all: bool = False,
    min_words_override: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Sequentially execute all 4 parts of a BKS-1 Blog Post Job using CLI_AI 48's
    ai_dispatch_call(), injecting Contextualize_Plan and Contextualize_Last into
    each subsequent part, and merge the complete 4-part post.
    """
    if job_slug is None:
        cms_root = None
        job_slug = str(cms_root_or_slug)
    else:
        cms_root = cms_root_or_slug
    paths = _get_bks_paths(cms_root)
    book_path = paths["books"] / f"{job_slug}.bks.bejson"
    if not book_path.exists():
        return {"ok": False, "error": f"Job '{job_slug}' not found"}

    C = Registry.F.Chapter
    doc = Store.bks_store_load(str(book_path))
    chapters = [c for c in Store.bks_store_chapters(doc) if Store.bks_store_is_writable(c)]

    step_results = []
    for ch in chapters:
        if not force_all and ch[C.chapter_status_text] == "accepted":
            continue
        res = cms_bks_execute_part(
            cms_root,
            job_slug,
            chapter_uuid=ch[C.chapter_uuid],
            provider=provider,
            model_id=model_id,
            author_name=author_name,
            author_system_instruction=author_system_instruction,
            extra_context=extra_context,
            min_words_override=min_words_override,
        )
        step_results.append(res.get("step_result"))

    merge_res = cms_bks_merge_parts(cms_root, job_slug)
    detail = cms_bks_get_job_detail(cms_root, job_slug)
    detail["step_results"] = step_results
    detail["results"] = step_results
    detail["merged"] = merge_res
    detail["merge_result"] = merge_res
    detail["detail"] = dict(detail)
    return detail


def cms_bks_approve_and_overwrite_post(
    cms_root_or_slug: Any,
    job_slug: Optional[str] = None,
    *,
    target_page_uuid: Optional[str] = None,
    title: Optional[str] = None,
    title_override: Optional[str] = None,
    category: Optional[str] = None,
    category_name: Optional[str] = None,
    category_override: Optional[str] = None,
    author: Optional[str] = None,
    author_name: Optional[str] = None,
    author_override: Optional[str] = None,
    template_key: Optional[str] = None,
    page_type_override: Optional[str] = None,
    edited_markdown: Optional[str] = None,
    merged_md_override: Optional[str] = None,
    merged_html_override: Optional[str] = None,
    trigger_publish: bool = False,
) -> Dict[str, Any]:
    """
    Approve the merged 4-part blog post and atomically OVERWRITE the target CMS post
    (or create it if no target_page_uuid was previously linked).
    Also finalizes the BKS-1 Book Document and records BKS Export rows when all
    4 parts are accepted.
    """
    if job_slug is None:
        cms_root = None
        job_slug = str(cms_root_or_slug)
    else:
        cms_root = cms_root_or_slug
    paths = _get_bks_paths(cms_root)
    book_path = paths["books"] / f"{job_slug}.bks.bejson"
    if not book_path.exists():
        return {"ok": False, "error": f"Job '{job_slug}' not found"}

    B = Registry.F.Book
    C = Registry.F.Chapter
    doc = Store.bks_store_load(str(book_path))
    book = Store.bks_store_book(doc)
    chapters = [c for c in Store.bks_store_chapters(doc) if Store.bks_store_is_writable(c)]
    link = _get_cms_link(paths["cms_links"], job_slug)

    merge_info = cms_bks_merge_parts(cms_root, job_slug)
    final_title = (title_override or title or book[B.book_title_text] or "Untitled Blog Post").strip()
    final_category = (
        category_override or category or category_name or link.get("category") or book.get(B.book_category_name_text) or "Uncategorized"
    ).strip()
    final_author = (
        author_override or author or author_name or link.get("author") or book.get(B.book_author_name_text) or "boehnenelton2024"
    ).strip()
    final_page_type = (page_type_override or link.get("page_type") or "blog").strip()
    if final_page_type not in ("blog", "article", "page"):
        final_page_type = "blog"

    md_override = edited_markdown or merged_md_override
    if md_override is not None and md_override.strip():
        merged_md = md_override.strip() + "\n"
        parsed_article = convert_markdown_to_cms_article(merged_md, final_title)
        merged_html = merged_html_override or f'<article class="bejson-cms-article">\n{parsed_article["html_body"]}\n</article>'
        (paths["merged"] / f"{job_slug}.md").write_text(merged_md, encoding="utf-8")
        (paths["merged"] / f"{job_slug}.html").write_text(merged_html, encoding="utf-8")
    else:
        merged_md = merge_info.get("merged_markdown", "")
        merged_html = merged_html_override or merge_info.get("merged_html", "")

    if not merged_md.strip():
        return {"ok": False, "error": "Merged post is empty — execute at least one part before approving."}

    if chapters and all(c[C.chapter_status_text] == "accepted" for c in chapters):
        try:
            if book[B.book_status_text] == "draft":
                Store.bks_store_mark_complete(doc)
            if Store.bks_store_book(doc)[B.book_status_text] == "complete":
                Store.bks_store_finalize(doc)
            Store.bks_store_commit(str(book_path), doc, level=3)
            Export.bks_export_write(str(paths["root"]), str(book_path), doc, "md")
            Export.bks_export_write(str(paths["root"]), str(book_path), doc, "html", theme="becss")
        except Exception as exp_err:
            logger.warning("BKS export warning during approve: %s", exp_err)

    resolved_uuid = (target_page_uuid if target_page_uuid is not None else link.get("target_page_uuid") or "").strip()
    slug = re.sub(r"[^a-z0-9]+", "-", final_title.lower()).strip("-") or "post"

    db = CMSCore.CMSCore(str(paths["manifest"]))
    db.mount()
    existing_pages = db.get_records("PageRecord")
    existing_page = next((p for p in existing_pages if p.get("page_uuid") == resolved_uuid), None) if resolved_uuid else None

    overwritten_existing = False
    if existing_page:
        overwritten_existing = True
        upd_fields = {
            "page_title": final_title,
            "page_slug": slug,
            "page_cat_name": final_category,
            "page_author_name": final_author,
            "page_type": final_page_type,
        }
        if template_key:
            upd_fields["page_template_key"] = template_key
        db.update_record("PageRecord", "page_uuid", resolved_uuid, upd_fields)
    else:
        if not resolved_uuid:
            resolved_uuid = str(uuid.uuid4())
        db.add_record(
            "PageRecord",
            {
                "page_uuid": resolved_uuid,
                "page_title": final_title,
                "page_slug": slug,
                "page_cat_name": final_category,
                "page_type": final_page_type,
                "page_created_at": datetime.now().strftime("%Y-%m-%d"),
                "page_external_url": None,
                "page_author_name": final_author,
                "page_featured_img": "default_page_image.webp",
                "page_template_key": template_key or "blank",
            },
        )

    paths["pages_db"].mkdir(parents=True, exist_ok=True)
    pfile = paths["pages_db"] / f"{resolved_uuid}.json"
    existing_source_code = ""
    if pfile.exists():
        try:
            old_doc = Core.bejson_core_load_file(str(pfile))
            if old_doc and old_doc.get("Fields"):
                fm_old = Core.bejson_core_get_field_map(old_doc)
                p_idx = fm_old.get("Record_Type_Parent", -1)
                sc_idx = fm_old.get("source_code", -1)
                for r in old_doc.get("Values", []):
                    if p_idx != -1 and r[p_idx] == "Content" and sc_idx != -1 and sc_idx < len(r):
                        existing_source_code = r[sc_idx] or ""
        except Exception:
            pass

    content_doc = {
        "Format": "BEJSON",
        "Format_Version": "104db",
        "Format_Creator": "Elton Boehnen",
        "Records_Type": ["PageMeta", "Content"],
        "Fields": [
            {"name": "Record_Type_Parent", "type": "string"},
            {"name": "meta_title", "type": "string", "Record_Type_Parent": "PageMeta"},
            {"name": "html_body", "type": "string", "Record_Type_Parent": "Content"},
            {"name": "markdown_body", "type": "string", "Record_Type_Parent": "Content"},
            {"name": "source_code", "type": "string", "Record_Type_Parent": "Content"},
        ],
        "Values": [
            ["PageMeta", final_title, None, None, None],
            ["Content", None, merged_html, merged_md, existing_source_code],
        ],
    }
    Core.bejson_core_atomic_write(str(pfile), content_doc)

    now_utc = Derive.bks_derive_now_utc()
    link.update({
        "job_slug": job_slug,
        "target_page_uuid": resolved_uuid,
        "category": final_category,
        "author": final_author,
        "page_type": final_page_type,
        "approval_status": "approved",
        "approved_at": now_utc,
    })
    _upsert_cms_link(paths["cms_links"], link)

    published_site = False
    if trigger_publish:
        try:
            web_dir = str(_resolve_cms_root(cms_root) / "src" / "web")
            if web_dir not in sys.path:
                sys.path.insert(0, web_dir)
            from BEJSON_CMS_Publisher import _execute
            _execute()
            published_site = True
        except Exception as pub_err:
            logger.warning("Publisher execution warning after approve: %s", pub_err)

    return {
        "ok": True,
        "job_slug": job_slug,
        "target_page_uuid": resolved_uuid,
        "overwritten_existing": overwritten_existing,
        "title": final_title,
        "slug": slug,
        "category": final_category,
        "author": final_author,
        "page_type": final_page_type,
        "word_count": Derive.bks_derive_count_words(merged_md),
        "approval_status": "approved",
        "approved_at": now_utc,
        "published_site": published_site,
        "merged_markdown": merged_md,
        "merged_md": merged_md,
        "merged_html": merged_html,
        "merged_md_path": str(paths["merged"] / f"{job_slug}.md"),
        "merged_html_path": str(paths["merged"] / f"{job_slug}.html"),
    }

