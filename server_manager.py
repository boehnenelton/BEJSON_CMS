#!/usr/bin/env python3
"""
Name:           server_manager.py
Description:    Asynchronous server lifecycle manager for BEJSON CMS static build preview
                and Flask publisher service with automated Termux clipboard copy and
                Android Chrome browser dispatch per System Invariants.
Version:        100
Date Created:   2026-11-12
Author Credit:  Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
RELATIONAL_ID:  a3c8e104-9d52-4731-bf8a-2e4a6d1b8c9e
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
BUILDS_DIR = PROJECT_ROOT / "storage" / "builds"
LOGS_DIR = PROJECT_ROOT / "storage" / "tmp" / "logs"
PID_DIR = PROJECT_ROOT / "storage" / "tmp"

PREVIEW_PID_FILE = PID_DIR / ".preview_server.pid"
PREVIEW_LOG_FILE = LOGS_DIR / "preview_server.log"

PUBLISHER_PID_FILE = PID_DIR / ".publisher_server.pid"
PUBLISHER_LOG_FILE = LOGS_DIR / "publisher_server.log"

PREVIEW_PORT_DEFAULT = 8000
PUBLISHER_PORT_DEFAULT = 5001


def is_pid_alive(pid: int) -> bool:
    """Check if process with PID is currently alive."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def get_pid_from_file(pid_path: Path) -> int:
    """Read PID integer from file if present and valid."""
    if not pid_path.exists():
        return 0
    try:
        pid_text = pid_path.read_text(encoding="utf-8").strip()
        return int(pid_text) if pid_text.isdigit() else 0
    except Exception:
        return 0


def copy_to_clipboard(url: str):
    """Copy URL to Termux clipboard via termux-clipboard-set if available."""
    try:
        proc = subprocess.run(["termux-clipboard-set"], input=url, text=True, capture_output=True, timeout=3)
        if proc.returncode == 0:
            print(f"[✓] Copied {url} to Termux clipboard.")
    except Exception:
        pass


