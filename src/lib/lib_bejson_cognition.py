"""
Library:      lib_bejson_cognition.py
Family:       Cognition
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.1.1 OFFICIAL (Security Hardening & Restoration)
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-06-02
Description:  Internal cognition and containment logic for autonomous agents.
REMEDIATED:   Fixed truncation, replaced wildcard imports, and added loud failure on import error.
"""

import json
import os
import sys
import uuid
import stat
import time
import random
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# --- Sibling Path Resolution ---
LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if LIB_DIR not in sys.path: sys.path.insert(0, LIB_DIR)

CORE_DIR = os.path.join(os.path.dirname(LIB_DIR), "Core")
if CORE_DIR not in sys.path: sys.path.insert(0, CORE_DIR)

try:
    from lib_bejson_core import (
        bejson_core_atomic_write, 
        bejson_core_load_file, 
        bejson_core_acquire_lock, 
        bejson_core_release_lock
    )
    from lib_mfdb_core import mfdb_core_resolve_path
    from lib_bejson_errors import (
        E_INVALID_JSON,
        E_FILE_NOT_FOUND,
        E_PERMISSION_DENIED,
        E_MFDB_CORE_LOCK_FAILED
    )
except ImportError as e:
    import logging
    logging.critical(f"[COGNITION] FATAL: Core security dependencies unreachable: {e}")
    raise SystemExit(1)

# Custom Error Code for Sandbox Violations
E_COGNITION_SANDBOX_VIOLATION = 403
E_COGNITION_LOCK_TIMEOUT = 275

BEJSON_COGNITION_SCHEMA = [
    {"name": "Record_Type_Parent", "type": "string"},
    {"name": "id", "type": "string", "Record_Type_Parent": "AgentState"},
    {"name": "timestamp", "type": "number", "Record_Type_Parent": "AgentState"},
    {"name": "last_checkpoint", "type": "string", "Record_Type_Parent": "AgentState"},
    {"name": "core_directives", "type": "object", "Record_Type_Parent": "AgentState"},
    {"name": "summary_blob", "type": "string", "Record_Type_Parent": "AgentState"},
    {"name": "stack_id", "type": "string", "Record_Type_Parent": "ExecutionStack"},
    {"name": "agent_id_fk", "type": "string", "Record_Type_Parent": "ExecutionStack"},
    {"name": "stack_timestamp", "type": "number", "Record_Type_Parent": "ExecutionStack"},
    {"name": "task_queue", "type": "array", "Record_Type_Parent": "ExecutionStack"},
    {"name": "pending_context", "type": "object", "Record_Type_Parent": "ExecutionStack"},
    {"name": "log_id", "type": "string", "Record_Type_Parent": "EpisodicLog"},
    {"name": "log_timestamp", "type": "number", "Record_Type_Parent": "EpisodicLog"},
    {"name": "user_input", "type": "string", "Record_Type_Parent": "EpisodicLog"},
    {"name": "agent_response", "type": "string", "Record_Type_Parent": "EpisodicLog"},
    {"name": "payloads_used", "type": "array", "Record_Type_Parent": "EpisodicLog"}
]

def bejson_cognition_check_sandbox(task_name: str) -> bool:
    """Checks if an operation is permitted by the current sandbox state."""
    sandbox_file = mfdb_core_resolve_path("{INTERNAL_STORAGE}/Admin/data/policy/sandbox_state.json")
    if os.path.exists(sandbox_file):
        try:
            with open(sandbox_file, "r") as f:
                state = json.load(f)
                if state.get("sandbox_enabled"):
                    logging.error(f"[SECURITY_BLOCK] Task '{task_name}' blocked by sandbox. Code: {E_COGNITION_SANDBOX_VIOLATION}")
                    return True # Is Blocked
        except Exception as e:
            logging.warning(f"[COGNITION] Sandbox check failed: {e}")
    return False # Not Blocked

def bejson_cognition_safe_write(filepath: str, data: dict, max_retries: int = 50) -> bool:
    """High-resilience atomic writer with randomized exponential backoff."""
    resolved_path = mfdb_core_resolve_path(filepath)
    attempt = 0
    base_sleep = 0.5
    while attempt < max_retries:
        if bejson_core_acquire_lock(resolved_path, timeout=5):
            try:
                return bejson_core_atomic_write(resolved_path, data)
            finally:
                bejson_core_release_lock(resolved_path)
        attempt += 1
        sleep_time = min(base_sleep * (2 ** attempt), 20) + random.uniform(0, 5)
        logging.warning(f"[COGNITION] Lock contention. Retrying in {sleep_time:.2f}s...")
        time.sleep(sleep_time)
    return False

def bejson_cognition_init_matrix(db_path: str) -> dict:
    resolved_path = mfdb_core_resolve_path(db_path)
    doc = bejson_core_load_file(resolved_path) if os.path.exists(resolved_path) else None
    if doc and doc.get("Format_Version") == "104db": return doc
    return {
        "Format": "BEJSON", "Format_Version": "104db", "Format_Creator": "Elton Boehnen",
        "Records_Type": ["AgentState", "ExecutionStack", "EpisodicLog"],
        "Fields": BEJSON_COGNITION_SCHEMA, "Values": []
    }

def bejson_cognition_query(doc: dict, record_type: str, filters: dict = None) -> List[dict]:
    results = []
    field_indices = {f["name"]: i for i, f in enumerate(doc["Fields"])}
    for row in doc.get("Values", []):
        if row[0] == record_type:
            record = {f["name"]: row[field_indices[f["name"]]] for f in doc["Fields"] if f.get("Record_Type_Parent") in [record_type, None]}
            if not filters or all(record.get(k) == v for k, v in filters.items()):
                results.append({k: v for k, v in record.items() if v is not None})
    return results

