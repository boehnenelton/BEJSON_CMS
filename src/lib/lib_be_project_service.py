"""
Library:      lib_be_project_service.py
Family:       System
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.2.1 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-06-04
Description:  Background service for project lifecycle and dependency management.
REMEDIATED:   Purged 'ADMIN_ROOT' and 'Brain-Container'; standardized to ADMIN_ROOT (Phase 6.5).
"""

import os
import sys
import json
import time
import shutil
import subprocess
from datetime import datetime
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

# --- Sibling Resolution ---
_DEFAULT_ADMIN_ROOT = str(Path(__file__).resolve().parent.parent.parent)
def get_admin_root():
    root_env = os.environ.get("ADMIN_ROOT")
    if root_env: return root_env
    return _DEFAULT_ADMIN_ROOT

ADMIN_ROOT = get_admin_root()
LIB_DIR = os.path.join(ADMIN_ROOT, 'libraries/Lib_PY/Core')
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

try:
    from lib_bejson_core import (
        bejson_core_acquire_lock, 
        bejson_core_release_lock,
        bejson_core_get_field_map
    )
    from lib_bejson_schema import SCHEMA_PROJECT_v140
except ImportError as e:
    print(f"Project Service Error: Dependencies missing. {e}")
    sys.exit(1)

# --- Legacy Fallback Constants (Phase 6.1.1) ---
_PROJECT_LEGACY = {
    "record_type_parent": 0, "project_id": 1, "project_name": 2, "project_path": 3,
    "version": 4, "created_at": 5, "project_type": 6, "is_active": 7,
    "is_visible": 8, "is_missing": 9, "description": 10, "tags": 11,
    "primary_agent": 12, "last_sync": 13, "file_count": 14, "total_size_kb": 15,
    "git_enabled": 16, "priority": 17, "category": 18, "internal_notes": 19,
    "is_archived": 20, "is_reset_protected": 21
}

_DEFAULT_ADMIN_DB = os.path.join(ADMIN_ROOT, 'data/centralized')
DB_FILE = os.path.join(os.environ.get('ADMIN_DB', _DEFAULT_ADMIN_DB), 'BE_Tracking.json')
PROJECTS_ROOT = os.environ.get('ADMIN_PROJECTS', os.path.join(ADMIN_ROOT, 'projects'))

import logging

