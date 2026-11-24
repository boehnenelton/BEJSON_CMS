#!/usr/bin/env python3
"""
Name:           BEJSON_CMS_APIPublisher.py
Family:         CMS
Description:    Independent API Publisher and Syndication Tracking Service for BEJSON_CMS.
                Reads CMS MFDB database pages, Google Blogger API posts, and Substack API
                posts/drafts. Provides baseline cross-platform URL tracking, group key
                lineage, and deduplication foundations.
Version:        1.0.0
Date Created:   2026-11-24
Author Credit:  Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
RELATIONAL_ID:  7d8e9f01-2345-4a67-89bc-def012345678
License:        PolyForm-Noncommercial-1.0.0
"""

import argparse
import base64
import html as _html_mod
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Self-locating path resolution
SCRIPT_PATH = Path(__file__).resolve()
WEB_DIR = SCRIPT_PATH.parent
CMS_ROOT = WEB_DIR.parent.parent
LIB_DIR = CMS_ROOT / "src" / "lib"

for path_entry in (str(WEB_DIR), str(LIB_DIR)):
    if path_entry not in sys.path:
        sys.path.insert(0, path_entry)

from lib_bejson_CMS_cms_core import CMSCore
import lib_bejson_CMS_cms_ports as CMSPorts
from BEJSON_CMS_Shared import register_auth_guard

from flask import Flask, jsonify, redirect, render_template_string, request

# Canonical paths
DEFINITIONS_FILE = Path("/storage/emulated/0/.env/user/definitions.json")
SECURE_ENV_FILE = Path("/storage/emulated/0/.env/secure/secureenv_file.json")
TOKEN_STORAGE_PATH = Path(os.path.expanduser("~/.env/blogger_token.json"))
CONFIG_PATH = CMS_ROOT / "config.json"
MANIFEST_PATH = CMS_ROOT / "storage" / "mfdb" / "site_master" / "104a.mfdb.bejson"
PAGES_INDEX = CMS_ROOT / "storage" / "mfdb" / "site_master" / "data" / "pagerecord.bejson"
PAGES_DB_DIR = CMS_ROOT / "storage" / "mfdb" / "pages_db"


def resolve_api_publisher_port() -> int:
    """Resolves service port: CMS_APIPUBLISHER_PORT env > config.json > 5005 default."""
    env_port = os.environ.get("CMS_APIPUBLISHER_PORT")
    if env_port and env_port.isdigit():
        return int(env_port)
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as file_handle:
                cfg_doc = json.load(file_handle)
            for row in cfg_doc.get("Values", []):
                if len(row) >= 2 and row[0] == "apipublisher_port":
                    return int(row[1])
        except Exception:
            pass
    return 5005


API_PUBLISHER_PORT = resolve_api_publisher_port()


def resolve_secure_secret(var_name: str, default: str = "") -> str:
    """Resolves secret variable from os.environ, secureenv_file.json, or definitions.json."""
    runtime_val = os.environ.get(var_name)
    if runtime_val:
        return runtime_val.strip()

    if SECURE_ENV_FILE.exists():
        try:
            with open(SECURE_ENV_FILE, "r", encoding="utf-8") as file_handle:
                sec_doc = json.load(file_handle)
            fields = [field_entry["name"] for field_entry in sec_doc.get("Fields", [])]
            if "var_name" in fields and "var_value" in fields:
                name_idx = fields.index("var_name")
                val_idx = fields.index("var_value")
                for row in sec_doc.get("Values", []):
                    if len(row) > max(name_idx, val_idx) and row[name_idx] == var_name:
                        return (row[val_idx] or "").strip()
        except Exception:
            pass

    if DEFINITIONS_FILE.exists():
        try:
            with open(DEFINITIONS_FILE, "r", encoding="utf-8") as file_handle:
                def_doc = json.load(file_handle)
            if var_name in def_doc:
                return str(def_doc[var_name]).strip()
        except Exception:
            pass

    return default


def get_blogger_config() -> Dict[str, str]:
    """Retrieves Google Blogger syndication configuration from environment / secureenv."""
    return {
        "blog_id": resolve_secure_secret("BLOGGER_BLOG_ID"),
        "client_id": resolve_secure_secret("BLOGGER_CLIENT_ID"),
        "client_secret": resolve_secure_secret("BLOGGER_CLIENT_SECRET"),
        "refresh_token": resolve_secure_secret("BLOGGER_REFRESH_TOKEN"),
        "api_key": resolve_secure_secret("BLOGGER_API_KEY"),
    }


