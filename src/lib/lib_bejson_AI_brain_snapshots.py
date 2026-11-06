"""
Library:         lib_bejson_AI_brain_snapshots.py
Family:          AI
Module Purpose:  Tiered snapshots of the Brain database (default, daily, monthly), retention, validated rollback with a safety snapshot.
Architecture:    Each snapshot is one MFDB-132 packaged document (Chunked-104a) at snapshots/<tier>/<YYYYMMDDTHHMMSSZ>_brain_snapshot.bejson carrying Brain_Snapshot_Reason and Brain_Content_Hash headers. Packaging reads a lock-free copy of brain_mfdb/, so no .lockdir ever enters a snapshot. Rollback validates, takes a pre-rollback safety snapshot, unpacks to brain_state/staging/, verifies the content hash and swaps by rename.
Version:         1.0.0
Release_Version: 300
Date:            2026-10-24
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   8c1c7a59-1c48-4050-9e45-1f36f3dd72df
"""

import json
import logging
import shutil
from pathlib import Path

import lib_bejson_AI_brain_core_bridge  # noqa: F401
from lib_bejson_Core_bejson_core import bejson_core_atomic_write
from lib_bejson_Core_bejson_chunking import (
    bejson_core_chunking_create_mfdb132_package, bejson_core_chunking_is_mfdb132_package,
    bejson_core_chunking_unchunk_mfdb132_package, bejson_core_chunking_validate_mfdb132_package,
)
from lib_bejson_Core_bejson_path_guard import bejson_safe_join
from lib_bejson_Core_mfdb_core import mfdb_core_deep_verify

import lib_bejson_AI_brain_audit as audit
from lib_bejson_AI_brain_errors import (
    BrainError, E_BRAIN_PATH_GUARD, E_BRAIN_ROLLBACK_VERIFY_FAILED, E_BRAIN_SNAPSHOT_INVALID,
    E_BRAIN_SNAPSHOT_NOT_FOUND, E_BRAIN_SNAPSHOT_PACKAGE_FAILED,
)
from lib_bejson_AI_brain_schema_registry import DB_NAME
from lib_bejson_AI_brain_store import BrainStore, MANIFEST_FILENAME, brain_store_hash_manifest

VERSION = "1.0.0"
RELATIONAL_ID = "8c1c7a59-1c48-4050-9e45-1f36f3dd72df"
_LOGGER = logging.getLogger("brain.snapshots")

TIER_DEFAULT = "default"
TIER_DAILY = "daily"
TIER_MONTHLY = "monthly"
TIERS = (TIER_DEFAULT, TIER_DAILY, TIER_MONTHLY)
REASON_BASELINE = "baseline"
SNAPSHOT_SUFFIX = "_brain_snapshot.bejson"

HDR_REASON = "Brain_Snapshot_Reason"
HDR_HASH = "Brain_Content_Hash"
HDR_CREATED = "Brain_Snapshot_Created_At"
HDR_TIER = "Brain_Snapshot_Tier"
HDR_SCHEMA = "Brain_Schema_Version"


# Directory of one tier.
def _tier_dir(store: BrainStore, tier: str) -> Path:
    return store.snapshot_dir / tier


# Reads a snapshot file's headers. Returns None when it is not a readable JSON object.
def _read_headers(path: Path) -> dict | None:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict):
        return None
    return {"created_at": doc.get(HDR_CREATED), "reason": doc.get(HDR_REASON), "hash": doc.get(HDR_HASH), "tier": doc.get(HDR_TIER)}


# All snapshots (optionally of one tier), newest first.
def snapshots_list(store: BrainStore, tier: str | None = None) -> list[dict]:
    entries = []
    for t in ([tier] if tier else TIERS):
        folder = _tier_dir(store, t)
        if not folder.is_dir():
            continue
        for path in folder.glob("*" + SNAPSHOT_SUFFIX):
            headers = _read_headers(path)
            if headers is None:
                entries.append({"tier": t, "filename": path.name, "path": str(path), "created_at": None, "reason": None, "hash": None, "valid": False})
            else:
                entries.append({"tier": t, "filename": path.name, "path": str(path), "valid": True,
                                "created_at": headers["created_at"], "reason": headers["reason"], "hash": headers["hash"]})
    entries.sort(key=lambda e: e["filename"], reverse=True)
    return entries


