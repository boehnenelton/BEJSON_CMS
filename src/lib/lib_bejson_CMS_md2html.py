#!/usr/bin/env python3
# =============================================================================
# Library:      lib_bejson_CMS_md2html.py
# Description:  Automated pipeline for converting Markdown documentation drops
#               into native BEJSON CMS articles and pages.
#               Generates style-agnostic HTML wrapped in <article class="bejson-cms-article">
#               with responsive table wrappers, syntax code blocks, and callouts.
#               Writes two-part page records: site_master/data/pagerecord.bejson
#               and pages_db/<uuid>.json storing both html_body and raw markdown.
# Version:      1.0.0
# Author:       Elton Boehnen
# Date:         2026-11-02
# Relational_ID: bejson-cms-md2html-lib-001
# =============================================================================

import os
import sys
import re
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

VERSION = "1.0.0"

# -----------------------------------------------------------------------------
# HTML ESCAPING & SLUG GENERATION
# -----------------------------------------------------------------------------

def _escape_html(text: str) -> str:
    """Escape characters that are special in HTML content."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _slugify(text: str) -> str:
    """Generate clean URL anchor/path slugs from text."""
    slug = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", slug)


def _inline(text: str) -> str:
    """Convert inline Markdown elements while preserving code literals."""
    parts = []
    last = 0
    # Inline code first
    for m in re.finditer(r"`([^`]+)`", text):
        parts.append(_inline_spans(text[last:m.start()]))
        parts.append(f"<code>{_escape_html(m.group(1))}</code>")
        last = m.end()
    parts.append(_inline_spans(text[last:]))
    return "".join(parts)


def _inline_spans(text: str) -> str:
    """Handle bold, italic, strikethrough, links, and images."""
    # Images before links
    text = re.sub(
        r"!\[([^\]]*)\]\(([^)]+)\)",
        lambda m: f'<img src="{m.group(2)}" alt="{_escape_html(m.group(1))}" loading="lazy">',
        text,
    )
    # Links
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: f'<a href="{m.group(2)}">{_escape_html(m.group(1))}</a>',
        text,
    )
    # Bold + italic
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"___(.+?)___", r"<strong><em>\1</em></strong>", text)
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)
    # Italic
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"(?<!\w)_([^_\s][^_]*)_(?!\w)", r"<em>\1</em>", text)
    # Strikethrough
    text = re.sub(r"~~(.+?)~~", r"<del>\1</del>", text)
    return text


def _is_table_separator(line: str) -> bool:
    return bool(re.match(r"^\|?[\s\-:|]+[\|\-:]+[\s\-:|]*\|?$", line.strip()))


def _is_table_row(line: str) -> bool:
    return "|" in line


def _parse_table(lines: list) -> str:
    rows = []
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)

    if len(rows) < 2:
        return "<p>" + _inline(" ".join(lines)) + "</p>"

    html = ['<div class="table-container">', "<table>", "<thead>", "<tr>"]
    for cell in rows[0]:
        html.append(f"  <th>{_inline(cell)}</th>")
    html += ["</tr>", "</thead>", "<tbody>"]

    for row in rows[2:]:
        html.append("<tr>")
        for cell in row:
            html.append(f"  <td>{_inline(cell)}</td>")
        html.append("</tr>")
    html += ["</tbody>", "</table>", "</div>"]
    return "\n".join(html)


def sanitize_html(html_str: str) -> str:
    """Sanitize output by stripping MS Word XML and Mso styling."""
    html_str = re.sub(r"</?o:p[^>]*>", "", html_str, flags=re.IGNORECASE)
    html_str = re.sub(r'style="[^"]*mso-[^"]*"', "", html_str, flags=re.IGNORECASE)
    return html_str


# -----------------------------------------------------------------------------
# CORE MARKDOWN CONVERSION
# -----------------------------------------------------------------------------

def convert_markdown_to_cms_article(md_text: str, fallback_title: str = "Untitled Document") -> Dict[str, Any]:
    """
    Convert raw Markdown into a CMS-compliant article payload.
    Returns:
        title: Extracted or fallback title
        slug: URL-safe slug
        html_body: Converted style-agnostic HTML
        markdown_body: Verbatim markdown string
        excerpt: Short plaintext description
        headings: List of (level, title, slug)
    """
    lines = md_text.splitlines()
    output = []
    headings = []
    title = None
    i = 0

    def flush_paragraph(buf: list):
        if buf:
            content = _inline(" ".join(buf))
            output.append(f"<p>{content}</p>")
            buf.clear()

    para_buf = []

    while i < len(lines):
        line = lines[i]

        # --- Fenced code block (``` or ~~~) ---
        fence_match = re.match(r"^\s*(`{3,}|~{3,})\s*([^\s`~]*)", line)
        if fence_match:
            flush_paragraph(para_buf)
            fence_char = fence_match.group(1)
            lang = fence_match.group(2).strip().lower()
            lang_attr = f' class="language-{_escape_html(lang)}"' if lang else ""
            code_lines = []
            i += 1
            while i < len(lines):
                if re.match(rf"^\s*{re.escape(fence_char[:3])}+\s*$", lines[i]):
                    break
                code_lines.append(_escape_html(lines[i]))
                i += 1
            joined_code = "\n".join(code_lines)
            output.append(f"<pre><code{lang_attr}>{joined_code}</code></pre>")
            i += 1
            continue

        # --- Horizontal rule ---
        if re.match(r"^(\*{3,}|-{3,}|_{3,})\s*$", line.strip()):
            flush_paragraph(para_buf)
            output.append("<hr>")
            i += 1
            continue

        # --- ATX Headings ---
        heading_match = re.match(r"^(#{1,6})\s+(.*)", line)
        if heading_match:
            flush_paragraph(para_buf)
            level = len(heading_match.group(1))
            heading_raw = heading_match.group(2).strip()
            slug = _slugify(heading_raw)
            if level == 1 and title is None:
                title = heading_raw
            headings.append((level, heading_raw, slug))
            text = _inline(heading_raw)
            output.append(f'<h{level} id="{slug}">{text}</h{level}>')
            i += 1
            continue

        # --- GitHub-style Callouts (> [!NOTE]) ---
        callout_match = re.match(r"^>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*(.*)", line, flags=re.IGNORECASE)
        if callout_match:
            flush_paragraph(para_buf)
            kind = callout_match.group(1).lower()
            extra = callout_match.group(2).strip()
            bq_lines = []
            if extra:
                bq_lines.append(extra)
            i += 1
            while i < len(lines) and lines[i].startswith(">"):
                clean_line = lines[i].lstrip("> ").rstrip()
                if clean_line:
                    bq_lines.append(clean_line)
                i += 1
            inner_content = _inline(" ".join(bq_lines)) if bq_lines else ""
            output.append(
                f'<blockquote class="callout callout-{kind}"><p><strong>{kind.title()}:</strong> {inner_content}</p></blockquote>'
            )
            continue

        # --- Standard Blockquote ---
        if line.startswith(">"):
            flush_paragraph(para_buf)
            bq_lines = []
            while i < len(lines) and lines[i].startswith(">"):
                bq_lines.append(lines[i].lstrip("> ").rstrip())
                i += 1
            inner = convert_markdown_to_cms_article("\n".join(bq_lines)).get("html_body", "")
            output.append(f"<blockquote>\n{inner}\n</blockquote>")
            continue

        # --- Task lists ---
        task_match = re.match(r"^\s*[\*\-\+]\s+\[([ xX])\]\s+(.*)", line)
        if task_match:
            flush_paragraph(para_buf)
            output.append('<ul class="task-list">')
            while i < len(lines):
                tm = re.match(r"^\s*[\*\-\+]\s+\[([ xX])\]\s+(.*)", lines[i])
                if not tm:
                    break
                checked = ' checked="checked"' if tm.group(1).lower() == "x" else ""
                item_text = _inline(tm.group(2).strip())
                output.append(
                    f'<li class="task-item"><input type="checkbox" disabled{checked}> <span>{item_text}</span></li>'
                )
                i += 1
            output.append("</ul>")
            continue

        # --- Bullet lists ---
        if re.match(r"^\s*[\*\-\+]\s+(.*)", line):
            flush_paragraph(para_buf)
            output.append("<ul>")
            while i < len(lines) and re.match(r"^\s*[\*\-\+]\s+(.*)", lines[i]):
                if re.match(r"^\s*[\*\-\+]\s+\[([ xX])\]\s+", lines[i]):
                    break
                m = re.match(r"^\s*[\*\-\+]\s+(.*)", lines[i])
                item_text = _inline(m.group(1).strip())
                output.append(f"<li>{item_text}</li>")
                i += 1
            output.append("</ul>")
            continue

        # --- Ordered lists ---
        if re.match(r"^\s*\d+\.\s+(.*)", line):
            flush_paragraph(para_buf)
            output.append("<ol>")
            while i < len(lines) and re.match(r"^\s*\d+\.\s+(.*)", lines[i]):
                m = re.match(r"^\s*\d+\.\s+(.*)", lines[i])
                item_text = _inline(m.group(1).strip())
                output.append(f"<li>{item_text}</li>")
                i += 1
            output.append("</ol>")
            continue

        # --- Tables ---
        if (
            _is_table_row(line)
            and i + 1 < len(lines)
            and _is_table_separator(lines[i + 1])
        ):
            flush_paragraph(para_buf)
            table_lines = []
            while i < len(lines) and _is_table_row(lines[i]):
                table_lines.append(lines[i])
                i += 1
            output.append(_parse_table(table_lines))
            continue

        # --- Blank line ---
        if line.strip() == "":
            flush_paragraph(para_buf)
            i += 1
            continue

        # --- Paragraph text ---
        para_buf.append(line.strip())
        i += 1

    flush_paragraph(para_buf)
    html_content = sanitize_html("\n".join(output))

    final_title = title or fallback_title
    final_slug = _slugify(final_title)

    # Extract clean excerpt
    excerpt = ""
    for line in md_text.splitlines():
        line = line.strip()
        if (
            line
            and not line.startswith("#")
            and not line.startswith("|")
            and not line.startswith(">")
            and not line.startswith("`")
            and not line.startswith("-")
            and not line.startswith("*")
        ):
            plain = re.sub(r"\*{1,3}|_{1,3}|~~|`", "", line)
            plain = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", plain).strip()
            if plain:
                excerpt = (plain[:152] + "...") if len(plain) > 155 else plain
                break

    return {
        "title": final_title,
        "slug": final_slug,
        "html_body": html_content,
        "markdown_body": md_text,
        "excerpt": excerpt,
        "headings": headings,
    }


# -----------------------------------------------------------------------------
# TWO-PART CMS PAGE INGESTION
# -----------------------------------------------------------------------------

def write_page_content_store(pages_db_dir: Path, page_uuid: str, title: str, html_body: str, markdown_body: str = "") -> Path:
    """Write two-part page content file under pages_db/<uuid>.json using BEJSON 104a."""
    pfile = pages_db_dir / f"{page_uuid}.json"
    doc = {
        "Format": "BEJSON",
        "Format_Version": "104a",
        "Format_Creator": "Elton Boehnen",
        "Records_Type": ["PageContent"],
        "Fields": [
            {"name": "Record_Type_Parent", "type": "string"},
            {"name": "meta_title", "type": "string"},
            {"name": "html_body", "type": "string"},
            {"name": "markdown_body", "type": "string"},
            {"name": "source_code", "type": "string"},
        ],
        "Values": [
            ["PageMeta", title, None, None, None],
            ["Content", None, html_body, markdown_body, ""],
        ],
    }
    pages_db_dir.mkdir(parents=True, exist_ok=True)
    tmp = pfile.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    os.replace(tmp, pfile)
    return pfile


def import_markdown_file_to_cms(
    md_path: Path,
    category: str = "Uncategorized",
    author: str = "boehnenelton2024",
    page_type: str = "blog",
    featured_img: str = "default_page_image.webp",
    cms_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Import a Markdown file into the CMS database as a native article.
    Updates site_master/data/pagerecord.bejson and writes pages_db/<uuid>.json.
    """
    if cms_root is None:
        cms_root = Path(__file__).resolve().parent.parent.parent

    site_master_dir = cms_root / "storage" / "mfdb" / "site_master"
    pagerecord_file = site_master_dir / "data" / "pagerecord.bejson"
    manifest_file = site_master_dir / "104a.mfdb.bejson"
    pages_db_dir = cms_root / "storage" / "mfdb" / "pages_db"

    md_text = md_path.read_text(encoding="utf-8")
    fallback_title = md_path.stem.replace("_", " ").replace("-", " ").title()
    parsed = convert_markdown_to_cms_article(md_text, fallback_title)

    title = parsed["title"]
    slug = parsed["slug"]
    html_body = parsed["html_body"]
    markdown_body = parsed["markdown_body"]

    # Wrap in canonical style-agnostic CMS article container
    wrapped_html = f'<article class="bejson-cms-article">\n{html_body}\n</article>'

    new_uuid = str(uuid.uuid4())
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Load pagerecord.bejson and resolve fields with O(1) field map
    if pagerecord_file.exists():
        pagerecord_doc = json.loads(pagerecord_file.read_text(encoding="utf-8"))
    else:
        pagerecord_doc = {
            "Format": "BEJSON",
            "Format_Version": "104a",
            "Format_Creator": "Elton Boehnen",
            "Records_Type": ["PageRecord"],
            "Fields": [
                {"name": "page_uuid", "type": "string"},
                {"name": "page_title", "type": "string"},
                {"name": "page_slug", "type": "string"},
                {"name": "page_cat_name", "type": "string"},
                {"name": "page_type", "type": "string"},
                {"name": "page_created_at", "type": "string"},
                {"name": "page_external_url", "type": "string"},
                {"name": "page_author_name", "type": "string"},
                {"name": "page_featured_img", "type": "string"},
                {"name": "page_featured_video_url", "type": "string"},
                {"name": "page_is_standalone_flag", "type": "boolean"},
            ],
            "Values": [],
        }

    fields = [f["name"] for f in pagerecord_doc.get("Fields", [])]
    field_map = {name: idx for idx, name in enumerate(fields)}

    # Construct new row matching exact schema columns
    new_row = [None] * len(fields)
    def set_cell(col: str, val: Any):
        if col in field_map:
            new_row[field_map[col]] = val

    set_cell("page_uuid", new_uuid)
    set_cell("page_title", title)
    set_cell("page_slug", slug)
    set_cell("page_cat_name", category)
    set_cell("page_type", page_type)
    set_cell("page_created_at", today_str)
    set_cell("page_external_url", None)
    set_cell("page_author_name", author)
    set_cell("page_featured_img", featured_img)
    set_cell("page_featured_video_url", None)
    set_cell("page_is_standalone_flag", (page_type == "page"))

    pagerecord_doc["Values"].append(new_row)

    # Write two-part content file
    write_page_content_store(pages_db_dir, new_uuid, title, wrapped_html, markdown_body)

    # Atomic write pagerecord.bejson
    tmp = pagerecord_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(pagerecord_doc, indent=2), encoding="utf-8")
    os.replace(tmp, pagerecord_file)

    # Update manifest entity count if manifest exists
    if manifest_file.exists():
        try:
            m_doc = json.loads(manifest_file.read_text(encoding="utf-8"))
            m_fields = [f["name"] for f in m_doc.get("Fields", [])]
            m_fmap = {n: i for i, n in enumerate(m_fields)}
            name_idx = m_fmap.get("entity_name", 0)
            count_idx = m_fmap.get("record_count", 3)
            for m_row in m_doc.get("Values", []):
                if m_row[name_idx] == "PageRecord":
                    m_row[count_idx] = len(pagerecord_doc["Values"])
                    break
            m_tmp = manifest_file.with_suffix(".tmp")
            m_tmp.write_text(json.dumps(m_doc, indent=2), encoding="utf-8")
            os.replace(m_tmp, manifest_file)
        except Exception:
            pass

    return {
        "page_uuid": new_uuid,
        "title": title,
        "slug": slug,
        "category": category,
        "page_type": page_type,
        "author": author,
        "featured_img": featured_img,
        "file_path": str(md_path),
    }


def batch_import_markdown_directory(
    dir_path: Path,
    category: str = "Uncategorized",
    author: str = "boehnenelton2024",
    page_type: str = "blog",
    default_featured_img: str = "default_page_image.webp",
    recursive: bool = False,
    cms_root: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Scan a directory for Markdown drops and batch convert them into CMS articles."""
    pattern = "**/*.md" if recursive else "*.md"
    md_files = sorted(dir_path.glob(pattern))
    results = []

    for md_file in md_files:
        try:
            res = import_markdown_file_to_cms(
                md_path=md_file,
                category=category,
                author=author,
                page_type=page_type,
                featured_img=default_featured_img,
                cms_root=cms_root,
            )
            results.append(res)
        except Exception as err:
            sys.stderr.write(f"Error importing {md_file.name}: {err}\n")

    return results
