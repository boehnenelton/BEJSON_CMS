"""
Library:        lib_bejson_CMS_cms_mfdb.py
Family:         CMS
Description:    Relational database layer for CMS content, pages, and taxonomies.
Version:        2.1.6
Date:           2026-08-07
CHANGE (2026-08-07): Fixed mount_system() lock-format drift (LIB-CMS-H5).
The manually-written initial .mfdb_lock omitted "original_hash", which
MFDBArchive.mount()'s sticky-mount check requires to match the archive's
current hash. Without it, every mount after the first fails the sticky
check and falls through to an unconditional rmtree+re-extract of the
live workspace from the archive -- discarding any live, un-repacked
edits. Lock files are now written after repack_system() using
MFDBCore's own _calculate_file_hash(), matching the exact format
MFDBArchive.mount() writes itself.
Author:         Elton Boehnen
Contact:        eltonboehnen@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  04a92a24-dda1-4e4f-b5a1-191623441ea3
CHANGE (2026-07-07): Fixed a verified bug - imported bejson_utility_slugify
from lib_bejson_Utility_bejson_utility, a module that doesn't exist
anywhere in the project (confirmed pre-existing, predates this session -
this file could never actually run). Implemented locally instead,
matching the identical pattern already used in Flask_Page_Editor.py's
_slug(). Verified via cms-manage.py actually running end-to-end
afterward, not just a syntax check.
"""

import os
import sys
import uuid
import hashlib
import shutil
import zipfile
import re
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Add Lib to path
LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if LIB_DIR not in sys.path:
    sys.path.append(LIB_DIR)

import lib_bejson_Core_bejson_core as BEJSONCore
import lib_bejson_Core_mfdb_core as MFDBCore
from lib_bejson_Core_bejson_path_guard import bejson_safe_join

def bejson_utility_slugify(text):
    """Was imported from lib_bejson_Utility_bejson_utility, which doesn't
    exist anywhere in this project (confirmed broken since before this
    session - this file could never actually run). Implemented locally,
    matching the identical pattern already used in Flask_Page_Editor.py's
    _slug()."""
    return re.sub(r'[^a-z0-9]+', '-', (text or '').lower()).strip('-')

# Standard Entity Schemas (Policy Standard)
SCHEMA_SITECONFIG = [
    {"name": "config_key", "type": "string"},
    {"name": "config_value", "type": "string"},
    {"name": "description", "type": "string"}
]

