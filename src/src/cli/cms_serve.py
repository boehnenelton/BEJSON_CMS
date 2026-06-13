#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEB_DIR = os.path.join(PROJECT_ROOT, "src", "web")

def main():
    parser = argparse.ArgumentParser(description="Bootstrap CMS services.")
    parser.add_argument("--service", choices=["cms", "editor", "publisher"], default="cms", help="Service to run.")
    args = parser.parse_args()
    
    scripts = {
        "cms": "Flask_CMS.py",
        "editor": "Flask_Page_Editor.py",
        "publisher": "Flask_CMS_Publisher.py"
    }
    
    script_path = os.path.join(WEB_DIR, scripts[args.service])
    if not os.path.exists(script_path):
        print(f"[Error] Script not found: {script_path}")
        sys.exit(1)
        
    print(f"[CMS Serve] Starting {args.service} ({script_path})...")
    subprocess.run([sys.executable, script_path])

if __name__ == "__main__":
    main()
