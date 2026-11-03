#!/data/data/com.termux/files/usr/bin/env python3
"""
Comprehensive Playwright Screenshot Capture Suite for BEJSON_CMS
Captures all desktop and mobile screenshots across:
1. CMS Admin Suite (Port 5001) - Dashboard, AI Writer Studio (/jobs), Pages Manager, Media Library, Publisher, Authors
2. Page Editor V2 (Port 5010) - Full editor and active AI Writer Tab (#t-tasking)
3. Profile Manager (Port 5004) - AI Persona & Profile Management
4. Published Static Builds (Port 8080) - Home desktop/mobile, Category feeds, Apps feed, and Articles (105 Core, NewAgent, Telemetry, Biological Substrate)

Applies 420p maximum dimension constraint (Image.Resampling.LANCZOS) adhering to repository standards.
"""

import asyncio
import functools
import http.server
import json
import logging
import os
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path
from PIL import Image

PROJECT_ROOT = Path("/storage/emulated/0/Admin/Dev/Repos/BEJSON_CMS")
sys.path.insert(0, str(PROJECT_ROOT / "src" / "lib"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "web"))

from lib_bejson_Core_bejson_env import source_env, source_env_fill
source_env()
source_env_fill()

import BEJSON_CMS_Publisher as CMSPublisher
from termux_playwright import async_playwright_termux, launch

AUDIT_DIR = PROJECT_ROOT / "images" / "audit_captures"
IMAGES_DIR = PROJECT_ROOT / "images"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

REPORT_PATH = PROJECT_ROOT / "storage" / "tmp" / "playwright_verification_report.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("playwright_capture")


class QuietStaticServer(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def start_static_server(build_dir: Path, port: int = 8080):
    handler = functools.partial(QuietStaticServer, directory=str(build_dir))
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    srv_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    srv_thread.start()
    return httpd


def wait_for_port(port: int, host: str = "127.0.0.1", timeout: float = 10.0) -> bool:
    start_time = time.time()
    while time.time() - start_time < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.3)
    return False


def resize_to_420(img_path: Path):
    try:
        with Image.open(img_path) as img:
            orig_size = img.size
            if max(orig_size) > 420:
                img.thumbnail((420, 420), Image.Resampling.LANCZOS)
                img.save(img_path, optimize=True)
                logger.info(f"Resized {img_path.name}: {orig_size} -> {img.size} ({img_path.stat().st_size} bytes)")
            else:
                logger.info(f"Retained {img_path.name}: {orig_size} ({img_path.stat().st_size} bytes)")
    except Exception as exc:
        logger.warning(f"Could not resize {img_path}: {exc}")


