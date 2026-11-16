#!/usr/bin/env python3
"""
# ==============================================================================
# Tool:        fix_and_publish_all_posts.py
# Family:      CMS
# Description: Batch synchronizer that edits and fixes all BEJSON_CMS posts on
#              Substack with strict 4-8 word purpose titles, snappy subtitles,
#              native ProseMirror AST compilation (zero raw HTML), and live publish.
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
from typing import Any, Dict, List, Optional

SCRIPT_PATH = Path(__file__).resolve()
CMS_ROOT = SCRIPT_PATH.parent.parent
DEFINITIONS_FILE = Path("/storage/emulated/0/.env/user/definitions.json")
SECURE_ENV_FILE = Path("/storage/emulated/0/.env/secure/secureenv_file.json")
SUBSTACK_TOOLS_DIR = Path("/data/data/com.termux/files/home/setup_tools/substack")

if str(SUBSTACK_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(SUBSTACK_TOOLS_DIR))

from md_to_prosemirror import convert_to_prosemirror, verify_zero_html
from substack_client import get_substack_credentials, make_substack_request

PAGES_INDEX = CMS_ROOT / "storage" / "mfdb" / "site_master" / "data" / "pagerecord.bejson"
PAGES_DB_DIR = CMS_ROOT / "storage" / "mfdb" / "pages_db"

# Refined Post Catalog: 4-8 Word Purpose Titles + Snappy Subtitles + Existing Draft ID Mapping
POST_METADATA_MAP: Dict[str, Dict[str, Any]] = {
    "7573cc7d-8b2d-4c23-8007-98beb8db8328": {
        "title": "The Elite BEJSON and MFDB Guide",
        "subtitle": "The No-BS breakdown of Zero-SQL flat-file positional matrices.",
        "existing_draft_id": 224844658,
    },
    "b9161aaf-c14c-4f5a-a444-9ff7399687b0": {
        "title": "BEJSON 105 and Cryptographic Integrity Masterclass",
        "subtitle": "Dissecting UUIDv4 keys, cross-entity relational hashes, and zero-SQL integrity.",
        "existing_draft_id": 224853615,
    },
    "7513e7fe-f937-4eaf-9908-96224251b66f": {
        "title": "BEJSON 104 Core Polyglot Guide Part 1",
        "subtitle": "Zero-SDK tabular persistence across Python, JS, TS, and Bash.",
        "existing_draft_id": 224853708,
    },
    "ebe88c9c-47bd-47a4-9f8d-35463bd523f1": {
        "title": "BEJSON 105 Core Polyglot Guide Part 2",
        "subtitle": "Multi-file database federation and UUIDv4 integrity without external daemons.",
        "existing_draft_id": 224843805,
    },
    "d0dc2f5b-ab44-47a1-ba62-fcf566309907": {
        "title": "Inside the BEJSON 104 AI Family",
        "subtitle": "Prompt hydration, schema caching, and 90% token reduction for LLM context windows.",
        "existing_draft_id": 224843808,
    },
    "89b6ebfa-ad88-4521-a700-bf6f43d2ac37": {
        "title": "The Shadow Link Action-RPG Engine Architecture",
        "subtitle": "Dissecting zero-hardcoded BEJSON 105 state and spatial rendering in React.",
        "existing_draft_id": 224843810,
    },
    "11986eaf-b66c-4243-89ae-7c9012543f01": {
        "title": "BEJSON Diagrammer and Spatial Validation Engine",
        "subtitle": "Autopsy of zero-SQL spatial layouts, interactive canvas generation, and schema linters.",
        "existing_draft_id": 224843814,
    },
    "a72368ee-3689-4b72-bd57-bcb4b6415e89": {
        "title": "The Zero-SQL BEJSON CMS Architecture",
        "subtitle": "Why your enterprise CMS stack is an overpriced dumpster fire.",
        "existing_draft_id": 224856544,
    },
    "bc247bd4-28d7-4d41-ab58-f55ae05433fb": {
        "title": "BEJSON and MFDB Crash Course 23",
        "subtitle": "Comprehensive architectural reference for Foundational and Integrity eras.",
        "existing_draft_id": 224843816,
    },
    "11a1a1b1-3356-4bed-b21e-b3ca94d503ac": {
        "title": "GitHub Ecosystem and Open Source Architecture",
        "subtitle": "Autonomous repo synchronization, multi-format documentation, and publishing pipelines.",
        "existing_draft_id": 224843823,
    },
    "a8a81b42-753a-493c-a539-47e8a659e04a": {
        "title": "The JSON Attention Tax on LLMs",
        "subtitle": "Why your $50k LLM inference bill is paying for repetitive structural garbage.",
        "existing_draft_id": 224843829,
    },
    "5cbdda76-937c-48ed-a697-6b38eec5efbd": {
        "title": "Database Passwords and In-Memory Security",
        "subtitle": "Ephemeral credentials, zero-SQL POSIX storage, and in-memory key elimination.",
        "existing_draft_id": 224843830,
    },
    "1d2ddf2f-c5a5-44fb-b76d-b8b769a3e6c1": {
        "title": "BEJSON 104 Foundations and Zero-Bloat Architecture",
        "subtitle": "Dissecting the cloud infrastructure scam, AI attention drift, and corporate bloat.",
        "existing_draft_id": 224852737,
    },
    "2ec89c17-9b49-40ec-a29f-ae89ecf9fd6f": {
        "title": "The Legacy BEJSON 104 Libraries Polyglot Guide",
        "subtitle": "Stop importing 80MB of npm trash: zero-SDK implementations with O(1) field map caching.",
        "existing_draft_id": 224852741,
    },
}


def load_cms_post(page_uuid: str) -> Optional[Dict[str, Any]]:
    """Loads a post payload from pages_db."""
    content_file = PAGES_DB_DIR / f"{page_uuid}.json"
    if not content_file.exists():
        return None

    with open(content_file, "r", encoding="utf-8") as fh:
        content_data = json.load(fh)

    c_fields = [f_entry["name"] for f_entry in content_data["Fields"]]
    body_idx = c_fields.index("html_body") if "html_body" in c_fields else -1
    md_idx = c_fields.index("markdown_body") if "markdown_body" in c_fields else -1

    html_body = ""
    markdown_body = ""
    for c_row in content_data.get("Values", []):
        if body_idx != -1 and c_row[body_idx] and c_row[body_idx].strip():
            html_body = c_row[body_idx]
        if md_idx != -1 and c_row[md_idx] and c_row[md_idx].strip():
            markdown_body = c_row[md_idx]
        if html_body or markdown_body:
            break

    # Look for matching markdown file in Reports
    if not markdown_body:
        reports_dir = Path("/storage/emulated/0/Admin/Resources/Reports")
        if reports_dir.exists():
            for md_f in reports_dir.glob("*.md"):
                if page_uuid in md_f.name:
                    markdown_body = md_f.read_text(encoding="utf-8")
                    break

    return {
        "page_uuid": page_uuid,
        "html_body": html_body,
        "markdown_body": markdown_body,
    }


def update_or_create_draft(
    base_url: str,
    session_sid: str,
    user_id: int,
    draft_id: Optional[int],
    title: str,
    subtitle: str,
    pm_doc: Dict[str, Any],
) -> Optional[int]:
    """Updates an existing draft or creates a new one using verified ProseMirror AST."""
    payload = {
        "draft_title": title,
        "draft_subtitle": subtitle,
        "draft_body": json.dumps(pm_doc),
        "type": "newsletter",
        "draft_bylines": [{"id": user_id, "is_guest": False}],
    }

    if draft_id:
        url = f"{base_url}/api/v1/drafts/{draft_id}"
        ok, res, err = make_substack_request(url, method="PUT", json_payload=payload, session_sid=session_sid)
        if ok:
            return draft_id
        else:
            print(f"    [!] PUT update on draft {draft_id} failed: {err}")
            # Fall back to creating fresh draft if PUT fails
            draft_id = None

    url = f"{base_url}/api/v1/drafts"
    ok, res, err = make_substack_request(url, method="POST", json_payload=payload, session_sid=session_sid)
    if ok:
        created_id = res.get("id") or res.get("draft", {}).get("id")
        return created_id
    else:
        print(f"    [!] POST draft creation failed: {err}")
        return None


def attempt_publish_draft(base_url: str, session_sid: str, draft_id: int) -> Tuple[bool, str]:
    """Attempts to publish a draft live."""
    # 1. Prepublish check
    make_substack_request(f"{base_url}/api/v1/drafts/{draft_id}/prepublish", session_sid=session_sid)

    # 2. Publish request
    url = f"{base_url}/api/v1/drafts/{draft_id}/publish"
    ok, res, err = make_substack_request(
        url,
        method="POST",
        json_payload={"send": False, "share_automatically": False},
        session_sid=session_sid,
    )
    if ok:
        return True, "Published live"
    else:
        return False, err


def main():
    print("=================================================")
    print(" SUBSTACK BATCH EDITOR & PUBLISHER (ZERO-HTML)")
    print("=================================================")

    session_sid, subdomain, base_url = get_substack_credentials()
    if not session_sid or not base_url:
        print("[X] Missing SUBSTACK credentials.")
        sys.exit(1)

    user_id_str = os.environ.get("SUBSTACK_USER_ID", "571928672").strip()
    try:
        user_id = int(user_id_str)
    except ValueError:
        user_id = 571928672

    print(f"[*] Target Publication: {base_url} (User ID: {user_id})")
    print(f"[*] Processing {len(POST_METADATA_MAP)} canonical posts...\n")

    summary_results = []

    for idx, (uuid_str, meta) in enumerate(POST_METADATA_MAP.items(), start=1):
        clean_title = meta["title"]
        clean_subtitle = meta["subtitle"]
        existing_draft_id = meta.get("existing_draft_id")

        print(f"[{idx}/{len(POST_METADATA_MAP)}] '{clean_title}'")
        print(f"    Subtitle: '{clean_subtitle}'")

        post_data = load_cms_post(uuid_str)
        if not post_data:
            print("    [X] Error: Could not find post in pages_db")
            continue

        raw_content = post_data.get("markdown_body") or post_data.get("html_body")
        if not raw_content:
            print("    [X] Error: No content in post")
            continue

        try:
            pm_doc = convert_to_prosemirror(raw_content)
            verify_zero_html(pm_doc)
            nodes_count = len(pm_doc.get("content", []))
            print(f"    [✓] ProseMirror AST compiled: {nodes_count} nodes (Zero-HTML verified)")
        except Exception as conv_err:
            print(f"    [X] Conversion failed: {conv_err}")
            continue

        # Update or create draft
        target_draft_id = update_or_create_draft(
            base_url=base_url,
            session_sid=session_sid,
            user_id=user_id,
            draft_id=existing_draft_id,
            title=clean_title,
            subtitle=clean_subtitle,
            pm_doc=pm_doc,
        )

        if not target_draft_id:
            print("    [X] Failed to save draft on Substack.")
            continue

        print(f"    [✓] Draft Synced: ID {target_draft_id} -> {base_url}/publish/post/{target_draft_id}")

        # Attempt to publish
        pub_ok, pub_msg = attempt_publish_draft(base_url, session_sid, target_draft_id)
        if pub_ok:
            print(f"    [✓] STATUS: PUBLISHED LIVE!")
            summary_results.append((clean_title, target_draft_id, "PUBLISHED", f"{base_url}/p/{target_draft_id}"))
        else:
            print(f"    [*] STATUS: DRAFT READY (Publish requires browser re-auth: {pub_msg})")
            summary_results.append((clean_title, target_draft_id, "DRAFT_READY", f"{base_url}/publish/post/{target_draft_id}"))

        time.sleep(1.5)

    print("\n" + "=" * 55)
    print(" SYNCHRONIZATION SUMMARY")
    print("=" * 55)
    for title, draft_id, status, link in summary_results:
        print(f"• [{status}] {title}")
        print(f"  Link: {link}")


if __name__ == "__main__":
    main()
