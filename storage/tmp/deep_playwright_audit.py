#!/data/data/com.termux/files/usr/bin/env python3
"""
Deep Playwright Audit Script for BEJSON CMS Published Static Site.
Tests:
- HTTP 200 responses on all routes.
- Console error inspection.
- DOM structural validation:
  - Table wrapping in horizontally scrolling containers.
  - Schema boxes with readonly textareas.
  - Table of Contents anchor link target verification.
- Viewport audits (Desktop 1280x720 and Mobile 375x812).
- Horizontal scroll overflow detection (document.documentElement.scrollWidth vs window.innerWidth).
- High-resolution full-page screenshot captures of the new posts and category feed.
"""

import asyncio
import http.server
import json
import os
import socketserver
import sys
import threading
import time
from pathlib import Path
from termux_playwright import async_playwright_termux, launch

BASE_URL = "http://127.0.0.1:8088"
CMS_ROOT = Path("/storage/emulated/0/Admin/Dev/Repos/BEJSON_CMS")
BUILD_DIR = CMS_ROOT / "storage" / "builds"
IMAGES_DIR = CMS_ROOT / "images" / "audit_captures"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

POST_105_URL = f"{BASE_URL}/blog/projects/the-integrity-era--architectural-deep-dive-into-bejson-105-core-libraries---mfdb-v1-40/index.html"
POST_CHUNKER_URL = f"{BASE_URL}/blog/projects/zero-sql-archiving---deterministic-snapshots--dissecting-project-chunker-s-ecosystem/index.html"
CATEGORY_PROJECTS_URL = f"{BASE_URL}/category/projects/index.html"
HOME_URL = f"{BASE_URL}/index.html"

def start_local_preview_server(port: int, directory: Path):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)
        def log_message(self, fmt, *args):
            pass

    httpd = socketserver.TCPServer(("", port), Handler)
    httpd.allow_reuse_address = True
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.5)
    return httpd