def open_browser(url: str):
    """Launch Google Chrome as mandatory primary browser via Android Activity Manager."""
    print(f"[*] Opening browser to {url}...")
    # 1. Primary: Chrome via Activity Manager
    try:
        am_cmd = ["am", "start", "-n", "com.android.chrome/com.google.android.apps.chrome.Main", "-d", url]
        res = subprocess.run(am_cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            print("[✓] Dispatched Google Chrome via Android Activity Manager.")
            return True
    except Exception:
        pass

    # 2. Secondary fallback: termux-open-url
    for fallback_tool in ("termux-open-url", "termux-open", "xdg-open"):
        try:
            res = subprocess.run([fallback_tool, url], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                print(f"[✓] Dispatched browser via {fallback_tool}.")
                return True
        except Exception:
            continue

    print(f"[!] Could not launch browser automatically. Please open: {url}")
    return False


def run_build() -> bool:
    """Execute static site build via BEJSON_CMS_Publisher."""
    print("[*] Running static site build...")
    manage_py = PROJECT_ROOT / "src" / "cms-manage.py"
    res = subprocess.run([sys.executable, str(manage_py), "publish"], cwd=str(PROJECT_ROOT), capture_output=False)
    return res.returncode == 0


def start_preview_server(port: int = PREVIEW_PORT_DEFAULT) -> bool:
    """Start Python HTTP server serving storage/builds in the background."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    PID_DIR.mkdir(parents=True, exist_ok=True)

    existing_pid = get_pid_from_file(PREVIEW_PID_FILE)
    if existing_pid and is_pid_alive(existing_pid):
        print(f"[i] Preview server already running on port {port} (PID: {existing_pid}).")
        return True

    if not BUILDS_DIR.exists() or not (BUILDS_DIR / "index.html").exists():
        print("[!] Builds directory empty. Building first...")
        run_build()

    log_fh = open(PREVIEW_LOG_FILE, "a", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--directory", str(BUILDS_DIR)],
        stdout=log_fh,
        stderr=log_fh,
        start_new_session=True,
    )
    time.sleep(0.4)
    if is_pid_alive(proc.pid):
        PREVIEW_PID_FILE.write_text(str(proc.pid), encoding="utf-8")
        print(f"[✓] Preview server started on http://localhost:{port} (PID: {proc.pid})")
        return True
    else:
        print("[!] Preview server failed to start. Check log:", PREVIEW_LOG_FILE)
        return False


def start_publisher_server(port: int = PUBLISHER_PORT_DEFAULT) -> bool:
    """Start BEJSON CMS Publisher Flask server in the background."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    PID_DIR.mkdir(parents=True, exist_ok=True)

    existing_pid = get_pid_from_file(PUBLISHER_PID_FILE)
    if existing_pid and is_pid_alive(existing_pid):
        print(f"[i] Publisher server already running on port {port} (PID: {existing_pid}).")
        return True

    publisher_script = PROJECT_ROOT / "src" / "web" / "BEJSON_CMS_Publisher.py"
    log_fh = open(PUBLISHER_LOG_FILE, "a", encoding="utf-8")
    env = os.environ.copy()
    env["CMS_PUBLISHER_PORT"] = str(port)

    proc = subprocess.Popen(
        [sys.executable, str(publisher_script)],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=log_fh,
        stderr=log_fh,
        start_new_session=True,
    )
    time.sleep(0.6)
    if is_pid_alive(proc.pid):
        PUBLISHER_PID_FILE.write_text(str(proc.pid), encoding="utf-8")
        print(f"[✓] Publisher server started on http://localhost:{port} (PID: {proc.pid})")
        return True
    else:
        print("[!] Publisher server failed to start. Check log:", PUBLISHER_LOG_FILE)
        return False


def stop_server(pid_file: Path, label: str):
    """Gracefully terminate a tracked server process."""
    pid = get_pid_from_file(pid_file)
    if not pid or not is_pid_alive(pid):
        if pid_file.exists():
            pid_file.unlink(missing_ok=True)
        print(f"[i] {label} is not running.")
        return

    print(f"[*] Stopping {label} (PID {pid})...")
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.5)
        if is_pid_alive(pid):
            os.kill(pid, signal.SIGKILL)
    except Exception:
        pass
    pid_file.unlink(missing_ok=True)
    print(f"[✓] {label} stopped.")


def status():
    """Print status table for servers."""
    prev_pid = get_pid_from_file(PREVIEW_PID_FILE)
    prev_alive = is_pid_alive(prev_pid)
    pub_pid = get_pid_from_file(PUBLISHER_PID_FILE)
    pub_alive = is_pid_alive(pub_pid)

    div = "=" * 57
    print(div)
    print(" BEJSON CMS SERVER STATUS")
    print(div)
    print(f" Preview Server (Built Site): {'RUNNING (PID ' + str(prev_pid) + ')' if prev_alive else 'STOPPED'}")
    print(f" URL: http://localhost:{PREVIEW_PORT_DEFAULT}")
    print(f" Publisher Control Center:   {'RUNNING (PID ' + str(pub_pid) + ')' if pub_alive else 'STOPPED'}")
    print(f" URL: http://localhost:{PUBLISHER_PORT_DEFAULT}")
    print(div)


def main():
    parser = argparse.ArgumentParser(description="BEJSON CMS Server Manager")
    parser.add_argument("--build", action="store_true", help="Compile static site before starting server")
    parser.add_argument("--preview-port", type=int, default=PREVIEW_PORT_DEFAULT, help="Port for preview server (default: 8000)")
    parser.add_argument("--publisher-port", type=int, default=PUBLISHER_PORT_DEFAULT, help="Port for publisher server (default: 5001)")
    parser.add_argument("--publisher", action="store_true", help="Also start the Publisher Flask control center")
    parser.add_argument("--no-browser", action="store_true", help="Do not launch browser")
    parser.add_argument("--stop", action="store_true", help="Stop running servers")
    parser.add_argument("--status", action="store_true", help="Check server status")
    parser.add_argument("--restart", action="store_true", help="Restart running servers")

    args = parser.parse_args()

    if args.status:
        status()
        return

    if args.stop or args.restart:
        stop_server(PREVIEW_PID_FILE, "Preview Server")
        stop_server(PUBLISHER_PID_FILE, "Publisher Server")
        if args.stop:
            return

    if args.build:
        run_build()

    # Start preview server by default
    preview_ok = start_preview_server(args.preview_port)

    # Optionally start publisher server
    if args.publisher:
        start_publisher_server(args.publisher_port)

    preview_url = f"http://localhost:{args.preview_port}"
    copy_to_clipboard(preview_url)

    if not args.no_browser and preview_ok:
        open_browser(preview_url)

    status()


if __name__ == "__main__":
    main()
