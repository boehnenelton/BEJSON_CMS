"""
Library:      lib_cms_content.py
Family:       CMS
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.1.0 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-06-04
Description:  Content handler and transformer for the CMS engine.
REMEDIATED:   Implemented Field Map Indexing with Safe Get fallbacks (Phase 8.1).
"""

import os
import sys
import uuid
import re
from datetime import datetime
from typing import Dict, List, Optional

# Ensure local directory is in path for relative imports
LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if LIB_DIR not in sys.path:
    sys.path.append(LIB_DIR)

import lib_bejson_core as BEJSONCore

# --- Legacy Fallback Constants ---
_CMS_CONTENT_LEGACY = {
    "PageRecord": {
        "record_type_parent": 0, "page_uuid": 1, "page_title": 2, "page_slug": 3,
        "category_ref": 4, "item_type": 5, "created_at": 6, "author_ref": 7, "featured_img": 8
    },
    "Content": {
        "record_type_parent": 0, "html_body": 3, "markdown_body": 4
    },
    "PageMeta": {
        "record_type_parent": 0, "meta_title": 1, "meta_description": 2
    }
}

def _slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')

# ---------------------------------------------------------------------------
# PAGE CONTENT OPERATIONS (pages_db/<uuid>.json)
# ---------------------------------------------------------------------------

def _cms_content_init_page_file(file_path: str, title: str, html_body: str = "") -> None:
    """Initialize an individual page content file in 104db format."""
    record_types = ["PageMeta", "Content"]
    fields = [
        {"name": "Record_Type_Parent", "type": "string"},
        {"name": "meta_title", "type": "string", "Record_Type_Parent": "PageMeta"},
        {"name": "meta_description", "type": "string", "Record_Type_Parent": "PageMeta"},
        {"name": "html_body", "type": "string", "Record_Type_Parent": "Content"},
        {"name": "markdown_body", "type": "string", "Record_Type_Parent": "Content"},
    ]
    
    doc = BEJSONCore.bejson_core_create_104db(record_types, fields, [])
    
    # Map for creation (standardized creation pattern)
    fm = {f["name"]: i for i, f in enumerate(fields)}
    f_count = len(fields)
    
    # Add Meta record
    meta_row = [None] * f_count
    meta_row[fm["Record_Type_Parent"]] = "PageMeta"
    meta_row[fm["meta_title"]]         = title
    meta_row[fm["meta_description"]]   = ""
    BEJSONCore.bejson_core_add_record(doc, meta_row)
    
    # Add Content record
    content_row = [None] * f_count
    content_row[fm["Record_Type_Parent"]] = "Content"
    content_row[fm["html_body"]]          = html_body
    content_row[fm["markdown_body"]]      = ""
    
    BEJSONCore.bejson_core_add_record(doc, content_row)
    BEJSONCore.bejson_core_atomic_write(file_path, doc)

def cms_content_get_page_body(pages_dir: str, page_uuid: str) -> str:
    """Retrieve html_body from a page's individual JSON file."""
    file_path = os.path.join(pages_dir, f"{page_uuid}.json")
    if not os.path.exists(file_path):
        return ""
    
    doc = BEJSONCore.bejson_core_load_file(file_path)
    fi = BEJSONCore.bejson_core_get_field_map(doc)
    
    rtp_idx = fi.get("Record_Type_Parent", 0)
    hb_idx  = fi.get("html_body", _CMS_CONTENT_LEGACY["Content"]["html_body"])
    
    records = [v for v in doc["Values"] if len(v) > rtp_idx and v[rtp_idx] == "Content"]
    
    if records:
        return records[0][hb_idx] if hb_idx < len(records[0]) else ""
    return ""

# ---------------------------------------------------------------------------
# MASTER INDEX OPERATIONS (site_master.json)
# ---------------------------------------------------------------------------

def cms_content_create_page(
    master_db_path: str, 
    pages_dir: str, 
    title: str, 
    category_ref: str = "Uncategorized", 
    author_ref: str = "Admin",
    html_body: str = "",
    featured_img: str = ""
) -> str:
    """
    Create a new page: generates UUID, updates master index, creates content file.
    Returns the new page_uuid.
    """
    page_uuid = str(uuid.uuid4())
    page_slug = _slugify(title)
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 1. Update Master Index
    doc = BEJSONCore.bejson_core_load_file(master_db_path)
    
    # Optimized Field Mapping + Internal Registry Injection
    fi = BEJSONCore.bejson_core_get_field_map(doc)
    doc["_bejson_field_map"] = fi # Inject for re-use
    
    def _idx(name):
        return fi.get(name, _CMS_CONTENT_LEGACY["PageRecord"].get(name.lower(), -1))

    new_row = [None] * len(doc["Fields"])
    new_row[_idx("Record_Type_Parent")] = "PageRecord"
    new_row[_idx("page_uuid")]          = page_uuid
    new_row[_idx("page_title")]         = title
    new_row[_idx("page_slug")]          = page_slug
    new_row[_idx("category_ref")]       = category_ref
    new_row[_idx("item_type")]          = "page"
    new_row[_idx("created_at")]         = today
    new_row[_idx("author_ref")]         = author_ref
    new_row[_idx("featured_img")]       = featured_img
    
    BEJSONCore.bejson_core_add_record(doc, new_row)
    BEJSONCore.bejson_core_atomic_write(master_db_path, doc)
    
    # 2. Create individual content file
    os.makedirs(pages_dir, exist_ok=True)
    page_file = os.path.join(pages_dir, f"{page_uuid}.json")
    _cms_content_init_page_file(page_file, title, html_body)
    
    return page_uuid

