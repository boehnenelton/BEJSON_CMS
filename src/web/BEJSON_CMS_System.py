"""
Library:         BEJSON_CMS_System
Family:          BEJSON_CMS
Description:     System Cube (Foundation): self-heal/seed lifecycle (init_master_db, _ensure_uncategorized_category, _migrate_db, _seed_default_brand_and_author), Site Config, DB/asset export, Factory Reset. Imports _make_thumbnail from BEJSON_CMS_Media to regenerate the default brand thumbnail during seeding/reset.
Version:         18.23
Library_Version: 57
Date:            2026-08-05
RELATIONAL_ID:   d9d9ce8f-ab86-4ea4-8f20-bfc4d35bd956
"""

import os
import json
import shutil
import zipfile
from datetime import datetime
from flask import Blueprint, request, redirect, flash, send_file

from BEJSON_CMS_Shared import (
    db, R, get_breadcrumbs, require_auth,
    MANIFEST_PATH, MFDB_DIR, PAGES_DB_DIR, ASSETS_DIR, APPS_STORAGE,
    EXPORTS_DIR, PUBLISH_DIR, UPLOAD_TMP, DEFAULT_FEATURED_IMAGE, SCRIPT_PATH,
    PROJECT_ROOT,
)
from BEJSON_CMS_Media import _make_thumbnail, _get_file_hash, _THUMBABLE_EXT
import lib_bejson_Core_mfdb_core as MFDBCore

system_cube = Blueprint('system', __name__)

