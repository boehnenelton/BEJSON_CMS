"""
Library:         lib_bejson_Writing_bks_export.py
Family:          Writing
Module Purpose:  Export operation: render, atomic file write, Export row (renderer, theme, path, hashes) and C4 commit; staleness listing and preview.
Architecture:    BKS-1 (BEJSON Book Standard) Writing family. Non-AI book organisation layer built on the frozen Core family (field-map cache, atomic write, validator, list validator). Contains no AI calls and no Flask code. Book Documents are BEJSON 104db; plans are the JobMaker 104a job schema.
Format_Scope:    104db (Book Document) | 104a (JobMaker plan)
Release_Version: 300
Version:         see VERSION below
Date:            2026-10-29
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   10000d9c-b712-4137-8891-e8d1508eeeac
"""

import hashlib
import os
import tempfile
from typing import List, Optional

import lib_bejson_Writing_bks_derive as Derive
import lib_bejson_Writing_bks_errors as Errors
import lib_bejson_Writing_bks_registry as Registry
import lib_bejson_Writing_bks_render as Render
import lib_bejson_Writing_bks_store as Store

VERSION = "1.0.0"
EXPORTS_DIRNAME = "exports"

# Why: R6 - an export is rendered, written atomically, recorded as an Export row, and the book is committed at C4, all as one operation.
# Input: project root (all stored paths are relative to it), the book's file path, the document, a format and theme.
# Output: the new Export row. Re-exporting the same format and path replaces its row. Raises BKSError on a refused render or commit.
def bks_export_write(project_root: str, book_path: str, doc: dict, fmt: str, *, theme: str = "becss", credit: bool = True,
                     now: Optional[str] = None) -> dict:
    X = Registry.F.Export
    rendered = Render.bks_render_book(doc, fmt, theme=theme, credit=credit)
    slug = Derive.bks_derive_slugify(Store.bks_store_book(doc)[Registry.F.Book.book_title_text])
    rel = f"{EXPORTS_DIRNAME}/{slug}/{rendered['filename']}"
    target = os.path.join(project_root, *rel.split("/"))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(rendered["bytes"])
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    row = {X.export_uuid: Derive.bks_derive_new_uuid(), X.export_book_uuid_fk: Store.bks_store_book(doc)[Registry.F.Book.book_uuid],
           X.export_format_text: fmt, X.export_renderer_text: rendered["renderer"], X.export_theme_text: rendered["theme"],
           X.export_path_text: rel, X.export_size_bytes_count: len(rendered["bytes"]),
           X.export_sha256_text: hashlib.sha256(rendered["bytes"]).hexdigest(),
           X.export_source_content_sha256_text: rendered["source_sha256"], X.export_created_at: now or Derive.bks_derive_now_utc()}
    tables = Store.bks_store_tables(doc)
    tables["Export"] = [r for r in tables["Export"] if not (r[X.export_format_text] == fmt and r[X.export_path_text] == rel)] + [row]
    Store.bks_store_set_tables(doc, tables)
    Store.bks_store_commit(book_path, doc, level=4)
    return row

# Why: the library view shows "needs re-render" from the rows alone (BKS-1 11.3).
# Output: Export rows whose source hash differs from the book's current hash.
def bks_export_stale(doc: dict) -> List[dict]:
    current = Store.bks_store_book(doc)[Registry.F.Book.book_content_sha256_text]
    return [r for r in Store.bks_store_rows(doc, "Export") if r[Registry.F.Export.export_source_content_sha256_text] != current]

# Why: R3 preview - render a draft with a DRAFT stamp and write no Export row.
# Output: render result dict (bytes, filename, ...).
def bks_export_preview(doc: dict, fmt: str = "md", *, theme: str = "becss") -> dict:
    return Render.bks_render_book(doc, fmt, theme=theme, preview=True)
