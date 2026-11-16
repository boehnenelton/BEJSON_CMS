#!/usr/bin/env python3
"""
# ==============================================================================
# Tool:        substack_publisher.py
# Family:      CMS
# Description: Zero-dependency Substack batch publisher and syndicator for
#              BEJSON_CMS posts with session token auth and duplicate avoidance.
# Version:     100
# Date:        2026-11-14
# Author:      Elton Boehnen · boehnenelton2024@gmail.com
# Relational ID: 4f8a32b1-91a7-4e63-b8f2-1d587c69a031
# License:     PolyForm-Noncommercial-1.0.0
# ==============================================================================
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional, Set

SUBSTACK_TOOLS_DIR = Path("/data/data/com.termux/files/home/setup_tools/substack")
if str(SUBSTACK_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(SUBSTACK_TOOLS_DIR))
try:
    from md_to_prosemirror import convert_to_prosemirror, verify_zero_html
except ImportError:
    convert_to_prosemirror = None  # type: ignore
    verify_zero_html = None  # type: ignore

SCRIPT_PATH = Path(__file__).resolve()
CMS_ROOT = SCRIPT_PATH.parent.parent
DEFINITIONS_FILE = Path("/storage/emulated/0/.env/user/definitions.json")
SECURE_ENV_FILE = Path("/storage/emulated/0/.env/secure/secureenv_file.json")

PAGES_INDEX = CMS_ROOT / "storage" / "mfdb" / "site_master" / "data" / "pagerecord.bejson"
PAGES_DB_DIR = CMS_ROOT / "storage" / "mfdb" / "pages_db"


def load_secure_env() -> dict[str, str]:
    """Loads environment variables from secureenv_file.json using BEJSON O(1) field map."""
    env_map: dict[str, str] = {}
    if SECURE_ENV_FILE.exists():
        try:
            with open(SECURE_ENV_FILE, "r", encoding="utf-8") as file_handle:
                data = json.load(file_handle)
            fields = [field_entry["name"] for field_entry in data.get("Fields", [])]
            name_idx = fields.index("var_name")
            val_idx = fields.index("var_value")
            for row in data.get("Values", []):
                if len(row) > max(name_idx, val_idx):
                    env_map[row[name_idx]] = row[val_idx] or ""
        except Exception:
            pass

    # Also overlay runtime os.environ
    for k, v in os.environ.items():
        if k.startswith("SUBSTACK_") and v:
            env_map[k] = v
    return env_map


def get_cms_posts() -> list[dict[str, Any]]:
    """Loads all post entities and their html_body payloads from the CMS MFDB."""
    if not PAGES_INDEX.exists():
        return []

    with open(PAGES_INDEX, "r", encoding="utf-8") as index_fh:
        index_data = json.load(index_fh)

    fields = [field_entry["name"] for field_entry in index_data["Fields"]]
    uuid_idx = fields.index("page_uuid")
    title_idx = fields.index("page_title")
    type_idx = fields.index("page_type")
    cat_idx = fields.index("page_cat_name")
    desc_idx = fields.index("page_meta_desc") if "page_meta_desc" in fields else -1

    posts = []
    for row in index_data.get("Values", []):
        page_uuid = row[uuid_idx]
        title = row[title_idx]
        page_type = row[type_idx]
        category = row[cat_idx]
        description = row[desc_idx] if desc_idx != -1 else ""

        content_file = PAGES_DB_DIR / f"{page_uuid}.json"
        if not content_file.exists():
            continue

        with open(content_file, "r", encoding="utf-8") as content_fh:
            content_data = json.load(content_fh)

        c_fields = [f_entry["name"] for f_entry in content_data["Fields"]]
        body_idx = c_fields.index("html_body") if "html_body" in c_fields else -1
        md_idx = c_fields.index("markdown_body") if "markdown_body" in c_fields else -1

        html_body = None
        markdown_body = None
        for c_row in content_data.get("Values", []):
            if body_idx != -1 and c_row[body_idx] and len(c_row[body_idx].strip()) > 0:
                html_body = c_row[body_idx]
            if md_idx != -1 and c_row[md_idx] and len(c_row[md_idx].strip()) > 0:
                markdown_body = c_row[md_idx]
            if html_body or markdown_body:
                break

        # Check for companion markdown report in $ADMIN_REPORTS
        if not markdown_body:
            reports_dir = Path("/storage/emulated/0/Admin/Resources/Reports")
            if reports_dir.exists():
                for md_cand in reports_dir.glob("*.md"):
                    if page_uuid in md_cand.name or (len(title) > 8 and title.lower()[:20] in md_cand.name.lower()):
                        markdown_body = md_cand.read_text(encoding="utf-8")
                        break

        if html_body or markdown_body:
            posts.append({
                "page_uuid": page_uuid,
                "title": title,
                "type": page_type,
                "category": category,
                "description": description,
                "html_body": html_body or "",
                "markdown_body": markdown_body or "",
            })

    return posts


def get_existing_titles(base_url: str, session_sid: str) -> dict[str, Any]:
    """Queries both published posts and drafts from Substack API to prevent duplication."""
    titles_map: dict[str, Any] = {}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"
        ),
        "Cookie": f"substack.sid={session_sid}; connect.sid={session_sid}",
        "Accept": "application/json",
    }

    # 1. Fetch published posts
    try:
        posts_url = f"{base_url}/api/v1/posts?limit=50"
        req = urllib.request.Request(posts_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("posts", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            for item in items:
                title = item.get("title", "").strip()
                if title:
                    titles_map[title.lower()] = {"id": item.get("id"), "title": title, "status": "published", "slug": item.get("slug")}
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
                title_cand = item.get("draft_title") or item.get("title")
                if title_cand:
                    title_clean = title_cand.strip()
                    if title_clean.lower() not in titles_map:
                        titles_map[title_clean.lower()] = {"id": item.get("id"), "title": title_clean, "status": "draft"}
    except Exception:
        pass

    return titles_map


def get_user_id(session_sid: str) -> Optional[int]:
    """Fetches the authenticated user ID from Substack profile self endpoint."""
    url = "https://substack.com/api/v1/user/profile/self"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"
        ),
        "Cookie": f"substack.sid={session_sid}; connect.sid={session_sid}",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("id")
    except Exception:
        return None


def post_to_substack(
    base_url: str,
    session_sid: str,
    title: str,
    subtitle: str,
    content: str,
    user_id: int = 571928672,
) -> dict[str, Any]:
    """Creates a new post draft on Substack with verified ProseMirror AST."""
    if convert_to_prosemirror is None or verify_zero_html is None:
        raise RuntimeError("md_to_prosemirror module could not be imported.")

    # Mandatory ProseMirror AST compilation & Pre-flight Zero-HTML gate
    pm_doc = convert_to_prosemirror(content)
    verify_zero_html(pm_doc)

    url = f"{base_url}/api/v1/drafts"
    payload = {
        "draft_title": title,
        "draft_subtitle": subtitle or "",
        "draft_body": json.dumps(pm_doc),
        "type": "newsletter",
        "draft_bylines": [{"id": user_id, "is_guest": False}],
    }
    encoded_data = json.dumps(payload).encode("utf-8")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"
        ),
        "Cookie": f"substack.sid={session_sid}; connect.sid={session_sid}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, data=encoded_data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def update_substack_draft(
    base_url: str,
    session_sid: str,
    draft_id: Any,
    title: str,
    subtitle: str,
    content: str,
    user_id: int = 571928672,
) -> dict[str, Any]:
    """Updates an existing draft/post on Substack with verified ProseMirror AST."""
    if convert_to_prosemirror is None or verify_zero_html is None:
        raise RuntimeError("md_to_prosemirror module could not be imported.")

    pm_doc = convert_to_prosemirror(content)
    verify_zero_html(pm_doc)

    url = f"{base_url}/api/v1/drafts/{draft_id}"
    payload = {
        "draft_title": title,
        "draft_subtitle": subtitle or "",
        "draft_body": json.dumps(pm_doc),
        "type": "newsletter",
        "draft_bylines": [{"id": user_id, "is_guest": False}],
    }
    encoded_data = json.dumps(payload).encode("utf-8")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"
        ),
        "Cookie": f"substack.sid={session_sid}; connect.sid={session_sid}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, data=encoded_data, headers=headers, method="PUT")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def publish_substack_draft(base_url: str, session_sid: str, draft_id: Any) -> tuple[bool, str]:
    """Publishes a draft live to Substack."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"
        ),
        "Cookie": f"substack.sid={session_sid}; connect.sid={session_sid}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        pre_req = urllib.request.Request(f"{base_url}/api/v1/drafts/{draft_id}/prepublish", headers=headers, method="GET")
        with urllib.request.urlopen(pre_req, timeout=15) as _:
            pass
    except Exception:
        pass

    pub_url = f"{base_url}/api/v1/drafts/{draft_id}/publish"
    pub_payload = {"send": False, "share_automatically": False}
    try:
        req = urllib.request.Request(pub_url, data=json.dumps(pub_payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return True, data.get("canonical_url") or f"{base_url}/p/{draft_id}"
    except urllib.error.HTTPError as http_err:
        err_msg = http_err.read().decode("utf-8", errors="ignore")
        return False, f"HTTP {http_err.code}: {err_msg}"
    except Exception as e:
        return False, str(e)


def main():
    should_publish = "--draft-only" not in sys.argv
    print("=================================================")
    print(" BEJSON_CMS -> Substack Batch Syndicator")
    print(f" Mode: {'Live (Publish)' if should_publish else 'Draft Only'}")
    print("=================================================")

    env_vars = load_secure_env()
    session_sid = env_vars.get("SUBSTACK_SID", "").strip()
    subdomain = env_vars.get("SUBSTACK_SUBDOMAIN", "").strip()
    base_url = env_vars.get("SUBSTACK_URL", "").strip()

    if not base_url and subdomain:
        base_url = f"https://{subdomain}.substack.com"

    if not session_sid or not base_url:
        print("[!] Error: Missing required SUBSTACK_SID or SUBSTACK_SUBDOMAIN in secureenv / environment.")
        print("[*] Run ~/setup_tools/substack/setup.sh to configure Substack credentials.")
        sys.exit(1)

    user_id_str = env_vars.get("SUBSTACK_USER_ID", "").strip()
    try:
        user_id = int(user_id_str) if user_id_str else None
    except ValueError:
        user_id = None
    if not user_id:
        user_id = get_user_id(session_sid) or 571928672
    print(f"[+] Authenticated as Substack User ID: {user_id}")

    posts = get_cms_posts()
    print(f"[+] Loaded {len(posts)} post(s) from BEJSON_CMS pages_db.")

    print(f"[*] Querying existing posts and drafts on {base_url} to avoid duplicates...")
    existing_map = get_existing_titles(base_url, session_sid)
    print(f"[+] Found {len(existing_map)} existing published/draft post(s) on publication.")

    published_count = 0
    for idx, post in enumerate(posts, start=1):
        clean_title = post["title"].strip()
        existing_entry = existing_map.get(clean_title.lower())

        if existing_entry:
            existing_id = existing_entry.get("id")
            existing_status = existing_entry.get("status")
            print(f"\n[{idx}/{len(posts)}] Existing {existing_status} found for '{clean_title}' (ID: {existing_id}).")
            if existing_status == "published":
                print(f"    -> Updating live published post draft on Substack...")
                try:
                    update_substack_draft(
                        base_url=base_url,
                        session_sid=session_sid,
                        draft_id=existing_id,
                        title=clean_title,
                        subtitle=post.get("description", ""),
                        content=post.get("markdown_body") or post.get("html_body", ""),
                        user_id=user_id,
                    )
                    print(f"    -> [✓] Updated draft content for ID {existing_id}.")
                except Exception as update_err:
                    print(f"    -> [!] Update note: {update_err}")
                continue

            elif existing_status == "draft" and should_publish:
                print(f"    -> Publishing existing draft {existing_id}...")
                ok, res_url = publish_substack_draft(base_url, session_sid, existing_id)
                if ok:
                    print(f"    -> [✓] Draft {existing_id} published live: {res_url}")
                    published_count += 1
                else:
                    print(f"    -> [!] Could not auto-publish: {res_url}")
                continue

        print(f"\n[{idx}/{len(posts)}] Creating on Substack: '{clean_title}'...")
        max_attempts = 3
        backoff_delay = 5
        for attempt in range(1, max_attempts + 1):
            try:
                res = post_to_substack(
                    base_url=base_url,
                    session_sid=session_sid,
                    title=clean_title,
                    subtitle=post.get("description", ""),
                    content=post.get("markdown_body") or post.get("html_body", ""),
                    user_id=user_id,
                )
                draft_id = res.get("id") or res.get("draft", {}).get("id", "N/A")
                print(f"    -> Draft Created! Draft ID: {draft_id}")
                existing_map[clean_title.lower()] = {"id": draft_id, "title": clean_title, "status": "draft"}

                if should_publish and draft_id != "N/A":
                    print(f"    -> Publishing draft {draft_id} live...")
                    ok, res_url = publish_substack_draft(base_url, session_sid, draft_id)
                    if ok:
                        print(f"    -> [✓] Published live: {res_url}")
                        published_count += 1
                    else:
                        print(f"    -> [!] Draft saved, publish notice: {res_url}")
                else:
                    print(f"    -> Edit URL: {base_url}/publish/post/{draft_id}")
                    published_count += 1

                time.sleep(3)
                break
            except urllib.error.HTTPError as http_err:
                error_body = http_err.read().decode("utf-8", errors="ignore")
                if http_err.code == 429:
                    print(f"    -> [!] Rate limit hit (attempt {attempt}/{max_attempts}). Backing off {backoff_delay}s...")
                    time.sleep(backoff_delay)
                    backoff_delay *= 2
                else:
                    print(f"    -> [!] HTTP Error {http_err.code}: {http_err.reason}\n       {error_body}")
                    break
            except Exception as gen_err:
                print(f"    -> [!] Failed: {gen_err}")
                break

    print(f"\n[+] Substack syndication completed.")


if __name__ == "__main__":
    main()
