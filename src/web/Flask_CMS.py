"""
BEJSON Web Manager v18.0 (Flask)
================================
RELATION_ID: 67784357-1cf2-4917-a738-b0849106116d
- v18.0: Finalized CMS update — bumped all versions to 18.0; synchronized
  latest BEJSON libraries (v2.x) back to production mirror.
- v17.1: Fixed Category entity read/write path — all write ops (add/remove/update)
  now use _load_entity_doc instead of bejson_core_load_file, matching the read
  path and avoiding resolve_path path-mangling on Android/Termux. Fixes:
  'bool' object is not subscriptable on get_records(Category) and
  'bool' object has no attribute 'get' on add_record(Category).
- v17.1: Fixed factory reset Internal Server Error — skeleton rebuild now
  includes THUMBS_DIR, PAGES_DB_DIR, and PUBLISH_DIR; removed redundant
  STORAGE_ROOT makedirs call inside the loop.
- v17.0: All src/lib/ updated to BEJSON Library v2.0.x (lib_bejson_path_guard new)
- v17.0: Fixed image upload freeze — thumbnail daemon thread now delayed 2 s to
  prevent I/O contention with assets_list page render on Android storage
- v17.0: Fixed HTML import preview freeze — BS4 parse input capped at 2 MB;
  full file still saved to disk
- HTML Import merged in (/import) — uploads .html/.htm files, strips Word/AI
  artefacts, imports as CMS pages with category assignment
- Factory Reset merged in (/reset) — replaces standalone Cleanup_Tool.py
- Ad Manager fully integrated
- Author Manager fully integrated
- Refactored to use BEJSON_Standard_Lib & BEJSON_Extended_Lib
- v16.1: Fixed init_master_db() — now bootstraps site_master MFDB on first run
"""

from flask import Flask, render_template_string, request, redirect, url_for, send_file, flash
import json
import os
import uuid
import shutil
import zipfile
import re
import sys
from datetime import datetime
from werkzeug.utils import secure_filename
import hashlib

import base64
import functools

# ─── HTTP Basic Auth ──────────────────────────────────────────────────────────
# Set CMS_PASSWORD env var before starting. Default: 'changeme' (MUST change).
_CMS_USER = os.environ.get("CMS_USER", "admin")
_CMS_PASS = os.environ.get("CMS_PASSWORD", "changeme")

def _check_auth(username, password):
    return username == _CMS_USER and password == _CMS_PASS

def _unauthorized():
    return ("Unauthorized — Set CMS_PASSWORD env var and restart.", 401,
            {"WWW-Authenticate": 'Basic realm="BEJSON CMS"'})

def require_auth(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not _check_auth(auth.username, auth.password):
            return _unauthorized()
        return f(*args, **kwargs)
    return decorated
# ─────────────────────────────────────────────────────────────────────────────
import html as _html_escape
from pathlib import Path

# --- SCRIPT_PATH Resolution (Mandate Sec 7.1) ---
def get_script_path() -> Path:
    return Path(__file__).resolve().parent
SCRIPT_PATH = get_script_path()

# Import BEJSON Libraries
# Import New MFDB Orchestrator
PROJECT_ROOT = SCRIPT_PATH.parent.parent
LIB_DIR = PROJECT_ROOT / "src" / "lib"

if str(LIB_DIR) not in sys.path:
    sys.path.append(str(LIB_DIR))

import lib_cms_core as CMSCore
import lib_mfdb_core as MFDBCore

try:
    from bs4 import BeautifulSoup
    _BS4_OK = True
except ImportError:
    _BS4_OK = False

def _get_file_hash(file_data):
    sha256_hash = hashlib.sha256()
    # Read in chunks for large files
    for chunk in iter(lambda: file_data.read(4096), b""):
        sha256_hash.update(chunk)
    file_data.seek(0) # Reset pointer
    return sha256_hash.hexdigest()

_PIL_OK = False
try:
    from PIL import Image as _PilImage
    _PIL_OK = True
except ImportError:
    pass

THUMB_SIZE = (300, 300)
# _make_thumbnail is defined later, after THUMBS_DIR path config is set up.


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('CMS_SECRET_KEY') or os.urandom(24).hex()  # Set CMS_SECRET_KEY env var in production
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
ALLOWED_ASSET_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg',
                              '.pdf', '.mp4', '.mp3', '.ogg', '.webm', '.ico'}
# NOTE: SVG is allowed but sanitize SVG content before serving to prevent XSS.

# =============================================================================
# PATH CONFIGURATION (Clean Root Architecture)
# =============================================================================

# (Duplicate PROJECT_ROOT removed by patch_cms.py)

# Storage Domains
STORAGE_ROOT = PROJECT_ROOT / "storage"
MFDB_DIR = STORAGE_ROOT / "mfdb"
MANIFEST_PATH = MFDB_DIR / "site_master" / "104a.mfdb.bejson"
PAGES_DB_DIR = MFDB_DIR / "pages_db"

ASSETS_DIR = MFDB_DIR / "assets"
THUMBS_DIR = ASSETS_DIR / "thumbs"
APPS_STORAGE = MFDB_DIR / "standalone_apps"
EXPORTS_DIR = STORAGE_ROOT / "exports"
PUBLISH_DIR = STORAGE_ROOT / "builds"
UPLOAD_TMP  = STORAGE_ROOT / "tmp" / "html_imports"

# Resources Domain
RESOURCES_ROOT = PROJECT_ROOT / "resources"
TEMPLATE_DIR = RESOURCES_ROOT / "templates"

for d in [MFDB_DIR, PAGES_DB_DIR, ASSETS_DIR, THUMBS_DIR, APPS_STORAGE, EXPORTS_DIR, PUBLISH_DIR, UPLOAD_TMP, TEMPLATE_DIR]:
    os.makedirs(str(d), exist_ok=True)


def _make_thumbnail(filename):
    """Create a 300×300 JPEG thumbnail in THUMBS_DIR.
    Defined here — after ASSETS_DIR and THUMBS_DIR are initialised — so the
    path references are valid. Returns True on success, False otherwise."""
    if not _PIL_OK:
        return False
    src = ASSETS_DIR / filename
    dst = THUMBS_DIR / filename
    if not src.exists():
        return False
    try:
        with _PilImage.open(src) as img:
            img.thumbnail(THUMB_SIZE, _PilImage.LANCZOS)
            if img.mode in ('RGBA', 'P', 'LA'):
                bg = _PilImage.new('RGB', img.size, (0, 0, 0))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                bg.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = bg
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            img.save(dst, 'JPEG', quality=78, optimize=True)
        return True
    except Exception:
        return False

# =============================================================================
# BEJSON STANDARD LIBRARY (embedded)
# =============================================================================

# Helper functions have been moved to CMSCore
db = CMSCore.CMSCore(str(MANIFEST_PATH))

def init_master_db():
    if MANIFEST_PATH.exists():
        return
    print("[CMS] Master MFDB manifest not found — bootstrapping site_master database...")
    site_master_dir = MANIFEST_PATH.parent
    entities = [
        {
            "name": "Category",
            "primary_key": "category_slug",
            "fields": [
                {"name": "category_name", "type": "string"},
                {"name": "category_slug", "type": "string"},
            ],
        },
        {
            "name": "PageRecord",
            "primary_key": "page_uuid",
            "fields": [
                {"name": "page_uuid",    "type": "string"},
                {"name": "page_title",   "type": "string"},
                {"name": "page_slug",    "type": "string"},
                {"name": "category_ref", "type": "string"},
                {"name": "item_type",    "type": "string"},
                {"name": "created_at",   "type": "string"},
                {"name": "external_url", "type": "string"},
                {"name": "author_ref",   "type": "string"},
                {"name": "featured_img", "type": "string"},
                {"name": "template_key", "type": "string"},
            ],
        },
        {
            "name": "StandaloneApp",
            "primary_key": "app_uuid",
            "fields": [
                {"name": "app_uuid",   "type": "string"},
                {"name": "app_name",   "type": "string"},
                {"name": "app_slug",   "type": "string"},
                {"name": "app_desc",   "type": "string"},
                {"name": "entry_file", "type": "string"},
                {"name": "app_image",  "type": "string"},
            ],
        },
        {
            "name": "AuthorProfile",
            "primary_key": "auth_name",
            "fields": [
                {"name": "auth_name", "type": "string"},
                {"name": "auth_bio",  "type": "string"},
                {"name": "auth_img",  "type": "string"},
            ],
        },
        {
            "name": "AdUnit",
            "primary_key": "ad_uuid",
            "fields": [
                {"name": "ad_uuid",   "type": "string"},
                {"name": "ad_name",   "type": "string"},
                {"name": "ad_image",  "type": "string"},
                {"name": "ad_link",   "type": "string"},
                {"name": "ad_zone",   "type": "string"},
                {"name": "ad_active", "type": "boolean"},
            ],
        },
        {
            "name": "SiteConfig",
            "primary_key": "config_key",
            "fields": [
                {"name": "config_key",   "type": "string"},
                {"name": "config_value", "type": "string"},
            ],
        },
        {
            "name": "SocialLink",
            "primary_key": "social_platform",
            "fields": [
                {"name": "social_platform", "type": "string"},
                {"name": "social_url",      "type": "string"},
            ],
        },
        {
            "name": "NavLink",
            "primary_key": "nav_label",
            "fields": [
                {"name": "nav_label", "type": "string"},
                {"name": "nav_url",   "type": "string"},
            ],
        },
        {
            "name": "ExternalMedia",
            "primary_key": "media_uuid",
            "fields": [
                {"name": "media_uuid",  "type": "string"},
                {"name": "media_name",  "type": "string"},
                {"name": "media_type",  "type": "string"},
                {"name": "media_url",   "type": "string"},
                {"name": "created_at",  "type": "string"},
            ],
        },
    ]
    MFDBCore.mfdb_core_create_database(
        root_dir=site_master_dir,
        db_name="BEJSON CMS Site Master",
        entities=entities,
        db_description="Primary CMS database — pages, categories, authors, ads, config.",
    )
    # Seed default category so the UI is never empty
    MFDBCore.mfdb_core_add_entity_record(
        MANIFEST_PATH, "Category", ["Uncategorized", "uncategorized"]
    )
    print("[CMS] site_master bootstrapped successfully.")

init_master_db()


def _migrate_db():
    """Add entities introduced in later versions to an already-bootstrapped
    manifest. Reads the manifest JSON directly so it never depends on CMSCore
    state. Runs on every startup; skips entities that already exist. """
    if not os.path.exists(MANIFEST_PATH):
        return  # init_master_db() will handle first boot

    # Full canonical schema — every entity the CMS needs.
    # Extend this list whenever a new entity is added.
    REQUIRED = [
        {
            "name": "NavLink",
            "primary_key": "nav_label",
            "fields": [
                {"name": "nav_label", "type": "string"},
                {"name": "nav_url",   "type": "string"},
            ],
        },
        {
            "name": "ExternalMedia",
            "primary_key": "media_uuid",
            "fields": [
                {"name": "media_uuid",  "type": "string"},
                {"name": "media_name",  "type": "string"},
                {"name": "media_type",  "type": "string"},
                {"name": "media_url",   "type": "string"},
                {"name": "created_at",  "type": "string"},
            ],
        },
    ]

    try:
        with open(MANIFEST_PATH, 'r', encoding='utf-8') as fh:
            manifest = json.load(fh)

        # entity_name is always position 0 in each manifest value row
        existing = {row[0] for row in manifest.get("Values", [])}
        site_dir  = os.path.dirname(MANIFEST_PATH)
        added     = []

        for spec in REQUIRED:
            name = spec["name"]
            if name in existing:
                continue

            # Create the entity BEJSON 104 file
            fp_rel   = f"data/{name.lower()}.bejson"
            abs_path = os.path.join(site_dir, fp_rel)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            entity_doc = {
                "Format":           "BEJSON",
                "Format_Version":   "104",
                "Format_Creator":   "Elton Boehnen",
                "Parent_Hierarchy": "../104a.mfdb.bejson",
                "Records_Type":     [name],
                "Fields":           spec["fields"],
                "Values":           [],
            }
            tmp = abs_path + ".tmp"
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump(entity_doc, fh, indent=2)
            os.replace(tmp, abs_path)

            # Append row to manifest Values
            # Manifest fields: entity_name, file_path, description,
            #                  record_count, schema_version, primary_key
            manifest["Values"].append(
                [name, fp_rel, None, 0, "1.0", spec.get("primary_key")]
            )
            added.append(name)

        if added:
            tmp = MANIFEST_PATH + ".tmp"
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump(manifest, fh, indent=2)
            os.replace(tmp, MANIFEST_PATH)
            print(f"[CMS] Migration: added missing entities {added}")

    except Exception as exc:
        print(f"[CMS] Migration warning (non-fatal): {exc}")


_migrate_db()

# =============================================================================
# NAVIGATION STRUCTURE
# =============================================================================

NAV_SECTIONS = {
    'dashboard': {
        'icon': '📊',
        'label': 'Dashboard',
        'href': '/',
        'children': []
    },
    'content': {
        'icon': '📝',
        'label': 'Content',
        'href': '/content',
        'children': [
            {'icon': '📄', 'label': 'All Pages', 'href': '/pages'},
            {'icon': '🔗', 'label': 'External Links', 'href': '/links'},
            {'icon': '📁', 'label': 'Categories', 'href': '/categories'},
            {'icon': '📥', 'label': 'HTML Import', 'href': '/import'},
        ]
    },
    'media': {
        'icon': '🖼️',
        'label': 'Media',
        'href': '/assets',
        'children': []
    },
    'apps': {
        'icon': '🚀',
        'label': 'Applications',
        'href': '/apps',
        'children': []
    },
    'site': {
        'icon': '⚙️',
        'label': 'Site Config',
        'href': '/site',
        'children': [
            {'icon': '🏠', 'label': 'General', 'href': '/site'},
            {'icon': '🧭', 'label': 'Navigation', 'href': '/site/nav'},
            {'icon': '👤', 'label': 'Authors', 'href': '/site/authors'},
            {'icon': '📢', 'label': 'Ads', 'href': '/site/ads'},
            {'icon': '🔗', 'label': 'Social Links', 'href': '/site/social'},
        ]
    },
    'publish': {
        'icon': '📦',
        'label': 'Publish',
        'href': '/publish',
        'children': []
    },
    'reset': {
        'icon': '⚠️',
        'label': 'Factory Reset',
        'href': '/reset',
        'children': []
    }
}

# =============================================================================
# BASE TEMPLATE
# =============================================================================

