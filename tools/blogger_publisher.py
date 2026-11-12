#!/usr/bin/env python3
"""
Tool:        blogger_publisher.py
Family:      CMS
Description: Zero-dependency Google Blogger OAuth 2.0 authenticator and batch publisher for BEJSON_CMS posts with rate limit handling and duplicate detection.
Version:     101
Date:        2026-11-11
Author:      Elton Boehnen
Contact:     boehnenelton2024@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID: 9e4f2a71-6c5b-4e12-8921-ef781a912c44
"""

import os
import sys
import time
import json
import subprocess
import urllib.parse
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Paths
SCRIPT_PATH = Path(__file__).resolve()
CMS_ROOT = SCRIPT_PATH.parent.parent
DEFINITIONS_FILE = Path("/storage/emulated/0/.env/user/definitions.json")
SECURE_ENV_FILE = Path("/storage/emulated/0/.env/secure/secureenv_file.json")
TOKEN_STORAGE_PATH = Path(os.path.expanduser("~/.env/blogger_token.json"))

PAGES_INDEX = CMS_ROOT / "storage" / "mfdb" / "site_master" / "data" / "pagerecord.bejson"
PAGES_DB_DIR = CMS_ROOT / "storage" / "mfdb" / "pages_db"

PORT = 8080
REDIRECT_URI = f"http://localhost:{PORT}/callback"
OAUTH_SCOPE = "https://www.googleapis.com/auth/blogger"


def load_secure_env() -> dict:
    if not SECURE_ENV_FILE.exists():
        raise FileNotFoundError(f"Secure environment file not found: {SECURE_ENV_FILE}")
    with open(SECURE_ENV_FILE, "r", encoding="utf-8") as file_handle:
        data = json.load(file_handle)
    fields = [field_entry["name"] for field_entry in data["Fields"]]
    name_idx = fields.index("var_name")
    val_idx = fields.index("var_value")
    return {row[name_idx]: row[val_idx] for row in data["Values"]}


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    captured_code = None
    captured_error = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/callback":
            query_params = urllib.parse.parse_qs(parsed.query)
            if "code" in query_params:
                OAuthCallbackHandler.captured_code = query_params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                response_html = (
                    "<html><body style='font-family:sans-serif;background:#000;color:#fff;text-align:center;padding:50px;'>"
                    "<h2 style='color:#22c55e;'>Authorization Successful!</h2>"
                    "<p>Google Blogger OAuth token received. You can close this tab and return to your terminal.</p>"
                    "</body></html>"
                )
                self.wfile.write(response_html.encode("utf-8"))
            elif "error" in query_params:
                OAuthCallbackHandler.captured_error = query_params["error"][0]
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"Authorization Failed: {OAuthCallbackHandler.captured_error}".encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format_spec, *args):
        return


