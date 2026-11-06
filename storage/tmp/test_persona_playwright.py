"""
test_persona_playwright.py
Automated Playwright test suite for BEJSON_CMS ProfileManager (Persona Hub / Editor).
Launches the server, verifies routes, captures desktop and mobile screenshots,
audits console errors and interactive DOM elements.
"""

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path("/storage/emulated/0/Admin/Dev/Repos/BEJSON_CMS")
sys.path.insert(0, str(PROJECT_ROOT / "src" / "lib"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "web"))

from termux_playwright import async_playwright_termux, launch

SCREENSHOT_DIR = PROJECT_ROOT / "images" / "audit_captures"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


async def main():
    print("=" * 60)
    print(" Playwright Test Suite: BEJSON_CMS Persona Hub / Editor")
    print("=" * 60)

    # 1. Start ProfileManager server on port 5004
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{PROJECT_ROOT}/src/lib:{PROJECT_ROOT}/src/web:{env.get('PYTHONPATH', '')}"
    server_proc = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "src" / "web" / "BEJSON_CMS_ProfileManager.py")],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    print("[*] Server process spawned (PID:", server_proc.pid, "). Waiting 3s for port 5004...")
    await asyncio.sleep(3)

    if server_proc.poll() is not None:
        stdout, stderr = server_proc.communicate()
        print("[!] Server failed to start!")
        print("STDOUT:", stdout.decode("utf-8", errors="replace"))
        print("STDERR:", stderr.decode("utf-8", errors="replace"))
        return 1

    console_logs = []
    page_errors = []

    try:
        async with async_playwright_termux() as p:
            browser = await launch(p, headless=True)

            # Setup authenticated desktop context
            context_desktop = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                http_credentials={"username": "admin", "password": "changeme"}
            )
            # Setup authenticated mobile context
            context_mobile = await browser.new_context(
                viewport={"width": 412, "height": 915},
                http_credentials={"username": "admin", "password": "changeme"},
                is_mobile=True
            )

            # --- Test 1: Desktop Persona Hub Home ---
            page_d = await context_desktop.new_page()
            page_d.on("console", lambda msg: console_logs.append(f"[Desktop Console {msg.type}] {msg.text}"))
            page_d.on("pageerror", lambda err: page_errors.append(f"[Desktop PageError] {err}"))

            print("[*] Navigating to http://localhost:5004/ (Desktop 1440x900)...")
            res_d = await page_d.goto("http://localhost:5004/", wait_until="networkidle")
            print(f"[*] Response Status: {res_d.status if res_d else 'None'}")
            title_d = await page_d.title()
            print(f"[*] Page Title: {title_d}")

            home_ss = SCREENSHOT_DIR / "persona_hub_desktop_initial.png"
            await page_d.screenshot(path=str(home_ss))
            print(f"[*] Saved screenshot: {home_ss}")

            # Inspect presence of key UI elements
            sidebar_items = await page_d.locator(".persona-card").count()
            print(f"[*] Found {sidebar_items} persona cards in sidebar.")

            tab_buttons = await page_d.locator(".tab-btn").count()
            print(f"[*] Found {tab_buttons} navigation tabs in editor.")

            # Test tab switching
            print("[*] Testing tab switching...")
            for tab_id in ["tab-identity", "tab-tones", "tab-model", "tab-tools", "tab-preview"]:
                tab_btn = page_d.locator(f"button[data-tab='{tab_id}']")
                if await tab_btn.count() > 0:
                    await tab_btn.click()
                    await asyncio.sleep(0.3)
                    pane_visible = await page_d.locator(f"#{tab_id}").is_visible()
                    print(f"    Tab '{tab_id}' switch: visible={pane_visible}")
                else:
                    print(f"    Tab '{tab_id}' button NOT found.")

            tab_test_ss = SCREENSHOT_DIR / "persona_hub_desktop_tab_preview.png"
            await page_d.screenshot(path=str(tab_test_ss))
            print(f"[*] Saved tab test screenshot: {tab_test_ss}")

            # --- Test 2: Mobile Viewport ---
            page_m = await context_mobile.new_page()
            page_m.on("console", lambda msg: console_logs.append(f"[Mobile Console {msg.type}] {msg.text}"))
            page_m.on("pageerror", lambda err: page_errors.append(f"[Mobile PageError] {err}"))

            print("[*] Navigating to http://localhost:5004/ (Mobile 412x915)...")
            res_m = await page_m.goto("http://localhost:5004/", wait_until="networkidle")
            print(f"[*] Response Status: {res_m.status if res_m else 'None'}")

            # Test mobile view toggling
            print("[*] Testing mobile view toggling (Catalog <-> Editor)...")
            btn_catalog = page_m.locator("#mobileTabList")
            btn_editor = page_m.locator("#mobileTabEditor")

            await btn_catalog.click()
            await asyncio.sleep(0.3)
            sidebar_visible = await page_m.locator("#sidebarContainer").is_visible()
            print(f"    Mobile Catalog view: sidebar visible={sidebar_visible}")
            mobile_catalog_ss = SCREENSHOT_DIR / "persona_hub_mobile_catalog.png"
            await page_m.screenshot(path=str(mobile_catalog_ss))

            await btn_editor.click()
            await asyncio.sleep(0.3)
            editor_visible = await page_m.locator("#editorContainer").is_visible()
            print(f"    Mobile Editor view: editor visible={editor_visible}")
            mobile_editor_ss = SCREENSHOT_DIR / "persona_hub_mobile_editor.png"
            await page_m.screenshot(path=str(mobile_editor_ss))

            # --- Test 3: API Endpoint ---
            print("[*] Testing API route /api/persona/boehnenelton2024...")
            api_res = await page_d.goto("http://localhost:5004/api/persona/boehnenelton2024")
            if api_res:
                api_json = await api_res.json()
                print(f"[*] API returned persona name: {api_json.get('Name')}")
                print(f"[*] Archetype: {api_json.get('Archetype')}")
                print(f"[*] Fields count: {len(api_json.keys())}")

            await browser.close()

        print("\n" + "=" * 60)
        print(" Playwright Audit Summary")
        print("=" * 60)
        print(f"[*] Console Log entries ({len(console_logs)}):")
        for log in console_logs[:10]:
            print("   ", log)
        print(f"[*] Page Errors ({len(page_errors)}):")
        for err in page_errors:
            print("   ", err)

        return 0

    finally:
        print("[*] Stopping ProfileManager server...")
        server_proc.terminate()
        try:
            server_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            server_proc.kill()
        print("[*] Server stopped cleanly.")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
