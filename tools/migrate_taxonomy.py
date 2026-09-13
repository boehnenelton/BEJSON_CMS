"""
Script:        migrate_taxonomy.py
Description:   Renames entity fields in live BEJSON data files to canonical
               taxonomy names and injects synthetic UUID columns for entities
               that lack a UUID primary key.
               All writes are atomic (temp + os.replace). Backup BEFORE running live.
               See docs/taxonomy_migration_tasks.md Steps 4.1-4.3
Version:       1.0.1
Author:        Elton Boehnen
Date:          2026-09-12
RELATIONAL_ID: 028eae73-d175-4f38-b2d5-df51e62523d6
CHANGE (2026-09-12): PKG133 -- external audit remediation (M-4). ENTITY_FILE_MAP
was missing "AI_Profile": "ai_profile.bejson", present in audit_taxonomy.py's
copy since pkg132 -- a future migration run would silently skip AI_Profile
while the audit tool already checks it. Added, matching audit_taxonomy.py.

Usage:
  python3 tools/migrate_taxonomy.py --dry-run   # reports changes, no writes
  python3 tools/migrate_taxonomy.py             # applies migration to live data
"""

import json
import os
import sys
import uuid
import argparse
from pathlib import Path
from datetime import datetime, timezone

SCRIPT_PATH = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_PATH.parent / "src" / "lib"))

import lib_bejson_CMS_taxonomy as T

DATA_DIR = SCRIPT_PATH.parent / "storage" / "mfdb" / "site_master" / "data"

ENTITY_FILE_MAP = {
    "AuthorProfile": "authorprofile.bejson",
    "Category":      "category.bejson",
    "PageRecord":    "pagerecord.bejson",
    "MediaAsset":    "mediaasset.bejson",
    "ExternalMedia": "externalmedia.bejson",
    "AdUnit":        "adunit.bejson",
    "StandaloneApp": "standaloneapp.bejson",
    "NavLink":       "navlink.bejson",
    "SiteConfig":    "siteconfig.bejson",
    "SocialLink":    "sociallink.bejson",
    "AI_Profile":    "ai_profile.bejson",
}

def _rename_fields_in_bejson(data: dict, entity: str, dry_run: bool) -> dict:
    """Rename Fields entries and re-align Values columns per alias map.
    Also injects UUID column if entity lacks its canonical UUID field.
    Returns a summary dict: {renames: [...], uuid_injected: bool}
    """
    alias_map = T.TAXONOMY_FIELD_ALIAS_MAP.get(entity, {})
    uuid_field = T.taxonomy_get_uuid_field(entity)

    fields = data.get("Fields", [])
    values = data.get("Values", [])

    # --- Step A: Rename existing fields in Fields array ---
    old_field_names = [fi["name"] for fi in fields]
    renames_applied = []
    new_fields = []
    for fi in fields:
        old_name = fi["name"]
        new_name = alias_map.get(old_name, old_name)
        if new_name != old_name:
            renames_applied.append((old_name, new_name))
        new_fields.append({"name": new_name, "type": fi.get("type", "string")})

    # --- Step B: Check for UUID injection ---
    current_names_after_rename = [fi["name"] for fi in new_fields]
    needs_uuid = (
        uuid_field is not None
        and uuid_field not in old_field_names
        and uuid_field not in current_names_after_rename
    )
    if needs_uuid:
        new_fields.insert(0, {"name": uuid_field, "type": "string"})

    # --- Step C: Update Values to match new column layout ---
    new_values = []
    for row in values:
        new_row = list(row)  # copy

        # Apply UUID injection at column 0
        if needs_uuid:
            new_row.insert(0, str(uuid.uuid4()))

        # Note: field RENAME doesn't change column positions — it only renames
        # the Fields header. Values column order stays the same.
        new_values.append(new_row)

    return {
        "renames_applied": renames_applied,
        "uuid_injected": needs_uuid,
        "uuid_field": uuid_field,
        "new_fields": new_fields,
        "new_values": new_values,
        "row_count": len(new_values),
    }


def run_migration(dry_run: bool):
    mode = "DRY-RUN" if dry_run else "LIVE MIGRATION"
    ts   = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("=" * 70)
    print(f"BEJSON CMS TAXONOMY MIGRATION — {mode}")
    print(f"Timestamp: {ts}")
    print("=" * 70)

    grand_renames = 0
    grand_uuids   = 0

    for entity, fname in ENTITY_FILE_MAP.items():
        fpath = DATA_DIR / fname
        if not fpath.exists():
            print(f"\n  {entity}: FILE NOT FOUND — skipping")
            continue

        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)

        result = _rename_fields_in_bejson(data, entity, dry_run)

        print(f"\n  {entity}  ({result['row_count']} rows)")

        if result["renames_applied"]:
            for old, new in result["renames_applied"]:
                print(f"    RENAME: {old:<28} -> {new}")
            grand_renames += len(result["renames_applied"])
        else:
            print("    RENAME: (none needed)")

        if result["uuid_injected"]:
            print(f"    UUID INJECT: adding '{result['uuid_field']}' to {result['row_count']} rows")
            grand_uuids += 1
        else:
            print(f"    UUID INJECT: '{result['uuid_field']}' already present")

        if dry_run:
            print(f"    [DRY-RUN] No files written.")
            continue

        # Apply changes to data dict
        data["Fields"]   = result["new_fields"]
        data["Values"]   = result["new_values"]
        data["Taxonomy_Migrated_At"] = ts
        data["Taxonomy_Version"]     = "1.0.0"

        # Atomic write: temp file + os.replace
        tmp_path = str(fpath) + ".migrate_tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, str(fpath))
        print(f"    Written: {fpath}")

    print()
    print("=" * 70)
    print(f"  Total field renames: {grand_renames}")
    print(f"  Total UUID injections: {grand_uuids}")
    if dry_run:
        print("  [DRY-RUN] No changes written to disk.")
    else:
        print("  MIGRATION COMPLETE. Run audit_taxonomy.py to verify.")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="BEJSON CMS Taxonomy Field Migration Tool v1.0.0"
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Show what would change without writing any files"
    )
    args = parser.parse_args()

    if not args.dry_run:
        print("WARNING: This will modify live BEJSON entity files in storage/mfdb/site_master/data/")
        print("Ensure you have run 'cms-manage.py backup' before proceeding.")
        confirm = input("Type 'MIGRATE' to proceed: ").strip()
        if confirm != "MIGRATE":
            print("Cancelled.")
            return

    run_migration(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