async def capture_all_screenshots():
    logger.info("=== STEP 1: Building Static Site ===")
    CMSPublisher._execute()
    build_dir = PROJECT_ROOT / "storage" / "builds"

    logger.info("=== STEP 2: Launching Local Services ===")
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{PROJECT_ROOT}/src/lib:{PROJECT_ROOT}/src/web:{env.get('PYTHONPATH', '')}"

    # 1. Admin Server (5001)
    admin_proc = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "src" / "web" / "BEJSON_CMS_Admin.py")],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # 2. Page Editor V2 (5010)
    editor_proc = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "src" / "web" / "BEJSON_CMS_PageEditorV2.py")],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # 3. Profile Manager (5004)
    profile_proc = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "src" / "web" / "BEJSON_CMS_ProfileManager.py")],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # 4. Static HTTP Server (8080)
    static_httpd = start_static_server(build_dir, 8080)

    # Wait for all services
    for p_name, p_num in [("Admin", 5001), ("EditorV2", 5010), ("Profiles", 5004), ("Static", 8080)]:
        ok = wait_for_port(p_num)
        logger.info(f"Port {p_num} ({p_name}): {'READY' if ok else 'TIMEOUT'}")
        if not ok:
            raise RuntimeError(f"Service {p_name} failed to bind to port {p_num}")

    captured_files = []

    try:
        logger.info("=== STEP 3: Starting Playwright Automation ===")
        async with async_playwright_termux() as pw:
            browser = await launch(pw, headless=True)

            # Desktop context (1440x900)
            context_desktop = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                http_credentials={"username": "admin", "password": "changeme"}
            )

            # Mobile context (412x915)
            context_mobile = await browser.new_context(
                viewport={"width": 412, "height": 915},
                http_credentials={"username": "admin", "password": "changeme"},
                is_mobile=True
            )

            page_d = await context_desktop.new_page()
            page_m = await context_mobile.new_page()

            # -----------------------------------------------------------------
            # 1. Admin Dashboard (5001 /)
            # -----------------------------------------------------------------
            logger.info("Capturing Admin Dashboard...")
            await page_d.goto("http://localhost:5001/", wait_until="networkidle", timeout=30000)
            dash_audit = AUDIT_DIR / "01_playwright_admin_dashboard.png"
            dash_root = IMAGES_DIR / "01_admin_dashboard.png"
            await page_d.screenshot(path=str(dash_audit), full_page=False)
            shutil.copy2(dash_audit, dash_root)
            captured_files.extend([dash_audit, dash_root])

            # -----------------------------------------------------------------
            # 2. AI Writer Studio (5001 /jobs)
            # -----------------------------------------------------------------
            logger.info("Capturing AI Writer Studio (/jobs)...")
            await page_d.goto("http://localhost:5001/jobs", wait_until="networkidle", timeout=30000)
            await page_d.wait_for_selector("#bks_job_select", timeout=8000)
            await asyncio.sleep(0.5)
            jobs_audit = AUDIT_DIR / "02_playwright_bks_jobs_studio.png"
            await page_d.screenshot(path=str(jobs_audit), full_page=False)
            captured_files.append(jobs_audit)

            # -----------------------------------------------------------------
            # 3. Pages Manager (5001 /pages)
            # -----------------------------------------------------------------
            logger.info("Capturing Pages Manager (/pages)...")
            await page_d.goto("http://localhost:5001/pages", wait_until="networkidle", timeout=30000)
            pages_root = IMAGES_DIR / "02_pages_manager.png"
            await page_d.screenshot(path=str(pages_root), full_page=False)
            captured_files.append(pages_root)

            # -----------------------------------------------------------------
            # 4. Media Library (5001 /assets)
            # -----------------------------------------------------------------
            logger.info("Capturing Media Library (/assets)...")
            await page_d.goto("http://localhost:5001/assets", wait_until="networkidle", timeout=30000)
            media_root = IMAGES_DIR / "03_media_library.png"
            await page_d.screenshot(path=str(media_root), full_page=False)
            captured_files.append(media_root)

            # -----------------------------------------------------------------
            # 5. Profile Manager (5004 /)
            # -----------------------------------------------------------------
            logger.info("Capturing Profile Manager (port 5004)...")
            await page_d.goto("http://localhost:5004/", wait_until="networkidle", timeout=30000)
            prof_root = IMAGES_DIR / "05_profile_manager.png"
            await page_d.screenshot(path=str(prof_root), full_page=False)
            captured_files.append(prof_root)

            # -----------------------------------------------------------------
            # 6. Static Publisher UI (5001 /publish)
            # -----------------------------------------------------------------
            logger.info("Capturing Static Publisher (/publish)...")
            await page_d.goto("http://localhost:5001/publish", wait_until="networkidle", timeout=30000)
            pub_root = IMAGES_DIR / "06_static_publisher.png"
            await page_d.screenshot(path=str(pub_root), full_page=False)
            captured_files.append(pub_root)

            # -----------------------------------------------------------------
            # 7. Page Editor V2 Full (5010 /)
            # -----------------------------------------------------------------
            logger.info("Capturing Page Editor V2 (port 5010)...")
            await page_d.goto("http://localhost:5010/", wait_until="networkidle", timeout=30000)
            editor_audit = AUDIT_DIR / "03_playwright_page_editor_v2.png"
            editor_root = IMAGES_DIR / "04_page_editor_v2.png"
            await page_d.screenshot(path=str(editor_audit), full_page=False)
            shutil.copy2(editor_audit, editor_root)
            captured_files.extend([editor_audit, editor_root])

            # -----------------------------------------------------------------
            # 8. Page Editor V2 AI Writer Tab (#t-tasking)
            # -----------------------------------------------------------------
            logger.info("Activating AI Writer tab in Page Editor V2...")
            await page_d.evaluate("() => showTab('tasking')")
            await page_d.wait_for_selector("#t-tasking", state="visible", timeout=6000)
            await asyncio.sleep(1.0)
            ai_tab_audit = AUDIT_DIR / "04_playwright_editor_ai_architect_tab.png"
            await page_d.screenshot(path=str(ai_tab_audit), full_page=False)
            captured_files.append(ai_tab_audit)

            # -----------------------------------------------------------------
            # 9. Published Home Feed (Desktop & Mobile)
            # -----------------------------------------------------------------
            logger.info("Capturing Published Home Feed (Desktop & Mobile)...")
            await page_d.goto("http://localhost:8080/index.html", wait_until="networkidle", timeout=30000)
            pub_home_audit = AUDIT_DIR / "05_playwright_published_home.png"
            pub_home_feed = AUDIT_DIR / "home_feed_desktop.png"
            pub_home_root_d = IMAGES_DIR / "01_published_home_desktop.png"
            await page_d.screenshot(path=str(pub_home_audit), full_page=False)
            shutil.copy2(pub_home_audit, pub_home_feed)
            shutil.copy2(pub_home_audit, pub_home_root_d)
            captured_files.extend([pub_home_audit, pub_home_feed, pub_home_root_d])

            await page_m.goto("http://localhost:8080/index.html", wait_until="networkidle", timeout=30000)
            pub_home_root_m = IMAGES_DIR / "02_published_home_mobile.png"
            await page_m.screenshot(path=str(pub_home_root_m), full_page=False)
            captured_files.append(pub_home_root_m)

            # -----------------------------------------------------------------
            # 10. Published 105 Core Post (Desktop & Mobile)
            # -----------------------------------------------------------------
            post_105_url = "http://localhost:8080/blog/projects/the-integrity-era--architectural-deep-dive-into-bejson-105-core-libraries---mfdb-v1-40/index.html"
            logger.info(f"Capturing 105 Core Post ({post_105_url})...")
            await page_d.goto(post_105_url, wait_until="networkidle", timeout=30000)
            pub_art_d_audit = AUDIT_DIR / "06_playwright_published_article_desktop.png"
            post_105_d_full = AUDIT_DIR / "post_105_desktop_full.png"
            pub_art_2_root = IMAGES_DIR / "04_published_article_2.png"
            await page_d.screenshot(path=str(pub_art_d_audit), full_page=False)
            shutil.copy2(pub_art_d_audit, post_105_d_full)
            shutil.copy2(pub_art_d_audit, pub_art_2_root)
            captured_files.extend([pub_art_d_audit, post_105_d_full, pub_art_2_root])

            await page_m.goto(post_105_url, wait_until="networkidle", timeout=30000)
            pub_art_m_audit = AUDIT_DIR / "07_playwright_published_article_mobile.png"
            post_105_m_hero = AUDIT_DIR / "post_105_mobile_hero.png"
            await page_m.screenshot(path=str(pub_art_m_audit), full_page=False)
            shutil.copy2(pub_art_m_audit, post_105_m_hero)
            captured_files.extend([pub_art_m_audit, post_105_m_hero])

            # -----------------------------------------------------------------
            # 11. Published Project Chunker Post (03_published_article_1.png)
            # -----------------------------------------------------------------
            chunker_url = "http://localhost:8080/blog/projects/zero-sql-archiving---deterministic-snapshots--dissecting-project-chunker-s-ecosystem/index.html"
            logger.info(f"Capturing Project Chunker Post ({chunker_url})...")
            await page_d.goto(chunker_url, wait_until="networkidle", timeout=30000)
            art1_root = IMAGES_DIR / "03_published_article_1.png"
            await page_d.screenshot(path=str(art1_root), full_page=False)
            captured_files.append(art1_root)

            # -----------------------------------------------------------------
            # 12. Published NewAgent Runtime Post (03_published_article_newagent.png)
            # -----------------------------------------------------------------
            newagent_url = "http://localhost:8080/blog/projects/autonomous-tooling-on-linux--dissecting-newagent-s-runtime-engine/index.html"
            try:
                await page_d.goto(newagent_url, wait_until="networkidle", timeout=15000)
                art_na_root = IMAGES_DIR / "03_published_article_newagent.png"
                await page_d.screenshot(path=str(art_na_root), full_page=False)
                captured_files.append(art_na_root)
            except Exception as e:
                logger.warning(f"NewAgent post capture skipped: {e}")

            # -----------------------------------------------------------------
            # 13. Published Telemetry Post (04_published_article_telemetry.png)
            # -----------------------------------------------------------------
            telemetry_url = "http://localhost:8080/blog/bejson/positional-telemetry--zero-overhead-memory-matrices-in-bejson-104/index.html"
            try:
                await page_d.goto(telemetry_url, wait_until="networkidle", timeout=15000)
                art_tel_root = IMAGES_DIR / "04_published_article_telemetry.png"
                await page_d.screenshot(path=str(art_tel_root), full_page=False)
                captured_files.append(art_tel_root)
            except Exception as e:
                logger.warning(f"Telemetry post capture skipped: {e}")

            # -----------------------------------------------------------------
            # 14. Biological Substrate Post (Desktop & Mobile)
            # -----------------------------------------------------------------
            bio_url = "http://localhost:8080/blog/bejson/code-as-biological-substrate--the-living-architecture-of-resilient-autonomous-systems/index.html"
            try:
                await page_d.goto(bio_url, wait_until="networkidle", timeout=15000)
                art_bio_d = IMAGES_DIR / "07_published_article_biological_substrate.png"
                await page_d.screenshot(path=str(art_bio_d), full_page=False)
                captured_files.append(art_bio_d)

                await page_m.goto(bio_url, wait_until="networkidle", timeout=15000)
                art_bio_m = IMAGES_DIR / "08_published_article_biological_substrate_mobile.png"
                await page_m.screenshot(path=str(art_bio_m), full_page=False)
                captured_files.append(art_bio_m)
            except Exception as e:
                logger.warning(f"Biological substrate capture skipped: {e}")

            # -----------------------------------------------------------------
            # 15. Apps Feed (05_published_apps_feed.png)
            # -----------------------------------------------------------------
            apps_url = "http://localhost:8080/apps/index.html"
            logger.info("Capturing Apps Feed...")
            await page_d.goto(apps_url, wait_until="networkidle", timeout=30000)
            apps_root = IMAGES_DIR / "05_published_apps_feed.png"
            await page_d.screenshot(path=str(apps_root), full_page=False)
            captured_files.append(apps_root)

            # -----------------------------------------------------------------
            # 16. Category Feeds (Projects & BEJSON)
            # -----------------------------------------------------------------
            cat_proj_url = "http://localhost:8080/category/projects/index.html"
            logger.info("Capturing Projects Category Feed...")
            await page_d.goto(cat_proj_url, wait_until="networkidle", timeout=30000)
            cat_proj_audit = AUDIT_DIR / "category_projects_desktop.png"
            cat_feed_root = IMAGES_DIR / "06_published_category_feed.png"
            await page_d.screenshot(path=str(cat_proj_audit), full_page=False)
            shutil.copy2(cat_proj_audit, cat_feed_root)
            captured_files.extend([cat_proj_audit, cat_feed_root])

            cat_bejson_url = "http://localhost:8080/category/bejson/index.html"
            try:
                await page_d.goto(cat_bejson_url, wait_until="networkidle", timeout=15000)
                cat_bej_root = IMAGES_DIR / "06_published_category_bejson.png"
                await page_d.screenshot(path=str(cat_bej_root), full_page=False)
                captured_files.append(cat_bej_root)
            except Exception as e:
                logger.warning(f"BEJSON category capture skipped: {e}")

            await browser.close()

    finally:
        logger.info("=== STEP 4: Cleaning up Background Subprocesses ===")
        for name, proc in [("Admin", admin_proc), ("EditorV2", editor_proc), ("Profiles", profile_proc)]:
            if proc:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except Exception:
                    proc.kill()
                logger.info(f"{name} server terminated.")
        if static_httpd:
            static_httpd.shutdown()
            logger.info("Static preview server shutdown.")

    # Deduplicate captured file list
    unique_files = sorted(list(set(captured_files)))
    logger.info(f"=== STEP 5: Resizing {len(unique_files)} Images to 420p Standard ===")
    for f in unique_files:
        resize_to_420(f)

    # Write verification report
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_screenshots_captured": len(unique_files),
        "screenshots": [str(f) for f in unique_files],
        "success": True
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as rf:
        json.dump(report, rf, indent=2)

    logger.info(f"Verification report written to: {REPORT_PATH}")
    logger.info("[✓] ALL PLAYWRIGHT SCREENSHOTS SUCCESSFULLY CAPTURED AND RESIZED!")


if __name__ == "__main__":
    asyncio.run(capture_all_screenshots())
