"""
Library:         lib_bejson_Core_bejson_chunking.py
Family:          Core
Module Purpose:  Chunked-104a project packaging (directory <-> one 104a document) plus MFDB-132 archive create/validate/unpack (MFDB in one Chunked-104a file).
Architecture:    Chunked-104a packaging: a directory tree stored as one BEJSON 104a document, and MFDB-132, which packs an entire MFDB (manifest + entity files) into one Chunked-104a document. Neither is BEJSON 104db.
Format_Scope:    Chunked-104a and MFDB-132 packaging (NOT 104db)
Glossary:        BEJSON 104, 104a and 104db are the three file formats (Format_Version). 104db = ONE file holding 2+ entity types
                 (Record_Type_Parent discriminator, null-padding). MFDB is NOT a format and NOT 104db: it is a layer made of one 104a manifest
                 (104a.mfdb.bejson) plus dense 104 entity files linked by Parent_Hierarchy. MFDB-132 = an MFDB packed into one Chunked-104a document.
Version:         1.9.4
Release_Version: 300
Date:            2026-10-06
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   e0ab1183-6aa6-439f-ba66-49632dfd8bcf
"""

import base64
import hashlib
import json
import logging
import os
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lib_bejson_Core_bejson_path_guard import bejson_safe_join

from lib_bejson_Core_mfdb_validator import (
    mfdb_validator_is_mfdb132_package,
    mfdb_validator_validate_mfdb132_package,
    mfdb_validator_detect_mfdb_in_chunk,
)

# ── Defaults (must match CLI_Chunker.py exactly) ───────────────────────────────

DEFAULT_EXTENSIONS = [".py", ".js", ".ts", ".html", ".css", ".md", ".json",
                       ".sh", ".txt", ".bejson", ".tsx", ".jsx"]
DEFAULT_EXCLUDES = [".git", "__pycache__", "node_modules", "lib", "output",
                     ".mfdb_lock", "dist", "build"]

# ── Chunked-104 schema (BEJSON 104a, flat, one record per file) ────────────────

CHUNKED_104_FIELDS = [
    {"name": "File_Name",      "type": "string"},
    {"name": "File_Extension", "type": "string"},
    {"name": "File_Content",   "type": "string"},
    {"name": "File_Version",   "type": "string"},
    {"name": "File_Hash",      "type": "string"},
    {"name": "Relative_Path",  "type": "string"},
    {"name": "Is_Binary",      "type": "boolean"},
    {"name": "Is_Mounted",     "type": "boolean"},
]

MFDB_MANIFEST_FILENAME = "104a.mfdb.bejson"
# Fixed packaging-format identifier for the MFDB-132 spec itself — NOT the
# database's own MFDB_Version (which lives inside the wrapped manifest and
# increments normally). This constant intentionally never changes; "1.32" is
# what makes it "MFDB-132." Do not bump this to track DB schema changes.
MFDB_CHUNK_SCHEMA_VERSION = "1.32"


# ISO-8601 UTC timestamp string used for chunk-document headers.
def bejson_core_chunking_get_timestamp() -> str:
    """ISO 8601 UTC timestamp, matching bejson_utility_get_timestamp()."""
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# True if the file should be treated as binary (stored base64) when chunking; same detection rule as the CLI chunker.
def bejson_core_chunking_is_binary(file_path) -> bool:
    """Detection logic matching official chunker tools (unchanged from CLI_Chunker.py)."""
    try:
        with open(file_path, 'tr', encoding='utf-8') as f:
            f.read(1024)
            return False
    except (UnicodeDecodeError, PermissionError):
        return True


# SHA-256 hex digest of raw file bytes: the File_Hash stored per row. Used for change detection and corruption checks, not as a signature.
def bejson_core_chunking_hash_file_bytes(raw_bytes: bytes) -> str:
    """
    SHA-256 hash (hex digest) used for the Chunked-104/104a schema's
    File_Hash field (corruption/change detection, not a security
    signature).

    File_Hash values are compared on re-chunk; a stored hash that does not match is re-hashed and
    stored, so change detection is self-correcting.
    """
    return hashlib.sha256(raw_bytes).hexdigest()


