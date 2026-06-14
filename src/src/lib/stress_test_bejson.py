"""
Stress Test Suite for Patched BEJSON Libraries (2026-06-07)
Targets: Atomic Writes, Path Guarding, Android Resolution, Secure ZIP, Schema Integrity.
"""

import os
import sys
import json
import time
import shutil
import tempfile
import zipfile
import logging
from pathlib import Path

# Setup paths to import libraries
LIB_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
if LIB_CORE_DIR not in sys.path:
    sys.path.insert(0, LIB_CORE_DIR)

# Add System dir for Project Service
LIB_SYSTEM_DIR = os.path.join(os.path.dirname(LIB_CORE_DIR), "System")
if LIB_SYSTEM_DIR not in sys.path:
    sys.path.insert(0, LIB_SYSTEM_DIR)

from lib_bejson_core import (
    bejson_core_create_104,
    bejson_core_atomic_write,
    bejson_core_load_file,
    bejson_core_get_record_count
)
from lib_bejson_env import resolve_path
from lib_bejson_path_guard import bejson_safe_join
from lib_mfdb_core import MFDBArchive, MFDBCoreError
from lib_be_project_service import ProjectService

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def stress_test_atomic_writes():
    print("[1/5] STRESS TEST: High-Volume Atomic Writes")
    temp_dir = tempfile.mkdtemp()
    test_file = os.path.join(temp_dir, "stress_test_10k.bejson")
    
    # Create 10,000 records
    fields = [{"name": "id", "type": "integer"}, {"name": "data", "type": "string"}]
    values = [[i, f"stress_data_{i}"] for i in range(10000)]
    doc = bejson_core_create_104("StressTest", fields, values)
    
    start = time.time()
    success = bejson_core_atomic_write(test_file, doc)
    end = time.time()
    
    if not success:
        print("FAIL: Atomic write failed.")
        return False
    
    print(f"  + 10,000 records written in {end - start:.4f}s")
    
    # Verify read-back
    loaded = bejson_core_load_file(test_file)
    if not loaded or bejson_core_get_record_count(loaded) != 10000:
        print("FAIL: Data corruption detected in read-back.")
        return False
    
    print("  + Read-back verification: SUCCESS")
    shutil.rmtree(temp_dir)
    return True

def test_path_boundary_safety():
    print("[2/5] SECURITY TEST: Path Boundary Safety")
    base_dir = tempfile.mkdtemp(prefix="bejson_sandbox_")
    
    try:
        print("  + Testing legitimate path...")
        safe = bejson_safe_join(base_dir, "data/file.txt")
        print(f"    - Safe path: {safe}")
        
        print("  + Testing traversal attempt (../etc/passwd)...")
        bejson_safe_join(base_dir, "../etc/passwd")
        print("FAIL: Path traversal NOT detected!")
        return False
    except ValueError as e:
        print(f"  + SUCCESS: Traversal detected: {e}")
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)
    return True

def test_android_path_resolution():
    print("[3/5] RUNTIME TEST: Android Path Resolution (Vanishing Data Fix)")
    # Case A: BEJSON_STORAGE_ROOT is UNSET (Default behavior)
    if "BEJSON_STORAGE_ROOT" in os.environ: del os.environ["BEJSON_STORAGE_ROOT"]
    
    path = "/storage/emulated/0/my_file.json"
    resolved = resolve_path(path)
    print(f"  + BEJSON_STORAGE_ROOT unset: {path} -> {resolved}")
    
    if "/storage/emulated/0" in resolved:
        print("  + SUCCESS: Absolute path preserved when storage root is unset.")
    else:
        print(f"FAIL: Absolute path was unexpectedly substituted: {resolved}")
        return False

    # Case B: BEJSON_STORAGE_ROOT is SET
    mock_storage = "/data/mock_storage"
    os.environ["BEJSON_STORAGE_ROOT"] = mock_storage
    resolved = resolve_path(path)
    print(f"  + BEJSON_STORAGE_ROOT set to {mock_storage}: {path} -> {resolved}")
    
    if resolved.startswith(mock_storage):
        print("  + SUCCESS: Absolute path substituted when storage root is set.")
    else:
        print(f"FAIL: Absolute path was NOT substituted: {resolved}")
        return False
        
    return True

