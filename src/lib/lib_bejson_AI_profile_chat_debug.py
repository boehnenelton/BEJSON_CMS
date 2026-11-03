"""
Library:         lib_bejson_AI_profile_chat_debug.py
Family:          AI
Module Purpose:  Debug logging, telemetry event streaming, and persistent gate management for ProfileChat Standard. Backed by BEJSON 104a (debug/logs/timestamp.bejson) with Field Map Cache and atomic writes.
Architecture:    Stdlib + BEJSON Core 104a primitives. Provides thread-safe append operations, in-memory subscriber ring buffers for real-time SSE terminal streaming, and masked keyslot resolution.
Version:         1.0.0
Release_Version: 300
Date:            2026-10-30
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   7c38bf64-219e-4a6c-9c56-f6c6d0549c81

Changelog:
  1.0.0 (2026-10-30) -- Initial modular release: BEJSON 104a debug logger with Record, Service, Engine, Tikmestp, Keyslot_ID, Timestamp, Session_ID fields; in-memory streaming listener queue for overlay terminal; masked keyslot resolution.
"""

import hashlib
import json
import logging
import os
import queue
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# --- Sibling Resolution ---
LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

CORE_DIR = os.path.join(os.path.dirname(LIB_DIR), "Core")
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

from lib_bejson_Core_bejson_core import (
    bejson_core_atomic_write,
    bejson_core_get_field_map,
    bejson_core_load_file,
)

logger = logging.getLogger("lib_bejson_AI_profile_chat_debug")

VERSION = "1.0.0"
DEBUG_LOG_FILENAME = "timestamp.bejson"

# Strict BEJSON 104a Schema matching user directive
# Log fields: Record, Service, Engine, Tikmestp, Keyslot_ID, Timestamp, Session_ID
SCHEMA_DEBUG_LOG = {
    "Format": "BEJSON",
    "Format_Version": "104a",
    "Format_Creator": "Elton Boehnen",
    "Schema_Name": "DebugLog",
    "Records_Type": ["DebugEntry"],
    "Fields": [
        {"name": "Record", "type": "string"},
        {"name": "Service", "type": "string"},
        {"name": "Engine", "type": "string"},
        {"name": "Tikmestp", "type": "string"},
        {"name": "Keyslot_ID", "type": "string"},
        {"name": "Timestamp", "type": "string"},
        {"name": "Session_ID", "type": "string"},
    ],
    "Values": [],
}

# In-memory streaming fan-out & ring buffer
_DEBUG_LOCK = threading.Lock()
_DEBUG_SUBSCRIBERS: List[queue.Queue] = []
_MAX_RING_ENTRIES = 200
_RING_BUFFER: List[Dict[str, Any]] = []


def debug_keyslot_resolve(api_key: Optional[str], env_prefix: str = "GEMINI_KEY", max_slots: int = 30) -> str:
    """
    Resolves the human-readable keyslot identifier (e.g. GEMINI_KEY_1, GEMINI_KEY_2)
    by matching against populated environment variables without exposing raw secret material.
    Falls back to a non-reversible SHA-256 key#hash.
    """
    if not api_key:
        return "none"

    clean_key = str(api_key).strip()

    # Check numbered environment slots (Section 4.2 convention)
    for i in range(1, max_slots + 1):
        slot_name = f"{env_prefix}_{i}"
        slot_val = os.environ.get(slot_name, "").strip()
        if slot_val and slot_val == clean_key:
            return slot_name

    # Check common single env vars
    for env_name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY"):
        val = os.environ.get(env_name, "").strip()
        if val and val == clean_key:
            return env_name

    # Non-reversible SHA-256 tag fallback
    key_tag = "key#" + hashlib.sha256(clean_key.encode("utf-8")).hexdigest()[:6]
    return f"slot_custom ({key_tag})"


def debug_log_get_path(debug_root: Union[str, Path]) -> Path:
    """Returns the canonical path: <debug_root>/logs/timestamp.bejson."""
    return Path(debug_root) / "logs" / DEBUG_LOG_FILENAME


