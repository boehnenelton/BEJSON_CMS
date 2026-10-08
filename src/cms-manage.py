#!/usr/bin/env python3
"""
Script:        cms-manage.py
Description:   Unified CLI Toolkit for BEJSON_CMS management.
Version:       18.12
Author:        Elton Boehnen
Date:          2026-09-20
Relational_ID: e0336281-1672-4062-a13a-0396e19e8d90
CHANGE (2026-09-20): PKG139 -- deferred-item sweep decisions (Elton). Removed
`mount`/`commit`/`repack` entirely -- deprecated escape hatches into the old
disconnected workspace/archive model, superseded by backup/restore (real
live-data snapshots) for a long time before this. get_manager()/
MFDB_CMS_Manager itself was NOT removed -- cmd_status() still reports on
that legacy workspace read-only in case something outside this CLI still
touches the archive directly; its printed NOTE updated to stop referencing
the now-gone commands. Also added app_created_at to `app add`'s
StandaloneApp record (see BEJSON_CMS_System.py's pkg139 entry for the
schema/self-heal side -- BEJSON_CMS_Publisher.py already read this field
defensively via .get() with a build-date fallback, so nothing there needed
to change, it just had nothing to read until now). Verified live: `mount`/
`commit` now correctly error as unknown commands, `status` still runs
clean with corrected messaging; `app add` confirmed writing a real
app_created_at, cleaned up after.
CHANGE (2026-09-16): PKG137 -- two things (Elton: continued CLI streamlining
+ "keep making everything uuid based").

(1) New commands: `find <entity> <query>` (fuzzy case-insensitive name->
UUID lookup across all 10 registered entity types -- _ENTITY_REGISTRY is
the new single source of truth for entity/uuid-field/name-fields, kept
separate from the older _DB_ENTITY_MAP used by `db list` rather than
merged into it, since that one has a different shape (a filter field, not
a uuid field) already in use); `export`/`import` (JSON or CSV round-trip
per entity -- import always generates a FRESH uuid for every row
regardless of what the file contains, even a re-imported previous export,
and skips a row whose name case-insensitively matches an existing live
record rather than creating a duplicate); `category merge <source> <into>`
(reassigns pages, deletes source, same "can't touch Uncategorized" guard
as rename, for the same self-heal reason). The previously-proposed --json
flag turned out to be unnecessary -- every `list` command already emits
clean JSON.

(2) Extended pkg135's uuid work into PageRecord's page_cat_name/
page_author_name: added page_cat_uuid/page_author_uuid, resolved and kept
in sync on every write in this file (cmd_page_add, cmd_page_update, both
branches of cmd_page_import) via a new _resolve_page_fk_uuids() helper.
cmd_category_merge (added earlier in this same entry) initially only
moved page_cat_name to the target category on merge -- found and fixed
before shipping: page_cat_uuid needs the TARGET's uuid on merge (identity
actually changes), unlike rename where it doesn't (same record, new
name only).

Every piece of both (1) and (2) verified live against real data end to
end -- find, export, import (JSON+CSV, fresh vs. duplicate), merge
(including the Uncategorized guard), and all four page commands' new FK
resolution -- with `doctor` run clean before and after as an extra check,
not just the individual round-trips. Live data confirmed back to its
exact original state after every test in this pass.
CHANGE (2026-09-14): PKG136 -- advanced CLI streamlining (Elton). Added
`author rename <old> <new>` and `category rename <slug> <new-name>` /
`category update` (now cascade-safe) -- both were previously either
impossible (author had no name-change path at all) or silently broken
(category update changed Category.cat_name but never touched
PageRecord.page_cat_name, so renamed categories quietly orphaned every
page already in them -- found while building this, not previously known).
Both new/fixed commands cascade the rename to every PageRecord that
references the old name, and both refuse a rename that would collide
case-insensitively with an existing different record. category rename
additionally refuses to rename "Uncategorized" itself -- found live while
testing: BEJSON_CMS_System.py's self-heal recreates a category by that
exact name on every boot if missing, so renaming it away would leave a
stray duplicate next restart. Also modernized cmd_author_update/delete to
resolve the typed name case-insensitively before keying the actual
operation by author_uuid (a softer version of the pkg134 bug class -- a
case-only typo could previously silently report "not found" even though
the author clearly existed).

Added `doctor` -- a health-check command bundling two checks the pkg135
UUID work made newly relevant: (1) orphaned page_cat_name/page_author_name
references (both are still plain name strings by design -- pkg135
deliberately didn't convert them to UUID FKs -- so nothing else catches a
page pointing at a category/author name that no longer exists), and (2)
case-insensitive duplicate names across AuthorProfile/Category/NavLink/
SocialLink/AI_Profile (only Author and Category are guarded against this
at add-time; Nav/Social aren't). Exits 1 if anything is found, for
scripting.

Every piece of this verified live against real data, not just compiled:
add->rename->verify-cascade->cleanup for both author and category (the
category test also live-confirmed the Uncategorized-rename guard fires
correctly, then reverted the test rename immediately since it's a
self-heal-load-bearing name); doctor run clean against real data first,
then deliberately fed a real orphan (create author+page, delete the
author) and a real duplicate (two navlinks differing only by case) to
confirm both detections fire with the correct message and exit code, then
fully cleaned up -- live data confirmed byte-for-byte back to its
pre-test state (1 author, 2 categories, 0 navlinks, 0 pages) after every
test in this pass.
CHANGE (2026-09-13): PKG135 -- "give them all uuids" (Elton). Category,
AuthorProfile, MediaAsset, NavLink, SiteConfig, SocialLink all gained a
real UUID field (AuthorProfile already had author_uuid included from
pkg134's fix). Added the corresponding uuid field to every add_record()
call in this file that creates one of these entities (category add, nav
add, social add, asset add, config set, and _bootstrap_live_schema's
Category/SiteConfig seeding loop) -- none of them had it, so every row
these commands created was landing with its new uuid field set to None,
defeating the entire point. Update/delete commands (category delete,
category update, nav delete, social delete) deliberately left keyed by
the human-typed slug/label, not the new UUID -- these are typed by a
person at a terminal who doesn't have the UUID memorized, and the
existing slug/label matching was never the source of a collision bug the
way cmd_author_add's case-sensitivity was at pkg134 (category slugs are
already deduplicated at add-time; nav/social have no dedup but also no
existing report of a collision). Verified live: ran category/navlink/
social add+delete and config set+delete against real data end to end,
confirmed correct UUIDs generated and live data restored afterward.
CHANGE (2026-09-12): PKG134 -- cmd_author_add()'s duplicate check was an
exact-match comparison (author_display_name ==), while both web-side
author-creation paths (BEJSON_CMS_Content.py's manage_authors(),
BEJSON_CMS_ProfileManager.py's persona->author sync) already compare
case-insensitively. AuthorProfile has no UUID -- author_display_name IS
the key -- so a case-only variant added via the CLI (e.g. "JANE DOE" when
"Jane Doe" already exists from the web UI) silently created a second,
disconnected row with nothing to catch the collision. Made cmd_author_add()
case-insensitive to match. Verified live: re-adding a case-variant of the
existing author is now rejected, a genuinely new name still adds and
deletes cleanly, live data unchanged.
"""

VERSION = "18.12"


import os
import sys
import argparse
import json
import shutil
import hashlib
import mimetypes
import uuid
import re
import zipfile
from pathlib import Path
from datetime import datetime, timezone

# --- SCRIPT_PATH Resolution (Mandate Sec 7.1) ---
def get_script_path() -> Path:
    return Path(__file__).resolve().parent
SCRIPT_PATH = get_script_path()

# --- Library Bootstrapping (Mandate Sec 7.2) ---
LIB_DIR = SCRIPT_PATH / "lib"
if not LIB_DIR.exists():
    # Fallback to master if local is missing
    MASTER_LIB = Path("/storage/emulated/0/Admin/libraries")
    if MASTER_LIB.exists():
        os.makedirs(LIB_DIR, exist_ok=True)
        # In a real scenario, we'd copy, but for now we assume they exist or we fail gracefully
        pass

sys.path.append(str(LIB_DIR))

try:
    from lib_bejson_CMS_cms_mfdb import MFDB_CMS_Manager
    import lib_bejson_Core_bejson_core as BEJSONCore
    import lib_bejson_CMS_cms_core as CMSCore
    from lib_bejson_Core_bejson_path_guard import safe_extract_zip
except ImportError as e:
    print(f"FATAL: Missing dependencies. {e}")
    sys.path.append(str(SCRIPT_PATH.parent / "lib")) # Try parent lib
    from lib_bejson_CMS_cms_mfdb import MFDB_CMS_Manager
    import lib_bejson_CMS_cms_core as CMSCore
    from lib_bejson_Core_bejson_path_guard import safe_extract_zip

def get_manager():
    # Discover data root from env or default
    data_root = os.environ.get("CMS_DATA_ROOT", str(SCRIPT_PATH.parent / "storage"))
    return MFDB_CMS_Manager(data_root)

# --- Live-database access (added: see docs/security-notes.md / the CLI data-
# layer disconnect report) ---
# get_manager() above talks to a disconnected workspace/archive copy that
# has never been connected to the real site in this project. get_db() talks
# to the SAME manifest the 6 Flask apps actually read/write. Commands are
# being migrated from get_manager() to get_db() one at a time as each
# entity's real (not assumed) field shape is confirmed compatible -- see the
# report for which commands are converted vs. still on the old manager.
def get_live_manifest_path():
    data_root = os.environ.get("CMS_DATA_ROOT", str(SCRIPT_PATH.parent / "storage"))
    return os.path.join(data_root, "mfdb", "site_master", "104a.mfdb.bejson")

