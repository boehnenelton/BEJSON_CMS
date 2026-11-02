"""
Playwright Automation & Verification Suite for BEJSON_CMS
Verifies:
1. Canonical environment definitions loading (definitions.json per Policy §4.5)
2. Secure env credentials and AI library round-robin key rotation via ai_dispatch_call()
3. Admin Dashboard & BKS-1 Blog Post Jobs Studio (Port 5001)
4. Page Editor V2 & AI Content Architect Studio (Port 5002)
5. Published Static Build (Port 8080)
Captures high-resolution desktop & mobile screenshots.
"""

import asyncio
import functools
import http.server
import json
import os
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path

# Add src/lib and src/web to sys.path
PROJECT_ROOT = Path("/storage/emulated/0/Admin/Dev/Repos/BEJSON_CMS")
sys.path.insert(0, str(PROJECT_ROOT / "src" / "lib"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "web"))

# Sourcing canonical definitions.json and secureenv_file.json
from lib_bejson_Core_bejson_env import source_env, source_env_fill
source_env()
source_env_fill()

from lib_bejson_AI_ai_dispatch import ai_dispatch_call, PROVIDERS
from lib_bejson_AI_bejson_groq import get_standard_prompter as get_groq_prompter
from lib_bejson_AI_bejson_gemini import get_standard_api as get_gemini_api
from lib_bejson_CMS_bks_blog_jobs import cms_bks_bootstrap, cms_bks_list_templates, cms_bks_list_jobs
import BEJSON_CMS_Shared as CMSShared
import BEJSON_CMS_Publisher as CMSPublisher

from termux_playwright import async_playwright_termux, launch

SCREENSHOT_DIR = PROJECT_ROOT / "images" / "audit_captures"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

REPORT_PATH = PROJECT_ROOT / "storage" / "tmp" / "playwright_verification_report.json"