# Computes the next Package_Version string from a prior chunk document (or the first one). Package_Version tracks chunk-document releases; it is unrelated to Format_Version.
def bejson_core_chunking_bump_package_version(prior_doc: Optional[Dict[str, Any]]) -> str:
    """
    Package_Version tracking, mirroring the project schema tracker's
    Project_Version / Package_Version split: Schema_Version is the chunk
    FORMAT's version (bumps only if CHUNKED_104_FIELDS itself changes),
    File_Version is the version of the PROJECT CONTENT being chunked
    (caller-supplied per chunk() call), and Package_Version is the version
    of this specific chunk ARTIFACT -- it bumps every time a chunk doc is
    (re)written for the same target, same as Rule 1 (Always Bump) in the
    project's own Package Version Rules, independent of whether File_Version
    changed. Numeric-string bump (e.g. "3" -> "4"); non-numeric or missing
    prior values reset to "1" rather than raising.
    """
    if not prior_doc:
        return "1"
    try:
        return str(int(prior_doc.get("Package_Version", "0")) + 1)
    except (TypeError, ValueError):
        return "1"


# Packs a directory tree into one Chunked-104a document: Fields describe a file (name, extension, relative path, content, hash, binary flag), Values hold one row per file. Chunked-104a: a whole directory stored in ONE BEJSON 104a document (one row per file). Not 104db, not MFDB.
# Filters: version label, extension list, excluded directories.
def bejson_core_chunking_create_chunked_104(target_dir: str, version: str = "latest",
                                             extensions: Optional[List[str]] = None,
                                             exclude_dirs: Optional[List[str]] = None,
                                             package_version: Optional[str] = None) -> Dict[str, Any]:
    """
    Generates a BEJSON 104a document matching the Chunked-104 schema:
    one flat record per file (File_Name/File_Extension/File_Content/File_Version/
    File_Hash/Relative_Path/Is_Binary/Is_Mounted).

    Exact port of bejson_utility_create_chunked_104() from CLI_Chunker.py v2.5.1.
    Binary files are base64-encoded into File_Content. Is_Binary is the label
    that tells bejson_core_chunking_unchunk_chunked_104() which decode path to
    use for that row (base64 -> bytes, vs. plain UTF-8 text) — no separate
    encoding field is added to the schema.

    Three distinct version concepts on the returned doc, tied back to the
    project schema tracker's own Project_Version / Package_Version split:
      - Schema_Version  (top-level, fixed "1.0.1"): version of the
        Chunked-104a FORMAT itself -- bumps only if CHUNKED_104_FIELDS
        changes structurally.
      - File_Version    (per-row, from the `version` param): version of the
        PROJECT CONTENT being chunked -- same across every row of one chunk.
      - Package_Version (top-level, from the `package_version` param, or
        "1" if not supplied): version of THIS chunk ARTIFACT. Pass the
        prior doc through bejson_core_chunking_bump_package_version() if
        you want it auto-incremented on every re-chunk of the same target,
        independent of File_Version -- mirrors Package Version Rule 1
        (Always Bump).
    """
    target_path = Path(target_dir).resolve()
    exts = extensions if extensions is not None else DEFAULT_EXTENSIONS
    excl = exclude_dirs if exclude_dirs is not None else DEFAULT_EXCLUDES

    values = []
    for root, dirs, files in os.walk(target_path):
        dirs[:] = [d for d in dirs if d not in excl]
        for file in files:
            f_path = Path(root) / file
            if f_path.suffix.lower() in exts:
                try:
                    rel_path = f_path.relative_to(target_path)
                    is_bin = bejson_core_chunking_is_binary(f_path)
                    raw_bytes = f_path.read_bytes()
                    if is_bin:
                        content = base64.b64encode(raw_bytes).decode("ascii")
                    else:
                        content = raw_bytes.decode("utf-8")
                    file_hash = bejson_core_chunking_hash_file_bytes(raw_bytes)

                    values.append([
                        f_path.name,      # File_Name
                        f_path.suffix,    # File_Extension
                        content,          # File_Content
                        version,          # File_Version
                        file_hash,        # File_Hash
                        str(rel_path),    # Relative_Path
                        is_bin,           # Is_Binary
                        False,            # Is_Mounted
                    ])
                except Exception:
                    continue

    return {
        "Format": "BEJSON",
        "Format_Version": "104a",
        "Format_Creator": "Elton Boehnen",
        "Schema_Name": "Chunked-104a",
        "Schema_Version": "1.0.1",
        "Schema_Description": "Standard schema for chunking single projects.",
        "Chunk_Date": bejson_core_chunking_get_timestamp()[:10],
        # Session-level mount flag (real boolean); distinct from the per-row Is_Mounted field in Fields[].
        "Session_Is_Mounted": False,
        "Mount_Path": "",
        "Package_Version": package_version or "1",
        "Records_Type": ["Chunked"],
        "Fields": CHUNKED_104_FIELDS,
        "Values": values,
    }