def get_db():
    return CMSCore.CMSCore(get_live_manifest_path())

def get_live_storage_root():
    return os.environ.get("CMS_DATA_ROOT", str(SCRIPT_PATH.parent / "storage"))

def get_pages_db_dir():
    return os.path.join(get_live_storage_root(), "mfdb", "pages_db")

def get_live_assets_dir():
    return os.path.join(get_live_storage_root(), "mfdb", "assets")

def get_live_apps_dir():
    return os.path.join(get_live_storage_root(), "mfdb", "standalone_apps")

DEFAULT_FEATURED_IMAGE = "default_page_image.webp"

def cmd_status(args):
    mgr = get_manager()
    print(f"CMS Data Root: {mgr.data_root}")
    print(f"Mounted: {Path(mgr.global_db_root).exists()}")
    live_manifest = get_live_manifest_path()
    print(f"Live site manifest: {live_manifest} (exists: {Path(live_manifest).exists()})")
    print("NOTE: 'Mounted' above refers to the disconnected workspace/archive")
    print("      copy -- a legacy layer with no remaining CLI commands that")
    print("      write to it (mount/commit/repack were removed at pkg139;")
    print("      this status line is read-only legacy diagnostic reporting,")
    print("      kept in case something outside this CLI still touches that")
    print("      archive). Every data command -- category/navlink/config/")
    print("      author/page/asset/app/ad/backup/restore -- reads/writes the")
    print("      real 'Live site manifest' path above via CMSCore. See")
    print("      docs/security-notes.md.")
    print(f"Dirty Changes: {mgr.is_dirty()}")

def cmd_doctor(args):
    """NEW (pkg136). One command bundling the two health checks the
    pkg135 "give them all uuids" pass made newly relevant:

    1. Orphaned FK check -- PageRecord.page_cat_name/page_author_name are
       still plain name strings (pkg135 deliberately did not convert these
       to reference the new cat_uuid/author_uuid), so nothing stops a page
       from pointing at a category or author name that no longer exists.
       This can happen today via any path that changes a category/author's
       name without going through the cascade-aware `rename` commands
       added alongside this one (e.g. hand-editing live data, or any
       future code path that doesn't know about the cascade).
    2. Case-insensitive duplicate-name check across every entity that
       still identifies itself to a human by name, now that AuthorProfile-
       specific case-insensitivity (pkg134) is the only entity actually
       guarded against this at add-time -- Category has a similar guard,
       but NavLink/SocialLink do not.

    Exits 0 clean, 1 if anything was found (so it's usable in a script/cron
    check, not just interactively).
    """
    db = get_db()
    issues_found = 0

    print("=== cms-manage.py doctor ===\n")

    # --- 1. Orphaned FK check ---
    print("-- Orphaned references --")
    categories = {c.get("cat_name") for c in db.get_records("Category")}
    authors = {a.get("author_display_name") for a in db.get_records("AuthorProfile")}
    pages = db.get_records("PageRecord")

    orphan_cats = [p for p in pages if p.get("page_cat_name") and p.get("page_cat_name") not in categories]
    orphan_authors = [p for p in pages if p.get("page_author_name") and p.get("page_author_name") not in authors]

    if not orphan_cats and not orphan_authors:
        print("  OK -- every page's category and author reference a live record.")
    else:
        for p in orphan_cats:
            print(f"  ORPHAN: page '{p.get('page_title')}' (UUID {p.get('page_uuid')}) "
                  f"references category '{p.get('page_cat_name')}', which no longer exists.")
            issues_found += 1
        for p in orphan_authors:
            print(f"  ORPHAN: page '{p.get('page_title')}' (UUID {p.get('page_uuid')}) "
                  f"references author '{p.get('page_author_name')}', which no longer exists.")
            issues_found += 1
        print(f"  Fix: 'page update <uuid> --category \"<live category name>\"' / --author, "
              f"or 'category rename' / 'author rename' if the name just moved.")

    # --- 2. Case-insensitive duplicate-name check ---
    print("\n-- Duplicate names (case-insensitive) --")
    dup_checks = [
        ("AuthorProfile", "author_display_name"),
        ("Category",      "cat_name"),
        ("NavLink",       "nav_display_label"),
        ("SocialLink",    "social_platform_name"),
        ("AI_Profile",    "persona_name"),
    ]
    any_dupes = False
    for entity, field in dup_checks:
        seen = {}
        for rec in db.get_records(entity):
            name = rec.get(field, "")
            if not name:
                continue
            seen.setdefault(name.lower(), []).append(name)
        dupes = {k: v for k, v in seen.items() if len(v) > 1}
        for lower_name, variants in dupes.items():
            any_dupes = True
            issues_found += 1
            print(f"  DUPLICATE in {entity}: {variants} all match case-insensitively.")
    if not any_dupes:
        print("  OK -- no case-insensitive name collisions in AuthorProfile, "
              "Category, NavLink, SocialLink, or AI_Profile.")

    print(f"\n=== {issues_found} issue{'s' if issues_found != 1 else ''} found ===")
    if issues_found:
        sys.exit(1)

def _write_page_content_file(page_uuid, title, html_body):
    """Matches the exact live shape written by BEJSON_CMS_Content.py::page_new()
    -- confirmed against a real live content file before writing this, not
    assumed. Two-part write contract: this file plus a PageRecord row are
    both required; the row alone renders a broken edit page."""
    pfile = os.path.join(get_pages_db_dir(), f"{page_uuid}.json")
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
    os.makedirs(os.path.dirname(pfile), exist_ok=True)
    tmp = pfile + ".tmp"
    with open(tmp, "w") as f:
        json.dump(doc, f, indent=2)
    os.replace(tmp, pfile)  # atomic write per Golden Rule/System Dev Policy conventions
    return pfile

def _resolve_page_fk_uuids(db, cat_name, author_name):
    """NEW (pkg137). Resolves a category/author NAME to its live UUID, for
    setting page_cat_uuid/page_author_uuid alongside the existing
    page_cat_name/page_author_name on every write -- same helper as
    BEJSON_CMS_Content.py's (this file doesn't share Python modules with
    the Flask blueprints, so it's duplicated rather than imported, matching
    this codebase's established file-independence convention)."""
    cat_uuid = next((c.get("cat_uuid") for c in db.get_records("Category") if c.get("cat_name") == cat_name), None)
    author_uuid = next((a.get("author_uuid") for a in db.get_records("AuthorProfile") if a.get("author_display_name") == author_name), None) if author_name else None
    return cat_uuid, author_uuid

def cmd_page_add(args):
    db = get_db()
    new_uuid = str(uuid.uuid4())
    slug = re.sub(r'[^a-z0-9]', '-', args.title.lower()).strip('-')
    html_body = args.body or f"<h2>{args.title}</h2><p>Start writing your content here...</p>"
    cat_uuid, author_uuid = _resolve_page_fk_uuids(db, args.category, args.author)
    if db.add_record("PageRecord", {
        "page_uuid": new_uuid, "page_title": args.title, "page_slug": slug,
        "page_cat_name": args.category, "page_type": args.type,
        "page_created_at": datetime.now().strftime("%Y-%m-%d"),
        "page_external_url": None, "page_author_name": args.author or "",
        "page_featured_img": DEFAULT_FEATURED_IMAGE,
        "page_template_key": "blank",
        "page_featured_video_url": args.featured_video or "",
        "page_cat_uuid": cat_uuid, "page_author_uuid": author_uuid,
    }):
        _write_page_content_file(new_uuid, args.title, html_body)
        print(f"Page created: {args.title} (UUID: {new_uuid})")
    else:
        print(f"Failed to create page: {args.title}")

def cmd_page_update(args):
    db = get_db()
    pages = db.get_records("PageRecord")
    page = next((p for p in pages if p.get("page_uuid") == args.uuid), None)
    if not page:
        print(f"Page not found: {args.uuid}")
        return
    updates = {"page_title": args.title}
    if args.category:
        updates["page_cat_name"] = args.category
        updates["page_cat_uuid"], _ = _resolve_page_fk_uuids(db, args.category, None)
    if args.author:
        updates["page_author_name"] = args.author
        _, updates["page_author_uuid"] = _resolve_page_fk_uuids(db, None, args.author)
    if args.featured_video is not None: updates["page_featured_video_url"] = args.featured_video
    db.update_record("PageRecord", "page_uuid", args.uuid, updates)
    if args.body is not None:
        pfile = os.path.join(get_pages_db_dir(), f"{args.uuid}.json")
        if os.path.exists(pfile):
            # Field Map Cache lookup, matching BEJSON_CMS_Content.py::edit_content()
            # exactly -- no positional indexing (System Development Policy Sec. BEJSON Usage).
            with open(pfile, "r") as f:
                data = json.load(f)
            field_map = BEJSONCore.bejson_core_get_field_map(data)
            p_idx = field_map.get("Record_Type_Parent", -1)
            h_idx = field_map.get("html_body", -1)
            m_idx = field_map.get("meta_title", -1)
            for row in data.get("Values", []):
                if p_idx == -1:
                    continue
                if row[p_idx] == "Content" and h_idx != -1:
                    row[h_idx] = args.body
                if row[p_idx] == "PageMeta" and m_idx != -1:
                    row[m_idx] = args.title
            tmp = pfile + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, pfile)
    print(f"Page updated: {args.uuid}")

