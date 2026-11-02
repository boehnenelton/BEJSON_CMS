"""
Library:         lib_bejson_Writing_bks_render.py
Family:          Writing
Module Purpose:  Pure renderers (md, md_zip, html, txt, json, bejson): deterministic bytes from a validated Book Document; refuses drafts except preview; escapes all body text.
Architecture:    BKS-1 (BEJSON Book Standard) Writing family. Non-AI book organisation layer built on the frozen Core family (field-map cache, atomic write, validator, list validator). Contains no AI calls and no Flask code. Book Documents are BEJSON 104db; plans are the JobMaker 104a job schema.
Format_Scope:    104db (Book Document) | 104a (JobMaker plan)
Release_Version: 300
Version:         see VERSION below
Date:            2026-10-29
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   abb02ed4-3059-41cd-a2ab-f7a57e1b8e41
"""

import html as _html
import io
import json
import re
import zipfile
from typing import Dict, List, Optional

import lib_bejson_Writing_bks_derive as Derive
import lib_bejson_Writing_bks_errors as Errors
import lib_bejson_Writing_bks_registry as Registry
import lib_bejson_Writing_bks_store as Store
import lib_bejson_Writing_bks_validator as Validator

VERSION = "1.0.0"
RENDERER_VERSION = "1.0.0"
FORMATS = ("md", "md_zip", "html", "txt", "json", "bejson")
THEMES = ("becss", "plain")
FILE_EXTENSIONS = {"md": ".md", "md_zip": ".zip", "html": ".html", "txt": ".txt", "json": ".bks.json", "bejson": ".bks.bejson"}
CREDIT_LINE = "Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton"
_FENCE = re.compile(r"^\s*```")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")

_CSS = {
    "becss": ":root{--bg:#FFFFFF;--fg:#000000;--accent:#DE2626}@media (prefers-color-scheme:dark){:root{--bg:#000000;--fg:#FFFFFF}}"
             "body{margin:0;background:var(--bg);color:var(--fg);font:1rem/1.65 Georgia,'Times New Roman',serif}"
             "main{max-width:46rem;margin:0 auto;padding:1rem 1rem 3rem}h1{border-bottom:3px solid var(--accent)}"
             "a,a:hover{color:var(--fg)}a:hover{color:var(--accent)}h2,h3,h4{border-left:4px solid var(--accent);padding-left:.5rem}"
             "pre{overflow-x:auto;border:1px solid var(--fg);padding:.75rem}code{font-family:ui-monospace,Menlo,monospace}"
             "blockquote{border-left:4px solid var(--accent);margin:1rem 0;padding-left:1rem}nav{border:1px solid var(--fg);padding:.5rem 1rem}"
             "footer{margin-top:3rem;font-size:.85rem;border-top:1px solid var(--fg);padding-top:.75rem}",
    "plain": ":root{--bg:#FFFFFF;--fg:#000000}@media (prefers-color-scheme:dark){:root{--bg:#000000;--fg:#FFFFFF}}"
             "body{margin:0;background:var(--bg);color:var(--fg);font:1rem/1.6 system-ui,sans-serif}main{max-width:46rem;margin:0 auto;padding:1rem}"
             "pre{overflow-x:auto;border:1px solid var(--fg);padding:.5rem}a{color:var(--fg)}footer{margin-top:2rem;font-size:.85rem}",
}

def _fail(message: str) -> Errors.BKSError:
    return Errors.BKSError(Errors.E_BKS_RENDER_FAILED, message)

def _roman(n: int) -> str:
    out = ""
    for value, sym in ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= value:
            out, n = out + sym, n - value
    return out

# Why: R4 - models usually repeat the title as a leading heading; the renderer owns headings and numbering.
# Output: body without a first heading that duplicates the node title (numbering prefixes are ignored in the comparison).
def bks_render_strip_duplicate_heading(body: Optional[str], title: str) -> str:
    lines = (body or "").split("\n")
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines):
        m = _HEADING.match(lines[i])
        if m:
            norm = lambda t: re.sub(r"^(chapter|part|section)?\s*[\dIVXivx]+[.:)\-]?\s+", "", re.sub(r"[*_`]", "", t).strip(), flags=re.I).strip().lower()
            if norm(m.group(2)) == norm(title) or re.sub(r"[*_`]", "", m.group(2)).strip().lower() == title.strip().lower():
                i += 1
                while i < len(lines) and not lines[i].strip():
                    i += 1
                return "\n".join(lines[i:])
    return "\n".join(lines[i:]) if i else (body or "")