# Restores the files of a Chunked-104a document to output_dir (Is_Binary decides text vs base64 decode). Returns the number of files written. Paths are checked so a row cannot escape output_dir.
def bejson_core_chunking_unchunk_chunked_104(doc: Dict[str, Any], output_dir: str) -> int:
    """
    Restores files from a Chunked-104a document back to disk. Is_Binary picks
    the decode path per row: True -> base64-decode File_Content back to raw
    bytes, False -> write File_Content as UTF-8 text. Returns the count of
    files actually written.
    """
    fm = {f["name"]: i for i, f in enumerate(doc.get("Fields", CHUNKED_104_FIELDS))}
    out_root = Path(output_dir).resolve()
    count = 0

    for row in doc.get("Values", []):
        rel_path = row[fm["Relative_Path"]]
        is_binary = row[fm["Is_Binary"]]
        content = row[fm["File_Content"]]
        if not rel_path or content is None:
            continue
        target_file = Path(bejson_safe_join(str(out_root), rel_path))
        target_file.parent.mkdir(parents=True, exist_ok=True)
        if is_binary:
            target_file.write_bytes(base64.b64decode(content))
        else:
            target_file.write_text(content, encoding="utf-8")
        count += 1

    return count


# ── MFDB 1.32 session-based mount ─────────────────────────────────────────────
# Mirrors MFDBArchive (131) exactly, substituting unchunk/rechunk for
# unzip/rezip. Lock file is .mfdb132_lock. Is_Mounted and Mount_Path
# top-level headers on the chunk doc are live mount-state markers.

LOCK_FILE_132 = ".mfdb132_lock"


# SHA-256 of a file on disk (streamed). Used for chunk integrity checks.
def _calculate_chunk_hash(file_path: str) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


# Writes the session headers Session_Is_Mounted and Mount_Path into a chunk document on disk. Any in-memory _bejson_field_map key is removed first so the cache is never written to disk.
def _set_chunk_doc_headers(chunk_doc_path: str, is_mounted: bool, mount_path: str) -> None:
    """Update Session_Is_Mounted / Mount_Path headers in a chunk doc file on disk."""
    try:
        with open(chunk_doc_path, "r", encoding="utf-8") as f:
            doc = json.load(f)
        doc.pop("_bejson_field_map", None)  # never rewrite an in-memory cache to disk
        doc["Session_Is_Mounted"] = bool(is_mounted)
        doc.pop("Is_Mounted", None)  # Session_Is_Mounted is the only document-level mount flag
        doc["Mount_Path"] = mount_path
        with open(chunk_doc_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)
    except Exception as e:
        logging.warning(f"[MFDB132] Could not update chunk doc headers: {e}")


