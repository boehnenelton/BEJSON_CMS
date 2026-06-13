#!/usr/bin/env python3
"""
Script:        cms-manage.py
Description:   Unified CLI Toolkit for BEJSON_CMS management.
Version:       1.1.0
Author:        Elton Boehnen
Date:          2026-06-11
Relational_ID: gcli-cms-cli-001
"""
...
VERSION = "1.1.0"

import sys
import argparse
import json
from pathlib import Path

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
    from lib_cms_mfdb import MFDB_CMS_Manager
    import lib_bejson_core as BEJSONCore
except ImportError as e:
    print(f"FATAL: Missing dependencies. {e}")
    sys.path.append(str(SCRIPT_PATH.parent / "lib")) # Try parent lib
    from lib_cms_mfdb import MFDB_CMS_Manager

VERSION = "1.0.0"

def get_manager():
    # Discover data root from env or default
    data_root = os.environ.get("CMS_DATA_ROOT", str(SCRIPT_PATH.parent / "storage"))
    return MFDB_CMS_Manager(data_root)

def cmd_status(args):
    mgr = get_manager()
    print(f"CMS Data Root: {mgr.data_root}")
    print(f"Mounted: {os.path.exists(mgr.global_db_root)}")
    print(f"Dirty Changes: {mgr.is_dirty()}")

def cmd_mount(args):
    mgr = get_manager()
    print(f"Mounting system at {mgr.data_root}...")
    mgr.mount_system(force=args.force)
    print("Mount complete.")

def cmd_commit(args):
    mgr = get_manager()
    print("Repacking system archives...")
    mgr.repack_system()
    print("Commit complete.")

def cmd_page_add(args):
    mgr = get_manager()
    content = {
        "html_body": args.body or "New Page Content",
        "author_fk": args.author or ""
    }
    uuid = mgr.create_page(args.title, args.category, args.type, content)
    print(f"Page created: {args.title} (UUID: {uuid})")

def cmd_page_update(args):
    mgr = get_manager()
    content = {}
    if args.body: content["html_body"] = args.body
    if args.author: content["author_fk"] = args.author
    mgr.update_page(args.uuid, args.title, args.category, args.type, content)
    print(f"Page updated: {args.uuid}")

def cmd_page_delete(args):
    mgr = get_manager()
    mgr.delete_page(args.uuid)
    print(f"Page deleted: {args.uuid}")

def cmd_page_import(args):
    mgr = get_manager()
    uuid = None
    if args.html:
        uuid = mgr.import_html_as_page(args.html, args.title, args.category, args.author or "")
        if uuid: print(f"HTML imported as page: {args.title} (UUID: {uuid})")
        else: print(f"Failed to import HTML: {args.html}")
    elif args.app:
        uuid = mgr.import_app_as_page(args.app, args.author or "")
        if uuid: print(f"App imported as page (UUID: {uuid})")
        else: print(f"Failed to import app: {args.app}")
    else:
        print("Error: Specify --html or --app for import.")

def cmd_author_add(args):
    mgr = get_manager()
    uuid = mgr.add_author(args.name, args.bio or "", args.image or "")
    print(f"Author added: {args.name} (UUID: {uuid})")

def cmd_author_update(args):
    mgr = get_manager()
    mgr.update_author(args.uuid, args.name, args.bio or "", args.image or "")
    print(f"Author updated: {args.uuid}")

def cmd_author_delete(args):
    mgr = get_manager()
    mgr.delete_author(args.uuid)
    print(f"Author deleted: {args.uuid}")

def cmd_author_list(args):
    mgr = get_manager()
    print(json.dumps(mgr.get_authors(), indent=2))

def cmd_category_add(args):
    mgr = get_manager()
    mgr.add_category(args.name, args.slug, args.desc or "", args.type or "blog")
    print(f"Category added: {args.name}")

def cmd_category_update(args):
    mgr = get_manager()
    mgr.update_category(args.slug, args.name)
    print(f"Category updated: {args.slug}")

def cmd_category_delete(args):
    mgr = get_manager()
    mgr.delete_category(args.slug)
    print(f"Category deleted: {args.slug}")

def cmd_category_list(args):
    mgr = get_manager()
    print(json.dumps(mgr.get_categories(), indent=2))

def cmd_nav_add(args):
    mgr = get_manager()
    mgr.add_nav_link(args.label, args.url, args.order)
    print(f"Nav link added: {args.label}")

