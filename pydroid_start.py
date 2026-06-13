#!/usr/bin/env python3
"""
SCRIPT_NAME:    pydroid_start.py
SCRIPT_VERSION: 17.0
AUTHOR:         Elton Boehnen
DESCRIPTION:    Pydroid/Termux launcher for BEJSON CMS.
                Launches Flask_CMS.py from the correct src/web path.
"""

VERSION = "17.0"
import os
import sys
import socket
import subprocess
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
FLASK_CMS_PATH = os.path.join(PROJECT_ROOT, "src", "web", "Flask_CMS.py")


def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def launch():
    print("====================================")
    print(f"    BEJSON CMS v{VERSION} LAUNCHER")
    print("====================================")

    if not os.path.exists(FLASK_CMS_PATH):
        print(f"[ERROR] Flask_CMS.py not found at: {FLASK_CMS_PATH}")
        sys.exit(1)

    ip = get_ip()
    url = f"http://127.0.0.1:5001"
    print(f"[*] Local IP: {ip}")
    print(f"[*] Starting CMS at {url}")

    cmd = [sys.executable, FLASK_CMS_PATH]
    proc = subprocess.Popen(cmd)

    time.sleep(2)
    try:
        os.system(f"termux-open-url {url}")
    except Exception:
        pass

    print(f"[*] Press Ctrl+C to stop.")
    try:
        proc.wait()
    except KeyboardInterrupt:
        print("[*] Stopping server...")
        proc.terminate()


if __name__ == "__main__":
    launch()