def exchange_code_for_tokens(client_id: str, client_secret: str, code: str) -> dict:
    token_url = "https://oauth2.googleapis.com/token"
    payload = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }).encode("utf-8")

    req = urllib.request.Request(token_url, data=payload, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    token_url = "https://oauth2.googleapis.com/token"
    payload = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }).encode("utf-8")

    req = urllib.request.Request(token_url, data=payload, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


def get_authorized_token(client_id: str, client_secret: str) -> str:
    if TOKEN_STORAGE_PATH.exists():
        try:
            with open(TOKEN_STORAGE_PATH, "r", encoding="utf-8") as file_handle:
                token_data = json.load(file_handle)
            if "refresh_token" in token_data:
                token_response = refresh_access_token(client_id, client_secret, token_data["refresh_token"])
                token_data["access_token"] = token_response["access_token"]
                with open(TOKEN_STORAGE_PATH, "w", encoding="utf-8") as file_handle:
                    json.dump(token_data, file_handle, indent=2)
                return token_data["access_token"]
        except Exception:
            pass

    auth_query = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": OAUTH_SCOPE,
        "access_type": "offline",
        "prompt": "consent"
    })
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{auth_query}"

    print(f"\n[+] Starting OAuth callback listener on {REDIRECT_URI}...")
    server = HTTPServer(("127.0.0.1", PORT), OAuthCallbackHandler)

    try:
        proc = subprocess.Popen(["termux-clipboard-set"], stdin=subprocess.PIPE)
        proc.communicate(input=auth_url.encode("utf-8"))
    except Exception:
        pass

    try:
        subprocess.run([
            "am", "start",
            "-n", "com.android.chrome/com.google.android.apps.chrome.Main",
            "-d", auth_url
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    while OAuthCallbackHandler.captured_code is None and OAuthCallbackHandler.captured_error is None:
        server.handle_request()

    server.server_close()

    if OAuthCallbackHandler.captured_error:
        raise RuntimeError(f"OAuth failed: {OAuthCallbackHandler.captured_error}")

    code = OAuthCallbackHandler.captured_code
    token_response = exchange_code_for_tokens(client_id, client_secret, code)

    TOKEN_STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_STORAGE_PATH, "w", encoding="utf-8") as file_handle:
        json.dump(token_response, file_handle, indent=2)

    return token_response["access_token"]


def get_existing_blog_titles(access_token: str, blog_id: str) -> set:
    titles = set()
    url = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts?maxResults=50"
    try:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for item in data.get("items", []):
                if "title" in item:
                    titles.add(item["title"].strip())
    except Exception as e:
        print(f"[*] Warning: Could not fetch existing posts: {e}")
    return titles


def get_cms_posts() -> list:
    if not PAGES_INDEX.exists():
        raise FileNotFoundError(f"Page record file not found: {PAGES_INDEX}")

    with open(PAGES_INDEX, "r", encoding="utf-8") as file_handle:
        index_data = json.load(file_handle)

    fields = [field_entry["name"] for field_entry in index_data["Fields"]]
    uuid_idx = fields.index("page_uuid")
    title_idx = fields.index("page_title")
    type_idx = fields.index("page_type")
    cat_idx = fields.index("page_cat_name")

    posts = []
    for row in index_data["Values"]:
        page_uuid = row[uuid_idx]
        title = row[title_idx]
        page_type = row[type_idx]
        category = row[cat_idx]

        content_file = PAGES_DB_DIR / f"{page_uuid}.json"
        if not content_file.exists():
            continue

        with open(content_file, "r", encoding="utf-8") as content_fh:
            content_data = json.load(content_fh)

        c_fields = [f_entry["name"] for f_entry in content_data["Fields"]]
        body_idx = c_fields.index("html_body")

        html_body = None
        for c_row in content_data["Values"]:
            val = c_row[body_idx]
            if val and len(val.strip()) > 0:
                html_body = val
                break

        if html_body:
            posts.append({
                "page_uuid": page_uuid,
                "title": title,
                "type": page_type,
                "category": category,
                "html_body": html_body
            })

    return posts


def post_to_blogger(access_token: str, blog_id: str, title: str, html_content: str, labels: list, is_draft: bool = False) -> dict:
    url = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts?isDraft={'true' if is_draft else 'false'}"
    post_body = {
        "kind": "blogger#post",
        "title": title,
        "content": html_content,
        "labels": labels
    }
    payload = json.dumps(post_body).encode("utf-8")

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("Content-Type", "application/json; charset=utf-8")

    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    is_draft = "--draft" in sys.argv
    print(f"=================================================")
    print(f" BEJSON_CMS -> Google Blogger Batch Publisher")
    print(f" Mode: {'Draft' if is_draft else 'Live (Published)'}")
    print(f"=================================================")

    env_vars = load_secure_env()
    client_id = env_vars.get("BLOGGER_CLIENT_ID")
    client_secret = env_vars.get("BLOGGER_CLIENT_SECRET")
    blog_id = env_vars.get("BLOGGER_BLOG_ID")

    if not client_id or not client_secret or not blog_id:
        print("[!] Error: Missing required BLOGGER credentials in secureenv_file.json")
        sys.exit(1)

    posts = get_cms_posts()
    print(f"[+] Loaded {len(posts)} posts from BEJSON_CMS pages_db.")

    access_token = get_authorized_token(client_id, client_secret)
    existing_titles = get_existing_blog_titles(access_token, blog_id)
    print(f"[+] Found {len(existing_titles)} existing post(s) on blog to avoid duplicates.")

    for idx, post in enumerate(posts, start=1):
        if post["title"].strip() in existing_titles:
            print(f"\n[{idx}/{len(posts)}] Skipped (already published): '{post['title']}'")
            continue

        labels = [post["category"]] if post.get("category") else ["BEJSON"]
        print(f"\n[{idx}/{len(posts)}] Publishing: '{post['title']}'...")

        max_attempts = 5
        backoff_delay = 5
        for attempt in range(1, max_attempts + 1):
            try:
                result = post_to_blogger(
                    access_token=access_token,
                    blog_id=blog_id,
                    title=post["title"],
                    html_content=post["html_body"],
                    labels=labels,
                    is_draft=is_draft
                )
                print(f"    -> Success! Post URL: {result.get('url', 'N/A')} (ID: {result.get('id')})")
                existing_titles.add(post["title"].strip())
                time.sleep(3)  # Gentle spacing between API posts
                break
            except urllib.error.HTTPError as http_err:
                error_details = http_err.read().decode("utf-8", errors="ignore")
                if http_err.code == 429:
                    print(f"    -> [!] Rate limit hit (attempt {attempt}/{max_attempts}). Backing off for {backoff_delay}s...")
                    time.sleep(backoff_delay)
                    backoff_delay *= 2
                else:
                    print(f"    -> [!] HTTP Error {http_err.code}: {http_err.reason}\n       {error_details}")
                    break
            except Exception as general_err:
                print(f"    -> [!] Failed: {general_err}")
                break

    print("\n[+] All posts processed.")


if __name__ == "__main__":
    main()