def cmd_page_delete(args):
    db = get_db()
    deleted = db.delete_record("PageRecord", "page_uuid", args.uuid)
    if deleted:
        pfile = os.path.join(get_pages_db_dir(), f"{args.uuid}.json")
        if os.path.exists(pfile):
            os.remove(pfile)
        print(f"Page deleted: {args.uuid}")
    else:
        print(f"Page not found: {args.uuid}")

def cmd_page_import(args):
    if args.html:
        if not Path(args.html).exists():
            print(f"Error: file not found: {args.html}")
            return
        html_body = Path(args.html).read_text()
        title = args.title or Path(args.html).stem
        db = get_db()
        new_uuid = str(uuid.uuid4())
        slug = re.sub(r'[^a-z0-9]', '-', title.lower()).strip('-')
        cat_uuid, author_uuid = _resolve_page_fk_uuids(db, args.category, args.author)
        if db.add_record("PageRecord", {
            "page_uuid": new_uuid, "page_title": title, "page_slug": slug,
            "page_cat_name": args.category, "page_type": "page",
            "page_created_at": datetime.now().strftime("%Y-%m-%d"),
            "page_external_url": None, "page_author_name": args.author or "",
            "page_featured_img": DEFAULT_FEATURED_IMAGE,
            "page_template_key": "blank", "page_featured_video_url": None,
            "page_cat_uuid": cat_uuid, "page_author_uuid": author_uuid,
        }):
            _write_page_content_file(new_uuid, title, html_body)
            print(f"HTML imported as page: {title} (UUID: {new_uuid})")
        else:
            print(f"Failed to import HTML: {args.html}")
    elif args.app:
        # Looks up app by UUID, creates a PageRecord row + pages_db content
        # file that embeds the app via iframe. Live write shape confirmed
        # against BEJSON_CMS_Content.py::page_new() and app_new().
        # See docs/taxonomy_remediation_plan.md.
        db = get_db()
        apps = db.get_records("StandaloneApp")
        app = next((a for a in apps if a.get("app_uuid") == args.app), None)
        if not app:
            print(f"Error: StandaloneApp not found with UUID: {args.app}")
            print("Run 'db list apps' to see available app UUIDs.")
            return
        app_name = app.get("app_name", "")
        app_slug = app.get("app_slug", "")
        page_title = args.title or f"App: {app_name}"
        new_uuid = str(uuid.uuid4())
        page_slug = re.sub(r'[^a-z0-9]', '-', page_title.lower()).strip('-')
        # Iframe embed body -- matches the live renderer's expectation for item_type="app"
        html_body = (
            f"<div class='app-embed-container'>\n"
            f"  <iframe src='/apps/{app_slug}/' "
            f"style='width:100%;height:80vh;border:none;' "
            f"title='{app_name}' loading='lazy'></iframe>\n"
            f"</div>"
        )
        cat_uuid, author_uuid = _resolve_page_fk_uuids(db, args.category, args.author)
        if db.add_record("PageRecord", {
            "page_uuid": new_uuid, "page_title": page_title,
            "page_slug": page_slug,
            "page_cat_name": args.category,
            "page_type": "app",
            "page_created_at": datetime.now().strftime("%Y-%m-%d"),
            "page_external_url": f"/apps/{app_slug}/",
            "page_author_name": args.author or "",
            "page_featured_img": DEFAULT_FEATURED_IMAGE,
            "page_template_key": "blank", "page_featured_video_url": None,
            "page_cat_uuid": cat_uuid,
            "page_author_uuid": author_uuid,
        }):
            _write_page_content_file(new_uuid, page_title, html_body)
            print(f"App '{app_name}' imported as page: {page_title} (UUID: {new_uuid})")
            print(f"  Embed route: /apps/{app_slug}/")
        else:
            print(f"Failed to create page for app: {app_name}")
    else:
        print("Error: Specify --html or --app for import.")

def cmd_author_add(args):
    # Live AuthorProfile schema (author_uuid, author_display_name,
    # author_bio, author_avatar_url) -- author_uuid is the real key as of
    # pkg135 ("give them all uuids"). Duplicate check is case-INSENSITIVE to
    # match the two web-side creation paths (BEJSON_CMS_Content.py's
    # manage_authors(), BEJSON_CMS_ProfileManager.py's persona->author
    # sync) -- both already compare .lower()==.lower(). This was previously
    # an exact-match (==) comparison here only, so e.g.
    # 'cms-manage.py author add "JANE DOE"' would silently create a second,
    # disconnected AuthorProfile row even with a web-created "Jane Doe"
    # already live -- there's no UUID to catch the collision once the name
    # key itself diverges by case (found + fixed pkg134).
    db = get_db()
    existing = next((a for a in db.get_records("AuthorProfile") if a.get("author_display_name", "").lower() == args.name.lower()), None)
    if existing:
        print(f"Error: an author named '{existing.get('author_display_name')}' already exists (case-insensitive match).")
        return
    if db.add_record("AuthorProfile", {"author_uuid": str(uuid.uuid4()), "author_display_name": args.name, "author_bio": args.bio or "", "author_avatar_url": args.image or ""}):
        print(f"Author added: {args.name}")
    else:
        print(f"Failed to add author: {args.name}")

def _find_author_ci(db, name):
    """Case-insensitive author lookup by current display name. Returns the
    full record (with author_uuid) or None. Shared by update/delete/rename
    so all three resolve a typed name the same way (pkg136)."""
    return next((a for a in db.get_records("AuthorProfile") if a.get("author_display_name", "").lower() == name.lower()), None)

def cmd_author_update(args):
    # Resolves args.name case-insensitively then updates by author_uuid
    # (pkg136) -- previously matched author_display_name exactly, which
    # could silently no-op ("Author not found") on a case-only typo even
    # though the author clearly exists, the same softer version of the
    # pkg134 bug class.
    db = get_db()
    author = _find_author_ci(db, args.name)
    if not author:
        print(f"Author not found: {args.name}")
        return
    updates = {}
    if args.bio is not None: updates["author_bio"] = args.bio
    if args.image is not None: updates["author_avatar_url"] = args.image
    if db.update_record("AuthorProfile", "author_uuid", author["author_uuid"], updates):
        print(f"Author updated: {author['author_display_name']}")
    else:
        print(f"Author not found: {args.name}")

def cmd_author_delete(args):
    db = get_db()
    author = _find_author_ci(db, args.name)
    if not author:
        print(f"Author not found: {args.name}")
        return
    if db.delete_record("AuthorProfile", "author_uuid", author["author_uuid"]):
        print(f"Author deleted: {author['author_display_name']}")
    else:
        print(f"Author not found: {args.name}")

def cmd_author_rename(args):
    # NEW (pkg136). Renaming an author was never actually possible before
    # -- cmd_author_update has no field for changing the name itself, only
    # bio/image. Made possible now that author_uuid (pkg135) means the
    # record's identity survives the display name changing under it.
    #
    # Cascades to every PageRecord.page_author_name that references the
    # OLD name -- that FK is still a plain string (pkg135 deliberately did
    # not convert it to reference author_uuid), so a rename that only
    # touched AuthorProfile would silently orphan every page already
    # bylined under the old name: they'd stop matching their author and
    # nothing would error, they'd just quietly stop being associated with
    # anyone. This is exactly the gap `doctor` (below) checks for.
    db = get_db()
    author = _find_author_ci(db, args.old_name)
    if not author:
        print(f"Author not found: {args.old_name}")
        return
    old_name = author["author_display_name"]
    if old_name == args.new_name:
        print("New name is the same as the current name -- nothing to do.")
        return
    collision = next((a for a in db.get_records("AuthorProfile")
                       if a["author_uuid"] != author["author_uuid"] and a.get("author_display_name", "").lower() == args.new_name.lower()), None)
    if collision:
        print(f"Error: an author named '{collision.get('author_display_name')}' already exists (case-insensitive match). Pick a different name.")
        return
    if not db.update_record("AuthorProfile", "author_uuid", author["author_uuid"], {"author_display_name": args.new_name}):
        print(f"Failed to rename author: {old_name}")
        return
    cascaded = 0
    for p in db.get_records("PageRecord"):
        if p.get("page_author_name") == old_name:
            if db.update_record("PageRecord", "page_uuid", p["page_uuid"], {"page_author_name": args.new_name}):
                cascaded += 1
    print(f"Author renamed: '{old_name}' -> '{args.new_name}' ({cascaded} page{'s' if cascaded != 1 else ''} updated)")

def cmd_author_list(args):
    db = get_db()
    print(json.dumps(db.get_records("AuthorProfile"), indent=2))

def cmd_category_add(args):
    db = get_db()
    if args.desc or args.type:
        print("Note: --desc/--type are not supported by the live Category schema "
              "(cat_name, cat_slug only) -- ignored.")
    existing = next((c for c in db.get_records("Category") if c.get("cat_slug") == args.slug), None)
    if existing:
        print(f"Error: a category with slug '{args.slug}' already exists.")
        return
    if db.add_record("Category", {"cat_uuid": str(uuid.uuid4()), "cat_name": args.name, "cat_slug": args.slug}):
        print(f"Category added: {args.name} ({args.slug})")
    else:
        print(f"Failed to add category: {args.name}")