# Why: body headings are shifted under the node heading so the document outline stays a tree (fence-aware).
def bks_render_shift_headings(body: str, node_hashes: int) -> str:
    out, in_fence = [], False
    for line in body.split("\n"):
        if _FENCE.match(line):
            in_fence = not in_fence
        m = None if in_fence else _HEADING.match(line)
        out.append("#" * min(6, node_hashes + len(m.group(1)) - 1) + " " + m.group(2) if m else line)
    return "\n".join(out)

def _nodes(doc: dict) -> List[dict]:
    C = Registry.F.Chapter
    chapters = Store.bks_store_chapters(doc)
    by_id = {c[C.chapter_uuid]: c for c in chapters}
    nodes, part_no, chap_no, sec_no = [], 0, 0, 0
    for c in chapters:
        kind, depth, cur = c[C.chapter_kind_text], 1, c
        while cur[C.chapter_parent_uuid_fk] in by_id:
            depth, cur = depth + 1, by_id[cur[C.chapter_parent_uuid_fk]]
        if kind == "part":
            part_no += 1
            label = f"Part {_roman(part_no)}:"
        elif kind == "chapter":
            chap_no, sec_no = chap_no + 1, 0
            label = f"{chap_no}."
        elif kind == "section":
            sec_no += 1
            label = f"{chap_no}.{sec_no}"
        else:
            label = ""
        title = c[C.chapter_title_text]
        body = bks_render_strip_duplicate_heading(c[C.chapter_body_md], title) if c[C.chapter_body_md] else ""
        nodes.append({"row": c, "kind": kind, "hashes": min(6, depth + 1), "heading": (label + " " + title).strip(), "body": body})
    return nodes

def _front_matter(book: dict, status: str, source_hash: str) -> str:
    B = Registry.F.Book
    pairs = [("title", book[B.book_title_text]), ("author", book[B.book_author_name_text]), ("language", book[B.book_language_text]),
             ("version", book[B.book_version_text]), ("status", status), ("content_sha256", source_hash)]
    return "---\n" + "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in pairs) + "\n---\n"

def _md(doc: dict, status: str, credit: bool, source_hash: str) -> str:
    B = Registry.F.Book
    book = Store.bks_store_book(doc)
    parts = [_front_matter(book, status, source_hash), "# " + book[B.book_title_text] + "\n"]
    if book[B.book_subtitle_text]:
        parts.append("*" + book[B.book_subtitle_text] + "*\n")
    if status == "DRAFT":
        parts.append("> DRAFT preview - not a release.\n")
    for n in _nodes(doc):
        parts.append("#" * n["hashes"] + " " + n["heading"] + "\n")
        if n["body"]:
            parts.append(bks_render_shift_headings(n["body"], n["hashes"]) + "\n")
    if credit:
        parts.append("---\n\n*" + CREDIT_LINE + "*\n")
    return "\n".join(parts)

def _txt(doc: dict, status: str, credit: bool) -> str:
    B = Registry.F.Book
    book = Store.bks_store_book(doc)
    title = book[B.book_title_text]
    lines = [title, "=" * len(title)]
    if book[B.book_subtitle_text]:
        lines.append(book[B.book_subtitle_text])
    lines += ["by " + book[B.book_author_name_text], ""]
    if status == "DRAFT":
        lines += ["[DRAFT preview - not a release]", ""]
    for n in _nodes(doc):
        lines += [n["heading"], "-" * len(n["heading"]), ""]
        if n["body"]:
            lines += [re.sub(r"^#{1,6}\s+", "", ln) for ln in n["body"].split("\n")] + [""]
    if credit:
        lines += ["", CREDIT_LINE]
    return "\n".join(lines).rstrip() + "\n"

