"""
Library:         lib_bejson_Writing_bks_booktypes.py
Family:          Writing
Module Purpose:  BookType library: the nine built-in types as data, BEJSON 104 files, gate rules, outline templates and new-book creation from a type.
Architecture:    BKS-1 (BEJSON Book Standard) Writing family. Non-AI book organisation layer built on the frozen Core family (field-map cache, atomic write, validator, list validator). Contains no AI calls and no Flask code. Book Documents are BEJSON 104db; plans are the JobMaker 104a job schema.
Format_Scope:    104db (Book Document) | 104a (JobMaker plan)
Release_Version: 300
Version:         see VERSION below
Date:            2026-10-29
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   693ff49d-8490-402a-894c-0718062f5a18
"""

import os
import uuid
from typing import Dict, List, Optional

import lib_bejson_Core_bejson_core as Core
import lib_bejson_Writing_bks_errors as Errors
import lib_bejson_Writing_bks_gates as Gates
import lib_bejson_Writing_bks_registry as Registry
import lib_bejson_Writing_bks_store as Store

VERSION = "1.0.0"
BOOKTYPE_FILE_SUFFIX = ".bks-type.bejson"
BUILTIN_STAMP = "2026-10-25T09:00:00Z"
# Built-in BookType ids are uuid5(this namespace, slug), so every install derives the same id.
BOOKTYPE_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://boehnenelton2024.pages.dev/bks/booktype")

_PLAN = ("Produce a book title, a subtitle and an ordered outline of {chapter_count} chapters for %s. Each chapter has a title (no numbering) "
         "and a 2-4 sentence brief saying what it must cover and how it connects to the previous chapter.%s")

def _o(title: str, brief: str, part: Optional[str] = None, kind: str = "chapter") -> dict:
    item = {"title": title, "brief": brief, "kind": kind}
    if part:
        item["part"] = part
    return item