def _cascade_category_rename(db, cat, new_name):
    """Shared by update and rename (pkg136) -- both change cat_name, and
    both need the SAME cascade to PageRecord.page_cat_name, which was
    previously missing entirely from cmd_category_update: renaming a
    category via `category update <slug> <name>` changed Category.cat_name
    but left every PageRecord.page_cat_name still pointing at the OLD name
    -- those pages silently stopped matching their category (nothing
    errors; they just fall out of that category's listing) even though the
    category itself still existed. Real, pre-existing bug, caught while
    building the rename feature and fixed here rather than shipped
    knowingly broken in one of the two callers.

    Also blocks renaming AWAY FROM "Uncategorized" -- found live while
    testing this feature: BEJSON_CMS_System.py's self-heal
    (_ensure_uncategorized_category) checks for cat_name == "Uncategorized"
    on every boot and creates a fresh one if missing. Rename it to
    something else and the next boot silently creates a SECOND, empty
    category also going by "Uncategorized" alongside the renamed one (now
    holding all the old pages) -- and categories_delete()'s existing
    "can't delete Uncategorized" guard would then be protecting the wrong,
    empty one. Same category of protection that guard already gives
    delete; rename needed it too."""
    old_name = cat["cat_name"]
    if old_name == "Uncategorized":
        print("Error: cannot rename 'Uncategorized' -- the system self-heal "
              "recreates a category by that exact name on every boot if it's "
              "missing, so renaming it away would leave a stray duplicate "
              "next restart. Create a new category and reassign pages instead.")
        return 0, False
    if old_name == new_name:
        return 0, True
    collision = next((c for c in db.get_records("Category")
                       if c["cat_uuid"] != cat["cat_uuid"] and c.get("cat_name", "").lower() == new_name.lower()), None)
    if collision:
        print(f"Error: a category named '{collision.get('cat_name')}' already exists (case-insensitive match). Pick a different name.")
        return 0, False
    if not db.update_record("Category", "cat_uuid", cat["cat_uuid"], {"cat_name": new_name}):
        return 0, False
    cascaded = 0
    for p in db.get_records("PageRecord"):
        if p.get("page_cat_name") == old_name:
            if db.update_record("PageRecord", "page_uuid", p["page_uuid"], {"page_cat_name": new_name}):
                cascaded += 1
    return cascaded, True

def cmd_category_update(args):
    db = get_db()
    cat = next((c for c in db.get_records("Category") if c.get("cat_slug") == args.slug), None)
    if not cat:
        print(f"Category not found: {args.slug}")
        return
    cascaded, ok = _cascade_category_rename(db, cat, args.name)
    if ok:
        print(f"Category updated: {args.slug} -> {args.name} ({cascaded} page{'s' if cascaded != 1 else ''} updated)")
    else:
        print(f"Failed to update category: {args.slug}")

def cmd_category_rename(args):
    # NEW (pkg136), alias of `category update` with clearer intent -- same
    # underlying cascade-safe implementation (_cascade_category_rename),
    # not a second, divergent code path.
    cmd_category_update(argparse.Namespace(slug=args.slug, name=args.new_name))

def cmd_category_delete(args):
    db = get_db()
    if db.delete_record("Category", "cat_slug", args.slug):
        print(f"Category deleted: {args.slug}")
    else:
        print(f"Category not found: {args.slug}")

def cmd_category_merge(args):
    """NEW (pkg137). Reassigns every page from the source category to the
    target, then deletes the source. Source may not be "Uncategorized" --
    same reasoning as the rename guard (_cascade_category_rename): the
    self-heal in BEJSON_CMS_System.py recreates a category by that exact
    name on every boot if missing, so deleting it out from under a merge
    would just have it silently reappear (empty) next restart while pages
    live on in the target -- confusing, not actually destructive, but not
    what "merge" should do either. Target may be "Uncategorized" (merging
    INTO the fallback category is exactly what you'd want e.g. before
    deleting a category by hand)."""
    db = get_db()
    source = next((c for c in db.get_records("Category") if c.get("cat_slug") == args.source_slug), None)
    target = next((c for c in db.get_records("Category") if c.get("cat_slug") == args.into_slug), None)
    if not source:
        print(f"Category not found: {args.source_slug}")
        return
    if not target:
        print(f"Category not found: {args.into_slug}")
        return
    if source["cat_uuid"] == target["cat_uuid"]:
        print("Source and target are the same category -- nothing to do.")
        return
    if source["cat_name"] == "Uncategorized":
        print("Error: cannot merge 'Uncategorized' away -- the system self-heal "
              "recreates it on every boot if missing. Merge other categories "
              "INTO Uncategorized instead, or move pages individually.")
        return
    cascaded = 0
    for p in db.get_records("PageRecord"):
        if p.get("page_cat_name") == source["cat_name"]:
            # page_cat_uuid updated too (pkg137) -- merge, unlike rename,
            # actually changes which category a page belongs to, so the
            # moved page needs the TARGET's uuid, not the source's. Missed
            # on first pass (this command predates page_cat_uuid existing
            # at all within the same session) -- found before shipping,
            # not after.
            if db.update_record("PageRecord", "page_uuid", p["page_uuid"], {"page_cat_name": target["cat_name"], "page_cat_uuid": target["cat_uuid"]}):
                cascaded += 1
    db.delete_record("Category", "cat_uuid", source["cat_uuid"])
    print(f"Merged '{source['cat_name']}' into '{target['cat_name']}' "
          f"({cascaded} page{'s' if cascaded != 1 else ''} moved), source deleted.")

def cmd_category_list(args):
    db = get_db()
    print(json.dumps(db.get_records("Category"), indent=2))

def cmd_nav_add(args):
    db = get_db()
    if args.order:
        print("Note: --order is not supported by the live NavLink schema (nav_display_label, nav_target_url only) -- ignored.")
    if db.add_record("NavLink", {"nav_uuid": str(uuid.uuid4()), "nav_display_label": args.label, "nav_target_url": args.url}):
        print(f"Nav link added: {args.label}")
    else:
        print(f"Failed to add nav link: {args.label}")

def cmd_nav_delete(args):
    db = get_db()
    if db.delete_record("NavLink", "nav_display_label", args.label):
        print(f"Nav link deleted: {args.label}")
    else:
        print(f"Nav link not found: {args.label}")

def cmd_nav_list(args):
    db = get_db()
    print(json.dumps(db.get_records("NavLink"), indent=2))

def cmd_social_add(args):
    db = get_db()
    if db.add_record("SocialLink", {"social_uuid": str(uuid.uuid4()), "social_platform_name": args.platform, "social_target_url": args.url}):
        print(f"Social link added: {args.platform}")
    else:
        print(f"Failed to add social link: {args.platform}")

def cmd_social_delete(args):
    db = get_db()
    if db.delete_record("SocialLink", "social_platform_name", args.platform):
        print(f"Social link deleted: {args.platform}")
    else:
        print(f"Social link not found: {args.platform}")

def cmd_social_list(args):
    db = get_db()
    print(json.dumps(db.get_records("SocialLink"), indent=2))

def cmd_ad_add(args):
    db = get_db()
    ad_uid = str(uuid.uuid4())
    if db.add_record("AdUnit", {
        "ad_uuid": ad_uid, "ad_name": args.name, "ad_banner_url": args.img,
        "ad_target_url": args.link, "ad_zone": args.zone, "ad_active": not args.inactive
    }):
        print(f"Ad added: {args.name} (UUID: {ad_uid})")
    else:
        print(f"Failed to add ad: {args.name}")

def cmd_ad_update(args):
    db = get_db()
    if db.update_record("AdUnit", "ad_uuid", args.uuid, {
        "ad_name": args.name, "ad_banner_url": args.img, "ad_target_url": args.link,
        "ad_zone": args.zone, "ad_active": not args.inactive
    }):
        print(f"Ad updated: {args.uuid}")
    else:
        print(f"Ad not found: {args.uuid}")

def cmd_ad_delete(args):
    db = get_db()
    if db.delete_record("AdUnit", "ad_uuid", args.uuid):
        print(f"Ad deleted: {args.uuid}")
    else:
        print(f"Ad not found: {args.uuid}")

def cmd_ad_list(args):
    db = get_db()
    print(json.dumps(db.get_records("AdUnit"), indent=2))

def cmd_asset_add(args):
    src = Path(args.file)
    if not src.exists() or not src.is_file():
        print(f"Error: file not found: {src}")
        return

    assets_dir = Path(get_live_assets_dir())
    assets_dir.mkdir(parents=True, exist_ok=True)
    dest = assets_dir / src.name
    if dest.exists():
        print(f"Error: an asset named '{src.name}' already exists -- rename the source file or delete the existing asset first.")
        return

    db = get_db()
    file_hash = hashlib.sha256(src.read_bytes()).hexdigest()
    if any(a.get("asset_file_hash") == file_hash for a in db.get_records("MediaAsset")):
        print(f"Error: a file with identical content is already registered (dedup by hash) -- not adding '{src.name}'.")
        return

    shutil.copy2(src, dest)
    file_size = dest.stat().st_size
    mime_type = mimetypes.guess_type(str(dest))[0] or "application/octet-stream"

    if db.add_record("MediaAsset", {
        "asset_uuid": str(uuid.uuid4()),
        "asset_filename": dest.name, "asset_original_name": src.name, "asset_file_hash": file_hash,
        "asset_file_size": file_size, "asset_mime_type": mime_type,
        "asset_uploaded_at": datetime.now(timezone.utc).isoformat()
    }, sync_count=False):
        db.sync_manifest_count("MediaAsset")
        print(f"Asset added: {dest.name} ({file_size} bytes, {mime_type})")
    else:
        print(f"Failed to register asset: {src.name}")
        dest.unlink(missing_ok=True)

def cmd_asset_delete(args):
    db = get_db()
    if db.delete_record("MediaAsset", "asset_filename", args.asset_filename):
        assets_dir = Path(get_live_assets_dir())
        (assets_dir / args.asset_filename).unlink(missing_ok=True)
        print(f"Asset deleted: {args.asset_filename}")
    else:
        print(f"Asset not found: {args.asset_filename}")