def cmd_nav_delete(args):
    mgr = get_manager()
    mgr.delete_nav_link(args.label)
    print(f"Nav link deleted: {args.label}")

def cmd_nav_list(args):
    mgr = get_manager()
    print(json.dumps(mgr.get_nav_links(), indent=2))

def cmd_ad_add(args):
    mgr = get_manager()
    uuid = mgr.add_ad(args.name, args.img, args.link, args.zone, not args.inactive)
    print(f"Ad added: {args.name} (UUID: {uuid})")

def cmd_ad_update(args):
    mgr = get_manager()
    mgr.update_ad(args.uuid, args.name, args.img, args.link, args.zone, not args.inactive)
    print(f"Ad updated: {args.uuid}")

def cmd_ad_delete(args):
    mgr = get_manager()
    mgr.delete_ad(args.uuid)
    print(f"Ad deleted: {args.uuid}")

def cmd_ad_list(args):
    mgr = get_manager()
    print(json.dumps(mgr.get_ads(), indent=2))

def cmd_asset_add(args):
    mgr = get_manager()
    fname = mgr.add_asset(args.file)
    if fname:
        print(f"Asset added: {fname}")
    else:
        print(f"Failed to add asset: {args.file}")

def cmd_asset_delete(args):
    mgr = get_manager()
    if mgr.delete_asset(args.filename):
        print(f"Asset deleted: {args.filename}")
    else:
        print(f"Asset not found: {args.filename}")

def cmd_asset_optimize(args):
    mgr = get_manager()
    print("Optimizing assets (PNG -> WebP)...")
    if mgr.optimize_assets(convert_webp=True):
        print("Asset optimization complete.")
    else:
        print("Asset optimization failed.")

def cmd_app_add(args):
    mgr = get_manager()
    mgr.create_app(args.name, args.desc, args.category, args.image, args.entry)
    print(f"App created: {args.name}")

def cmd_app_delete(args):
    mgr = get_manager()
    mgr.delete_app(args.uuid)
    print(f"App deleted: {args.uuid}")

def cmd_app_list(args):
    mgr = get_manager()
    print(json.dumps(mgr.get_apps(), indent=2))

def cmd_reset(args):
    if input("Are you sure you want to FACTORY RESET the CMS? (y/N): ").lower() == 'y':
        mgr = get_manager()
        mgr.factory_reset()
        print("CMS Factory Reset complete.")
    else:
        print("Reset cancelled.")

def cmd_backup(args):
    mgr = get_manager()
    backup_dir = args.dir or "/storage/emulated/0/Admin/backups/BEJSON_CMS"
    print(f"Creating site backup in {backup_dir}...")
    path = mgr.create_site_backup(backup_dir)
    if path:
        print(f"Backup created successfully: {path}")
    else:
        print("Backup failed.")

def cmd_restore(args):
    if not os.path.exists(args.file):
        print(f"Error: Backup file not found: {args.file}")
        return
    if input(f"Are you sure you want to RESTORE from {args.file}? This will overwrite current state. (y/N): ").lower() == 'y':
        mgr = get_manager()
        if mgr.restore_site_backup(args.file):
            print("Restore complete.")
        else:
            print("Restore failed.")
    else:
        print("Restore cancelled.")

def cmd_config_set(args):
    mgr = get_manager()
    mgr.add_global_config(args.key, args.value, args.desc or "")
    print(f"Config set: {args.key} = {args.value}")

def cmd_config_list(args):
    mgr = get_manager()
    print(json.dumps(mgr.get_global_configs(), indent=2))