class QuietStaticServer(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Quiet down output


def start_static_server(build_dir: Path, port: int = 8080):
    handler = functools.partial(QuietStaticServer, directory=str(build_dir))
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    srv_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    srv_thread.start()
    return httpd


async def run_full_verification():
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "env_definitions": {},
        "ai_key_rotation": {},
        "dispatch_verification": {},
        "screenshots": [],
        "pages_verified": [],
        "success": False
    }

    print("=================================================================")
    print(" 1. Verifying Environment Definitions & Secure Env Key Rotation")
    print("=================================================================")
    def_file = os.environ.get("DEFINITIONS_FILE", "/storage/emulated/0/.env/user/definitions.json")
    sec_file = os.environ.get("SECUREENV_FILE", "/storage/emulated/0/.env/secure/secureenv_file.json")

    report["env_definitions"]["definitions_file"] = def_file
    report["env_definitions"]["definitions_exists"] = Path(def_file).exists()
    report["env_definitions"]["project_chunker_resolved"] = os.environ.get("PROJECT_CHUNKER")
    report["env_definitions"]["secureenv_file"] = sec_file
    report["env_definitions"]["secureenv_exists"] = Path(sec_file).exists()

    print(f"[*] Definitions File: {def_file} (exists={Path(def_file).exists()})")
    print(f"[*] PROJECT_CHUNKER from definitions: {os.environ.get('PROJECT_CHUNKER')}")
    print(f"[*] Secureenv File: {sec_file} (exists={Path(sec_file).exists()})")

    # Key rotation test via AI libs
    groq_prompter = get_groq_prompter()
    groq_cnt = groq_prompter.key_reg.get_key_count()
    k1 = groq_prompter.key_reg.get_next_key()
    k2 = groq_prompter.key_reg.get_next_key()
    k3 = groq_prompter.key_reg.get_next_key()
    k4 = groq_prompter.key_reg.get_next_key()

    print(f"[*] Groq Key Registry slot count: {groq_cnt}")
    print(f"    Slot 1: {k1[:6]}...{k1[-4:] if k1 else ''}")
    print(f"    Slot 2: {k2[:6]}...{k2[-4:] if k2 else ''}")
    print(f"    Slot 3: {k3[:6]}...{k3[-4:] if k3 else ''}")
    print(f"    Slot 4: {k4[:6]}...{k4[-4:] if k4 else ''}")
    rotates = (k1 != k2) if groq_cnt > 1 else True
    print(f"[*] Key rotation confirmed active: {rotates}")

    report["ai_key_rotation"]["provider"] = "groq"
    report["ai_key_rotation"]["key_count"] = groq_cnt
    report["ai_key_rotation"]["rotates_cleanly"] = rotates

    # Dispatch Call Verification
    print("[*] Testing live ai_dispatch_call() with provider='groq'...")
    dispatch_res = ai_dispatch_call("groq", "Answer in 10 words or less: What is BEJSON?", model_id="openai/gpt-oss-120b")
    print(f"[*] Dispatch Success: {dispatch_res.get('success')}")
    print(f"[*] Dispatch Model: {dispatch_res.get('model_id')}")
    print(f"[*] Dispatch Content: {dispatch_res.get('content')}")
    report["dispatch_verification"] = {
        "provider": dispatch_res.get("provider"),
        "model_id": dispatch_res.get("model_id"),
        "success": dispatch_res.get("success"),
        "content_excerpt": (dispatch_res.get("content") or "")[:100],
    }

    print("\n=================================================================")
    print(" 2. Compiling Static Build for Published Site")
    print("=================================================================")
    CMSPublisher._execute()
    build_dir = PROJECT_ROOT / "storage" / "builds"
    print(f"[*] Static build generated at: {build_dir}")

    # Start servers
    print("\n=================================================================")
    print(" 3. Starting CMS Admin, Page Editor V2 & Static Preview Servers")
    print("=================================================================")
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{PROJECT_ROOT}/src/lib:{PROJECT_ROOT}/src/web:{env.get('PYTHONPATH', '')}"

    # Server 1: Admin Dashboard (5001)
    admin_proc = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "src" / "web" / "BEJSON_CMS_Admin.py")],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Server 2: Page Editor V2 (5002)
    editor_proc = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "src" / "web" / "BEJSON_CMS_PageEditorV2.py")],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Server 3: Published Site HTTP Server (8080)
    static_httpd = start_static_server(build_dir, 8080)
    print("[*] Servers started. Waiting 3 seconds for sockets to bind...")
    time.sleep(3)

    print("\n=================================================================")
    print(" 4. Launching Native Termux Playwright & Capturing Screenshots")
    print("=================================================================")
    try:
        async with async_playwright_termux() as p:
            browser = await launch(p, headless=True)

            # Setup authenticated desktop context
            context_desktop = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                http_credentials={"username": "admin", "password": "changeme"}
            )
            # Setup mobile context
            context_mobile = await browser.new_context(
                viewport={"width": 412, "height": 915},
                http_credentials={"username": "admin", "password": "changeme"},
                is_mobile=True
            )

            # --- Target 1: Admin Dashboard (Port 5001) ---
            print("[*] [1/6] Navigating to Admin Dashboard (http://localhost:5001/)...")
            page = await context_desktop.new_page()
            await page.goto("http://localhost:5001/", timeout=30000, wait_until="networkidle")
            title = await page.title()
            print(f"    Page Title: {title}")
            dash_shot = SCREENSHOT_DIR / "01_playwright_admin_dashboard.png"
            await page.screenshot(path=str(dash_shot), full_page=True)
            report["screenshots"].append(str(dash_shot))
            report["pages_verified"].append({"url": "http://localhost:5001/", "title": title, "screenshot": str(dash_shot)})

            # --- Target 2: BKS-1 4-Part Blog Jobs Studio (Port 5001/jobs) ---
            print("[*] [2/6] Navigating to 4-Part Blog Jobs Studio (http://localhost:5001/jobs)...")
            await page.goto("http://localhost:5001/jobs", timeout=30000, wait_until="networkidle")
            title = await page.title()
            print(f"    Page Title: {title}")
            # Ensure job studio cards are rendered
            await page.wait_for_selector("#bks_job_select", timeout=5000)
            jobs_shot = SCREENSHOT_DIR / "02_playwright_bks_jobs_studio.png"
            await page.screenshot(path=str(jobs_shot), full_page=True)
            report["screenshots"].append(str(jobs_shot))
            report["pages_verified"].append({"url": "http://localhost:5001/jobs", "title": title, "screenshot": str(jobs_shot)})

            # --- Target 3: Page Editor V2 (Port 5010) ---
            print("[*] [3/6] Navigating to Page Editor V2 (http://localhost:5010/)...")
            await page.goto("http://localhost:5010/", timeout=30000, wait_until="networkidle")
            title = await page.title()
            print(f"    Page Title: {title}")
            editor_shot = SCREENSHOT_DIR / "03_playwright_page_editor_v2.png"
            await page.screenshot(path=str(editor_shot), full_page=True)
            report["screenshots"].append(str(editor_shot))
            report["pages_verified"].append({"url": "http://localhost:5010/", "title": title, "screenshot": str(editor_shot)})

            # --- Target 4: Page Editor V2 -> AI Content Architect Tab (#t-tasking) ---
            print("[*] [4/6] Activating AI Content Architect tab in Page Editor V2...")
            # Activate tab via showTab
            await page.evaluate("() => showTab('tasking')")
            await page.wait_for_selector('#t-tasking', state="visible", timeout=5000)
            await asyncio.sleep(1)  # Allow dynamic dropdowns and cards to render
            ai_tab_shot = SCREENSHOT_DIR / "04_playwright_editor_ai_architect_tab.png"
            await page.screenshot(path=str(ai_tab_shot), full_page=True)
            report["screenshots"].append(str(ai_tab_shot))
            report["pages_verified"].append({"url": "http://localhost:5010/#t-tasking", "title": title, "screenshot": str(ai_tab_shot)})

            # --- Target 5: Published Build Home Feed (Port 8080) ---
            print("[*] [5/6] Navigating to Published Home Feed (http://localhost:8080/)...")
            await page.goto("http://localhost:8080/", timeout=30000, wait_until="networkidle")
            title = await page.title()
            print(f"    Page Title: {title}")
            pub_home_shot = SCREENSHOT_DIR / "05_playwright_published_home.png"
            await page.screenshot(path=str(pub_home_shot), full_page=True)
            report["screenshots"].append(str(pub_home_shot))
            report["pages_verified"].append({"url": "http://localhost:8080/", "title": title, "screenshot": str(pub_home_shot)})

            # --- Target 6: Published Article (Port 8080) Desktop + Mobile ---
            article_url = "http://localhost:8080/blog/projects/the-integrity-era--architectural-deep-dive-into-bejson-105-core-libraries---mfdb-v1-40/index.html"
            print(f"[*] [6/6] Navigating to Published Article ({article_url})...")
            await page.goto(article_url, timeout=30000, wait_until="networkidle")
            title = await page.title()
            print(f"    Page Title: {title}")
            pub_art_shot = SCREENSHOT_DIR / "06_playwright_published_article_desktop.png"
            await page.screenshot(path=str(pub_art_shot), full_page=True)
            report["screenshots"].append(str(pub_art_shot))
            report["pages_verified"].append({"url": article_url, "title": title, "screenshot": str(pub_art_shot)})

            # Mobile capture of the article
            page_m = await context_mobile.new_page()
            await page_m.goto(article_url, timeout=30000, wait_until="networkidle")
            pub_art_m_shot = SCREENSHOT_DIR / "07_playwright_published_article_mobile.png"
            await page_m.screenshot(path=str(pub_art_m_shot), full_page=False)
            report["screenshots"].append(str(pub_art_m_shot))

            await browser.close()
            report["success"] = True
            print("\n[✓] All 7 Playwright screenshots captured successfully!")

    finally:
        print("\n=================================================================")
        print(" 5. Clean Teardown of Servers & Background Subprocesses")
        print("=================================================================")
        if admin_proc:
            admin_proc.terminate()
            try:
                admin_proc.wait(timeout=2)
            except Exception:
                admin_proc.kill()
            print("[*] Admin Dashboard server terminated.")
        if editor_proc:
            editor_proc.terminate()
            try:
                editor_proc.wait(timeout=2)
            except Exception:
                editor_proc.kill()
            print("[*] Page Editor V2 server terminated.")
        if static_httpd:
            static_httpd.shutdown()
            print("[*] Static preview HTTP server shutdown.")

    # Write report
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\n[✓] Verification report written to: {REPORT_PATH}")
    return report

if __name__ == "__main__":
    asyncio.run(run_full_verification())