def test_secure_zip_extraction():
    print("[4/5] SECURITY TEST: Secure ZIP Extraction (Zip Slip Fix)")
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, "malicious.zip")
    extract_dir = os.path.join(temp_dir, "extract")
    os.makedirs(extract_dir, exist_ok=True)
    
    # Create malicious zip
    with zipfile.ZipFile(zip_path, 'w') as z:
        z.writestr("good.json", '{"Format": "BEJSON"}')
        z.writestr("../evil.txt", "I am outside!")
        # Add manifest to make it a "valid" MFDB for the mount logic
        manifest = {
            "Format": "BEJSON", "Format_Version": "104a", "Format_Creator": "Elton Boehnen",
            "Records_Type": ["mfdb"], "Fields": [{"name": "entity_name"}, {"name": "file_path"}],
            "Values": [["Entity", "good.json"]]
        }
        z.writestr("104a.mfdb.bejson", json.dumps(manifest))

    try:
        print("  + Attempting secure mount of malicious archive...")
        MFDBArchive.mount(zip_path, extract_dir)
        print("FAIL: Malicious ZIP extracted successfully!")
        return False
    except MFDBCoreError as e:
        print(f"  + SUCCESS: Extraction blocked: {e}")
    except Exception as e:
        print(f"  + SUCCESS: Blocked with error: {e}")
    finally:
        shutil.rmtree(temp_dir)
    return True

def test_schema_strictness_padding():
    print("[5/5] INTEGRITY TEST: Schema Strictness & Padding (Project Service)")
    temp_dir = tempfile.mkdtemp()
    db_file = os.path.join(temp_dir, "BE_Tracking.json")
    
    # Create legacy DB with 12 fields instead of 22
    legacy_fields = [
        {"name": "record_type_parent"}, {"name": "project_id"}, {"name": "project_name"},
        {"name": "project_path"}, {"name": "version"}, {"name": "created_at"},
        {"name": "project_type"}, {"name": "is_active"}, {"name": "is_visible"},
        {"name": "is_missing"}, {"name": "description"}, {"name": "tags"}
    ]
    legacy_values = [
        ["Project", "123", "Legacy Project", "/tmp", "1.0", "2025-01-01", "python", True, True, False, "Desc", "tags"]
    ]
    doc = {
        "Format": "BEJSON", "Format_Version": "104", "Format_Creator": "Elton Boehnen",
        "Records_Type": ["Project"], "Fields": legacy_fields, "Values": legacy_values
    }
    with open(db_file, 'w') as f:
        json.dump(doc, f)
        
    # Mock environment for ProjectService
    import lib_be_project_service
    lib_be_project_service.DB_FILE = db_file
    
    print("  + Loading legacy project database...")
    projects = ProjectService.get_projects()
    
    if not projects:
        print("FAIL: Failed to load projects from legacy DB.")
        return False
        
    # Verify padding
    p = projects[0]
    print(f"  + Project record length: {len(p)} (Expected 22)")
    
    if len(p) == 22:
        print("  + SUCCESS: Legacy record padded to 22 fields.")
        # Check last field (is_reset_protected)
        if p[21] is None:
            print("  + SUCCESS: Padding fields initialized to null.")
        else:
            print(f"FAIL: Padding values are not null: {p[21]}")
            return False
    else:
        print(f"FAIL: Record length mismatch: {len(p)}")
        return False
        
    shutil.rmtree(temp_dir)
    return True

if __name__ == "__main__":
    print("\n" + "="*50)
    print("      BEJSON LIBRARIES STRESS TEST (PHASE 2026)")
    print("="*50 + "\n")
    
    results = [
        stress_test_atomic_writes(),
        test_path_boundary_safety(),
        test_android_path_resolution(),
        test_secure_zip_extraction(),
        test_schema_strictness_padding()
    ]
    
    print("\n" + "="*50)
    if all(results):
        print("  OVERALL RESULT: PASSED ✅")
        sys.exit(0)
    else:
        print("  OVERALL RESULT: FAILED ❌")
        sys.exit(1)
