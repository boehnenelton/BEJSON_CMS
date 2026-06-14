"""
Library:      lib_cms_mfdb.py
Family:       CMS
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.0.4 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-18
Description:  Relational database layer for CMS content, pages, and taxonomies.
REMEDIATED:   Implemented Granular State Management (Change Tracking).
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

import lib_bejson_core as BEJSONCore
import lib_mfdb_core as MFDBCore
from lib_bejson_path_guard import bejson_safe_join

class MFDB_CMS_Manager:
    def __init__(self, data_root: str):
        self.data_root = data_root
        self.workspace_root = os.path.join(data_root, "workspace")
        self.global_db_root = os.path.join(self.workspace_root, "db_global")
        self.content_db_root = os.path.join(self.workspace_root, "db_content")
        self.assets_dir = os.path.join(data_root, "assets")
        self.apps_dir = os.path.join(data_root, "standalone_apps")
        self.www_root = os.path.join(os.path.dirname(data_root), "Processing", "www")
        
        # Manifests inside the workspace
        self.global_manifest = os.path.join(self.global_db_root, "104a.mfdb.bejson")
        self.content_manifest = os.path.join(self.content_db_root, "104a.mfdb.bejson")
        
        # Transport Archives
        self.global_archive = os.path.join(data_root, "global_master.mfdb.zip")
        self.content_archive = os.path.join(data_root, "content_master.mfdb.zip")

        # REMEDIATED: Granular Change Tracking
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
        if not os.path.exists(self.global_archive) or not os.path.exists(self.content_archive):
            if not os.path.exists(self.global_db_root): os.makedirs(self.global_db_root)
            if not os.path.exists(self.content_db_root): os.makedirs(self.content_db_root)
            self.initialize_system()
            for db_root in [self.global_db_root, self.content_db_root]:
                lock_file = os.path.join(db_root, ".mfdb_lock")
                if not os.path.exists(lock_file):
                    with open(lock_file, "w") as f:
                        json.dump({"pid": os.getpid(), "mounted_at": "initial_setup"}, f)
            self.repack_system()
            return

        MFDBCore.MFDBArchive.mount(self.global_archive, self.global_db_root, force=force)
        MFDBCore.MFDBArchive.mount(self.content_archive, self.content_db_root, force=force)
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

    def factory_reset(self):
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
                {"name": "MediaAsset", "primary_key": "filename", "fields": [{"name": "filename", "type": "string"}, {"name": "original_name", "type": "string"}, {"name": "file_hash", "type": "string"}, {"name": "file_size", "type": "integer"}, {"name": "mime_type", "type": "string"}, {"name": "uploaded_at", "type": "string"}]}
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
        # Schema lookup for dynamic creation
        schema = [{"name": "config_key", "type": "string"}, {"name": "config_value", "type": "string"}, {"name": "description", "type": "string"}]
        row = self._create_record(schema, "SiteConfig", {"config_key": key, "config_value": value, "description": desc})
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
                MFDBCore.mfdb_core_update_entity_record(self.global_manifest, "AuthorProfile", i, "name", name)
                MFDBCore.mfdb_core_update_entity_record(self.global_manifest, "AuthorProfile", i, "bio", bio)
                MFDBCore.mfdb_core_update_entity_record(self.global_manifest, "AuthorProfile", i, "image_url", image_url)
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

    def add_asset(self, src_path: str, custom_filename: str = None):
        """Copies a file to assets and registers it in the database."""
        src = Path(src_path)
        if not src.exists(): return None
        
        fname = custom_filename or src.name
        dest = os.path.join(self.assets_dir, fname)
        shutil.copy2(src, dest)
        
        with open(dest, "rb") as f:
            data = f.read()
        fhash = hashlib.sha256(data).hexdigest()
        fsize = len(data)
        mtype = "application/octet-stream"
        
        uploaded_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        MFDBCore.mfdb_core_add_entity_record(self.global_manifest, "MediaAsset", [fname, src.name, fhash, fsize, mtype, uploaded_at])
        self.log_change("MediaAsset", "ADD", fname)
        return fname

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

    def update_category(self, slug: str, name: str):
        recs = MFDBCore.mfdb_core_load_entity(self.content_manifest, "Category")
        for i, r in enumerate(recs):
            if r["category_slug"] == slug:
                MFDBCore.mfdb_core_update_entity_record(self.content_manifest, "Category", i, "category_name", name)
                self.log_change("Category", "UPDATE", slug)
                break

    def create_page(self, title: str, category_slug: str, page_type: str, content_data: Dict[str, Any]) -> str:
        page_uuid = str(uuid.uuid4())
        page_slug = title.lower().replace(" ", "-")
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        MFDBCore.mfdb_core_add_entity_record(self.content_manifest, "Page", [page_uuid, title, page_slug, category_slug, content_data.get("author_fk", ""), page_type, content_data.get("featured_img"), created_at])
        content_values = [page_uuid, content_data.get("html_body", ""), content_data.get("markdown_body", ""), content_data.get("source_files", []), content_data.get("video_url", ""), content_data.get("pdf_url", ""), content_data.get("pros", []), content_data.get("cons", []), content_data.get("verdict_score", 0.0)]
        MFDBCore.mfdb_core_add_entity_record(self.content_manifest, "PageContent", content_values)
        self.log_change("Page", "ADD", page_uuid)
        return page_uuid

    def update_page(self, page_uuid: str, title: str, category_slug: str, page_type: str, content_data: Dict[str, Any]):
        recs = MFDBCore.mfdb_core_load_entity(self.content_manifest, "Page")
        for i, r in enumerate(recs):
            if r["page_uuid"] == page_uuid:
                MFDBCore.mfdb_core_update_entity_record(self.content_manifest, "Page", i, "title", title)
                MFDBCore.mfdb_core_update_entity_record(self.content_manifest, "Page", i, "category_fk", category_slug)
                MFDBCore.mfdb_core_update_entity_record(self.content_manifest, "Page", i, "page_type", page_type)
                self.log_change("Page", "UPDATE", page_uuid)
                break
        crecs = MFDBCore.mfdb_core_load_entity(self.content_manifest, "PageContent")
        for i, r in enumerate(crecs):
            if r["page_uuid_fk"] == page_uuid:
                for key in ["html_body", "markdown_body", "source_files", "video_url", "pdf_url", "pros", "cons", "verdict_score"]:
                    if key in content_data: MFDBCore.mfdb_core_update_entity_record(self.content_manifest, "PageContent", i, key, content_data[key])
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
                MFDBCore.mfdb_core_update_entity_record(self.global_manifest, "AdUnit", i, "name", name)
                MFDBCore.mfdb_core_update_entity_record(self.global_manifest, "AdUnit", i, "image_url", img)
                MFDBCore.mfdb_core_update_entity_record(self.global_manifest, "AdUnit", i, "link_url", link)
                MFDBCore.mfdb_core_update_entity_record(self.global_manifest, "AdUnit", i, "zone", zone)
                MFDBCore.mfdb_core_update_entity_record(self.global_manifest, "AdUnit", i, "active", active)
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
        import hashlib
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
        import uuid as _uuid
        from datetime import datetime, timezone as _tz
        app_uuid   = str(_uuid.uuid4())
        slug       = name.lower().replace(" ", "-")
        created_at = datetime.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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
                        
                        # Update registry
                        file_size = os.path.getsize(new_path)
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
                    target = bejson_safe_join(self.data_root, db_zip)
                    zf.extract(db_zip, self.data_root)
                
            # Restore Assets
            if os.path.exists(self.assets_dir): shutil.rmtree(self.assets_dir)
            for item in zf.namelist():
                if item.startswith("assets/"):
                    # Boundary check via bejson_safe_join
                    target = bejson_safe_join(self.data_root, item)
                    zf.extract(item, self.data_root)
                    
            # Restore Apps
            if os.path.exists(self.apps_dir): shutil.rmtree(self.apps_dir)
            for item in zf.namelist():
                if item.startswith("standalone_apps/"):
                    # Boundary check via bejson_safe_join
                    target = bejson_safe_join(self.data_root, item)
                    zf.extract(item, self.data_root)
                    
        # 3. Re-mount
        self.mount_system(force=True)
        return True
