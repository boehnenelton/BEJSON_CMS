"""
Library:        lib_bejson_CMS_cms_ports.py
Family:         CMS
Description:    Reads/creates config.json (BEJSON 104a ScriptConfig, per
                System Development Policy §8.4) at the project root and
                resolves each service's port with precedence:
                env var (if set) > config.json > hardcoded default.
                Auto-generates config.json with defaults on first run if
                it's missing or unreadable. New in pkg75 -- added as a new
                function/module rather than edited into an existing lib,
                per Library Immutability policy.
Version:        1.1.0
Date:           2026-10-25
Author:         Elton Boehnen
Contact:        eltonboehnen@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  8d2b7f3c-5e1e-4b8f-9a1f-3c7b4d0e2f8a
"""

import os
import json
from typing import Dict, Optional
from lib_bejson_Core_bejson_core import bejson_core_get_field_map, bejson_core_atomic_write

VERSION = "1.1.0"

# setting_name -> (default_port, description)
_PORT_SETTINGS = {
    "admin_port":       (5001, "Port for BEJSON_CMS_Admin.py (dashboard)."),
    "pageeditor_port":  (5003, "Port for BEJSON_CMS_PageEditor.py (V1)."),
    "pageeditorv2_port": (5010, "Port for BEJSON_CMS_PageEditorV2.py (V2)."),
    "publisher_port":   (5001, "Port for BEJSON_CMS_Publisher.py. Same default as "
                                "admin_port -- the advanced launcher auto-bumps this by "
                                "+10 if both are started at once, to avoid a collision."),
    "profiles_port":    (5004, "Port for BEJSON_CMS_ProfileManager.py (Persona Hub)."),
}

# service_key (as used by advanced_launcher.py) -> (setting_name, env_var)
SERVICE_PORT_MAP = {
    "admin":      ("admin_port", "CMS_ADMIN_PORT"),
    "editor":     ("pageeditor_port", "CMS_PAGEEDITOR_PORT"),
    "editorv2":   ("pageeditorv2_port", "CMS_PAGEEDITORV2_PORT"),
    "publisher":  ("publisher_port", "CMS_PUBLISHER_PORT"),
    "profiles":   ("profiles_port", "CMS_PROFILES_PORT"),
}


def _default_doc() -> dict:
    return {
        "Format": "BEJSON",
        "Format_Version": "104a",
        "Format_Creator": "Elton Boehnen",
        "Records_Type": ["ScriptConfig"],
        "Fields": [
            {"name": "setting_name", "type": "string"},
            {"name": "setting_value", "type": "any"},
            {"name": "description", "type": "string"},
        ],
        "Values": [[name, default, desc] for name, (default, desc) in _PORT_SETTINGS.items()],
    }


def ensure_config(config_path: str) -> dict:
    """Loads config.json if present and valid; otherwise (re)creates it with
    defaults via an atomic write. Always returns a usable doc."""
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                doc = json.load(f)
            if isinstance(doc, dict) and "Values" in doc and "Fields" in doc:
                return doc
        except Exception:
            pass  # fall through and regenerate a corrupt/unreadable file

    doc = _default_doc()
    bejson_core_atomic_write(config_path, doc)
    return doc


def get_port(config_path: str, setting_name: str, env_var: Optional[str] = None) -> int:
    """Resolves one service's port: env var (if set and valid) > config.json
    value > hardcoded default. Never raises -- falls back safely at each step."""
    if env_var:
        raw = os.environ.get(env_var)
        if raw:
            try:
                return int(raw)
            except ValueError:
                pass

    doc = ensure_config(config_path)
    field_map = bejson_core_get_field_map(doc)
    name_col_idx = field_map.get("setting_name")
    value_col_idx = field_map.get("setting_value")
    if name_col_idx is not None and value_col_idx is not None:
        for row in doc.get("Values", []):
            if row and len(row) > max(name_col_idx, value_col_idx) and str(row[name_col_idx]).strip() == setting_name:
                try:
                    return int(row[value_col_idx])
                except (TypeError, ValueError):
                    break

    return _PORT_SETTINGS.get(setting_name, (5000, ""))[0]


def get_all_ports(config_path: str) -> Dict[str, int]:
    """Returns every configured port as {setting_name: port}, config.json
    values layered over defaults (does not apply env var overrides -- callers
    needing the fully-resolved value for one service should use get_port())."""
    result = {name: default for name, (default, _desc) in _PORT_SETTINGS.items()}
    doc = ensure_config(config_path)
    field_map = bejson_core_get_field_map(doc)
    name_col_idx = field_map.get("setting_name")
    value_col_idx = field_map.get("setting_value")
    if name_col_idx is not None and value_col_idx is not None:
        for row in doc.get("Values", []):
            if row and len(row) > max(name_col_idx, value_col_idx):
                row_setting_name = str(row[name_col_idx]).strip()
                if row_setting_name in result:
                    try:
                        result[row_setting_name] = int(row[value_col_idx])
                    except (TypeError, ValueError):
                        pass
    return result