def _inline(escaped: str) -> str:
    pieces = escaped.split("`")
    if len(pieces) % 2 == 0:  # unbalanced backtick: leave the text as escaped, add no markup
        return escaped
    out = []
    for i, piece in enumerate(pieces):
        if i % 2:
            out.append("<code>" + piece + "</code>")
        else:
            piece = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", piece)
            out.append(re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", piece))
    return "".join(out)

# Why: R5 - every character of body text is escaped before any markup is added; only a small safe subset of Markdown is rendered and links are never made live.
def bks_render_markdown_to_html(body: str, node_hashes: int) -> str:
    out, para, items, kind, in_fence, code = [], [], [], None, False, []
    def flush_para():
        if para:
            out.append("<p>" + _inline(_html.escape(" ".join(para))) + "</p>")
            para.clear()
    def flush_list():
        nonlocal kind
        if items:
            out.append(f"<{kind}>" + "".join(f"<li>{_inline(_html.escape(i))}</li>" for i in items) + f"</{kind}>")
            items.clear()
        kind = None
    for line in bks_render_shift_headings(body, node_hashes).split("\n"):
        if _FENCE.match(line):
            if in_fence:
                out.append("<pre><code>" + _html.escape("\n".join(code)) + "</code></pre>")
                code.clear()
            else:
                flush_para(); flush_list()
            in_fence = not in_fence
            continue
        if in_fence:
            code.append(line)
            continue
        h, ul, ol, bq = _HEADING.match(line), re.match(r"^\s*[-*]\s+(.*)$", line), re.match(r"^\s*\d+[.)]\s+(.*)$", line), re.match(r"^>\s?(.*)$", line)
        if not line.strip():
            flush_para(); flush_list()
        elif h:
            flush_para(); flush_list()
            out.append(f"<h{len(h.group(1))}>{_inline(_html.escape(h.group(2)))}</h{len(h.group(1))}>")
        elif ul or ol:
            flush_para()
            want = "ul" if ul else "ol"
            if kind not in (None, want):
                flush_list()
            kind = want
            items.append((ul or ol).group(1))
        elif bq:
            flush_para(); flush_list()
            out.append("<blockquote>" + _inline(_html.escape(bq.group(1))) + "</blockquote>")
        else:
            flush_list()
            para.append(line.strip())
    if in_fence:
        out.append("<pre><code>" + _html.escape("\n".join(code)) + "</code></pre>")
    flush_para(); flush_list()
    return "\n".join(out)

def _html_page(doc: dict, status: str, theme: str, credit: bool, source_hash: str) -> str:
    B = Registry.F.Book
    e = _html.escape
    book = Store.bks_store_book(doc)
    nodes = _nodes(doc)
    toc = "".join(f'<li><a href="#n{n["row"][Registry.F.Chapter.chapter_order_index]}">{e(n["heading"])}</a></li>' for n in nodes)
    body = []
    for n in nodes:
        order = n["row"][Registry.F.Chapter.chapter_order_index]
        body.append(f'<section id="n{order}"><h{n["hashes"]}>{e(n["heading"])}</h{n["hashes"]}>' + bks_render_markdown_to_html(n["body"], n["hashes"]) + "</section>")
    foot = f"<p>{e(book[B.book_title_text])} · version {e(book[B.book_version_text])} · {e(status)} · content {e(source_hash[:12])}</p>"
    if credit:
        foot += f"<p>{e(CREDIT_LINE)}</p>"
    sub = f"<p><em>{e(book[B.book_subtitle_text])}</em></p>" if book[B.book_subtitle_text] else ""
    draft = "<p><strong>DRAFT preview - not a release.</strong></p>" if status == "DRAFT" else ""
    return ("<!DOCTYPE html>\n<html lang=\"" + e(book[B.book_language_text]) + "\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>" + e(book[B.book_title_text]) + "</title>"
            "<style>" + _CSS[theme] + "</style></head><body><main><h1>" + e(book[B.book_title_text]) + "</h1>" + sub
            + f"<p>by {e(book[B.book_author_name_text])}</p>" + draft + "<nav><ol>" + toc + "</ol></nav>" + "\n".join(body)
            + "<footer>" + foot + "</footer></main></body></html>\n")

def _json(doc: dict) -> str:
    tables = Store.bks_store_tables(doc)
    return json.dumps({"bks": "1.0.0", "book": tables["Book"][0], "chapters": Store.bks_store_chapters(doc),
                       "generations": tables["Generation"]}, indent=2, ensure_ascii=False) + "\n"

def _canonical_bejson(doc: dict) -> bytes:
    clean = {k: v for k, v in doc.items() if not k.startswith("_")}
    return (json.dumps(clean, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

def _zip(doc: dict, status: str, source_hash: str) -> bytes:
    B, C = Registry.F.Book, Registry.F.Chapter
    book = Store.bks_store_book(doc)
    slug = Derive.bks_derive_slugify(book[B.book_title_text])
    entries, listing = {}, []
    for n in _nodes(doc):
        row = n["row"]
        if n["kind"] == "part":
            continue
        name = f"{slug}/chapters/{row[C.chapter_order_index]:03d}-{Derive.bks_derive_slugify(row[C.chapter_title_text], 'chapter')}.md"
        entries[name] = ("# " + n["heading"] + "\n\n" + bks_render_shift_headings(n["body"], 1) + "\n").encode("utf-8")
        listing.append({"order": row[C.chapter_order_index], "uuid": row[C.chapter_uuid], "kind": n["kind"], "title": row[C.chapter_title_text],
                        "file": name.split("/", 1)[1], "word_count": row[C.chapter_word_count]})
    entries[f"{slug}/book.bks.bejson"] = _canonical_bejson(doc)
    entries[f"{slug}/metadata.json"] = (json.dumps({"bks": "1.0.0", "title": book[B.book_title_text], "subtitle": book[B.book_subtitle_text],
        "author": book[B.book_author_name_text], "language": book[B.book_language_text], "version": book[B.book_version_text], "status": status,
        "content_sha256": source_hash, "chapter_count": book[B.book_chapter_count], "word_count": book[B.book_word_count],
        "chapters": listing}, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            zf.writestr(info, entries[name])
    return buf.getvalue()

# Why: R1-R5 in one pure function: same document and options give the same bytes; it reads only the Book Document; a draft is refused unless preview.
# Input: Book Document, format (one of FORMATS), theme (html only), preview flag, credit flag.
# Output: {"bytes","filename","format","renderer","theme","source_sha256","status"}. Raises BKSError E_BKS_RENDER_FAILED.
def bks_render_book(doc: dict, fmt: str, *, theme: str = "becss", preview: bool = False, credit: bool = True) -> Dict[str, object]:
    if fmt not in FORMATS:
        raise _fail(f"unknown format '{fmt}'")
    if theme not in THEMES:
        raise _fail(f"unknown theme '{theme}'")
    check = Validator.bks_validate_book(doc, level=3)
    if check.level_reached < 3:
        raise _fail("document does not conform: " + check.problems[0].message)
    B = Registry.F.Book
    book = Store.bks_store_book(doc)
    if book[B.book_status_text] == "draft" and not preview:
        raise _fail("book is a draft; render a preview or complete the book first")
    status = "DRAFT" if (preview or book[B.book_status_text] == "draft") else book[B.book_status_text]
    source_hash = book[B.book_content_sha256_text]
    if fmt == "md":
        data = _md(doc, status, credit, source_hash).encode("utf-8")
    elif fmt == "txt":
        data = _txt(doc, status, credit).encode("utf-8")
    elif fmt == "html":
        data = _html_page(doc, status, theme, credit, source_hash).encode("utf-8")
    elif fmt == "json":
        data = _json(doc).encode("utf-8")
    elif fmt == "bejson":
        data = _canonical_bejson(doc)
    else:
        data = _zip(doc, status, source_hash)
    slug = Derive.bks_derive_slugify(book[B.book_title_text])
    return {"bytes": data, "filename": slug + FILE_EXTENSIONS[fmt], "format": fmt, "renderer": f"{fmt}@{RENDERER_VERSION}",
            "theme": theme if fmt == "html" else None, "source_sha256": source_hash, "status": status}