# slug, name, description, family, plan fragment, plan suffix, identity, outline, required sections, min/default/max chapters, min words, profile, exports
_BUILTINS = [
    ("general_document", "General Document", "A clear, well-organised document on any subject.", "nonfiction",
     "a general document", "", "You are a clear, careful writer producing a well-organised document. Use plain language and short paragraphs.",
     [_o("Overview", "What the document covers and who it is for."), _o("Main Content", "The substance, in logical order."), _o("Conclusion", "What the reader should take away.")],
     [], 1, 5, 30, 200, "standard", ["md", "html"]),
    ("standard_book", "Standard Book", "A conventional non-fiction book.", "nonfiction",
     "a non-fiction book", " Group chapters into parts only when the book has more than ten chapters.",
     "You are an experienced non-fiction author. Write engaging, well-structured chapters that build on one another and end by pointing to the next.",
     [_o("Introduction", "Why the subject matters and what the book will do."), _o("Core Ideas", "The central concepts, explained from first principles."), _o("Putting It Into Practice", "How the reader applies the ideas."), _o("Conclusion", "What was covered and where to go next.")],
     [], 3, 8, 40, 500, "standard", ["md", "html", "md_zip"]),
    ("technical_manual", "Technical Manual", "A practical, example-driven manual for practitioners.", "technical",
     "a practical technical manual", " Group chapters into at most four parts.",
     "You are a senior practitioner writing a precise, example-driven technical manual. Define terms on first use, show runnable examples, and end every chapter with a '## Summary' section.",
     [_o("Foundations", "Core concepts and the smallest working example.", "Foundations"), _o("Building Blocks", "The main components and how they compose.", "Foundations"), _o("Testing and Delivery", "Verifying and packaging the result.", "Delivery")],
     ["Summary"], 4, 8, 40, 600, "strict", ["md", "html", "md_zip"]),
    ("readme", "README", "A project README: what it is, how to install it, how to use it.", "technical",
     "a project README", "", "You are a maintainer writing a concise, scannable README. Lead with what the project does, give copy-paste commands, and avoid marketing language.",
     [_o("What It Is", "One paragraph on purpose and audience."), _o("Install and Run", "Exact commands, requirements and first run."), _o("Usage", "Common tasks with examples."), _o("Contributing and License", "How to help and under what terms.")],
     [], 3, 6, 12, 80, "standard", ["md"]),
    ("structural_report", "Structural Analysis Report", "A report that analyses how a system or document is structured.", "analysis",
     "a structural analysis report", "", "You are an analyst producing a rigorous structural analysis. State findings plainly, support each with evidence, and end every chapter with a '## Summary' section.",
     [_o("Scope and Method", "What was analysed and how."), _o("Structure Found", "The components and how they relate."), _o("Issues and Risks", "Weak points, with evidence."), _o("Recommendations", "Concrete next steps in priority order.")],
     ["Summary"], 3, 7, 20, 250, "strict", ["md", "html"]),
    ("code_analysis", "Code Analysis Document", "A document that analyses a codebase.", "analysis",
     "a code analysis document", "", "You are a senior engineer analysing code. Reference real files and functions, explain behaviour precisely, and end every chapter with a '## Summary' section.",
     [_o("Overview", "What the code does and how it is laid out."), _o("Key Modules", "The important modules and their responsibilities."), _o("Data and Control Flow", "How information moves through the system."), _o("Risks and Improvements", "Defects, debt and suggested changes.")],
     ["Summary"], 3, 7, 20, 250, "strict", ["md", "html"]),
    ("fiction_novel", "Fiction Novel", "A novel told in chapters.", "creative",
     "a novel", " Include a clear arc: setup, rising conflict, climax and resolution. Chapter briefs describe events, not themes.",
     "You are a novelist. Write vivid scenes with concrete detail, distinct character voices and forward momentum. Do not summarise; dramatise.",
     [_o("Opening", "Introduce the protagonist, setting and the disturbance that starts the story."), _o("Rising Conflict", "Stakes escalate and choices get harder."), _o("Climax", "The decisive confrontation."), _o("Resolution", "Consequences and the new normal.")],
     [], 8, 20, 60, 1500, "standard", ["md", "html", "md_zip"]),
    ("poetry_collection", "Poetry Collection", "A themed collection of poems.", "creative",
     "a poetry collection", " Each chapter is one poem or a short sequence, with a title and a one-sentence brief on subject and form.",
     "You are a poet. Favour concrete imagery, deliberate line breaks and economy of language. Keep each piece self-contained.",
     [_o("Opening Poem", "Sets the tone and central image of the collection."), _o("Middle Sequence", "Poems that develop and complicate the theme."), _o("Closing Poem", "A poem that resolves or reframes the collection.")],
     [], 5, 20, 100, 20, "none", ["md", "html"]),
    ("biography", "Biography", "A biography told chronologically.", "nonfiction",
     "a biography", " Order chapters chronologically and name the period each covers.",
     "You are a biographer. Write in a measured, evidence-based voice, distinguish fact from interpretation, and give each chapter a clear period.",
     [_o("Origins", "Family, place and early influences."), _o("Formative Years", "Education, first work and defining choices."), _o("Peak and Legacy", "Major achievements and lasting impact.")],
     [], 5, 12, 40, 800, "standard", ["md", "html", "md_zip"]),
]

# Why: built-in types are data, not code branches (BKS-1 9). One function builds each registry row.
# Output: list of BookType row dicts keyed by registry field names.
def bks_booktypes_builtin_rows() -> List[dict]:
    T = Registry.F.BookType
    rows = []
    for slug, name, desc, family, frag, suffix, identity, outline, required, lo, dflt, hi, words, profile, exports in _BUILTINS:
        rows.append({T.booktype_uuid: str(uuid.uuid5(BOOKTYPE_NAMESPACE, slug)), T.booktype_slug_text: slug, T.booktype_name_text: name,
                     T.booktype_description_text: desc, T.booktype_family_text: family,
                     T.booktype_plan_instruction_text: _PLAN % (frag, suffix), T.booktype_chapter_identity_text: identity,
                     T.booktype_outline_template_list: outline, T.booktype_required_sections_list: required or None,
                     T.booktype_min_chapters_count: lo, T.booktype_max_chapters_count: hi, T.booktype_default_chapters_count: dflt,
                     T.booktype_min_words_per_chapter_count: words, T.booktype_audit_profile_text: profile,
                     T.booktype_default_exports_list: exports, T.booktype_is_builtin_flag: True,
                     T.booktype_schema_version_text: Registry.BKS_SCHEMA_VERSION, T.booktype_created_at: BUILTIN_STAMP,
                     T.booktype_updated_at: BUILTIN_STAMP})
    # the technical_manual plan instruction is the standard's own text, verbatim
    rows[2][T.booktype_plan_instruction_text] = ("Produce a book title, a subtitle and an ordered outline of {chapter_count} chapters for a practical technical manual. "
        "Each chapter has a title (no numbering) and a 2-4 sentence brief saying what it must cover and how it connects to the previous chapter. Group chapters into at most four parts.")
    return rows

