#!/usr/bin/env python3
"""
Script:        cms-manage.py
Description:   Unified CLI Toolkit for BEJSON_CMS management.
Version:       18.7
Author:        Elton Boehnen
Date:          2026-08-21
Relational_ID: 4e8b1a7c-3f2d-4c9e-b0a5-7d6e3f1c9b2c
"""

VERSION = "18.7"


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
    print("      copy -- only 'mount'/'commit' still use it (deprecated legacy")
    print("      escape hatches, --force required). Every data command --")
    print("      category/navlink/config/author/page/asset/app/ad/backup/restore")
    print("      -- reads/writes the real 'Live site manifest' path above via")
    print("      CMSCore. See docs/security-notes.md.")
    print(f"Dirty Changes: {mgr.is_dirty()}")

def cmd_mount(args):
    print("'mount' operates on the old disconnected workspace/archive copy --")
    print("it does NOT touch live site data. Use 'backup'/'restore' for real")
    print("live-data snapshots instead. See docs/security-notes.md.")
    if not args.force:
        print("Pass --force to run the old disconnected mount anyway.")
        return
    mgr = get_manager()
    print(f"Mounting disconnected workspace at {mgr.data_root}...")
    mgr.mount_system(force=args.force)
    print("Mount complete (disconnected workspace only -- live site unchanged).")

def cmd_commit(args):
    print("'commit'/'repack' operates on the old disconnected workspace/archive")
    print("copy -- it does NOT touch live site data. Deprecated; no-op.")
    print("Use 'backup' for a real live-data snapshot instead.")

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

