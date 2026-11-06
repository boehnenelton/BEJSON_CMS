#!/usr/bin/env python3
"""
Library:        cms_quick_poster.py
Family:         CMS
Description:    High-speed CLI utility for rapid post/chapter creation, category resolution, and static publishing.
Version:        100
Date:           2026-11-06
Author:         Elton Boehnen
Contact:        boehnenelton2024@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  c0316e68-0775-45dc-b1e7-8b093df02391
"""

import os
import sys
import json
import uuid
import re
import argparse
from pathlib import Path
from datetime import datetime

# Portability Logic
SCRIPT_PATH = Path(__file__).resolve().parent
CMS_ROOT = SCRIPT_PATH.parent.parent.parent
SRC_DIR = CMS_ROOT / "src"
LIB_DIR = SRC_DIR / "lib"
WEB_DIR = SRC_DIR / "web"

for path_dir in (str(CMS_ROOT), str(SRC_DIR), str(LIB_DIR), str(WEB_DIR)):
    if path_dir not in sys.path:
        sys.path.insert(0, path_dir)

try:
    import lib_bejson_Core_bejson_core as BEJSONCore
    from lib_bejson_CMS_cms_core import CMSCore
except ImportError as err:
    print(f"[!] Error loading core libraries: {err}")
    sys.exit(1)

MANIFEST_PATH = CMS_ROOT / "storage" / "mfdb" / "site_master" / "104a.mfdb.bejson"
PAGES_DB_DIR = CMS_ROOT / "storage" / "mfdb" / "pages_db"
DEFAULT_FEATURED_IMAGE = "default_page_image.webp"


def get_db():
    return CMSCore(str(MANIFEST_PATH))


def write_page_content_file(page_uuid: str, title: str, html_body: str):
    PAGES_DB_DIR.mkdir(parents=True, exist_ok=True)
    pfile = PAGES_DB_DIR / f"{page_uuid}.json"
    doc = {
        "Format": "BEJSON",
        "Format_Version": "104db",
        "Format_Creator": "Elton Boehnen",
        "Records_Type": ["PageMeta", "Content"],
        "Fields": [
            {"name": "Record_Type_Parent", "type": "string"},
            {"name": "meta_title", "type": "string"},
            {"name": "html_body", "type": "string"},
            {"name": "markdown_body", "type": "string"},
            {"name": "source_code", "type": "string"}
        ],
        "Values": [
            ["PageMeta", title, None, None, None],
            ["Content", None, html_body, "", ""]
        ]
    }
    tmp = pfile.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
    os.replace(tmp, pfile)
    return pfile


def trigger_publish():
    print("[*] Triggering static site build...")
    try:
        from BEJSON_CMS_Publisher import _execute
        _execute()
        print("[✓] Static site successfully republished.")
    except Exception as err:
        print(f"[!] Build error: {err}")


def cmd_post(args):
    db = get_db()
    new_uuid = str(uuid.uuid4())
    slug = args.slug or re.sub(r'[^a-z0-9]', '-', args.title.lower()).strip('-')

    # Auto-resolve / auto-create category
    cats = [c.get("cat_name") for c in db.get_records("Category")]
    if args.category not in cats:
        cat_slug = re.sub(r'[^a-z0-9]', '-', args.category.lower()).strip('-')
        db.add_record("Category", {"cat_name": args.category, "cat_slug": cat_slug})
        print(f"[+] Auto-created missing category: '{args.category}' ({cat_slug})")

    html_body = ""
    if args.body_file:
        with open(args.body_file, "r", encoding="utf-8") as f:
            html_body = f.read()
    elif args.md_file:
        try:
            from lib_bejson_CMS_md2html import md_to_html
            with open(args.md_file, "r", encoding="utf-8") as f:
                html_body = md_to_html(f.read())
        except Exception:
            with open(args.md_file, "r", encoding="utf-8") as f:
                html_body = f"<pre>{f.read()}</pre>"
    elif args.body:
        html_body = args.body
    elif not sys.stdin.isatty():
        html_body = sys.stdin.read()
    else:
        html_body = f"<h2>{args.title}</h2><p>Content body placeholder...</p>"

    featured_img = args.featured_img or DEFAULT_FEATURED_IMAGE
    author_name = args.author or "Leethaxor69"
    post_type = args.type or "blog"

    if db.add_record("PageRecord", {
        "page_uuid": new_uuid,
        "page_title": args.title,
        "page_slug": slug,
        "page_cat_name": args.category,
        "page_type": post_type,
        "page_created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "page_external_url": "",
        "page_author_name": author_name,
        "page_featured_img": featured_img,
        "page_template_key": "post.html",
        "page_featured_video_url": args.featured_video or ""
    }):
        write_page_content_file(new_uuid, args.title, html_body)
        print(f"[✓] Quick post created: '{args.title}'")
        print(f"    UUID:     {new_uuid}")
        print(f"    Slug:     {slug}")
        print(f"    Category: {args.category}")
        print(f"    Author:   {author_name}")
        if args.publish:
            trigger_publish()
    else:
        print(f"[!] Failed to create quick post: {args.title}")


