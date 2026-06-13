#!/usr/bin/env python3
import os
import sys
import argparse
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB_DIR = os.path.join(PROJECT_ROOT, "src", "lib")
if LIB_DIR not in sys.path:
    sys.path.append(LIB_DIR)

import lib_cms_core as CMSCore

MANIFEST_PATH = os.path.join(PROJECT_ROOT, "storage", "mfdb", "site_master", "104a.mfdb.bejson")

db = CMSCore.CMSCore(MANIFEST_PATH)

def main():
    parser = argparse.ArgumentParser(description="Add a record.")
    parser.add_argument("--entity", required=True, help="Entity name")
    parser.add_argument("--data", required=True, help="JSON string of the record data")
    args = parser.parse_args()
    
    try:
        data = json.loads(args.data)
    except json.JSONDecodeError:
        print("[Error] Invalid JSON data.")
        sys.exit(1)
        
    db.mount()
    if db.add_record(args.entity, data):
        db.commit()
        print(f"[Success] Added record to {args.entity}")
    else:
        print("[Error] Failed to add record.")

if __name__ == "__main__":
    main()