def cmd_asset_add_external(args):
    db = get_db()
    muuid = str(uuid.uuid4())
    if db.add_record("ExternalMedia", {
        "extmedia_uuid": muuid, "extmedia_name": args.name, "extmedia_type": args.type,
        "extmedia_url": args.url, "extmedia_created_at": datetime.now(timezone.utc).isoformat()
    }):
        print(f"External media added: {muuid} ({args.type}) -> {args.url}")
    else:
        print(f"Failed to add external media: {args.name}")

def cmd_asset_delete_external(args):
    db = get_db()
    if db.delete_record("ExternalMedia", "extmedia_uuid", args.uuid):
        print(f"External media deleted: {args.uuid}")
    else:
        print(f"External media not found: {args.uuid}")

def cmd_asset_list_external(args):
    db = get_db()
    print(json.dumps(db.get_records("ExternalMedia"), indent=2))

def cmd_asset_optimize(args):
    """Reimplemented against live data (storage/mfdb/assets/ + CMSCore).
    Converts PNG assets to WebP, updates live MediaAsset rows, then patches
    any pages_db/<uuid>.json content files that reference the old filename.
    Verified to match the live write contract -- no positional indexing, all
    reads via Field Map Cache. See docs/remediation_checklist.md Issue 1.
    """
    try:
        from PIL import Image
    except ImportError:
        print("Error: Pillow library not found. Install with: pip install pillow")
        return

    dry_run = getattr(args, 'dry_run', False)
    assets_dir = Path(get_live_assets_dir())
    if not assets_dir.exists():
        print(f"Error: live assets directory not found: {assets_dir}")
        return

    db = get_db()
    assets = db.get_records("MediaAsset")
    pngs = [a for a in assets if a.get("asset_filename", "").lower().endswith(".png")]

    if not pngs:
        print("No PNG assets found in live MediaAsset registry.")
        return

    print(f"Found {len(pngs)} PNG asset(s) to optimize{' (dry run)' if dry_run else ''}.")
    updated_names = {}  # old_filename -> new_filename

    for asset in pngs:
        old_name = asset.get("asset_filename", "")
        new_name = old_name.rsplit(".", 1)[0] + ".webp"
        old_path = assets_dir / old_name
        new_path = assets_dir / new_name

        if not old_path.exists():
            print(f"  SKIP {old_name}: source file not found on disk")
            continue
        if new_path.exists():
            print(f"  SKIP {old_name}: {new_name} already exists")
            continue
        if dry_run:
            print(f"  DRY-RUN: would convert {old_name} -> {new_name}")
            updated_names[old_name] = new_name
            continue

        # Convert via Pillow
        try:
            img = Image.open(old_path)
            img.save(new_path, "webp")
            webp_size = new_path.stat().st_size
            if webp_size == 0:
                raise IOError(f"WebP conversion produced a 0-byte file: {new_name}")
        except Exception as e:
            print(f"  FAIL {old_name}: {e}")
            new_path.unlink(missing_ok=True)
            continue

        # Compute new hash
        new_hash = hashlib.sha256(new_path.read_bytes()).hexdigest()

        # Update live MediaAsset row (Field Map Cache, no positional indexing)
        updated = db.update_record("MediaAsset", "asset_filename", old_name, {
            "asset_filename": new_name,
            "asset_mime_type": "image/webp",
            "asset_file_size": webp_size,
            "asset_file_hash": new_hash
        })
        if not updated:
            print(f"  FAIL {old_name}: could not update MediaAsset row -- WebP file written but NOT registered. Remove {new_name} manually.")
            continue

        # Remove old PNG
        old_path.unlink(missing_ok=True)
        updated_names[old_name] = new_name
        print(f"  OK {old_name} -> {new_name} ({webp_size} bytes)")

    if not updated_names:
        print("No assets converted.")
        return

    # Patch references in all pages_db/<uuid>.json content files
    # Uses Field Map Cache lookups -- no positional indexing (BEJSON Core Mandate).
    pages_dir = Path(get_pages_db_dir())
    patched_pages = 0
    for pfile in pages_dir.glob("*.json"):
        try:
            with open(pfile, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            field_map = BEJSONCore.bejson_core_get_field_map(data)
            h_idx = field_map.get("html_body", -1)
            m_idx = field_map.get("markdown_body", -1)
            changed = False
            for row in data.get("Values", []):
                if h_idx != -1 and isinstance(row[h_idx], str):
                    for old, new in updated_names.items():
                        if old in row[h_idx]:
                            row[h_idx] = row[h_idx].replace(old, new)
                            changed = True
                if m_idx != -1 and isinstance(row[m_idx], str):
                    for old, new in updated_names.items():
                        if old in row[m_idx]:
                            row[m_idx] = row[m_idx].replace(old, new)
                            changed = True
            if changed and not dry_run:
                tmp = str(pfile) + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, indent=2)
                os.replace(tmp, str(pfile))
                patched_pages += 1
            elif changed and dry_run:
                print(f"  DRY-RUN: would patch references in {pfile.name}")
                patched_pages += 1
        except Exception as e:
            print(f"  WARNING: could not scan {pfile.name}: {e}")

    print(f"Done. Converted {len(updated_names)} asset(s). Updated references in {patched_pages} page content file(s).")

def cmd_app_add(args):
    # Live StandaloneApp schema has no 'category' field (confirmed against
    # app_new() in BEJSON_CMS_Content.py) -- dropped, matching category.md
    # convention used elsewhere in this remediation.
    if args.category:
        print("Note: --category is not supported by the live StandaloneApp schema -- ignored.")
    db = get_db()
    new_uuid = str(uuid.uuid4())
    slug = re.sub(r'[^a-z0-9]', '-', args.name.lower()).strip('-')
    entry_file = args.entry or "index.html"
    if args.entry:
        # Matches app_new(): a real entry file must live under
        # storage/mfdb/standalone_apps/<uuid>/ for the app to actually load.
        src = Path(args.entry)
        if not src.exists():
            print(f"Error: entry file not found: {src}")
            return
        app_dir = Path(get_live_apps_dir()) / new_uuid
        app_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, app_dir / src.name)
        entry_file = src.name
    if db.add_record("StandaloneApp", {
        "app_uuid": new_uuid, "app_name": args.name, "app_slug": slug,
        "app_description": args.desc or "", "app_entry_file": entry_file, "app_featured_img": args.image or "",
        "app_created_at": datetime.now().strftime("%Y-%m-%d")
    }):
        print(f"App created: {args.name} (UUID: {new_uuid})")
    else:
        print(f"Failed to create app: {args.name}")

def cmd_app_delete(args):
    db = get_db()
    if db.delete_record("StandaloneApp", "app_uuid", args.uuid):
        app_dir = Path(get_live_apps_dir()) / args.uuid
        if app_dir.exists():
            shutil.rmtree(app_dir, ignore_errors=True)
        print(f"App deleted: {args.uuid}")
    else:
        print(f"App not found: {args.uuid}")

def cmd_app_list(args):
    db = get_db()
    print(json.dumps(db.get_records("StandaloneApp"), indent=2))

# Bootstrap data that the live site requires to function.
# Matches BEJSON_CMS_System.py's ensure_uncategorized_exists() and the
# default SiteConfig keys expected by Publisher + Admin UI.
_BOOTSTRAP_CATEGORIES = [
    {"cat_name": "Uncategorized", "cat_slug": "uncategorized"}
]
_BOOTSTRAP_SITE_CONFIG = [
    {"sys_key": "title",       "sys_value": "My BEJSON Site"},
    {"sys_key": "description", "sys_value": "A BEJSON CMS powered site"},
    {"sys_key": "creator",     "sys_value": "Admin"},
    {"sys_key": "base_url",    "sys_value": "https://example.com"},
]

def _bootstrap_live_schema(db):
    """Seed the minimal records required for the live CMS to operate.
    Called after a factory reset wipes storage/mfdb/.
    Must match the self-heal logic in BEJSON_CMS_System.py (confirmed).
    """
    for cat in _BOOTSTRAP_CATEGORIES:
        db.add_record("Category", {**cat, "cat_uuid": str(uuid.uuid4())})
    for cfg in _BOOTSTRAP_SITE_CONFIG:
        db.add_record("SiteConfig", {**cfg, "sys_uuid": str(uuid.uuid4())})
    print("Schema bootstrapped: Uncategorized category + default SiteConfig written.")

