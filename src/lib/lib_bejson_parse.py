"""
Library:      lib_bejson_parse.py
Family:       Core
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.1.0 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-21
Description:  Rapid indexing and retrieval engine for dense tabular data.
              REMEDIATED: Removed all regex usage. Uses strictly string methods.
"""

import datetime
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

# ------------------------------------------------------------------
# BEJSON ecosystem — core + validator sourced here
# ------------------------------------------------------------------
from lib_bejson_core import (
    BEJSONCoreError,
    bejson_core_is_valid,
    bejson_core_get_version,
    bejson_core_get_stats,
)
from lib_bejson_validator import (
    BEJSONValidationError,
    bejson_validator_validate_string,
    bejson_validator_get_report,
)

# Default output dir
_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT  = os.path.join(_SCRIPT_DIR, "output")

# ------------------------------------------------------------------
# ATOMIC WRITE HELPER
# ------------------------------------------------------------------

def _atomic_write_text(file_path: str, content: str) -> None:
    """Write text to file_path atomically with fsync."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    temp_dir = str(path.parent)
    fd, tmp_path = tempfile.mkstemp(dir=temp_dir, suffix=".tmp", prefix=".parse_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.rename(tmp_path, file_path)
        # fsync the directory
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

from lib_bejson_utility import bejson_utility_parse_json, bejson_utility_slugify

# ------------------------------------------------------------------
# PARSER CORE (Best Practices - No Regex)
# ------------------------------------------------------------------

def parse_json(text):
    """Delegates to standardized utility parser (COMPLEX-6)."""
    return bejson_utility_parse_json(text)

def extract_data(data):
    fields = data.get("Fields", [])
    values = data.get("Values", [])
    if not values:
        return "My_Project", []

    # Map fields by exact name (COMPLEX-5)
    f_map = {f["name"]: i for i, f in enumerate(fields)}

    def get_val(row, key):
        idx = f_map.get(key)
        if idx is not None and idx < len(row):
            v = row[idx]
            if v is not None:
                return str(v).strip()
        return None

    project_name = "My_Project"
    for row in values:
        # Check standard project identifiers
        for key in ("project_name", "zip_filename", "container_name"):
            v = get_val(row, key)
            if v:
                project_name = v
                break
        if project_name != "My_Project":
            break

    # Use utility slugify for consistency (REC-1)
    project_name = bejson_utility_slugify(project_name).replace("-", "_")

    files = []
    for row in values:
        # Standard range check for chunked files
        for i in range(1, 51):
            fname = get_val(row, f"file_{i}_name")
            fcont = get_val(row, f"file_{i}_content")
            if fname and fcont:
                files.append({"name": fname, "content": fcont})

    return project_name, files

from lib_bejson_path_guard import bejson_safe_join

def save_files(proj, files, cfg):
    base_dir = cfg.get("output_path") or DEFAULT_OUT
    if not os.path.isdir(base_dir):
        try:
            os.makedirs(base_dir, exist_ok=True)
        except Exception as e:
            return {"success": False, "message": "Cannot create output dir: " + str(e)}

    overwrite = cfg.get("overwrite_enabled", False)

    if overwrite:
        target     = os.path.join(base_dir, proj)
        bak_target = os.path.join(base_dir, proj + "_BACKUP")
        if os.path.exists(target):
            if os.path.exists(bak_target):
                shutil.rmtree(bak_target, ignore_errors=True)
            try:
                shutil.copytree(target, bak_target)
            except Exception as e:
                print("Backup warning: " + str(e))
    else:
        ts     = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        target = os.path.join(base_dir, ts + "_" + proj)

    try:
        # Phase 2: Resolve and Guard target path
        target = os.path.abspath(target)
        os.makedirs(target, exist_ok=True)

        for f in files:
            # Phase 2: Assert boundary prefixes via safe_join
            fpath = bejson_safe_join(target, f["name"])
            _atomic_write_text(fpath, f["content"])

        # Build report
        ts_now   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        mode_str = "Merge/Update (overwrite)" if overwrite else "Timestamped (new folder)"
        lines    = []
        lines.append("=" * 52)
        lines.append("  STRUCTURED PARSER — BUILD REPORT")
        lines.append("=" * 52)
        lines.append("Project    : " + proj)
        lines.append("Generated  : " + ts_now)
        lines.append("Mode       : " + mode_str)
        lines.append("Output Dir : " + target)
        lines.append("Files      : " + str(len(files)))
        lines.append("-" * 52)
        lines.append("FILE LIST")
        lines.append("-" * 52)
        for idx, f in enumerate(files):
            size_b = len(f["content"].encode("utf-8"))
            if size_b >= 1024:
                size_s = str(round(size_b / 1024.0, 1)) + " KB"
            else:
                size_s = str(size_b) + " B"
            lines.append("  [" + str(idx + 1).zfill(2) + "] " + f["name"] + "  (" + size_s + ")")
        lines.append("-" * 52)
        lines.append("Zip        : " + proj + "_update.zip")
        lines.append("=" * 52)
        report_text = "\n".join(lines) + "\n"

        # Write report to disk atomically
        report_path = os.path.join(target, "_REPORT.txt")
        _atomic_write_text(report_path, report_text)

        # Build zip
        zip_path = os.path.join(target, proj + "_update.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                zf.writestr(f["name"], f["content"])
            zf.writestr("_REPORT.txt", report_text)

        return {
            "success":    True,
            "message":    "Saved " + str(len(files)) + " file(s)",
            "path":       target,
            "file_count": len(files),
        }

    except Exception as e:
        return {"success": False, "message": str(e)}