def get_substack_config() -> Dict[str, str]:
    """Retrieves Substack syndication configuration from environment / secureenv."""
    subdomain = resolve_secure_secret("SUBSTACK_SUBDOMAIN")
    base_url = resolve_secure_secret("SUBSTACK_URL")
    if not base_url and subdomain:
        base_url = f"https://{subdomain}.substack.com"
    return {
        "session_sid": resolve_secure_secret("SUBSTACK_SID"),
        "subdomain": subdomain,
        "base_url": base_url,
        "user_id": resolve_secure_secret("SUBSTACK_USER_ID"),
        "user_handle": resolve_secure_secret("SUBSTACK_USER_HANDLE"),
    }


def normalize_group_key(text_content: str) -> str:
    """Normalizes titles and slugs into deterministic alphanumeric hyphenated group keys."""
    if not text_content:
        return ""
    cleaned = text_content.lower().strip()
    cleaned = re.sub(r"[^\w\s-]", "", cleaned)
    cleaned = re.sub(r"[\s_-]+", "-", cleaned).strip("-")
    return cleaned


# ==============================================================================
# BASELINE READERS
# ==============================================================================

def read_cms_posts(db_instance: Optional[CMSCore] = None) -> List[Dict[str, Any]]:
    """Reads all PageRecord rows from the CMS database and maps tracking fields."""
    target_db = db_instance
    if target_db is None:
        if MANIFEST_PATH.exists():
            target_db = CMSCore(str(MANIFEST_PATH))
        else:
            return []

    records = target_db.get_records("PageRecord")
    cms_posts = []
    for record in records:
        page_uuid = record.get("page_uuid", "")
        page_title = record.get("page_title", "")
        page_slug = record.get("page_slug", "")
        page_type = record.get("page_type", "article")
        page_category = record.get("page_cat_name", "")
        created_at = record.get("created_at", "")
        meta_description = record.get("page_meta_desc", "")

        content_path = PAGES_DB_DIR / f"{page_uuid}.json"
        has_content = content_path.exists()

        group_key = normalize_group_key(page_slug or page_title)
        canonical_path = f"/articles/{page_slug}.html" if page_type == "article" else f"/{page_slug}.html"

        cms_posts.append({
            "cms_uuid": page_uuid,
            "title": page_title,
            "slug": page_slug,
            "page_type": page_type,
            "category": page_category,
            "created_at": created_at,
            "description": meta_description,
            "has_content": has_content,
            "group_key": group_key,
            "canonical_path": canonical_path,
            "platform": "cms",
        })
    return cms_posts


def get_blogger_authorized_token(blogger_cfg: Dict[str, str]) -> Optional[str]:
    """Retrieves or refreshes Google Blogger OAuth 2.0 access token without browser popup."""
    client_id = blogger_cfg.get("client_id", "")
    client_secret = blogger_cfg.get("client_secret", "")
    refresh_token = blogger_cfg.get("refresh_token", "")

    # 1. Check local token storage
    if TOKEN_STORAGE_PATH.exists():
        try:
            with open(TOKEN_STORAGE_PATH, "r", encoding="utf-8") as file_handle:
                token_data = json.load(file_handle)
            stored_refresh = token_data.get("refresh_token") or refresh_token
            if stored_refresh and client_id and client_secret:
                token_url = "https://oauth2.googleapis.com/token"
                payload = urllib.parse.urlencode({
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": stored_refresh,
                    "grant_type": "refresh_token",
                }).encode("utf-8")
                req = urllib.request.Request(token_url, data=payload, method="POST")
                req.add_header("Content-Type", "application/x-www-form-urlencoded")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    new_token = resp_data.get("access_token")
                    if new_token:
                        token_data["access_token"] = new_token
                        with open(TOKEN_STORAGE_PATH, "w", encoding="utf-8") as file_writer:
                            json.dump(token_data, file_writer, indent=2)
                        return new_token
            if token_data.get("access_token"):
                return token_data["access_token"]
        except Exception:
            pass

    # 2. Direct refresh using secureenv credentials
    if client_id and client_secret and refresh_token:
        try:
            token_url = "https://oauth2.googleapis.com/token"
            payload = urllib.parse.urlencode({
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }).encode("utf-8")
            req = urllib.request.Request(token_url, data=payload, method="POST")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                new_token = resp_data.get("access_token")
                if new_token:
                    TOKEN_STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
                    with open(TOKEN_STORAGE_PATH, "w", encoding="utf-8") as file_writer:
                        json.dump(resp_data, file_writer, indent=2)
                    return new_token
        except Exception:
            pass

    return None


