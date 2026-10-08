"""
Library:         BEJSON_CMS_System
Family:          BEJSON_CMS
Description:     System Cube (Foundation): self-heal/seed lifecycle (init_master_db, _ensure_uncategorized_category, _migrate_db, _seed_default_brand_and_author), Site Config, DB/asset export, Factory Reset. Imports _make_thumbnail from BEJSON_CMS_Media to regenerate the default brand thumbnail during seeding/reset.
Version:         18.27
Library_Version: 57
Date:            2026-09-20
RELATIONAL_ID:   842ad706-0538-4835-9c6c-5ec05b6b93bd
CHANGE (2026-09-20): PKG139 -- deferred-item sweep decisions (Elton: "add
app_created_at field" -- audit L-4). Added app_created_at to
StandaloneApp's schema in init_master_db(), plus a dedicated self-heal
step in _migrate_db() that backfills EXISTING apps with the migration
run's own timestamp -- unlike the uuid self-heals elsewhere in this file,
a single shared value across every pre-existing row is honest here, not
wrong: there's no recoverable true creation date for an app that predates
this field, so "the date we started tracking it" is the correct semantics
for every one of them, not a per-row-distinct value that would falsely
imply precision that doesn't exist. BEJSON_CMS_Publisher.py already read
this field defensively (sa.get("app_created_at", <build-date fallback>)),
so nothing there needed to change -- it just had nothing to read until
new/backfilled data existed. Verified in an isolated sandbox before
trusting it: two synthetic pre-existing apps both correctly got the SAME
backfilled timestamp (the correct behavior here, unlike the uuid case).
CHANGE (2026-09-16): PKG137 -- extended "give them all uuids" to PageRecord's
FK-by-name fields (Elton: "keep making everything uuid based"). Added
page_cat_uuid/page_author_uuid -- kept IN SYNC alongside the existing
page_cat_name/page_author_name on every write, not replacing them:
deliberately additive so no render/permalink/related-content path that
already reads the name fields needed to change (that conversion is still a
separate, larger decision, not made this pass). Schema added to both
init_master_db() and _migrate_db()'s REQUIRED list. Added a dedicated
self-heal resolver in _migrate_db() that backfills these two fields on
existing pages by RESOLVING their current name against live Category/
AuthorProfile -- not the generic FIELD-level migration loop, which
backfills with one shared None for every row (wrong here: two pages in two
different categories both getting None would look like a shared identity
they don't have). A page whose name doesn't resolve to any live record
correctly gets None -- that's the same orphan case `cms-manage.py doctor`
already checks for, not a bug in the resolver. Verified in an isolated
sandbox with synthetic data before trusting it: a page with a real,
matching category/author resolved to the exact right UUIDs; a page with
made-up names correctly got None for both, not a false match.

While rewriting this REQUIRED list also found and fixed a leftover from
pkg135: NavLink/MediaAsset/AI_Profile's entries in _migrate_db() (as
opposed to init_master_db()) still had their pre-pkg135 field lists and
primary_key values -- harmless today since these entities already exist in
any real manifest, so this branch of _migrate_db() was never actually
reached for them, but a real latent inconsistency between the two schema
definitions this file maintains. Fixed to match.
CHANGE (2026-09-13): PKG135 -- "give them all uuids" (Elton). Category,
AuthorProfile, MediaAsset, NavLink, SiteConfig, SocialLink, AI_Profile all
got a real UUID field for the first time (via tools/migrate_taxonomy.py,
run live against real data, backed up first). This file: added the new
uuid field + updated primary_key for all 7 entities in both
init_master_db() (fresh-bootstrap schema) and the field lists reused by
_migrate_db(); added a NEW, dedicated per-row UUID self-heal step to
_migrate_db() (driven by lib_bejson_CMS_taxonomy.py's registry, one source
of truth) -- deliberately NOT folded into the existing generic FIELD-level
migration loop, which backfills missing fields with a single shared `None`
for every row: correct for an ordinary new field, wrong for a UUID, where
every row needs its own distinct value. Verified live in a throwaway
sandbox copy of real data with the UUID field stripped back out: two
existing rows got two distinct real UUIDs, not a shared None. Also added
the uuid field to every add_record() call in this file that creates a
Category/AuthorProfile/MediaAsset/SiteConfig row (4 seeding sites) --
these were missed on a first pass and would otherwise have written
`_uuid: None` into new rows, defeating the entire point.
CHANGE (2026-09-12): PKG133 -- external audit remediation (M-5). site_config()'s
POST handler wrote a "site_name" SiteConfig row on every save, byte-identical
to "title" -- no code path anywhere read "site_name" (Publisher reads "title",
per pkg125 M-3), so it was dead data silently accumulating on every save.
Removed. (H-1, the AI_Profile manifest primary_key drift, was a one-cell fix
in storage/mfdb/site_master/104a.mfdb.bejson itself -- this file's own
init_master_db()/_migrate_db() REQUIRED specs already correctly declared
"primary_key": "persona_name"; only the manifest's live Values row was stale.)
"""