# Writes a snapshot of the current state into a tier and prunes that tier. Returns the new entry.
def snapshots_create(store: BrainStore, tier: str, reason: str) -> dict:
    if tier not in TIERS:
        raise BrainError(E_BRAIN_SNAPSHOT_INVALID, f"Unknown snapshot tier '{tier}'.")
    with store.locked():
        scratch = store.state_dir / "snapshot_tmp"
        if scratch.exists():
            shutil.rmtree(scratch)
        copy_dir = scratch / "db"
        try:
            # Copy without any lock directories, then package the copy: the package can never contain lock state.
            shutil.copytree(store.db_dir, copy_dir, ignore=shutil.ignore_patterns("*.lockdir*", "*.tmp"))
            doc = bejson_core_chunking_create_mfdb132_package(str(copy_dir), DB_NAME)
            content_hash = brain_store_hash_manifest(str(copy_dir / MANIFEST_FILENAME))
        except (OSError, ValueError, KeyError) as exc:
            raise BrainError(E_BRAIN_SNAPSHOT_PACKAGE_FAILED, f"Could not package the snapshot: {exc}") from exc
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        moment = store.now()
        folder = _tier_dir(store, tier)
        folder.mkdir(parents=True, exist_ok=True)
        from datetime import timedelta
        while (folder / (moment.strftime("%Y%m%dT%H%M%SZ") + SNAPSHOT_SUFFIX)).exists():
            moment += timedelta(seconds=1)
        doc[HDR_REASON] = reason
        doc[HDR_HASH] = content_hash
        doc[HDR_CREATED] = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
        doc[HDR_TIER] = tier
        path = folder / (moment.strftime("%Y%m%dT%H%M%SZ") + SNAPSHOT_SUFFIX)
        if not bejson_core_atomic_write(str(path), doc):
            raise BrainError(E_BRAIN_SNAPSHOT_PACKAGE_FAILED, "Could not write the snapshot file.", {"path": str(path)})
        snapshots_prune(store, tier)
        audit.brain_audit_append(store.state_dir, store.now(), "user", f"snapshot:{tier}", path.name, True, reason, int(store.limits["audit_max_rows"]))
        return {"tier": tier, "filename": path.name, "path": str(path), "created_at": doc[HDR_CREATED], "reason": reason, "hash": content_hash, "valid": True}


# Creates a snapshot only when the content differs from the newest snapshot of that tier. Returns the entry or None.
def snapshots_create_if_changed(store: BrainStore, tier: str, reason: str) -> dict | None:
    newest = snapshots_list(store, tier)
    if newest and newest[0].get("hash") == store.content_hash():
        return None
    return snapshots_create(store, tier, reason)


# Applies the retention rule of a tier. Default: the baseline plus the newest N others. Daily/monthly: the newest N.
def snapshots_prune(store: BrainStore, tier: str) -> list[str]:
    entries = snapshots_list(store, tier)
    removed: list[str] = []
    if tier == TIER_DEFAULT:
        baseline = next((e for e in entries if e["reason"] == REASON_BASELINE), None)
        others = [e for e in entries if e is not baseline]
        doomed = others[int(store.limits["snapshot_default_keep"]):]
    elif tier == TIER_DAILY:
        doomed = entries[int(store.limits["snapshot_daily_keep"]):]
    else:
        doomed = entries[int(store.limits["snapshot_monthly_keep"]):]
    for entry in doomed:
        try:
            Path(entry["path"]).unlink()
            removed.append(entry["filename"])
        except OSError as exc:
            _LOGGER.error("Could not prune %s: %s", entry["path"], exc)
    return removed


# Daily and monthly tiers: at most one new snapshot per UTC day / month, and only when the content changed since the previous one in that tier.
def snapshots_maintain(store: BrainStore) -> list[dict]:
    created = []
    now_text, current_hash = store.now_text(), store.content_hash()
    for tier, width in ((TIER_DAILY, 10), (TIER_MONTHLY, 7)):
        latest = snapshots_list(store, tier)
        if not latest:
            created.append(snapshots_create(store, tier, tier))
            continue
        newest = latest[0]
        if newest["hash"] != current_hash and (newest["created_at"] or "")[:width] != now_text[:width]:
            created.append(snapshots_create(store, tier, tier))
    return created