def cms_content_update_page(
    master_db_path: str,
    pages_dir: str,
    page_uuid: str,
    updates: Dict
) -> None:
    """
    Update page metadata in master and/or content in individual file.
    'updates' can contain: title, category_ref, author_ref, featured_img, html_body.
    """
    # 1. Update Master Index if needed
    master_updates = {k: v for k, v in updates.items() if k in ["title", "category_ref", "author_ref", "featured_img"]}
    if master_updates:
        doc = BEJSONCore.bejson_core_load_file(master_db_path)
        fi = BEJSONCore.bejson_core_get_field_map(doc)
        
        rtp_idx   = fi.get("Record_Type_Parent", 0)
        uuid_idx  = fi.get("page_uuid", _CMS_CONTENT_LEGACY["PageRecord"]["page_uuid"])
        title_idx = fi.get("page_title", _CMS_CONTENT_LEGACY["PageRecord"]["page_title"])
        slug_idx  = fi.get("page_slug", _CMS_CONTENT_LEGACY["PageRecord"]["page_slug"])
        
        found = False
        for row in doc["Values"]:
            if len(row) > uuid_idx and row[rtp_idx] == "PageRecord" and row[uuid_idx] == page_uuid:
                for k, v in master_updates.items():
                    # Handle title -> page_title mapping
                    if k == "title":
                        row[title_idx] = v
                        row[slug_idx]  = _slugify(v)
                    else:
                        idx = fi.get(k, _CMS_CONTENT_LEGACY["PageRecord"].get(k, -1))
                        if idx != -1 and idx < len(row):
                            row[idx] = v
                found = True
                break
        if found:
            BEJSONCore.bejson_core_atomic_write(master_db_path, doc)

    # 2. Update Content File if needed
    html_body = updates.get("html_body")
    if html_body is not None or "title" in updates:
        page_file = os.path.join(pages_dir, f"{page_uuid}.json")
        if os.path.exists(page_file):
            pdoc = BEJSONCore.bejson_core_load_file(page_file)
            pfi = BEJSONCore.bejson_core_get_field_map(pdoc)
            
            rtp_idx = pfi.get("Record_Type_Parent", 0)
            
            if html_body is not None:
                hb_idx = pfi.get("html_body", _CMS_CONTENT_LEGACY["Content"]["html_body"])
                for row in pdoc["Values"]:
                    if len(row) > hb_idx and row[rtp_idx] == "Content":
                        row[hb_idx] = html_body
                        
            if "title" in updates:
                mt_idx = pfi.get("meta_title", _CMS_CONTENT_LEGACY["PageMeta"]["meta_title"])
                for row in pdoc["Values"]:
                    if len(row) > mt_idx and row[rtp_idx] == "PageMeta":
                        row[mt_idx] = updates["title"]
                        
            BEJSONCore.bejson_core_atomic_write(page_file, pdoc)

def cms_content_delete_page(master_db_path: str, pages_dir: str, page_uuid: str) -> bool:
    """Delete page from master index and remove its content file."""
    # 1. Master Index
    doc = BEJSONCore.bejson_core_load_file(master_db_path)
    fi = BEJSONCore.bejson_core_get_field_map(doc)
    
    rtp_idx  = fi.get("Record_Type_Parent", 0)
    uuid_idx = fi.get("page_uuid", _CMS_CONTENT_LEGACY["PageRecord"]["page_uuid"])
    
    new_values = []
    found = False
    for row in doc["Values"]:
        if len(row) > uuid_idx and row[rtp_idx] == "PageRecord" and row[uuid_idx] == page_uuid:
            found = True
            continue
        new_values.append(row)
        
    if found:
        doc["Values"] = new_values
        BEJSONCore.bejson_core_atomic_write(master_db_path, doc)
        
        # 2. Content File
        page_file = os.path.join(pages_dir, f"{page_uuid}.json")
        if os.path.exists(page_file):
            os.remove(page_file)
            
    return found

def cms_content_list_pages(master_db_path: str) -> List[Dict]:
    """List all pages from master index as a list of dictionaries."""
    doc = BEJSONCore.bejson_core_load_file(master_db_path)
    records = BEJSONCore.bejson_core_get_records_by_type(doc, "PageRecord")
    fields = doc.get("Fields", [])
    
    results = []
    for row in records:
        item = {}
        for i, f in enumerate(fields):
            if i < len(row):
                item[f['name']] = row[i]
        results.append(item)
    return results