class MFDB_CMS_Manager:
    def __init__(self, data_root: str):
        self.data_root = data_root
        self.workspace_root = os.path.join(data_root, "workspace")
        self.global_db_root = os.path.join(self.workspace_root, "db_global")
        self.content_db_root = os.path.join(self.workspace_root, "db_content")
        self.assets_dir = os.path.join(data_root, "assets")
        self.apps_dir = os.path.join(data_root, "standalone_apps")
        # FIX (LIB-CMS-H3): os.path.dirname(data_root) degrades badly for
        # any non-normalized input. If data_root is relative (e.g. "Data",
        # a very plausible constructor argument for local scripts), dirname
        # returns "" and this silently becomes a CWD-relative path -
        # www_root then drifts depending on the working directory at each
        # call, not the project location. If data_root sits at a filesystem
        # root (e.g. "/Data"), dirname returns "/", giving "/Processing/www".
        # Resolving to an absolute path first makes this deterministic and
        # anchored to data_root's actual location either way, while keeping
        # the same "Processing/www" is a sibling of data_root" layout.
        self.www_root = os.path.join(os.path.dirname(os.path.abspath(data_root)), "Processing", "www")
        
        # Manifests inside the workspace
        self.global_manifest = os.path.join(self.global_db_root, "104a.mfdb.bejson")
        self.content_manifest = os.path.join(self.content_db_root, "104a.mfdb.bejson")
        
        # Transport Archives
        self.global_archive = os.path.join(data_root, "global_master.mfdb.zip")
        self.content_archive = os.path.join(data_root, "content_master.mfdb.zip")

        # Granular Change Tracking
        self.change_log = []
        
        if not os.path.exists(self.assets_dir): os.makedirs(self.assets_dir)
        if not os.path.exists(self.apps_dir): os.makedirs(self.apps_dir)

    def log_change(self, entity: str, action: str, identifier: Any, metadata: dict = None):
        """Records a specific modification for granular state tracking."""
        self.change_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "entity": entity,
            "action": action,
            "id": identifier,
            "metadata": metadata or {}
        })

    def is_dirty(self) -> bool:
        return len(self.change_log) > 0

    def clear_changes(self):
        self.change_log = []

    def mount_system(self, force: bool = False):
        """Ensures both workspace roots have an active .mfdb_lock so
        repack_system() can commit. Live workspace files under db_root are
        this app's actual source of truth - CRUD methods read/write
        <db_root>/104a.mfdb.bejson directly, and the .zip archives are only
        written when repack_system() runs.

        CORRECTION (2026-08-07) to the LIB-CMS-H5 fix recorded in this
        package's changelog: that fix only patched the hash written by the
        bootstrap branch, which fixes the narrow "fresh install, restart
        immediately, nothing else ever touched the workspace" case - and
        introduced a new regression doing it (repack_system() was called
        BEFORE the lock file existed, so commit() raised "No active mount
        session found" on every fresh install). It did not fix the actual
        real-world bug: whenever the archives already exist but no
        .mfdb_lock is present (any live workspace that predates this fix,
        or any restart after the lock is lost for any reason - confirmed
        against a copy of Experimental CMS's actual shipped data), this
        fell straight into MFDBArchive.mount()'s cold-mount path, which
        wipes target_dir and re-extracts from the archive unconditionally.
        Reproduced directly against this file: 1 live row -> 0 after one
        mount_system() call.

        Fix: never call MFDBArchive.mount() (extract-from-archive) unless
        no live manifest exists yet for that root. If live data is already
        on disk, this only ensures a lock session exists - it never wipes.
        MFDBArchive.mount()'s extract-and-wipe behavior is only actually
        correct for the one case where there is no live workspace at all.
        """
        needs_bootstrap_repack = []
        for db_root, manifest_path, archive in [
            (self.global_db_root, self.global_manifest, self.global_archive),
            (self.content_db_root, self.content_manifest, self.content_archive),
        ]:
            os.makedirs(db_root, exist_ok=True)
            lock_file = os.path.join(db_root, ".mfdb_lock")

            if os.path.exists(manifest_path):
                # Live data already present - the source of truth. Only
                # ensure a lock session exists; never wipe/re-extract.
                if force or not os.path.exists(lock_file):
                    with open(lock_file, "w") as f:
                        json.dump({"pid": os.getpid(), "mounted_at": datetime.now(timezone.utc).isoformat()}, f)
            elif os.path.exists(archive):
                # No live workspace yet, but a transport archive exists -
                # the one case MFDBArchive.mount()'s extract behavior is
                # actually the correct operation for.
                MFDBCore.MFDBArchive.mount(archive, db_root, force=force)
            else:
                # True fresh install: no schema anywhere yet for this root.
                needs_bootstrap_repack.append(db_root)

        self.initialize_system()  # no-op for any root whose manifest already exists

        for db_root in needs_bootstrap_repack:
            # Lock must exist BEFORE repack_system()/commit() runs, or
            # commit() raises "No active mount session found" - this is
            # exactly the ordering bug in the previous fix attempt.
            lock_file = os.path.join(db_root, ".mfdb_lock")
            if not os.path.exists(lock_file):
                with open(lock_file, "w") as f:
                    json.dump({"pid": os.getpid(), "mounted_at": datetime.now(timezone.utc).isoformat()}, f)

        if needs_bootstrap_repack:
            self.repack_system()
            # repack_system() writes fresh archives; refresh original_hash
            # in each lock so a later restart's sticky check (if this
            # workspace is ever cold-mounted elsewhere from the archive)
            # matches instead of always missing the key.
            for db_root, archive in ((self.global_db_root, self.global_archive),
                                      (self.content_db_root, self.content_archive)):
                if db_root in needs_bootstrap_repack:
                    lock_file = os.path.join(db_root, ".mfdb_lock")
                    with open(lock_file, "r") as f:
                        lock_data = json.load(f)
                    lock_data["original_hash"] = MFDBCore._calculate_file_hash(archive)
                    with open(lock_file, "w") as f:
                        json.dump(lock_data, f)

        self.clear_changes()

    def repack_system(self):
        MFDBCore.MFDBArchive.commit(self.global_db_root, self.global_archive)
        MFDBCore.MFDBArchive.commit(self.content_db_root, self.content_archive)
        self.clear_changes()

    def _create_record(self, entity_schema: List[Dict], rtp: str, values_map: Dict) -> List:
        """Helper to create a positional record from a named values map."""
        fm = {f["name"]: i for i, f in enumerate(entity_schema)}
        row = [None] * len(entity_schema)
        # 104db discriminator handling
        if "Record_Type_Parent" in fm:
            row[fm["Record_Type_Parent"]] = rtp
        for k, v in values_map.items():
            if k in fm: row[fm[k]] = v
        return row

    def factory_reset(self, confirm: bool = False):
        """Wipes all workspace data and archives - IRREVERSIBLE.

        FIX (LIB-CMS-H1): previously had no confirmation gate at all - any
        caller (including a stray script, or a route with no method/confirm
        guard) could wipe everything with a single call. Now requires
        confirm=True explicitly; every existing call site must be updated
        to pass it deliberately, which surfaces any caller that was invoking
        this without a real confirmation step upstream.
        """
        if not confirm:
            raise ValueError(
                "factory_reset() requires confirm=True. This permanently deletes "
                "all workspace data and archives with no way to undo it - the "
                "caller must obtain explicit user confirmation before passing "
                "confirm=True."
            )
        dirs_to_wipe = [self.workspace_root, self.assets_dir, self.apps_dir, self.www_root]
        for d in dirs_to_wipe:
            if os.path.exists(d): shutil.rmtree(d)
            os.makedirs(d)
        for arc in [self.global_archive, self.content_archive]:
            if os.path.exists(arc): os.remove(arc)
        self.clear_changes()
        print("Factory reset complete. System wiped.")

    def initialize_system(self):
        # 1. GLOBAL DATABASE
        if not os.path.exists(self.global_manifest):
            global_entities = [
                {"name": "SiteConfig", "primary_key": "config_key", "fields": [{"name": "config_key", "type": "string"}, {"name": "config_value", "type": "string"}, {"name": "description", "type": "string"}]},
                {"name": "NavLink", "fields": [{"name": "label", "type": "string"}, {"name": "url", "type": "string"}, {"name": "order", "type": "integer"}]},
                {"name": "SocialLink", "fields": [{"name": "platform", "type": "string"}, {"name": "url", "type": "string"}, {"name": "icon", "type": "string"}]},
                {"name": "AuthorProfile", "primary_key": "author_uuid", "fields": [{"name": "author_uuid", "type": "string"}, {"name": "name", "type": "string"}, {"name": "bio", "type": "string"}, {"name": "image_url", "type": "string"}]},
                {"name": "AdUnit", "primary_key": "ad_uuid", "fields": [{"name": "ad_uuid", "type": "string"}, {"name": "name", "type": "string"}, {"name": "image_url", "type": "string"}, {"name": "link_url", "type": "string"}, {"name": "zone", "type": "string"}, {"name": "active", "type": "boolean"}]},
                {"name": "MediaAsset", "primary_key": "filename", "fields": [{"name": "filename", "type": "string"}, {"name": "original_name", "type": "string"}, {"name": "file_hash", "type": "string"}, {"name": "file_size", "type": "integer"}, {"name": "mime_type", "type": "string"}, {"name": "uploaded_at", "type": "string"}, {"name": "folder", "type": "string"}]}
            ]
            MFDBCore.mfdb_core_create_database(root_dir=self.global_db_root, db_name="BEJSON CMS Global", entities=global_entities)
            self.add_global_config("site_title", "boehnenelton2024")
            self.add_global_config("site_tagline", "Premium Dark Theme Templates")
            self.add_global_config("base_url", "https://boehnenelton2024.pages.dev")
            
            # Dynamic Creation
            soc_schema = next(e["fields"] for e in global_entities if e["name"] == "SocialLink")
            MFDBCore.mfdb_core_add_entity_record(self.global_manifest, "SocialLink", 
                self._create_record(soc_schema, "SocialLink", {"platform": "GitHub", "url": "https://github.com/boehnenelton", "icon": "github"}))

        # 2. CONTENT DATABASE
        if not os.path.exists(self.content_manifest):
            content_entities = [
                {"name": "Category", "primary_key": "category_slug", "fields": [
                    {"name": "category_name", "type": "string"},
                    {"name": "category_slug", "type": "string"},
                    {"name": "description", "type": "string"},
                    {"name": "feed_type", "type": "string"}
                ]},
                {"name": "Page", "primary_key": "page_uuid", "fields": [{"name": "page_uuid", "type": "string"}, {"name": "title", "type": "string"}, {"name": "slug", "type": "string"}, {"name": "category_fk", "type": "string"}, {"name": "author_fk", "type": "string"}, {"name": "page_type", "type": "string"}, {"name": "featured_img", "type": "string"}, {"name": "created_at", "type": "string"}]},
                {"name": "PageContent", "fields": [{"name": "page_uuid_fk", "type": "string"}, {"name": "html_body", "type": "string"}, {"name": "markdown_body", "type": "string"}, {"name": "source_files", "type": "array"}, {"name": "video_url", "type": "string"}, {"name": "pdf_url", "type": "string"}, {"name": "pros", "type": "array"}, {"name": "cons", "type": "array"}, {"name": "verdict_score", "type": "number"}]},
                {"name": "StandaloneApp", "primary_key": "app_uuid", "fields": [{"name": "app_uuid", "type": "string"}, {"name": "name", "type": "string"}, {"name": "slug", "type": "string"}, {"name": "description", "type": "string"}, {"name": "category_fk", "type": "string"}, {"name": "featured_img", "type": "string"}, {"name": "entry_file", "type": "string"}, {"name": "created_at", "type": "string"}]}
            ]
            MFDBCore.mfdb_core_create_database(root_dir=self.content_db_root, db_name="BEJSON CMS Content", entities=content_entities)
            self.add_category("Uncategorized", "uncategorized", "General posts", "blog")

    def add_global_config(self, key: str, value: str, desc: str = ""):
        # Use module-level schema constant (REC-6)
        row = self._create_record(SCHEMA_SITECONFIG, "SiteConfig", {"config_key": key, "config_value": value, "description": desc})
        MFDBCore.mfdb_core_add_entity_record(self.global_manifest, "SiteConfig", row)
        self.log_change("SiteConfig", "ADD", key)

    def get_global_configs(self) -> Dict[str, str]:
        recs = MFDBCore.mfdb_core_load_entity(self.global_manifest, "SiteConfig")
        return {r["config_key"]: r["config_value"] for r in recs}

    def add_nav_link(self, label: str, url: str, order: int = 0):
        MFDBCore.mfdb_core_add_entity_record(self.global_manifest, "NavLink", [label, url, order])
        self.log_change("NavLink", "ADD", label)

    def delete_nav_link(self, label: str):
        recs = MFDBCore.mfdb_core_load_entity(self.global_manifest, "NavLink")
        for i, r in enumerate(recs):
            if r["label"] == label:
                MFDBCore.mfdb_core_remove_entity_record(self.global_manifest, "NavLink", i)
                self.log_change("NavLink", "DELETE", label)
                break

    def add_author(self, name: str, bio: str, image_url: str):
        auuid = str(uuid.uuid4())
        MFDBCore.mfdb_core_add_entity_record(self.global_manifest, "AuthorProfile", [auuid, name, bio, image_url])
        self.log_change("AuthorProfile", "ADD", auuid)
        return auuid

    def update_author(self, author_uuid: str, name: str, bio: str, image_url: str):
        recs = self.get_authors()
        for i, r in enumerate(recs):
            if r["author_uuid"] == author_uuid:
                updates = {
                    "name": name,
                    "bio": bio,
                    "image_url": image_url
                }
                MFDBCore.mfdb_core_update_entity_record_bulk(self.global_manifest, "AuthorProfile", i, updates)
                self.log_change("AuthorProfile", "UPDATE", author_uuid)
                break

    def delete_author(self, author_uuid: str):
        recs = self.get_authors()
        for i, r in enumerate(recs):
            if r["author_uuid"] == author_uuid:
                MFDBCore.mfdb_core_remove_entity_record(self.global_manifest, "AuthorProfile", i)
                self.log_change("AuthorProfile", "DELETE", author_uuid)
                break

    def get_authors(self) -> List[Dict]: return MFDBCore.mfdb_core_load_entity(self.global_manifest, "AuthorProfile")

    def add_ad(self, name: str, img: str, link: str, zone: str, active: bool = True):
        auuid = str(uuid.uuid4())
        MFDBCore.mfdb_core_add_entity_record(self.global_manifest, "AdUnit", [auuid, name, img, link, zone, active])
        self.log_change("AdUnit", "ADD", auuid)
        return auuid

    def add_asset(self, filename: str, original_name: str, file_hash: str, file_size: int, mime_type: str, folder: str = ""):
        """Registers an asset that has already been saved to the assets directory."""
        uploaded_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        MFDBCore.mfdb_core_add_entity_record(self.global_manifest, "MediaAsset", [filename, original_name, file_hash, file_size, mime_type, uploaded_at, folder])
        self.log_change("MediaAsset", "ADD", filename)
        return filename

    def delete_asset(self, filename: str):
        recs = MFDBCore.mfdb_core_load_entity(self.global_manifest, "MediaAsset")
        for i, r in enumerate(recs):
            if r["filename"] == filename:
                MFDBCore.mfdb_core_remove_entity_record(self.global_manifest, "MediaAsset", i)
                fpath = os.path.join(self.assets_dir, filename)
                if os.path.exists(fpath): os.remove(fpath)
                self.log_change("MediaAsset", "DELETE", filename)
                return True
        return False

    def add_category(self, name: str, slug: str, description: str = "", feed_type: str = "blog"):
        MFDBCore.mfdb_core_add_entity_record(self.content_manifest, "Category", [name, slug, description, feed_type])
        self.log_change("Category", "ADD", slug)

    def update_category(self, slug: str, name: str, description: str = None, feed_type: str = None):
        recs = self.get_categories()
        for i, r in enumerate(recs):
            if r["category_slug"] == slug:
                updates = {"category_name": name}
                if description is not None: updates["description"] = description
                if feed_type is not None: updates["feed_type"] = feed_type
                MFDBCore.mfdb_core_update_entity_record_bulk(self.content_manifest, "Category", i, updates)
                self.log_change("Category", "UPDATE", slug)
                break

    def create_page(self, title: str, category_slug: str, page_type: str, content_data: Dict[str, Any]) -> str:
        page_uuid = str(uuid.uuid4())
        page_slug = bejson_utility_slugify(title)
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        MFDBCore.mfdb_core_add_entity_record(self.content_manifest, "Page", [page_uuid, title, page_slug, category_slug, content_data.get("author_fk", ""), page_type, content_data.get("featured_img"), created_at])
        content_values = [page_uuid, content_data.get("html_body", ""), content_data.get("markdown_body", ""), content_data.get("source_files", []), content_data.get("video_url", ""), content_data.get("pdf_url", ""), content_data.get("pros", []), content_data.get("cons", []), content_data.get("verdict_score", 0.0)]
        MFDBCore.mfdb_core_add_entity_record(self.content_manifest, "PageContent", content_values)
        self.log_change("Page", "ADD", page_uuid)
        return page_uuid

    def update_page(self, page_uuid: str, title: str, category_slug: str, page_type: str, content_data: Dict[str, Any]):
        """FIX (LIB-CMS-H4): previously did 3 separate single-field writes
        for the Page record, then up to 8 more individually for
        PageContent - each mfdb_core_update_entity_record() call is its own
        full read-lock-write cycle, so a single page save could trigger 11
        sequential lock/read/write round-trips on the same two entity
        files, and a crash between any two of them left a partially-updated
        record. Now batches each entity into one bulk update."""
        recs = MFDBCore.mfdb_core_load_entity(self.content_manifest, "Page")
        for i, r in enumerate(recs):
            if r["page_uuid"] == page_uuid:
                MFDBCore.mfdb_core_update_entity_record_bulk(self.content_manifest, "Page", i, {
                    "title": title,
                    "category_fk": category_slug,
                    "page_type": page_type,
                })
                self.log_change("Page", "UPDATE", page_uuid)
                break
        crecs = MFDBCore.mfdb_core_load_entity(self.content_manifest, "PageContent")
        for i, r in enumerate(crecs):
            if r["page_uuid_fk"] == page_uuid:
                updates = {key: content_data[key] for key in
                           ["html_body", "markdown_body", "source_files", "video_url", "pdf_url", "pros", "cons", "verdict_score"]
                           if key in content_data}
                if updates:
                    MFDBCore.mfdb_core_update_entity_record_bulk(self.content_manifest, "PageContent", i, updates)
                break

    def delete_page(self, page_uuid: str):
        # 1. Remove from Page entity
        pages = MFDBCore.mfdb_core_load_entity(self.content_manifest, "Page")
        for i, p in enumerate(pages):
            if p.get("page_uuid") == page_uuid:
                MFDBCore.mfdb_core_remove_entity_record(self.content_manifest, "Page", i)
                break
        
        # 2. Remove from PageContent entity
        contents = MFDBCore.mfdb_core_load_entity(self.content_manifest, "PageContent")
        for i, c in enumerate(contents):
            if c.get("page_uuid_fk") == page_uuid:
                MFDBCore.mfdb_core_remove_entity_record(self.content_manifest, "PageContent", i)
                break
        self.log_change("Page", "DELETE", page_uuid)

    def delete_category(self, slug: str):
        recs = MFDBCore.mfdb_core_load_entity(self.content_manifest, "Category")
        for i, r in enumerate(recs):
            if r.get("category_slug") == slug:
                MFDBCore.mfdb_core_remove_entity_record(self.content_manifest, "Category", i)
                break
        self.log_change("Category", "DELETE", slug)

    def delete_ad(self, ad_uuid: str):
        recs = self.get_ads()
        for i, r in enumerate(recs):
            if r.get("ad_uuid") == ad_uuid:
                MFDBCore.mfdb_core_remove_entity_record(self.global_manifest, "AdUnit", i)
                self.log_change("AdUnit", "DELETE", ad_uuid)
                break

    def update_ad(self, ad_uuid: str, name: str, img: str, link: str, zone: str, active: bool = True):
        recs = self.get_ads()
        for i, r in enumerate(recs):
            if r["ad_uuid"] == ad_uuid:
                updates = {
                    "name": name,
                    "image_url": img,
                    "link_url": link,
                    "zone": zone,
                    "active": active
                }
                MFDBCore.mfdb_core_update_entity_record_bulk(self.global_manifest, "AdUnit", i, updates)
                self.log_change("AdUnit", "UPDATE", ad_uuid)
                break

    def delete_app(self, app_uuid: str):
        recs = MFDBCore.mfdb_core_load_entity(self.content_manifest, "StandaloneApp")
        for i, r in enumerate(recs):
            if r["app_uuid"] == app_uuid:
                MFDBCore.mfdb_core_remove_entity_record(self.content_manifest, "StandaloneApp", i)
                self.log_change("StandaloneApp", "DELETE", app_uuid)
                break

    # -----------------------------------------------------------------------
    # Read helpers — not yet in upstream lib; required by Flask routes
    # -----------------------------------------------------------------------

    def get_ads(self) -> List[Dict]:
        return MFDBCore.mfdb_core_load_entity(self.global_manifest, "AdUnit")

    def get_nav_links(self) -> List[Dict]:
        return MFDBCore.mfdb_core_load_entity(self.global_manifest, "NavLink")

    def get_assets(self) -> List[Dict]:
        return MFDBCore.mfdb_core_load_entity(self.global_manifest, "MediaAsset")

    def get_asset_by_hash(self, file_hash: str) -> Optional[Dict]:
        return next((a for a in self.get_assets() if a["file_hash"] == file_hash), None)

    def get_file_hash(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def get_apps(self) -> List[Dict]:
        return MFDBCore.mfdb_core_load_entity(self.content_manifest, "StandaloneApp")

    def get_pages(self) -> List[Dict]:
        return MFDBCore.mfdb_core_load_entity(self.content_manifest, "Page")

    def get_categories(self) -> List[Dict]:
        return MFDBCore.mfdb_core_load_entity(self.content_manifest, "Category")

    def get_pages_in_category(self, category_slug: str) -> List[Dict]:
        return [p for p in MFDBCore.mfdb_core_load_entity(self.content_manifest, "Page")
                if p.get("category_fk") == category_slug]

    def get_apps_in_category(self, category_slug: str) -> List[Dict]:
        return [a for a in self.get_apps() if a.get("category_fk") == category_slug]

    def get_full_page_data(self, page_uuid: str) -> Optional[Dict]:
        pages = MFDBCore.mfdb_core_load_entity(self.content_manifest, "Page")
        page = next((p for p in pages if p.get("page_uuid") == page_uuid), None)
        if not page:
            return None
        contents = MFDBCore.mfdb_core_load_entity(self.content_manifest, "PageContent")
        content = next((c for c in contents if c.get("page_uuid_fk") == page_uuid), {})
        return {**page, **content}

    def create_app(self, name: str, description: str, category: str,
                   featured_img: str, entry_file: str):
        app_uuid   = str(uuid.uuid4())
        slug       = bejson_utility_slugify(name)
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        MFDBCore.mfdb_core_add_entity_record(
            self.content_manifest, "StandaloneApp",
            [app_uuid, name, slug, description, category, featured_img, entry_file, created_at]
        )
        self.log_change("StandaloneApp", "ADD", app_uuid)
        return app_uuid

    def import_html_as_page(self, file_path: str, title: str, category: str, author_uuid: str = ""):
        """Imports an HTML file as a new CMS page."""
        path = Path(file_path)
        if not path.exists(): return None
        
        content = path.read_text(encoding="utf-8")
        # Simple extraction: if <body> exists, take inner, else take all
        import re
        body_match = re.search(r"<body[^>]*>(.*?)</body>", content, re.DOTALL | re.IGNORECASE)
        html_body = body_match.group(1) if body_match else content
        
        return self.create_page(title, category, "blog", {"html_body": html_body, "author_fk": author_uuid})

    def import_app_as_page(self, app_uuid: str, author_uuid: str = ""):
        """Wraps a StandaloneApp in a CMS page."""
        apps = self.get_apps()
        app = next((a for a in apps if a["app_uuid"] == app_uuid), None)
        if not app: return None
        
        content = {
            "html_body": f'<iframe src="{app["entry_file"]}" style="width:100%; height:80vh; border:none;"></iframe>',
            "author_fk": author_uuid
        }
        return self.create_page(f"App: {app['name']}", app["category_fk"], "app", content)

    def optimize_assets(self, convert_webp: bool = True):
        """Converts PNGs to WebP and updates all database references."""
        try:
            from PIL import Image
        except ImportError:
            print("Error: Pillow library required for image optimization.")
            return False
            
        recs = self.get_assets()
        updated_paths = {}
        
        for r in recs:
            filename = r["filename"]
            if convert_webp and filename.lower().endswith(".png"):
                old_path = os.path.join(self.assets_dir, filename)
                new_filename = filename.rsplit(".", 1)[0] + ".webp"
                new_path = os.path.join(self.assets_dir, new_filename)
                
                if os.path.exists(old_path):
                    try:
                        img = Image.open(old_path)
                        img.save(new_path, "webp")

                        # FIX (LIB-CMS-H2): img.save() can complete without
                        # raising on a truncated/empty write (e.g. disk full
                        # mid-write on some filesystems), which would then
                        # get registered and have the original deleted out
                        # from under it with no verification. The "file
                        # exists" and "db record added" failure modes were
                        # already implicitly covered - both raise inside this
                        # same try block, which skips delete_asset() below -
                        # but a 0-byte/corrupt success was not. Fail loudly
                        # instead of silently registering a broken asset.
                        file_size = os.path.getsize(new_path)
                        if file_size == 0:
                            raise IOError(f"WebP conversion of {filename} produced a 0-byte file")

                        with open(new_path, "rb") as f:
                            file_hash = self.get_file_hash(f.read())
                        
                        # Add new record directly (avoid redundant copy)
                        uploaded_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                        MFDBCore.mfdb_core_add_entity_record(self.global_manifest, "MediaAsset", [new_filename, r["original_name"], file_hash, file_size, "image/webp", uploaded_at])
                        
                        # Delete old
                        self.delete_asset(filename)
                        updated_paths[filename] = new_filename
                        print(f"Optimized: {filename} -> {new_filename}")
                    except Exception as e:
                        print(f"Failed to optimize {filename}: {e}")
        
        # Update PageContent references
        if updated_paths:
            page_contents = MFDBCore.mfdb_core_load_entity(self.content_manifest, "PageContent")
            for i, pc in enumerate(page_contents):
                body = pc.get("html_body", "")
                md_body = pc.get("markdown_body", "")
                changed = False
                for old, new in updated_paths.items():
                    if old in body:
                        body = body.replace(old, new)
                        changed = True
                    if md_body and old in md_body:
                        md_body = md_body.replace(old, new)
                        changed = True
                
                if changed:
                    MFDBCore.mfdb_core_update_entity_record(self.content_manifest, "PageContent", i, "html_body", body)
                    if md_body:
                        MFDBCore.mfdb_core_update_entity_record(self.content_manifest, "PageContent", i, "markdown_body", md_body)
            print(f"Updated references for {len(updated_paths)} assets across pages.")
        return True

    def create_site_backup(self, backup_dir: str) -> Optional[str]:
        """Creates a full site backup zip containing DBs, assets, and apps."""
        if self.is_dirty():
            self.repack_system()
            
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_name = f"bejson_cms_backup_{ts}.zip"
        backup_path = os.path.join(backup_dir, backup_name)
        
        os.makedirs(backup_dir, exist_ok=True)
        
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add DB Archives
            if os.path.exists(self.global_archive):
                zf.write(self.global_archive, "global_master.mfdb.zip")
            if os.path.exists(self.content_archive):
                zf.write(self.content_archive, "content_master.mfdb.zip")
            
            # Add Assets
            for root, _, files in os.walk(self.assets_dir):
                for file in files:
                    fpath = os.path.join(root, file)
                    zf.write(fpath, os.path.join("assets", os.path.relpath(fpath, self.assets_dir)))
            
            # Add Apps
            for root, _, files in os.walk(self.apps_dir):
                for file in files:
                    fpath = os.path.join(root, file)
                    zf.write(fpath, os.path.join("standalone_apps", os.path.relpath(fpath, self.apps_dir)))
                    
        return backup_path

    def restore_site_backup(self, backup_path: str) -> bool:
        """Restores a full site backup."""
        if not os.path.exists(backup_path):
            return False
            
        # 1. Clear Workspace
        if os.path.exists(self.workspace_root):
            shutil.rmtree(self.workspace_root)
        os.makedirs(self.workspace_root, exist_ok=True)
        
        # 2. Extract Archive
        with zipfile.ZipFile(backup_path, 'r') as zf:
            # Restore Databases
            for db_zip in ["global_master.mfdb.zip", "content_master.mfdb.zip"]:
                if db_zip in zf.namelist():
                    # R5-NEW-08: validate AND use the validated path for extraction
                    target = bejson_safe_join(self.data_root, db_zip)  # raises on traversal
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with zf.open(db_zip) as src, open(target, 'wb') as dst:
                        dst.write(src.read())
                
            # Restore Assets
            if os.path.exists(self.assets_dir): shutil.rmtree(self.assets_dir)
            for item in zf.namelist():
                if item.startswith("assets/"):
                    # R5-NEW-08: validated path is now actually used for extraction
                    target = bejson_safe_join(self.data_root, item)  # raises on traversal
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    if not item.endswith('/'):
                        with zf.open(item) as src, open(target, 'wb') as dst:
                            dst.write(src.read())
                    
            # Restore Apps
            if os.path.exists(self.apps_dir): shutil.rmtree(self.apps_dir)
            for item in zf.namelist():
                if item.startswith("standalone_apps/"):
                    # R5-NEW-08: validated path is now actually used for extraction
                    target = bejson_safe_join(self.data_root, item)  # raises on traversal
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    if not item.endswith('/'):
                        with zf.open(item) as src, open(target, 'wb') as dst:
                            dst.write(src.read())
                    
        # 3. Re-mount
        self.mount_system(force=True)
        return True
