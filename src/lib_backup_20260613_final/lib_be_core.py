"""
Library:      lib_be_core.py
Family:       Core
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.1.3 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-06-05
Description:  BE-specific core system abstractions and utility wrappers.
REMEDIATED:   Purged transition stubs for Core (Phase 1).
"""

import os
import sys
import time
from pathlib import Path

# --- Sibling Path Resolution ---
LIB_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_DIR = os.path.join(os.path.dirname(LIB_DIR), "Core")
if CORE_DIR not in sys.path: sys.path.insert(0, CORE_DIR)

from lib_bejson_core import ResilientPIDLock

_DEFAULT_ADMIN_ROOT = str(Path(__file__).resolve().parent.parent.parent)

def get_admin_root():
    # Priority: 1. ENV, 2. Root State File, 3. Inferred Parent
    root_env = os.environ.get("ADMIN_ROOT")
    if root_env: return root_env
    
    # Resolve storage root from env to avoid hardcodes
    storage_root = os.environ.get("BEJSON_STORAGE_ROOT")
    if storage_root:
        root_file = os.path.join(storage_root, "Admin/data/state/ADMIN_ROOT.txt")
        if os.path.exists(root_file):
            with open(root_file, 'r') as f: return f.read().strip()
            
    return _DEFAULT_ADMIN_ROOT

def save_state(manager, key, value):
    """Saves a key-value pair to a manager state file with locking to prevent races."""
    root = get_admin_root()
    state_file = os.path.join(root, f"data/state/{manager}_manager_state.txt")
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    
    with ResilientPIDLock(state_file, timeout_seconds=10):
        try:
            lines = []
            if os.path.exists(state_file):
                with open(state_file, 'r') as f: lines = f.readlines()
            
            key_found = False
            new_lines = []
            for line in lines:
                if line.startswith(f"{key}="):
                    new_lines.append(f"{key}={value}\n")
                    key_found = True
                else: new_lines.append(line)
            
            if not key_found: new_lines.append(f"{key}={value}\n")
            
            tmp_file = state_file + ".tmp"
            with open(tmp_file, 'w') as f:
                f.writelines(new_lines)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, state_file)
        except Exception as e:
            print(f"Error saving state: {e}")

def load_state(manager, key):
    root = get_admin_root()
    state_file = os.path.join(root, f"data/state/{manager}_manager_state.txt")
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            for line in f:
                if line.startswith(f"{key}="): return line.split("=", 1)[1].strip()
    return ""

def load_all_state(manager):
    root = get_admin_root()
    state_file = os.path.join(root, f"data/state/{manager}_manager_state.txt")
    state_dict = {}
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            for line in f:
                if "=" in line:
                    k, v = line.split("=", 1)
                    state_dict[k.strip()] = v.strip()
    return state_dict