def read_blogger_posts(blogger_cfg: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """Fetches existing post list from Google Blogger v3 API."""
    cfg = blogger_cfg or get_blogger_config()
    blog_id = cfg.get("blog_id")
    if not blog_id:
        return []

    token = get_blogger_authorized_token(cfg)
    api_key = cfg.get("api_key")

    posts = []
    # Try Bearer token authorization first
    if token:
        url = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts?maxResults=50"
        try:
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("items", []):
                    title = item.get("title", "").strip()
                    posts.append({
                        "blogger_id": str(item.get("id", "")),
                        "title": title,
                        "url": item.get("url", ""),
                        "published": item.get("published", ""),
                        "updated": item.get("updated", ""),
                        "labels": item.get("labels", []),
                        "status": item.get("status", "LIVE"),
                        "group_key": normalize_group_key(title),
                        "platform": "blogger",
                    })
                return posts
        except Exception:
            pass

    # Fallback to API Key if token was unavailable
    if api_key:
        url = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts?key={api_key}&maxResults=50"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("items", []):
                    title = item.get("title", "").strip()
                    posts.append({
                        "blogger_id": str(item.get("id", "")),
                        "title": title,
                        "url": item.get("url", ""),
                        "published": item.get("published", ""),
                        "updated": item.get("updated", ""),
                        "labels": item.get("labels", []),
                        "status": item.get("status", "LIVE"),
                        "group_key": normalize_group_key(title),
                        "platform": "blogger",
                    })
                return posts
        except Exception:
            pass

    return posts


def read_substack_posts(substack_cfg: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """Fetches published posts and drafts from Substack API via session token auth."""
    cfg = substack_cfg or get_substack_config()
    session_sid = cfg.get("session_sid")
    base_url = cfg.get("base_url")
    if not base_url or not session_sid:
        return []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"
        ),
        "Cookie": f"substack.sid={session_sid}; connect.sid={session_sid}",
        "Accept": "application/json",
    }

    posts = []
    seen_ids: Set[str] = set()

    # 1. Fetch published posts
    try:
        posts_url = f"{base_url}/api/v1/posts?limit=50"
        req = urllib.request.Request(posts_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("posts", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            for item in items:
                post_id = str(item.get("id", ""))
                title = item.get("title", "").strip()
                slug = item.get("slug", "")
                post_url = item.get("canonical_url") or f"{base_url}/p/{slug}"
                if post_id and post_id not in seen_ids:
                    seen_ids.add(post_id)
                    posts.append({
                        "substack_id": post_id,
                        "title": title,
                        "slug": slug,
                        "url": post_url,
                        "published_at": item.get("post_date", ""),
                        "status": "published",
                        "group_key": normalize_group_key(title),
                        "platform": "substack",
                    })
    except Exception:
        pass

    # 2. Fetch drafts
    try:
        drafts_url = f"{base_url}/api/v1/drafts?filter=draft"
        req = urllib.request.Request(drafts_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("posts", []) if isinstance(data, dict) else (data if isinstance(data, list) else data.get("drafts", []))
            for item in items:
                draft_id = str(item.get("id", ""))
                title = (item.get("draft_title") or item.get("title") or "").strip()
                slug = item.get("slug", "")
                draft_url = f"{base_url}/p/{draft_id}" if draft_id else ""
                if draft_id and draft_id not in seen_ids:
                    seen_ids.add(draft_id)
                    posts.append({
                        "substack_id": draft_id,
                        "title": title,
                        "slug": slug,
                        "url": draft_url,
                        "published_at": item.get("updated_at", ""),
                        "status": "draft",
                        "group_key": normalize_group_key(title),
                        "platform": "substack",
                    })
    except Exception:
        pass

    return posts


def correlate_lineage(
    cms_posts: List[Dict[str, Any]],
    blogger_posts: List[Dict[str, Any]],
    substack_posts: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Correlates records across CMS, Blogger, and Substack by group_key and title."""
    lineage_map: Dict[str, Dict[str, Any]] = {}
    alias_to_primary: Dict[str, str] = {}

    for cms_item in cms_posts:
        title_key = normalize_group_key(cms_item["title"])
        slug_key = normalize_group_key(cms_item["slug"])
        primary_key = title_key or slug_key
        if not primary_key:
            continue

        alias_to_primary[primary_key] = primary_key
        if slug_key:
            alias_to_primary[slug_key] = primary_key

        lineage_map[primary_key] = {
            "group_key": primary_key,
            "title": cms_item["title"],
            "cms": cms_item,
            "blogger": None,
            "substack": None,
            "syndicated_to": ["cms"],
        }

    def _find_matching_key(candidate_keys: List[str]) -> Optional[str]:
        for cand in candidate_keys:
            if not cand:
                continue
            if cand in alias_to_primary:
                return alias_to_primary[cand]
            for registered_key in lineage_map.keys():
                if cand == registered_key or cand in registered_key or registered_key in cand:
                    return registered_key
        return None

    for blogger_item in blogger_posts:
        title_key = normalize_group_key(blogger_item["title"])
        matched_key = _find_matching_key([title_key])

        if matched_key:
            lineage_map[matched_key]["blogger"] = blogger_item
            if "blogger" not in lineage_map[matched_key]["syndicated_to"]:
                lineage_map[matched_key]["syndicated_to"].append("blogger")
        else:
            lineage_map[title_key] = {
                "group_key": title_key,
                "title": blogger_item["title"],
                "cms": None,
                "blogger": blogger_item,
                "substack": None,
                "syndicated_to": ["blogger"],
            }
            alias_to_primary[title_key] = title_key

    for substack_item in substack_posts:
        title_key = normalize_group_key(substack_item["title"])
        slug_key = normalize_group_key(substack_item.get("slug", ""))
        matched_key = _find_matching_key([title_key, slug_key])

        if matched_key:
            lineage_map[matched_key]["substack"] = substack_item
            if "substack" not in lineage_map[matched_key]["syndicated_to"]:
                lineage_map[matched_key]["syndicated_to"].append("substack")
        else:
            lineage_map[title_key] = {
                "group_key": title_key,
                "title": substack_item["title"],
                "cms": None,
                "blogger": None,
                "substack": substack_item,
                "syndicated_to": ["substack"],
            }
            alias_to_primary[title_key] = title_key

    return sorted(list(lineage_map.values()), key=lambda entry: entry["title"].lower())


# ==============================================================================
# FLASK WEB APP
# ==============================================================================

app = Flask(__name__)
register_auth_guard(app)

_state_cache: Dict[str, Any] = {
    "cms_posts": [],
    "blogger_posts": [],
    "substack_posts": [],
    "lineage": [],
    "last_refresh": None,
}


def refresh_all_sources(db_instance: Optional[CMSCore] = None):
    """Executes fresh reads of CMS DB, Blogger API, and Substack API."""
    cms_posts = read_cms_posts(db_instance)
    blogger_posts = read_blogger_posts()
    substack_posts = read_substack_posts()
    lineage = correlate_lineage(cms_posts, blogger_posts, substack_posts)

    _state_cache["cms_posts"] = cms_posts
    _state_cache["blogger_posts"] = blogger_posts
    _state_cache["substack_posts"] = substack_posts
    _state_cache["lineage"] = lineage
    _state_cache["last_refresh"] = Path(__file__).stat().st_mtime
    return _state_cache


HTML_DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>API Publisher - BEJSON_CMS</title>
  <style>
    :root {
      --bg-body: #000000;
      --bg-card: #0a0a0a;
      --border: #222222;
      --primary: #DE2626;
      --text: #ffffff;
      --muted: #888888;
      --green: #22c55e;
      --yellow: #eab308;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 16px;
      background: var(--bg-body);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-size: 14px;
      line-height: 1.5;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 20px;
      flex-wrap: wrap;
      gap: 10px;
    }
    .header h1 {
      margin: 0;
      font-size: 1.25rem;
      font-weight: 700;
      color: #fff;
    }
    .badge {
      display: inline-block;
      padding: 3px 8px;
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      border-radius: 4px;
      letter-spacing: 0.5px;
    }
    .badge-on { background: #14532d; color: #4ade80; }
    .badge-off { background: #3f3f46; color: #a1a1aa; }
    .badge-red { background: #7f1d1d; color: #fca5a5; }
    .badge-yellow { background: #713f12; color: #fde047; }
    .btn {
      display: inline-block;
      padding: 6px 14px;
      font-size: 0.8rem;
      font-weight: 600;
      border: 1px solid var(--border);
      border-radius: 4px;
      background: #18181b;
      color: #fff;
      cursor: pointer;
      text-decoration: none;
    }
    .btn:hover { background: #27272a; }
    .btn-red { background: var(--primary); border-color: var(--primary); }
    .btn-red:hover { background: #b91c1c; }
    .grid3 {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 16px;
    }
    .card-hd {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 10px;
    }
    .card-hd h3 {
      margin: 0;
      font-size: 0.95rem;
      font-weight: 700;
    }
    .stat-number {
      font-size: 2rem;
      font-weight: 800;
      margin: 4px 0 8px 0;
      color: #ffffff;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.8rem;
      text-align: left;
    }
    th, td {
      padding: 8px 10px;
      border-bottom: 1px solid var(--border);
    }
    th {
      background: #111;
      color: var(--muted);
      font-weight: 600;
      text-transform: uppercase;
      font-size: 0.7rem;
    }
    tr:hover { background: #141414; }
    code {
      font-family: monospace;
      color: #ff8080;
      font-size: 0.78rem;
      word-break: break-all;
    }
    a { color: #60a5fa; text-decoration: none; }
    a:hover { text-decoration: underline; }
    @media (max-width: 600px) {
      body { padding: 10px; }
      .grid3 { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1>API Publisher &bull; Syndication &amp; Lineage</h1>
      <div style="font-size:0.75rem;color:var(--muted);margin-top:2px;">
        Zero-duplicate tracking for CMS, Blogger, and Substack
      </div>
    </div>
    <div style="display:flex;gap:8px;align-items:center;">
      <form method="POST" action="/refresh" style="margin:0;">
        <button class="btn btn-red">&#8635; Refresh Data</button>
      </form>
      <a href="http://localhost:5001" class="btn" target="_blank">&larr; Admin</a>
    </div>
  </div>

  <div class="grid3">
    <!-- CMS DATABASE -->
    <div class="card">
      <div class="card-hd">
        <h3>CMS Database</h3>
        <span class="badge badge-on">Local MFDB</span>
      </div>
      <div class="stat-number">{{ cms_posts|length }}</div>
      <p style="color:var(--muted);font-size:0.76rem;margin:0;">
        PageRecord entities registered in <code>storage/mfdb/site_master/</code>.
      </p>
    </div>

    <!-- GOOGLE BLOGGER -->
    <div class="card">
      <div class="card-hd">
        <h3>Google Blogger</h3>
        {% if blogger_connected %}
          <span class="badge badge-on">&#10003; Connected</span>
        {% else %}
          <span class="badge badge-off">Unconfigured</span>
        {% endif %}
      </div>
      <div class="stat-number">{{ blogger_posts|length }}</div>
      <p style="color:var(--muted);font-size:0.76rem;margin:0;">
        Blog ID: <code>{{ blogger_blog_id or 'ENV:BLOGGER_BLOG_ID' }}</code>
      </p>
    </div>

    <!-- SUBSTACK -->
    <div class="card">
      <div class="card-hd">
        <h3>Substack</h3>
        {% if substack_connected %}
          <span class="badge badge-on">&#10003; Connected</span>
        {% else %}
          <span class="badge badge-off">Unconfigured</span>
        {% endif %}
      </div>
      <div class="stat-number">{{ substack_posts|length }}</div>
      <p style="color:var(--muted);font-size:0.76rem;margin:0;">
        Target: <code>{{ substack_subdomain or 'ENV:SUBSTACK_SUBDOMAIN' }}</code>
      </p>
    </div>
  </div>

  <!-- CROSS PLATFORM LINEAGE TABLE -->
  <div class="card" style="margin-bottom:24px;">
    <div class="card-hd">
      <h3>Cross-Platform Content Lineage</h3>
      <span class="badge badge-yellow">{{ lineage|length }} Traced Items</span>
    </div>
    <p style="color:var(--muted);font-size:0.78rem;margin-bottom:12px;">
      Correlates every article between the CMS database, Google Blogger, and Substack by deterministic group key to prevent duplicate syndication.
    </p>
    <div style="overflow-x:auto;">
      <table>
        <thead>
          <tr>
            <th>Title / Group Key</th>
            <th>CMS Page</th>
            <th>Google Blogger</th>
            <th>Substack</th>
            <th>Coverage</th>
          </tr>
        </thead>
        <tbody>
          {% for item in lineage %}
          <tr>
            <td>
              <strong>{{ item.title }}</strong><br>
              <code>{{ item.group_key }}</code>
            </td>
            <td>
              {% if item.cms %}
                <span class="badge badge-on">CMS Live</span><br>
                <code>{{ item.cms.cms_uuid[:8] }}...</code>
              {% else %}
                <span class="badge badge-off">Not on CMS</span>
              {% endif %}
            </td>
            <td>
              {% if item.blogger %}
                <span class="badge badge-on">{{ item.blogger.status }}</span><br>
                <a href="{{ item.blogger.url }}" target="_blank">View Post &rarr;</a>
              {% else %}
                <span class="badge badge-off">Missing</span>
              {% endif %}
            </td>
            <td>
              {% if item.substack %}
                <span class="badge {% if item.substack.status == 'published' %}badge-on{% else %}badge-yellow{% endif %}">{{ item.substack.status }}</span><br>
                {% if item.substack.url %}
                  <a href="{{ item.substack.url }}" target="_blank">View Substack &rarr;</a>
                {% else %}
                  <code>ID: {{ item.substack.substack_id }}</code>
                {% endif %}
              {% else %}
                <span class="badge badge-off">Missing</span>
              {% endif %}
            </td>
            <td>
              {% for plat in item.syndicated_to %}
                <span class="badge badge-on" style="margin-right:2px;">{{ plat }}</span>
              {% endfor %}
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""


@app.route("/", methods=["GET"])
@app.route("/api-publisher", methods=["GET"])
def r_dashboard():
    if not _state_cache.get("cms_posts"):
        refresh_all_sources()

    b_cfg = get_blogger_config()
    s_cfg = get_substack_config()

    blogger_connected = bool(b_cfg.get("blog_id") and (b_cfg.get("refresh_token") or b_cfg.get("client_id")))
    substack_connected = bool(s_cfg.get("session_sid") and (s_cfg.get("subdomain") or s_cfg.get("base_url")))

    return render_template_string(
        HTML_DASHBOARD_TEMPLATE,
        cms_posts=_state_cache.get("cms_posts", []),
        blogger_posts=_state_cache.get("blogger_posts", []),
        substack_posts=_state_cache.get("substack_posts", []),
        lineage=_state_cache.get("lineage", []),
        blogger_connected=blogger_connected,
        blogger_blog_id=b_cfg.get("blog_id", ""),
        substack_connected=substack_connected,
        substack_subdomain=s_cfg.get("subdomain", ""),
    )


@app.route("/refresh", methods=["POST", "GET"])
def r_refresh():
    refresh_all_sources()
    return redirect("/")


@app.route("/api/status", methods=["GET"])
def r_api_status():
    if not _state_cache.get("cms_posts"):
        refresh_all_sources()

    b_cfg = get_blogger_config()
    s_cfg = get_substack_config()

    return jsonify({
        "status": "online",
        "service": "BEJSON_CMS_APIPublisher",
        "port": API_PUBLISHER_PORT,
        "counts": {
            "cms_posts": len(_state_cache.get("cms_posts", [])),
            "blogger_posts": len(_state_cache.get("blogger_posts", [])),
            "substack_posts": len(_state_cache.get("substack_posts", [])),
            "lineage_items": len(_state_cache.get("lineage", [])),
        },
        "blogger_connected": bool(b_cfg.get("blog_id")),
        "substack_connected": bool(s_cfg.get("session_sid")),
    })


@app.route("/api/cms", methods=["GET"])
def r_api_cms():
    posts = read_cms_posts()
    return jsonify({"count": len(posts), "posts": posts})


@app.route("/api/blogger", methods=["GET"])
def r_api_blogger():
    posts = read_blogger_posts()
    return jsonify({"count": len(posts), "posts": posts})


@app.route("/api/substack", methods=["GET"])
def r_api_substack():
    posts = read_substack_posts()
    return jsonify({"count": len(posts), "posts": posts})


@app.route("/api/lineage", methods=["GET"])
def r_api_lineage():
    if not _state_cache.get("lineage"):
        refresh_all_sources()
    return jsonify({"count": len(_state_cache["lineage"]), "lineage": _state_cache["lineage"]})


# ==============================================================================
# CLI DISPATCH
# ==============================================================================

def print_terminal_status():
    """Prints 49-column mobile portrait terminal status banner per §3.5."""
    div49 = "=" * 49
    sub49 = "-" * 49

    cms_list = read_cms_posts()
    b_cfg = get_blogger_config()
    s_cfg = get_substack_config()
    blogger_list = read_blogger_posts(b_cfg)
    substack_list = read_substack_posts(s_cfg)
    lineage_list = correlate_lineage(cms_list, blogger_list, substack_list)

    print(div49)
    print(" BEJSON CMS API PUBLISHER STATUS")
    print(div49)
    print(f" CMS MFDB Database Pages : {len(cms_list)}")
    print(f" Google Blogger API Posts: {len(blogger_list)}")
    print(f" Substack API Posts/Draft: {len(substack_list)}")
    print(f" Correlated Lineage Items: {len(lineage_list)}")
    print(sub49)
    print(f" Blogger Auth Configured : {'YES' if b_cfg.get('blog_id') else 'NO'}")
    print(f" Substack Auth Configured: {'YES' if s_cfg.get('session_sid') else 'NO'}")
    print(f" Listening Web Port      : {API_PUBLISHER_PORT}")
    print(div49)


def main():
    parser = argparse.ArgumentParser(description="BEJSON_CMS API Publisher & Lineage Service")
    parser.add_argument("--status", action="store_true", help="Print terminal status report (49 columns)")
    parser.add_argument("--read-cms", action="store_true", help="Read and print CMS database posts")
    parser.add_argument("--read-blogger", action="store_true", help="Read and print Google Blogger posts")
    parser.add_argument("--read-substack", action="store_true", help="Read and print Substack posts/drafts")
    parser.add_argument("--lineage", action="store_true", help="Print correlated cross-platform lineage")
    parser.add_argument("--json", action="store_true", help="Format output as JSON")
    parser.add_argument("--server", action="store_true", help="Run independent Flask server")
    args = parser.parse_args()

    if args.status:
        print_terminal_status()
        return

    if args.read_cms:
        posts = read_cms_posts()
        if args.json:
            print(json.dumps(posts, indent=2))
        else:
            print(f"[*] CMS Database Posts ({len(posts)} records):")
            for p in posts:
                print(f" - [{p['cms_uuid'][:8]}] {p['title']} (slug: {p['slug']})")
        return

    if args.read_blogger:
        posts = read_blogger_posts()
        if args.json:
            print(json.dumps(posts, indent=2))
        else:
            print(f"[*] Google Blogger Posts ({len(posts)} records):")
            for p in posts:
                print(f" - [{p['blogger_id']}] {p['title']} -> {p['url']}")
        return

    if args.read_substack:
        posts = read_substack_posts()
        if args.json:
            print(json.dumps(posts, indent=2))
        else:
            print(f"[*] Substack Posts/Drafts ({len(posts)} records):")
            for p in posts:
                print(f" - [{p['status']}] {p['title']} -> {p['url']}")
        return

    if args.lineage:
        cms_list = read_cms_posts()
        blogger_list = read_blogger_posts()
        substack_list = read_substack_posts()
        lineage_list = correlate_lineage(cms_list, blogger_list, substack_list)
        if args.json:
            print(json.dumps(lineage_list, indent=2))
        else:
            print(f"[*] Cross-Platform Lineage ({len(lineage_list)} items):")
            for item in lineage_list:
                print(f" - {item['title']} (Key: {item['group_key']}) -> Syndicated: {', '.join(item['syndicated_to'])}")
        return

    # Default action: start independent Flask server
    print_terminal_status()
    print(f"[*] Starting independent API Publisher web service at http://0.0.0.0:{API_PUBLISHER_PORT}...")
    app.run(host="0.0.0.0", port=API_PUBLISHER_PORT, debug=False)


if __name__ == "__main__":
    main()
