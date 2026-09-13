#!/usr/bin/env python3
"""
SCRIPT_NAME:    pydroid_start.py
SCRIPT_VERSION: 18.0
AUTHOR:         Elton Boehnen
DESCRIPTION:    Pydroid/Termux launcher for BEJSON CMS.
                Launches BEJSON_CMS_Admin.py from the correct src/web path.
"""

VERSION = "18.0"
import os
import sys
import socket
import subprocess
import time
from pathlib import Path

def get_script_path() -> Path:
    return Path(__file__).resolve().parent
SCRIPT_PATH = get_script_path()

PROJECT_ROOT = SCRIPT_PATH
FLASK_CMS_PATH = SCRIPT_PATH / "src" / "web" / "BEJSON_CMS_Admin.py"
LIB_PATH = SCRIPT_PATH / "src" / "lib"
CONFIG_PATH = SCRIPT_PATH / "config.json"
sys.path.insert(0, str(LIB_PATH))
import lib_bejson_CMS_cms_ports as CMSPorts


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
    print("    BEJSON CMS LAUNCHER")
    print("====================================")

    if not FLASK_CMS_PATH.exists():
        print(f"[ERROR] BEJSON_CMS_Admin.py not found at: {FLASK_CMS_PATH}")
        sys.exit(1)

    ip = get_ip()
    admin_port = CMSPorts.get_port(str(CONFIG_PATH), "admin_port", "CMS_ADMIN_PORT")
    url = f"http://127.0.0.1:{admin_port}"
    print(f"[*] Local IP: {ip}")
    print(f"[*] Starting CMS at {url}")

    cmd = [sys.executable, str(FLASK_CMS_PATH)]
    proc = subprocess.Popen(cmd)

    time.sleep(2)
    try:
        subprocess.run(["termux-open-url", url], check=False)
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