# Why: a BookType file is BEJSON 104 with the registry columns and one row.
def bks_booktypes_doc(row: dict) -> dict:
    fields = [{"name": fd.name, "type": fd.type} for fd in Registry.bks_registry_fields("BookType")]
    return Core.bejson_core_create_104("BookType", fields, [[row[fd["name"]] for fd in fields]])

# Why: first-run seeding writes the nine built-ins to book_types/<slug>.bks-type.bejson (atomic; existing files are left alone).
# Output: list of paths written.
def bks_booktypes_write_builtin(directory: str, overwrite: bool = False) -> List[str]:
    os.makedirs(directory, exist_ok=True)
    written = []
    for row in bks_booktypes_builtin_rows():
        path = os.path.join(directory, row[Registry.F.BookType.booktype_slug_text] + BOOKTYPE_FILE_SUFFIX)
        if os.path.exists(path) and not overwrite:
            continue
        if not Core.bejson_core_atomic_write(path, bks_booktypes_doc(row)):
            raise Errors.BKSError(Errors.E_BKS_STRUCTURE, f"could not write {path}")
        written.append(path)
    return written

# Why: read one BookType file through the field map.
# Output: row dict, or None when the file is missing or has no row.
def bks_booktypes_load(path: str) -> Optional[dict]:
    doc = Core.bejson_core_load_file(path)
    if not doc or not doc.get("Values"):
        return None
    fm = Core.bejson_core_get_field_map(doc)
    return {fd.name: doc["Values"][0][fm[fd.name]] for fd in Registry.bks_registry_fields("BookType")}

# Why: the library view lists every type in the folder.
# Output: {slug: row}.
def bks_booktypes_list(directory: str) -> Dict[str, dict]:
    out = {}
    if os.path.isdir(directory):
        for name in sorted(os.listdir(directory)):
            if name.endswith(BOOKTYPE_FILE_SUFFIX):
                row = bks_booktypes_load(os.path.join(directory, name))
                if row:
                    out[row[Registry.F.BookType.booktype_slug_text]] = row
    return out

# Why: the audit profile plus floors become the in-process gate (BKS-1 9.1). No shell is ever involved.
def bks_booktypes_gate_rules(row: dict) -> Optional[dict]:
    T = Registry.F.BookType
    return Gates.bks_gates_rules_for_profile(row[T.booktype_audit_profile_text], row[T.booktype_min_words_per_chapter_count],
                                             row[T.booktype_required_sections_list])

# Why: chapter limits apply when a plan is made, not when a book is opened.
# Output: None when n is within the type's limits, otherwise a message.
def bks_booktypes_check_chapter_count(row: dict, n: int) -> Optional[str]:
    T = Registry.F.BookType
    lo, hi = row[T.booktype_min_chapters_count], row[T.booktype_max_chapters_count]
    return None if lo <= n <= hi else f"{row[T.booktype_name_text]} allows {lo}-{hi} chapters, got {n}"

# Why: the type's starting outline becomes the node list of a new book.
# Input: type row and optional chapter count (the template is truncated, never padded). Output: node dicts for bks_store_create_book.
def bks_booktypes_outline_nodes(row: dict, chapter_count: Optional[int] = None) -> List[dict]:
    items = [dict(i) for i in (row[Registry.F.BookType.booktype_outline_template_list] or [])]
    return items[:chapter_count] if chapter_count else items

# Why: one call makes a new book from a type: slug, id, outline and gate-ready metadata.
def bks_booktypes_new_book(row: dict, *, chapter_count: Optional[int] = None, nodes: Optional[List[dict]] = None, **book_kwargs) -> dict:
    T = Registry.F.BookType
    return Store.bks_store_create_book(booktype_slug=row[T.booktype_slug_text], booktype_uuid=row[T.booktype_uuid],
                                       nodes=nodes if nodes is not None else bks_booktypes_outline_nodes(row, chapter_count), **book_kwargs)