def cmd_reset(args):
    """Live factory reset -- wipes storage/mfdb/ (site_master, pages_db,
    assets, standalone_apps), takes a mandatory safety backup first, and
    re-bootstraps the minimum schema the live CMS needs to run.
    Decision recorded: docs/remediation_checklist.md Issue 4.
    """
    storage_root  = get_live_storage_root()
    mfdb_root     = os.path.join(storage_root, "mfdb")
    live_manifest = get_live_manifest_path()

    if not os.path.exists(mfdb_root):
        print(f"Error: live data directory not found: {mfdb_root}")
        return

    print("=" * 60)
    print(" BEJSON CMS -- LIVE FACTORY RESET")
    print("=" * 60)
    print()
    print("This will PERMANENTLY delete all live site data:")
    for sub in _LIVE_BACKUP_DIRS:
        sub_path = os.path.join(mfdb_root, sub)
        if os.path.isdir(sub_path):
            print(f"  - {sub_path}")
    print()
    print("A mandatory safety backup will be taken first.")
    print()

    confirm1 = input("Type 'RESET' to confirm you want to wipe all live data: ").strip()
    if confirm1 != "RESET":
        print("Reset cancelled.")
        return

    confirm2 = input("Type 'YES I AM SURE' to proceed (this is irreversible without the backup): ").strip()
    if confirm2 != "YES I AM SURE":
        print("Reset cancelled.")
        return

    # Step 1: mandatory safety backup
    print()
    print("Step 1/3: Taking mandatory safety backup before wiping...")
    cmd_backup(argparse.Namespace(dir=os.path.join(storage_root, "exports")))

    # Step 2: wipe live data directories
    print()
    print("Step 2/3: Wiping live data...")
    for sub in _LIVE_BACKUP_DIRS:
        sub_path = os.path.join(mfdb_root, sub)
        if os.path.isdir(sub_path):
            shutil.rmtree(sub_path)
            print(f"  Deleted: {sub_path}")
    # Also wipe builds/ and tmp/html_imports for parity with the web reset
    # (BEJSON_CMS_System.py factory_reset_confirm()) -- NOT exports/, since
    # that's where the mandatory safety backup taken in Step 1 just landed;
    # wiping it here would destroy the very backup this reset just made.
    for extra in ("builds", os.path.join("tmp", "html_imports")):
        extra_path = os.path.join(storage_root, extra)
        if os.path.isdir(extra_path):
            shutil.rmtree(extra_path)
            print(f"  Deleted: {extra_path}")
    os.makedirs(os.path.join(storage_root, "tmp", "html_imports"), exist_ok=True)
    # Remove the site master manifest so CMSCore recreates it fresh
    site_master_dir = os.path.join(mfdb_root, "site_master")
    os.makedirs(site_master_dir, exist_ok=True)
    os.makedirs(os.path.join(mfdb_root, "pages_db"), exist_ok=True)
    os.makedirs(os.path.join(mfdb_root, "assets"), exist_ok=True)
    os.makedirs(os.path.join(mfdb_root, "standalone_apps"), exist_ok=True)

    # Step 3: bootstrap minimum schema
    print()
    print("Step 3/3: Re-bootstrapping live schema...")
    db = get_db()
    _bootstrap_live_schema(db)

    print()
    print("Factory reset complete. Live site is now empty with default schema.")
    print("Your pre-reset data is in the safety backup under:")
    print(f"  {os.path.join(storage_root, 'exports')}")

_LIVE_BACKUP_DIRS = ["site_master", "pages_db", "assets", "standalone_apps"]

def cmd_backup(args):
    # Real live-data backup: zips storage/mfdb/{site_master,pages_db,assets,
    # standalone_apps} -- the same directories the 5 Flask apps read/write.
    storage_root = get_live_storage_root()
    mfdb_root = os.path.join(storage_root, "mfdb")
    backup_dir = args.dir or os.path.join(storage_root, "exports")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(backup_dir, f"BEJSON_CMS_live_backup_{ts}.zip")
    print(f"Creating live-data backup: {out_path}")
    file_count = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for sub in _LIVE_BACKUP_DIRS:
            src_dir = os.path.join(mfdb_root, sub)
            if not os.path.isdir(src_dir):
                continue
            for root, _, files in os.walk(src_dir):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    arcname = os.path.join("mfdb", os.path.relpath(fpath, mfdb_root))
                    zf.write(fpath, arcname)
                    file_count += 1
    print(f"Backup created successfully: {out_path} ({file_count} files)")

def cmd_restore(args):
    if not Path(args.file).exists():
        print(f"Error: Backup file not found: {args.file}")
        return
    storage_root = get_live_storage_root()
    mfdb_root = os.path.join(storage_root, "mfdb")
    print("WARNING: this will overwrite live site data currently served by")
    print("all 5 Flask apps (storage/mfdb/site_master, pages_db, assets, standalone_apps).")
    if input(f"Restore from {args.file}? (y/N): ").lower() != 'y':
        print("Restore cancelled.")
        return

    # Automatic safety backup first -- never overwrite live data without
    # a way back out, per Golden Rule discretion on destructive operations.
    print("Taking an automatic safety backup of current live data first...")
    cmd_backup(argparse.Namespace(dir=os.path.join(storage_root, "exports")))

    with zipfile.ZipFile(args.file, "r") as zf:
        names = zf.namelist()
        if not any(n.startswith("mfdb/") for n in names):
            print("Error: this zip doesn't look like a live-data backup from "
                  "'cms-manage.py backup' (no mfdb/ prefix found) -- refusing to restore.")
            return
        try:
            safe_extract_zip(zf, storage_root)
        except ValueError as e:
            print(f"Error: restore rejected -- {e}")
            print("This zip contains a member that would extract outside the storage root.")
            return
    print("Restore complete.")

def cmd_config_set(args):
    db = get_db()
    if args.desc:
        print("Note: --desc is not supported by the live SiteConfig schema (sys_key, sys_value only) -- ignored.")
    existing = next((c for c in db.get_records("SiteConfig") if c.get("sys_key") == args.key), None)
    if existing:
        db.update_record("SiteConfig", "sys_key", args.key, {"sys_value": args.value})
    else:
        db.add_record("SiteConfig", {"sys_uuid": str(uuid.uuid4()), "sys_key": args.key, "sys_value": args.value})
    print(f"Config set: {args.key} = {args.value}")

def cmd_config_list(args):
    db = get_db()
    recs = db.get_records("SiteConfig")
    print(json.dumps({r["sys_key"]: r["sys_value"] for r in recs}, indent=2))

def cmd_config_delete(args):
    db = get_db()
    if db.delete_record("SiteConfig", "sys_key", args.key):
        print(f"Config deleted: {args.key}")
    else:
        print(f"Config key not found: {args.key}")

def cmd_serve(args):
    scripts = {
        "cms": "BEJSON_CMS_Admin.py",
        "editor": "BEJSON_CMS_PageEditor.py",
        "editorv2": "BEJSON_CMS_PageEditorV2.py",
        "profiles": "BEJSON_CMS_ProfileManager.py",
        "publisher": "BEJSON_CMS_Publisher.py"
    }
    script_name = scripts.get(args.service)
    script_path = SCRIPT_PATH / "web" / script_name
    if not script_path.exists():
        print(f"Error: Script not found at {script_path}")
        return

    print(f"Starting {args.service} service...")
    import subprocess
    try:
        subprocess.run([sys.executable, str(script_path)])
    except KeyboardInterrupt:
        print("\nService stopped.")

_DB_ENTITY_MAP = {
    "authors": ("AuthorProfile", None),
    "pages": ("PageRecord", "page_cat_name"),
    "categories": ("Category", None),
    "assets": ("MediaAsset", None),
    "apps": ("StandaloneApp", None),
    "ads": ("AdUnit", None),
    "navlinks": ("NavLink", None),
}

# NEW (pkg137). Single source of truth for `find`/`export`/`import` --
# (BEJSON entity name, uuid field, [human-readable fields to search/export
# as the "name" column]). Deliberately a separate registry from
# _DB_ENTITY_MAP above rather than merged into it: that one is keyed by the
# plural/legacy names `db list` already shipped with (mixed with a filter
# field, not a uuid field), and changing its shape would be a needless
# behavior change to a command that already works. Covers every entity
# that has a uuid field as of pkg135 ("give them all uuids") plus the ones
# that already had one before that (PageRecord, StandaloneApp, AdUnit,
# ExternalMedia).
_ENTITY_REGISTRY = {
    "author":   ("AuthorProfile",   "author_uuid",   ["author_display_name"]),
    "category": ("Category",        "cat_uuid",      ["cat_name", "cat_slug"]),
    "page":     ("PageRecord",      "page_uuid",     ["page_title", "page_slug"]),
    "asset":    ("MediaAsset",      "asset_uuid",    ["asset_original_name", "asset_filename"]),
    "app":      ("StandaloneApp",   "app_uuid",      ["app_name", "app_slug"]),
    "ad":       ("AdUnit",          "ad_uuid",       ["ad_name"]),
    "navlink":  ("NavLink",         "nav_uuid",      ["nav_display_label"]),
    "social":   ("SocialLink",      "social_uuid",   ["social_platform_name"]),
    "persona":  ("AI_Profile",      "persona_uuid",  ["persona_name"]),
    "extmedia": ("ExternalMedia",   "extmedia_uuid", ["extmedia_name"]),
}

def cmd_find(args):
    """NEW (pkg137). Fuzzy name->UUID lookup. Now that UUID is the real
    identity for every entity in _ENTITY_REGISTRY, the practical gap is
    going the other way: a human remembers a name, not a UUID. Substring,
    case-insensitive match across every registered "name" field for the
    given entity type."""
    entry = _ENTITY_REGISTRY.get(args.entity)
    if not entry:
        print(f"Unknown entity type '{args.entity}'. Known types: {', '.join(sorted(_ENTITY_REGISTRY))}")
        return
    entity_name, uuid_field, name_fields = entry
    db = get_db()
    query = args.query.lower()
    matches = []
    for rec in db.get_records(entity_name):
        if any(query in str(rec.get(f, "")).lower() for f in name_fields):
            matches.append(rec)
    if not matches:
        print(f"No {args.entity} records matching '{args.query}'.")
        return
    for rec in matches:
        label = " / ".join(str(rec.get(f, "")) for f in name_fields if rec.get(f))
        print(f"{rec.get(uuid_field)}  {label}")
    if len(matches) > 1:
        print(f"\n{len(matches)} matches.")

