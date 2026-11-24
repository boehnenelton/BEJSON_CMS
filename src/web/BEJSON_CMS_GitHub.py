# Technical Note: Dedicated GitHub Hub blueprint (/github), connectivity check, BEJSON 104a stats cache, and 1-click Repo-to-Project importer.
"""
Library:         BEJSON_CMS_GitHub
Family:          BEJSON_CMS
Description:     Manages GitHub integration toggles (SiteConfig), ephemeral/ENV token
                 resolution (zero secrets on disk), connectivity-aware cached repo stats,
                 and 1-click repository import into canonical BEJSON 104db Project Pages.
Version:         19.01
Date:            2026-11-24
RELATIONAL_ID:  80697ac7-78d0-4a14-ac00-23c818a88ea8
"""

import html as _html_mod
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from flask import Blueprint, flash, redirect, request

from BEJSON_CMS_Shared import (
    DEFAULT_FEATURED_IMAGE,
    MFDB_DIR,
    PAGES_DB_DIR,
    R,
    db as _shared_db,
)

def get_db():
    return _shared_db

github_cube = Blueprint("github_cube", __name__)

STATS_CACHE_PATH = os.path.join(MFDB_DIR, "data", "github_stats_cache.104a.bejson")

# Ephemeral in-memory session token only (never written to disk, configs, or logs)
_SESSION_GITHUB_TOKEN = ""
_CACHED_REPO_LIST = []


def get_github_settings(db=None) -> dict:
    """Reads non-secret GitHub integration settings and ENV pointer from SiteConfig (sys_key/sys_value)."""
    settings = {
        "github_username": "boehnenelton",
        "github_token_pointer": "ENV:GITHUB_TOKEN",
        "github_stats_enabled": "true",
        "github_post_strip_enabled": "true",
    }
    try:
        db_obj = db or get_db()
        for row in db_obj.get_records("SiteConfig") or []:
            k = row.get("sys_key") or row.get("config_key") or row.get("key") or ""
            v = row.get("sys_value") if "sys_value" in row else (row.get("config_value") if "config_value" in row else row.get("value"))
            if k in settings and v is not None and str(v).strip() != "":
                settings[k] = str(v).strip()
    except Exception:
        pass
    return settings


def save_github_settings(updates: dict, db=None) -> None:
    """Persists non-secret GitHub settings (never raw tokens) into SiteConfig (sys_key/sys_value)."""
    allowed = {"github_username", "github_token_pointer", "github_stats_enabled", "github_post_strip_enabled"}
    db_obj = db or get_db()
    existing = {
        (r.get("sys_key") or r.get("config_key") or r.get("key")): r
        for r in (db_obj.get_records("SiteConfig") or [])
    }
    for k, v in updates.items():
        if k not in allowed:
            continue
        val_str = str(v).strip()
        if k in existing:
            key_col = "sys_key" if "sys_key" in existing[k] else ("config_key" if "config_key" in existing[k] else "key")
            val_col = "sys_value" if "sys_value" in existing[k] else ("config_value" if "config_value" in existing[k] else "value")
            db_obj.update_record("SiteConfig", key_col, k, {val_col: val_str})
        else:
            db_obj.add_record("SiteConfig", {"sys_key": k, "sys_value": val_str})


def resolve_github_token(db=None, explicit_token: str = None) -> str:
    """Resolves GitHub token strictly in memory: explicit -> session -> ENV pointer -> GITHUB_TOKEN."""
    if explicit_token and explicit_token.strip():
        return explicit_token.strip()
    if _SESSION_GITHUB_TOKEN:
        return _SESSION_GITHUB_TOKEN
    cfg = get_github_settings(db)
    ptr = cfg.get("github_token_pointer", "ENV:GITHUB_TOKEN").strip()
    if ptr.upper().startswith("ENV:"):
        env_name = ptr.split(":", 1)[1].strip()
        val = os.environ.get(env_name, "").strip()
        if val:
            return val
    return os.environ.get("GITHUB_TOKEN", "").strip()


