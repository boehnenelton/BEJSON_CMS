#!/usr/bin/env python3
"""
#===============================================================================
# BEJSON ECOSYSTEM MANDATE: CHUNKING POLICY (v2.0)
#===============================================================================
# [USAGE NOTE]: Use MFDB Chunker v5 for LONG-TERM version history, relational
# archiving, and lossless binary storage (Base64). Best for active dev projects.
# ALWAYS check and obey the Chunking Policy in the Policy Registry.
#===============================================================================
<!--
FILE:        mfdb_chunker.py
VERSION:     6.1.0
             Architecture v2: one entity file per project holds ALL versions
             as rows (distinguished by 'version' field). The manifest tracks
             per-version metadata. Export/import packages are self-contained zips.
COMPLIANCE:  MFDB Spec v1.31 | BEJSON Formats: 104 · 104a
CHANGELOG:
  6.1.0 - Packaged as lib_mfdb_chunker_v6.py for BEJSON Lib ecosystem.
  6.0.0 - Integrated Snapshot Backups for point-in-time recovery.
          Added DB Integrity Validation (--validate).
          UI: Added Project Removal and File Tree Preview.
  5.0.0 - Upgraded to official BEJSON Library v2.0.1 (MFDB 1.31).
          Removed create_backup kwarg (no longer in bejson_core_atomic_write v2.0.1).
          Added: lib_bejson_errors.py, lib_bejson_env.py, lib_bejson_schema.py,
          lib_bejson_state_management.py, lib_mfdb_extensions.py.
          COMPLIANCE: MFDB Spec v1.31 | Lib Family v2.0.1 OFFICIAL.
  4.0.0 - Optional base64 encoding of binary files (include_binary_base64 config flag).
          Auto-detected on unchunk: base64 content decoded back to original binary.
  3.0.0 - Auto-set project_name from target directory name on first chunk.
  2.0.0 - BREAKING: One entity file per project (all versions as rows with
          version field). Added: version tagging, inline changelog edit,
          prune, export-zip, import-zip. --prune, --export, --import CLI flags.
  1.2.0 - Flask UI, project mode, changelog field, bump buttons, restore.
  1.1.0 - MFDB Spec 1.31 compliance.
  1.0.2 - create_backup=False on all atomic writes.
  1.0.0 - Initial release.
-->
"""
import os
import sys
import json
import zipfile
import argparse
import time
import base64
import tempfile
import shutil
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR / "lib"))

try:
    import lib_bejson_core as BEJSONCore