def bejson_cognition_upsert(doc: dict, record_type: str, record_id: str, **kwargs) -> dict:
    field_indices = {f["name"]: i for i, f in enumerate(doc["Fields"])}
    id_field = {"AgentState": "id", "ExecutionStack": "stack_id", "EpisodicLog": "log_id"}.get(record_type, "id")
    ts_field = {"AgentState": "timestamp", "ExecutionStack": "stack_timestamp", "EpisodicLog": "log_timestamp"}.get(record_type, "timestamp")

    target_idx = next((i for i, r in enumerate(doc["Values"]) if r[0] == record_type and r[field_indices[id_field]] == record_id), -1)
    
    row_data = list(doc["Values"][target_idx]) if target_idx != -1 else [None] * len(doc["Fields"])
    row_data[0] = record_type
    row_data[field_indices[id_field]] = record_id
    row_data[field_indices[ts_field]] = time.time()
    
    for key, val in kwargs.items():
        if key in field_indices: row_data[field_indices[key]] = val
    
    if target_idx != -1: doc["Values"][target_idx] = row_data
    else: doc["Values"].append(row_data)
    return doc

def bejson_cognition_apply_patches(index_path: str, db_path: str, patches: List[dict]):
    """Applies a list of patches to the cognitive matrix and system tools."""
    index_doc = bejson_core_load_file(mfdb_core_resolve_path(index_path))
    db_doc = bejson_core_load_file(mfdb_core_resolve_path(db_path))
    
    if not index_doc or not db_doc:
        logging.error("[COGNITION] Failed to load documents for patch application.")
        return

    for patch in patches:
        instr = patch.get("instruction", {})
        
        # --- LAYER: Tooling (Forge) ---
        if patch["target_layer"] == "Tooling" and instr.get("action") == "FORGE_TOOL":
            try:
                metadata = instr.get("tool_metadata", {})
                filename = metadata.get("filename")
                code = instr.get("code")
                
                if not filename or not code:
                    logging.error(f"[COGNITION] Patch {patch['patch_id']} missing filename or code.")
                    continue
                
                # 1. Forge the physical tool
                tools_dir = mfdb_core_resolve_path("{INTERNAL_STORAGE}/Admin/tools")
                os.makedirs(tools_dir, exist_ok=True)
                tool_path = os.path.join(tools_dir, os.path.basename(filename))
                
                with open(tool_path, "w") as f:
                    f.write(code)
                
                # 2. Apply executable permissions
                st = os.stat(tool_path)
                os.chmod(tool_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
                
                # 3. Register in CLITool Registry
                registry_path = mfdb_core_resolve_path("{INTERNAL_STORAGE}/Admin/init/registry/mfdb_layers/data/clitool.bejson")
                registry_doc = bejson_core_load_file(registry_path)
                
                if registry_doc and "Values" in registry_doc:
                    new_record = [
                        metadata.get("name", "Generated Tool"),
                        metadata.get("identifier", uuid.uuid4().hex[:8]),
                        tool_path,
                        metadata.get("version", "1.0.0"),
                        metadata.get("description", "Autonomously forged tool."),
                        True,
                        "boehnenelton2024@gmail.com",
                        "boehnenelton2024.pages.dev",
                        f"guid-forge-{uuid.uuid4().hex[:8]}",
                        datetime.now(timezone.utc).isoformat(),
                        "forge-session"
                    ]
                    registry_doc["Values"].append(new_record)
                    bejson_core_atomic_write(registry_path, registry_doc)
                
                db_doc = bejson_cognition_upsert(db_doc, "MetaPatch", patch["patch_id"], status="applied")
                logging.info(f"[COGNITION] Tool '{filename}' forged and registered successfully.")
                
            except Exception as e:
                logging.error(f"[COGNITION] Failed to forge tool in patch {patch['patch_id']}: {e}")
                db_doc = bejson_cognition_upsert(db_doc, "MetaPatch", patch["patch_id"], status="failed")

        # --- LAYER: Orchestration (The Hive Mind) ---
        elif patch["target_layer"] == "Orchestration" and instr.get("action") == "SPAWN_AGENT":
            try:
                agent_id = instr.get("agent_id")
                persona = instr.get("persona", "Worker")
                initial_task = instr.get("initial_task")
                
                if not agent_id or not initial_task:
                    logging.error(f"[COGNITION] SPAWN_AGENT patch {patch['patch_id']} missing agent_id or task.")
                    continue
                
                # 1. Initialize AgentState
                db_doc = bejson_cognition_upsert(
                    db_doc, "AgentState", agent_id,
                    core_directives={"persona": persona, "status": "active"},
                    summary_blob="Initialized by Orchestrator.",
                    last_checkpoint=datetime.now(timezone.utc).isoformat()
                )
                
                # 2. Initialize ExecutionStack with task
                db_doc = bejson_cognition_upsert(
                    db_doc, "ExecutionStack", f"STK-{agent_id}",
                    agent_id_fk=agent_id,
                    task_queue=[{"task_id": uuid.uuid4().hex[:4], "description": initial_task, "status": "pending", "result": None}],
                    pending_context={}
                )
                
                logging.info(f"[COGNITION] Hive Mind: Spawned sub-agent {agent_id}.")
                db_doc = bejson_cognition_upsert(db_doc, "MetaPatch", patch["patch_id"], status="applied")
                
            except Exception as e:
                logging.error(f"[COGNITION] Failed to spawn agent in patch {patch['patch_id']}: {e}")
                db_doc = bejson_cognition_upsert(db_doc, "MetaPatch", patch["patch_id"], status="failed")

    bejson_cognition_safe_write(index_path, index_doc)
    bejson_cognition_safe_write(db_path, db_doc)
