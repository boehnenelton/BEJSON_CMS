"""
Library:        lib_bejson_CMS_cms_core.py
Family:         CMS
Description:    add_record() now accepts sync_count to defer manifest fsync
                for batch/looped inserts; update_record() writes all changed
                fields in one call via mfdb_core_update_entity_record_bulk
                instead of one entity-file rewrite per field.
Version:        2.0.4
Date:           2026-07-06
Author:         Elton Boehnen
Contact:        eltonboehnen@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  251c3930-f0fd-4f77-8812-f85d5c3395df
"""

# ==============================================================================
# LIBRARY: lib_bejson_CMS_cms_core.py
# PURPOSE: Extension library for BEJSON_CMS built on core MFDB libraries.
# VERSION: 18.0 (CoreEvolution Integration)
# AUTHOR:  Elton Boehnen
# DATE:    2026-06-06
# CHANGES: - Integrated bejson_core_get_field_map() for O(1) field lookups.
#          - Refactored add_record/update_record to use cached maps.
#          - Added robust type checks to prevent 'bool' subscript errors 
#            on corrupted BEJSON files.
#          - Updated library imports to align with Lib_PY 2.0.1.
# ==============================================================================

import os
import sys
import logging

# Ensure Core libraries are accessible
LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if LIB_DIR not in sys.path:
    sys.path.append(LIB_DIR)

try:
    import lib_bejson_Core_mfdb_core as MFDB
    import lib_bejson_Core_bejson_core as Core
except ImportError:
    # Handle if run from outside
    try:
        from . import lib_bejson_Core_mfdb_core as MFDB
        from . import lib_bejson_Core_bejson_core as Core
    except:
        MFDB = None
        Core = None

class CMSCore:
    def __init__(self, manifest_path: str):
        self.manifest_path = manifest_path

    def mount(self):
        """Deprecated: Modular access does not require mounting."""
        return True

    def commit(self):
        """Deprecated: Modular access atomic writes handle commits automatically."""
        return True

    def get_records(self, entity_name: str) -> list[dict]:
        """Loads all records for an entity as a list of dicts."""
        if not MFDB: return []
        try:
            records = MFDB.mfdb_core_load_entity(self.manifest_path, entity_name)
            if not isinstance(records, list):
                return []
            return records
        except Exception as e:
            print(f"[CMSCore] Get Records Error ({entity_name}): {e}")
            return []

    def add_record(self, entity_name: str, record_dict: dict, sync_count: bool = True) -> bool:
        """Adds a record to the entity using cached field mapping.

        sync_count: when False, skips the manifest record-count fsync for this
        call. Callers doing bulk/looped inserts (e.g. multi-file upload, batch
        import) should pass False on every call except the last, then call
        sync_manifest_count() once afterward. This avoids one full manifest
        read+write+fsync per record on every batch operation.
        """
        if not MFDB or not Core: return False
        try:
            doc = MFDB.mfdb_core_get_entity_doc(self.manifest_path, entity_name)
            if not isinstance(doc, dict):
                raise ValueError(f"Entity document for '{entity_name}' is corrupted or invalid.")
                
            fields = doc.get("Fields", [])
            field_map = Core.bejson_core_get_field_map(doc)
            
            row = [None] * len(fields)
            for field_name, val in record_dict.items():
                idx = field_map.get(field_name, -1)
                if idx != -1:
                    row[idx] = val
            
            # Handle Record_Type_Parent discriminator (104db)
            rtp_idx = field_map.get('Record_Type_Parent', -1)
            if rtp_idx != -1 and row[rtp_idx] is None:
                row[rtp_idx] = entity_name

            MFDB.mfdb_core_add_entity_record(self.manifest_path, entity_name, row, sync_count=sync_count)
            return True
        except Exception as e:
            print(f"[CMSCore] Add Record Error ({entity_name}): {e}")
            return False

    def sync_manifest_count(self, entity_name: str) -> int:
        """Recount rows in an entity file and fsync the manifest once.
        Call this after a batch of add_record(..., sync_count=False) calls."""
        if not MFDB: return -1
        try:
            return MFDB.mfdb_core_sync_manifest_count(self.manifest_path, entity_name)
        except Exception as e:
            print(f"[CMSCore] Sync Manifest Count Error ({entity_name}): {e}")
            return -1

    def delete_record(self, entity_name: str, match_field: str, match_value: any) -> bool:
        """Deletes a record matching the field/value."""
        if not MFDB: return False
        try:
            records = self.get_records(entity_name)
            target_idx = -1
            for i, rec in enumerate(records):
                if rec.get(match_field) == match_value:
                    target_idx = i
                    break
            
            if target_idx != -1:
                MFDB.mfdb_core_remove_entity_record(self.manifest_path, entity_name, target_idx)
                return True
            return False
        except Exception as e:
            print(f"[CMSCore] Delete Record Error ({entity_name}): {e}")
            return False

    def update_record(self, entity_name: str, match_field: str, match_value: any, updates: dict) -> bool:
        """Updates a record matching the field/value."""
        if not MFDB: return False
        try:
            records = self.get_records(entity_name)
            target_idx = -1
            for i, rec in enumerate(records):
                if rec.get(match_field) == match_value:
                    target_idx = i
                    break
            
            if target_idx != -1:
                # FIX (LIB-CMS-M1): previously fetched the entity doc twice -
                # once inside self.get_field_map(entity_name), and again
                # here immediately after. Fetch once and derive the field
                # map from the same doc directly.
                doc = MFDB.mfdb_core_get_entity_doc(self.manifest_path, entity_name)
                field_map = Core.bejson_core_get_field_map(doc) if (MFDB and Core and isinstance(doc, dict)) else {}
                fields = doc.get("Fields", [])

                coerced_updates = {}
                for k, v in updates.items():
                    # Data Integrity: Coerce None to "" for strings (BUG-11)
                    idx = field_map.get(k, -1)
                    if idx != -1 and v is None and fields[idx].get("type") == "string":
                        v = ""
                    coerced_updates[k] = v
                # Single bulk write instead of one entity-file fsync per field
                MFDB.mfdb_core_update_entity_record_bulk(self.manifest_path, entity_name, target_idx, coerced_updates)
                return True
            return False
        except Exception as e:
            logging.error(f"[CMSCore] Update Record Error ({entity_name}): {e}", exc_info=True)
            return False

    def get_field_map(self, entity_name: str) -> dict:
        """Returns the cached field-name-to-index map for an entity."""
        if not MFDB or not Core:
            return {}
        try:
            doc = MFDB.mfdb_core_get_entity_doc(self.manifest_path, entity_name)
            if not isinstance(doc, dict): return {}
            return Core.bejson_core_get_field_map(doc)
        except Exception as e:
            # FIX (LIB-CMS-M2): was a bare print() - invisible in production
            # (stdout, not a log stream) and indistinguishable from a
            # legitimately empty entity. Logged with a real severity level
            # and full traceback instead; still returns {} to preserve the
            # existing return contract for callers, since this method (and
            # its sibling update_record above) already establish "log and
            # return an empty/falsy default" as this class's error-handling
            # convention throughout - changing the contract here alone would
            # be an inconsistent, wider-reaching API change.
            logging.error(f"[CMSCore] get_field_map Error ({entity_name}): {e}", exc_info=True)
            return {}