class ProjectService:
    @staticmethod
    def _create_project_record(proj_id: str, name: str, path: str, p_type: str, created: str) -> List:
        """Helper to create a standardized v1.4.0 Project record (22 fields)."""
        record = [None] * 22
        
        # We assume the doc structure matches current v1.4.0 for initialization
        # but use mapping for safety if we had an existing doc context here.
        # Since this creates a NEW record for an implied schema, we use the constants.
        record[_PROJECT_LEGACY["record_type_parent"]] = 'Project'
        record[_PROJECT_LEGACY["project_id"]]         = proj_id
        record[_PROJECT_LEGACY["project_name"]]       = name
        record[_PROJECT_LEGACY["project_path"]]       = path
        record[_PROJECT_LEGACY["version"]]            = '0.0.1'
        record[_PROJECT_LEGACY["created_at"]]         = created
        record[_PROJECT_LEGACY["project_type"]]       = p_type
        record[_PROJECT_LEGACY["is_active"]]          = True
        record[_PROJECT_LEGACY["is_visible"]]         = True
        record[_PROJECT_LEGACY["is_missing"]]         = False
        record[_PROJECT_LEGACY["is_archived"]]        = False
        record[_PROJECT_LEGACY["is_reset_protected"]] = False
        return record

    @staticmethod
    def validate_record(record: List) -> bool:
        """Ensures record strictly adheres to the authoritative 22-field v1.4.0 schema."""
        if not isinstance(record, list) or len(record) != 22:
            logging.error(f"[ProjectService] Schema Violation: Expected 22 fields, got {len(record)}")
            return False
        if record[0] != 'Project':
            logging.error(f"[ProjectService] Record Type Mismatch: {record[0]}")
            return False
        return True

    @staticmethod
    def _load_db():
        if not os.path.exists(DB_FILE): return None
        with open(DB_FILE, 'r') as f:
            try: 
                doc = json.load(f)
                # REMEDIATED: Ensure all project records are padded to 22 fields (Audit Finding 5).
                if doc and "Values" in doc:
                    for i, row in enumerate(doc["Values"]):
                        if len(row) < 22:
                            padding = [None] * (22 - len(row))
                            doc["Values"][i] = row + padding
                return doc
            except json.JSONDecodeError: return None

    @staticmethod
    def _save_db(doc):
        if not doc: return
        with tempfile.NamedTemporaryFile('w', dir=os.path.dirname(DB_FILE), delete=False) as tf:
            json.dump(doc, tf, indent=2)
            tmp_name = tf.name
        os.replace(tmp_name, DB_FILE)

    @staticmethod
    def get_projects(project_type: str = None, include_archived: bool = False) -> List:
        doc = ProjectService._load_db()
        if not doc: return []
        
        fi = bejson_core_get_field_map(doc)
        rtp_idx      = fi.get("record_type_parent", _PROJECT_LEGACY["record_type_parent"])
        type_idx     = fi.get("project_type",       _PROJECT_LEGACY["project_type"])
        archived_idx = fi.get("is_archived",         _PROJECT_LEGACY["is_archived"])
        
        projects = [v for v in doc['Values'] if len(v) > rtp_idx and v[rtp_idx] == 'Project']
        if project_type:
            projects = [v for v in projects if len(v) > type_idx and v[type_idx] == project_type]
        if not include_archived:
            # REMEDIATED: Treat None as False for backward compatibility with padded records.
            projects = [v for v in projects if len(v) > archived_idx and v[archived_idx] is not True]
        return projects

    @staticmethod
    def add_project(name: str, p_type: str, path: str = None) -> bool:
        if not path:
            path = os.path.join(PROJECTS_ROOT, name.replace(" ", "_"))
        bejson_core_acquire_lock(DB_FILE)
        try:
            doc = ProjectService._load_db()
            if not doc: return False
            
            fi = bejson_core_get_field_map(doc)
            rtp_idx  = fi.get("record_type_parent", _PROJECT_LEGACY["record_type_parent"])
            name_idx = fi.get("project_name",       _PROJECT_LEGACY["project_name"])
            path_idx = fi.get("project_path",       _PROJECT_LEGACY["project_path"])
            
            norm_path = os.path.normpath(path)
            exists = any(len(v) > path_idx and (v[name_idx] == name or os.path.normpath(v[path_idx]) == norm_path)
                         for v in doc['Values'] if len(v) > rtp_idx and v[rtp_idx] == 'Project')
            if exists: return False
            
            if not os.path.exists(path): os.makedirs(path, exist_ok=True)
            proj_id = str(int(time.time() * 1000))
            created = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            record = ProjectService._create_project_record(proj_id, name, path, p_type, created)
            if ProjectService.validate_record(record):
                doc['Values'].append(record)
                ProjectService._save_db(doc)
                return True
            return False
        finally:
            bejson_core_release_lock(DB_FILE)

    @staticmethod
    def scan_and_sync():
        bejson_core_acquire_lock(DB_FILE)
        try:
            doc = ProjectService._load_db()
            if not doc: return
            
            fi = bejson_core_get_field_map(doc)
            rtp_idx     = fi.get("record_type_parent", _PROJECT_LEGACY["record_type_parent"])
            path_idx    = fi.get("project_path",       _PROJECT_LEGACY["project_path"])
            missing_idx = fi.get("is_missing",         _PROJECT_LEGACY["is_missing"])
            
            if os.path.exists(PROJECTS_ROOT):
                for item in os.listdir(PROJECTS_ROOT):
                    full_path = os.path.join(PROJECTS_ROOT, item)
                    if not os.path.isdir(full_path): continue
                    norm_path = os.path.normpath(full_path)
                    exists = any(len(v) > path_idx and os.path.normpath(v[path_idx]) == norm_path 
                                 for v in doc['Values'] if len(v) > rtp_idx and v[rtp_idx] == 'Project')
                    if not exists:
                        p_type = "python" if any(f.endswith('.py') for f in os.listdir(full_path)) else "bash"
                        proj_id = str(int(time.time() * 1000))
                        created = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        record = ProjectService._create_project_record(proj_id, item, full_path, p_type, created)
                        if ProjectService.validate_record(record): doc['Values'].append(record)
            
            for v in doc['Values']:
                if len(v) > rtp_idx and v[rtp_idx] == 'Project':
                    v[missing_idx] = not os.path.exists(v[path_idx]) # is_missing
            ProjectService._save_db(doc)
        finally:
            bejson_core_release_lock(DB_FILE)

    @staticmethod
    def get_project_path(name: str) -> Optional[str]:
        doc = ProjectService._load_db()
        if not doc: return None
        
        fi = bejson_core_get_field_map(doc)
        rtp_idx  = fi.get("record_type_parent", _PROJECT_LEGACY["record_type_parent"])
        name_idx = fi.get("project_name",       _PROJECT_LEGACY["project_name"])
        path_idx = fi.get("project_path",       _PROJECT_LEGACY["project_path"])
        
        for v in doc['Values']:
            if len(v) > name_idx and v[rtp_idx] == 'Project' and v[name_idx] == name: 
                return v[path_idx]
        return None

# Legacy Wrappers
def track_project(name, p_type, path=None): return ProjectService.add_project(name, p_type, path)
def list_projects(p_type=None, include_archived=False): return ProjectService.get_projects(p_type, include_archived)
def get_project_path(name): return ProjectService.get_project_path(name)