except ImportError as e:
    print(f"CRITICAL: Local libraries not found in lib/: {e}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MFDB_SPEC_VERSION = "1.31"

DEFAULT_CONFIG = {
    "project_name": "MyProject",
    "version":      "1.0.0",
    "extensions":   [".py", ".js", ".ts", ".html", ".css", ".md", ".json",
                     ".sh", ".txt", ".bejson"],
    "exclude_dirs": [".git", "__pycache__", "node_modules", "lib",
                     "output", ".mfdb_lock"],
    "output_base":              str(BASE_DIR / "output"),
    "include_binary_base64":    False,
}
TEMPLATE_META_FILE = "__template_meta__.json"

# Manifest: one row per version. Tags stored as comma-separated string (104a primitive constraint).
MANIFEST_FIELDS = [
    {"name": "entity_name",    "type": "string"},   # e.g. "v1_2_0"
    {"name": "file_path",      "type": "string"},   # always "data/<project>.bejson"
    {"name": "description",    "type": "string"},
    {"name": "record_count",   "type": "integer"},
    {"name": "schema_version", "type": "string"},   # semver
    {"name": "primary_key",    "type": "string"},   # "file_path"
    {"name": "changelog",      "type": "string"},
    {"name": "chunked_at",     "type": "string"},   # ISO 8601 UTC
    {"name": "tags",           "type": "string"},   # comma-separated, e.g. "stable,release"
]

# Entity: one row per (version, file) pair. All versions in one file.
ENTITY_FIELDS = [
    {"name": "version",   "type": "string"},
    {"name": "file_path", "type": "string"},
    {"name": "file_name", "type": "string"},
    {"name": "content",   "type": "string"},
    {"name": "is_binary", "type": "boolean"},
    {"name": "is_base64", "type": "boolean"},
]

# Manifest field indices (matched to MANIFEST_FIELDS order above)
M_ENTITY_NAME    = 0
M_FILE_PATH      = 1
M_DESCRIPTION    = 2
M_RECORD_COUNT   = 3
M_SCHEMA_VERSION = 4
M_PRIMARY_KEY    = 5
M_CHANGELOG      = 6
M_CHUNKED_AT     = 7
M_TAGS           = 8

# Entity field indices
E_VERSION   = 0
E_FILE_PATH = 1
E_FILE_NAME = 2
E_CONTENT   = 3
E_IS_BINARY = 4
E_IS_BASE64 = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sanitize_name(name: str) -> str:
    """Lowercase, spaces to underscores, keep alnum and underscores."""
    return "".join(c if c.isalnum() or c == "_" else "_"
                   for c in name.lower().replace(" ", "_"))


def load_or_create_config(target_path: Path) -> dict:
    config_path = target_path / "chunker_config.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                if k not in config:
                    config[k] = v
            return config
        except Exception as e:
            print(f"Warning: Failed to read config. Error: {e}")
    new_config = dict(DEFAULT_CONFIG)
    new_config["project_name"] = target_path.name
    try:
        with open(config_path, "w") as f:
            json.dump(new_config, f, indent=2)
        print(f"[*] Created config at {config_path}  (project_name: {new_config['project_name']})")
    except Exception as e:
        print(f"Warning: Could not create config. Error: {e}")
    return new_config


def save_config(target_path: Path, config: dict) -> None:
    config_path = target_path / "chunker_config.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


def is_binary(file_path: Path) -> bool:
    try:
        with open(file_path, "tr") as f:
            f.read(512)
        return False
    except UnicodeDecodeError:
        return True


def version_to_entity_name(version: str) -> str:
    return "v" + version.replace(".", "_")


def bump_version(version: str, part: str = "patch") -> str:
    try:
        parts = [int(x) for x in version.split(".")]
        while len(parts) < 3:
            parts.append(0)
        if part == "major":
            parts = [parts[0] + 1, 0, 0]
        elif part == "minor":
            parts = [parts[0], parts[1] + 1, 0]
        else:
            parts = [parts[0], parts[1], parts[2] + 1]
        return ".".join(str(p) for p in parts)
    except Exception:
        return version


def parse_tags(tags_str: str) -> list[str]:
    return [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []


def format_tags(tags: list[str]) -> str:
    return ",".join(t.strip() for t in tags if t.strip())


def get_mfdb_dir(config: dict) -> Path:
    return Path(config["output_base"]) / f"{config['project_name']}_MFDB"


def get_manifest_path(config: dict) -> Path:
    return get_mfdb_dir(config) / "104a.mfdb.bejson"


def get_entity_path(config: dict) -> Path:
    return get_mfdb_dir(config) / "data" / f"{sanitize_name(config['project_name'])}.bejson"


def get_templates_dir(config: dict) -> Path:
    return get_mfdb_dir(config) / "templates"


def safe_extract_zip(zip_file: zipfile.ZipFile, output_dir: Path) -> None:
    output_dir = output_dir.resolve()
    for member in zip_file.infolist():
        member_path = (output_dir / member.filename).resolve()
        if not str(member_path).startswith(str(output_dir)):
            raise ValueError(f"Unsafe zip path blocked: {member.filename}")
    zip_file.extractall(str(output_dir))


def collect_project_files(target_path: Path, config: dict) -> list[Path]:
    exts = set(config["extensions"])
    excludes = set(config["exclude_dirs"])
    files: list[Path] = []
    for root, dirs, filenames in os.walk(target_path):
        dirs[:] = [d for d in dirs if d not in excludes]
        for file_name in sorted(filenames):
            file_path = Path(root) / file_name
            if file_name == "chunker_config.json":
                continue
            if file_path.suffix.lower() not in exts:
                continue
            files.append(file_path)
    return files


# ---------------------------------------------------------------------------
# Manifest management
# ---------------------------------------------------------------------------

def init_manifest(config: dict) -> str:
    manifest_path = get_manifest_path(config)
    if manifest_path.exists():
        return str(manifest_path)

    mfdb_dir = get_mfdb_dir(config)
    mfdb_dir.mkdir(parents=True, exist_ok=True)
    (mfdb_dir / "data").mkdir(exist_ok=True)

    manifest_doc = {
        "Format":         "BEJSON",
        "Format_Version": "104a",
        "Format_Creator": "Elton Boehnen",
        "MFDB_Version":   MFDB_SPEC_VERSION,
        "DB_Name":        config["project_name"],
        "DB_Description": f"Version archive for project: {config['project_name']}",
        "Schema_Version": "1.0.0",
        "Author":         "Elton Boehnen",
        "Created_At":     now_iso(),
        "Records_Type":   ["mfdb"],
        "Fields":         MANIFEST_FIELDS,
        "Values":         [],
    }
    BEJSONCore.bejson_core_atomic_write(str(manifest_path), manifest_doc)
    return str(manifest_path)


def version_exists_in_manifest(manifest_path: str, entity_name: str) -> bool:
    try:
        doc = BEJSONCore.bejson_core_load_file(manifest_path)
        return any(row[M_ENTITY_NAME] == entity_name for row in doc["Values"])
    except Exception:
        return False


def _write_manifest(manifest_path: str, doc: dict) -> None:
    BEJSONCore.bejson_core_atomic_write(manifest_path, doc)


def _write_entity(entity_path: str, doc: dict) -> None:
    BEJSONCore.bejson_core_atomic_write(entity_path, doc)


# ---------------------------------------------------------------------------
# Entity file management
# ---------------------------------------------------------------------------

def _load_or_create_entity(entity_path: str, config: dict,
                            parent_hierarchy: str) -> dict:
    ep = Path(entity_path)
    if ep.exists():
        return BEJSONCore.bejson_core_load_file(entity_path)

    ep.parent.mkdir(parents=True, exist_ok=True)
    entity_type = sanitize_name(config["project_name"])
    doc = BEJSONCore.bejson_core_create_104(
        record_type=entity_type,
        fields=ENTITY_FIELDS,
        values=[],
    )
    doc["Parent_Hierarchy"] = parent_hierarchy
    return doc


def _get_version_rows(entity_doc: dict, entity_name: str) -> list:
    """Return all rows matching this entity_name (version)."""
    return [r for r in entity_doc["Values"] if r[E_VERSION] == entity_name]


def _remove_version_rows(entity_doc: dict, entity_name: str) -> int:
    original = len(entity_doc["Values"])
    entity_doc["Values"] = [r for r in entity_doc["Values"]
                             if r[E_VERSION] != entity_name]
    return original - len(entity_doc["Values"])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def do_validate(manifest_path_arg: str) -> dict:
    """Verify MFDB integrity: manifest existence, entity files, and row counts."""
    manifest_path = Path(manifest_path_arg).resolve()
    if not manifest_path.exists():
        return {"ok": False, "message": "Manifest not found."}
    
    errors = []
    try:
        manifest_doc = BEJSONCore.bejson_core_load_file(str(manifest_path))
        m_fields = [f["name"] for f in manifest_doc["Fields"]]
        en_idx = m_fields.index("entity_name")
        fp_idx = m_fields.index("file_path")
        rc_idx = m_fields.index("record_count")

        for row in manifest_doc["Values"]:
            if row is None or not any(row): continue
            if row is None or not any(row): continue
            v_name = row[en_idx]
            e_rel = row[fp_idx]
            e_count = row[rc_idx]
            e_abs = manifest_path.parent / e_rel
            
            if not e_abs.exists():
                errors.append(f"Version {v_name}: Entity file missing: {e_rel}")
                continue
            
            try:
                entity_doc = BEJSONCore.bejson_core_load_file(str(e_abs))
                actual_count = len(_get_version_rows(entity_doc, v_name))
                if actual_count != e_count:
                    errors.append(f"Version {v_name}: Count mismatch. Manifest={e_count}, Entity={actual_count}")
            except Exception as e:
                errors.append(f"Version {v_name}: Error reading entity: {e}")
        
        if errors:
            return {"ok": False, "message": f"Validation failed with {len(errors)} errors.", "errors": errors}
        return {"ok": True, "message": "MFDB INTEGRITY VERIFIED (OK)"}
    except Exception as e:
        return {"ok": False, "message": f"Validation error: {e}"}

def do_snapshot(target_dir: str) -> dict:
    """Create a full zip snapshot of the MFDB directory."""
    target_path = Path(target_dir).resolve()
    config = load_or_create_config(target_path)
    mfdb_dir = get_mfdb_dir(config)
    
    if not mfdb_dir.exists():
        return {"ok": False, "message": "MFDB directory not found. Chunk first."}
    
    snapshots_dir = mfdb_dir / "snapshots"
    snapshots_dir.mkdir(exist_ok=True)
    
    ts = get_timestamp()
    zip_name = f"snapshot_{config['project_name']}_{ts}.zip"
    zip_path = snapshots_dir / zip_name
    
    try:
        with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, filenames in os.walk(mfdb_dir):
                if "snapshots" in root: continue
                for filename in filenames:
                    abs_path = Path(root) / filename
                    rel_path = abs_path.relative_to(mfdb_dir)
                    zf.write(str(abs_path), str(rel_path))
        return {
            "ok": True, 
            "message": f"SNAPSHOT CREATED: {zip_name}", 
            "zip_path": str(zip_path)
        }
    except Exception as e:
        return {"ok": False, "message": f"Snapshot failed: {e}"}

def get_version_files(manifest_path_arg: str, version: str) -> list:
    """Return list of file paths in a given version."""
    manifest_path = Path(manifest_path_arg).resolve()
    entity_name = version_to_entity_name(version)
    try:
        manifest_doc = BEJSONCore.bejson_core_load_file(str(manifest_path))
        m_fields = [f["name"] for f in manifest_doc["Fields"]]
        fp_idx = m_fields.index("file_path")
        en_idx = m_fields.index("entity_name")
        row = next((r for r in manifest_doc["Values"] if r and any(r) and r[en_idx] == entity_name), None)
        if not row: return []
        entity_abs = manifest_path.parent / row[fp_idx]
        entity_doc = BEJSONCore.bejson_core_load_file(str(entity_abs))
        rows = _get_version_rows(entity_doc, entity_name)
        return [{"path": r[E_FILE_PATH], "name": r[E_FILE_NAME], "binary": r[E_IS_BINARY]} for r in rows if r and any(r)]
    except: return []

def list_versions(manifest_path: str) -> list[dict]:
    try:
        doc    = BEJSONCore.bejson_core_load_file(manifest_path)
        fields = [f["name"] for f in doc["Fields"]]
        result = []
        for row in doc["Values"]:
            rd = {}
            for i, fname in enumerate(fields):
                rd[fname] = row[i] if i < len(row) else None
            result.append(rd)
        return result
    except Exception:
        return []


def get_manifest_meta(manifest_path: str) -> dict:
    try:
        doc = BEJSONCore.bejson_core_load_file(manifest_path)
        return {
            "DB_Name":        doc.get("DB_Name", ""),
            "DB_Description": doc.get("DB_Description", ""),
            "MFDB_Version":   doc.get("MFDB_Version", ""),
            "Created_At":     doc.get("Created_At", ""),
        }
    except Exception:
        return {}


def do_chunk(target_dir: str, changelog: str = "",
             tags: str = "") -> dict:
    try:
        target_path = Path(target_dir).resolve()
        if not target_path.is_dir():
            return {"ok": False, "message": f"Not a directory: {target_dir}", "detail": {}}
    
        config         = load_or_create_config(target_path)
        version        = config["version"]
        entity_name    = version_to_entity_name(version)
        incl_b64       = config.get("include_binary_base64", False)
    
        manifest_path = init_manifest(config)
    
        if version_exists_in_manifest(manifest_path, entity_name):
            return {
                "ok":      False,
                "message": f"Version '{version}' already exists. Bump the version first.",
                "detail":  {},
            }
    
        entity_path      = str(get_entity_path(config))
        mfdb_dir         = get_mfdb_dir(config)
        data_dir         = mfdb_dir / "data"
        parent_hierarchy = os.path.relpath(manifest_path, str(data_dir))
        entity_rel_path  = f"data/{Path(entity_path).name}"
    
        entity_doc = _load_or_create_entity(entity_path, config, parent_hierarchy)
        if changelog:
            entity_doc["Changelog_Latest"] = f"[{entity_name}] {changelog}"
    
        new_rows   = []
        file_count = 0
        skipped    = []
    
        for f_path in collect_project_files(target_path, config):
            try:
                rel_path = str(f_path.relative_to(target_path))
                binary   = is_binary(f_path)
                is_b64   = False
                if binary and incl_b64:
                    raw     = f_path.read_bytes()
                    content = base64.b64encode(raw).decode("ascii")
                    is_b64  = True
                else:
                    content = "" if binary else f_path.read_text(encoding="utf-8")
                new_rows.append([entity_name, rel_path, f_path.name, content, binary, is_b64])
                file_count += 1
            except Exception as e:
                skipped.append(f"{f_path.name}: {e}")
    
        entity_doc["Values"].extend(new_rows)
        _write_entity(entity_path, entity_doc)
    
        # Append manifest row
        manifest_doc = BEJSONCore.bejson_core_load_file(manifest_path)
        manifest_doc["Values"].append([
            entity_name,
            entity_rel_path,
            f"Project version {version}",
            file_count,
            version,
            "file_path",
            changelog or "",
            now_iso(),
            tags or "",
        ])
        _write_manifest(manifest_path, manifest_doc)
    
        return {
            "ok":      True,
            "message": f"VERSION {version} CHUNKED SUCCESSFULLY",
            "detail":  {
                "version":     version,
                "entity_name": entity_name,
                "file_count":  file_count,
                "skipped":     skipped,
                "entity_path": entity_path,
                "manifest":    manifest_path,
            },
        }
    except Exception as e:
        return {"ok": False, "message": f"CRITICAL CHUNK ERROR: {str(e)}", "detail": {}}


def do_chunk_template(target_dir: str, template_name: str = "") -> dict:
    """
    Create a reusable template snapshot zip in:
      <output>/<project>_MFDB/templates/
    Template can be restored later with do_unchunk_template.
    """
    target_path = Path(target_dir).resolve()
    if not target_path.is_dir():
        return {"ok": False, "message": f"Not a directory: {target_dir}", "template_path": ""}

    config = load_or_create_config(target_path)
    templates_dir = get_templates_dir(config)
    templates_dir.mkdir(parents=True, exist_ok=True)

    files_to_pack = collect_project_files(target_path, config)
    if not files_to_pack:
        return {"ok": False, "message": "No files matched chunker config filters.", "template_path": ""}

    base_name = sanitize_name(template_name.strip()) if template_name else ""
    if not base_name:
        base_name = f"{sanitize_name(config['project_name'])}_{version_to_entity_name(config['version'])}"
    zip_name = f"{base_name}.template.zip"
    zip_path = templates_dir / zip_name
    if zip_path.exists():
        zip_name = f"{base_name}_{get_timestamp()}.template.zip"
        zip_path = templates_dir / zip_name

    meta = {
        "template_name": base_name,
        "project_name": config["project_name"],
        "project_version": config["version"],
        "created_at": now_iso(),
        "source_dir": str(target_path),
        "file_count": len(files_to_pack),
        "extensions": list(config.get("extensions", [])),
    }

    try:
        with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(TEMPLATE_META_FILE, json.dumps(meta, indent=2, ensure_ascii=False))
            for file_path in files_to_pack:
                rel_path = str(file_path.relative_to(target_path))
                zf.write(str(file_path), rel_path)
        return {
            "ok": True,
            "message": f"TEMPLATE CHUNKED: {zip_name}",
            "template_path": str(zip_path),
            "file_count": len(files_to_pack),
        }
    except Exception as e:
        return {"ok": False, "message": str(e), "template_path": ""}


def do_unchunk_template(target_dir: str, template_name: str = "", out_dir: str = "") -> dict:
    """
    Restore a template snapshot zip from:
      <output>/<project>_MFDB/templates/
    If template_name is empty, restores the latest template zip.
    """
    target_path = Path(target_dir).resolve()
    if not target_path.is_dir():
        return {"ok": False, "message": f"Not a directory: {target_dir}", "out_dir": ""}

    config = load_or_create_config(target_path)
    templates_dir = get_templates_dir(config)
    if not templates_dir.exists():
        return {"ok": False, "message": f"Templates directory not found: {templates_dir}", "out_dir": ""}

    selected_zip: Path | None = None
    if template_name:
        candidate = Path(template_name)
        if candidate.exists() and candidate.is_file():
            selected_zip = candidate.resolve()
        else:
            normalized = sanitize_name(template_name.strip())
            if normalized.endswith(".template.zip"):
                expected = templates_dir / normalized
            else:
                expected = templates_dir / f"{normalized}.template.zip"
            if expected.exists():
                selected_zip = expected
    if selected_zip is None:
        all_templates = sorted(templates_dir.glob("*.template.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not all_templates:
            return {"ok": False, "message": "No template zips found.", "out_dir": ""}
        selected_zip = all_templates[0]

    if out_dir:
        output_path = Path(out_dir).resolve()
    else:
        output_path = get_mfdb_dir(config).parent / "unchunked_templates" / f"{sanitize_name(config['project_name'])}_{selected_zip.stem}_{get_timestamp()}"
    output_path.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(str(selected_zip), "r") as zf:
            safe_extract_zip(zf, output_path)
        meta_path = output_path / TEMPLATE_META_FILE
        if meta_path.exists():
            meta_path.unlink()
        return {
            "ok": True,
            "message": f"TEMPLATE RESTORED: {selected_zip.name}",
            "out_dir": str(output_path),
            "template_path": str(selected_zip),
        }
    except Exception as e:
        return {"ok": False, "message": str(e), "out_dir": ""}


def do_bump(target_dir: str, part: str = "patch") -> dict:
    target_path = Path(target_dir).resolve()
    if not target_path.is_dir():
        return {"ok": False, "message": f"Not a directory: {target_dir}", "new_version": ""}
    config      = load_or_create_config(target_path)
    old_version = config["version"]
    new_version = bump_version(old_version, part)
    config["version"] = new_version
    save_config(target_path, config)
    return {"ok": True, "message": f"{old_version} → {new_version}", "new_version": new_version}


def do_unchunk(manifest_path_arg: str, version: str) -> dict:
    manifest_path = Path(manifest_path_arg).resolve()
    if not manifest_path.exists():
        return {"ok": False, "message": f"Manifest not found: {manifest_path}", "out_dir": ""}

    entity_name = version_to_entity_name(version)
    try:
        manifest_doc = BEJSONCore.bejson_core_load_file(str(manifest_path))
        m_fields     = [f["name"] for f in manifest_doc["Fields"]]
        fp_idx       = m_fields.index("file_path")
        en_idx       = m_fields.index("entity_name")

        row = next((r for r in manifest_doc["Values"]
                    if r[en_idx] == entity_name), None)
        if row is None:
            return {"ok": False, "message": f"Version '{version}' not found in manifest.",
                    "out_dir": ""}

        entity_abs = manifest_path.parent / row[fp_idx]
        if not entity_abs.exists():
            return {"ok": False, "message": f"Entity file missing: {entity_abs}",
                    "out_dir": ""}

        entity_doc = BEJSONCore.bejson_core_load_file(str(entity_abs))
        version_rows = _get_version_rows(entity_doc, entity_name)

        if not version_rows:
            return {"ok": False, "message": f"No file records found for version '{version}'.",
                    "out_dir": ""}

        db_name = manifest_doc.get("DB_Name", "project")
        out_dir = manifest_path.parent.parent / "unchunked" / \
                  f"{db_name}_{entity_name}_{get_timestamp()}"
        out_dir.mkdir(parents=True, exist_ok=True)

        file_count = 0
        for record in version_rows:
            rel_path = record[E_FILE_PATH]
            if not rel_path:
                continue
            out_file = out_dir / rel_path
            out_file.parent.mkdir(parents=True, exist_ok=True)
            is_b64 = len(record) > E_IS_BASE64 and record[E_IS_BASE64]
            if is_b64:
                out_file.write_bytes(base64.b64decode(record[E_CONTENT]))
            elif record[E_IS_BINARY]:
                out_file.touch()
            else:
                out_file.write_text(record[E_CONTENT] or "", encoding="utf-8")
            file_count += 1

        return {
            "ok":        True,
            "message":   f"VERSION {version} RESTORED TO DISK",
            "out_dir":   str(out_dir),
            "file_count": file_count,
        }
    except Exception as e:
        return {"ok": False, "message": str(e), "out_dir": ""}


def do_update_changelog(manifest_path_arg: str, version: str,
                        new_changelog: str) -> dict:
    """Edit changelog of an already-chunked version in the manifest only."""
    manifest_path = Path(manifest_path_arg).resolve()
    if not manifest_path.exists():
        return {"ok": False, "message": "Manifest not found."}

    entity_name = version_to_entity_name(version)
    try:
        doc = BEJSONCore.bejson_core_load_file(str(manifest_path))
        found = False
        for row in doc["Values"]:
            if row[M_ENTITY_NAME] == entity_name:
                # Extend row if it's an older manifest without all fields
                while len(row) < len(MANIFEST_FIELDS):
                    row.append("")
                row[M_CHANGELOG] = new_changelog
                found = True
                break
        if not found:
            return {"ok": False, "message": f"Version '{version}' not found."}
        _write_manifest(str(manifest_path), doc)
        return {"ok": True, "message": f"CHANGELOG UPDATED FOR {version}"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


def do_update_tags(manifest_path_arg: str, version: str,
                   tags: str) -> dict:
    """Set tags (comma-separated string) on a version in the manifest."""
    manifest_path = Path(manifest_path_arg).resolve()
    if not manifest_path.exists():
        return {"ok": False, "message": "Manifest not found."}

    entity_name = version_to_entity_name(version)
    try:
        doc = BEJSONCore.bejson_core_load_file(str(manifest_path))
        found = False
        for row in doc["Values"]:
            if row[M_ENTITY_NAME] == entity_name:
                while len(row) < len(MANIFEST_FIELDS):
                    row.append("")
                row[M_TAGS] = tags
                found = True
                break
        if not found:
            return {"ok": False, "message": f"Version '{version}' not found."}
        _write_manifest(str(manifest_path), doc)
        return {"ok": True, "message": f"TAGS UPDATED FOR {version}"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


def do_prune(manifest_path_arg: str, version: str) -> dict:
    """Remove a version from the manifest and its rows from the entity file."""
    manifest_path = Path(manifest_path_arg).resolve()
    if not manifest_path.exists():
        return {"ok": False, "message": "Manifest not found."}

    entity_name = version_to_entity_name(version)
    try:
        manifest_doc = BEJSONCore.bejson_core_load_file(str(manifest_path))

        # Find the manifest row
        target_row = next((r for r in manifest_doc["Values"] if r and any(r) and r[M_ENTITY_NAME] == entity_name), None)
        if target_row is None:
            return {"ok": False, "message": f"Version '{version}' not found in manifest."}

        entity_rel  = target_row[M_FILE_PATH]
        entity_abs  = manifest_path.parent / entity_rel

        # Remove from entity file (atomic)
        rows_removed = 0
        if entity_abs.exists():
            entity_doc   = BEJSONCore.bejson_core_load_file(str(entity_abs))
            rows_removed = _remove_version_rows(entity_doc, entity_name)
            _write_entity(str(entity_abs), entity_doc)

        # Remove from manifest (atomic)
        manifest_doc["Values"] = [r for r in manifest_doc["Values"]
                                   if r[M_ENTITY_NAME] != entity_name]
        _write_manifest(str(manifest_path), manifest_doc)

        return {
            "ok":          True,
            "message":     f"VERSION {version} PRUNED",
            "rows_removed": rows_removed,
        }
    except Exception as e:
        return {"ok": False, "message": str(e)}


def do_export(manifest_path_arg: str, version: str, out_path: str) -> dict:
    """
    Export a version as a self-contained zip.
    Zip layout: 104a.mfdb.bejson + data/<entity>.bejson (version rows only).
    """
    manifest_path = Path(manifest_path_arg).resolve()
    if not manifest_path.exists():
        return {"ok": False, "message": "Manifest not found.", "zip_path": ""}

    entity_name = version_to_entity_name(version)
    try:
        manifest_doc = BEJSONCore.bejson_core_load_file(str(manifest_path))

        target_row = next((r for r in manifest_doc["Values"] if r and any(r) and r[M_ENTITY_NAME] == entity_name), None)
        if target_row is None:
            return {"ok": False, "message": f"Version '{version}' not found.", "zip_path": ""}

        entity_rel = target_row[M_FILE_PATH]
        entity_abs = manifest_path.parent / entity_rel
        if not entity_abs.exists():
            return {"ok": False, "message": f"Entity file missing: {entity_abs}", "zip_path": ""}

        entity_doc   = BEJSONCore.bejson_core_load_file(str(entity_abs))
        version_rows = _get_version_rows(entity_doc, entity_name)

        # Build export manifest with only this version's row
        export_manifest = dict(manifest_doc)
        export_manifest["Values"] = [target_row]

        # Build export entity with only this version's rows
        export_entity = dict(entity_doc)
        export_entity["Values"] = version_rows

        # Write to temp dir then zip
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "data").mkdir()

            manifest_tmp = tmp_path / "104a.mfdb.bejson"
            entity_tmp   = tmp_path / entity_rel

            manifest_tmp.write_text(json.dumps(export_manifest, indent=2, ensure_ascii=False),
                                    encoding="utf-8")
            entity_tmp.write_text(json.dumps(export_entity, indent=2, ensure_ascii=False),
                                  encoding="utf-8")

            zip_path = Path(out_path)
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(str(manifest_tmp), "104a.mfdb.bejson")
                zf.write(str(entity_tmp), entity_rel)

        db_name = manifest_doc.get("DB_Name", "project")
        return {
            "ok":       True,
            "message":  f"VERSION {version} EXPORTED",
            "zip_path": str(zip_path),
            "files":    len(version_rows),
            "db_name":  db_name,
        }
    except Exception as e:
        return {"ok": False, "message": str(e), "zip_path": ""}


def do_import(manifest_path_arg: str, zip_path_arg: str,
              on_conflict: str = "reject") -> dict:
    """
    Import versions from an export zip into an existing MFDB.
    on_conflict: "reject" (skip existing) | "prefix" (rename with _imp suffix)
    """
    manifest_path = Path(manifest_path_arg).resolve()
    zip_path      = Path(zip_path_arg).resolve()

    if not manifest_path.exists():
        return {"ok": False, "message": "Target manifest not found.", "imported": [], "skipped": []}
    if not zip_path.exists():
        return {"ok": False, "message": f"Zip not found: {zip_path}", "imported": [], "skipped": []}

    imported = []
    skipped  = []

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with zipfile.ZipFile(str(zip_path), "r") as zf:
                zf.extractall(str(tmp_path))

            imp_manifest_path = tmp_path / "104a.mfdb.bejson"
            if not imp_manifest_path.exists():
                return {"ok": False, "message": "Zip missing 104a.mfdb.bejson",
                        "imported": [], "skipped": []}

            imp_manifest = BEJSONCore.bejson_core_load_file(str(imp_manifest_path))
            tgt_manifest = BEJSONCore.bejson_core_load_file(str(manifest_path))

            existing_entity_names = {r[M_ENTITY_NAME] for r in tgt_manifest["Values"]}

            for imp_row in imp_manifest["Values"]:
                # Extend row to full width if needed
                while len(imp_row) < len(MANIFEST_FIELDS):
                    imp_row.append("")

                imp_entity_name = imp_row[M_ENTITY_NAME]
                imp_entity_rel  = imp_row[M_FILE_PATH]
                imp_entity_abs  = tmp_path / imp_entity_rel

                if not imp_entity_abs.exists():
                    skipped.append(f"{imp_entity_name}: entity file missing in zip")
                    continue

                # Conflict handling
                final_entity_name = imp_entity_name
                if imp_entity_name in existing_entity_names:
                    if on_conflict == "reject":
                        skipped.append(f"{imp_entity_name}: already exists (rejected)")
                        continue
                    else:  # prefix
                        final_entity_name = imp_entity_name + "_imp"
                        if final_entity_name in existing_entity_names:
                            skipped.append(f"{imp_entity_name}: conflict and prefix taken")
                            continue
                        imp_row[M_ENTITY_NAME] = final_entity_name

                # Load import entity and rename its version keys if prefixed
                imp_entity = BEJSONCore.bejson_core_load_file(str(imp_entity_abs))
                new_rows   = []
                for r in imp_entity["Values"]:
                    r = list(r)
                    if r[E_VERSION] == imp_entity_name and final_entity_name != imp_entity_name:
                        r[E_VERSION] = final_entity_name
                    new_rows.append(r)

                # Target entity path (same entity file as other versions of this DB)
                tgt_entity_rel  = imp_entity_rel
                tgt_entity_abs  = manifest_path.parent / tgt_entity_rel
                tgt_entity_abs.parent.mkdir(parents=True, exist_ok=True)

                if tgt_entity_abs.exists():
                    tgt_entity = BEJSONCore.bejson_core_load_file(str(tgt_entity_abs))
                else:
                    tgt_entity = dict(imp_entity)
                    tgt_entity["Values"] = []
                    ph = os.path.relpath(str(manifest_path),
                                         str(tgt_entity_abs.parent))
                    tgt_entity["Parent_Hierarchy"] = ph

                tgt_entity["Values"].extend(new_rows)
                _write_entity(str(tgt_entity_abs), tgt_entity)

                # Append manifest row
                imp_row[M_FILE_PATH] = tgt_entity_rel
                tgt_manifest["Values"].append(imp_row)
                existing_entity_names.add(final_entity_name)
                imported.append(final_entity_name)

            _write_manifest(str(manifest_path), tgt_manifest)

        return {
            "ok":      True,
            "message": f"IMPORT COMPLETE: {len(imported)} imported, {len(skipped)} skipped",
            "imported": imported,
            "skipped":  skipped,
        }
    except Exception as e:
        return {"ok": False, "message": str(e), "imported": [], "skipped": []}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=f"BEJSON MFDB Chunker v2 — MFDB Spec {MFDB_SPEC_VERSION}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python mfdb_chunker.py --chunk  ./MyProject --changelog "Fix auth" --tags "stable,release"
  python mfdb_chunker.py --chunk-template ./MyProject --template-name sprint_baseline
  python mfdb_chunker.py --unchunk-template ./MyProject --template-name sprint_baseline
  python mfdb_chunker.py --bump   ./MyProject --bump-part minor
  python mfdb_chunker.py --list   ./output/MyProject_MFDB/104a.mfdb.bejson
  python mfdb_chunker.py --unchunk ./output/MyProject_MFDB/104a.mfdb.bejson --version 1.0.0
  python mfdb_chunker.py --prune  ./output/MyProject_MFDB/104a.mfdb.bejson --version 1.0.0
  python mfdb_chunker.py --export ./output/MyProject_MFDB/104a.mfdb.bejson --version 1.0.0 --out ./export.zip
  python mfdb_chunker.py --import ./output/MyProject_MFDB/104a.mfdb.bejson --zip ./export.zip
""",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--chunk",    metavar="DIR")
    group.add_argument("--chunk-template", metavar="DIR")
    group.add_argument("--unchunk",  metavar="MANIFEST")
    group.add_argument("--unchunk-template", metavar="DIR")
    group.add_argument("--list",     metavar="MANIFEST")
    group.add_argument("--bump",     metavar="DIR")
    group.add_argument("--prune",    metavar="MANIFEST")
    group.add_argument("--export",   metavar="MANIFEST")
    group.add_argument("--import",   metavar="MANIFEST", dest="import_manifest")
    group.add_argument("--validate", metavar="MANIFEST")
    group.add_argument("--snapshot", metavar="DIR")

    parser.add_argument("--version",     metavar="VER")
    parser.add_argument("--template-name", metavar="NAME",
                        help="Template name for --chunk-template / --unchunk-template")
    parser.add_argument("--template-out", metavar="PATH",
                        help="Output path for --unchunk-template")
    parser.add_argument("--changelog",   metavar="TEXT",  default="")
    parser.add_argument("--tags",        metavar="TAGS",  default="",
                        help="Comma-separated tags e.g. 'stable,release'")
    parser.add_argument("--bump-part",   metavar="PART",  default="patch",
                        choices=["major", "minor", "patch"])
    parser.add_argument("--out",         metavar="PATH",
                        help="Output path for --export")
    parser.add_argument("--zip",         metavar="PATH",
                        help="Zip path for --import")
    parser.add_argument("--on-conflict", metavar="MODE",  default="reject",
                        choices=["reject", "prefix"],
                        help="Conflict resolution for --import: reject or prefix")

    args = parser.parse_args()

    if args.chunk:
        r = do_chunk(args.chunk, args.changelog, args.tags)
        print(f"[{'OK' if r['ok'] else 'ERROR'}] {r['message']}")
        if r["ok"]:
            d = r["detail"]
            print(f"  Files   : {d['file_count']}")
            print(f"  Entity  : {d['entity_path']}")
            if d["skipped"]:
                print(f"  Skipped : {d['skipped']}")

    elif args.chunk_template:
        r = do_chunk_template(args.chunk_template, args.template_name or "")
        print(f"[{'OK' if r['ok'] else 'ERROR'}] {r['message']}")
        if r["ok"]:
            print(f"  Template: {r['template_path']}")
            print(f"  Files   : {r['file_count']}")

    elif args.unchunk_template:
        r = do_unchunk_template(args.unchunk_template, args.template_name or "",
                                args.template_out or "")
        print(f"[{'OK' if r['ok'] else 'ERROR'}] {r['message']}")
        if r["ok"]:
            print(f"  Template: {r['template_path']}")
            print(f"  Output  : {r['out_dir']}")

    elif args.unchunk:
        if not args.version:
            parser.error("--unchunk requires --version")
        r = do_unchunk(args.unchunk, args.version)
        print(f"[{'OK' if r['ok'] else 'ERROR'}] {r['message']}")
        if r["ok"]:
            print(f"  Output  : {r['out_dir']}")
            print(f"  Files   : {r['file_count']}")

    elif args.bump:
        r = do_bump(args.bump, args.bump_part)
        print(f"[{'OK' if r['ok'] else 'ERROR'}] {r['message']}")

    elif args.prune:
        if not args.version:
            parser.error("--prune requires --version")
        r = do_prune(args.prune, args.version)
        print(f"[{'OK' if r['ok'] else 'ERROR'}] {r['message']}")
        if r["ok"]:
            print(f"  Rows removed: {r['rows_removed']}")

    elif args.export:
        if not args.version:
            parser.error("--export requires --version")
        out = args.out or f"./{args.version}.mfdb.zip"
        r   = do_export(args.export, args.version, out)
        print(f"[{'OK' if r['ok'] else 'ERROR'}] {r['message']}")
        if r["ok"]:
            print(f"  Zip   : {r['zip_path']}")
            print(f"  Files : {r['files']}")

    elif args.import_manifest:
        if not args.zip:
            parser.error("--import requires --zip")
        r = do_import(args.import_manifest, args.zip, args.on_conflict)
        print(f"[{'OK' if r['ok'] else 'ERROR'}] {r['message']}")
        if r["imported"]:
            print(f"  Imported: {', '.join(r['imported'])}")
        if r["skipped"]:
            print(f"  Skipped : {', '.join(r['skipped'])}")


    elif args.validate:
        r = do_validate(args.validate)
        print(f"[{'OK' if r['ok'] else 'ERROR'}] {r['message']}")
        if not r['ok'] and 'errors' in r:
            for err in r['errors']: print(f"  - {err}")

    elif args.snapshot:
        r = do_snapshot(args.snapshot)
        print(f"[{'OK' if r['ok'] else 'ERROR'}] {r['message']}")
        if r['ok']: print(f"  Zip: {r['zip_path']}")

    elif args.list:
        versions = list_versions(args.list)
        meta     = get_manifest_meta(args.list)
        print(f"DB: {meta.get('DB_Name', '?')}  |  MFDB {meta.get('MFDB_Version', '?')}")
        print(f"Versions ({len(versions)}):")
        for v in versions:
            tags = f"  [{v.get('tags')}]" if v.get("tags") else ""
            print(f"  [{v.get('entity_name')}]  files={v.get('record_count')}"
                  f"  chunked={str(v.get('chunked_at',''))[:19].replace('T',' ')}{tags}")
            if v.get("changelog"):
                print(f"    → {v['changelog']}")


if __name__ == "__main__":
    main()
