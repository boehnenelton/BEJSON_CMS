"""
Script:        audit_taxonomy.py
Description:   Dry-run field audit — reads all live entity BEJSON files and
               reports which fields need renaming per lib_bejson_CMS_taxonomy.py.
               No writes. Safe to run at any time.
               See docs/taxonomy_migration_tasks.md Step 2.1
Version:       1.0.0
Author:        Elton Boehnen
Date:          2026-08-10
RELATIONAL_ID: 3d7f2a1e-8c4b-4e9d-b6a0-5f1c8e7d2b3a
"""

import json, os, sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_PATH.parent / "src" / "lib"))

import lib_bejson_CMS_taxonomy as T

MASTER_PATH = SCRIPT_PATH.parent / "storage" / "mfdb" / "site_master"
DATA_DIR    = MASTER_PATH / "data"
MANIFEST    = MASTER_PATH / "104a.mfdb.bejson"
OUT_JSON    = SCRIPT_PATH.parent / "storage" / "tmp" / "taxonomy_audit.json"

# Entity name -> filename mapping (lowercase entity name = filename)
ENTITY_FILE_MAP = {
    "AuthorProfile": "authorprofile.bejson",
    "Category":      "category.bejson",
    "PageRecord":    "pagerecord.bejson",
    "MediaAsset":    "mediaasset.bejson",
    "ExternalMedia": "externalmedia.bejson",
    "AdUnit":        "adunit.bejson",
    "StandaloneApp": "standaloneapp.bejson",  # not in taxonomy but check anyway
    "NavLink":       "navlink.bejson",
    "SiteConfig":    "siteconfig.bejson",
    "SocialLink":    "sociallink.bejson",
    "AI_Profile":    "ai_profile.bejson",
}

def audit():
    print("=" * 70)
    print("BEJSON CMS TAXONOMY FIELD AUDIT")
    print("Comparing live entity files against taxonomy alias map...")
    print("=" * 70)

    summary = {}
    total_renames = 0
    total_uuid_injections = 0

    for entity, fname in ENTITY_FILE_MAP.items():
        fpath = DATA_DIR / fname
        if not fpath.exists():
            print(f"\n  {entity}: FILE NOT FOUND ({fname}) -- skipping")
            summary[entity] = {"status": "missing"}
            continue

        with open(fpath) as f:
            data = json.load(f)

        live_fields = [fi["name"] for fi in data.get("Fields", [])]
        row_count   = len(data.get("Values", []))
        validation  = T.taxonomy_validate_entity_fields(entity, live_fields)
        uuid_field  = T.taxonomy_get_uuid_field(entity)
        needs_uuid  = uuid_field not in live_fields if uuid_field else False

        renames = {old: T.taxonomy_resolve_field(entity, old)
                   for old in validation["known_old"]}
        total_renames += len(renames)
        if needs_uuid:
            total_uuid_injections += 1

        summary[entity] = {
            "file":       fname,
            "row_count":  row_count,
            "live_fields": live_fields,
            "fields_to_rename": renames,
            "already_canonical": validation["already_canonical"],
            "needs_uuid_injection": needs_uuid,
            "uuid_field": uuid_field,
        }

        print(f"\n  {entity}  ({row_count} rows, {fname})")
        if renames:
            print(f"    Fields to rename ({len(renames)}):")
            for old, new in renames.items():
                print(f"      {old:<28} -> {new}")
        else:
            print("    Fields to rename: (none)")
        print(f"    Already canonical: {validation['already_canonical']}")
        if needs_uuid:
            print(f"    *** UUID injection needed: add '{uuid_field}' field ***")
        else:
            print(f"    UUID field '{uuid_field}': {'present' if uuid_field in live_fields else 'N/A'}")

    print()
    print("=" * 70)
    print(f"  TOTAL fields to rename:      {total_renames}")
    print(f"  TOTAL UUID injections needed: {total_uuid_injections}")
    print("=" * 70)

    # Write machine-readable summary
    os.makedirs(OUT_JSON.parent, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n  Summary written: {OUT_JSON}")

if __name__ == "__main__":
    audit()
