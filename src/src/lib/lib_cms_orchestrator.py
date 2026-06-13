"""
Library:      lib_cms_orchestrator.py
Family:       CMS
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.0.1 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-18
Description:  Master controller for the BEJSON-powered Content Management System.
"""

import os
import sys
from typing import Dict, List, Optional

LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if LIB_DIR not in sys.path: sys.path.append(LIB_DIR)

import lib_cms_config as CMSConfig
import lib_cms_taxonomy as CMSTaxonomy
import lib_cms_content as CMSContent
import lib_cms_mfdb as CMSMFDB

class CMSOrchestrator:
    def __init__(self, data_root: str, use_mfdb: bool = False):
        self.data_root = data_root
        self.use_mfdb = use_mfdb
        if use_mfdb:
            # FIX: Corrected class name from CMSMFDBManager to MFDB_CMS_Manager
            self.mfdb_manager = CMSMFDB.MFDB_CMS_Manager(data_root)
        else:
            self.master_db = os.path.join(data_root, "site_master.json")
            self.pages_db_dir = os.path.join(data_root, "pages_db")
        self._ensure_dirs()
        
    def _ensure_dirs(self):
        if self.use_mfdb:
            if not os.path.exists(os.path.join(self.data_root, "104a.mfdb.bejson")):
                self.mfdb_manager.initialize_system()
        else:
            os.makedirs(self.data_root, exist_ok=True)
            os.makedirs(self.pages_db_dir, exist_ok=True)
            if not os.path.exists(self.master_db):
                CMSConfig.cms_config_init_master(self.master_db)

    def get_config(self) -> Dict[str, str]:
        if self.use_mfdb: return self.mfdb_manager.get_global_configs()
        return CMSConfig.cms_config_get_all(self.master_db)
    
    def set_config(self, key: str, value: str):
        if self.use_mfdb: self.mfdb_manager.add_global_config(key, value)
        else: CMSConfig.cms_config_set(self.master_db, key, value)

    def get_categories(self) -> List[Dict]: return CMSTaxonomy.cms_taxonomy_get_categories(self.master_db)
    def add_category(self, name: str, slug: Optional[str] = None): CMSTaxonomy.cms_taxonomy_add_category(self.master_db, name, slug)
    def get_authors(self) -> List[Dict]: return CMSTaxonomy.cms_taxonomy_get_authors(self.master_db)
    def add_author(self, name: str, bio: str = "", image: str = ""): CMSTaxonomy.cms_taxonomy_add_author(self.master_db, name, bio, image)

    def create_page(self, title: str, category: str = "Uncategorized", author: str = "Admin", body: str = "", image: str = "") -> str:
        if self.use_mfdb: return self.mfdb_manager.create_page(title, category.lower(), "page", {"html_body": body, "featured_img": image})
        return CMSContent.cms_content_create_page(self.master_db, self.pages_db_dir, title, category, author, body, image)
    
    def update_page(self, page_uuid: str, updates: Dict): CMSContent.cms_content_update_page(self.master_db, self.pages_db_dir, page_uuid, updates)
    def delete_page(self, page_uuid: str) -> bool: return CMSContent.cms_content_delete_page(self.master_db, self.pages_db_dir, page_uuid)
    def list_pages(self) -> List[Dict]: return CMSContent.cms_content_list_pages(self.master_db)
    def get_page_body(self, page_uuid: str) -> str: return CMSContent.cms_content_get_page_body(self.pages_db_dir, page_uuid)

    def get_site_feed(self) -> Dict:
        return {"config": self.get_config(), "categories": self.get_categories(), "authors": self.get_authors(), "pages": self.list_pages()}
