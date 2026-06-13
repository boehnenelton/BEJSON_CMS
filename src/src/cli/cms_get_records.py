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
    parser = argparse.ArgumentParser(description="Dump records for an entity.")
    parser.add_argument("--entity", required=True, help="Entity name (e.g., SiteConfig)")
    args = parser.parse_args()
    
    db.mount()
    records = db.get_records(args.entity)
    print(json.dumps(records, indent=2))

if __name__ == "__main__":
    main()
