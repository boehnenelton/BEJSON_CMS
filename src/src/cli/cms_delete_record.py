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
    parser = argparse.ArgumentParser(description="Delete a record.")
    parser.add_argument("--entity", required=True, help="Entity name")
    parser.add_argument("--match_field", required=True, help="Field to match")
    parser.add_argument("--match_val", required=True, help="Value to match")
    args = parser.parse_args()
        
    db.mount()
    if db.delete_record(args.entity, args.match_field, args.match_val):
        db.commit()
        print(f"[Success] Deleted record from {args.entity}")
    else:
        print("[Error] Failed to delete record.")

if __name__ == "__main__":
    main()