def cmd_export(args):
    """NEW (pkg137). Dump one entity's live records to a file --
    JSON (full fidelity) or CSV (for spreadsheet editing). Pairs with
    cmd_import below for a round trip."""
    entry = _ENTITY_REGISTRY.get(args.entity)
    if not entry:
        print(f"Unknown entity type '{args.entity}'. Known types: {', '.join(sorted(_ENTITY_REGISTRY))}")
        return
    entity_name, uuid_field, name_fields = entry
    db = get_db()
    recs = db.get_records(entity_name)
    out_path = args.out or f"{args.entity}_export.{args.format}"
    if args.format == "json":
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(recs, f, indent=2)
    else:  # csv
        import csv as _csv
        fieldnames = list(recs[0].keys()) if recs else [uuid_field] + name_fields
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            writer = _csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in recs:
                writer.writerow(r)
    print(f"Exported {len(recs)} {args.entity} record(s) to {out_path}")

def cmd_import(args):
    """NEW (pkg137). Bulk-add records from a JSON or CSV file exported by
    cmd_export (or hand-written in the same shape). Every imported row
    gets a FRESH uuid generated here -- imported data is never trusted to
    supply its own uuid_field value, even if the file has one (e.g.
    re-importing a previous export), to guarantee no collision with a live
    record's identity is possible. Skips (does not overwrite) a row whose
    first name field case-insensitively matches an existing live record,
    printing what it skipped, so a partially-duplicate import file doesn't
    silently create duplicates as a side effect of the very feature meant
    to reduce name-based duplication risk."""
    entry = _ENTITY_REGISTRY.get(args.entity)
    if not entry:
        print(f"Unknown entity type '{args.entity}'. Known types: {', '.join(sorted(_ENTITY_REGISTRY))}")
        return
    entity_name, uuid_field, name_fields = entry
    db = get_db()
    fmt = args.format or ("csv" if args.file.lower().endswith(".csv") else "json")
    if fmt == "json":
        with open(args.file, "r", encoding="utf-8") as f:
            rows = json.load(f)
    else:
        import csv as _csv
        with open(args.file, "r", encoding="utf-8", newline="") as f:
            rows = list(_csv.DictReader(f))

    primary_name_field = name_fields[0]
    existing_names = {r.get(primary_name_field, "").lower() for r in db.get_records(entity_name) if r.get(primary_name_field)}

    added, skipped = 0, 0
    for row in rows:
        row = dict(row)
        row.pop(uuid_field, None)  # never trust an imported uuid -- always fresh
        row[uuid_field] = str(uuid.uuid4())
        name_val = row.get(primary_name_field, "")
        if name_val and name_val.lower() in existing_names:
            print(f"  Skipped (already exists): {name_val}")
            skipped += 1
            continue
        if db.add_record(entity_name, row):
            added += 1
            if name_val:
                existing_names.add(name_val.lower())
        else:
            print(f"  Failed to add: {name_val or row}")
    print(f"Imported {added} {args.entity} record(s), skipped {skipped} duplicate(s).")

def cmd_db_list(args):
    entry = _DB_ENTITY_MAP.get(args.entity)
    if not entry:
        print("Unknown entity type.")
        return
    entity_name, filter_field = entry
    db = get_db()
    recs = db.get_records(entity_name)
    if args.filter and filter_field:
        recs = [r for r in recs if r.get(filter_field) == args.filter]
    elif args.filter and not filter_field:
        print(f"Note: --filter is not supported for '{args.entity}' -- ignored.")
    print(json.dumps(recs, indent=2))