def debug_log_append(
    debug_root: Union[str, Path],
    service: str,
    engine: str,
    keyslot_id: str,
    session_id: str,
    timestamp: Optional[str] = None,
    tikmestp: Optional[str] = None,
    record_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Appends a new telemetry record to <debug_root>/logs/timestamp.bejson using Field Map Cache
    and broadcasts the event to all active streaming subscribers.
    """
    now_utc = datetime.now(timezone.utc)
    ts_str = timestamp or now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    tik_str = tikmestp or str(int(now_utc.timestamp() * 1000))

    log_path = debug_log_get_path(debug_root)

    with _DEBUG_LOCK:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            doc = None
            if log_path.is_file():
                doc = bejson_core_load_file(str(log_path))

            if not doc or "Fields" not in doc:
                doc = {
                    "Format": "BEJSON",
                    "Format_Version": "104a",
                    "Format_Creator": "Elton Boehnen",
                    "Schema_Name": "DebugLog",
                    "Records_Type": ["DebugEntry"],
                    "Fields": list(SCHEMA_DEBUG_LOG["Fields"]),
                    "Values": [],
                }

            values = doc.get("Values", [])
            rec_id = record_id or str(len(values) + 1)

            entry_dict = {
                "Record": rec_id,
                "Service": str(service or "gemini"),
                "Engine": str(engine or "interactions"),
                "Tikmestp": tik_str,
                "Keyslot_ID": str(keyslot_id or "unknown"),
                "Timestamp": ts_str,
                "Session_ID": str(session_id or "default"),
            }

            fmap = bejson_core_get_field_map(doc)
            row = [""] * len(doc["Fields"])
            for field_name, field_val in entry_dict.items():
                if field_name in fmap:
                    row[fmap[field_name]] = field_val

            values.append(row)
            doc["Values"] = values

            bejson_core_atomic_write(str(log_path), doc)

            # Update memory ring buffer
            _RING_BUFFER.append(entry_dict)
            if len(_RING_BUFFER) > _MAX_RING_ENTRIES:
                _RING_BUFFER.pop(0)

            # Broadcast to live SSE queues
            dead_subscribers = []
            for sub_queue in _DEBUG_SUBSCRIBERS:
                try:
                    sub_queue.put_nowait(entry_dict)
                except queue.Full:
                    dead_subscribers.append(sub_queue)
            for dead in dead_subscribers:
                if dead in _DEBUG_SUBSCRIBERS:
                    _DEBUG_SUBSCRIBERS.remove(dead)

            return entry_dict
        except Exception as exc:
            logger.error("Failed to append debug log to %s: %s", log_path, exc)
            return {
                "Record": "err",
                "Service": str(service),
                "Engine": str(engine),
                "Tikmestp": tik_str,
                "Keyslot_ID": str(keyslot_id),
                "Timestamp": ts_str,
                "Session_ID": str(session_id),
                "error": str(exc),
            }


def debug_log_read(debug_root: Union[str, Path], limit: int = 100) -> List[Dict[str, Any]]:
    """
    Reads entries from <debug_root>/logs/timestamp.bejson using O(1) Field Map Cache.
    Returns the most recent entries up to `limit`.
    """
    log_path = debug_log_get_path(debug_root)
    with _DEBUG_LOCK:
        if not log_path.is_file():
            return list(_RING_BUFFER[-limit:])

        try:
            doc = bejson_core_load_file(str(log_path))
            if not doc or "Fields" not in doc:
                return []
            fmap = bejson_core_get_field_map(doc)
            records = []
            for row in doc.get("Values", []):
                rec = {
                    "Record": str(row[fmap.get("Record", 0)]) if "Record" in fmap else "",
                    "Service": str(row[fmap.get("Service", 1)]) if "Service" in fmap else "",
                    "Engine": str(row[fmap.get("Engine", 2)]) if "Engine" in fmap else "",
                    "Tikmestp": str(row[fmap.get("Tikmestp", 3)]) if "Tikmestp" in fmap else "",
                    "Keyslot_ID": str(row[fmap.get("Keyslot_ID", 4)]) if "Keyslot_ID" in fmap else "",
                    "Timestamp": str(row[fmap.get("Timestamp", 5)]) if "Timestamp" in fmap else "",
                    "Session_ID": str(row[fmap.get("Session_ID", 6)]) if "Session_ID" in fmap else "",
                }
                records.append(rec)
            return records[-limit:]
        except Exception as exc:
            logger.error("Failed to read debug log %s: %s", log_path, exc)
            return list(_RING_BUFFER[-limit:])


def debug_log_clear(debug_root: Union[str, Path]) -> bool:
    """Resets <debug_root>/logs/timestamp.bejson to an empty BEJSON 104a document."""
    log_path = debug_log_get_path(debug_root)
    with _DEBUG_LOCK:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            doc = {
                "Format": "BEJSON",
                "Format_Version": "104a",
                "Format_Creator": "Elton Boehnen",
                "Schema_Name": "DebugLog",
                "Records_Type": ["DebugEntry"],
                "Fields": list(SCHEMA_DEBUG_LOG["Fields"]),
                "Values": [],
            }
            bejson_core_atomic_write(str(log_path), doc)
            _RING_BUFFER.clear()
            return True
        except Exception as exc:
            logger.error("Failed to clear debug log %s: %s", log_path, exc)
            return False


def debug_stream_subscribe() -> queue.Queue:
    """Registers a thread-safe queue for SSE streaming."""
    q: queue.Queue = queue.Queue(maxsize=100)
    with _DEBUG_LOCK:
        _DEBUG_SUBSCRIBERS.append(q)
    return q


def debug_stream_unsubscribe(q: queue.Queue) -> None:
    """Unregisters an SSE streaming queue."""
    with _DEBUG_LOCK:
        if q in _DEBUG_SUBSCRIBERS:
            _DEBUG_SUBSCRIBERS.remove(q)
