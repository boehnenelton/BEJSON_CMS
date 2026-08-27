"""
Library:         BEJSON_CMS_Shared
Family:          BEJSON_CMS
Description:     Shared substrate for all BEJSON_CMS blueprints: path config, DB handle, base template/render helper, nav structure, auth guard.
Version:         18.23
Library_Version: 57
Date:            2026-08-05
RELATIONAL_ID:   b8e14c52-46ea-4b2e-af32-b4c2bcc1698b
"""

import os
import sys
import logging
import logging.handlers
from pathlib import Path
from flask import request, render_template_string

# ─── HTTP Basic Auth ────────────────────────────────────────────────────────
import functools

# ─── HTTP Basic Auth ──────────────────────────────────────────────────────────
# Set CMS_PASSWORD env var before starting. Default: 'changeme' (MUST change).
_CMS_USER = os.environ.get("CMS_USER", "admin")
_CMS_PASS = os.environ.get("CMS_PASSWORD", "changeme")
_USING_DEFAULT_PASSWORD = "CMS_PASSWORD" not in os.environ

def _check_auth(username, password):
    return username == _CMS_USER and password == _CMS_PASS

def _unauthorized():
    return ("Unauthorized — Set CMS_PASSWORD env var and restart.", 401,
            {"WWW-Authenticate": 'Basic realm="BEJSON CMS"'})