BASE_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>{% block title %}BEJSON Manager{% endblock %}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;900&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0a0a0a;
            --bg-secondary: #141414;
            --bg-card: #1e1e1e;
            --accent: #DE2626;
            --accent-hover: #b91c1c;
            --text-primary: #ffffff;
            --text-secondary: #a0a0a0;
            --border: #2a2a2a;
            --success: #22c55e;
            --warning: #f59e0b;
            --sidebar-width: 280px;
            --header-height: 64px;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body { height: 100%; }
        body {
            font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            overflow-x: hidden;
        }
        .app-wrapper { display: flex; min-height: 100vh; }
        .sidebar {
            width: var(--sidebar-width);
            background: var(--bg-secondary);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            position: fixed;
            top: 0; left: 0; bottom: 0;
            z-index: 1000;
            transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .sidebar-header {
            padding: 0 20px;
            border-bottom: 2px solid var(--accent);
            display: flex;
            align-items: center;
            justify-content: space-between;
            height: var(--header-height);
            background: var(--bg-secondary);
        }
        .logo { font-size: 1.5rem; font-weight: 900; color: var(--text-primary); text-decoration: none; letter-spacing: -1px; }
        .logo span { color: var(--accent); }
        .sidebar-close {
            display: none;
            background: none;
            border: none;
            color: var(--text-primary);
            font-size: 1.75rem;
            cursor: pointer;
            width: 40px; height: 40px;
            border-radius: 8px;
            align-items: center;
            justify-content: center;
        }
        .sidebar-close:hover { background: rgba(255,255,255,0.1); }
        .sidebar-nav { flex: 1; overflow-y: auto; padding: 12px 0; }
        .nav-section { margin-bottom: 4px; }
        .nav-item {
            display: flex;
            align-items: center;
            gap: 14px;
            padding: 12px 20px;
            color: var(--text-secondary);
            text-decoration: none;
            font-weight: 500;
            font-size: 0.95rem;
            transition: all 0.2s ease;
            cursor: pointer;
        }
        .nav-item:hover { background: rgba(222, 38, 38, 0.1); color: var(--text-primary); }
        .nav-item.active { background: var(--accent); color: white; }
        .nav-item .icon { font-size: 1.25rem; width: 26px; text-align: center; flex-shrink: 0; }
        .nav-toggle { margin-left: auto; font-size: 0.7rem; transition: transform 0.2s ease; opacity: 0.7; }
        .nav-toggle.expanded { transform: rotate(90deg); }
        .nav-children { display: none; background: rgba(0,0,0,0.2); }
        .nav-children.expanded { display: block; }
        .nav-child { padding-left: 60px; font-size: 0.9rem; }
        .sidebar-footer {
            padding: 16px 20px;
            border-top: 1px solid var(--border);
            font-size: 0.75rem;
            color: var(--text-secondary);
        }
        .main-wrapper {
            flex: 1;
            min-width: 0;
            width: 0;
            margin-left: var(--sidebar-width);
            display: flex;
            flex-direction: column;
            min-height: 100vh;
            transition: margin-left 0.3s ease;
        }
        .top-header {
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border);
            padding: 0 24px;
            height: var(--header-height);
            display: flex;
            align-items: center;
            justify-content: space-between;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        .header-left { display: flex; align-items: center; gap: 16px; }
        .menu-toggle {
            display: none;
            background: none;
            border: none;
            color: var(--text-primary);
            font-size: 1.5rem;
            cursor: pointer;
            width: 40px; height: 40px;
            border-radius: 8px;
            align-items: center;
            justify-content: center;
        }
        .menu-toggle:hover { background: rgba(255,255,255,0.1); }
        .breadcrumbs { display: flex; align-items: center; gap: 8px; font-size: 0.875rem; flex-wrap: wrap; }
        .breadcrumbs a { color: var(--text-secondary); text-decoration: none; transition: color 0.2s; }
        .breadcrumbs a:hover { color: var(--accent); }
        .breadcrumbs .separator { color: var(--text-secondary); opacity: 0.4; }
        .breadcrumbs .current { color: var(--text-primary); font-weight: 600; }
        .content-area {
            flex: 1;
            padding: 24px;
            max-width: 1400px;
            margin: 0 auto;
            width: 100%;
            min-width: 0;
            box-sizing: border-box;
        }
        .sidebar-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.7);
            backdrop-filter: blur(4px);
            z-index: 999;
            opacity: 0;
            transition: opacity 0.3s ease;
        }
        .sidebar-overlay.active { display: block; opacity: 1; }
        .page-header { margin-bottom: 24px; }
        .page-header h1 { font-size: 1.75rem; font-weight: 800; color: var(--accent); margin-bottom: 6px; }
        .page-header p { color: var(--text-secondary); font-size: 0.95rem; }
        .card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
            min-width: 0;
            overflow: hidden;
        }
        .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }
        .card-title { font-size: 1.1rem; font-weight: 700; }
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            font-family: inherit;
            font-weight: 600;
            font-size: 0.9rem;
            cursor: pointer;
            transition: all 0.2s ease;
            text-decoration: none;
        }
        .btn-primary { background: var(--accent); color: white; }
        .btn-primary:hover { background: var(--accent-hover); transform: translateY(-1px); }
        .btn-secondary { background: var(--bg-secondary); color: var(--text-primary); border: 1px solid var(--border); }
        .btn-secondary:hover { background: var(--border); }
        .btn-success { background: var(--success); color: white; }
        .btn-danger { background: #dc2626; color: white; }
        .btn-sm { padding: 6px 14px; font-size: 0.8rem; }
        .form-group { margin-bottom: 20px; }
        .form-label { display: block; margin-bottom: 8px; font-weight: 600; color: var(--text-secondary); font-size: 0.9rem; }
        .form-control {
            width: 100%;
            padding: 12px 16px;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text-primary);
            font-family: inherit;
            font-size: 1rem;
            transition: border-color 0.2s;
        }
        .form-control:focus { outline: none; border-color: var(--accent); }
        textarea.form-control { min-height: 120px; resize: vertical; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(280px, 100%), 1fr)); gap: 20px; }
        .grid > *, .grid-2 > *, .grid-3 > *, .grid-4 > * { min-width: 0; }
        .grid-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .grid-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
        .grid-4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
        @media (max-width: 1024px) { .grid-4 { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
        @media (max-width: 768px) {
            .grid-2, .grid-3, .grid-4 { grid-template-columns: 1fr; }
            .grid-stat { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }
        }
        .table-container { overflow-x: auto; border-radius: 8px; -webkit-overflow-scrolling: touch; display: block; width: 100%; }
        .table-container table { min-width: 500px; width: 100%; }
        th, td { white-space: nowrap; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 14px 16px; text-align: left; border-bottom: 1px solid var(--border); }
        th { font-weight: 600; color: var(--text-secondary); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; }
        tr:hover { background: rgba(222, 38, 38, 0.03); }
        .badge { display: inline-block; padding: 4px 10px; border-radius: 6px; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; }
        .badge-page { background: #3b82f6; color: white; }
        .badge-app { background: var(--success); color: white; }
        .badge-link { background: #8b5cf6; color: white; }
        .badge-active { background: var(--success); color: white; }
        .badge-inactive { background: #555; color: #ccc; }
        .alert { padding: 16px 20px; border-radius: 8px; margin-bottom: 20px; }
        .alert-success { background: rgba(34, 197, 94, 0.15); border: 1px solid rgba(34, 197, 94, 0.3); color: #4ade80; }
        .alert-error { background: rgba(220, 38, 38, 0.15); border: 1px solid rgba(220, 38, 38, 0.3); color: #f87171; }
        .tabs { display: flex; gap: 4px; margin-bottom: 24px; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
        .tab { padding: 12px 20px; background: none; border: none; color: var(--text-secondary); font-family: inherit; font-weight: 600; cursor: pointer; border-bottom: 2px solid transparent; font-size: 0.9rem; transition: all 0.2s; }
        .tab.active { color: var(--accent); border-bottom-color: var(--accent); }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .empty-state { text-align: center; padding: 60px 20px; color: var(--text-secondary); }
        .empty-state h3 { margin-bottom: 10px; color: var(--text-primary); font-size: 1.25rem; }
        .toolbar { display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }
        .search-box { position: relative; flex: 1; min-width: 200px; max-width: 400px; }
        .search-box input { width: 100%; padding-left: 44px; }
        .search-box::before { content: "🔍"; position: absolute; left: 14px; top: 50%; transform: translateY(-50%); opacity: 0.6; }
        .editor-toolbar { display: flex; gap: 6px; padding: 12px; background: var(--bg-secondary); border-radius: 8px 8px 0 0; border: 1px solid var(--border); border-bottom: none; flex-wrap: wrap; }
        .editor-toolbar button { padding: 8px 14px; background: var(--bg-card); border: 1px solid var(--border); color: var(--text-primary); border-radius: 6px; cursor: pointer; font-size: 0.8rem; font-weight: 500; transition: all 0.2s; }
        .editor-toolbar button:hover { background: var(--accent); border-color: var(--accent); }
        .editor-area { width: 100%; min-height: 400px; padding: 16px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 0 0 8px 8px; color: var(--text-primary); font-family: "Consolas", "Monaco", monospace; font-size: 0.9rem; line-height: 1.6; resize: vertical; }
        .modal-overlay { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8); backdrop-filter: blur(4px); z-index: 1001; align-items: center; justify-content: center; padding: 20px; }
        .modal-overlay.active { display: flex; }
        .modal { background: var(--bg-card); border-radius: 12px; width: 100%; max-width: 600px; max-height: 85vh; overflow-y: auto; border: 1px solid var(--border); }
        .modal-header { padding: 20px 24px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
        .modal-body { padding: 24px; }
        .close-btn { background: none; border: none; color: var(--text-secondary); font-size: 1.5rem; cursor: pointer; width: 36px; height: 36px; border-radius: 8px; display: flex; align-items: center; justify-content: center; }
        .close-btn:hover { background: rgba(255,255,255,0.1); color: var(--text-primary); }
        .asset-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 12px; }
        .asset-item { position: relative; cursor: pointer; border-radius: 8px; overflow: hidden; border: 2px solid transparent; transition: all 0.2s; }
        .asset-item:hover, .asset-item.selected { border-color: var(--accent); }
        .asset-item img { width: 100%; height: 100px; object-fit: cover; }
        .asset-item .asset-name { padding: 8px; font-size: 0.7rem; background: var(--bg-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .status-bar { background: var(--bg-secondary); border-top: 1px solid var(--border); padding: 12px 24px; display: flex; justify-content: space-between; align-items: center; font-size: 0.8rem; color: var(--text-secondary); }
        .stat-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; display: flex; align-items: center; gap: 14px; min-width: 0; }
        .stat-icon { width: 52px; height: 52px; flex-shrink: 0; background: rgba(222, 38, 38, 0.15); border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 1.6rem; }
        .stat-value { font-size: 2rem; font-weight: 800; color: var(--accent); line-height: 1; }
        .stat-label { color: var(--text-secondary); font-size: 0.85rem; margin-top: 4px; }
        .quick-actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
        .quick-action-btn { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 18px 10px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; color: var(--text-primary); text-decoration: none; transition: all 0.2s; min-width: 0; }
        .quick-action-btn:hover { border-color: var(--accent); background: rgba(222, 38, 38, 0.08); transform: translateY(-2px); }
        .quick-action-btn .icon { font-size: 1.5rem; }
        .quick-action-btn .label { font-size: 0.8rem; font-weight: 600; text-align: center; word-break: break-word; }
        @media (max-width: 768px) {
            .sidebar { transform: translateX(-100%); }
            .sidebar.open { transform: translateX(0); }
            .sidebar-close { display: flex; }
            .main-wrapper { margin-left: 0; width: 100%; }
            .menu-toggle { display: flex; }
            .breadcrumbs { display: none; }
            .content-area { padding: 12px; }
            .page-header h1 { font-size: 1.4rem; }
            .card { padding: 14px; }
            .stat-card { flex-direction: column; text-align: center; padding: 14px 10px; }
            .stat-icon { width: 44px; height: 44px; font-size: 1.3rem; }
            .stat-value { font-size: 1.6rem; }
            .top-header { padding: 0 14px; }
            .grid-stat { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; gap: 10px !important; }
            .system-status-grid { grid-template-columns: 1fr !important; }
            .form-group { margin-bottom: 12px; }
        }
    </style>
</head>
<body>
    <div class="app-wrapper">
        <div class="sidebar-overlay" id="sidebarOverlay" onclick="closeSidebar()"></div>
        <aside class="sidebar" id="sidebar">
            <div class="sidebar-header">
                <a href="/" class="logo">BEJSON<span>.</span></a>
                <button class="sidebar-close" onclick="closeSidebar()">&times;</button>
            </div>
            <nav class="sidebar-nav">
                {% for section_id, section in nav_sections.items() %}
                <div class="nav-section">
                    {% if section.children %}
                    <a class="nav-item {% if active_section == section_id %}active{% endif %}" onclick="toggleNavSection(\'{{ section_id }}\')">
                        <span class="icon">{{ section.icon }}</span>
                        <span>{{ section.label }}</span>
                        <span class="nav-toggle {% if active_section == section_id %}expanded{% endif %}" id="toggle-{{ section_id }}">&#9654;</span>
                    </a>
                    <div class="nav-children {% if active_section == section_id %}expanded{% endif %}" id="children-{{ section_id }}">
                        {% for child in section.children %}
                        <a href="{{ child.href }}" class="nav-item nav-child {% if request.path == child.href %}active{% endif %}">
                            <span class="icon">{{ child.icon }}</span>
                            <span>{{ child.label }}</span>
                        </a>
                        {% endfor %}
                    </div>
                    {% else %}
                    <a href="{{ section.href }}" class="nav-item {% if request.path == section.href or (section_id != \'dashboard\' and section.href in request.path) %}active{% endif %}">
                        <span class="icon">{{ section.icon }}</span>
                        <span>{{ section.label }}</span>
                    </a>
                    {% endif %}
                </div>
                {% endfor %}
            </nav>
            <div class="sidebar-footer">
                <div>BEJSON Manager v17.1</div>
                <div>Ready</div>
            </div>
        </aside>
        <div class="main-wrapper">
            <header class="top-header">
                <div class="header-left">
                    <button class="menu-toggle" onclick="openSidebar()">&#9776;</button>
                    <nav class="breadcrumbs">
                        <a href="/">Home</a>
                        {% for crumb in breadcrumbs %}
                        <span class="separator">/</span>
                        {% if crumb.href %}
                        <a href="{{ crumb.href }}">{{ crumb.label }}</a>
                        {% else %}
                        <span class="current">{{ crumb.label }}</span>
                        {% endif %}
                        {% endfor %}
                    </nav>
                </div>
                <div class="header-right">
                    <span class="badge" style="background: var(--accent); color: white; padding: 4px 10px; border-radius: 6px; font-size: 0.7rem; font-weight: 600;">v17.0</span>
                </div>
            </header>
            <main class="content-area">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                {% block content %}{% endblock %}
            </main>
            <div class="status-bar">
                <span>BEJSON Web Manager v17.1</span>
                <span>Ready</span>
            </div>
        </div>
    </div>
    <script>
        function openSidebar() {
            document.getElementById(\'sidebar\').classList.add(\'open\');
            document.getElementById(\'sidebarOverlay\').classList.add(\'active\');
            document.body.style.overflow = \'hidden\';
        }
        function closeSidebar() {
            document.getElementById(\'sidebar\').classList.remove(\'open\');
            document.getElementById(\'sidebarOverlay\').classList.remove(\'active\');
            document.body.style.overflow = \'\';
        }
        function toggleNavSection(sectionId) {
            const children = document.getElementById(\'children-\' + sectionId);
            const toggle = document.getElementById(\'toggle-\' + sectionId);
            if (children.classList.contains(\'expanded\')) {
                children.classList.remove(\'expanded\');
                toggle.classList.remove(\'expanded\');
            } else {
                children.classList.add(\'expanded\');
                toggle.classList.add(\'expanded\');
            }
        }
        document.querySelectorAll(\'.tab\').forEach(tab => {
            tab.addEventListener(\'click\', () => {
                const target = tab.dataset.tab;
                document.querySelectorAll(\'.tab\').forEach(t => t.classList.remove(\'active\'));
                document.querySelectorAll(\'.tab-content\').forEach(c => c.classList.remove(\'active\'));
                tab.classList.add(\'active\');
                document.getElementById(target).classList.add(\'active\');
            });
        });
        function openModal(id) { document.getElementById(id).classList.add(\'active\'); }
        function closeModal(id) { document.getElementById(id).classList.remove(\'active\'); }
        function insertTag(tag) {
            const editor = document.getElementById(\'html-editor\');
            if (!editor) return;
            const start = editor.selectionStart;
            const end = editor.selectionEnd;
            const selected = editor.value.substring(start, end);
            const before = editor.value.substring(0, start);
            const after = editor.value.substring(end);
            let insert = \'\';
            if (tag === \'br\') insert = \'<br>\\n\';
            else if (tag === \'p\') insert = \'<p>\' + (selected || \'Paragraph text\') + \'</p>\';
            else if (tag === \'h2\') insert = \'<h2>\' + (selected || \'Heading\') + \'</h2>\';
            else if (tag === \'h3\') insert = \'<h3>\' + (selected || \'Subheading\') + \'</h3>\';
            else if (tag === \'b\') insert = selected ? \'<strong>\' + selected + \'</strong>\' : \'<strong>Bold text</strong>\';
            else if (tag === \'a\') insert = \'<a href="#">\' + (selected || \'Link text\') + \'</a>\';
            else if (tag === \'img\') insert = \'<img src="../../../assets/image.jpg" alt="Image" style="max-width:100%;">\';
            editor.value = before + insert + after;
            editor.focus();
        }
        function insertImage(filename) {
            const editor = document.getElementById(\'html-editor\');
            if (!editor) return;
            const tag = \'<img src="../../../assets/\' + filename + \'" alt="\' + filename + \'" style="max-width:100%; border-radius:8px; margin: 20px 0;">\';
            const pos = editor.selectionStart;
            editor.value = editor.value.substring(0, pos) + \'\\n\' + tag + \'\\n\' + editor.value.substring(pos);
            editor.selectionStart = editor.selectionEnd = pos + tag.length + 2;
            editor.focus();
            closeModal(\'asset-modal\');
        }
        function filterTable(input, tableId) {
            const filter = input.value.toLowerCase();
            const table = document.getElementById(tableId);
            if (!table) return;
            const rows = table.getElementsByTagName(\'tr\');
            for (let i = 1; i < rows.length; i++) {
                const text = rows[i].textContent.toLowerCase();
                rows[i].style.display = text.includes(filter) ? \'\' : \'none\';
            }
        }
        window.addEventListener(\'resize\', () => { if (window.innerWidth > 768) { closeSidebar(); } });
    </script>
</body>
</html>'''


def R(content, **kwargs):
    """Helper to render with base template."""
    return render_template_string(
        BASE_TEMPLATE.replace('{% block content %}{% endblock %}', content),
        nav_sections=NAV_SECTIONS,
        **kwargs
    )


def get_breadcrumbs(path):
    if path == '/':
        return [{'label': 'Dashboard', 'href': None}]
    path_parts = [p for p in path.split('/') if p]
    breadcrumb_map = {
        'pages': ('Content', '/content'),
        'content': ('Content', None),
        'links': ('External Links', None),
        'categories': ('Categories', None),
        'new': ('New', None),
        'edit': ('Edit', None),
        'assets': ('Media', None),
        'apps': ('Applications', None),
        'site': ('Site Config', None),
        'nav': ('Navigation', None),
        'authors': ('Authors', None),
        'ads': ('Ads', None),
        'social': ('Social Links', None),
        'publish': ('Publish', None),
    }
    breadcrumbs = []
    for i, part in enumerate(path_parts):
        label, href = breadcrumb_map.get(part, (part.capitalize(), None))
        if href is None and i < len(path_parts) - 1:
            href = '/' + '/'.join(path_parts[:i+1])
        elif i == len(path_parts) - 1:
            href = None
        breadcrumbs.append({'label': label, 'href': href})
    return breadcrumbs


def get_active_section(path):
    if path == '/':
        return 'dashboard'
    elif '/pages' in path or '/links' in path or '/categories' in path or '/content' in path:
        return 'content'
    elif '/assets' in path:
        return 'media'
    elif '/apps' in path:
        return 'apps'
    elif '/site' in path:
        return 'site'
    elif '/publish' in path:
        return 'publish'
    return ''


def get_assets():
    return [f for f in sorted(os.listdir(ASSETS_DIR)) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))]


# =============================================================================
# ROUTES — DASHBOARD
# =============================================================================

@app.route('/')
@require_auth
def dashboard():
    db.mount()
    stats = {
        'pages': len([r for r in db.get_records("PageRecord") if r.get('item_type') != 'external_link']),
        'apps': len(db.get_records("StandaloneApp")),
        'categories': len(db.get_records("Category")),
        'assets': len(get_assets()),
        'ads': len(db.get_records("AdUnit")),
    }
    pages = db.get_records("PageRecord")
    pages.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    recent = [{'title': p.get('page_title'), 'type': p.get('item_type', 'page'), 'date': p.get('created_at', 'N/A'), 'uuid': p.get('page_uuid')} for p in pages[:5]]
    

    html = '''
    <div class="page-header"><h1>Dashboard</h1><p>BEJSON Content Management System</p></div>
    <div class="grid grid-4 grid-stat" style="margin-bottom: 24px;">
        <div class="stat-card"><div class="stat-icon">&#128196;</div><div><div class="stat-value">{{ stats.pages }}</div><div class="stat-label">Pages</div></div></div>
        <div class="stat-card"><div class="stat-icon">&#128640;</div><div><div class="stat-value">{{ stats.apps }}</div><div class="stat-label">Applications</div></div></div>
        <div class="stat-card"><div class="stat-icon">&#128193;</div><div><div class="stat-value">{{ stats.categories }}</div><div class="stat-label">Categories</div></div></div>
        <div class="stat-card"><div class="stat-icon">&#128444;</div><div><div class="stat-value">{{ stats.assets }}</div><div class="stat-label">Assets</div></div></div>
    </div>
    <div class="grid grid-2">
        <div class="card">
            <div class="card-header"><span class="card-title">Recent Content</span><a href="/pages" class="btn btn-secondary btn-sm">View All</a></div>
            {% if recent %}<div class="table-container"><table><thead><tr><th>Title</th><th>Type</th><th>Date</th><th>Actions</th></tr></thead><tbody>{% for item in recent %}<tr><td>{{ item.title }}</td><td><span class="badge badge-{{ item.type }}">{{ item.type }}</span></td><td>{{ item.date }}</td><td><a href="/edit/{{ item.uuid }}" class="btn btn-primary btn-sm">Edit</a></td></tr>{% endfor %}</tbody></table></div>
            {% else %}<div class="empty-state"><h3>No content yet</h3><p>Create your first page to get started</p><br><a href="/pages/new" class="btn btn-primary">Create Page</a></div>{% endif %}
        </div>
        <div class="card">
            <div class="card-header"><span class="card-title">Quick Actions</span></div>
            <div class="quick-actions">
                <a href="/pages/new" class="quick-action-btn"><span class="icon">&#10133;</span><span class="label">New Page</span></a>
                <a href="/apps/new" class="quick-action-btn"><span class="icon">&#128230;</span><span class="label">Import App</span></a>
                <a href="/assets" class="quick-action-btn"><span class="icon">&#128228;</span><span class="label">Upload Asset</span></a>
                <a href="/site/ads" class="quick-action-btn"><span class="icon">&#128226;</span><span class="label">Manage Ads</span></a>
            </div>
        </div>
    </div>
    <div class="card">
        <div class="card-header"><span class="card-title">System Status</span></div>
        <div class="system-status-grid" style="color: var(--text-secondary); display: grid; grid-template-columns: repeat(auto-fit, minmax(min(250px,100%), 1fr)); gap: 12px;">
            <p><strong>Database:</strong> &#9989; Connected</p>
            <p><strong>Assets Dir:</strong> <code style="background: var(--bg-secondary); padding: 2px 6px; border-radius: 4px; word-break: break-all; font-size: 0.8rem;">{{ assets_dir }}</code></p>
            <p><strong>Publish Dir:</strong> <code style="background: var(--bg-secondary); padding: 2px 6px; border-radius: 4px; word-break: break-all; font-size: 0.8rem;">{{ publish_dir }}</code></p>
            <p><strong>Active Ads:</strong> {{ stats.ads }}</p>
        </div>
    </div>'''
    return R(html, stats=stats, recent=recent, assets_dir=ASSETS_DIR, publish_dir=PUBLISH_DIR,
             breadcrumbs=get_breadcrumbs(request.path), active_section='dashboard')


# =============================================================================
# ROUTES — CONTENT
# =============================================================================

@app.route('/content')
def content_hub():
    html = '''
    <div class="page-header"><h1>Content Management</h1><p>Manage all your website content</p></div>
    <div class="grid grid-3">
        <a href="/pages" class="card" style="text-decoration:none;color:inherit;"><div style="text-align:center;padding:20px;"><div style="font-size:3rem;margin-bottom:15px;">&#128196;</div><h3>Pages</h3><p style="color:var(--text-secondary);">Create and edit pages</p></div></a>
        <a href="/links" class="card" style="text-decoration:none;color:inherit;"><div style="text-align:center;padding:20px;"><div style="font-size:3rem;margin-bottom:15px;">&#128279;</div><h3>External Links</h3><p style="color:var(--text-secondary);">Manage external link references</p></div></a>
        <a href="/categories" class="card" style="text-decoration:none;color:inherit;"><div style="text-align:center;padding:20px;"><div style="font-size:3rem;margin-bottom:15px;">&#128193;</div><h3>Categories</h3><p style="color:var(--text-secondary);">Organize content by category</p></div></a>
    </div>'''
    return R(html, breadcrumbs=get_breadcrumbs(request.path), active_section='content')


@app.route('/pages')
def pages_list():
    db.mount()
    items = db.get_records("PageRecord")
    categories = db.get_records("Category")
    
    pages = [p for p in items if p.get('item_type') != 'external_link']
    links = [p for p in items if p.get('item_type') == 'external_link']

    html = '''
    <div class="page-header"><h1>Pages</h1><p>Manage your website pages and articles</p></div>
    <div class="tabs">
        <button class="tab active" data-tab="tab-pages">Pages ({{ pages|length }})</button>
        <button class="tab" data-tab="tab-links">External Links ({{ links|length }})</button>
        <button class="tab" data-tab="tab-categories">Categories ({{ categories|length }})</button>
    </div>
    <div id="tab-pages" class="tab-content active">
        <div class="toolbar"><a href="/pages/new" class="btn btn-primary">+ New Page</a>
        <div class="search-box"><input type="text" class="form-control" placeholder="Search pages..." onkeyup="filterTable(this, \'pages-table\')"></div></div>
        <div class="card">{% if pages %}<div class="table-container"><table id="pages-table"><thead><tr><th>Title</th><th>Category</th><th>Type</th><th>Date</th><th>Actions</th></tr></thead><tbody>
        {% for p in pages %}<tr><td>{{ p.page_title }}</td><td>{{ p.category_ref or \'Uncategorized\' }}</td><td><span class="badge badge-page">{{ p.item_type or \'page\' }}</span></td><td>{{ p.created_at or \'N/A\' }}</td>
        <td><a href="/edit/{{ p.page_uuid }}" class="btn btn-primary btn-sm">Edit</a> <form method="post" action="/pages/delete/{{ p.page_uuid }}" style="display:inline;" onsubmit="return confirm(\'Delete this page?\')"><button type="submit" class="btn btn-danger btn-sm">Delete</button></form></td></tr>{% endfor %}
        </tbody></table></div>{% else %}<div class="empty-state"><h3>No pages yet</h3><a href="/pages/new" class="btn btn-primary">Create your first page</a></div>{% endif %}</div>
    </div>
    <div id="tab-links" class="tab-content">
        <div class="toolbar"><a href="/links/new" class="btn btn-primary">+ Add External Link</a></div>
        <div class="card">{% if links %}<div class="table-container"><table><thead><tr><th>Label</th><th>URL</th><th>Category</th><th>Actions</th></tr></thead><tbody>
        {% for l in links %}<tr><td>&#128279; {{ l.page_title }}</td><td><a href="{{ l.external_url }}" target="_blank" style="color:var(--accent);">{{ l.external_url[:60] if l.external_url else \'\' }}</a></td><td>{{ l.category_ref or \'Uncategorized\' }}</td>
        <td><form method="post" action="/pages/delete/{{ l.page_uuid }}" style="display:inline;" onsubmit="return confirm(\'Delete this page?\')"><button type="submit" class="btn btn-danger btn-sm">Delete</button></form></td></tr>{% endfor %}
        </tbody></table></div>{% else %}<div class="empty-state"><h3>No external links</h3></div>{% endif %}</div>
    </div>
    <div id="tab-categories" class="tab-content">
        <div class="toolbar">
            <form action="/categories/add" method="POST" style="display:flex;gap:10px;flex:1;">
                <input type="text" name="category_name" class="form-control" placeholder="New category name..." required>
                <button type="submit" class="btn btn-primary">Add Category</button>
            </form>
        </div>
        <div class="card"><div class="table-container"><table><thead><tr><th>Category Name</th><th>Slug</th><th>Actions</th></tr></thead><tbody>
        {% for c in categories %}<tr><td>{{ c.category_name }}</td><td><code style="background:var(--bg-secondary);padding:2px 8px;border-radius:4px;">{{ c.category_slug }}</code></td>
        <td>{% if c.category_name != \'Uncategorized\' %}<form method="post" action="/categories/delete/{{ c.category_name }}" style="display:inline;" onsubmit="return confirm(\'Delete category?\')"><button type="submit" class="btn btn-danger btn-sm">Delete</button></form>{% endif %}</td></tr>{% endfor %}
        </tbody></table></div></div>
    </div>'''
    return R(html, pages=pages, links=links, categories=categories,
             breadcrumbs=get_breadcrumbs(request.path), active_section='content')


@app.route('/pages/new', methods=['GET', 'POST'])
def page_new():
    db.mount()
    categories = db.get_records("Category")
    assets = get_assets()
    

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        category = request.form.get('category', '').strip()
        featured_img = request.form.get('featured_img', '')
        author = request.form.get('author', '')
        if not title:
            return "Title required", 400
        if not category:
            return "Category required", 400
        new_uuid = str(uuid.uuid4())
        slug = re.sub(r'[^a-z0-9]', '-', title.lower()).strip('-')
        db.mount()
        db.add_record("PageRecord", {"page_uuid": new_uuid, "page_title": title, "page_slug": slug,
            "category_ref": category, "item_type": "page", "created_at": datetime.now().strftime("%Y-%m-%d"),
            "external_url": None, "author_ref": author, "featured_img": featured_img})
        
        pfile = os.path.join(PAGES_DB_DIR, f"{new_uuid}.json")
        import json
        data = {
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
                ["Content", None, f"<h2>{title}</h2><p>Start writing your content here...</p>", "", ""]
            ]
        }
        with open(pfile, 'w') as f:
            json.dump(data, f, indent=2)
        
        return redirect(f'/edit/{new_uuid}')

    html = '''
    <div class="page-header"><h1>Create New Page</h1><p>Add a new page to your website</p></div>
    <form method="POST" class="card">
        <div class="form-group"><label class="form-label">Page Title *</label><input type="text" name="title" class="form-control" required autofocus></div>
        <div class="grid grid-2">
            <div class="form-group"><label class="form-label">Category *</label><select name="category" class="form-control" required><option value="" disabled selected>-- Select Category --</option>{% for c in categories %}<option value="{{ c.category_name }}">{{ c.category_name }}</option>{% endfor %}</select></div>
            <div class="form-group"><label class="form-label">Author</label><input type="text" name="author" class="form-control" placeholder="Author name"></div>
        </div>
        <div class="form-group"><label class="form-label">Featured Image</label><select name="featured_img" class="form-control"><option value="">-- No image --</option>{% for a in assets %}<option value="{{ a }}">{{ a }}</option>{% endfor %}</select></div>
        <div style="display:flex;gap:10px;margin-top:30px;"><button type="submit" class="btn btn-primary">Create Page</button><a href="/pages" class="btn btn-secondary">Cancel</a></div>
    </form>'''
    return R(html, categories=categories, assets=assets,
             breadcrumbs=get_breadcrumbs(request.path), active_section='content')


@app.route('/edit/<page_uuid>', methods=['GET', 'POST'])
def edit_content(page_uuid):
    pfile = os.path.join(PAGES_DB_DIR, f"{page_uuid}.json")
    if not os.path.exists(pfile):
        return "Content file not found", 404
    db.mount()
    pages = db.get_records("PageRecord")
    page = next((p for p in pages if p['page_uuid'] == page_uuid), None)
    
    if not page:
        return "Page not found", 404

    if request.method == 'POST':
        html_content = request.form.get('html_content', '')
        title = request.form.get('title', page['page_title'])
        featured_img = request.form.get('featured_img', page.get('featured_img', ''))
        author = request.form.get('author_ref', page.get('author_ref', ''))
        # Update content file
        try:
            import json
            import lib_bejson_core as Core
            with open(pfile, "r") as f: data = json.load(f)
            field_map = Core.bejson_core_get_field_map(data)
            p_idx = field_map.get("Record_Type_Parent", -1)
            h_idx = field_map.get("html_body", -1)
            m_idx = field_map.get("meta_title", -1)
            for row in data.get("Values", []):
                if p_idx != -1:
                    if row[p_idx] == "Content" and h_idx != -1: row[h_idx] = html_content
                    if row[p_idx] == "PageMeta" and m_idx != -1: row[m_idx] = title
            with open(pfile, "w") as f: json.dump(data, f, indent=2)
        except Exception as err: print(f"Content write error: {err}")

        # Update Master Record
        db.update_record("PageRecord", "page_uuid", page_uuid, {
            "page_title": title, "featured_img": featured_img, "author_ref": author
        })
        flash("Changes saved successfully!", "success")
        return redirect(f"/edit/{page_uuid}")

    # GET - Load content
    html_content = ""
    try:
        import json
        import lib_bejson_core as Core
        with open(pfile, "r") as f: data = json.load(f)
        field_map = Core.bejson_core_get_field_map(data)
        p_idx = field_map.get("Record_Type_Parent", -1)
        h_idx = field_map.get("html_body", -1)
        for row in data.get("Values", []):
            if p_idx != -1 and row[p_idx] == "Content" and h_idx != -1:
                html_content = row[h_idx] or ""
                break
    except Exception: pass
    
    assets = get_assets()

    html = '''
    <div class="page-header"><h1>Edit: {{ page.page_title }}</h1><p>UUID: {{ page_uuid }}</p></div>
    <form method="POST">
        <div class="card">
            <div class="form-group"><label class="form-label">Title</label><input type="text" name="title" class="form-control" value="{{ page.page_title }}"></div>
            <div class="grid grid-2">
                <div class="form-group">
                    <label class="form-label">Featured Image</label>
                    <select name="featured_img" class="form-control">
                        <option value="">-- No image --</option>
                        {% for a in assets %}<option value="{{ a }}" {% if a == page.featured_img and page.featured_img and page.featured_img != 'None' %}selected{% endif %}>{{ a }}</option>{% endfor %}
                    </select>
                    {% if page.featured_img and page.featured_img != 'None' %}<div style="margin-top:8px;"><img src="/assets/{{ page.featured_img }}" style="max-height:80px;border-radius:6px;border:1px solid var(--border);" alt="current"></div>{% endif %}
                </div>
                <div class="form-group"><label class="form-label">Author</label><input type="text" name="author_ref" class="form-control" value="{{ page.author_ref or \'\' }}" placeholder="Author name"></div>
            </div>
        </div>
        <div class="card">
            <div class="card-header"><span class="card-title">HTML Content Editor</span><div><button type="button" class="btn btn-secondary btn-sm" onclick="openModal(\'asset-modal\')">&#128444; Insert Image</button></div></div>
            <div class="editor-toolbar"><button type="button" onclick="insertTag(\'h2\')">H2</button><button type="button" onclick="insertTag(\'h3\')">H3</button><button type="button" onclick="insertTag(\'p\')">P</button><button type="button" onclick="insertTag(\'b\')">Bold</button><button type="button" onclick="insertTag(\'br\')">Break</button><button type="button" onclick="insertTag(\'a\')">Link</button></div>
            <textarea id="html-editor" name="html_content" class="editor-area"></textarea>
            <script>document.addEventListener('DOMContentLoaded',function(){document.getElementById('html-editor').value={{ html_content | tojson }};});</script>
        </div>
        <div style="display:flex;gap:10px;margin-top:20px;"><button type="submit" class="btn btn-primary">&#128190; Save Changes</button><a href="/pages" class="btn btn-secondary">&#8592; Back to Pages</a></div>
    </form>
    <div id="asset-modal" class="modal-overlay" onclick="if(event.target===this)closeModal(\'asset-modal\')"><div class="modal"><div class="modal-header"><h3>Select Image</h3><button class="close-btn" onclick="closeModal(\'asset-modal\')">&times;</button></div><div class="modal-body"><div class="asset-grid">{% for a in assets %}<div class="asset-item" onclick="insertImage(\'{{ a }}\')"><img src="/assets/{{ a }}" alt="{{ a }}" loading="lazy"><div class="asset-name">{{ a }}</div></div>{% endfor %}</div></div></div></div>'''
    breadcrumbs = [{'label': 'Content', 'href': '/content'}, {'label': 'Pages', 'href': '/pages'}, {'label': page['page_title'], 'href': None}]
    return R(html, page=page, page_uuid=page_uuid, html_content=html_content, assets=assets,
             breadcrumbs=breadcrumbs, active_section='content')


@app.route('/pages/delete/<page_uuid>', methods=['POST'])
def delete_page(page_uuid):
    db.mount()
    deleted = db.delete_record("PageRecord", "page_uuid", page_uuid)
    
    if deleted:
        pfile = os.path.join(PAGES_DB_DIR, f"{page_uuid}.json")
        if os.path.exists(pfile):
            os.remove(pfile)
        flash('Page deleted.', 'success')
    else:
        flash('Error: page could not be deleted from database.', 'error')
    return redirect('/pages')


@app.route('/links')
def links_list():
    db.mount()
    links = [p for p in db.get_records("PageRecord") if p.get('item_type') == 'external_link']
    
    html = '''
    <div class="page-header"><h1>External Links</h1><p>Manage external link references</p></div>
    <div class="toolbar"><a href="/links/new" class="btn btn-primary">+ Add External Link</a></div>
    <div class="card">{% if links %}<div class="table-container"><table><thead><tr><th>Label</th><th>URL</th><th>Category</th><th>Actions</th></tr></thead><tbody>
    {% for l in links %}<tr><td>&#128279; {{ l.page_title }}</td><td><a href="{{ l.external_url }}" target="_blank" style="color:var(--accent);">{{ l.external_url[:60] if l.external_url else \'\' }}</a></td><td>{{ l.category_ref or \'Uncategorized\' }}</td>
    <td><form method="post" action="/pages/delete/{{ p.page_uuid }}" style="display:inline;" onsubmit="return confirm(\'Delete this page?\')"><button type="submit" class="btn btn-danger btn-sm">Delete</button></form></td></tr>{% endfor %}
    </tbody></table></div>{% else %}<div class="empty-state"><h3>No external links</h3><p>Add links to external resources</p><br><a href="/links/new" class="btn btn-primary">Add Link</a></div>{% endif %}</div>'''
    return R(html, links=links, breadcrumbs=get_breadcrumbs(request.path), active_section='content')


@app.route('/links/new', methods=['GET', 'POST'])
def link_new():
    db.mount()
    categories = db.get_records("Category")
    
    if request.method == 'POST':
        label = request.form.get('label', '').strip()
        url = request.form.get('url', '').strip()
        category = request.form.get('category', 'Uncategorized')
        if not label or not url:
            flash('Label and URL are required.', 'error')
            return redirect('/links/new')
        new_uuid = str(uuid.uuid4())
        slug = re.sub(r'[^a-z0-9]', '-', label.lower()).strip('-')
        db.mount()
        db.add_record("PageRecord", {"page_uuid": new_uuid, "page_title": label, "page_slug": slug,
            "category_ref": category, "item_type": "external_link", "external_url": url,
            "created_at": datetime.now().strftime("%Y-%m-%d"), "author_ref": "", "featured_img": ""})
        
        flash('External link added.', 'success')
        return redirect('/links')
    html = '''
    <div class="page-header"><h1>Add External Link</h1></div>
    <form method="POST" class="card">
        <div class="form-group"><label class="form-label">Label *</label><input type="text" name="label" class="form-control" required autofocus></div>
        <div class="form-group"><label class="form-label">URL *</label><input type="url" name="url" class="form-control" required placeholder="https://"></div>
        <div class="form-group"><label class="form-label">Category</label><select name="category" class="form-control">{% for c in categories %}<option value="{{ c.category_name }}">{{ c.category_name }}</option>{% endfor %}</select></div>
        <div style="display:flex;gap:10px;margin-top:20px;"><button type="submit" class="btn btn-primary">Add Link</button><a href="/links" class="btn btn-secondary">Cancel</a></div>
    </form>'''
    return R(html, categories=categories, breadcrumbs=get_breadcrumbs(request.path), active_section='content')


@app.route('/categories')
def categories_list():
    db.mount()
    categories = db.get_records("Category")
    
    html = '''
    <div class="page-header"><h1>Categories</h1><p>Organize your content by category</p></div>
    <div class="toolbar">
        <form action="/categories/add" method="POST" style="display:flex;gap:10px;flex:1;">
            <input type="text" name="category_name" class="form-control" placeholder="New category name..." required>
            <button type="submit" class="btn btn-primary">Add Category</button>
        </form>
    </div>
    <div class="card"><div class="table-container"><table><thead><tr><th>Category Name</th><th>Slug</th><th>Actions</th></tr></thead><tbody>
    {% for c in categories %}<tr><td>{{ c.category_name }}</td><td><code style="background:var(--bg-secondary);padding:2px 8px;border-radius:4px;">{{ c.category_slug }}</code></td>
    <td>{% if c.category_name != \'Uncategorized\' %}<form method="post" action="/categories/delete/{{ c.category_name }}" style="display:inline;" onsubmit="return confirm(\'Delete category?\')"><button type="submit" class="btn btn-danger btn-sm">Delete</button></form>{% endif %}</td></tr>{% endfor %}
    </tbody></table></div></div>'''
    return R(html, categories=categories, breadcrumbs=get_breadcrumbs(request.path), active_section='content')


@app.route('/categories/add', methods=['POST'])
def categories_add():
    name = request.form.get('category_name', '').strip()
    if name:
        slug = re.sub(r'[^a-z0-9]', '-', name.lower()).strip('-')
        db.mount()
        exists = any(c.get('category_name') == name for c in db.get_records("Category"))
        if not exists:
            db.add_record("Category", {"category_name": name, "category_slug": slug})
        
        flash(f'Category "{name}" added.', 'success')
    return redirect('/categories')


@app.route("/categories/delete/<name>", methods=['POST'])
def categories_delete(name):
    if name == "Uncategorized":
        flash("Cannot delete Uncategorized.", "error")
        return redirect("/categories")
    
    # Delete the category
    db.delete_record("Category", "category_name", name)
    
    # Reassign pages to Uncategorized using orchestrator
    pages = db.get_records("PageRecord")
    for p in pages:
        if p.get("category_ref") == name:
            db.update_record("PageRecord", "page_uuid", p["page_uuid"], {"category_ref": "Uncategorized"})
            
    flash(f"Category '{name}' deleted. Pages reassigned to Uncategorized.", "success")
    return redirect("/categories")


# =============================================================================
# ROUTES — ASSETS
# =============================================================================

@app.route('/assets')
def assets_list():
    import collections
    import re as _re

    # -- Physical files -------------------------------------------------------
    all_files = sorted([f for f in os.listdir(ASSETS_DIR) if not f.startswith('.')])
    grouped   = collections.defaultdict(list)
    img_exts  = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}

    for f in all_files:
        path = os.path.join(ASSETS_DIR, f)
        if not os.path.isfile(path):
            continue
        size  = os.path.getsize(path)
        first = f[0].upper() if f[0].isalpha() else '#'
        ext   = os.path.splitext(f)[1].lower()
        has_thumb = os.path.exists(os.path.join(THUMBS_DIR, f))
        grouped[first].append({
            'name':     f,
            'size':     f"{size/1024:.1f} KB",
            'url':      f"/assets/{f}",
            'thumb':    f"/assets/thumbs/{f}" if has_thumb else f"/assets/{f}",
            'ext':      ext,
            'is_img':   ext in img_exts,
            'kind':     'file',
            'safe_id':  _re.sub(r'[^a-zA-Z0-9]', '_', f),
        })

    sorted_groups = sorted(grouped.items())
    all_img_urls  = [f"/assets/{f}" for f in all_files
                     if os.path.splitext(f)[1].lower() in img_exts]

    # -- External / YouTube media ---------------------------------------------
    ext_media = []
    try:
        db.mount()
        for r in db.get_records("ExternalMedia"):
            mtype = r.get('media_type', 'external')
            murl  = r.get('media_url', '')
            thumb = murl
            if mtype == 'youtube':
                vid_match = _re.search(r'(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})', murl)
                if vid_match:
                    thumb = f"https://img.youtube.com/vi/{vid_match.group(1)}/hqdefault.jpg"
            ext_media.append({
                'uuid':    r.get('media_uuid', ''),
                'name':    r.get('media_name') or murl,
                'type':    mtype,
                'url':     murl,
                'thumb':   thumb,
                'created': r.get('created_at', ''),
                'safe_id': _re.sub(r'[^a-zA-Z0-9]', '_', r.get('media_uuid', '')),
            })
    except Exception:
        pass

    # -- References check -----------------------------------------------------
    cms_assets = set()
    try:
        for r in db.get_records("PageRecord"):
            if r.get("featured_img"): cms_assets.add(r["featured_img"])
        for r in db.get_records("StandaloneApp"):
            if r.get("app_image"):   cms_assets.add(r["app_image"])
        for r in db.get_records("AuthorProfile"):
            if r.get("auth_img"):    cms_assets.add(r["auth_img"])
        for r in db.get_records("AdUnit"):
            if r.get("ad_image"):    cms_assets.add(r["ad_image"])
    except Exception:
        pass
    missing_assets = [a for a in cms_assets
                      if not os.path.exists(os.path.join(ASSETS_DIR, a))]

    html = """
    <style>
        .media-container { max-width:1200px; margin:0 auto; width:100%; padding:0 10px; }
        .accordion-item  { border:1px solid var(--border); border-radius:8px; margin-bottom:12px; overflow:hidden; background:var(--card); }
        .accordion-header{ padding:14px 18px; cursor:pointer; display:flex; justify-content:space-between; align-items:center; font-weight:700; transition:background 0.2s; }
        .accordion-header:hover { background:rgba(255,255,255,0.05); }
        .accordion-content{ display:none; padding:15px; border-top:1px solid var(--border); }
        .accordion-item.active .accordion-content { display:block; }
        .accordion-item.active .accordion-header  { background:rgba(222,38,38,0.08); color:var(--accent); }
        .asset-list { display:grid; grid-template-columns:repeat(auto-fill, minmax(150px,1fr)); gap:8px; }
        @media(max-width:480px){ .asset-list{ grid-template-columns:repeat(3,1fr); gap:5px; } }
        .asset-card { border:1px solid var(--border); border-radius:6px; overflow:hidden; background:var(--bg-secondary); cursor:pointer; transition:border-color 0.15s; display:flex; flex-direction:column; }
        .asset-card:hover { border-color:var(--accent); }
        .asset-thumb-wrap { width:100%; aspect-ratio:1/1; overflow:hidden; background:#111; flex-shrink:0; }
        .asset-thumb { width:100%; height:100%; object-fit:cover; display:block; }
        .asset-thumb-ph { width:100%; height:100%; display:flex; align-items:center; justify-content:center; font-size:1.6rem; }
        .asset-footer { padding:6px 8px; }
        .asset-fn { font-size:0.72rem; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-bottom:2px; }
        .asset-meta { font-size:0.65rem; color:var(--text-secondary); margin-bottom:4px; }
        .asset-actions { display:flex; gap:3px; flex-wrap:wrap; }
        .btn-xs { padding:3px 6px; font-size:0.65rem; border-radius:3px; font-weight:700; cursor:pointer; border:none; }
        .rename-form { display:none; padding:7px; border-top:1px solid var(--border); background:rgba(0,0,0,0.3); }
        .missing-badge { background:var(--accent); color:white; padding:2px 8px; border-radius:4px; font-size:0.7rem; font-weight:900; }
        /* Lightbox */
        #lb-overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.93); z-index:9999; flex-direction:column; align-items:center; justify-content:center; }
        #lb-overlay.open { display:flex; }
        #lb-img  { max-width:90vw; max-height:78vh; border-radius:6px; object-fit:contain; box-shadow:0 8px 40px rgba(0,0,0,0.6); }
        #lb-name { margin-top:14px; color:#ddd; font-size:0.88rem; font-family:monospace; text-align:center; padding:0 20px; word-break:break-all; }
        #lb-counter { color:#777; font-size:0.72rem; margin-top:5px; }
        .lb-nav  { position:fixed; top:50%; transform:translateY(-50%); background:rgba(255,255,255,0.08); border:none; color:#fff; font-size:2.2rem; line-height:1; padding:12px 18px; cursor:pointer; border-radius:8px; }
        #lb-prev { left:10px; }
        #lb-next { right:10px; }
        #lb-close{ position:fixed; top:14px; right:14px; background:rgba(255,255,255,0.1); border:none; color:#fff; font-size:1.3rem; padding:6px 12px; cursor:pointer; border-radius:6px; }
        .ext-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(170px,1fr)); gap:10px; }
        .ext-badge { display:inline-block; padding:2px 6px; border-radius:3px; font-size:0.65rem; font-weight:900; text-transform:uppercase; vertical-align:middle; }
        .ext-badge.youtube  { background:#ff0000; color:#fff; }
        .ext-badge.external { background:#1e40af; color:#fff; }
        /* View switcher */
        .view-bar { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:16px; }
        .view-btn { padding:6px 14px; border:1px solid var(--border); background:var(--bg-secondary); color:var(--text-primary); border-radius:20px; font-size:0.78rem; font-weight:600; cursor:pointer; transition:all 0.15s; white-space:nowrap; }
        .view-btn.active { background:var(--accent); border-color:var(--accent); color:#fff; }
    </style>

    <!-- Lightbox -->
    <div id="lb-overlay" onclick="lbClickBg(event)">
        <button id="lb-close" onclick="lbClose()">&times;</button>
        <button class="lb-nav" id="lb-prev" onclick="lbNav(-1)">&#8249;</button>
        <img id="lb-img" src="" alt="">
        <button class="lb-nav" id="lb-next" onclick="lbNav(1)">&#8250;</button>
        <div id="lb-name"></div>
        <div id="lb-counter"></div>
    </div>

    <div class="media-container">
        <div class="page-header">
            <h1>Media Library</h1>
            <div style="display:flex;gap:8px;align-items:center;">
                <span class="badge b-on">{{ total_count }} Files</span>
                {% if missing_count > 0 %}<span class="missing-badge">{{ missing_count }} MISSING</span>{% endif %}
            </div>
        </div>

        <div class="toolbar" style="margin-bottom:16px;">
            <form action="/assets/upload" method="POST" enctype="multipart/form-data" style="display:flex;gap:10px;flex:1;">
                <input type="file" name="files" multiple class="form-control" style="flex:1;font-size:0.8rem;">
                <button type="submit" class="btn btn-primary" style="white-space:nowrap;">Upload</button>
            </form>
            <form action="/assets/regen-thumbs" method="POST" style="flex-shrink:0;">
                <button type="submit" class="btn btn-secondary" style="white-space:nowrap;" title="Generate thumbnails for all images (requires Pillow)">&#128444; Regen Thumbs</button>
            </form>
        </div>

        <div class="view-bar" id="view-bar">
            <button class="view-btn active" onclick="setView('all',this)">All</button>
            <button class="view-btn" onclick="setView('images',this)">Images</button>
            <button class="view-btn" onclick="setView('documents',this)">Documents</button>
            <button class="view-btn" onclick="setView('video',this)">Video</button>
            <button class="view-btn" onclick="setView('external',this)">External</button>
            <button class="view-btn" onclick="setView('youtube',this)">YouTube</button>
        </div>

        <div class="card" style="margin-bottom:20px;">
            <div class="card-header"><span class="card-title">Add External Media</span></div>
            <form action="/assets/add-external" method="POST" style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;padding:12px;">
                <div class="form-group" style="flex:2;min-width:160px;margin-bottom:0;">
                    <label class="form-label" style="font-size:0.8rem;">URL &mdash; paste an image URL or a YouTube link</label>
                    <input type="url" name="media_url" class="form-control" placeholder="https://..." required>
                </div>
                <div class="form-group" style="flex:1;min-width:120px;margin-bottom:0;">
                    <label class="form-label" style="font-size:0.8rem;">Display Name (optional)</label>
                    <input type="text" name="media_name" class="form-control" placeholder="My screenshot">
                </div>
                <button type="submit" class="btn btn-secondary" style="white-space:nowrap;">Add</button>
            </form>
        </div>

        {% if missing_assets %}
        <div class="card" style="border-left:3px solid var(--accent);margin-bottom:20px;padding:15px;">
            <h3 style="margin-bottom:8px;font-size:0.9rem;color:var(--accent);">&#9888; Broken References</h3>
            <div style="display:flex;flex-wrap:wrap;gap:6px;">
                {% for m in missing_assets %}
                <span style="background:rgba(222,38,38,0.1);padding:4px 8px;border-radius:4px;border:1px solid rgba(222,38,38,0.2);font-size:0.75rem;font-family:monospace;color:#fca5a5;">{{ m }}</span>
                {% endfor %}
            </div>
        </div>
        {% endif %}

        {% if ext_media %}
        <div id="ext-media-section" class="card" style="margin-bottom:20px;">
            <div class="card-header"><span class="card-title">External Media ({{ ext_media|length }})</span></div>
            <div style="padding:12px;">
            <div class="ext-grid">
            {% for em in ext_media %}
            <div class="ext-media-card" data-type="{{ em.type }}" style="border:1px solid var(--border);border-radius:6px;overflow:hidden;background:var(--bg-secondary);">
                <img src="{{ em.thumb }}" style="width:100%;height:110px;object-fit:cover;display:block;" loading="lazy" onerror="this.style.background='#222';this.style.height='40px'">
                <div style="padding:8px;">
                    <div style="font-size:0.75rem;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:5px;" title="{{ em.url }}">{{ em.name }}</div>
                    <div style="display:flex;gap:5px;align-items:center;flex-wrap:wrap;">
                        <span class="ext-badge {{ em.type }}">{{ em.type }}</span>
                        <button class="btn btn-secondary btn-xs" onclick="copyExtTag('{{ em.type }}','{{ em.url|e }}','{{ em.name|e }}')">TAG</button>
                        <form method="post" action="/assets/external/delete/{{ em.uuid }}" style="display:inline;" onsubmit="return confirm('Remove this entry?')">
                            <button type="submit" class="btn btn-danger btn-xs">DEL</button>
                        </form>
                    </div>
                </div>
            </div>
            {% endfor %}
            </div>
            </div>
        </div>
        {% endif %}

        <div class="accordion" id="main-accordion" data-img-urls='{{ all_img_urls|tojson|safe }}'>
        {% for char, group in groups %}
        <div class="accordion-item" id="group-{{ char }}">
            <div class="accordion-header" onclick="toggleAccordion('group-{{ char }}')">
                <span>{{ char }} <small style="font-weight:400;margin-left:8px;opacity:0.5;">({{ group|length }})</small></span>
                <span style="font-size:0.7rem;">&#9660;</span>
            </div>
            <div class="accordion-content">
                <div class="asset-list">
                {% for a in group %}
                <div class="asset-card" {% if a.is_img %}data-img-url="{{ a.url }}"{% endif %} onclick="if(this.dataset.imgUrl) lbOpenCard(this);">
                    <div class="asset-thumb-wrap">
                    {% if a.is_img %}
                    <img src="{{ a.thumb }}" class="asset-thumb" loading="lazy" alt="{{ a.name }}" onerror="this.src='{{ a.url }}'">
                    {% else %}
                    <div class="asset-thumb-ph">{{ a.ext[1:]|upper if a.ext else '??' }}</div>
                    {% endif %}
                    </div>
                    <div class="asset-footer">
                        <div class="asset-fn" title="{{ a.name }}" data-ext="{{ a.ext }}">{{ a.name }}</div>
                        <div class="asset-meta">{{ a.size }}</div>
                        <div class="asset-actions">
                            <button class="btn btn-secondary btn-xs" onclick="event.stopPropagation();copyTag('{{ a.name }}')">TAG</button>
                            <button class="btn btn-secondary btn-xs" onclick="event.stopPropagation();showRename('{{ a.safe_id }}')">RENAME</button>
                            <form method="post" action="/assets/delete/{{ a.name }}" style="display:inline;" onsubmit="event.stopPropagation();return confirm('Delete permanently?')">
                                <button type="submit" class="btn btn-danger btn-xs">DEL</button>
                            </form>
                        </div>
                        <div id="rename-{{ a.safe_id }}" class="rename-form" onclick="event.stopPropagation()">
                            <form action="/assets/rename/{{ a.name }}" method="POST" style="display:flex;flex-direction:column;gap:5px;">
                                <input type="text" name="new_name" value="{{ a.name }}" class="form-control" style="padding:5px;font-size:0.8rem;">
                                <div style="display:flex;gap:4px;">
                                    <button class="btn btn-primary btn-xs" style="flex:1;">SAVE</button>
                                    <button type="button" class="btn btn-secondary btn-xs" onclick="hideRename('{{ a.safe_id }}')">&#10005;</button>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>
                {% endfor %}
                </div>
            </div>
        </div>
        {% endfor %}
        </div>

        {% if not groups %}<div class="card empty-state"><h3>Library is empty</h3><p>Upload files to get started.</p></div>{% endif %}
    </div>

    <script>
        function toggleAccordion(id) { document.getElementById(id).classList.toggle('active'); }

        function copyTag(fn) {
            var tag = '<img src="../../../assets/' + fn + '" alt="' + fn + '" style="max-width:100%;">';
            navigator.clipboard.writeText(tag);
            alert('HTML tag copied!');
        }
        function copyExtTag(type, url, name) {
            var tag;
            if (type === 'youtube') {
                var m = url.match(/(?:v=|youtu\\.be\\/)([A-Za-z0-9_-]{11})/);
                var vid = m ? m[1] : '';
                tag = '<iframe width="560" height="315" src="https://www.youtube.com/embed/' + vid + '" frameborder="0" allowfullscreen></iframe>';
            } else {
                tag = '<img src="' + url + '" alt="' + name + '" style="max-width:100%;">';
            }
            navigator.clipboard.writeText(tag);
            alert('Embed tag copied!');
        }
        function showRename(sid) {
            document.querySelectorAll('.rename-form').forEach(function(el){ el.style.display='none'; });
            var el = document.getElementById('rename-' + sid);
            if (el) el.style.display = 'block';
        }
        function hideRename(sid) {
            var el = document.getElementById('rename-' + sid);
            if (el) el.style.display = 'none';
        }

        // Lightbox
        var _lbUrls = [], _lbIdx = 0;
        function lbOpenCard(card) {
            var accordion = document.getElementById('main-accordion');
            try {
                _lbUrls = JSON.parse(accordion.dataset.imgUrls || '[]');
            } catch(e) { _lbUrls = []; }
            var curUrl = card.dataset.imgUrl || '';
            _lbIdx = _lbUrls.indexOf(curUrl);
            if (_lbIdx < 0) _lbIdx = 0;
            _lbShow();
            document.getElementById('lb-overlay').classList.add('open');
            document.addEventListener('keydown', lbKey);
        }
        // Legacy alias kept for any external callers
        function lbOpen(urls, curUrl) {
            _lbUrls = urls;
            _lbIdx  = _lbUrls.indexOf(curUrl);
            if (_lbIdx < 0) _lbIdx = 0;
            _lbShow();
            document.getElementById('lb-overlay').classList.add('open');
            document.addEventListener('keydown', lbKey);
        }
        function _lbShow() {
            var url  = _lbUrls[_lbIdx];
            document.getElementById('lb-img').src            = url;
            document.getElementById('lb-name').textContent   = decodeURIComponent(url.split('/').pop());
            document.getElementById('lb-counter').textContent = (_lbIdx + 1) + ' / ' + _lbUrls.length;
        }
        function lbNav(dir) {
            _lbIdx = (_lbIdx + dir + _lbUrls.length) % _lbUrls.length;
            _lbShow();
        }
        function lbClose() {
            document.getElementById('lb-overlay').classList.remove('open');
            document.removeEventListener('keydown', lbKey);
        }
        function lbClickBg(e) { if (e.target.id === 'lb-overlay') lbClose(); }
        function lbKey(e) {
            if (e.key === 'Escape')     lbClose();
            if (e.key === 'ArrowRight') lbNav(1);
            if (e.key === 'ArrowLeft')  lbNav(-1);
        }

        // View switcher
        var IMG_EXTS  = new Set(['.png','.jpg','.jpeg','.gif','.webp','.svg']);
        var DOC_EXTS  = new Set(['.pdf','.doc','.docx','.txt','.csv','.xls','.xlsx']);
        var VID_EXTS  = new Set(['.mp4','.webm','.mp3','.ogg','.mov','.avi']);
        var _curView  = 'all';

        function setView(view, btn) {
            _curView = view;
            document.querySelectorAll('.view-btn').forEach(function(b){ b.classList.remove('active'); });
            btn.classList.add('active');

            // Physical-file accordions
            var allCards = document.querySelectorAll('.asset-card');
            allCards.forEach(function(card) {
                var fn  = card.querySelector('.asset-fn');
                var ext = fn ? fn.getAttribute('data-ext') : '';
                var show = false;
                if (view === 'all')       show = true;
                else if (view === 'images')    show = IMG_EXTS.has(ext);
                else if (view === 'documents') show = DOC_EXTS.has(ext);
                else if (view === 'video')     show = VID_EXTS.has(ext);
                card.style.display = show ? '' : 'none';
            });

            // Hide accordion groups that are now empty
            document.querySelectorAll('.accordion-item').forEach(function(grp) {
                var visible = grp.querySelectorAll('.asset-card:not([style*="display: none"]):not([style*="display:none"])').length;
                grp.style.display = visible ? '' : 'none';
            });

            // External media section
            var extSection = document.getElementById('ext-media-section');
            if (extSection) {
                extSection.style.display = (view === 'all' || view === 'external' || view === 'youtube') ? '' : 'none';
            }

            // Filter individual ext-media cards by type
            if (view === 'external' || view === 'youtube') {
                document.querySelectorAll('.ext-media-card').forEach(function(card) {
                    var t = card.getAttribute('data-type');
                    card.style.display = (t === view) ? '' : 'none';
                });
            } else {
                document.querySelectorAll('.ext-media-card').forEach(function(card) {
                    card.style.display = '';
                });
            }
        }
    </script>
    """
    return R(html, groups=sorted_groups, total_count=len(all_files),
             missing_assets=missing_assets, missing_count=len(missing_assets),
             ext_media=ext_media, all_img_urls=all_img_urls,
             breadcrumbs=get_breadcrumbs(request.path), active_section='media')

@app.route('/assets/upload', methods=['POST'])
def assets_upload():
    files = request.files.getlist('files')
    # No hashing at all — hash reads the entire file on Android storage and
    # blocks Flask's single thread. Dedup by filename within this batch only.
    batch_names   = set()
    uploaded_count = 0
    skipped_count  = 0

    for f in files:
        if not f or not f.filename:
            continue
        filename = secure_filename(f.filename)
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_ASSET_EXTENSIONS:
            flash(f'Rejected "{filename}" — file type not allowed.', 'error')
            skipped_count += 1
            continue
        if filename in batch_names:
            skipped_count += 1
            continue
        batch_names.add(filename)
        if os.path.exists(os.path.join(ASSETS_DIR, filename)):
            base, fext = os.path.splitext(filename)
            filename = f"{base}_{uuid.uuid4().hex[:6]}{fext}"
        f.save(os.path.join(ASSETS_DIR, filename))
        # Generate thumbnail in a daemon thread so the upload response
        # is not blocked by Pillow I/O on Android storage.
        # Delay start by 2 s so the redirect + assets_list page render
        # completes before Pillow competes for Android storage I/O.
        import threading as _threading
        import time as _time
        def _delayed_thumb(fn):
            _time.sleep(2)
            _make_thumbnail(fn)
        _threading.Thread(
            target=_delayed_thumb, args=(filename,), daemon=True
        ).start()
        uploaded_count += 1

    if uploaded_count > 0:
        flash(f'Uploaded {uploaded_count} file(s).', 'success')
    if skipped_count > 0:
        flash(f'Skipped {skipped_count} file(s).', 'info')
    if uploaded_count == 0 and skipped_count == 0:
        flash('No files selected or all were invalid.', 'error')

    return redirect('/assets')


@app.route('/assets/delete/<filename>', methods=['POST'])
def assets_delete(filename):
    fpath = os.path.join(ASSETS_DIR, secure_filename(filename))
    if os.path.exists(fpath):
        os.remove(fpath)
        flash(f'Asset "{filename}" deleted.', 'success')
    return redirect('/assets')


@app.route('/assets/rename/<filename>', methods=['POST'])
def assets_rename(filename):
    new_name = request.form.get('new_name', '').strip()
    if not new_name:
        flash('New name cannot be empty.', 'error')
        return redirect('/assets')
    
    new_name = secure_filename(new_name)
    # Ensure extension is preserved if not provided
    _, old_ext = os.path.splitext(filename)
    if not os.path.splitext(new_name)[1]:
        new_name += old_ext
    
    old_path = os.path.join(ASSETS_DIR, secure_filename(filename))
    new_path = os.path.join(ASSETS_DIR, new_name)
    
    if os.path.exists(new_path):
        flash(f'An asset named "{new_name}" already exists.', 'error')
    elif os.path.exists(old_path):
        os.rename(old_path, new_path)
        flash(f'Asset renamed to "{new_name}".', 'success')
    else:
        flash('Asset not found.', 'error')
        
    return redirect('/assets')


@app.route('/assets/add-external', methods=['POST'])
def assets_add_external():
    import re as _re
    db.mount()
    media_url  = request.form.get('media_url', '').strip()
    media_name = request.form.get('media_name', '').strip()
    if not media_url:
        flash('URL is required.', 'error')
        return redirect('/assets')
    # Detect YouTube
    yt_match = _re.search(r'(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})', media_url)
    media_type = 'youtube' if yt_match else 'external'
    if not media_name:
        media_name = f"YouTube — {yt_match.group(1)}" if yt_match else media_url[:60]
    db.add_record("ExternalMedia", {
        "media_uuid":  str(uuid.uuid4()),
        "media_name":  media_name,
        "media_type":  media_type,
        "media_url":   media_url,
        "created_at":  datetime.now().strftime("%Y-%m-%d"),
    })
    db.commit()
    flash(f'External media "{media_name}" added.', 'success')
    return redirect('/assets')


@app.route('/assets/external/delete/<media_uuid>', methods=['POST'])
def assets_external_delete(media_uuid):
    db.mount()
    db.delete_record("ExternalMedia", "media_uuid", media_uuid)
    db.commit()
    flash('External media entry removed.', 'success')
    return redirect('/assets')

@app.route('/assets/thumbs/<path:filename>')
def serve_thumb(filename):
    """Serve thumbnail; fall back to original if thumb doesn't exist."""
    thumb_path = os.path.join(THUMBS_DIR, filename)
    if os.path.exists(thumb_path):
        return send_file(thumb_path)
    return send_file(os.path.join(ASSETS_DIR, filename))


@app.route('/assets/regen-thumbs', methods=['POST'])
def regen_thumbs():
    """Backfill thumbnails for all existing images in ASSETS_DIR."""
    if not _PIL_OK:
        flash('Pillow not installed — install with: pip install Pillow --break-system-packages', 'error')
        return redirect('/assets')
    img_exts = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
    count = 0
    for f in os.listdir(ASSETS_DIR):
        if os.path.splitext(f)[1].lower() in img_exts:
            if _make_thumbnail(f):
                count += 1
    flash(f'Generated {count} thumbnail(s).', 'success')
    return redirect('/assets')


@app.route('/assets/<path:filename>')
def serve_asset(filename):
    return send_file(os.path.join(ASSETS_DIR, filename))


# =============================================================================
# ROUTES — APPLICATIONS
# =============================================================================

@app.route('/apps')
def apps_list():
    db.mount()
    apps = db.get_records("StandaloneApp")
    
    html = '''
    <div class="page-header"><h1>Applications</h1><p>Manage standalone HTML/JS applications</p></div>
    <div class="toolbar"><a href="/apps/new" class="btn btn-primary">+ Import App</a></div>
    <div class="grid">{% for a in apps %}<div class="card"><div style="display:flex;justify-content:space-between;align-items:start;"><div><h3 style="margin-bottom:10px;">{{ a.app_name }}</h3><p style="color:var(--text-secondary);font-size:0.9rem;">{{ a.app_desc or \'No description\' }}</p><p style="color:var(--text-secondary);font-size:0.8rem;margin-top:10px;">Slug: <code>{{ a.app_slug }}</code></p></div>{% if a.app_image %}<img src="/assets/{{ a.app_image }}" style="width:80px;height:80px;object-fit:cover;border-radius:6px;">{% endif %}</div><div style="margin-top:20px;display:flex;gap:10px;"><a href="/apps/view/{{ a.app_uuid }}" class="btn btn-secondary btn-sm">View</a><form method="post" action="/apps/delete/{{ a.app_uuid }}" style="display:inline;" onsubmit="return confirm(\'Delete app?\')"><button type="submit" class="btn btn-danger btn-sm">Delete</button></form></div></div>{% endfor %}</div>
    {% if not apps %}<div class="card empty-state"><h3>No applications yet</h3><p>Import HTML files or ZIP archives</p><br><a href="/apps/new" class="btn btn-primary">Import App</a></div>{% endif %}'''
    return R(html, apps=apps, breadcrumbs=get_breadcrumbs(request.path), active_section='apps')


@app.route('/apps/new', methods=['GET', 'POST'])
def app_new():
    assets = get_assets()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        desc = request.form.get('desc', '')
        entry_file = request.form.get('entry_file', 'index.html')
        app_image = request.form.get('app_image', '')
        if not name:
            return "App name required", 400
        uploaded_file = request.files.get('app_file')
        new_uuid = str(uuid.uuid4())
        slug = re.sub(r'[^a-z0-9]', '-', name.lower()).strip('-')
        app_dir = os.path.join(APPS_STORAGE, new_uuid)
        os.makedirs(app_dir, exist_ok=True)
        if uploaded_file and uploaded_file.filename:
            filename = secure_filename(uploaded_file.filename)
            if filename.endswith('.zip'):
                zip_path = os.path.join(app_dir, 'temp.zip')
                uploaded_file.save(zip_path)
                with zipfile.ZipFile(zip_path, 'r') as z:
                    z.extractall(app_dir)
                os.remove(zip_path)
            else:
                uploaded_file.save(os.path.join(app_dir, filename))
                entry_file = filename
        db.mount()
        db.add_record("StandaloneApp", {"app_uuid": new_uuid, "app_name": name, "app_slug": slug,
            "app_desc": desc, "entry_file": entry_file, "app_image": app_image})
        
        flash(f'App "{name}" imported.', 'success')
        return redirect('/apps')
    html = '''
    <div class="page-header"><h1>Import Application</h1><p>Add a standalone application</p></div>
    <form method="POST" enctype="multipart/form-data" class="card">
        <div class="form-group"><label class="form-label">App Name *</label><input type="text" name="name" class="form-control" required></div>
        <div class="form-group"><label class="form-label">Description</label><textarea name="desc" class="form-control"></textarea></div>
        <div class="form-group"><label class="form-label">Entry File (e.g., index.html)</label><input type="text" name="entry_file" class="form-control" value="index.html"></div>
        <div class="form-group"><label class="form-label">Featured Image</label><select name="app_image" class="form-control"><option value="">-- No image --</option>{% for a in assets %}<option value="{{ a }}">{{ a }}</option>{% endfor %}</select></div>
        <div class="form-group"><label class="form-label">App File (HTML or ZIP) *</label><input type="file" name="app_file" class="form-control" accept=".html,.htm,.zip" required></div>
        <div style="display:flex;gap:10px;margin-top:30px;"><button type="submit" class="btn btn-primary">Import App</button><a href="/apps" class="btn btn-secondary">Cancel</a></div>
    </form>'''
    return R(html, assets=assets, breadcrumbs=get_breadcrumbs(request.path), active_section='apps')


@app.route('/apps/delete/<app_uuid>', methods=['POST'])
def app_delete(app_uuid):
    db.mount()
    db.delete_record("StandaloneApp", "app_uuid", app_uuid)
    
    app_dir = os.path.join(APPS_STORAGE, app_uuid)
    if os.path.exists(app_dir):
        shutil.rmtree(app_dir)
    flash('App deleted.', 'success')
    return redirect('/apps')


@app.route('/apps/view/<app_uuid>')
def serve_app(app_uuid):
    app_dir = os.path.join(APPS_STORAGE, app_uuid)
    if not os.path.exists(app_dir):
        return "App not found", 404
    db.mount()
    apps = db.get_records("StandaloneApp")
    
    app_data = next((a for a in apps if a['app_uuid'] == app_uuid), None)
    if not app_data:
        return "App not found in database", 404
    entry_file = app_data.get('entry_file', 'index.html')
    entry_path = os.path.join(app_dir, entry_file)
    if not os.path.exists(entry_path):
        return "Entry file not found", 404
    return send_file(entry_path)


import uuid as _uuid_mod

@app.route('/apps/view/<app_uuid>/<path:filename>')
def serve_app_static(app_uuid, filename):
    # Validate app_uuid is a proper UUID to prevent path traversal
    try:
        _uuid_mod.UUID(app_uuid)
    except ValueError:
        return 'Invalid app ID', 400
    safe_root = os.path.realpath(APPS_STORAGE)
    file_path = os.path.realpath(os.path.join(APPS_STORAGE, app_uuid, filename))
    if not file_path.startswith(safe_root + os.sep):
        return 'Access denied', 403
    if os.path.exists(file_path):
        return send_file(file_path)
    return 'File not found', 404


# =============================================================================
# ROUTES — SITE CONFIG
# =============================================================================

@app.route("/site", methods=["GET", "POST"])
def site_config():
    if request.method == "POST":
        configs = {
            "site_name": request.form.get("site_title", ""),
            "title": request.form.get("site_title", ""),
            "creator": request.form.get("site_creator", ""),
            "description": request.form.get("site_desc", ""),
            "base_url": request.form.get("base_url", "")
        }
        
        for k, v in configs.items():
            # Update existing or add new
            existing = db.get_records("SiteConfig")
            match = next((r for r in existing if r.get("config_key") == k), None)
            if match:
                db.update_record("SiteConfig", "config_key", k, {"config_value": v})
            else:
                db.add_record("SiteConfig", {"config_key": k, "config_value": v})
                
        flash("Configuration saved!", "success")
        return redirect("/site")

    configs = {}
    for r in db.get_records("SiteConfig"):
        configs[r.get('config_key', '')] = r.get('config_value', '')
    

    html = '''
    <div class="page-header"><h1>Site Configuration</h1><p>Configure your website settings</p></div>
    <form method="POST" class="card">
        <div class="form-group"><label class="form-label">Site Title</label><input type="text" name="site_title" class="form-control" value="{{ configs.get(\'title\', \'\') }}"></div>
        <div class="form-group"><label class="form-label">Author / Creator</label><input type="text" name="site_creator" class="form-control" value="{{ configs.get(\'creator\', \'\') }}"></div>
        <div class="form-group"><label class="form-label">Description</label><textarea name="site_desc" class="form-control">{{ configs.get(\'description\', \'\') }}</textarea></div>
        <div class="form-group"><label class="form-label">Base URL</label><input type="text" name="base_url" class="form-control" value="{{ configs.get(\'base_url\', \'\') }}" placeholder="https://yoursite.com"></div>
        <button type="submit" class="btn btn-primary">Save Configuration</button>
    </form>'''
    return R(html, configs=configs, breadcrumbs=get_breadcrumbs(request.path), active_section='site')


@app.route('/site/nav', methods=['GET', 'POST'])
def site_nav():
    db.mount()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            label = request.form.get('nav_label', '').strip()
            url = request.form.get('nav_url', '').strip()
            if label and url:
                db.add_record("NavLink", {"nav_label": label, "nav_url": url})
        elif action == 'delete':
            label = request.form.get('nav_label', '')
            db.delete_record("NavLink", "nav_label", label)
        db.commit()
        
        flash('Navigation updated.', 'success')
        return redirect('/site/nav')

    nav_links = db.get_records("NavLink")
    

    html = '''
    <div class="page-header"><h1>Navigation Links</h1><p>Manage your site navigation menu</p></div>
    <div class="grid grid-2">
        <div class="card">
            <div class="card-header"><span class="card-title">Add Nav Link</span></div>
            <form method="POST">
                <input type="hidden" name="action" value="add">
                <div class="form-group"><label class="form-label">Label</label><input type="text" name="nav_label" class="form-control" required></div>
                <div class="form-group"><label class="form-label">URL</label><input type="text" name="nav_url" class="form-control" required placeholder="/page or https://..."></div>
                <button type="submit" class="btn btn-primary">Add Link</button>
            </form>
        </div>
        <div class="card">
            <div class="card-header"><span class="card-title">Current Nav Links</span></div>
            {% for nav in nav_links %}
            <div style="display:flex;justify-content:space-between;align-items:center;padding:10px;background:var(--bg-secondary);margin-bottom:5px;border-radius:4px;">
                <span>{{ nav.nav_label }} &rarr; {{ nav.nav_url }}</span>
                <form method="POST" style="display:inline;">
                    <input type="hidden" name="action" value="delete">
                    <input type="hidden" name="nav_label" value="{{ nav.nav_label }}">
                    <button type="submit" class="btn btn-danger btn-sm" onclick="return confirm(\'Remove?\')">Remove</button>
                </form>
            </div>
            {% else %}<p style="color:var(--text-secondary);">No nav links yet.</p>{% endfor %}
        </div>
    </div>'''
    return R(html, nav_links=nav_links, breadcrumbs=get_breadcrumbs(request.path), active_section='site')


@app.route('/site/social', methods=['GET', 'POST'])
def site_social():
    db.mount()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            platform = request.form.get('social_platform', '').strip()
            url = request.form.get('social_url', '').strip()
            if platform and url:
                db.add_record("SocialLink", {"social_platform": platform, "social_url": url})
        elif action == 'delete':
            platform = request.form.get('social_platform', '')
            db.delete_record("SocialLink", "social_platform", platform)
        db.commit()
        
        flash('Social links updated.', 'success')
        return redirect('/site/social')

    social_links = db.get_records("SocialLink")
    

    html = '''
    <div class="page-header"><h1>Social Media Links</h1><p>Manage your social media profiles</p></div>
    <div class="grid grid-2">
        <div class="card">
            <div class="card-header"><span class="card-title">Add Social Link</span></div>
            <form method="POST">
                <input type="hidden" name="action" value="add">
                <div class="form-group"><label class="form-label">Platform (e.g. Twitter, YouTube)</label><input type="text" name="social_platform" class="form-control" required></div>
                <div class="form-group"><label class="form-label">URL</label><input type="url" name="social_url" class="form-control" required placeholder="https://"></div>
                <button type="submit" class="btn btn-primary">Add</button>
            </form>
        </div>
        <div class="card">
            <div class="card-header"><span class="card-title">Current Social Links</span></div>
            {% for soc in social_links %}
            <div style="display:flex;justify-content:space-between;align-items:center;padding:10px;background:var(--bg-secondary);margin-bottom:5px;border-radius:4px;">
                <span>{{ soc.social_platform }} &rarr; {{ soc.social_url }}</span>
                <form method="POST" style="display:inline;">
                    <input type="hidden" name="action" value="delete">
                    <input type="hidden" name="social_platform" value="{{ soc.social_platform }}">
                    <button type="submit" class="btn btn-danger btn-sm" onclick="return confirm(\'Remove?\')">Remove</button>
                </form>
            </div>
            {% else %}<p style="color:var(--text-secondary);">No social links yet.</p>{% endfor %}
        </div>
    </div>'''
    return R(html, social_links=social_links, breadcrumbs=get_breadcrumbs(request.path), active_section='site')


@app.route('/site/authors', methods=['GET', 'POST'])
def manage_authors():
    db.mount()
    if request.method == 'POST':
        action = request.form.get('action', 'add')
        if action == 'add':
            name = request.form.get('auth_name', '').strip()
            bio  = request.form.get('auth_bio', '')
            img  = request.form.get('auth_img', '')
            if name:
                db.add_record("AuthorProfile", {"auth_name": name, "auth_bio": bio, "auth_img": img})
                db.commit()
                flash(f'Author "{name}" added.', 'success')
        elif action == 'edit':
            name = request.form.get('auth_name', '').strip()
            bio  = request.form.get('auth_bio', '')
            img  = request.form.get('auth_img', '')
            db.update_record("AuthorProfile", "auth_name", name, {"auth_bio": bio, "auth_img": img})
            db.commit()
            flash(f'Author "{name}" updated.', 'success')
        elif action == 'delete':
            name = request.form.get('auth_name', '')
            db.delete_record("AuthorProfile", "auth_name", name)
            db.commit()
            flash('Author deleted.', 'success')
        return redirect('/site/authors')

    authors = db.get_records("AuthorProfile")
    assets  = get_assets()

    html = '''
    <style>
        .author-edit-panel { display:none; margin-top:12px; padding:12px; background:rgba(0,0,0,0.3); border-radius:6px; border:1px solid var(--border); }
    </style>
    <div class="page-header"><h1>Manage Authors</h1><p>Manage author profiles for your site</p></div>
    <div class="grid grid-2">
        <div class="card">
            <div class="card-header"><span class="card-title">Add New Author</span></div>
            <form method="POST">
                <input type="hidden" name="action" value="add">
                <div class="form-group"><label class="form-label">Author Name *</label><input type="text" name="auth_name" class="form-control" required></div>
                <div class="form-group"><label class="form-label">Bio</label><textarea name="auth_bio" class="form-control" rows="3"></textarea></div>
                <div class="form-group"><label class="form-label">Profile Image</label>
                    <select name="auth_img" class="form-control"><option value="">-- No image --</option>{% for a in assets %}<option value="{{ a }}">{{ a }}</option>{% endfor %}</select>
                </div>
                <button type="submit" class="btn btn-primary">Add Author</button>
            </form>
        </div>
        <div class="card">
            <div class="card-header"><span class="card-title">Existing Authors ({{ authors|length }})</span></div>
            {% for auth in authors %}
            {% set aid = auth.auth_name | replace(\' \', \'_\') %}
            <div style="padding:15px;background:var(--bg-secondary);margin-bottom:10px;border-radius:8px;">
                <div style="display:flex;justify-content:space-between;align-items:start;">
                    <div style="display:flex;gap:12px;align-items:center;">
                        {% if auth.auth_img %}
                        <img src="/assets/{{ auth.auth_img }}" style="width:48px;height:48px;border-radius:50%;object-fit:cover;border:2px solid var(--border);">
                        {% else %}
                        <div style="width:48px;height:48px;border-radius:50%;background:var(--border);display:flex;align-items:center;justify-content:center;font-size:1.3rem;">👤</div>
                        {% endif %}
                        <div>
                            <strong>{{ auth.auth_name }}</strong>
                            <p style="margin-top:3px;color:var(--text-secondary);font-size:0.85rem;">{{ auth.auth_bio[:80] if auth.auth_bio else \'No bio\' }}</p>
                        </div>
                    </div>
                    <div style="display:flex;gap:6px;flex-shrink:0;">
                        <button class="btn btn-secondary btn-sm" onclick="toggleEdit(\'{{ aid }}\')" type="button">Edit</button>
                        <form method="POST" style="display:inline;">
                            <input type="hidden" name="action" value="delete">
                            <input type="hidden" name="auth_name" value="{{ auth.auth_name }}">
                            <button type="submit" class="btn btn-danger btn-sm" onclick="return confirm(\'Delete author?\')">Delete</button>
                        </form>
                    </div>
                </div>
                <div id="edit-{{ aid }}" class="author-edit-panel">
                    <form method="POST">
                        <input type="hidden" name="action" value="edit">
                        <input type="hidden" name="auth_name" value="{{ auth.auth_name }}">
                        <div class="form-group"><label class="form-label" style="font-size:0.8rem;">Bio</label>
                            <textarea name="auth_bio" class="form-control" rows="3">{{ auth.auth_bio or \'\'  }}</textarea>
                        </div>
                        <div class="form-group"><label class="form-label" style="font-size:0.8rem;">Profile Image</label>
                            <select name="auth_img" class="form-control">
                                <option value="">-- No image --</option>
                                {% for a in assets %}<option value="{{ a }}" {% if a == auth.auth_img %}selected{% endif %}>{{ a }}</option>{% endfor %}
                            </select>
                        </div>
                        <div style="display:flex;gap:8px;">
                            <button type="submit" class="btn btn-primary btn-sm">Save</button>
                            <button type="button" class="btn btn-secondary btn-sm" onclick="toggleEdit(\'{{ aid }}\')" >Cancel</button>
                        </div>
                    </form>
                </div>
            </div>
            {% else %}<div class="empty-state"><h3>No authors yet</h3></div>{% endfor %}
        </div>
    </div>
    <script>
        function toggleEdit(aid) {
            var el = document.getElementById(\'edit-\' + aid);
            if (el) el.style.display = el.style.display === \'block\' ? \'none\' : \'block\';
        }
    </script>'''
    return R(html, authors=authors, assets=assets, breadcrumbs=get_breadcrumbs(request.path), active_section='site')


# =============================================================================
# ROUTES — AD MANAGER (integrated from BEJSON_Ad_Manager.py)
# =============================================================================

@app.route('/site/ads', methods=['GET', 'POST'])
def manage_ads():
    db.mount()

    if request.method == 'POST':
        action = request.form.get('action', 'add')

        if action == 'add':
            name = request.form.get('ad_name', '').strip()
            link = request.form.get('ad_link', '').strip()
            image = request.form.get('ad_image', '')
            zone = request.form.get('ad_zone', 'header')
            active = request.form.get('ad_active') == 'on'
            if name and image:
                ad_uid = str(uuid.uuid4())
                db.add_record("AdUnit", {
                    "ad_uuid": ad_uid,
                    "ad_name": name,
                    "ad_image": image,
                    "ad_link": link,
                    "ad_zone": zone,
                    "ad_active": active
                })
                db.commit()
                flash(f'Ad "{name}" saved.', 'success')
            else:
                flash('Ad name and image are required.', 'error')

        elif action == 'toggle':
            ad_uid = request.form.get('ad_uuid', '')
            ads = db.get_records("AdUnit")
            ad = next((a for a in ads if a.get('ad_uuid') == ad_uid), None)
            if ad:
                db.update_record("AdUnit", "ad_uuid", ad_uid, {"ad_active": not ad.get('ad_active', True)})
            flash('Ad status toggled.', 'success')

        elif action == 'delete':
            ad_uid = request.form.get('ad_uuid', '')
            db.delete_record("AdUnit", "ad_uuid", ad_uid)
            flash('Ad deleted.', 'success')

        
        return redirect('/site/ads')

    ads = db.get_records("AdUnit")
    assets = get_assets()
    

    html = '''
    <div class="page-header"><h1>Ad Manager</h1><p>Manage advertising units for your site</p></div>
    <div class="grid grid-2">
        <div class="card">
            <div class="card-header"><span class="card-title">Create Ad Unit</span></div>
            <form method="POST">
                <input type="hidden" name="action" value="add">
                <div class="form-group"><label class="form-label">Internal Name *</label><input type="text" name="ad_name" class="form-control" required></div>
                <div class="form-group"><label class="form-label">Target URL</label><input type="url" name="ad_link" class="form-control" placeholder="https://advertiser.com"></div>
                <div class="form-group"><label class="form-label">Image Asset *</label><select name="ad_image" class="form-control" required><option value="">-- Select image --</option>{% for a in assets %}<option value="{{ a }}">{{ a }}</option>{% endfor %}</select></div>
                <div class="form-group"><label class="form-label">Zone</label><select name="ad_zone" class="form-control"><option value="header">Header</option><option value="footer">Footer</option><option value="sidebar">Sidebar</option></select></div>
                <div class="form-group" style="display:flex;align-items:center;gap:10px;"><input type="checkbox" name="ad_active" id="ad_active" checked style="width:auto;"><label for="ad_active" style="margin:0;cursor:pointer;">Active</label></div>
                <button type="submit" class="btn btn-primary">Save Ad Unit</button>
            </form>
        </div>
        <div class="card">
            <div class="card-header"><span class="card-title">Ad Units ({{ ads|length }})</span></div>
            {% if ads %}
            <div class="table-container"><table><thead><tr><th>Name</th><th>Zone</th><th>Status</th><th>Actions</th></tr></thead><tbody>
            {% for ad in ads %}
            <tr>
                <td>
                    {% if ad.ad_image %}<img src="/assets/{{ ad.ad_image }}" style="width:40px;height:30px;object-fit:cover;border-radius:4px;margin-right:8px;vertical-align:middle;">{% endif %}
                    {{ ad.ad_name }}
                </td>
                <td><span class="badge" style="background:var(--bg-secondary);color:var(--text-primary);">{{ ad.ad_zone }}</span></td>
                <td>
                    {% if ad.ad_active %}<span class="badge badge-active">Active</span>{% else %}<span class="badge badge-inactive">Inactive</span>{% endif %}
                </td>
                <td style="display:flex;gap:6px;flex-wrap:wrap;">
                    <form method="POST" style="display:inline;">
                        <input type="hidden" name="action" value="toggle">
                        <input type="hidden" name="ad_uuid" value="{{ ad.ad_uuid }}">
                        <button type="submit" class="btn btn-secondary btn-sm">Toggle</button>
                    </form>
                    <form method="POST" style="display:inline;">
                        <input type="hidden" name="action" value="delete">
                        <input type="hidden" name="ad_uuid" value="{{ ad.ad_uuid }}">
                        <button type="submit" class="btn btn-danger btn-sm" onclick="return confirm(\'Delete ad?\')">Delete</button>
                    </form>
                </td>
            </tr>
            {% endfor %}
            </tbody></table></div>
            {% else %}<div class="empty-state"><h3>No ad units yet</h3><p>Create your first ad unit using the form.</p></div>{% endif %}
        </div>
    </div>
    <div class="card">
        <div class="card-header"><span class="card-title">Ad Zones Summary</span></div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:15px;">
            {% set zones = [\'header\', \'footer\', \'sidebar\'] %}
            {% for zone in zones %}
            {% set zone_ads = ads | selectattr(\'ad_zone\', \'equalto\', zone) | list %}
            {% set active_count = zone_ads | selectattr(\'ad_active\') | list | length %}
            <div style="padding:15px;background:var(--bg-secondary);border-radius:8px;text-align:center;">
                <div style="font-weight:700;text-transform:capitalize;margin-bottom:5px;">{{ zone }}</div>
                <div style="font-size:1.5rem;font-weight:800;color:var(--accent);">{{ zone_ads|length }}</div>
                <div style="font-size:0.8rem;color:var(--text-secondary);">{{ active_count }} active</div>
            </div>
            {% endfor %}
        </div>
    </div>'''
    return R(html, ads=ads, assets=assets, breadcrumbs=get_breadcrumbs(request.path), active_section='site')


# =============================================================================
# ROUTES — PUBLISH
# =============================================================================

@app.route('/publish')
def publish_interface():
    built = os.path.exists(PUBLISH_DIR) and len(os.listdir(PUBLISH_DIR)) > 0
    html = '''
    <div class="page-header"><h1>Publish</h1><p>Export your data for use with BEJSON_Web_Publisher.py</p></div>
    <div class="grid grid-2">
        <div class="card">
            <div class="card-header"><span class="card-title">Export Data</span></div>
            <p style="color:var(--text-secondary);margin-bottom:20px;">Download your BEJSON database and assets for use with the external web publisher.</p>
            <div style="display:flex;flex-direction:column;gap:10px;">
                <a href="/export/db" class="btn btn-primary">&#128190; Download Database</a>
                <a href="/export/assets" class="btn btn-secondary">&#128444; Download Assets ZIP</a>
            </div>
        </div>
        <div class="card">
            <div class="card-header"><span class="card-title">Publish Directory</span></div>
            <p style="color:var(--text-secondary);margin-bottom:10px;">Your web publisher writes output here:</p>
            <code style="display:block;padding:15px;background:var(--bg-secondary);border-radius:6px;word-break:break-all;">{{ publish_dir }}</code>
            {% if built %}<p style="margin-top:10px;color:var(--success);">&#9989; Published site detected</p>{% else %}<p style="margin-top:10px;color:var(--text-secondary);">No published site yet — run BEJSON_Web_Publisher.py</p>{% endif %}
        </div>
    </div>'''
    return R(html, built=built, publish_dir=PUBLISH_DIR,
             breadcrumbs=get_breadcrumbs(request.path), active_section='publish')


@app.route('/export/db')
def export_db():
    if os.path.exists(MANIFEST_PATH):
        return send_file(MANIFEST_PATH, as_attachment=True, download_name='site_master.json')
    return "Database not found", 404


@app.route('/export/assets')
def export_assets():
    zip_path = os.path.join(EXPORTS_DIR, 'assets_export.zip')
    with zipfile.ZipFile(zip_path, 'w') as zf:
        for f in os.listdir(ASSETS_DIR):
            zf.write(os.path.join(ASSETS_DIR, f), f)
    return send_file(zip_path, as_attachment=True, download_name='assets_export.zip')


# =============================================================================
# HTML IMPORT  (merged from HTML_Importer.py)
# =============================================================================

def _strip_word_html(soup):
    """
    Remove Microsoft Word HTML artefacts from a BeautifulSoup tree.
    Targets: o:p tags, MsoXxx classes, mso- inline styles, Word section divs,
    empty paragraphs left by Word, and Word-generated footer boilerplate.
    """
    # Remove <o:p> tags (Word XML namespace leftovers)
    for tag in soup.find_all('o:p'):
        tag.decompose()

    # Remove any tag whose class list contains a "Mso" class
    for tag in soup.find_all(True):
        classes = tag.get('class', [])
        if any('Mso' in c for c in classes):
            tag.unwrap()  # keep inner text, drop the wrapper

    # Remove inline mso- styles but keep the element
    for tag in soup.find_all(True, style=True):
        style = tag.get('style', '')
        if 'mso-' in style:
            # Strip only the mso-* declarations, leave other styles
            cleaned = '; '.join(
                p for p in style.split(';') if 'mso-' not in p.lower()
            ).strip().strip(';')
            if cleaned:
                tag['style'] = cleaned
            else:
                del tag['style']

    # Remove Word section divs
    for tag in soup.find_all('div', id=re.compile(r'WordSection|Section\d', re.I)):
        tag.unwrap()
    for tag in soup.find_all('div', class_=re.compile(r'WordSection|Section\d', re.I)):
        tag.unwrap()

    # Remove footer / boilerplate elements that contain only Word/AI watermark text
    _WATERMARK_PATTERNS = re.compile(
        r'(microsoft\s+word|generated\s+by|created\s+with|renderer:|'
        r'claude\s+ai|gemini\s+ai|openai|chatgpt|copilot)',
        re.I
    )
    for tag in soup.find_all(['footer', 'div', 'p', 'span']):
        text = tag.get_text(strip=True)
        # Only remove short boilerplate nodes (< 200 chars) matching watermark patterns
        if text and len(text) < 200 and _WATERMARK_PATTERNS.search(text):
            # Make sure it doesn't contain meaningful body content
            if not tag.find(['h1', 'h2', 'h3', 'ul', 'ol', 'table']):
                tag.decompose()

    # Remove div.meta watermark containers
    for tag in soup.find_all('div', class_='meta'):
        tag.decompose()

    return soup


def extract_from_html(html_bytes):
    """
    Parse an HTML document and return (title, body_html, preview_text).
    Strips scripts, styles, Word artefacts, and AI watermarks.
    Requires beautifulsoup4; falls back to raw text extraction if unavailable.
    """
    if not _BS4_OK:
        raw = html_bytes.decode('utf-8', errors='replace')
        title = re.search(r'<title[^>]*>(.*?)</title>', raw, re.I | re.S)
        title = title.group(1).strip() if title else 'Imported Page'
        body  = re.sub(r'<[^>]+>', ' ', raw)
        body  = re.sub(r'\s+', ' ', body).strip()
        return title, f'<p>{body[:50000]}</p>', body[:200]

    soup = BeautifulSoup(html_bytes, 'html.parser')

    # --- Title ---
    title_tag = soup.find('title')
    title = title_tag.get_text(strip=True) if title_tag else ''
    if not title:
        h1 = soup.find('h1')
        title = h1.get_text(strip=True) if h1 else 'Imported Page'

    # --- Body ---
    body = soup.find('body') or soup

    # Remove noise elements
    for tag in body.find_all(['script', 'style', 'noscript', 'link', 'meta']):
        tag.decompose()

    # Strip Word HTML artefacts + AI watermarks
    body = _strip_word_html(body)

    body_html = body.decode_contents().strip()

    # Preview text
    preview = re.sub(r'\s+', ' ', body.get_text(separator=' ', strip=True))[:200]

    return title, body_html, preview


def _create_import_page(title, category, body_html, author=''):
    """Register a new PageRecord in the master DB and write the page content file."""
    new_uuid = str(uuid.uuid4())
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')

    db.mount()
    db.add_record("PageRecord", {
        "page_uuid":    new_uuid,
        "page_title":   title,
        "page_slug":    slug,
        "category_ref": category,
        "item_type":    "page",
        "created_at":   datetime.now().strftime("%Y-%m-%d"),
        "external_url": None,
        "author_ref":   author,
        "featured_img": None,
    })
    

    # Write per-page content file
    pfile = os.path.join(PAGES_DB_DIR, f"{new_uuid}.json")
    # Create content file using standardized BEJSON 104db structure
    content_doc = {
        "Format": "BEJSON", "Format_Version": "104db", "Format_Creator": "Elton Boehnen",
        "Records_Type": ["PageMeta", "Content"],
        "Fields": [
            {"name": "Record_Type_Parent", "type": "string"},
            {"name": "meta_title", "type": "string", "Record_Type_Parent": "PageMeta"},
            {"name": "html_body", "type": "string", "Record_Type_Parent": "Content"},
            {"name": "markdown_body", "type": "string", "Record_Type_Parent": "Content"},
            {"name": "source_code", "type": "string", "Record_Type_Parent": "Content"}
        ],
        "Values": [
            ["PageMeta", title, None, None, None],
            ["Content", None, body_html, "", ""]
        ]
    }
    import json
    with open(pfile, "w") as f: json.dump(content_doc, f, indent=2)
    return new_uuid


@app.route('/import', methods=['GET'])
def import_index():
    db.mount()
    cats = db.get_records("Category")
    
    if not cats:
        cats = [{'category_name': 'Uncategorized', 'category_slug': 'uncategorized'}]

    bs4_warn = '' if _BS4_OK else '''
    <div class="alert alert-error" style="margin-bottom:20px;">
      ⚠ <strong>beautifulsoup4</strong> is not installed.
      Install it with <code>pip install beautifulsoup4</code> for full HTML parsing.
      Basic extraction will still work without it.
    </div>'''

    html = f'''
    {bs4_warn}
    <div class="page-header"><h1>HTML Import</h1>
    <p>Upload HTML files and import them as CMS pages. Word artefacts and AI watermarks are stripped automatically.</p></div>
    <form action="/import/preview" method="POST" enctype="multipart/form-data">
      <div class="card">
        <div class="card-header"><span class="card-title">📂 Select HTML Files</span></div>
        <div id="dropZone" onclick="document.getElementById('fileInput').click()"
             style="border:2px dashed var(--border);border-radius:8px;padding:48px 24px;text-align:center;cursor:pointer;transition:.2s;"
             ondragover="event.preventDefault();this.style.borderColor='var(--accent)'"
             ondragleave="this.style.borderColor='var(--border)'"
             ondrop="event.preventDefault();this.style.borderColor='var(--border)';document.getElementById('fileInput').files=event.dataTransfer.files;showFiles(document.getElementById('fileInput'))">
          <div style="font-size:2.5rem;margin-bottom:12px;">📄</div>
          <p style="color:var(--text-secondary);margin-bottom:14px;">Click to browse or drag &amp; drop .html / .htm files</p>
          <input type="file" id="fileInput" name="html_files" multiple accept=".html,.htm"
                 style="display:none" onchange="showFiles(this)">
          <span class="btn btn-secondary">Browse Files</span>
        </div>
        <div id="fileList" style="margin-top:16px;"></div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">⚙️ Import Settings</span></div>
        <div class="grid-2" style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
          <div class="form-group">
            <label class="form-label">Target Category *</label>
            <select name="category" class="form-control" required>
              <option value="" disabled selected>-- Select Target Category --</option>
              {"".join(f'<option value="{c["category_name"]}">{c["category_name"]}</option>' for c in cats)}
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Author (optional)</label>
            <input type="text" name="author" class="form-control" placeholder="Leave blank to skip">
          </div>
        </div>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;">
        <button type="submit" class="btn btn-primary">🔍 Preview &amp; Review →</button>
      </div>
    </form>
    <script>
    function showFiles(inp) {{
      const list = document.getElementById('fileList');
      list.innerHTML = '';
      if (!inp.files.length) return;
      const hdr = document.createElement('p');
      hdr.style = 'font-size:.85rem;color:var(--text-secondary);margin-bottom:8px;font-weight:600;';
      hdr.textContent = inp.files.length + ' file(s) selected:';
      list.appendChild(hdr);
      for (const f of inp.files) {{
        const item = document.createElement('div');
        item.style = 'background:var(--bg-secondary);border:1px solid var(--border);border-radius:8px;padding:14px 18px;margin-bottom:10px;display:flex;align-items:center;gap:14px;';
        item.innerHTML = '<span style="font-size:1.4rem;">📄</span><div><div style="font-weight:600;font-size:.9rem;">' + f.name + '</div><div style="font-size:.78rem;color:var(--text-secondary);">' + (f.size/1024).toFixed(1) + ' KB</div></div>';
        list.appendChild(item);
      }}
    }}
    </script>'''
    return R(html, breadcrumbs=get_breadcrumbs(request.path), active_section='content')


@app.route('/import/preview', methods=['POST'])
def import_preview():
    files    = request.files.getlist('html_files')
    category = request.form.get('category', '').strip()
    author   = request.form.get('author', '').strip()

    if not category:
        flash('Target category is required for import.', 'error')
        return redirect('/import')

    if not files or not files[0].filename:
        flash('Please select at least one HTML file.', 'error')
        return redirect('/import')

    previews = []
    for f in files:
        if not f.filename:
            continue
        fname = secure_filename(f.filename)
        if not fname.lower().endswith(('.html', '.htm')):
            flash(f'{fname} skipped — not an HTML file.', 'error')
            continue
        try:
            raw = f.read()
            # Cap BS4 parsing at 2 MB — larger files freeze Flask's single
            # thread on Android; the full bytes are still saved to disk.
            _MAX_PARSE = 2 * 1024 * 1024
            parse_bytes = raw[:_MAX_PARSE]
            title, _, preview_text = extract_from_html(parse_bytes)
            tmp_path = os.path.join(UPLOAD_TMP, fname)
            with open(tmp_path, 'wb') as fh:
                fh.write(raw)
            previews.append({
                'fname':   fname,
                'title':   title,
                'preview': preview_text,
                'size':    f'{len(raw)/1024:.1f} KB',
            })
        except Exception as e:
            flash(f'Could not parse {f.filename}: {e}', 'error')

    if not previews:
        flash('No valid HTML files found.', 'error')
        return redirect('/import')

    rows = ''
    for p in previews:
        rows += f'''
        <div class="card">
          <div class="card-header"><span class="card-title">📄 {p["fname"]} <span style="font-weight:400;font-size:.8rem;color:var(--text-secondary);">({p["size"]})</span></span></div>
          <input type="hidden" name="fnames" value="{p["fname"]}">
          <div class="grid-2" style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
            <div class="form-group">
              <label class="form-label">Page Title</label>
              <input type="text" name="title_{p["fname"]}" value="{_html_escape.escape(p['title'])}" class="form-control">
            </div>
            <div class="form-group" style="display:flex;align-items:center;gap:12px;padding-top:28px;">
              <input type="checkbox" name="include_{p["fname"]}" id="inc_{p["fname"]}"
                     style="width:20px;height:20px;accent-color:var(--accent);" checked>
              <label for="inc_{p["fname"]}" style="margin:0;font-size:.95rem;">Include this file</label>
            </div>
          </div>
          <div class="form-group">
            <label class="form-label">Content Preview</label>
            <div style="background:var(--bg-secondary);border:1px solid var(--border);border-radius:8px;padding:12px 16px;font-size:.82rem;color:var(--text-secondary);line-height:1.6;font-style:italic;">{_html_escape.escape(p["preview"])}{"…" if len(p["preview"])==200 else ""}</div>
          </div>
        </div>'''

    html = f'''
    <div class="page-header"><h1>Review Import</h1>
    <p>Confirm titles and check which files to import, then click Import All.</p></div>
    <form action="/import/confirm" method="POST">
      <input type="hidden" name="category" value="{category}">
      <input type="hidden" name="author"   value="{author}">
      {rows}
      <div class="card" style="padding:16px 22px;">
        <span style="color:var(--text-secondary);font-size:.85rem;">Category:</span>
        <strong style="margin-left:8px;">{_html_escape.escape(category)}</strong>
        &nbsp;&nbsp;
        <span style="color:var(--text-secondary);font-size:.85rem;">Author:</span>
        <strong style="margin-left:8px;">{_html_escape.escape(author) if author else "—"}</strong>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:4px;">
        <button type="submit" class="btn btn-primary">🚀 Import to CMS</button>
        <a href="/import" class="btn btn-secondary">← Start Over</a>
      </div>
    </form>'''
    return R(html, breadcrumbs=get_breadcrumbs(request.path), active_section='content')


@app.route('/import/confirm', methods=['POST'])
def import_confirm():
    category = request.form.get('category', 'Uncategorized')
    author   = request.form.get('author', '').strip()
    fnames   = request.form.getlist('fnames')

    import_queue = []
    for fname in fnames:
        if not request.form.get(f'include_{fname}'):
            continue
        title = request.form.get(f'title_{fname}', '').strip() or fname
        import_queue.append({'fname': fname, 'title': title})

    if not import_queue:
        flash('No files selected for import.', 'error')
        return redirect('/import')

    html = f'''
    <div class="page-header"><h1>Processing Import Queue</h1>
    <p>Please wait while your files are being imported into the CMS.</p></div>
    
    <div class="card" style="padding:30px;">
        <div id="import-progress-container">
            <div style="display:flex;justify-content:space-between;margin-bottom:10px;">
                <span id="progress-status" style="font-weight:700;color:var(--accent);">Initializing...</span>
                <span id="progress-percent">0%</span>
            </div>
            <div style="height:10px;background:var(--bg-secondary);border-radius:5px;overflow:hidden;margin-bottom:25px;border:1px solid var(--border);">
                <div id="progress-bar" style="height:100%;width:0%;background:var(--accent);transition:width 0.3s ease;"></div>
            </div>
        </div>
        
        <div id="import-log" style="background:var(--bg-secondary);border:1px solid var(--border);border-radius:8px;padding:15px;max-height:300px;overflow-y:auto;font-family:monospace;font-size:.85rem;line-height:1.6;">
            <!-- Process logs will appear here -->
        </div>
        
        <div id="completion-actions" style="display:none;margin-top:30px;gap:10px;">
            <a href="/pages" class="btn btn-primary">View All Pages ↗</a>
            <a href="/import" class="btn btn-secondary">Import More</a>
        </div>
    </div>

    <script>
    const queue = {json.dumps(import_queue)};
    const category = "{_html_escape.escape(category)}";
    const author = "{_html_escape.escape(author)}";
    const log = document.getElementById('import-log');
    const bar = document.getElementById('progress-bar');
    const pct = document.getElementById('progress-percent');
    const status = document.getElementById('progress-status');
    const actions = document.getElementById('completion-actions');

    async function processQueue() {{
        let successCount = 0;
        let failCount = 0;
        
        for(let i=0; i < queue.length; i++) {{
            const item = queue[i];
            const p = Math.round(((i) / queue.length) * 100);
            bar.style.width = p + "%";
            pct.textContent = p + "%";
            status.textContent = "Importing: " + item.title + "...";
            
            const entry = document.createElement('div');
            entry.style.marginBottom = "5px";
            entry.innerHTML = `<span style="color:var(--accent)">[PROCESS]</span> Attempting to import "${{item.title}}"...`;
            log.appendChild(entry);
            log.scrollTop = log.scrollHeight;

            try {{
                const res = await fetch('/api/import/process_item', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        fname: item.fname,
                        title: item.title,
                        category: category,
                        author: author
                    }})
                }});
                const data = await res.json();
                
                if(data.success) {{
                    successCount++;
                    entry.innerHTML = `<span style="color:#10b981">[SUCCESS]</span> Imported "${{item.title}}" successfully.`;
                }} else {{
                    failCount++;
                    entry.innerHTML = `<span style="color:#ef4444">[ERROR]</span> Failed to import "${{item.title}}": ${{data.error}}`;
                }}
            }} catch(e) {{
                failCount++;
                entry.innerHTML = `<span style="color:#ef4444">[CRITICAL]</span> Connection error importing "${{item.title}}": ${{e}}`;
            }}
        }}
        
        bar.style.width = "100%";
        pct.textContent = "100%";
        status.textContent = "Import Complete!";
        status.style.color = "#10b981";
        
        const finalEntry = document.createElement('div');
        finalEntry.style.marginTop = "15px";
        finalEntry.style.fontWeight = "bold";
        finalEntry.style.borderTop = "1px solid var(--border)";
        finalEntry.style.paddingTop = "10px";
        finalEntry.innerHTML = `FINISHED: ${{successCount}} successful, ${{failCount}} failed.`;
        log.appendChild(finalEntry);
        log.scrollTop = log.scrollHeight;
        
        actions.style.display = "flex";
    }}

    document.addEventListener('DOMContentLoaded', processQueue);
    </script>
    '''
    return R(html, breadcrumbs=get_breadcrumbs(request.path), active_section='content')


@app.route('/api/import/process_item', methods=['POST'])
@require_auth
def api_import_process_item():
    data = request.json
    fname = data.get('fname')
    title = data.get('title')
    category = data.get('category')
    author = data.get('author')

    tmp_path = os.path.join(UPLOAD_TMP, fname)
    if not category:
        return jsonify({"success": False, "error": "Category is missing"})
    if not os.path.exists(tmp_path):
        return jsonify({"success": False, "error": "Temporary file missing"})

    try:
        with open(tmp_path, 'rb') as fh:
            raw = fh.read()
        _, body_html, _ = extract_from_html(raw)
        new_uuid = _create_import_page(title, category, body_html, author)
        os.remove(tmp_path)
        return jsonify({"success": True, "uuid": new_uuid})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# =============================================================================
# FACTORY RESET  (merged from Cleanup_Tool.py)
# =============================================================================

@app.route('/reset', methods=['GET'])
def factory_reset():
    html = '''
    <div class="page-header"><h1 style="color:var(--accent);">⚠️ Factory Reset</h1>
    <p>Permanently wipe all CMS data and return the system to a fresh state.</p></div>
    <div class="card" style="max-width:560px;">
      <div class="card-header"><span class="card-title" style="color:#f87171;">This action cannot be undone</span></div>
      <p style="color:var(--text-secondary);line-height:1.9;margin-bottom:20px;">
        This will permanently delete:<br>
        &bull; All pages, articles &amp; categories<br>
        &bull; All images / assets<br>
        &bull; All standalone apps<br>
        &bull; The published static website<br>
        &bull; All ZIP exports
      </p>
      <form method="POST" action="/reset/confirm"
            onsubmit="return confirm('Are you absolutely sure? ALL CMS data will be permanently lost.');">
        <div style="margin-bottom:14px;">
          <label style="color:var(--text-secondary);font-size:.9rem;">Type <strong style="color:var(--accent);">RESET</strong> to confirm:</label><br>
          <input type="text" name="confirm_word" class="form-control" placeholder="RESET" style="margin-top:6px;max-width:200px;" required>
        </div>
        <button class="btn btn-danger">🗑 Wipe Everything</button>
        <a href="/" class="btn btn-secondary" style="margin-left:10px;">Cancel</a>
      </form>
    </div>'''
    return R(html, breadcrumbs=get_breadcrumbs(request.path), active_section='reset')


@app.route('/reset/confirm', methods=['POST'])
def factory_reset_confirm():
    confirm_word = request.form.get('confirm_word', '').strip()
    if confirm_word != 'RESET':
        flash('Reset cancelled — you must type RESET to confirm.', 'error')
        return redirect('/reset')
    errors = []
    for path in [MFDB_DIR, PUBLISH_DIR, EXPORTS_DIR]:
        if os.path.exists(path):
            try:
                shutil.rmtree(path)
            except Exception as e:
                errors.append(str(e))

    # Re-create clean skeleton directories
    for d in [
        os.path.join(MFDB_DIR, "assets"),
        os.path.join(MFDB_DIR, "assets", "thumbs"),
        os.path.join(MFDB_DIR, "Context"),
        os.path.join(MFDB_DIR, "standalone_apps"),
        os.path.join(MFDB_DIR, "pages_db"),
        PUBLISH_DIR,
        EXPORTS_DIR,
        UPLOAD_TMP,
    ]:
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass

    # Re-initialise a fresh master DB
    init_master_db()

    if errors:
        flash('Reset completed with errors: ' + '; '.join(errors), 'error')
    else:
        flash('✅ System reset complete. All data has been wiped and a fresh database created.', 'success')
    return redirect('/')


# =============================================================================
# ERROR HANDLERS
# =============================================================================

@app.errorhandler(404)
def not_found(e):
    html = '''<div class="empty-state"><h1 style="font-size:4rem;color:var(--accent);">404</h1><h3>Page not found</h3><p>The page you\'re looking for doesn\'t exist.</p><br><a href="/" class="btn btn-primary">Go Home</a></div>'''
    return R(html, breadcrumbs=[{'label': '404', 'href': None}], active_section=''), 404


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    print(f'''
    ============================================
    BEJSON Web Manager v17.1 (Flask)
    ============================================
    Data Directory: {MFDB_DIR}
    Assets Directory: {ASSETS_DIR}
    Publish Directory: {PUBLISH_DIR}

    NEW IN v18.0:
    - Finalized CMS update — bumped all versions to 18.0.
    - Synchronized latest BEJSON libraries (v2.x) back to production mirror.

    NEW IN v17.1:
    - Fixed Category 'bool' subscript error — write ops now use _load_entity_doc
    - Fixed factory reset Internal Server Error — full skeleton rebuild
    NEW IN v17.0:
    - All src/lib/ updated to BEJSON Library v2.0.x
      (lib_bejson_path_guard.py added)
    - Fixed: image upload freeze — thumbnail thread delayed
      2 s to prevent Android storage I/O contention
    - Fixed: HTML import preview freeze — BS4 parse input
      capped at 2 MB; full file still saved to disk

    Starting server on http://localhost:5001
    Press CTRL+C to stop
    ============================================
    ''')
    app.run(host='127.0.0.1', port=5001, debug=os.getenv('FLASK_DEBUG','0')=='1', threaded=True, use_reloader=False)
