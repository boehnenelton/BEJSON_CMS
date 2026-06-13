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
    print('[Info] Modular database access enabled. Mount/Commit pattern is no longer required.')
    return
    if db.commit():
        print(f"[Success] Committed {MOUNT_DIR} to {MASTER_ZIP}")
    else:
        print("[Error] Failed to commit.")

if __name__ == "__main__":
    main()