def cmd_append(args):
    pfile = PAGES_DB_DIR / f"{args.uuid}.json"
    if not pfile.exists():
        print(f"[!] Page file not found: {pfile}")
        return

    content_to_append = ""
    if args.body_file:
        with open(args.body_file, "r", encoding="utf-8") as f:
            content_to_append = f.read()
    elif args.md_file:
        try:
            from lib_bejson_CMS_md2html import md_to_html
            with open(args.md_file, "r", encoding="utf-8") as f:
                content_to_append = md_to_html(f.read())
        except Exception:
            with open(args.md_file, "r", encoding="utf-8") as f:
                content_to_append = f"<pre>{f.read()}</pre>"
    elif args.body:
        content_to_append = args.body
    elif not sys.stdin.isatty():
        content_to_append = sys.stdin.read()

    if not content_to_append:
        print("[!] Error: No content provided to append.")
        return

    with open(pfile, "r", encoding="utf-8") as f:
        data = json.load(f)

    field_map = BEJSONCore.bejson_core_get_field_map(data)
    p_idx = field_map.get("Record_Type_Parent", -1)
    h_idx = field_map.get("html_body", -1)
    updated = False

    for row in data.get("Values", []):
        if p_idx != -1 and row[p_idx] == "Content" and h_idx != -1:
            row[h_idx] = (row[h_idx] or "") + "\n" + content_to_append
            updated = True

    if updated:
        tmp = pfile.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, pfile)
        print(f"[✓] Appended content to page {args.uuid}")
        if args.publish:
            trigger_publish()
    else:
        print(f"[!] Failed to locate Content row in {pfile}")


def cmd_category(args):
    db = get_db()
    slug = args.slug or re.sub(r'[^a-z0-9]', '-', args.name.lower()).strip('-')
    existing = next((c for c in db.get_records("Category") if c.get("cat_slug") == slug), None)
    if existing:
        print(f"[!] Category with slug '{slug}' already exists.")
        return
    if db.add_record("Category", {"cat_name": args.name, "cat_slug": slug}):
        print(f"[✓] Category created: '{args.name}' ({slug})")
        if args.publish:
            trigger_publish()
    else:
        print(f"[!] Failed to create category: {args.name}")


def main():
    parser = argparse.ArgumentParser(description="BEJSON CMS Quick Poster & Publisher")
    subparsers = parser.add_subparsers(dest="command")

    # Post
    p_post = subparsers.add_parser("post", help="Create a post quickly")
    p_post.add_argument("title", help="Post title")
    p_post.add_argument("--category", default="Uncategorized", help="Category name (auto-created if missing)")
    p_post.add_argument("--author", default="Leethaxor69", help="Author display name")
    p_post.add_argument("--slug", help="Custom URL slug")
    p_post.add_argument("--body", help="HTML body string")
    p_post.add_argument("--body-file", help="File with HTML content")
    p_post.add_argument("--md-file", help="File with Markdown content")
    p_post.add_argument("--featured-img", default=DEFAULT_FEATURED_IMAGE, help="Featured image filename")
    p_post.add_argument("--featured-video", help="YouTube watch URL or video ID")
    p_post.add_argument("--type", default="blog", choices=["blog", "article", "page"], help="Page type")
    p_post.add_argument("--publish", action="store_true", help="Publish immediately after creation")

    # Append
    p_app = subparsers.add_parser("append", help="Append content to a page")
    p_app.add_argument("uuid", help="Page UUID")
    p_app.add_argument("--body", help="HTML string to append")
    p_app.add_argument("--body-file", help="File with HTML to append")
    p_app.add_argument("--md-file", help="File with Markdown to append")
    p_app.add_argument("--publish", action="store_true", help="Publish immediately")

    # Category
    p_cat = subparsers.add_parser("category", help="Create a category quickly")
    p_cat.add_argument("name", help="Category name")
    p_cat.add_argument("slug", nargs="?", default=None, help="Category slug")
    p_cat.add_argument("--publish", action="store_true", help="Publish immediately")

    # Publish
    subparsers.add_parser("publish", help="Compile and publish static site")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    if args.command == "post":
        cmd_post(args)
    elif args.command == "append":
        cmd_append(args)
    elif args.command == "category":
        cmd_category(args)
    elif args.command == "publish":
        trigger_publish()


if __name__ == "__main__":
    main()