def check_connectivity(timeout: float = 2.0) -> bool:
    """Fast pre-flight connectivity probe (Google 204 endpoint with GitHub API fallback)."""
    for probe_url in ("https://www.google.com/generate_204", "https://api.github.com"):
        try:
            req = urllib.request.Request(probe_url, method="HEAD", headers={"User-Agent": "BEJSON_CMS-ConnectivityCheck"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if 200 <= resp.status < 400:
                    return True
        except Exception:
            continue
    return False


def extract_github_owner_repo(project_meta: dict):
    """Extract (owner, repo) from project_github_url or project_featured_links."""
    candidates = []
    if project_meta.get("project_github_url"):
        candidates.append(str(project_meta["project_github_url"]))
    raw_feat = str(project_meta.get("project_featured_links") or "")
    for line in raw_feat.splitlines():
        line = line.strip()
        if not line:
            continue
        candidates.append(line.split("|", 1)[1].strip() if "|" in line else line)
    gh_re = re.compile(r"https?://(?:www\\.)?github\\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\\.git)?(?:/|$|\\?|#)", re.IGNORECASE)
    for url in candidates:
        m = gh_re.search(url)
        if m:
            return m.group(1), m.group(2)
    return None


def load_stats_cache() -> dict:
    """Loads public GitHub stats cache from BEJSON 104a file (keyed by lowercase owner/repo)."""
    if not os.path.exists(STATS_CACHE_PATH):
        return {}
    try:
        with open(STATS_CACHE_PATH, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        fm = {f["name"]: i for i, f in enumerate(doc.get("Fields", []))}
        out = {}
        for row in doc.get("Values", []):
            fn = str(row[fm["full_name"]]).strip()
            out[fn.lower()] = {
                "full_name": fn,
                "stars": int(row[fm["stars"]]),
                "forks": int(row[fm["forks"]]),
                "open_issues": int(row[fm["open_issues"]]),
                "language": str(row[fm["language"]] or ""),
                "license": str(row[fm["license"]] or ""),
                "pushed_at": str(row[fm["pushed_at"]] or ""),
                "cached_at": str(row[fm["cached_at"]] or ""),
                "is_cached": True,
            }
        return out
    except Exception:
        return {}


def save_stats_cache(cache_map: dict) -> None:
    """Atomically writes public GitHub stats (never tokens) into BEJSON 104a cache."""
    os.makedirs(os.path.dirname(STATS_CACHE_PATH), exist_ok=True)
    rows = []
    for _, item in sorted(cache_map.items()):
        rows.append([
            str(item.get("full_name", "")),
            int(item.get("stars", 0)),
            int(item.get("forks", 0)),
            int(item.get("open_issues", 0)),
            str(item.get("language", "")),
            str(item.get("license", "")),
            str(item.get("pushed_at", "")),
            str(item.get("cached_at", datetime.now().strftime("%Y-%m-%d"))),
        ])
    doc = {
        "Format": "BEJSON",
        "Format_Version": "104a",
        "Format_Creator": "Elton Boehnen",
        "Schema_Name": "GitHub_Stats_Cache",
        "Records_Type": ["GitHubRepoStats"],
        "Fields": [
            {"name": "full_name", "type": "string"},
            {"name": "stars", "type": "integer"},
            {"name": "forks", "type": "integer"},
            {"name": "open_issues", "type": "integer"},
            {"name": "language", "type": "string"},
            {"name": "license", "type": "string"},
            {"name": "pushed_at", "type": "string"},
            {"name": "cached_at", "type": "string"},
        ],
        "Values": rows,
    }
    fd, tmp_p = tempfile.mkstemp(dir=os.path.dirname(STATS_CACHE_PATH), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_p, STATS_CACHE_PATH)
    except Exception:
        if os.path.exists(tmp_p):
            os.unlink(tmp_p)


def fetch_github_repo_stats(owner: str, repo: str, token: str = ""):
    """Fetches public repo metrics via GitHub REST API using stdlib urllib."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "BEJSON_CMS-GitHubHub",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"https://api.github.com/repos/{owner}/{repo}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            if resp.status != 200:
                return None
            payload = json.loads(resp.read().decode("utf-8"))
        lic = payload.get("license") or {}
        spdx = lic.get("spdx_id") if isinstance(lic, dict) else ""
        if spdx == "NOASSERTION":
            spdx = ""
        return {
            "full_name": payload.get("full_name") or f"{owner}/{repo}",
            "stars": int(payload.get("stargazers_count") or 0),
            "forks": int(payload.get("forks_count") or 0),
            "open_issues": int(payload.get("open_issues_count") or 0),
            "language": payload.get("language") or "",
            "license": spdx or "",
            "pushed_at": payload.get("pushed_at") or "",
            "cached_at": datetime.now().strftime("%Y-%m-%d"),
            "is_cached": False,
        }
    except Exception:
        return None


def get_repo_stats_with_fallback(owner: str, repo: str, token: str, is_online: bool, cache_map: dict):
    """Online fetch with cache update; instant cache fallback when offline or rate-limited."""
    key = f"{owner}/{repo}".lower()
    if is_online:
        fresh = fetch_github_repo_stats(owner, repo, token)
        if fresh:
            cache_map[key] = fresh
            return fresh
    return cache_map.get(key)


@github_cube.route("/github")
def github_dashboard():
    db = get_db()
    cfg = get_github_settings(db)
    token_active = bool(resolve_github_token(db))
    token_source = "Session Memory" if _SESSION_GITHUB_TOKEN else ("ENV Pointer" if token_active else "None (Public API)")
    cache_map = load_stats_cache()
    existing_projects = {
        str(p.get("page_slug", "")).lower(): p
        for p in (db.get_records("PageRecord") or [])
        if p.get("page_type") == "project"
    }

    repo_rows_html = ""
    for repo in _CACHED_REPO_LIST:
        r_name = repo.get("name", "")
        r_slug = re.sub(r"[^a-z0-9]+", "-", r_name.lower()).strip("-")
        already = r_slug in existing_projects
        status_badge = '<span class="badge" style="background:#14532d;color:#86efac;">In CMS</span>' if already else '<span class="badge" style="background:#1f2937;color:#e5e7eb;">Not Imported</span>'
        era_guess = "105" if "105" in r_name.lower() or "sword-slasher" in r_name.lower() else "104"
        action_btn = (
            f'<a href="/projects/edit/{existing_projects[r_slug]["page_uuid"]}" class="btn btn-secondary btn-sm">Edit Project</a>'
            if already
            else f'<form method="POST" action="/github/import-repo" style="display:inline;">'
                 f'<input type="hidden" name="repo_name" value="{_html_mod.escape(r_name)}">'
                 f'<input type="hidden" name="repo_url" value="{_html_mod.escape(repo.get("html_url", ""))}">'
                 f'<input type="hidden" name="repo_desc" value="{_html_mod.escape(repo.get("description") or "")}">'
                 f'<input type="hidden" name="repo_era" value="{era_guess}">'
                 f'<button class="btn btn-primary btn-sm">+ Create Project</button></form>'
        )
        repo_rows_html += (
            f"<tr><td><strong>{_html_mod.escape(r_name)}</strong><br>"
            f"<small style='color:var(--text-secondary);'>{_html_mod.escape((repo.get('description') or '')[:90])}</small></td>"
            f"<td>{_html_mod.escape(repo.get('language') or '—')}</td>"
            f"<td>{status_badge}</td><td>{action_btn}</td></tr>"
        )

    body = f"""
    <div class="card" style="margin-bottom:20px;">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:14px;">
        <h2 style="margin:0;">GitHub Integration Hub</h2>
        <span class="badge" style="background:{'#14532d' if token_active else '#374151'};color:#fff;">Token: {token_source} &middot; Cached Repos: {len(cache_map)}</span>
      </div>
      <form method="POST" action="/github/settings">
        <div class="form-group"><label class="form-label">GitHub Username</label><input type="text" name="github_username" class="form-control" value="{_html_mod.escape(cfg['github_username'])}"></div>
        <div class="form-group"><label class="form-label">ENV Token Pointer (Zero Secrets on Disk)</label><input type="text" name="github_token_pointer" class="form-control" value="{_html_mod.escape(cfg['github_token_pointer'])}"></div>
        <div class="form-group"><label class="form-label">Ephemeral Session Token (In-Memory Only, Optional)</label><input type="password" name="session_github_token" autocomplete="off" class="form-control" placeholder="Leave blank to keep ENV pointer"></div>
        <div style="display:flex;gap:18px;flex-wrap:wrap;margin:12px 0;">
          <label><input type="checkbox" name="github_stats_enabled" value="true" {'checked' if cfg['github_stats_enabled'] == 'true' else ''}> Enable Live/Cached GitHub Stats on Build</label>
          <label><input type="checkbox" name="github_post_strip_enabled" value="true" {'checked' if cfg['github_post_strip_enabled'] == 'true' else ''}> Auto-Inject Compact Project Link Strip on Linked Posts</label>
        </div>
        <div style="display:flex;gap:10px;flex-wrap:wrap;">
          <button class="btn btn-primary" type="submit">Save GitHub Settings</button>
          <button class="btn btn-secondary" type="submit" formaction="/github/clear-token">Clear Session Token</button>
          <button class="btn btn-secondary" type="submit" formaction="/github/fetch-repos">Fetch Repos from GitHub</button>
        </div>
      </form>
    </div>
    <div class="card">
      <h3 style="margin-top:0;">Repository Importer (1-Click Project Page Creation)</h3>
      <p style="color:var(--text-secondary);font-size:0.88rem;">Click <strong>Fetch Repos from GitHub</strong> above to browse repositories and create canonical 104db Project Pages directly.</p>
      {'<table class="table"><thead><tr><th>Repository</th><th>Language</th><th>Status</th><th>Action</th></tr></thead><tbody>' + repo_rows_html + '</tbody></table>' if repo_rows_html else '<p style="color:var(--text-secondary);">No repositories loaded yet.</p>'}
    </div>
    """
    return R(body, breadcrumbs=[{"label": "Dashboard", "href": "/"}, {"label": "GitHub", "href": None}], active_section="github")


@github_cube.route("/github/settings", methods=["POST"])
def github_save_settings():
    global _SESSION_GITHUB_TOKEN
    db = get_db()
    save_github_settings({
        "github_username": request.form.get("github_username", "boehnenelton").strip() or "boehnenelton",
        "github_token_pointer": request.form.get("github_token_pointer", "ENV:GITHUB_TOKEN").strip() or "ENV:GITHUB_TOKEN",
        "github_stats_enabled": "true" if request.form.get("github_stats_enabled") else "false",
        "github_post_strip_enabled": "true" if request.form.get("github_post_strip_enabled") else "false",
    }, db)
    sess_tok = request.form.get("session_github_token", "").strip()
    if sess_tok:
        _SESSION_GITHUB_TOKEN = sess_tok
    flash("GitHub settings saved (tokens remain in memory/ENV only).", "success")
    return redirect("/github")


@github_cube.route("/github/clear-token", methods=["POST"])
def github_clear_token():
    global _SESSION_GITHUB_TOKEN
    _SESSION_GITHUB_TOKEN = ""
    flash("Ephemeral session GitHub token cleared from memory.", "info")
    return redirect("/github")


@github_cube.route("/github/fetch-repos", methods=["POST"])
def github_fetch_repos():
    global _CACHED_REPO_LIST
    db = get_db()
    cfg = get_github_settings(db)
    if not check_connectivity():
        flash("Offline: connectivity check failed. Using cached stats on build.", "warning")
        return redirect("/github")
    tok = resolve_github_token(db)
    user = cfg.get("github_username", "boehnenelton")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "BEJSON_CMS-GitHubHub"}
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    try:
        req = urllib.request.Request(f"https://api.github.com/users/{user}/repos?per_page=100&sort=updated", headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            _CACHED_REPO_LIST = json.loads(resp.read().decode("utf-8"))
        flash(f"Loaded {len(_CACHED_REPO_LIST)} repositories for {user}.", "success")
    except Exception as exc:
        flash(f"Could not fetch GitHub repositories: {exc}", "error")
    return redirect("/github")


@github_cube.route("/github/import-repo", methods=["POST"])
def github_import_repo():
    from BEJSON_CMS_Content import _write_project_page_doc
    db = get_db()
    repo_name = request.form.get("repo_name", "").strip()
    repo_url = re.sub(r"\\.git/?$", "", request.form.get("repo_url", "").strip(), flags=re.IGNORECASE)
    repo_desc = request.form.get("repo_desc", "").strip() or f"{repo_name} repository in the zero-SQL BEJSON ecosystem."
    repo_era = request.form.get("repo_era", "104").strip()
    if not repo_name:
        return redirect("/github")
    new_uuid = str(uuid.uuid4())
    slug = re.sub(r"[^a-z0-9]+", "-", repo_name.lower()).strip("-")
    db.add_record("PageRecord", {
        "page_uuid": new_uuid,
        "page_title": repo_name,
        "page_slug": slug,
        "page_cat_name": "Projects",
        "page_type": "project",
        "page_created_at": datetime.now().strftime("%Y-%m-%d"),
        "page_external_url": None,
        "page_author_name": "Elton Boehnen",
        "page_featured_img": DEFAULT_FEATURED_IMAGE,
        "page_featured_video_url": "",
        "page_featured_diagram": "",
        "page_project_uuid": "",
    })
    html_body = f"<h2>{_html_mod.escape(repo_name)}</h2><p>{_html_mod.escape(repo_desc)}</p>"
    _write_project_page_doc(new_uuid, repo_name, html_body, {
        "project_github_url": repo_url,
        "project_gemini_notepad_url": "",
        "project_featured_links": "",
        "project_youtube_links": "",
        "project_asset_links": "",
        "project_bejson_era": repo_era,
    })
    flash(f"Imported '{repo_name}' as a Project Page.", "success")
    return redirect(f"/projects/edit/{new_uuid}")