def main():
    parser = argparse.ArgumentParser(description=f"BEJSON_CMS CLI Toolkit v{VERSION}")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    
    subparsers = parser.add_subparsers(dest="command", help="Management commands")

    # Status
    subparsers.add_parser("status", help="Show system status")

    # Reset
    subparsers.add_parser("factory-reset", help="FACTORY RESET the CMS system")

    # Backup/Restore
    p_backup = subparsers.add_parser("backup", help="Create a site backup")
    p_backup.add_argument("--dir", help="Target backup directory")
    
    p_restore = subparsers.add_parser("restore", help="Restore site from backup")
    p_restore.add_argument("file", help="Path to backup zip file")

    # mount/commit removed at pkg139 (Elton's call, following the pkg132
    # audit's "pending Elton's call" note in docs/security-notes.md):
    # deprecated escape hatches into the old disconnected workspace/archive
    # model, superseded entirely by backup/restore (which operate on real
    # live data) for years before this. get_manager()/MFDB_CMS_Manager
    # itself is NOT removed -- cmd_status() still reports on that legacy
    # workspace read-only, in case something outside this CLI still touches
    # the archive directly.
    subparsers.add_parser("doctor", help="Health check: orphaned category/author refs + duplicate names")

    p_find = subparsers.add_parser("find", help="Fuzzy name->UUID lookup across any entity type")
    p_find.add_argument("entity", choices=sorted(_ENTITY_REGISTRY.keys()), help="Entity type to search")
    p_find.add_argument("query", help="Case-insensitive substring to match against the entity's name field(s)")

    p_export = subparsers.add_parser("export", help="Export one entity's live records to a file")
    p_export.add_argument("entity", choices=sorted(_ENTITY_REGISTRY.keys()), help="Entity type to export")
    p_export.add_argument("--format", choices=["json", "csv"], default="json", help="Output format (default json)")
    p_export.add_argument("--out", help="Output file path (default: <entity>_export.<format>)")

    p_import = subparsers.add_parser("import", help="Bulk-import records for one entity from a file")
    p_import.add_argument("entity", choices=sorted(_ENTITY_REGISTRY.keys()), help="Entity type to import")
    p_import.add_argument("file", help="Path to a JSON or CSV file (as produced by 'export')")
    p_import.add_argument("--format", choices=["json", "csv"], help="Input format (default: inferred from file extension)")

    # Page Management
    p_page = subparsers.add_parser("page", help="Page operations")
    page_sub = p_page.add_subparsers(dest="op")
    
    p_padd = page_sub.add_parser("add", help="Add a new page")
    p_padd.add_argument("title", help="Page title")
    p_padd.add_argument("--category", default="Uncategorized", help="Category NAME (not slug) -- must match a live Category's cat_name exactly, e.g. 'Uncategorized' or 'BEJSON'. Run 'category list' to see valid names.")
    p_padd.add_argument("--type", default="page", help="Page type")
    p_padd.add_argument("--body", help="HTML body content")
    p_padd.add_argument("--author", help="Author NAME (not UUID) -- must match a live AuthorProfile's author_display_name exactly. Run 'author list' to see valid names.")
    p_padd.add_argument("--featured-video", help="Featured YouTube video -- a full watch URL or bare 11-character video ID. Rendered above the article body on publish.")

    p_pupd = page_sub.add_parser("update", help="Update a page")
    p_pupd.add_argument("uuid", help="Page UUID")
    p_pupd.add_argument("title", help="Page title")
    p_pupd.add_argument("--category", help="Category NAME (not slug) -- must match a live Category's cat_name exactly. Run 'category list' to see valid names.")
    p_pupd.add_argument("--type", help="Page type")
    p_pupd.add_argument("--body", help="HTML body content")
    p_pupd.add_argument("--author", help="Author NAME (not UUID) -- must match a live AuthorProfile's author_display_name exactly. Run 'author list' to see valid names.")
    p_pupd.add_argument("--featured-video", help="Featured YouTube video -- a full watch URL or bare 11-character video ID. Pass an empty string to clear it.")

    p_pdel = page_sub.add_parser("delete", help="Delete a page")
    p_pdel.add_argument("uuid", help="Page UUID")

    p_pimp = page_sub.add_parser("import", help="Import a page from HTML or App")
    p_pimp.add_argument("--html", help="HTML file path")
    p_pimp.add_argument("--app", help="App UUID")
    p_pimp.add_argument("--title", help="Page title (for HTML import)")
    p_pimp.add_argument("--category", default="Uncategorized", help="Category NAME (not slug) -- must match a live Category's cat_name exactly, e.g. 'Uncategorized' or 'BEJSON'. Run 'category list' to see valid names.")
    p_pimp.add_argument("--author", help="Author NAME (not UUID) -- must match a live AuthorProfile's author_display_name exactly. Run 'author list' to see valid names.")

    page_sub.add_parser("list", help="List pages")

    # Author Management
    p_author = subparsers.add_parser("author", help="Author operations")
    author_sub = p_author.add_subparsers(dest="op")
    
    p_aadd = author_sub.add_parser("add", help="Add an author")
    p_aadd.add_argument("name", help="Author name")
    p_aadd.add_argument("--bio", help="Author bio")
    p_aadd.add_argument("--image", help="Author image URL")

    p_aupd = author_sub.add_parser("update", help="Update an author's bio/image")
    p_aupd.add_argument("name", help="Author name (case-insensitive match; identity is author_uuid internally, pkg135)")
    p_aupd.add_argument("--bio", help="Author bio")
    p_aupd.add_argument("--image", help="Author image URL")

    p_aren = author_sub.add_parser("rename", help="Rename an author, cascading to every page's byline")
    p_aren.add_argument("old_name", help="Current author name (case-insensitive match)")
    p_aren.add_argument("new_name", help="New author name")

    p_adel = author_sub.add_parser("delete", help="Delete an author")
    p_adel.add_argument("name", help="Author name (case-insensitive match; identity is author_uuid internally, pkg135)")
    
    author_sub.add_parser("list", help="List authors")

    # Category Management
    p_cat = subparsers.add_parser("category", help="Category operations")
    cat_sub = p_cat.add_subparsers(dest="op")
    
    p_cadd = cat_sub.add_parser("add", help="Add a category")
    p_cadd.add_argument("name", help="Category name")
    p_cadd.add_argument("slug", help="Category slug")
    p_cadd.add_argument("--desc", help="Category description")
    p_cadd.add_argument("--type", help="Feed type (blog, portfolio, etc)")

    p_cupd = cat_sub.add_parser("update", help="Update a category's name (cascades to every page's category)")
    p_cupd.add_argument("slug", help="Category slug")
    p_cupd.add_argument("name", help="New category name")

    p_cren = cat_sub.add_parser("rename", help="Rename a category, cascading to every page's category")
    p_cren.add_argument("slug", help="Category slug (unchanged by rename -- only the display name changes)")
    p_cren.add_argument("new_name", help="New category name")

    p_cdel = cat_sub.add_parser("delete", help="Delete a category")
    p_cdel.add_argument("slug", help="Category slug")

    p_cmerge = cat_sub.add_parser("merge", help="Merge a category into another, moving all its pages")
    p_cmerge.add_argument("source_slug", help="Category to merge away (deleted after merge)")
    p_cmerge.add_argument("into_slug", help="Category to merge into (kept)")

    cat_sub.add_parser("list", help="List categories")

    # NavLink Management
    p_nav = subparsers.add_parser("navlink", help="Navigation link operations")
    nav_sub = p_nav.add_subparsers(dest="op")
    
    p_nadd = nav_sub.add_parser("add", help="Add a nav link")
    p_nadd.add_argument("label", help="Link label")
    p_nadd.add_argument("url", help="Link URL")
    p_nadd.add_argument("--order", type=int, default=0, help="Display order")
    
    p_ndel = nav_sub.add_parser("delete", help="Delete a nav link")
    p_ndel.add_argument("label", help="Link label")
    
    nav_sub.add_parser("list", help="List nav links")

    p_social = subparsers.add_parser("social", help="Social link operations")
    social_sub = p_social.add_subparsers(dest="op")

    p_soadd = social_sub.add_parser("add", help="Add a social link")
    p_soadd.add_argument("platform", help="Platform name (e.g. Twitter, GitHub)")
    p_soadd.add_argument("url", help="Profile URL")

    p_sodel = social_sub.add_parser("delete", help="Delete a social link")
    p_sodel.add_argument("platform", help="Platform name")

    social_sub.add_parser("list", help="List social links")

    # Ad Management
    p_ad = subparsers.add_parser("ad", help="Advertisement operations")
    ad_sub = p_ad.add_subparsers(dest="op")
    
    p_adadd = ad_sub.add_parser("add", help="Add an ad unit")
    p_adadd.add_argument("name", help="Ad name")
    p_adadd.add_argument("img", help="Image URL")
    p_adadd.add_argument("link", help="Click URL")
    p_adadd.add_argument("zone", help="Ad zone")
    p_adadd.add_argument("--inactive", action="store_true", help="Set as inactive")

    p_adupd = ad_sub.add_parser("update", help="Update an ad unit")
    p_adupd.add_argument("uuid", help="Ad UUID")
    p_adupd.add_argument("name", help="Ad name")
    p_adupd.add_argument("img", help="Image URL")
    p_adupd.add_argument("link", help="Click URL")
    p_adupd.add_argument("zone", help="Ad zone")
    p_adupd.add_argument("--inactive", action="store_true", help="Set as inactive")

    p_addel = ad_sub.add_parser("delete", help="Delete an ad unit")
    p_addel.add_argument("uuid", help="Ad UUID")
    
    ad_sub.add_parser("list", help="List ad units")

    # Asset Management
    p_asset = subparsers.add_parser("asset", help="Media asset operations")
    asset_sub = p_asset.add_subparsers(dest="op")
    
    p_asadd = asset_sub.add_parser("add", help="Add a media asset")
    p_asadd.add_argument("file", help="Path to file")
    
    p_asdel = asset_sub.add_parser("delete", help="Delete a media asset")
    p_asdel.add_argument("asset_filename", help="Asset filename")
    
    p_asopt = asset_sub.add_parser("optimize", help="Optimize assets: convert PNG to WebP (updates live data)")
    p_asopt.add_argument("--dry-run", dest="dry_run", action="store_true", help="Show what would be converted without changing anything")
    
    asset_sub.add_parser("list", help="List assets")

    # ExternalMedia (PDF-embed / linked-media feature, added BEJSON_CMS_Media.py
    # pkg74) -- previously had no CLI coverage at all.
    p_asaddext = asset_sub.add_parser("add-external", help="Register an externally-hosted media item (e.g. a PDF URL)")
    p_asaddext.add_argument("name", help="Display name")
    p_asaddext.add_argument("url", help="Full URL to the external media")
    p_asaddext.add_argument("--type", default="pdf", help="Media type (default: pdf)")

    p_asdelext = asset_sub.add_parser("delete-external", help="Delete an external media record")
    p_asdelext.add_argument("uuid", help="media_uuid to delete")

    asset_sub.add_parser("list-external", help="List external media (e.g. embedded PDFs)")

    # App Management
    p_app = subparsers.add_parser("app", help="Standalone app operations")
    app_sub = p_app.add_subparsers(dest="op")
    
    p_apadd = app_sub.add_parser("add", help="Create a standalone app")
    p_apadd.add_argument("name", help="App name")
    p_apadd.add_argument("--desc", help="Description")
    p_apadd.add_argument("--category", help="Not supported by the live StandaloneApp schema -- accepted for backward compatibility but ignored (a warning is printed).")
    p_apadd.add_argument("--image", help="Featured image URL")
    p_apadd.add_argument("--entry", help="Entry file path")

    p_apdel = app_sub.add_parser("delete", help="Delete a standalone app")
    p_apdel.add_argument("uuid", help="App UUID")
    
    app_sub.add_parser("list", help="List apps")

    # Config Management
    p_config = subparsers.add_parser("config", help="Configuration operations")
    config_sub = p_config.add_subparsers(dest="op")
    
    p_cset = config_sub.add_parser("set", help="Set a config value")
    p_cset.add_argument("key", help="Config key")
    p_cset.add_argument("value", help="Config value")
    p_cset.add_argument("--desc", help="Config description")
    
    config_sub.add_parser("list", help="List configs")

    p_cdel = config_sub.add_parser("delete", help="Delete a config value")
    p_cdel.add_argument("key", help="Config key")

    # Service Management
    p_serve = subparsers.add_parser("serve", help="Start a single CMS service in the foreground (blocks until Ctrl+C -- for multiple services at once or persistent background operation, use advanced_launcher.py instead)")
    p_serve.add_argument("service", choices=["cms", "editor", "editorv2", "profiles", "publisher"], default="cms", help="Service to start")

    # DB Operations
    p_db = subparsers.add_parser("db", help="Database operations")
    db_sub = p_db.add_subparsers(dest="op")
    
    p_list = db_sub.add_parser("list", help="List records")
    p_list.add_argument("entity", choices=["authors", "pages", "categories", "assets", "apps", "ads", "navlinks"], help="Entity type")
    p_list.add_argument("--filter", help="Filter value (only supported for 'pages', matched against page_cat_name -- a category NAME like 'Uncategorized', not a slug)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    commands = {
        "status": cmd_status,
        "factory-reset": cmd_reset,
        "backup": cmd_backup,
        "restore": cmd_restore,
        "doctor": cmd_doctor,
        "find": cmd_find,
        "export": cmd_export,
        "import": cmd_import,
        "page": lambda a: {"add": cmd_page_add, "update": cmd_page_update, "delete": cmd_page_delete, "import": cmd_page_import, "list": lambda _: cmd_db_list(argparse.Namespace(entity="pages", filter=None))}.get(a.op)(a) if a.op else None,
        "author": lambda a: {"add": cmd_author_add, "update": cmd_author_update, "rename": cmd_author_rename, "delete": cmd_author_delete, "list": cmd_author_list}.get(a.op)(a) if a.op else None,
        "category": lambda a: {"add": cmd_category_add, "update": cmd_category_update, "rename": cmd_category_rename, "merge": cmd_category_merge, "delete": cmd_category_delete, "list": cmd_category_list}.get(a.op)(a) if a.op else None,
        "navlink": lambda a: {"add": cmd_nav_add, "delete": cmd_nav_delete, "list": cmd_nav_list}.get(a.op)(a) if a.op else None,
        "social": lambda a: {"add": cmd_social_add, "delete": cmd_social_delete, "list": cmd_social_list}.get(a.op)(a) if a.op else None,
        "ad": lambda a: {"add": cmd_ad_add, "update": cmd_ad_update, "delete": cmd_ad_delete, "list": cmd_ad_list}.get(a.op)(a) if a.op else None,
        "asset": lambda a: {"add": cmd_asset_add, "delete": cmd_asset_delete, "optimize": cmd_asset_optimize, "list": lambda _: cmd_db_list(argparse.Namespace(entity="assets", filter=None)), "add-external": cmd_asset_add_external, "delete-external": cmd_asset_delete_external, "list-external": cmd_asset_list_external}.get(a.op)(a) if a.op else None,
        "app": lambda a: {"add": cmd_app_add, "delete": cmd_app_delete, "list": cmd_app_list}.get(a.op)(a) if a.op else None,
        "config": lambda a: {"set": cmd_config_set, "list": cmd_config_list, "delete": cmd_config_delete}.get(a.op)(a) if a.op else None,
        "serve": cmd_serve,
        "db": lambda a: cmd_db_list(a) if a.op == "list" else None
    }

    func = commands.get(args.command)
    if func:
        try:
            func(args)
        except Exception as e:
            print(f"Error executing command '{args.command}': {e}")
    else:
        print("Invalid command.")

if __name__ == "__main__":
    main()