# ─── Self-heal / seed lifecycle ─────────────────────────────────────────────
def init_master_db():
    if MANIFEST_PATH.exists():
        return
    print("[CMS] Master MFDB manifest not found — bootstrapping site_master database...")
    site_master_dir = MANIFEST_PATH.parent
    entities = [
        {
            "name": "Category",
            "primary_key": "cat_slug",
            "fields": [
                {"name": "cat_name", "type": "string"},
                {"name": "cat_slug", "type": "string"},
            ],
        },
        {
            "name": "PageRecord",
            "primary_key": "page_uuid",
            "fields": [
                {"name": "page_uuid",    "type": "string"},
                {"name": "page_title",   "type": "string"},
                {"name": "page_slug",    "type": "string"},
                {"name": "page_cat_name", "type": "string"},
                {"name": "page_type",    "type": "string"},
                {"name": "page_created_at",   "type": "string"},
                {"name": "page_external_url", "type": "string"},
                {"name": "page_author_name",   "type": "string"},
                {"name": "page_featured_img", "type": "string"},
                {"name": "page_template_key", "type": "string"},
            ],
        },
        {
            "name": "StandaloneApp",
            "primary_key": "app_uuid",
            "fields": [
                {"name": "app_uuid",   "type": "string"},
                {"name": "app_name",   "type": "string"},
                {"name": "app_slug",   "type": "string"},
                {"name": "app_description",   "type": "string"},
                {"name": "app_entry_file", "type": "string"},
                {"name": "app_featured_img",  "type": "string"},
            ],
        },
        {
            "name": "AuthorProfile",
            "primary_key": "author_display_name",
            "fields": [
                {"name": "author_display_name", "type": "string"},
                {"name": "author_bio",  "type": "string"},
                {"name": "author_avatar_url",  "type": "string"},
            ],
        },
        {
            "name": "AdUnit",
            "primary_key": "ad_uuid",
            "fields": [
                {"name": "ad_uuid",   "type": "string"},
                {"name": "ad_name",   "type": "string"},
                {"name": "ad_banner_url",  "type": "string"},
                {"name": "ad_target_url",   "type": "string"},
                {"name": "ad_zone",   "type": "string"},
                {"name": "ad_active", "type": "boolean"},
            ],
        },
        {
            "name": "SiteConfig",
            "primary_key": "sys_key",
            "fields": [
                {"name": "sys_key",   "type": "string"},
                {"name": "sys_value", "type": "string"},
            ],
        },
        {
            "name": "SocialLink",
            "primary_key": "social_platform_name",
            "fields": [
                {"name": "social_platform_name", "type": "string"},
                {"name": "social_target_url",      "type": "string"},
            ],
        },
        {
            "name": "NavLink",
            "primary_key": "nav_display_label",
            "fields": [
                {"name": "nav_display_label", "type": "string"},
                {"name": "nav_target_url",   "type": "string"},
            ],
        },
        {
            # BUG FIX: BEJSON_CMS_ProfileManager.py (Persona Hub, port 5004)
            # uses this entity for every one of its operations, but it was
            # never registered anywhere -- the entire app was silently
            # non-functional (every list/save call failed inside CMSCore's
            # own error handling and returned an empty result, with no
            # visible error to the person using it). Field names kept
            # exactly as ProfileManager.py already expects them (PascalCase,
            # inconsistent with this project's snake_case convention
            # elsewhere) rather than also renaming them, since fixing the
            # "entity doesn't exist" bug doesn't require also touching the
            # working display/save code's naming style.
            #
            # Expanded to the full 23-field canonical schema (matching
            # BEProfiler.py's BEJSON_FIELDS exactly) rather than just the 8
            # fields ProfileManager.py's minimal UI writes -- lib_cms_
            # persona_writer.py's assemble_system_instruction() already
            # reads Tone and CodeParsing_Languages, which didn't exist
            # before this. ProfileManager.py's save() now fills safe
            # defaults for every field it doesn't have its own UI control
            # for yet, so nothing reading the full schema breaks.
            "name": "AI_Profile",
            "primary_key": "Name",
            "fields": [
                {"name": "Record_Type_Parent",              "type": "string"},
                {"name": "Name",                            "type": "string"},
                {"name": "Archetype",                       "type": "string"},
                {"name": "Persona",                         "type": "string"},
                {"name": "SystemInstruction",               "type": "string"},
                {"name": "Active",                          "type": "boolean"},
                {"name": "MaxResponseTokens",               "type": "integer"},
                {"name": "Creativity",                      "type": "number"},
                {"name": "Tone",                            "type": "array"},
                {"name": "Formality",                       "type": "string"},
                {"name": "Verbosity",                       "type": "string"},
                {"name": "EmotionalExpression_Enabled",     "type": "boolean"},
                {"name": "EmotionalExpression_Intensity",   "type": "number"},
                {"name": "GoogleSearch_Enabled",            "type": "boolean"},
                {"name": "CodeInterpreter_Enabled",         "type": "boolean"},
                {"name": "EphemeralMemory",                 "type": "boolean"},
                {"name": "CodeParsing_Mode",                "type": "string"},
                {"name": "CodeParsing_Languages",           "type": "array"},
                {"name": "CodeParsing_StructureValidation", "type": "boolean"},
                {"name": "CodeParsing_VersionControl",      "type": "boolean"},
                {"name": "Thinking_Supported",              "type": "boolean"},
                {"name": "ForbiddenTopics",                 "type": "array"},
                {"name": "Avatar_Type",                     "type": "string"},
                {"name": "Avatar_sourceUrl",                "type": "string"},
                {"name": "Avatar_Data",                     "type": "string"},
            ],
        },
        {
            "name": "PageVideoMetadata",
            "primary_key": "video_meta_uuid",
            "fields": [
                {"name": "video_meta_uuid",      "type": "string"},
                {"name": "page_uuid",            "type": "string"},
                {"name": "video_embed_url",      "type": "string"},
                {"name": "video_duration",       "type": "string"},
                {"name": "video_provider",       "type": "string"},
                {"name": "video_transcript_uuid","type": "string"},
            ],
        },
        {
            "name": "PageDocumentMetadata",
            "primary_key": "doc_meta_uuid",
            "fields": [
                {"name": "doc_meta_uuid",        "type": "string"},
                {"name": "page_uuid",            "type": "string"},
                {"name": "doc_asset_uuid",       "type": "string"},
                {"name": "doc_version",          "type": "string"},
                {"name": "doc_file_size",        "type": "integer"},
                {"name": "doc_download_rules",   "type": "string"},
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
        str(MANIFEST_PATH), "Category", ["Uncategorized", "uncategorized"]
    )
    print("[CMS] site_master bootstrapped successfully.")


def _ensure_uncategorized_category():
    """Self-heal: guarantee 'Uncategorized' always exists as a real,
    permanent Category record — not merely a UI fallback shown only when
    the category list is completely empty. Root cause of the "no way to
    leave something uncategorized" bug: Uncategorized only ever appeared
    via an empty-list fallback in a couple of routes; the instant ANY real
    category existed, that fallback stopped firing and there was no
    neutral option left in the (required) category dropdowns at all.
    Runs on every startup, so it also repairs existing/older databases,
    not just freshly-created ones."""
    try:
        Existing_Category_Records = db.get_records("Category")
        if not any(c.get('cat_name') == 'Uncategorized' for c in Existing_Category_Records):
            db.add_record("Category", {"cat_name": "Uncategorized", "cat_slug": "uncategorized"})
    except Exception as e:
        print(f"[CMS] Failed to self-heal Uncategorized category: {e}")

# Matches cms-manage.py's _BOOTSTRAP_SITE_CONFIG exactly, so the web reset
# and the CLI reset produce an identical SiteConfig starting state instead
# of diverging (external audit H-2: the web reset never seeded SiteConfig
# at all, so a fresh web-reset install published with hardcoded fallback
# title/description/base_url instead of real, editable values).
DEFAULT_SITE_CONFIG = {
    "title": "My BEJSON Site",
    "description": "A BEJSON CMS powered site",
    "creator": "Admin",
    "base_url": "https://example.com",
}

def _seed_default_site_config():
    """Guarantee the SiteConfig keys Publisher/Admin expect always exist,
    even immediately after a factory reset. Idempotent: only adds keys that
    don't already exist, never overwrites a value the user has actually
    set."""
    try:
        existing_keys = {c.get('sys_key') for c in db.get_records("SiteConfig")}
        for key, value in DEFAULT_SITE_CONFIG.items():
            if key not in existing_keys:
                db.add_record("SiteConfig", {"sys_key": key, "sys_value": value})
    except Exception as e:
        print(f"[CMS] Failed to seed default SiteConfig: {e}")

DEFAULT_BRAND_ASSETS_DIR = PROJECT_ROOT / "resources" / "default_brand_assets"
DEFAULT_AUTHOR_NAME = "boehnenelton2024"

def _seed_default_brand_and_author():
    """Guarantees the BEJSON brand assets, the boehnenelton2024 author
    profile, and a 'BEJSON' category all exist — even immediately after a
    factory reset, which wipes ASSETS_DIR and the whole database. Bundled
    source images live in resources/default_brand_assets/ (shipped with the
    app, outside the wipeable storage tree) and get re-copied + re-registered
    every time this runs. Idempotent: safe to call on every startup and
    after every reset — skips anything already present rather than
    duplicating it."""
    try:
        db.mount()

        cats = db.get_records("Category")
        if not any(c.get('cat_name') == 'BEJSON' for c in cats):
            db.add_record("Category", {"cat_name": "BEJSON", "cat_slug": "bejson"})

        seeded_filenames = []
        if DEFAULT_BRAND_ASSETS_DIR.exists():
            existing_assets = db.get_records("MediaAsset")
            existing_hashes = {a.get('asset_file_hash') for a in existing_assets if a.get('asset_file_hash')}
            existing_filenames = {a.get('asset_filename') for a in existing_assets}
            added_any = False
            for src in sorted(DEFAULT_BRAND_ASSETS_DIR.iterdir()):
                if not src.is_file():
                    continue
                Brand_Asset_Copy_Destination = ASSETS_DIR / src.name
                if not Brand_Asset_Copy_Destination.exists():
                    shutil.copy2(str(src), str(Brand_Asset_Copy_Destination))
                seeded_filenames.append(src.name)
                if src.name in existing_filenames:
                    continue  # already registered from a prior run
                file_hash = _get_file_hash(Brand_Asset_Copy_Destination)
                if file_hash in existing_hashes:
                    continue  # identical content already registered under a different name
                db.add_record("MediaAsset", {
                    "asset_filename": src.name,
                    "asset_original_name": src.name,
                    "asset_file_hash": file_hash,
                    "asset_file_size": Brand_Asset_Copy_Destination.stat().st_size,
                    "asset_mime_type": "image/webp" if src.suffix.lower() == ".webp" else "image/jpeg",
                    "asset_uploaded_at": datetime.utcnow().isoformat(),
                }, sync_count=False)
                existing_hashes.add(file_hash)
                existing_filenames.add(src.name)
                added_any = True
                if src.suffix.lower() in _THUMBABLE_EXT:
                    _make_thumbnail(src.name)
            if added_any:
                db.sync_manifest_count("MediaAsset")

        authors = db.get_records("AuthorProfile")
        if not any(a.get('author_display_name') == DEFAULT_AUTHOR_NAME for a in authors):
            default_avatar = "bejson_brand_3_icon.jpeg" if "bejson_brand_3_icon.jpeg" in seeded_filenames else (seeded_filenames[0] if seeded_filenames else "")
            db.add_record("AuthorProfile", {
                "author_display_name": DEFAULT_AUTHOR_NAME,
                "author_bio": "",
                "author_avatar_url": default_avatar,
            })
    except Exception as e:
        print(f"[CMS] Failed to seed default brand/author content: {e}")

# NOTE: the actual call to _seed_default_brand_and_author() happens further
# down, after the Media Library helpers it depends on (_get_file_hash,
# _make_thumbnail) are defined - see that section. Calling it here would
# silently fail every time (NameError, caught by the try/except above),
# which is exactly what was happening before this was found and fixed.


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
            "primary_key": "nav_display_label",
            "fields": [
                {"name": "nav_display_label", "type": "string"},
                {"name": "nav_target_url",   "type": "string"},
            ],
        },
        {
            "name": "MediaAsset",
            "primary_key": "asset_filename",
            "fields": [
                {"name": "asset_filename",      "type": "string"},
                {"name": "asset_original_name", "type": "string"},
                {"name": "asset_file_hash",     "type": "string"},
                {"name": "asset_file_size",     "type": "integer"},
                {"name": "asset_mime_type",     "type": "string"},
                {"name": "asset_uploaded_at",   "type": "string"},
            ],
        },
        {
            "name": "ExternalMedia",
            "primary_key": "extmedia_uuid",
            "fields": [
                {"name": "extmedia_uuid", "type": "string"},
                {"name": "extmedia_name", "type": "string"},
                {"name": "extmedia_type", "type": "string"},
                {"name": "extmedia_url",  "type": "string"},
                {"name": "extmedia_created_at", "type": "string"},
            ],
        },
        {
            "name": "AI_Profile",
            "primary_key": "Name",
            "fields": [
                {"name": "Record_Type_Parent",              "type": "string"},
                {"name": "Name",                            "type": "string"},
                {"name": "Archetype",                       "type": "string"},
                {"name": "Persona",                         "type": "string"},
                {"name": "SystemInstruction",               "type": "string"},
                {"name": "Active",                          "type": "boolean"},
                {"name": "MaxResponseTokens",               "type": "integer"},
                {"name": "Creativity",                      "type": "number"},
                {"name": "Tone",                            "type": "array"},
                {"name": "Formality",                       "type": "string"},
                {"name": "Verbosity",                       "type": "string"},
                {"name": "EmotionalExpression_Enabled",     "type": "boolean"},
                {"name": "EmotionalExpression_Intensity",   "type": "number"},
                {"name": "GoogleSearch_Enabled",            "type": "boolean"},
                {"name": "CodeInterpreter_Enabled",         "type": "boolean"},
                {"name": "EphemeralMemory",                 "type": "boolean"},
                {"name": "CodeParsing_Mode",                "type": "string"},
                {"name": "CodeParsing_Languages",           "type": "array"},
                {"name": "CodeParsing_StructureValidation", "type": "boolean"},
                {"name": "CodeParsing_VersionControl",      "type": "boolean"},
                {"name": "Thinking_Supported",              "type": "boolean"},
                {"name": "ForbiddenTopics",                 "type": "array"},
                {"name": "Avatar_Type",                     "type": "string"},
                {"name": "Avatar_sourceUrl",                "type": "string"},
                {"name": "Avatar_Data",                     "type": "string"},
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

        # FIELD-level migration: an entity that already exists may still be
        # missing fields added to its schema in a later version (the loop
        # above only handles "entity doesn't exist yet"). AI_Profile grew
        # from 8 to 25 fields after Persona Hub's connection to author
        # profiles / AI generation was wired up -- any AI_Profile entity
        # file already on disk from before that needs the new field names
        # appended to its own Fields list AND every existing row backfilled
        # with None for the new columns, or reading those new fields via
        # field-map indexing would throw IndexError on old rows. Always
        # APPEND new fields at the end, never reorder -- BEJSON is
        # positional.
        field_migrated = []
        for spec in REQUIRED:
            name = spec["name"]
            if name not in existing:
                continue  # just-created above, already has every field
            entity_row = next((v for v in manifest["Values"] if v[0] == name), None)
            if not entity_row:
                continue
            fp_rel = entity_row[1]
            abs_path = os.path.join(site_dir, fp_rel)
            if not os.path.exists(abs_path):
                continue
            with open(abs_path, 'r', encoding='utf-8') as fh:
                entity_doc = json.load(fh)
            current_field_names = [f["name"] for f in entity_doc.get("Fields", [])]
            missing_fields = [f for f in spec["fields"] if f["name"] not in current_field_names]
            if not missing_fields:
                continue
            entity_doc["Fields"] = entity_doc.get("Fields", []) + missing_fields
            entity_doc["Values"] = [row + [None] * len(missing_fields) for row in entity_doc.get("Values", [])]
            tmp = abs_path + ".tmp"
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump(entity_doc, fh, indent=2)
            os.replace(tmp, abs_path)
            field_migrated.append(f"{name}(+{len(missing_fields)} fields)")

        if field_migrated:
            print(f"[CMS] Migration: backfilled fields on existing entities {field_migrated}")

        if added:
            Manifest_Temp_Write_Path = str(MANIFEST_PATH) + ".tmp"
            with open(Manifest_Temp_Write_Path, 'w', encoding='utf-8') as fh:
                json.dump(manifest, fh, indent=2)
            os.replace(Manifest_Temp_Write_Path, MANIFEST_PATH)
            print(f"[CMS] Migration: added missing entities {added}")

    except Exception as exc:
        print(f"[CMS] Migration warning (non-fatal): {exc}")


# ─── Routes ──────────────────────────────────────────────────────────────────
@system_cube.route("/site", methods=["GET", "POST"])
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
            match = next((r for r in existing if r.get("sys_key") == k), None)
            if match:
                db.update_record("SiteConfig", "sys_key", k, {"sys_value": v})
            else:
                db.add_record("SiteConfig", {"sys_key": k, "sys_value": v})
                
        flash("Configuration saved!", "success")
        return redirect("/site")

    configs = {}
    for r in db.get_records("SiteConfig"):
        configs[r.get('sys_key', '')] = r.get('sys_value', '')
    

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


@system_cube.route('/export/db')
def export_db():
    if os.path.exists(MANIFEST_PATH):
        return send_file(MANIFEST_PATH, as_attachment=True, download_name='site_master.json')
    return "Database not found", 404


@system_cube.route('/export/assets')
def export_assets():
    zip_path = os.path.join(EXPORTS_DIR, 'assets_export.zip')
    with zipfile.ZipFile(zip_path, 'w') as zf:
        for f in os.listdir(ASSETS_DIR):
            zf.write(os.path.join(ASSETS_DIR, f), f)
    return send_file(zip_path, as_attachment=True, download_name='assets_export.zip')


@system_cube.route('/reset', methods=['GET'])
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


@system_cube.route('/reset/confirm', methods=['POST'])
def factory_reset_confirm():
    confirm_word = request.form.get('confirm_word', '').strip()
    if confirm_word != 'RESET':
        flash('Reset cancelled — you must type RESET to confirm.', 'error')
        return redirect('/reset')
    errors = []
    for path in [MFDB_DIR, PUBLISH_DIR, EXPORTS_DIR, UPLOAD_TMP]:
        if os.path.exists(path):
            try:
                shutil.rmtree(path)
            except Exception as e:
                errors.append(str(e))

    # Re-create clean skeleton directories
    for d in [
        os.path.join(MFDB_DIR, "assets"),
        os.path.join(MFDB_DIR, "assets", "_thumbs"),
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
    _migrate_db()
    _ensure_uncategorized_category()
    _seed_default_site_config()
    _seed_default_brand_and_author()

    if errors:
        flash('Reset completed with errors: ' + '; '.join(errors), 'error')
    else:
        flash('✅ System reset complete. All data has been wiped and a fresh database created.', 'success')
    return redirect('/')


# ─── Run lifecycle in original order: init -> migrate -> self-heal -> seed ──
init_master_db()
_migrate_db()
_ensure_uncategorized_category()
_seed_default_site_config()
_seed_default_brand_and_author()