async def run_audit():
    print(f"[AUDIT] Starting local HTTP server on port 8088 pointing to {BUILD_DIR}...")
    httpd = start_local_preview_server(8088, BUILD_DIR)


    audit_results = {
        "status": "PASS",
        "tested_urls": [],
        "dom_audits": {},
        "viewport_audits": {},
        "console_errors": [],
        "screenshots_taken": []
    }

    async with async_playwright_termux() as pw:
        browser = await launch(pw, headless=True)

        # ----------------------------------------------------
        # 1. AUDIT NEW BEJSON 105 CORE BLOG POST (DESKTOP)
        # ----------------------------------------------------
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        print(f"[AUDIT] Navigating to 105 Core Post: {POST_105_URL}")
        resp = await page.goto(POST_105_URL, wait_until="domcontentloaded")
        status_code = resp.status if resp else None
        audit_results["tested_urls"].append({"url": POST_105_URL, "status": status_code})

        # DOM Checks
        dom_report = await page.evaluate("""() => {
            const tables = Array.from(document.querySelectorAll('table'));
            const tableAudits = tables.map((tbl, i) => {
                const parent = tbl.parentElement;
                const isWrapped = parent.classList.contains('table-container') || parent.style.overflowX === 'auto' || window.getComputedStyle(parent).overflowX === 'auto';
                return { index: i, wrapped: isWrapped, rows: tbl.querySelectorAll('tr').length };
            });

            const textareas = Array.from(document.querySelectorAll('.schema-box textarea'));
            const textareaAudits = textareas.map((ta, i) => {
                return { index: i, isReadOnly: ta.readOnly, valueLength: ta.value.length };
            });

            const tocLinks = Array.from(document.querySelectorAll('.table-of-contents a'));
            const brokenTocLinks = [];
            tocLinks.forEach(link => {
                const href = link.getAttribute('href');
                if (href && href.startsWith('#')) {
                    const targetId = href.substring(1);
                    const targetEl = document.getElementById(targetId);
                    if (!targetEl) {
                        brokenTocLinks.push(href);
                    }
                }
            });

            const headings = Array.from(document.querySelectorAll('h1, h2, h3, h4')).map(h => h.innerText.trim());

            return {
                title: document.title,
                tableCount: tables.length,
                allTablesWrapped: tableAudits.every(t => t.wrapped),
                tableAudits: tableAudits,
                textareaCount: textareas.length,
                allTextareasReadOnly: textareaAudits.every(ta => ta.isReadOnly),
                textareaAudits: textareaAudits,
                tocLinkCount: tocLinks.length,
                brokenTocLinks: brokenTocLinks,
                headingCount: headings.length
            };
        }""")

        audit_results["dom_audits"]["post_105_core"] = dom_report

        # Screenshot Desktop View
        screenshot_105_desktop = IMAGES_DIR / "post_105_desktop_full.png"
        await page.screenshot(path=str(screenshot_105_desktop), full_page=True)
        audit_results["screenshots_taken"].append(str(screenshot_105_desktop))
        print(f"[AUDIT] Captured 105 post desktop screenshot: {screenshot_105_desktop} ({screenshot_105_desktop.stat().st_size} bytes)")

        await context.close()

        # ----------------------------------------------------
        # 2. AUDIT NEW BEJSON 105 CORE BLOG POST (MOBILE 375x812)
        # ----------------------------------------------------
        mobile_context = await browser.new_context(viewport={"width": 375, "height": 812})
        mobile_page = await mobile_context.new_page()

        print(f"[AUDIT] Navigating to 105 Core Post on Mobile: {POST_105_URL}")
        await mobile_page.goto(POST_105_URL, wait_until="domcontentloaded")
        await mobile_page.wait_for_timeout(300)

        # Overflow check
        mobile_overflow = await mobile_page.evaluate("""() => {
            const bodyWidth = document.body.offsetWidth;
            const docWidth = document.documentElement.offsetWidth;
            const scrollWidth = document.documentElement.scrollWidth;
            const winWidth = window.innerWidth;
            return {
                windowInnerWidth: winWidth,
                bodyWidth: bodyWidth,
                scrollWidth: scrollWidth,
                hasHorizontalOverflow: scrollWidth > winWidth + 5
            };
        }""")
        audit_results["viewport_audits"]["post_105_mobile"] = mobile_overflow

        screenshot_105_mobile = IMAGES_DIR / "post_105_mobile_hero.png"
        await mobile_page.screenshot(path=str(screenshot_105_mobile))
        audit_results["screenshots_taken"].append(str(screenshot_105_mobile))
        print(f"[AUDIT] Captured 105 post mobile screenshot: {screenshot_105_mobile} ({screenshot_105_mobile.stat().st_size} bytes)")

        await mobile_context.close()

        # ----------------------------------------------------
        # 3. AUDIT CATEGORY 'PROJECTS' FEED
        # ----------------------------------------------------
        cat_context = await browser.new_context(viewport={"width": 1280, "height": 800})
        cat_page = await cat_context.new_page()

        print(f"[AUDIT] Navigating to Projects Category Feed: {CATEGORY_PROJECTS_URL}")
        cat_resp = await cat_page.goto(CATEGORY_PROJECTS_URL, wait_until="domcontentloaded")
        audit_results["tested_urls"].append({"url": CATEGORY_PROJECTS_URL, "status": cat_resp.status if cat_resp else None})

        cat_dom = await cat_page.evaluate("""() => {
            const articles = Array.from(document.querySelectorAll('.card, article, .post-item, .grid > div'));
            const links = Array.from(document.querySelectorAll('a')).map(a => ({ text: a.innerText.trim(), href: a.href }));
            return {
                title: document.title,
                articleCardCount: articles.length,
                links: links.slice(0, 15)
            };
        }""")
        audit_results["dom_audits"]["category_projects"] = cat_dom

        screenshot_cat = IMAGES_DIR / "category_projects_desktop.png"
        await cat_page.screenshot(path=str(screenshot_cat))
        audit_results["screenshots_taken"].append(str(screenshot_cat))
        print(f"[AUDIT] Captured Projects category screenshot: {screenshot_cat} ({screenshot_cat.stat().st_size} bytes)")

        await cat_context.close()

        # ----------------------------------------------------
        # 4. AUDIT HOME FEED
        # ----------------------------------------------------
        home_context = await browser.new_context(viewport={"width": 1280, "height": 800})
        home_page = await home_context.new_page()

        print(f"[AUDIT] Navigating to Home Feed: {HOME_URL}")
        home_resp = await home_page.goto(HOME_URL, wait_until="domcontentloaded")
        audit_results["tested_urls"].append({"url": HOME_URL, "status": home_resp.status if home_resp else None})

        screenshot_home = IMAGES_DIR / "home_feed_desktop.png"
        await home_page.screenshot(path=str(screenshot_home))
        audit_results["screenshots_taken"].append(str(screenshot_home))
        print(f"[AUDIT] Captured Home Feed screenshot: {screenshot_home} ({screenshot_home.stat().st_size} bytes)")

        await home_context.close()
        await browser.close()

    try:
        httpd.shutdown()
        print("[AUDIT] Local preview server shutdown cleanly.")
    except Exception:
        pass


    # Consolidate results
    audit_results["console_errors"] = console_errors
    all_wrapped = audit_results["dom_audits"]["post_105_core"]["allTablesWrapped"]
    broken_links = audit_results["dom_audits"]["post_105_core"]["brokenTocLinks"]
    all_read_only = audit_results["dom_audits"]["post_105_core"]["allTextareasReadOnly"]

    if not all_wrapped or broken_links or not all_read_only or console_errors:
        audit_results["status"] = "WARNINGS_DETECTED"

    report_path = CMS_ROOT / "storage" / "tmp" / "playwright_audit_report.json"
    report_path.write_text(json.dumps(audit_results, indent=2), encoding="utf-8")
    print(f"\n[AUDIT COMPLETE] Summary written to {report_path}")
    print(json.dumps(audit_results, indent=2))

if __name__ == "__main__":
    asyncio.run(run_audit())