def require_auth(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        Request_Basic_Auth_Header = request.authorization
        if not Request_Basic_Auth_Header or not _check_auth(Request_Basic_Auth_Header.username, Request_Basic_Auth_Header.password):
            return _unauthorized()
        return f(*args, **kwargs)
    return decorated

# ─── Script path resolution + BEJSON library imports ───────────────────────
def get_script_path() -> Path:
    return Path(__file__).resolve().parent
SCRIPT_PATH = get_script_path()

# Import BEJSON Libraries
# Import New MFDB Orchestrator
PROJECT_ROOT = SCRIPT_PATH.parent.parent
LIB_DIR = PROJECT_ROOT / "src" / "lib"

if str(LIB_DIR) not in sys.path:
    sys.path.append(str(LIB_DIR))

import lib_bejson_CMS_cms_core as CMSCore
import lib_bejson_Core_mfdb_core as MFDBCore
import lib_bejson_CMS_cms_config as CMSConfig
import lib_bejson_CMS_cms_ports as CMSPorts

# ─── Deployment config (config.json — ports etc., see lib_bejson_CMS_cms_ports) ─
# Auto-created with defaults on first read if missing. Precedence for any
# single port: env var > config.json > hardcoded default.
CONFIG_PATH = PROJECT_ROOT / "config.json"
SERVICE_PORTS = CMSPorts.get_all_ports(str(CONFIG_PATH))   # {"admin_port": 5001, ...} from config.json
ADMIN_PORT = CMSPorts.get_port(str(CONFIG_PATH), "admin_port", "CMS_ADMIN_PORT")
PUBLISHER_PORT = CMSPorts.get_port(str(CONFIG_PATH), "publisher_port", "CMS_PUBLISHER_PORT")

# ─── Path configuration (Clean Root Architecture) ──────────────────────────
# Storage Domains
STORAGE_ROOT = PROJECT_ROOT / "storage"
MFDB_DIR = STORAGE_ROOT / "mfdb"
MANIFEST_PATH = MFDB_DIR / "site_master" / "104a.mfdb.bejson"
PAGES_DB_DIR = MFDB_DIR / "pages_db"

ASSETS_DIR = MFDB_DIR / "assets"
THUMBS_DIR = MFDB_DIR / "assets" / "_thumbs"
APPS_STORAGE = MFDB_DIR / "standalone_apps"
DEFAULT_FEATURED_IMAGE = "default_page_image.webp"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
THUMBS_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# DEBUG SWITCH + VERBOSE IMPORT/WRITE-PATH LOGGING (Sec 5.9)
# =============================================================================
# Persistent boolean switch lives in SiteConfig (config_key="debug_import_logging").
# Defaults to "true" (fail-open) since this is the active diagnostic pass for
# the import/upload freeze — set the SiteConfig value to "false" once resolved
# to silence it. Log file: storage/logs/import_debug.log (rotated at 2MB x3).
LOGS_DIR = STORAGE_ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

def _debug_logging_enabled() -> bool:
    try:
        Debug_Import_Logging_Flag_Raw = CMSConfig.cms_config_get(str(MANIFEST_PATH), "debug_import_logging", "true")
        return str(Debug_Import_Logging_Flag_Raw).strip().lower() in ("1", "true", "yes", "on")
    except Exception:
        return True  # fail open — never let a config read error silence diagnostics

_log_handler = logging.handlers.RotatingFileHandler(
    str(LOGS_DIR / "import_debug.log"), maxBytes=2_000_000, backupCount=3, encoding="utf-8"
)
_log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logging.getLogger().addHandler(_log_handler)
logging.getLogger().setLevel(logging.DEBUG if _debug_logging_enabled() else logging.WARNING)
logging.info("[CMS] Logging initialized. debug_import_logging=%s -> level=%s",
             _debug_logging_enabled(), logging.getLevelName(logging.getLogger().level))
EXPORTS_DIR = STORAGE_ROOT / "exports"
PUBLISH_DIR = STORAGE_ROOT / "builds"
UPLOAD_TMP  = STORAGE_ROOT / "tmp" / "html_imports"

# Resources Domain
RESOURCES_ROOT = PROJECT_ROOT / "resources"
TEMPLATE_DIR = RESOURCES_ROOT / "templates"

for d in [MFDB_DIR, PAGES_DB_DIR, ASSETS_DIR, APPS_STORAGE, EXPORTS_DIR, PUBLISH_DIR, UPLOAD_TMP, TEMPLATE_DIR]:
    os.makedirs(str(d), exist_ok=True)

db = CMSCore.CMSCore(str(MANIFEST_PATH))

# ─── Navigation structure ───────────────────────────────────────────────────
# =============================================================================

NAV_SECTIONS = {
    'dashboard': {
        'icon': '📊',
        'label': 'Dashboard',
        'href': '/',
        'children': []
    },
    'content': {
        'icon': '📝',
        'label': 'Content',
        'href': '/content',
        'children': [
            {'icon': '📄', 'label': 'All Pages', 'href': '/pages'},
            {'icon': '🔗', 'label': 'External Links', 'href': '/links'},
            {'icon': '📁', 'label': 'Categories', 'href': '/categories'},
            {'icon': '📥', 'label': 'HTML Import', 'href': '/import'},
        ]
    },
    'apps': {
        'icon': '🚀',
        'label': 'Applications',
        'href': '/apps',
        'children': []
    },
    'assets': {
        'icon': '🖼️',
        'label': 'Media Library',
        'href': '/assets',
        'children': []
    },
    'site': {
        'icon': '⚙️',
        'label': 'Site Config',
        'href': '/site',
        'children': [
            {'icon': '🏠', 'label': 'General', 'href': '/site'},
            {'icon': '🧭', 'label': 'Navigation', 'href': '/site/nav'},
            {'icon': '👤', 'label': 'Authors', 'href': '/site/authors'},
            {'icon': '📢', 'label': 'Ads', 'href': '/site/ads'},
            {'icon': '🔗', 'label': 'Social Links', 'href': '/site/social'},
        ]
    },
    'publish': {
        'icon': '📦',
        'label': 'Publish',
        'href': '/publish',
        'children': []
    },
    'reset': {
        'icon': '⚠️',
        'label': 'Factory Reset',
        'href': '/reset',
        'children': []
    }
}

# =============================================================================
# BASE TEMPLATE
# =============================================================================

# ─── Base template ──────────────────────────────────────────────────────────
BASE_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>{% block title %}BEJSON Manager{% endblock %}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;900&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0a0a0a;
            --bg-secondary: #141414;
            --bg-card: #1e1e1e;
            --accent: #DE2626;
            --accent-hover: #b91c1c;
            --text-primary: #ffffff;
            --text-secondary: #a0a0a0;
            --border: #2a2a2a;
            --success: #22c55e;
            --warning: #f59e0b;
            --sidebar-width: 280px;
            --header-height: 64px;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body { height: 100%; }
        body {
            font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            overflow-x: hidden;
        }
        .app-wrapper { display: flex; min-height: 100vh; }
        .sidebar {
            width: var(--sidebar-width);
            background: var(--bg-secondary);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            position: fixed;
            top: 0; left: 0; bottom: 0;
            z-index: 1000;
            transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .sidebar-header {
            padding: 0 20px;
            border-bottom: 2px solid var(--accent);
            display: flex;
            align-items: center;
            justify-content: space-between;
            height: var(--header-height);
            background: var(--bg-secondary);
        }
        .logo { font-size: 1.5rem; font-weight: 900; color: var(--text-primary); text-decoration: none; letter-spacing: -1px; }
        .logo span { color: var(--accent); }
        .sidebar-close {
            display: none;
            background: none;
            border: none;
            color: var(--text-primary);
            font-size: 1.75rem;
            cursor: pointer;
            width: 40px; height: 40px;
            border-radius: 8px;
            align-items: center;
            justify-content: center;
        }
        .sidebar-close:hover { background: rgba(255,255,255,0.1); }
        .sidebar-nav { flex: 1; overflow-y: auto; padding: 12px 0; }
        .nav-section { margin-bottom: 4px; }
        .nav-item {
            display: flex;
            align-items: center;
            gap: 14px;
            padding: 12px 20px;
            color: var(--text-secondary);
            text-decoration: none;
            font-weight: 500;
            font-size: 0.95rem;
            transition: all 0.2s ease;
            cursor: pointer;
        }
        .nav-item:hover { background: rgba(222, 38, 38, 0.1); color: var(--text-primary); }
        .nav-item.active { background: var(--accent); color: white; }
        .nav-item .icon { font-size: 1.25rem; width: 26px; text-align: center; flex-shrink: 0; }
        .nav-toggle { margin-left: auto; font-size: 0.7rem; transition: transform 0.2s ease; opacity: 0.7; }
        .nav-toggle.expanded { transform: rotate(90deg); }
        .nav-children { display: none; background: rgba(0,0,0,0.2); }
        .nav-children.expanded { display: block; }
        .nav-child { padding-left: 60px; font-size: 0.9rem; }
        .sidebar-footer {
            padding: 16px 20px;
            border-top: 1px solid var(--border);
            font-size: 0.75rem;
            color: var(--text-secondary);
        }
        .main-wrapper {
            flex: 1;
            min-width: 0;
            width: 0;
            margin-left: var(--sidebar-width);
            display: flex;
            flex-direction: column;
            min-height: 100vh;
            transition: margin-left 0.3s ease;
        }
        .top-header {
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border);
            padding: 0 24px;
            height: var(--header-height);
            display: flex;
            align-items: center;
            justify-content: space-between;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        .header-left { display: flex; align-items: center; gap: 16px; }
        .menu-toggle {
            display: none;
            background: none;
            border: none;
            color: var(--text-primary);
            font-size: 1.5rem;
            cursor: pointer;
            width: 40px; height: 40px;
            border-radius: 8px;
            align-items: center;
            justify-content: center;
        }
        .menu-toggle:hover { background: rgba(255,255,255,0.1); }
        .breadcrumbs { display: flex; align-items: center; gap: 8px; font-size: 0.875rem; flex-wrap: wrap; }
        .breadcrumbs a { color: var(--text-secondary); text-decoration: none; transition: color 0.2s; }
        .breadcrumbs a:hover { color: var(--accent); }
        .breadcrumbs .separator { color: var(--text-secondary); opacity: 0.4; }
        .breadcrumbs .current { color: var(--text-primary); font-weight: 600; }
        .content-area {
            flex: 1;
            padding: 24px;
            max-width: 1400px;
            margin: 0 auto;
            width: 100%;
            min-width: 0;
            box-sizing: border-box;
        }
        .sidebar-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.7);
            backdrop-filter: blur(4px);
            z-index: 999;
            opacity: 0;
            transition: opacity 0.3s ease;
        }
        .sidebar-overlay.active { display: block; opacity: 1; }
        .page-header { margin-bottom: 24px; }
        .page-header h1 { font-size: 1.75rem; font-weight: 800; color: var(--accent); margin-bottom: 6px; }
        .page-header p { color: var(--text-secondary); font-size: 0.95rem; }
        .card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
            min-width: 0;
            overflow: hidden;
        }
        .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }
        .card-title { font-size: 1.1rem; font-weight: 700; }
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            font-family: inherit;
            font-weight: 600;
            font-size: 0.9rem;
            cursor: pointer;
            transition: all 0.2s ease;
            text-decoration: none;
        }
        .btn-primary { background: var(--accent); color: white; }
        .btn-primary:hover { background: var(--accent-hover); transform: translateY(-1px); }
        .btn-secondary { background: var(--bg-secondary); color: var(--text-primary); border: 1px solid var(--border); }
        .btn-secondary:hover { background: var(--border); }
        .btn-success { background: var(--success); color: white; }
        .btn-danger { background: #dc2626; color: white; }
        .btn-sm { padding: 6px 14px; font-size: 0.8rem; }
        .form-group { margin-bottom: 20px; }
        .form-label { display: block; margin-bottom: 8px; font-weight: 600; color: var(--text-secondary); font-size: 0.9rem; }
        .form-control {
            width: 100%;
            padding: 12px 16px;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text-primary);
            font-family: inherit;
            font-size: 1rem;
            transition: border-color 0.2s;
        }
        .form-control:focus { outline: none; border-color: var(--accent); }
        textarea.form-control { min-height: 120px; resize: vertical; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(280px, 100%), 1fr)); gap: 20px; }
        .grid > *, .grid-2 > *, .grid-3 > *, .grid-4 > * { min-width: 0; }
        .grid-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .grid-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
        .grid-4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
        @media (max-width: 1024px) { .grid-4 { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
        @media (max-width: 768px) {
            .grid-2, .grid-3, .grid-4 { grid-template-columns: 1fr; }
            .grid-stat { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }
        }
        .table-container { overflow-x: auto; border-radius: 8px; -webkit-overflow-scrolling: touch; display: block; width: 100%; }
        .table-container table { min-width: 500px; width: 100%; }
        th, td { white-space: nowrap; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 14px 16px; text-align: left; border-bottom: 1px solid var(--border); }
        th { font-weight: 600; color: var(--text-secondary); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; }
        tr:hover { background: rgba(222, 38, 38, 0.03); }
        .badge { display: inline-block; padding: 4px 10px; border-radius: 6px; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; }
        .badge-page { background: #3b82f6; color: white; }
        .badge-app { background: var(--success); color: white; }
        .badge-link { background: #8b5cf6; color: white; }
        .badge-active { background: var(--success); color: white; }
        .badge-inactive { background: #555; color: #ccc; }
        .alert { padding: 16px 20px; border-radius: 8px; margin-bottom: 20px; }
        .alert-success { background: rgba(34, 197, 94, 0.15); border: 1px solid rgba(34, 197, 94, 0.3); color: #4ade80; }
        .alert-error { background: rgba(220, 38, 38, 0.15); border: 1px solid rgba(220, 38, 38, 0.3); color: #f87171; }
        .tabs { display: flex; gap: 4px; margin-bottom: 24px; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
        .tab { padding: 12px 20px; background: none; border: none; color: var(--text-secondary); font-family: inherit; font-weight: 600; cursor: pointer; border-bottom: 2px solid transparent; font-size: 0.9rem; transition: all 0.2s; }
        .tab.active { color: var(--accent); border-bottom-color: var(--accent); }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .empty-state { text-align: center; padding: 60px 20px; color: var(--text-secondary); }
        .empty-state h3 { margin-bottom: 10px; color: var(--text-primary); font-size: 1.25rem; }
        .toolbar { display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }
        .search-box { position: relative; flex: 1; min-width: 200px; max-width: 400px; }
        .search-box input { width: 100%; padding-left: 44px; }
        .search-box::before { content: "🔍"; position: absolute; left: 14px; top: 50%; transform: translateY(-50%); opacity: 0.6; }
        .editor-toolbar { display: flex; gap: 6px; padding: 12px; background: var(--bg-secondary); border-radius: 8px 8px 0 0; border: 1px solid var(--border); border-bottom: none; flex-wrap: wrap; }
        .editor-toolbar button { padding: 8px 14px; background: var(--bg-card); border: 1px solid var(--border); color: var(--text-primary); border-radius: 6px; cursor: pointer; font-size: 0.8rem; font-weight: 500; transition: all 0.2s; }
        .editor-toolbar button:hover { background: var(--accent); border-color: var(--accent); }
        .editor-area { width: 100%; min-height: 400px; padding: 16px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 0 0 8px 8px; color: var(--text-primary); font-family: "Consolas", "Monaco", monospace; font-size: 0.9rem; line-height: 1.6; resize: vertical; }
        .modal-overlay { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8); backdrop-filter: blur(4px); z-index: 1001; align-items: center; justify-content: center; padding: 20px; }
        .modal-overlay.active { display: flex; }
        .modal { background: var(--bg-card); border-radius: 12px; width: 100%; max-width: 600px; max-height: 85vh; overflow-y: auto; border: 1px solid var(--border); }
        .modal-header { padding: 20px 24px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
        .modal-body { padding: 24px; }
        .close-btn { background: none; border: none; color: var(--text-secondary); font-size: 1.5rem; cursor: pointer; width: 36px; height: 36px; border-radius: 8px; display: flex; align-items: center; justify-content: center; }
        .close-btn:hover { background: rgba(255,255,255,0.1); color: var(--text-primary); }
        .asset-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 12px; }
        .asset-item { position: relative; cursor: pointer; border-radius: 8px; overflow: hidden; border: 2px solid transparent; transition: all 0.2s; }
        .asset-item:hover, .asset-item.selected { border-color: var(--accent); }
        .asset-item img { width: 100%; height: 100px; object-fit: cover; }
        .asset-item .asset-name { padding: 8px; font-size: 0.7rem; background: var(--bg-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .status-bar { background: var(--bg-secondary); border-top: 1px solid var(--border); padding: 12px 24px; display: flex; justify-content: space-between; align-items: center; font-size: 0.8rem; color: var(--text-secondary); }
        .stat-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; display: flex; align-items: center; gap: 14px; min-width: 0; }
        .stat-icon { width: 52px; height: 52px; flex-shrink: 0; background: rgba(222, 38, 38, 0.15); border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 1.6rem; }
        .stat-value { font-size: 2rem; font-weight: 800; color: var(--accent); line-height: 1; }
        .stat-label { color: var(--text-secondary); font-size: 0.85rem; margin-top: 4px; }
        .quick-actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
        .quick-action-btn { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 18px 10px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; color: var(--text-primary); text-decoration: none; transition: all 0.2s; min-width: 0; }
        .quick-action-btn:hover { border-color: var(--accent); background: rgba(222, 38, 38, 0.08); transform: translateY(-2px); }
        .quick-action-btn .icon { font-size: 1.5rem; }
        .quick-action-btn .label { font-size: 0.8rem; font-weight: 600; text-align: center; word-break: break-word; }
        @media (max-width: 768px) {
            .sidebar { transform: translateX(-100%); }
            .sidebar.open { transform: translateX(0); }
            .sidebar-close { display: flex; }
            .main-wrapper { margin-left: 0; width: 100%; }
            .menu-toggle { display: flex; }
            .breadcrumbs { display: none; }
            .content-area { padding: 12px; }
            .page-header h1 { font-size: 1.4rem; }
            .card { padding: 14px; }
            .stat-card { flex-direction: column; text-align: center; padding: 14px 10px; }
            .stat-icon { width: 44px; height: 44px; font-size: 1.3rem; }
            .stat-value { font-size: 1.6rem; }
            .top-header { padding: 0 14px; }
            .grid-stat { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; gap: 10px !important; }
            .system-status-grid { grid-template-columns: 1fr !important; }
            .form-group { margin-bottom: 12px; }
        }
    </style>
</head>
<body>
    <div class="app-wrapper">
        <div class="sidebar-overlay" id="sidebarOverlay" onclick="closeSidebar()"></div>
        <aside class="sidebar" id="sidebar">
            <div class="sidebar-header">
                <a href="/" class="logo">BEJSON<span>.</span></a>
                <button class="sidebar-close" onclick="closeSidebar()">&times;</button>
            </div>
            <nav class="sidebar-nav">
                {% for section_id, section in nav_sections.items() %}
                <div class="nav-section">
                    {% if section.children %}
                    <a class="nav-item {% if active_section == section_id %}active{% endif %}" onclick="toggleNavSection(\'{{ section_id }}\')">
                        <span class="icon">{{ section.icon }}</span>
                        <span>{{ section.label }}</span>
                        <span class="nav-toggle {% if active_section == section_id %}expanded{% endif %}" id="toggle-{{ section_id }}">&#9654;</span>
                    </a>
                    <div class="nav-children {% if active_section == section_id %}expanded{% endif %}" id="children-{{ section_id }}">
                        {% for child in section.children %}
                        <a href="{{ child.href }}" class="nav-item nav-child {% if request.path == child.href %}active{% endif %}">
                            <span class="icon">{{ child.icon }}</span>
                            <span>{{ child.label }}</span>
                        </a>
                        {% endfor %}
                    </div>
                    {% else %}
                    <a href="{{ section.href }}" class="nav-item {% if request.path == section.href or (section_id != \'dashboard\' and section.href in request.path) %}active{% endif %}">
                        <span class="icon">{{ section.icon }}</span>
                        <span>{{ section.label }}</span>
                    </a>
                    {% endif %}
                </div>
                {% endfor %}
            </nav>
            <div class="sidebar-footer">
                <div>BEJSON Manager</div>
                <div>Ready</div>
            </div>
        </aside>
        <div class="main-wrapper">
            <header class="top-header">
                <div class="header-left">
                    <button class="menu-toggle" onclick="openSidebar()">&#9776;</button>
                    <nav class="breadcrumbs">
                        <a href="/">Home</a>
                        {% for crumb in breadcrumbs %}
                        <span class="separator">/</span>
                        {% if crumb.href %}
                        <a href="{{ crumb.href }}">{{ crumb.label }}</a>
                        {% else %}
                        <span class="current">{{ crumb.label }}</span>
                        {% endif %}
                        {% endfor %}
                    </nav>
                </div>
                <div class="header-right"></div>
            </header>
            <main class="content-area">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                {% block content %}{% endblock %}
            </main>
            <div class="status-bar">
                <span>BEJSON Web Manager</span>
                <span>Ready</span>
            </div>
        </div>
    </div>
    <script>
        function openSidebar() {
            document.getElementById(\'sidebar\').classList.add(\'open\');
            document.getElementById(\'sidebarOverlay\').classList.add(\'active\');
            document.body.style.overflow = \'hidden\';
        }
        function closeSidebar() {
            document.getElementById(\'sidebar\').classList.remove(\'open\');
            document.getElementById(\'sidebarOverlay\').classList.remove(\'active\');
            document.body.style.overflow = \'\';
        }
        function toggleNavSection(sectionId) {
            const children = document.getElementById(\'children-\' + sectionId);
            const toggle = document.getElementById(\'toggle-\' + sectionId);
            if (children.classList.contains(\'expanded\')) {
                children.classList.remove(\'expanded\');
                toggle.classList.remove(\'expanded\');
            } else {
                children.classList.add(\'expanded\');
                toggle.classList.add(\'expanded\');
            }
        }
        document.querySelectorAll(\'.tab\').forEach(tab => {
            tab.addEventListener(\'click\', () => {
                const target = tab.dataset.tab;
                document.querySelectorAll(\'.tab\').forEach(t => t.classList.remove(\'active\'));
                document.querySelectorAll(\'.tab-content\').forEach(c => c.classList.remove(\'active\'));
                tab.classList.add(\'active\');
                document.getElementById(target).classList.add(\'active\');
            });
        });
        function openModal(id) { document.getElementById(id).classList.add(\'active\'); }
        function closeModal(id) { document.getElementById(id).classList.remove(\'active\'); }
        function insertTag(tag) {
            const editor = document.getElementById(\'html-editor\');
            if (!editor) return;
            const start = editor.selectionStart;
            const end = editor.selectionEnd;
            const selected = editor.value.substring(start, end);
            const before = editor.value.substring(0, start);
            const after = editor.value.substring(end);
            let insert = \'\';
            if (tag === \'br\') insert = \'<br>\\n\';
            else if (tag === \'p\') insert = \'<p>\' + (selected || \'Paragraph text\') + \'</p>\';
            else if (tag === \'h2\') insert = \'<h2>\' + (selected || \'Heading\') + \'</h2>\';
            else if (tag === \'h3\') insert = \'<h3>\' + (selected || \'Subheading\') + \'</h3>\';
            else if (tag === \'b\') insert = selected ? \'<strong>\' + selected + \'</strong>\' : \'<strong>Bold text</strong>\';
            else if (tag === \'a\') insert = \'<a href="#">\' + (selected || \'Link text\') + \'</a>\';
            else if (tag === \'img\') insert = \'<img src="../../../assets/image.jpg" alt="Image" style="max-width:100%;">\';
            editor.value = before + insert + after;
            editor.focus();
        }
        function insertImage(filename) {
            const editor = document.getElementById(\'html-editor\');
            if (!editor) return;
            const tag = \'<img src="../../../assets/\' + filename + \'" alt="\' + filename + \'" style="max-width:100%; border-radius:8px; margin: 20px 0;">\';
            const pos = editor.selectionStart;
            editor.value = editor.value.substring(0, pos) + \'\\n\' + tag + \'\\n\' + editor.value.substring(pos);
            editor.selectionStart = editor.selectionEnd = pos + tag.length + 2;
            editor.focus();
            closeModal(\'asset-modal\');
        }
        function pdfShowTabCC(which) {
            const libTab = document.getElementById(\'pdfTabLibraryCC\'), urlTab = document.getElementById(\'pdfTabUrlCC\');
            const libPane = document.getElementById(\'pdfPaneLibraryCC\'), urlPane = document.getElementById(\'pdfPaneUrlCC\');
            if (!libTab || !urlTab) return;
            if (which === \'library\') {
                libTab.classList.add(\'active\'); urlTab.classList.remove(\'active\');
                libTab.style.borderBottomColor = \'var(--accent)\'; libTab.style.color = \'var(--text)\';
                urlTab.style.borderBottomColor = \'transparent\'; urlTab.style.color = \'var(--text-secondary)\';
                libPane.style.display = \'block\'; urlPane.style.display = \'none\';
            } else {
                urlTab.classList.add(\'active\'); libTab.classList.remove(\'active\');
                urlTab.style.borderBottomColor = \'var(--accent)\'; urlTab.style.color = \'var(--text)\';
                libTab.style.borderBottomColor = \'transparent\'; libTab.style.color = \'var(--text-secondary)\';
                urlPane.style.display = \'block\'; libPane.style.display = \'none\';
            }
        }
        // Shared by every "Insert PDF" picker (Content editor, PageEditor V1/V2 use
        // their own local copies of this same bej-pdf-wrap markup) -- keep the
        // embed HTML identical across all three so a PDF looks/behaves the same
        // regardless of which editor inserted it.
        function escapeHtml(str) {
            const div = document.createElement(\'div\');
            div.textContent = str == null ? \'\' : String(str);
            return div.innerHTML;
        }
        function insertPdf(src, label) {
            const editor = document.getElementById(\'html-editor\');
            if (!editor) return;
            const safeSrc = escapeHtml(src);
            const tag = \'\\n<div class="bej-pdf-wrap" style="width:100%;margin:30px 0;border:1px solid #e5e5e5;border-radius:4px;overflow:hidden;">\\n  <object data="\' + safeSrc + \'" type="application/pdf" style="width:100%;height:820px;display:block;">\\n    <div style="padding:40px;text-align:center;background:#f8f8f8;">\\n      <p style="font-size:1.1rem;margin-bottom:16px;">Your browser cannot display this PDF inline.</p>\\n      <a href="\' + safeSrc + \'" download style="display:inline-block;padding:12px 28px;background:#DE2626;color:#fff;font-weight:700;text-decoration:none;border-radius:4px;">&#11015; Download PDF</a>\\n    </div>\\n  </object>\\n</div>\\n\';
            const pos = editor.selectionStart;
            editor.value = editor.value.substring(0, pos) + tag + editor.value.substring(pos);
            editor.selectionStart = editor.selectionEnd = pos + tag.length;
            editor.focus();
            closeModal(\'pdf-insert-modal\');
        }
        function insertPdfFromUrlCC() {
            const input = document.getElementById(\'pdfExternalUrlCC\');
            const url = input.value.trim();
            if (!url) { alert(\'Enter a PDF URL first.\'); return; }
            insertPdf(url, url);
            input.value = \'\';
        }
        function ytShowTabCC(which) {
            const libTab = document.getElementById(\'ytTabLibraryCC\'), urlTab = document.getElementById(\'ytTabUrlCC\');
            const libPane = document.getElementById(\'ytPaneLibraryCC\'), urlPane = document.getElementById(\'ytPaneUrlCC\');
            if (!libTab || !urlTab) return;
            if (which === \'library\') {
                libTab.classList.add(\'active\'); urlTab.classList.remove(\'active\');
                libTab.style.borderBottomColor = \'var(--accent)\'; libTab.style.color = \'var(--text)\';
                urlTab.style.borderBottomColor = \'transparent\'; urlTab.style.color = \'var(--text-secondary)\';
                libPane.style.display = \'block\'; urlPane.style.display = \'none\';
            } else {
                urlTab.classList.add(\'active\'); libTab.classList.remove(\'active\');
                urlTab.style.borderBottomColor = \'var(--accent)\'; urlTab.style.color = \'var(--text)\';
                libTab.style.borderBottomColor = \'transparent\'; libTab.style.color = \'var(--text-secondary)\';
                urlPane.style.display = \'block\'; libPane.style.display = \'none\';
            }
        }
        function ytIdFromUrlCC(raw) {
            raw = raw.trim();
            if (/^[A-Za-z0-9_-]{11}$/.test(raw)) return raw;
            const m = raw.match(/(?:v=|youtu\\.be\\/|embed\\/)([A-Za-z0-9_-]{11})/);
            return m ? m[1] : null;
        }
        // Shared by every "Insert YouTube" picker -- keep the embed HTML
        // identical everywhere (same bej-video-wrap markup used by PageEditor
        // V1/V2's own local copies of this function).
        function insertYt(raw, label) {
            const editor = document.getElementById(\'html-editor\');
            if (!editor) return;
            const vid = ytIdFromUrlCC(raw);
            if (!vid) { alert(\'Could not extract a YouTube video ID from that URL. Try pasting the full watch URL or just the 11-character ID.\'); return; }
            const safeLabel = escapeHtml(label || \'YouTube Video\');
            const tag = \'\\n<div class="bej-video-wrap" style="max-width:800px;margin:40px auto;">\\n  <div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;border-radius:8px;border:1px solid #333;background:#000;">\\n    <iframe src="https://www.youtube.com/embed/\' + vid + \'" title="\' + safeLabel + \'" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen style="position:absolute;top:0;left:0;width:100%;height:100%;"></iframe>\\n  </div>\\n</div>\\n\';
            const pos = editor.selectionStart;
            editor.value = editor.value.substring(0, pos) + tag + editor.value.substring(pos);
            editor.selectionStart = editor.selectionEnd = pos + tag.length;
            editor.focus();
            closeModal(\'yt-insert-modal\');
        }
        function insertYtFromUrlCC() {
            const input = document.getElementById(\'ytExternalUrlCC\');
            const url = input.value.trim();
            if (!url) { alert(\'Enter a YouTube URL or ID first.\'); return; }
            insertYt(url, url);
            input.value = \'\';
        }
        // Delegated click handler for the PDF/YouTube "Insert" picker grids
        // (Content.py's pdf-insert-modal/yt-insert-modal) -- data-* read via
        // .dataset instead of building onclick="insertX(\'...\')" from raw
        // interpolated values, same fix class as pkg123/pkg124.
        document.body.addEventListener(\'click\', function(ev) {
            var t = ev.target.closest(\'.picker-insert-item\');
            if (!t) return;
            if (t.dataset.action === \'pdf\') {
                insertPdf(t.dataset.url, t.dataset.label);
            } else if (t.dataset.action === \'yt\') {
                insertYt(t.dataset.url, t.dataset.label);
            }
        });
        function filterTable(input, tableId) {
            const filter = input.value.toLowerCase();
            const table = document.getElementById(tableId);
            if (!table) return;
            const rows = table.getElementsByTagName(\'tr\');
            for (let i = 1; i < rows.length; i++) {
                const text = rows[i].textContent.toLowerCase();
                rows[i].style.display = text.includes(filter) ? \'\' : \'none\';
            }
        }
        window.addEventListener(\'resize\', () => { if (window.innerWidth > 768) { closeSidebar(); } });
    </script>
</body>
</html>'''

# ─── Render helpers ─────────────────────────────────────────────────────────
def R(content, **kwargs):
    """Helper to render with base template."""
    return render_template_string(
        BASE_TEMPLATE.replace('{% block content %}{% endblock %}', content),
        nav_sections=NAV_SECTIONS,
        **kwargs
    )


def get_breadcrumbs(path):
    if path == '/':
        return [{'label': 'Dashboard', 'href': None}]
    path_parts = [p for p in path.split('/') if p]
    breadcrumb_map = {
        'pages': ('Content', '/content'),
        'content': ('Content', None),
        'links': ('External Links', None),
        'categories': ('Categories', None),
        'new': ('New', None),
        'edit': ('Edit', None),
        'apps': ('Applications', None),
        'site': ('Site Config', None),
        'nav': ('Navigation', None),
        'authors': ('Authors', None),
        'ads': ('Ads', None),
        'social': ('Social Links', None),
        'publish': ('Publish', None),
    }
    breadcrumbs = []
    for i, part in enumerate(path_parts):
        label, Breadcrumb_Segment_Href = breadcrumb_map.get(part, (part.capitalize(), None))
        if Breadcrumb_Segment_Href is None and i < len(path_parts) - 1:
            Breadcrumb_Segment_Href = '/' + '/'.join(path_parts[:i+1])
        elif i == len(path_parts) - 1:
            Breadcrumb_Segment_Href = None
        breadcrumbs.append({'label': label, 'href': Breadcrumb_Segment_Href})
    return breadcrumbs


def get_image_assets():
    """Replaces get_assets() for picker UIs. get_assets() lists whatever
    files are physically sitting in ASSETS_DIR -- so an orphaned file left
    on disk (failed upload, manual copy, restored backup, anything not
    cleanly deleted through the real Delete button) stays visible in every
    picker forever, in a pool that doesn't shrink even after Delete or
    Factory Reset touch the database. This reads the same MediaAsset MFDB
    table the Media Library page and edit_content()'s picker already use
    (pkg68 fix), filtered to image MIME types, so every picker shows only
    what the database says exists. Returns a flat list of filenames,
    matching get_assets()'s return shape exactly, since existing templates
    render each entry directly as both the <option> value and label."""
    db.mount()
    assets = db.get_records("MediaAsset")
    assets.sort(key=lambda a: a.get('asset_uploaded_at') or '', reverse=True)
    return [a['asset_filename'] for a in assets if (a.get('asset_mime_type') or '').startswith('image/')]


_LEGACY_WEB_FILES = [
    "Flask_CMS.py", "Flask_CMS_Publisher.py", "Flask_Page_Editor.py",
    "Flask_Profile_Manager.py", "Page_Editor_v2.py",
]

def warn_about_legacy_files():
    # These are the pre-Blueprint-split monolith and its siblings, renamed
    # away to BEJSON_CMS_Admin.py/Publisher.py/PageEditor.py/PageEditorV2.py/
    # ProfileManager.py. Extracting a new package ZIP on top of an existing
    # project folder (rather than into a clean/empty one) does not delete
    # files absent from the new archive -- so these can silently reappear.
    # If any of them ever actually gets launched instead of its replacement,
    # you end up running old, unmaintained code (missing every security/bug
    # fix made since) side by side with the current app, both pointed at
    # the exact same on-disk data -- which produces exactly the kind of
    # "two different systems, factory reset doesn't clean up right"
    # confusion this check exists to catch early. Called from every app's
    # own __main__ block, not just this one, since any of the 5 could be
    # the one that accidentally gets launched.
    web_dir = os.path.dirname(os.path.abspath(__file__))
    found = [f for f in _LEGACY_WEB_FILES if os.path.exists(os.path.join(web_dir, f))]
    if found:
        print(f'''
    !! WARNING: Found old pre-rename file(s) still present: {", ".join(found)}
    !! These are leftovers from before the Blueprint split and should not
    !! exist any more -- they were replaced by BEJSON_CMS_Admin.py,
    !! BEJSON_CMS_Publisher.py, BEJSON_CMS_PageEditor.py,
    !! BEJSON_CMS_PageEditorV2.py, and BEJSON_CMS_ProfileManager.py.
    !! If any of these old files ever gets run instead of its replacement,
    !! you will get old, unfixed behavior (this exact scenario has already
    !! caused real bugs). Delete them: they are not needed for anything.
        ''')

