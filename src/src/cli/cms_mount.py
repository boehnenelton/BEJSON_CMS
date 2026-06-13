#!/usr/bin/env python3
"""
SCRIPT_NAME:    cms_mount.py
SCRIPT_VERSION: 15.4.2
AUTHOR:         Elton Boehnen
DESCRIPTION:    Deprecated mount CLI tool.
                MFDB now uses direct modular file access — mounting is not required.
                Patched by patch_cms.py (M-05).
"""
import sys


def main():
    print("[Info] MFDB mount is no longer required.")
    print("[Info] The BEJSON CMS uses direct modular file access.")
    print("[Info] All read/write operations are handled automatically by lib_mfdb_core.")
    sys.exit(0)


if __name__ == "__main__":
    main()
