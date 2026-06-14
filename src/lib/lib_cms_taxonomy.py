"""
Library:      lib_cms_taxonomy.py
Family:       CMS
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.0.1 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-18
Description:  Category and tag manager for CMS data structures.
"""

import os
import sys
import re
from typing import Dict, List, Optional

# Ensure local directory is in path for relative imports
LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if LIB_DIR not in sys.path:
    sys.path.append(LIB_DIR)

import lib_bejson_core as BEJSONCore
from lib_bejson_utility import bejson_utility_slugify

# ---------------------------------------------------------------------------
# CATEGORY OPERATIONS
# ---------------------------------------------------------------------------

def cms_taxonomy_get_categories(db_path: str) -> List[Dict]:
    """
    List all categories from the master database.
    """
    doc = BEJSONCore.bejson_core_load_file(db_path)
    if not doc: return []
    records = BEJSONCore.bejson_core_filter_rows(doc, "Record_Type_Parent", "Category")
    
    cat_name_idx = BEJSONCore.bejson_core_get_field_index(doc, "category_name")
    cat_slug_idx = BEJSONCore.bejson_core_get_field_index(doc, "category_slug")
    
    categories = []
    for row in records:
        categories.append({
            "name": row[cat_name_idx],
            "slug": row[cat_slug_idx]
        })
    return categories

def cms_taxonomy_add_category(db_path: str, name: str, slug: Optional[str] = None) -> None:
    """
    Add a new category to the database.
    """
    if not slug:
        slug = bejson_utility_slugify(name)
        
    doc = BEJSONCore.bejson_core_load_file(db_path)
    
    # Check if exists
    cats = cms_taxonomy_get_categories(db_path)
    if any(c['slug'] == slug for c in cats):
        return # Already exists
        
    cat_name_idx = BEJSONCore.bejson_core_get_field_index(doc, "category_name")
    cat_slug_idx = BEJSONCore.bejson_core_get_field_index(doc, "category_slug")
    t_idx = 0
    
    field_count = len(doc["Fields"])
    new_row = [None] * field_count
    new_row[t_idx] = "Category"
    new_row[cat_name_idx] = name
    new_row[cat_slug_idx] = slug
    
    BEJSONCore.bejson_core_add_record(doc, new_row)
    BEJSONCore.bejson_core_atomic_write(db_path, doc)

def cms_taxonomy_delete_category(db_path: str, slug: str) -> bool:
    """
    Delete a category by slug.
    """
    doc = BEJSONCore.bejson_core_load_file(db_path)
    fi = BEJSONCore.bejson_core_get_field_map(doc)
    
    t_idx = fi.get("Record_Type_Parent", 0)
    slug_idx = fi.get("category_slug", _CMS_TAXONOMY_LEGACY["Category"]["category_slug"])
    
    new_values = []
    found = False
    for row in doc["Values"]:
        if len(row) > slug_idx and row[t_idx] == "Category" and row[slug_idx] == slug:
            found = True
            continue
        new_values.append(row)
        
    if found:
        doc["Values"] = new_values
        BEJSONCore.bejson_core_atomic_write(db_path, doc)
    return found

# ---------------------------------------------------------------------------
# AUTHOR OPERATIONS
# ---------------------------------------------------------------------------

def cms_taxonomy_get_authors(db_path: str) -> List[Dict]:
    """
    List all authors from the master database.
    """
    doc = BEJSONCore.bejson_core_load_file(db_path)
    if not doc: return []
    records = BEJSONCore.bejson_core_filter_rows(doc, "Record_Type_Parent", "AuthorProfile")
    
    uuid_idx = BEJSONCore.bejson_core_get_field_index(doc, "author_uuid")
    name_idx = BEJSONCore.bejson_core_get_field_index(doc, "name")
    bio_idx = BEJSONCore.bejson_core_get_field_index(doc, "bio")
    img_idx = BEJSONCore.bejson_core_get_field_index(doc, "image_url")
    
    authors = []
    for row in records:
        authors.append({
            "author_uuid": row[uuid_idx],
            "name": row[name_idx],
            "bio": row[bio_idx],
            "image_url": row[img_idx]
        })
    return authors

def cms_taxonomy_add_author(db_path: str, name: str, bio: str = "", image: str = "") -> None:
    """
    Add a new author to the database.
    """
    import uuid
    auuid = str(uuid.uuid4())
    doc = BEJSONCore.bejson_core_load_file(db_path)
    
    uuid_idx = BEJSONCore.bejson_core_get_field_index(doc, "author_uuid")
    name_idx = BEJSONCore.bejson_core_get_field_index(doc, "name")
    bio_idx = BEJSONCore.bejson_core_get_field_index(doc, "bio")
    img_idx = BEJSONCore.bejson_core_get_field_index(doc, "image_url")
    t_idx = 0
    
    field_count = len(doc["Fields"])
    new_row = [None] * field_count
    new_row[t_idx] = "AuthorProfile"
    new_row[uuid_idx] = auuid
    new_row[name_idx] = name
    new_row[bio_idx] = bio
    new_row[img_idx] = image
    
    BEJSONCore.bejson_core_add_record(doc, new_row)
    BEJSONCore.bejson_core_atomic_write(db_path, doc)
