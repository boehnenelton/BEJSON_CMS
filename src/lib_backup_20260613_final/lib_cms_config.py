"""
Library:      lib_cms_config.py
Family:       CMS
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.0.1 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-18
Description:  Configuration manager for CMS-specific settings.
"""

import os
import sys
import copy
from typing import Any, Dict, Optional

# Ensure local directory is in path for relative imports
LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if LIB_DIR not in sys.path:
    sys.path.append(LIB_DIR)

import lib_bejson_core as BEJSONCore

# --- Legacy Fallback Constants ---
_CMS_CONFIG_LEGACY = {
    "SiteConfig": {
        "config_key": 1,
        "config_value": 2
    }
}

def cms_config_init_master(db_path: str, site_title: str = "My BEJSON Site") -> Dict:
    """
    Initialize a new site_master.json file with the required 104db structure.
    """
    record_types = ["SiteConfig", "Category", "Author", "PageRecord", "NavLink", "SocialLink", "AdUnit", "StandaloneApp"]
    
    fields = [
        {"name": "Record_Type_Parent", "type": "string"},
        # SiteConfig fields
        {"name": "config_key", "type": "string", "Record_Type_Parent": "SiteConfig"},
        {"name": "config_value", "type": "string", "Record_Type_Parent": "SiteConfig"},
        # Category fields
        {"name": "category_name", "type": "string", "Record_Type_Parent": "Category"},
        {"name": "category_slug", "type": "string", "Record_Type_Parent": "Category"},
        # Author fields
        {"name": "author_name", "type": "string", "Record_Type_Parent": "Author"},
        {"name": "author_bio", "type": "string", "Record_Type_Parent": "Author"},
        {"name": "author_image", "type": "string", "Record_Type_Parent": "Author"},
        # PageRecord fields
        {"name": "page_uuid", "type": "string", "Record_Type_Parent": "PageRecord"},
        {"name": "page_title", "type": "string", "Record_Type_Parent": "PageRecord"},
        {"name": "page_slug", "type": "string", "Record_Type_Parent": "PageRecord"},
        {"name": "category_ref", "type": "string", "Record_Type_Parent": "PageRecord"},
        {"name": "item_type", "type": "string", "Record_Type_Parent": "PageRecord"},
        {"name": "created_at", "type": "string", "Record_Type_Parent": "PageRecord"},
        {"name": "external_url", "type": "string", "Record_Type_Parent": "PageRecord"},
        {"name": "author_ref", "type": "string", "Record_Type_Parent": "PageRecord"},
        {"name": "featured_img", "type": "string", "Record_Type_Parent": "PageRecord"},
    ]
    
    doc = BEJSONCore.bejson_core_create_104db(record_types, fields, [])
    
    # Add default config records
    field_count = len(fields)
    defaults = [
        ["SiteConfig", "title", site_title],
        ["SiteConfig", "description", "Built with BEJSON CMS Framework"],
        ["SiteConfig", "base_url", "http://localhost:8000"],
        ["SiteConfig", "creator", "Admin"],
        ["SiteConfig", "theme", "dark.css"]
    ]
    
    for row in defaults:
        # Pad with None to match field count
        padded_row = row + [None] * (field_count - len(row))
        BEJSONCore.bejson_core_add_record(doc, padded_row)
        
    BEJSONCore.bejson_core_atomic_write(db_path, doc)
    return doc

def cms_config_get_all(db_path: str) -> Dict[str, str]:
    """
    Retrieve all site configuration key-value pairs.
    """
    doc = BEJSONCore.bejson_core_load_file(db_path)
    if not doc: return {}
    
    records = BEJSONCore.bejson_core_filter_rows(doc, "Record_Type_Parent", "SiteConfig")
    
    # Optimized Field Mapping
    fi = BEJSONCore.bejson_core_get_field_map(doc)
    k_idx = fi.get("config_key", _CMS_CONFIG_LEGACY["SiteConfig"]["config_key"])
    v_idx = fi.get("config_value", _CMS_CONFIG_LEGACY["SiteConfig"]["config_value"])
    
    config = {}
    for row in records:
        if len(row) > max(k_idx, v_idx):
            config[row[k_idx]] = row[v_idx]
    return config

def cms_config_set(db_path: str, key: str, value: str) -> None:
    """
    Set or update a configuration value.
    """
    doc = BEJSONCore.bejson_core_load_file(db_path)
    if not doc: return

    # Work on a copy to ensure memory consistency on write failure (Finding 20)
    doc_copy = copy.deepcopy(doc)
    records = doc_copy["Values"]
    
    fi = BEJSONCore.bejson_core_get_field_map(doc_copy)
    k_idx = fi.get("config_key", _CMS_CONFIG_LEGACY["SiteConfig"]["config_key"])
    v_idx = fi.get("config_value", _CMS_CONFIG_LEGACY["SiteConfig"]["config_value"])
    t_idx = 0 # Record_Type_Parent is always first in 104db per convention
    
    found = False
    for i, row in enumerate(records):
        if row[t_idx] == "SiteConfig" and row[k_idx] == key:
            row[v_idx] = value
            found = True
            break
            
    if not found:
        # Add new config record
        field_count = len(doc_copy["Fields"])
        new_row = [None] * field_count
        new_row[t_idx] = "SiteConfig"
        new_row[k_idx] = key
        new_row[v_idx] = value
        BEJSONCore.bejson_core_add_record(doc_copy, new_row)
        
    BEJSONCore.bejson_core_atomic_write(db_path, doc_copy)

def cms_config_get(db_path: str, key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get a specific configuration value.
    """
    config = cms_config_get_all(db_path)
    return config.get(key, default)