# Resolves a snapshot reference ("<tier>/<filename>" or a bare filename) to an existing path inside snapshots/. Raises on traversal or absence.
def _resolve_snapshot(store: BrainStore, reference: str) -> tuple[Path, str]:
    try:
        parts = [p for p in str(reference).replace("\\", "/").split("/") if p]
        if len(parts) == 2:
            candidates = [(parts[0], parts[1])]
        elif len(parts) == 1:
            candidates = [(t, parts[0]) for t in TIERS]
        else:
            raise ValueError("bad reference")
        for tier, name in candidates:
            if tier not in TIERS:
                raise ValueError("bad tier")
            path = Path(bejson_safe_join(str(store.snapshot_dir), tier, name))
            if path.is_file():
                return path, tier
    except ValueError as exc:
        raise BrainError(E_BRAIN_PATH_GUARD, f"Rejected snapshot reference: {exc}", {"reference": reference}) from exc
    raise BrainError(E_BRAIN_SNAPSHOT_NOT_FOUND, f"No snapshot '{reference}'.", {"reference": reference})


# Loads a snapshot and checks it structurally. Returns the document.
def snapshots_validate(path: str | Path) -> dict:
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BrainError(E_BRAIN_SNAPSHOT_INVALID, f"Snapshot is not readable JSON: {exc}", {"path": str(path)}) from exc
    if not isinstance(doc, dict) or not bejson_core_chunking_is_mfdb132_package(doc):
        raise BrainError(E_BRAIN_SNAPSHOT_INVALID, "Snapshot is not an MFDB-132 package.", {"path": str(path)})
    for header in (HDR_HASH, HDR_REASON, HDR_CREATED):
        if not doc.get(header):
            raise BrainError(E_BRAIN_SNAPSHOT_INVALID, f"Snapshot is missing header {header}.", {"path": str(path)})
    result = bejson_core_chunking_validate_mfdb132_package(doc)
    if not result.get("valid", False):
        raise BrainError(E_BRAIN_SNAPSHOT_INVALID, "Snapshot failed package validation.", {"path": str(path), "errors": result.get("errors")})
    return doc


# Restores the database from a snapshot. Takes a safety snapshot first, verifies the unpacked copy, then swaps by rename.
def snapshots_rollback(store: BrainStore, reference: str) -> dict:
    store._require_init()
    path, tier = _resolve_snapshot(store, reference)
    doc = snapshots_validate(path)
    with store.locked():
        safety = snapshots_create(store, TIER_DEFAULT, f"before rollback to {path.name}")
        if store.staging_dir.exists():
            shutil.rmtree(store.staging_dir)
        try:
            _, validation = bejson_core_chunking_unchunk_mfdb132_package(doc, str(store.staging_dir))
            if not validation.get("valid", False):
                raise BrainError(E_BRAIN_ROLLBACK_VERIFY_FAILED, "Unpacked snapshot failed validation.", {"errors": validation.get("errors")})
            staged_manifest = store.staging_dir / MANIFEST_FILENAME
            findings = [f for f in mfdb_core_deep_verify(str(staged_manifest)) if "error" in f]
            if findings:
                raise BrainError(E_BRAIN_ROLLBACK_VERIFY_FAILED, "Unpacked snapshot failed the database check.", {"findings": findings})
            if brain_store_hash_manifest(str(staged_manifest)) != doc[HDR_HASH]:
                raise BrainError(E_BRAIN_ROLLBACK_VERIFY_FAILED, "Snapshot content does not match its recorded hash (modified or damaged).", {"snapshot": path.name})
        except BrainError:
            shutil.rmtree(store.staging_dir, ignore_errors=True)
            raise
        except Exception as exc:  # noqa: BLE001 - any unpack failure is a verify failure; the live database is untouched
            shutil.rmtree(store.staging_dir, ignore_errors=True)
            raise BrainError(E_BRAIN_ROLLBACK_VERIFY_FAILED, f"Could not unpack the snapshot: {exc}", {"snapshot": path.name}) from exc
        store._crash("before_swap")
        store.swap_in_directory(store.staging_dir)
        audit.brain_audit_append(store.state_dir, store.now(), "user", "rollback", path.name, True, f"safety={safety['filename']}", int(store.limits["audit_max_rows"]))
        return {"restored": f"{tier}/{path.name}", "safety_snapshot": f"{safety['tier']}/{safety['filename']}", "content_hash": doc[HDR_HASH]}