class MFDB132Archive:
    """
    Session-based mount for MFDB 1.32 chunked packages.
    Mirrors MFDBArchive (131) but uses unchunk/rechunk instead of unzip/rezip.

    Lock file:  <workspace>/.mfdb132_lock  (JSON: pid, chunk_doc_path,
                                             original_hash, workspace_dir, mounted_at)
    Is_Mounted: Top-level header on the chunk doc — set True on mount,
                False on unmount.
    Mount_Path: Top-level header on the chunk doc — workspace abs path while
                mounted, empty string when not.
    """

    # Chunked-104a session step: extracts the document into a workspace directory, takes a '132' session lock and sets Session_Is_Mounted / Mount_Path. sticky=True reuses valid extracted files.
    # If the chunk document holds a packaged MFDB (MFDB-132), the workspace is an ordinary MFDB directory (104a manifest + 104 entity files).
    @staticmethod
    def mount(chunk_doc_path: str, target_dir: str,
              force: bool = False, sticky: bool = True) -> str:
        """
        Unchunk an MFDB132 package to a workspace and create a session lock.
        sticky=True reuses an existing valid workspace when the chunk doc hash
        matches. Returns the absolute path to the restored manifest.
        """
        chunk_p = Path(chunk_doc_path).resolve()
        if not chunk_p.exists():
            from lib_bejson_Core_bejson_errors import E_MFDB_CORE_ARCHIVE_ERROR
            raise ValueError(f"Chunk doc not found: {chunk_doc_path}")

        target_p = Path(target_dir)
        lock_file = target_p / LOCK_FILE_132
        manifest_path = target_p / "104a.mfdb.bejson"
        current_hash = _calculate_chunk_hash(str(chunk_p))

        # ── Sticky reuse ───────────────────────────────────────────────────────
        if sticky and lock_file.exists() and manifest_path.exists():
            try:
                with open(lock_file, "r") as f:
                    lock_data = json.load(f)
                if lock_data.get("original_hash") == current_hash:
                    from lib_bejson_Core_mfdb_validator import mfdb_validator_validate_database
                    if mfdb_validator_validate_database(str(manifest_path)):
                        return str(manifest_path.absolute())
            except Exception:
                pass  # Fall through to full re-unchunk

        # ── Ownership check ────────────────────────────────────────────────────
        if lock_file.exists() and not force:
            with open(lock_file, "r") as f:
                lock_data = json.load(f)
            if lock_data.get("pid") != os.getpid():
                raise PermissionError(
                    f"Workspace {target_dir} is locked by PID {lock_data.get('pid')}."
                    " Pass force=True to override."
                )

        # ── Clear workspace, unchunk ───────────────────────────────────────────
        if target_p.exists():
            shutil.rmtree(target_dir)
        target_p.mkdir(parents=True, exist_ok=True)

        with open(chunk_p, "r", encoding="utf-8") as f:
            doc = json.load(f)

        count = bejson_core_chunking_unchunk_chunked_104(doc, target_dir)
        if count == 0:
            shutil.rmtree(target_dir)
            raise ValueError("Unchunk produced zero files — chunk doc may be empty.")

        if not manifest_path.exists():
            shutil.rmtree(target_dir)
            raise ValueError(
                "Invalid MFDB132 package: 104a.mfdb.bejson missing after unchunk."
            )

        # ── Write session lock ─────────────────────────────────────────────────
        lock_data = {
            "pid": os.getpid(),
            "mounted_at": datetime.now(timezone.utc).isoformat(),
            "original_hash": current_hash,
            "chunk_doc_path": str(chunk_p),
            "workspace_dir": str(target_p.absolute()),
        }
        with open(lock_file, "w") as f:
            json.dump(lock_data, f)

        # ── Activate headers in chunk doc ──────────────────────────────────────
        _set_chunk_doc_headers(str(chunk_p), True, str(target_p.absolute()))

        return str(manifest_path.absolute())

    # Re-chunks the mounted workspace back into the chunk document (atomic). With validate=True it refuses to write if validation fails. Returns the output path.
    @staticmethod
    def commit(mount_dir: str, output_path: Optional[str] = None,
               validate: bool = True) -> str:
        """
        Re-chunk the workspace back into an MFDB132 package atomically.
        Runs full MFDB validation as a pre-write gate (refuses bad writes before
        touching disk — unlike the post-write check in unchunk_mfdb132_package).
        """
        mount_p = Path(mount_dir)
        lock_file = mount_p / LOCK_FILE_132
        manifest_path = mount_p / "104a.mfdb.bejson"

        if not lock_file.exists():
            raise RuntimeError(f"No active 132 mount session in {mount_dir}")

        with open(lock_file, "r") as f:
            lock_data = json.load(f)

        # ── Pre-write validation gate ──────────────────────────────────────────
        if validate:
            if not manifest_path.exists():
                raise RuntimeError("Commit rejected: manifest missing in workspace.")
            from lib_bejson_Core_mfdb_validator import mfdb_validator_validate_database
            try:
                mfdb_validator_validate_database(str(manifest_path))
            except Exception as e:
                raise RuntimeError(f"Commit rejected: validation failed — {e}")

        dest_path = output_path or lock_data.get("chunk_doc_path")
        if not dest_path:
            raise RuntimeError("Destination chunk doc path unknown.")

        # Read DB_Name from restored manifest for rechunking
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_doc = json.load(f)
        db_name = manifest_doc.get("DB_Name", "")

        # ── Rechunk to temp, atomic swap ───────────────────────────────────────
        fd, temp_chunk = tempfile.mkstemp(suffix=".mfdb132.bejson")
        os.close(fd)
        try:
            new_doc = bejson_core_chunking_create_mfdb132_package(mount_dir, db_name)
            with open(temp_chunk, "w", encoding="utf-8") as f:
                json.dump(new_doc, f, indent=2)
            shutil.move(temp_chunk, dest_path)
        except Exception as e:
            if os.path.exists(temp_chunk):
                os.remove(temp_chunk)
            raise RuntimeError(f"Commit failed during rechunk: {e}")

        # ── Update lock hash; keep Is_Mounted=True until explicit unmount ──────
        new_hash = _calculate_chunk_hash(dest_path)
        lock_data["original_hash"] = new_hash
        with open(lock_file, "w") as f:
            json.dump(lock_data, f)

        _set_chunk_doc_headers(dest_path, True, str(mount_p.absolute()))
        return dest_path

    # Recovery helper: re-extracts a single file from the chunk document into the mounted workspace.
    @staticmethod
    def resurrect_file(mount_dir: str, relative_path: str) -> bool:
        """
        Re-unchunk a single file from the chunk doc into the workspace.
        Used for recovery when an entity file is missing or corrupted.
        No full re-unchunk required.
        """
        mount_p = Path(mount_dir)
        lock_file = mount_p / LOCK_FILE_132
        if not lock_file.exists():
            return False

        with open(lock_file, "r") as f:
            lock_data = json.load(f)

        chunk_doc_path = lock_data.get("chunk_doc_path")
        if not chunk_doc_path or not os.path.exists(chunk_doc_path):
            return False

        try:
            with open(chunk_doc_path, "r", encoding="utf-8") as f:
                doc = json.load(f)

            fm = {field["name"]: i
                  for i, field in enumerate(doc.get("Fields", CHUNKED_104_FIELDS))}
            target_rel = Path(relative_path)

            for row in doc.get("Values", []):
                row_rel = Path(row[fm["Relative_Path"]])
                if row_rel == target_rel:
                    target_file = Path(bejson_safe_join(str(mount_p), str(row_rel)))
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    is_binary = row[fm["Is_Binary"]]
                    content   = row[fm["File_Content"]]
                    if is_binary:
                        target_file.write_bytes(base64.b64decode(content))
                    else:
                        target_file.write_text(content, encoding="utf-8")
                    return True
        except Exception as e:
            logging.warning(f"[MFDB132] resurrect_file failed for {relative_path}: {e}")
        return False

    # Releases the 132 session lock and clears Session_Is_Mounted / Mount_Path; with cleanup=True also removes the workspace.
    @staticmethod
    def unmount(mount_dir: str, cleanup: bool = True) -> None:
        """
        Release the 132 session lock and clear Is_Mounted / Mount_Path headers
        on the chunk doc. Optionally deletes the workspace directory.
        """
        mount_p = Path(mount_dir)
        lock_file = mount_p / LOCK_FILE_132

        if lock_file.exists():
            try:
                with open(lock_file, "r") as f:
                    lock_data = json.load(f)
                chunk_doc_path = lock_data.get("chunk_doc_path")
                if chunk_doc_path and os.path.exists(chunk_doc_path):
                    _set_chunk_doc_headers(chunk_doc_path, False, "")
            except Exception:
                pass
            os.remove(lock_file)

        if cleanup and mount_p.exists():
            shutil.rmtree(mount_dir)


