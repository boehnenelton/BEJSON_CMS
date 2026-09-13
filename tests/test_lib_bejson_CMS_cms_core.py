"""
Name:           test_lib_bejson_CMS_cms_core.py
Description:    Real CRUD round-trip tests for CMSCore, requested in the
                 P1 audit item ("Add integration tests for ... CMSCore CRUD
                 cycles"). Every test builds its own throw-away MFDB in a
                 pytest tmp_path fixture via mfdb_core_create_database() --
                 never touches the real project's storage/mfdb/, learned
                 the hard way this session (see docs/security-notes.md /
                 the pkg128 changelog entry for what happens when a test
                 believes it's isolated but isn't).
Version:        1.0
Date:           2026-09-04
Author:         Elton Boehnen (written by Claude)
RELATIONAL_ID:  7c3e9a1f-4b2d-4e8a-9f1c-6d5a8b7e2c4f
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "lib"))

import lib_bejson_Core_mfdb_core as mfdb_core
import lib_bejson_CMS_cms_core as CMSCore


_TEST_ENTITIES = [
    {
        "name": "TestWidget",
        "primary_key": "widget_uuid",
        "fields": [
            {"name": "widget_uuid", "type": "string"},
            {"name": "widget_name", "type": "string"},
            {"name": "widget_qty",  "type": "integer"},
        ],
    },
]


def _build_db(tmp_path):
    """Real MFDB, real manifest, real entity files -- just in a pytest
    tmp_path, never inside the real project tree."""
    root = tmp_path / "site_master"
    mfdb_core.mfdb_core_create_database(
        root_dir=str(root),
        db_name="test_site_master",
        entities=_TEST_ENTITIES,
    )
    manifest_path = str(root / "104a.mfdb.bejson")
    return CMSCore.CMSCore(manifest_path)


class TestCMSCoreCRUD:
    def test_add_then_get_returns_the_record(self, tmp_path):
        db = _build_db(tmp_path)
        assert db.add_record("TestWidget", {"widget_uuid": "w1", "widget_name": "Gear", "widget_qty": 5})
        recs = db.get_records("TestWidget")
        assert len(recs) == 1
        assert recs[0]["widget_name"] == "Gear"
        assert recs[0]["widget_qty"] == 5

    def test_get_records_on_empty_entity_returns_empty_list(self, tmp_path):
        db = _build_db(tmp_path)
        assert db.get_records("TestWidget") == []

    def test_update_record_changes_only_targeted_fields(self, tmp_path):
        db = _build_db(tmp_path)
        db.add_record("TestWidget", {"widget_uuid": "w1", "widget_name": "Gear", "widget_qty": 5})
        assert db.update_record("TestWidget", "widget_uuid", "w1", {"widget_qty": 9})
        rec = db.get_records("TestWidget")[0]
        assert rec["widget_qty"] == 9
        assert rec["widget_name"] == "Gear"  # untouched field survives

    def test_update_record_on_missing_match_returns_falsy(self, tmp_path):
        db = _build_db(tmp_path)
        assert not db.update_record("TestWidget", "widget_uuid", "does-not-exist", {"widget_qty": 1})

    def test_delete_record_removes_it(self, tmp_path):
        db = _build_db(tmp_path)
        db.add_record("TestWidget", {"widget_uuid": "w1", "widget_name": "Gear", "widget_qty": 5})
        assert db.delete_record("TestWidget", "widget_uuid", "w1")
        assert db.get_records("TestWidget") == []

    def test_delete_record_on_missing_match_returns_falsy(self, tmp_path):
        db = _build_db(tmp_path)
        assert not db.delete_record("TestWidget", "widget_uuid", "does-not-exist")

    def test_multiple_records_add_get_survive_together(self, tmp_path):
        db = _build_db(tmp_path)
        db.add_record("TestWidget", {"widget_uuid": "w1", "widget_name": "Gear", "widget_qty": 5})
        db.add_record("TestWidget", {"widget_uuid": "w2", "widget_name": "Bolt", "widget_qty": 100})
        recs = db.get_records("TestWidget")
        assert len(recs) == 2
        names = {r["widget_name"] for r in recs}
        assert names == {"Gear", "Bolt"}
        db.delete_record("TestWidget", "widget_uuid", "w1")
        remaining = db.get_records("TestWidget")
        assert len(remaining) == 1
        assert remaining[0]["widget_name"] == "Bolt"

    def test_full_round_trip_add_update_delete(self, tmp_path):
        """The exact cycle every CMS entity command (category, author, ad,
        app, page...) goes through -- add, confirm, update, confirm,
        delete, confirm gone."""
        db = _build_db(tmp_path)
        db.add_record("TestWidget", {"widget_uuid": "rt1", "widget_name": "Original", "widget_qty": 1})
        assert db.get_records("TestWidget")[0]["widget_name"] == "Original"

        db.update_record("TestWidget", "widget_uuid", "rt1", {"widget_name": "Renamed"})
        assert db.get_records("TestWidget")[0]["widget_name"] == "Renamed"

        db.delete_record("TestWidget", "widget_uuid", "rt1")
        assert db.get_records("TestWidget") == []