def cmd_serve(args):
    scripts = {
        "cms": "Flask_CMS.py",
        "editor": "Flask_Page_Editor.py",
        "publisher": "Flask_CMS_Publisher.py",
        "library": "Flask_Library_Manager.py"
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

def cmd_db_list(args):
    mgr = get_manager()
    if args.entity == "authors":
        recs = mgr.get_authors()
    elif args.entity == "pages":
        if args.filter:
            recs = mgr.get_pages_in_category(args.filter)
        else:
            recs = mgr.get_pages()
    elif args.entity == "categories":
        recs = mgr.get_categories()
    elif args.entity == "assets":
        recs = mgr.get_assets()
    elif args.entity == "apps":
        recs = mgr.get_apps()
    elif args.entity == "ads":
        recs = mgr.get_ads()
    elif args.entity == "navlinks":
        recs = mgr.get_nav_links()
    else:
        print("Unknown entity type.")
        return

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
    p_padd.add_argument("--category", default="uncategorized", help="Category slug")
    p_padd.add_argument("--type", default="blog", help="Page type")
    p_padd.add_argument("--body", help="HTML body content")
    p_padd.add_argument("--author", help="Author UUID")

    p_pupd = page_sub.add_parser("update", help="Update a page")
    p_pupd.add_argument("uuid", help="Page UUID")
    p_pupd.add_argument("title", help="Page title")
    p_pupd.add_argument("--category", help="Category slug")
    p_pupd.add_argument("--type", help="Page type")
    p_pupd.add_argument("--body", help="HTML body content")
    p_pupd.add_argument("--author", help="Author UUID")

    p_pdel = page_sub.add_parser("delete", help="Delete a page")
    p_pdel.add_argument("uuid", help="Page UUID")

    p_pimp = page_sub.add_parser("import", help="Import a page from HTML or App")
    p_pimp.add_argument("--html", help="HTML file path")
    p_pimp.add_argument("--app", help="App UUID")
    p_pimp.add_argument("--title", help="Page title (for HTML import)")
    p_pimp.add_argument("--category", default="uncategorized", help="Category slug")
    p_pimp.add_argument("--author", help="Author UUID")

    page_sub.add_parser("list", help="List pages")

    # Author Management
    p_author = subparsers.add_parser("author", help="Author operations")
    author_sub = p_author.add_subparsers(dest="op")
    
    p_aadd = author_sub.add_parser("add", help="Add an author")
    p_aadd.add_argument("name", help="Author name")
    p_aadd.add_argument("--bio", help="Author bio")
    p_aadd.add_argument("--image", help="Author image URL")

    p_aupd = author_sub.add_parser("update", help="Update an author")
    p_aupd.add_argument("uuid", help="Author UUID")
    p_aupd.add_argument("name", help="Author name")
    p_aupd.add_argument("--bio", help="Author bio")
    p_aupd.add_argument("--image", help="Author image URL")
    
    p_adel = author_sub.add_parser("delete", help="Delete an author")
    p_adel.add_argument("uuid", help="Author UUID")
    
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
    p_asdel.add_argument("filename", help="Asset filename")
    
    asset_sub.add_parser("optimize", help="Optimize assets (PNG to WebP)")
    
    asset_sub.add_parser("list", help="List assets")

    # App Management
    p_app = subparsers.add_parser("app", help="Standalone app operations")
    app_sub = p_app.add_subparsers(dest="op")
    
    p_apadd = app_sub.add_parser("add", help="Create a standalone app")
    p_apadd.add_argument("name", help="App name")
    p_apadd.add_argument("--desc", help="Description")
    p_apadd.add_argument("--category", help="Category slug")
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

    # Service Management
    p_serve = subparsers.add_parser("serve", help="Start CMS services")
    p_serve.add_argument("service", choices=["cms", "editor", "publisher", "library"], default="cms", help="Service to start")

    # DB Operations
    p_db = subparsers.add_parser("db", help="Database operations")
    db_sub = p_db.add_subparsers(dest="op")
    
    p_list = db_sub.add_parser("list", help="List records")
    p_list.add_argument("entity", choices=["authors", "pages", "categories", "assets", "apps", "ads", "navlinks"], help="Entity type")
    p_list.add_argument("--filter", help="Filter (e.g. category slug)")

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
        "ad": lambda a: {"add": cmd_ad_add, "update": cmd_ad_update, "delete": cmd_ad_delete, "list": cmd_ad_list}.get(a.op)(a) if a.op else None,
        "asset": lambda a: {"add": cmd_asset_add, "delete": cmd_asset_delete, "optimize": cmd_asset_optimize, "list": lambda _: cmd_db_list(argparse.Namespace(entity="assets", filter=None))}.get(a.op)(a) if a.op else None,
        "app": lambda a: {"add": cmd_app_add, "delete": cmd_app_delete, "list": cmd_app_list}.get(a.op)(a) if a.op else None,
        "config": lambda a: {"set": cmd_config_set, "list": cmd_config_list}.get(a.op)(a) if a.op else None,
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