# ── MFDB 1.32 packaging extension ──────────────────────────────────────────────
# 1.31 stays fully valid and unchanged (manifest + entity files, optionally
# zipped). 1.32 adds a second, optional container: the entire MFDB directory
# (manifest + every entity file) chunked into ONE Chunked-104a document. This
# is purely additive — nothing about the 1.31 disk layout or validation rules
# changes.

# MFDB-132 packaging: reads an MFDB directory (the 104a manifest 104a.mfdb.bejson + its 104 entity files) and stores all of it in ONE Chunked-104a document.
# MFDB-132 is a packaging wrapper around an ordinary MFDB; it does not change the MFDB structure and is not 104db.
def bejson_core_chunking_create_mfdb132_package(mfdb_root_dir: str, db_name: str,
                                                 extensions: Optional[List[str]] = None,
                                                 exclude_dirs: Optional[List[str]] = None,
                                                 package_version: Optional[str] = None,
                                                 prior_package_doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Chunks an entire MFDB 1.31-layout directory (104a.mfdb.bejson manifest +
    data/*.bejson entity files) into a single Chunked-104a document, tagged
    with MFDB_Version/DB_Name headers so validators can recognize it as a
    packaged MFDB 1.32 database rather than a plain project chunk.

    Raises ValueError if no 104a.mfdb.bejson manifest is found directly under
    mfdb_root_dir — a package without its manifest is not a valid MFDB.

    package_version: explicit Package_Version for this artifact. If omitted
    and prior_package_doc is given (the previous chunk doc for this same
    target, if one exists on disk), it auto-bumps via
    bejson_core_chunking_bump_package_version() -- same Always-Bump
    convention as the project schema tracker's own Package_Version Rule 1.
    Falls back to "1" if neither is supplied.
    """
    root_path = Path(mfdb_root_dir).resolve()
    if not (root_path / MFDB_MANIFEST_FILENAME).is_file():
        raise ValueError(
            f"No {MFDB_MANIFEST_FILENAME} found at root of {root_path} — "
            "cannot package a directory that isn't a valid MFDB layout."
        )

    resolved_package_version = package_version or bejson_core_chunking_bump_package_version(prior_package_doc)

    doc = bejson_core_chunking_create_chunked_104(
        target_dir=str(root_path),
        version=MFDB_CHUNK_SCHEMA_VERSION,
        extensions=extensions if extensions is not None else DEFAULT_EXTENSIONS,
        exclude_dirs=exclude_dirs,
        package_version=resolved_package_version,
    )

    # Overwrite the inherited Chunked-104a schema identity: MFDB-132 is a
    # customized packaging built on Chunked-104a internals, but it must
    # self-identify as its own schema, not as a plain project chunk that
    # happens to carry extra headers (Package_Format alone isn't authoritative
    # for discovery — see mfdb_validator_is_mfdb132_package()).
    doc["Schema_Name"] = "MFDB-132"
    doc["Records_Type"] = ["MFDB-132"]
    doc["MFDB_Version"] = MFDB_CHUNK_SCHEMA_VERSION
    doc["DB_Name"] = db_name
    doc["Package_Format"] = "MFDB-Chunked-104a"
    return doc



# True if a Chunked-104a document is a packaged MFDB-132 (it contains an MFDB manifest and entity files as rows).
def bejson_core_chunking_is_mfdb132_package(doc: Dict[str, Any]) -> bool:
    """
    Discovery check: True if this Chunked-104a document represents a packaged
    MFDB 1.32 database rather than a plain project chunk.

    Thin wrapper — validation logic lives in
    lib_bejson_Core_mfdb_validator.mfdb_validator_is_mfdb132_package().
    """
    return mfdb_validator_is_mfdb132_package(doc)


# Level-1 validation of an MFDB-132 package document: required rows (manifest, entity files) present and consistent. Returns a result dict (valid, errors, warnings).
def bejson_core_chunking_validate_mfdb132_package(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Level 1 validation for a chunked MFDB 1.32 package.

    Thin wrapper — validation logic lives in
    lib_bejson_Core_mfdb_validator.mfdb_validator_validate_mfdb132_package().
    """
    return mfdb_validator_validate_mfdb132_package(doc)


# Unpacks an MFDB-132 package into a normal MFDB directory layout (104a manifest + 104 entity files). Returns (files_written, info dict).
def bejson_core_chunking_unchunk_mfdb132_package(doc: Dict[str, Any], output_dir: str) -> Tuple[int, Dict[str, Any]]:
    """
    Restores a chunked MFDB 1.32 package back to a standard 1.31-layout
    directory (104a.mfdb.bejson + data/*.bejson), then re-runs the Level 1
    package validation against the restored manifest path. Returns
    (files_written, validation_result_dict).

    Note: binary files (Is_Binary=True rows) ARE restored -- File_Content is
    base64-decoded back to raw bytes by bejson_core_chunking_unchunk_chunked_104.
    MFDB entity files and manifests are always text/JSON; binary assets left inside the MFDB directory
    also round-trip.
    """
    validation = bejson_core_chunking_validate_mfdb132_package(doc)
    count = bejson_core_chunking_unchunk_chunked_104(doc, output_dir)

    out_root = Path(output_dir).resolve()
    manifest_restored = (out_root / MFDB_MANIFEST_FILENAME).is_file()
    if not manifest_restored:
        validation["valid"] = False
        validation.setdefault("errors", []).append(
            f"Manifest {MFDB_MANIFEST_FILENAME} was not found on disk after unchunking."
        )

    return count, validation


# ── MFDB-in-chunk deep detection (validator extension) ─────────────────────
# Thin wrapper over lib_bejson_Core_mfdb_validator.py, exposed through the chunking library.

# Scans any Chunked-104a document for an embedded, valid MFDB and reports where its manifest and entity rows are. Read-only.
def bejson_core_chunking_detect_mfdb_in_chunk(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Scans any Chunked-104a document for an embedded, valid MFDB database.

    Thin wrapper — validation logic lives in
    lib_bejson_Core_mfdb_validator.mfdb_validator_detect_mfdb_in_chunk().
    """
    return mfdb_validator_detect_mfdb_in_chunk(doc)


# ── MFDB rolling multi-version schema (unify layer) ─────────────────────────
# Everything above this line (bejson_core_chunking_*) is the Chunked-104a /
# MFDB-132 flat one-shot schema: one doc per chunk, no version concept, no
# manifest/entity split.
#
# Everything below (bejson_core_chunking_mfdb_*) is a distinct function set,
# same file/family, for the OTHER schema in the ecosystem: mfdb_chunker.py's
# rolling multi-version layout (manifest + entity split, one entity file
# holds ALL versions as rows, distinguished by a 'version' field). Both schemas share the same
# per-file field vocabulary (File_Name/File_Extension/Relative_Path/File_Content/File_Hash/
# Is_Binary/Is_Mounted) -- rolling MFDB entities just add 'version' on top.
# This section is the detection + dispatch layer that lets calling code hand
# it ANY of the four known doc shapes and get the right restore behavior
# back without knowing which one it is up front. It does not duplicate the
# flat-schema restore logic above -- bejson_core_chunking_mfdb_unchunk()
# delegates to bejson_core_chunking_unchunk_chunked_104() for that case.
#
# MFDB versioning is handled leniently: MFDB_Version header values are
# informational only (1.31/1.32/1.38 and any future value all pass) --
# schema detection is structural (which Fields are present), never a
# version-string allowlist, so a newer/older MFDB_Version this file hasn't
# been told about yet still detects correctly.

BEJSON_CORE_CHUNKING_MFDB_SCHEMA_MANIFEST      = "mfdb_manifest"
BEJSON_CORE_CHUNKING_MFDB_SCHEMA_ENTITY        = "mfdb_entity"
BEJSON_CORE_CHUNKING_MFDB_SCHEMA_ENTITY_LEGACY = "mfdb_entity_legacy"
BEJSON_CORE_CHUNKING_MFDB_SCHEMA_CHUNKED_104A  = "chunked_104a"
BEJSON_CORE_CHUNKING_MFDB_SCHEMA_UNKNOWN       = "unknown"

# Field names a current MFDB entity row must have.
_MFDB_ENTITY_FIELD_NAMES = {
    "version", "File_Name", "File_Extension", "Relative_Path",
    "File_Content", "File_Hash", "Is_Binary", "Is_Mounted",
}
# Field names of the lowercase MFDB entity schema (see SCHEMA_MFDB_ENTITY_v5); detected as the "mfdb_entity_legacy" shape.
_MFDB_ENTITY_LEGACY_FIELD_NAMES = {
    "version", "file_path", "file_name", "content", "is_binary", "is_base64",
}
_CHUNKED_104A_FIELD_NAMES = {f["name"] for f in CHUNKED_104_FIELDS}

_mfdb_field_map_cache: Dict[Tuple[str, ...], Dict[str, int]] = {}


# Field-name -> index map for a chunk document, cached per distinct Fields signature (no hardcoded positions).
def bejson_core_chunking_mfdb_get_field_map(doc: Dict[str, Any]) -> Dict[str, int]:
    """Field Map Indexing, cached per distinct Fields signature -- authoritative
    over positional hard-coding, per standing convention."""
    fields = doc.get("Fields", [])
    key = tuple(f["name"] for f in fields)
    fmap = _mfdb_field_map_cache.get(key)
    if fmap is None:
        fmap = {f["name"]: i for i, f in enumerate(fields)}
        _mfdb_field_map_cache[key] = fmap
    return fmap


# Classifies a chunk document's field layout among the known chunk shapes (Chunked-104a file rows, MFDB entity rows, MFDB manifest rows, and the lowercase variants). Pure structure check.
def bejson_core_chunking_mfdb_detect_schema(doc: Dict[str, Any]) -> str:
    """Structural detection across all four known chunk doc shapes."""
    records_type = doc.get("Records_Type")
    field_names = {f["name"] for f in doc.get("Fields", [])}

    if records_type == ["MFDB-132"] or doc.get("Schema_Name") == "MFDB-132":
        return BEJSON_CORE_CHUNKING_MFDB_SCHEMA_CHUNKED_104A
    if records_type == ["Chunked"] and field_names == _CHUNKED_104A_FIELD_NAMES:
        return BEJSON_CORE_CHUNKING_MFDB_SCHEMA_CHUNKED_104A
    if field_names == _MFDB_ENTITY_FIELD_NAMES:
        return BEJSON_CORE_CHUNKING_MFDB_SCHEMA_ENTITY
    if field_names == _MFDB_ENTITY_LEGACY_FIELD_NAMES:
        return BEJSON_CORE_CHUNKING_MFDB_SCHEMA_ENTITY_LEGACY
    if records_type == ["mfdb"] and "entity_name" in field_names and "file_path" in field_names:
        return BEJSON_CORE_CHUNKING_MFDB_SCHEMA_MANIFEST
    return BEJSON_CORE_CHUNKING_MFDB_SCHEMA_UNKNOWN


# Checks that a chunk document's MFDB package version is one of the known versions (1.31, 1.32, 1.38). Version here is the MFDB package/convention version, not a BEJSON Format_Version.
def bejson_core_chunking_mfdb_check_version(
    doc: Dict[str, Any],
    known_versions: Tuple[str, ...] = ("1.31", "1.32", "1.38"),
) -> Optional[str]:
    """
    Lenient version check: returns a warning string if MFDB_Version is present
    but not in the known set, or None if it's known (or absent -- absence
    isn't an error). Never raises, never blocks processing -- structural
    detection in bejson_core_chunking_mfdb_detect_schema() is what actually
    gates behavior, not this.
    """
    mfdb_version = doc.get("MFDB_Version")
    if mfdb_version is None:
        return None
    if str(mfdb_version) not in known_versions:
        return (f"MFDB_Version '{mfdb_version}' not in known set {known_versions} -- "
                f"proceeding on structural detection anyway, but this is worth a look.")
    return None


# Restores a rolling multi-version MFDB chunk (manifest + entity split, all versions as rows) into a directory; version selects which release to extract.
def bejson_core_chunking_mfdb_unchunk(doc: Dict[str, Any], output_dir: str,
                                       version: Optional[str] = None,
                                       manifest_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Single entry point for restoring ANY of the four known schemas.

    - CHUNKED_104A: doc is the complete flat bundle; delegates to
      bejson_core_chunking_unchunk_chunked_104(). Ignores `version` (this
      schema has no version concept).
    - MFDB entity (current): doc is one entity file; `version` selects which
      rows to restore (required) -- expects the entity_name form (e.g.
      "v1_2_0"), same as mfdb_chunker.py's version_to_entity_name().
    - MFDB entity (legacy): refused -- no migration path, matches the
      mfdb_chunker.py policy of purge-and-rechunk-clean rather than reading
      the old layout.
    - MFDB manifest: `manifest_dir` (the manifest's own parent directory,
      needed to resolve the sibling entity file's relative path) and
      `version` are both required. Loads the entity file and recurses.
    """
    schema = bejson_core_chunking_mfdb_detect_schema(doc)
    warning = bejson_core_chunking_mfdb_check_version(doc)
    out_root = Path(output_dir).resolve()

    if schema == BEJSON_CORE_CHUNKING_MFDB_SCHEMA_CHUNKED_104A:
        count = bejson_core_chunking_unchunk_chunked_104(doc, output_dir)
        return {"ok": True, "message": f"Restored {count} file(s) from Chunked-104a/MFDB-132 bundle.",
                "schema": schema, "warning": warning, "out_dir": str(out_root), "file_count": count}

    if schema == BEJSON_CORE_CHUNKING_MFDB_SCHEMA_MANIFEST:
        if manifest_dir is None or not version:
            return {"ok": False, "message": "MFDB manifest requires manifest_dir and version.",
                    "schema": schema, "warning": warning}
        fm = bejson_core_chunking_mfdb_get_field_map(doc)
        row = next((r for r in doc.get("Values", []) if r[fm["entity_name"]] == version), None)
        if row is None:
            return {"ok": False, "message": f"Version '{version}' not found in manifest.",
                    "schema": schema, "warning": warning}
        entity_path = manifest_dir / row[fm["file_path"]]
        if not entity_path.exists():
            return {"ok": False, "message": f"Entity file missing: {entity_path}",
                    "schema": schema, "warning": warning}
        import json
        entity_doc = json.loads(entity_path.read_text(encoding="utf-8"))
        return bejson_core_chunking_mfdb_unchunk(entity_doc, output_dir, version=version)

    if schema == BEJSON_CORE_CHUNKING_MFDB_SCHEMA_ENTITY:
        if not version:
            return {"ok": False, "message": "MFDB entity requires version.",
                    "schema": schema, "warning": warning}
        fm = bejson_core_chunking_mfdb_get_field_map(doc)
        rows = [r for r in doc.get("Values", []) if r[fm["version"]] == version]
        if not rows:
            return {"ok": False, "message": f"No rows for version '{version}'.",
                    "schema": schema, "warning": warning}
        out_root.mkdir(parents=True, exist_ok=True)
        count = 0
        for row in rows:
            rel_path = row[fm["Relative_Path"]]
            if not rel_path:
                continue
            target = Path(bejson_safe_join(str(out_root), rel_path))
            target.parent.mkdir(parents=True, exist_ok=True)
            if row[fm["Is_Binary"]]:
                target.write_bytes(base64.b64decode(row[fm["File_Content"]] or ""))
            else:
                target.write_text(row[fm["File_Content"]] or "", encoding="utf-8")
            count += 1
        return {"ok": True, "message": f"Restored {count} file(s) for version '{version}'.",
                "schema": schema, "warning": warning, "out_dir": str(out_root), "file_count": count}

    if schema == BEJSON_CORE_CHUNKING_MFDB_SCHEMA_ENTITY_LEGACY:
        return {"ok": False, "message": "Legacy MFDB entity schema -- no migration path by design. "
                "Re-chunk the source project with current tooling first.",
                "schema": schema, "warning": warning}

    return {"ok": False, "message": "Could not identify chunk schema (structural detection failed).",
            "schema": BEJSON_CORE_CHUNKING_MFDB_SCHEMA_UNKNOWN, "warning": warning}