import os
import mimetypes
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
import lib_bejson_CMS_taxonomy as Taxonomy
import uuid as _uuid

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
            "primary_key": "cat_uuid",
            "fields": [
                {"name": "cat_uuid", "type": "string"},
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
                {"name": "page_featured_video_url", "type": "string"},
                {"name": "page_cat_uuid",    "type": "string"},
                {"name": "page_author_uuid", "type": "string"},
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
                {"name": "app_created_at", "type": "string"},
            ],
        },
        {
            "name": "AuthorProfile",
            "primary_key": "author_uuid",
            "fields": [
                {"name": "author_uuid", "type": "string"},
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
            "primary_key": "sys_uuid",
            "fields": [
                {"name": "sys_uuid",  "type": "string"},
                {"name": "sys_key",   "type": "string"},
                {"name": "sys_value", "type": "string"},
            ],
        },
        {
            "name": "SocialLink",
            "primary_key": "social_uuid",
            "fields": [
                {"name": "social_uuid", "type": "string"},
                {"name": "social_platform_name", "type": "string"},
                {"name": "social_target_url",      "type": "string"},
            ],
        },
        {
            "name": "NavLink",
            "primary_key": "nav_uuid",
            "fields": [
                {"name": "nav_uuid", "type": "string"},
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
            "primary_key": "persona_uuid",
            "fields": [
                {"name": "persona_uuid",                  "type": "string"},
                {"name": "persona_record_type",           "type": "string"},
                {"name": "persona_name",                  "type": "string"},
                {"name": "persona_archetype",              "type": "string"},
                {"name": "persona_bio",                    "type": "string"},
                {"name": "persona_system_instruction",     "type": "string"},
                {"name": "persona_active",                 "type": "boolean"},
                {"name": "persona_max_tokens",             "type": "integer"},
                {"name": "persona_creativity",             "type": "number"},
                {"name": "persona_tone",                   "type": "array"},
                {"name": "persona_formality",              "type": "string"},
                {"name": "persona_verbosity",               "type": "string"},
                {"name": "persona_emotion_enabled",         "type": "boolean"},
                {"name": "persona_emotion_intensity",       "type": "number"},
                {"name": "persona_google_search_enabled",   "type": "boolean"},
                {"name": "persona_code_interpreter_enabled","type": "boolean"},
                {"name": "persona_ephemeral_memory",        "type": "boolean"},
                {"name": "persona_code_parsing_mode",       "type": "string"},
                {"name": "persona_code_parsing_languages",  "type": "array"},
                {"name": "persona_code_structure_validation","type": "boolean"},
                {"name": "persona_code_version_control",    "type": "boolean"},
                {"name": "persona_thinking_supported",      "type": "boolean"},
                {"name": "persona_forbidden_topics",        "type": "array"},
                {"name": "persona_avatar_type",             "type": "string"},
                {"name": "persona_avatar_source_url",       "type": "string"},
                {"name": "persona_avatar_data",             "type": "string"},
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
        {
            "name": "MediaAsset",
            "primary_key": "asset_uuid",
            "fields": [
                {"name": "asset_uuid",          "type": "string"},
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
            db.add_record("Category", {"cat_uuid": str(_uuid.uuid4()), "cat_name": "Uncategorized", "cat_slug": "uncategorized"})
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
                db.add_record("SiteConfig", {"sys_uuid": str(_uuid.uuid4()), "sys_key": key, "sys_value": value})
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
            db.add_record("Category", {"cat_uuid": str(_uuid.uuid4()), "cat_name": "BEJSON", "cat_slug": "bejson"})

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
                    "asset_uuid": str(_uuid.uuid4()),
                    "asset_filename": src.name,
                    "asset_original_name": src.name,
                    "asset_file_hash": file_hash,
                    "asset_file_size": Brand_Asset_Copy_Destination.stat().st_size,
                    "asset_mime_type": mimetypes.guess_type(src.name)[0] or "application/octet-stream",
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
                "author_uuid": str(_uuid.uuid4()),
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
                {"name": "page_featured_video_url", "type": "string"},
                {"name": "page_cat_uuid",    "type": "string"},
                {"name": "page_author_uuid", "type": "string"},
            ],
        },
        {
            "name": "NavLink",
            "primary_key": "nav_uuid",
            "fields": [
                {"name": "nav_uuid", "type": "string"},
                {"name": "nav_display_label", "type": "string"},
                {"name": "nav_target_url",   "type": "string"},
            ],
        },
        {
            "name": "MediaAsset",
            "primary_key": "asset_uuid",
            "fields": [
                {"name": "asset_uuid",          "type": "string"},
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
            "primary_key": "persona_uuid",
            "fields": [
                {"name": "persona_uuid",                  "type": "string"},
                {"name": "persona_record_type",           "type": "string"},
                {"name": "persona_name",                  "type": "string"},
                {"name": "persona_archetype",              "type": "string"},
                {"name": "persona_bio",                    "type": "string"},
                {"name": "persona_system_instruction",     "type": "string"},
                {"name": "persona_active",                 "type": "boolean"},
                {"name": "persona_max_tokens",             "type": "integer"},
                {"name": "persona_creativity",             "type": "number"},
                {"name": "persona_tone",                   "type": "array"},
                {"name": "persona_formality",              "type": "string"},
                {"name": "persona_verbosity",               "type": "string"},
                {"name": "persona_emotion_enabled",         "type": "boolean"},
                {"name": "persona_emotion_intensity",       "type": "number"},
                {"name": "persona_google_search_enabled",   "type": "boolean"},
                {"name": "persona_code_interpreter_enabled","type": "boolean"},
                {"name": "persona_ephemeral_memory",        "type": "boolean"},
                {"name": "persona_code_parsing_mode",       "type": "string"},
                {"name": "persona_code_parsing_languages",  "type": "array"},
                {"name": "persona_code_structure_validation","type": "boolean"},
                {"name": "persona_code_version_control",    "type": "boolean"},
                {"name": "persona_thinking_supported",      "type": "boolean"},
                {"name": "persona_forbidden_topics",        "type": "array"},
                {"name": "persona_avatar_type",             "type": "string"},
                {"name": "persona_avatar_source_url",       "type": "string"},
                {"name": "persona_avatar_data",             "type": "string"},
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

        # UUID self-heal (pkg135, "give them all uuids"): 7 entities
        # (Category, AuthorProfile, MediaAsset, NavLink, SiteConfig,
        # SocialLink, AI_Profile) were name-keyed with no UUID field at all
        # until this pass. The live data for THIS project was already
        # migrated directly via tools/migrate_taxonomy.py, but any other
        # deployment of this codebase (an older checkout, a fresh clone that
        # skipped the manual migration step) would still have pre-UUID data
        # on next boot -- this makes that self-healing rather than a one-time
        # manual step. Driven by lib_bejson_CMS_taxonomy.py's registry (one
        # source of truth for which entities want a UUID and what it's
        # called), not a second hardcoded list here.
        #
        # This is intentionally NOT folded into the generic FIELD-level
        # migration loop below: that loop backfills every missing field with
        # a single shared `None` value for every row, which is correct for
        # an ordinary new field but WRONG for a UUID -- every row needs its
        # own distinct value, or every pre-existing row would collide on the
        # same `None` "identity". New field appended at the end (never
        # inserted/reordered -- BEJSON is positional), matching this
        # function's existing convention, even though the one-time manual
        # migration put it first on the entities already migrated -- field
        # position is irrelevant to correctness under Field Map Cache
        # resolution (System Development Policy §6.2).
        uuid_healed = []
        for entity_name, meta in Taxonomy.TAXONOMY_PREFIX_REGISTRY.items():
            uuid_field = meta.get("uuid_field")
            if not uuid_field or entity_name not in existing:
                continue
            entity_row = next((v for v in manifest["Values"] if v[0] == entity_name), None)
            if not entity_row:
                continue
            fp_rel = entity_row[1]
            abs_path = os.path.join(site_dir, fp_rel)
            if not os.path.exists(abs_path):
                continue
            with open(abs_path, 'r', encoding='utf-8') as fh:
                entity_doc = json.load(fh)
            current_field_names = [f["name"] for f in entity_doc.get("Fields", [])]
            if uuid_field in current_field_names:
                continue  # already has it (this project's live data, post pkg135)
            entity_doc["Fields"] = entity_doc.get("Fields", []) + [{"name": uuid_field, "type": "string"}]
            entity_doc["Values"] = [row + [str(_uuid.uuid4())] for row in entity_doc.get("Values", [])]
            tmp = abs_path + ".tmp"
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump(entity_doc, fh, indent=2)
            os.replace(tmp, abs_path)
            entity_row[5] = uuid_field  # manifest primary_key now points at the UUID
            uuid_healed.append(f"{entity_name}(+{uuid_field})")

        if uuid_healed:
            print(f"[CMS] Migration: injected UUID fields on existing entities {uuid_healed}")
            manifest_changed = True
        else:
            manifest_changed = False

        # PageRecord FK-uuid self-heal (pkg137). page_cat_name/
        # page_author_name are still plain strings (pkg135 deliberately
        # left them that way -- converting every render/permalink path
        # that reads them was a separate, larger decision). What pkg137
        # adds is a genuine, resolvable identity link alongside them:
        # page_cat_uuid/page_author_uuid, kept in sync automatically by
        # every write path (page create/update/import, and category
        # merge). Existing pages written before this field existed need
        # it BACKFILLED BY RESOLUTION -- looking up their current
        # page_cat_name/page_author_name against live Category/
        # AuthorProfile records -- not by the generic FIELD-level
        # migration loop below, which backfills missing fields with a
        # single shared `None` for every row (fine for an ordinary new
        # field, wrong here: two different pages in two different
        # categories both getting `None` would make them look like they
        # share an identity they don't). A page whose category/author name
        # doesn't resolve to any live record (the exact orphan case
        # `doctor` already checks for) correctly gets `None` here -- that
        # is the honest state, not a bug.
        page_fk_healed = 0
        if "PageRecord" in existing:
            page_row = next((v for v in manifest["Values"] if v[0] == "PageRecord"), None)
            if page_row:
                page_path = os.path.join(site_dir, page_row[1])
                if os.path.exists(page_path):
                    with open(page_path, 'r', encoding='utf-8') as fh:
                        page_doc = json.load(fh)
                    page_field_names = [f["name"] for f in page_doc.get("Fields", [])]
                    if "page_cat_uuid" not in page_field_names or "page_author_uuid" not in page_field_names:
                        # Read Category/AuthorProfile directly via the manifest,
                        # same as everything else in this function -- _migrate_db()
                        # deliberately never depends on CMSCore/db (see docstring).
                        def _read_entity_name_to_uuid(entity_name, name_field, uuid_field):
                            row = next((v for v in manifest["Values"] if v[0] == entity_name), None)
                            if not row:
                                return {}
                            path = os.path.join(site_dir, row[1])
                            if not os.path.exists(path):
                                return {}
                            with open(path, 'r', encoding='utf-8') as fh2:
                                doc = json.load(fh2)
                            fnames = [f["name"] for f in doc.get("Fields", [])]
                            if name_field not in fnames or uuid_field not in fnames:
                                return {}
                            ni, ui = fnames.index(name_field), fnames.index(uuid_field)
                            return {r[ni]: r[ui] for r in doc.get("Values", []) if ni < len(r) and ui < len(r)}
                        cat_by_name = _read_entity_name_to_uuid("Category", "cat_name", "cat_uuid")
                        author_by_name = _read_entity_name_to_uuid("AuthorProfile", "author_display_name", "author_uuid")
                        new_fields = list(page_doc.get("Fields", []))
                        add_cat = "page_cat_uuid" not in page_field_names
                        add_author = "page_author_uuid" not in page_field_names
                        if add_cat:
                            new_fields.append({"name": "page_cat_uuid", "type": "string"})
                        if add_author:
                            new_fields.append({"name": "page_author_uuid", "type": "string"})
                        cat_idx = page_field_names.index("page_cat_name") if "page_cat_name" in page_field_names else None
                        author_idx = page_field_names.index("page_author_name") if "page_author_name" in page_field_names else None
                        new_values = []
                        for row in page_doc.get("Values", []):
                            new_row = list(row)
                            if add_cat:
                                cat_name = row[cat_idx] if cat_idx is not None and cat_idx < len(row) else None
                                new_row.append(cat_by_name.get(cat_name))
                            if add_author:
                                author_name = row[author_idx] if author_idx is not None and author_idx < len(row) else None
                                new_row.append(author_by_name.get(author_name) if author_name else None)
                            new_values.append(new_row)
                        page_doc["Fields"] = new_fields
                        page_doc["Values"] = new_values
                        tmp = page_path + ".tmp"
                        with open(tmp, 'w', encoding='utf-8') as fh:
                            json.dump(page_doc, fh, indent=2)
                        os.replace(tmp, page_path)
                        page_fk_healed = len(new_values)
        if page_fk_healed:
            print(f"[CMS] Migration: resolved page_cat_uuid/page_author_uuid on {page_fk_healed} existing PageRecord row(s)")

        # StandaloneApp app_created_at self-heal (pkg139, Elton: "add
        # app_created_at field" -- audit L-4). Unlike the uuid self-heals
        # above, a shared value across every pre-existing row is honest
        # here, not wrong: there IS no recoverable true creation date for
        # an app that predates this field, so every pre-existing app gets
        # THIS migration run's timestamp -- "the date we started tracking
        # it" -- rather than a per-row distinct value that would falsely
        # imply precision that doesn't exist. New apps created after this
        # point get their real creation date at creation time (see
        # BEJSON_CMS_Content.py's apps_new() and cms-manage.py's app add).
        app_fk_healed = 0
        if "StandaloneApp" in existing:
            app_row = next((v for v in manifest["Values"] if v[0] == "StandaloneApp"), None)
            if app_row:
                app_path = os.path.join(site_dir, app_row[1])
                if os.path.exists(app_path):
                    with open(app_path, 'r', encoding='utf-8') as fh:
                        app_doc = json.load(fh)
                    app_field_names = [f["name"] for f in app_doc.get("Fields", [])]
                    if "app_created_at" not in app_field_names:
                        now_iso = datetime.utcnow().isoformat()
                        app_doc["Fields"] = list(app_doc.get("Fields", [])) + [{"name": "app_created_at", "type": "string"}]
                        app_doc["Values"] = [row + [now_iso] for row in app_doc.get("Values", [])]
                        tmp = app_path + ".tmp"
                        with open(tmp, 'w', encoding='utf-8') as fh:
                            json.dump(app_doc, fh, indent=2)
                        os.replace(tmp, app_path)
                        app_fk_healed = len(app_doc["Values"])
        if app_fk_healed:
            print(f"[CMS] Migration: backfilled app_created_at on {app_fk_healed} existing StandaloneApp row(s)")

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

        if added or manifest_changed:
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
            # "site_name" removed (audit M-5): duplicate of "title", written
            # with the same value on every save but never read by the
            # Publisher (which reads "title", per pkg125 M-3) or anywhere
            # else -- was dead accumulating data.
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
                db.add_record("SiteConfig", {"sys_uuid": str(_uuid.uuid4()), "sys_key": k, "sys_value": v})
                
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
