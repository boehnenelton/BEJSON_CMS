"""
Library:         lib_bejson_AI_brain_audit.py
Family:          AI
Module Purpose:  Append-only audit trail of every Brain write, kept outside the memory database so rollback never erases history.
Architecture:    BEJSON 104 file brain_state/audit.bejson (audit_at, audit_actor, audit_action, audit_target, audit_ok, audit_detail). Trimmed to audit_max_rows. Also answers the AI write-rate question.
Version:         1.0.0
Release_Version: 300
Date:            2026-10-24
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   37c568ee-a9b5-4157-bc51-df5405ecedfd
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import lib_bejson_AI_brain_core_bridge  # noqa: F401
from lib_bejson_Core_bejson_core import ResilientPIDLock, bejson_core_atomic_write, bejson_core_get_field_map

VERSION = "1.0.0"
RELATIONAL_ID = "37c568ee-a9b5-4157-bc51-df5405ecedfd"
AUDIT_FILENAME = "audit.bejson"
_LOGGER = logging.getLogger("brain.audit")


class AuditF:
    AT = "audit_at"
    ACTOR = "audit_actor"
    ACTION = "audit_action"
    TARGET = "audit_target"
    OK = "audit_ok"
    DETAIL = "audit_detail"


_AUDIT_FIELDS = [
    (AuditF.AT, "string"), (AuditF.ACTOR, "string"), (AuditF.ACTION, "string"),
    (AuditF.TARGET, "string"), (AuditF.OK, "boolean"), (AuditF.DETAIL, "string"),
]


# Fresh empty audit document.
def _empty_document() -> dict:
    return {
        "Format": "BEJSON", "Format_Version": "104", "Format_Creator": "Elton Boehnen",
        "Records_Type": ["BrainAudit"],
        "Fields": [{"name": n, "type": t} for n, t in _AUDIT_FIELDS],
        "Values": [],
    }


# Reads the audit document, tolerating a missing or unreadable file (an unreadable audit log never blocks a write).
def _load(path: Path) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("Records_Type") == ["BrainAudit"]:
            return doc
    except (OSError, ValueError, AttributeError):
        pass
    return _empty_document()


# Appends one audit row. Never raises: auditing must not turn a successful write into a failure.
def brain_audit_append(state_dir: str | Path, at: datetime, actor: str, action: str, target: str, ok: bool, detail: str = "", max_rows: int = 2000) -> None:
    path = Path(state_dir) / AUDIT_FILENAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with ResilientPIDLock(str(path), timeout_seconds=5):
            doc = _load(path)
            row = {AuditF.AT: at.strftime("%Y-%m-%dT%H:%M:%SZ"), AuditF.ACTOR: actor, AuditF.ACTION: action,
                   AuditF.TARGET: target, AuditF.OK: bool(ok), AuditF.DETAIL: detail[:300]}
            fmap = bejson_core_get_field_map(doc)
            values = [None] * len(doc["Fields"])
            for name, index in fmap.items():
                values[index] = row.get(name)
            doc["Values"].append(values)
            if len(doc["Values"]) > max_rows:
                doc["Values"] = doc["Values"][-max_rows:]
            bejson_core_atomic_write(str(path), doc)
    except Exception as exc:  # noqa: BLE001 - audit must never break the caller
        _LOGGER.error("Audit append failed: %s", exc)


# Returns the last n audit rows as dicts, newest last.
def brain_audit_tail(state_dir: str | Path, n: int = 50) -> list[dict]:
    doc = _load(Path(state_dir) / AUDIT_FILENAME)
    fmap = bejson_core_get_field_map(doc)
    return [{name: row[index] for name, index in fmap.items()} for row in doc["Values"][-n:]]


# Counts successful AI write rows newer than `since`. Used for the writes-per-hour limit.
def brain_audit_count_ai_writes(state_dir: str | Path, now: datetime, window: timedelta = timedelta(hours=1)) -> int:
    cutoff = (now - window).strftime("%Y-%m-%dT%H:%M:%SZ")
    count = 0
    for row in brain_audit_tail(state_dir, 10_000):
        if row.get(AuditF.ACTOR) == "ai" and row.get(AuditF.OK) and str(row.get(AuditF.ACTION, "")).startswith("write:") \
                and str(row.get(AuditF.AT, "")) >= cutoff:
            count += 1
    return count