def cmd_page_add(args):
    db = get_db()
    new_uuid = str(uuid.uuid4())
    slug = re.sub(r'[^a-z0-9]', '-', args.title.lower()).strip('-')
    html_body = args.body or f"<h2>{args.title}</h2><p>Start writing your content here...</p>"
    if db.add_record("PageRecord", {
        "page_uuid": new_uuid, "page_title": args.title, "page_slug": slug,
        "page_cat_name": args.category, "page_type": args.type,
        "page_created_at": datetime.now().strftime("%Y-%m-%d"),
        "page_external_url": None, "page_author_name": args.author or "",
        "page_featured_img": DEFAULT_FEATURED_IMAGE,
        "page_template_key": "blank",
        "page_featured_video_url": args.featured_video or ""
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
    if args.category: updates["page_cat_name"] = args.category
    if args.author: updates["page_author_name"] = args.author
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
        if db.add_record("PageRecord", {
            "page_uuid": new_uuid, "page_title": title, "page_slug": slug,
            "page_cat_name": args.category, "page_type": "page",
            "page_created_at": datetime.now().strftime("%Y-%m-%d"),
            "page_external_url": None, "page_author_name": args.author or "",
            "page_featured_img": DEFAULT_FEATURED_IMAGE,
            "page_template_key": "blank", "page_featured_video_url": None
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
        if db.add_record("PageRecord", {
            "page_uuid": new_uuid, "page_title": page_title,
            "page_slug": page_slug,
            "page_cat_name": args.category,
            "page_type": "app",
            "page_created_at": datetime.now().strftime("%Y-%m-%d"),
            "page_external_url": f"/apps/{app_slug}/",
            "page_author_name": args.author or "",
            "page_featured_img": DEFAULT_FEATURED_IMAGE,
            "page_template_key": "blank", "page_featured_video_url": None
        }):
            _write_page_content_file(new_uuid, page_title, html_body)
            print(f"App '{app_name}' imported as page: {page_title} (UUID: {new_uuid})")
            print(f"  Embed route: /apps/{app_slug}/")
        else:
            print(f"Failed to create page for app: {app_name}")
    else:
        print("Error: Specify --html or --app for import.")

def cmd_author_add(args):
    # Live AuthorProfile schema (author_display_name, author_bio,
    # author_avatar_url) has no UUID field -- the name IS the key, matching BEJSON_CMS_ProfileManager.py.
    db = get_db()
    existing = next((a for a in db.get_records("AuthorProfile") if a.get("author_display_name") == args.name), None)
    if existing:
        print(f"Error: an author named '{args.name}' already exists.")
        return
    if db.add_record("AuthorProfile", {"author_display_name": args.name, "author_bio": args.bio or "", "author_avatar_url": args.image or ""}):
        print(f"Author added: {args.name}")
    else:
        print(f"Failed to add author: {args.name}")

def cmd_author_update(args):
    db = get_db()
    updates = {}
    if args.bio is not None: updates["author_bio"] = args.bio
    if args.image is not None: updates["author_avatar_url"] = args.image
    if db.update_record("AuthorProfile", "author_display_name", args.name, updates):
        print(f"Author updated: {args.name}")
    else:
        print(f"Author not found: {args.name}")

def cmd_author_delete(args):
    db = get_db()
    if db.delete_record("AuthorProfile", "author_display_name", args.name):
        print(f"Author deleted: {args.name}")
    else:
        print(f"Author not found: {args.name}")

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
    if db.add_record("Category", {"cat_name": args.name, "cat_slug": args.slug}):
        print(f"Category added: {args.name} ({args.slug})")
    else:
        print(f"Failed to add category: {args.name}")

def cmd_category_update(args):
    db = get_db()
    if db.update_record("Category", "cat_slug", args.slug, {"cat_name": args.name}):
        print(f"Category updated: {args.slug} -> {args.name}")
    else:
        print(f"Category not found: {args.slug}")

def cmd_category_delete(args):
    db = get_db()
    if db.delete_record("Category", "cat_slug", args.slug):
        print(f"Category deleted: {args.slug}")
    else:
        print(f"Category not found: {args.slug}")

def cmd_category_list(args):
    db = get_db()
    print(json.dumps(db.get_records("Category"), indent=2))

def cmd_nav_add(args):
    db = get_db()
    if args.order:
        print("Note: --order is not supported by the live NavLink schema (nav_display_label, nav_target_url only) -- ignored.")
    if db.add_record("NavLink", {"nav_display_label": args.label, "nav_target_url": args.url}):
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
    if db.add_record("SocialLink", {"social_platform_name": args.platform, "social_target_url": args.url}):
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
        "app_description": args.desc or "", "app_entry_file": entry_file, "app_featured_img": args.image or ""
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
        db.add_record("Category", cat)
    for cfg in _BOOTSTRAP_SITE_CONFIG:
        db.add_record("SiteConfig", cfg)
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
        db.add_record("SiteConfig", {"sys_key": args.key, "sys_value": args.value})
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

    # Mount/Commit
    p_mount = subparsers.add_parser("mount", help="Mount MFDB archives to workspace")
    p_mount.add_argument("--force", action="store_true", help="Force mount")
    
    subparsers.add_parser("commit", help="Commit workspace changes to archives")

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

    p_aupd = author_sub.add_parser("update", help="Update an author")
    p_aupd.add_argument("name", help="Author name (identifies the record -- live schema has no UUID)")
    p_aupd.add_argument("--bio", help="Author bio")
    p_aupd.add_argument("--image", help="Author image URL")
    
    p_adel = author_sub.add_parser("delete", help="Delete an author")
    p_adel.add_argument("name", help="Author name (identifies the record -- live schema has no UUID)")
    
    author_sub.add_parser("list", help="List authors")

    # Category Management
    p_cat = subparsers.add_parser("category", help="Category operations")
    cat_sub = p_cat.add_subparsers(dest="op")
    
    p_cadd = cat_sub.add_parser("add", help="Add a category")
    p_cadd.add_argument("name", help="Category name")
    p_cadd.add_argument("slug", help="Category slug")
    p_cadd.add_argument("--desc", help="Category description")
    p_cadd.add_argument("--type", help="Feed type (blog, portfolio, etc)")

    p_cupd = cat_sub.add_parser("update", help="Update a category")
    p_cupd.add_argument("slug", help="Category slug")
    p_cupd.add_argument("name", help="Category name")

    p_cdel = cat_sub.add_parser("delete", help="Delete a category")
    p_cdel.add_argument("slug", help="Category slug")
    
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
        "mount": cmd_mount,
        "commit": cmd_commit,
        "repack": cmd_commit,
        "page": lambda a: {"add": cmd_page_add, "update": cmd_page_update, "delete": cmd_page_delete, "import": cmd_page_import, "list": lambda _: cmd_db_list(argparse.Namespace(entity="pages", filter=None))}.get(a.op)(a) if a.op else None,
        "author": lambda a: {"add": cmd_author_add, "update": cmd_author_update, "delete": cmd_author_delete, "list": cmd_author_list}.get(a.op)(a) if a.op else None,
        "category": lambda a: {"add": cmd_category_add, "update": cmd_category_update, "delete": cmd_category_delete, "list": cmd_category_list}.get(a.op)(a) if a.op else None,
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
