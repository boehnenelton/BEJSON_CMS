"""
Name:           test_bejson_cms_app_uuid_validation.py
Description:    Regression test for a real incident this session: an
                 unvalidated app_uuid in BEJSON_CMS_Content.py's
                 app_delete() let a single authenticated POST with
                 app_uuid=".." recursively delete the entire mfdb/ tree
                 via shutil.rmtree(), not just one app's folder. Confirmed
                 destructive in an isolated full-project copy before the
                 fix, confirmed blocked after. This test is the permanent
                 guard against that regressing silently.

                 APPS_STORAGE and db are monkeypatched to pytest tmp_path /
                 an isolated CMSCore instance for every test here -- never
                 touches the real project's storage/mfdb/, same lesson as
                 test_lib_bejson_CMS_cms_core.py.
Version:        1.0
Date:           2026-09-04
Author:         Elton Boehnen (written by Claude)
RELATIONAL_ID:  9d4f1e7b-2a6c-4f9e-8b3d-1c7a5e9f2b6d
"""
import os
import sys
import base64

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "web"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "lib"))

os.environ.setdefault("CMS_PASSWORD", "test-only-password-for-pytest")

import BEJSON_CMS_Admin as admin
import BEJSON_CMS_Content as content
import lib_bejson_Core_mfdb_core as mfdb_core
import lib_bejson_CMS_cms_core as CMSCore


_MINIMAL_ENTITIES = [
    {
        "name": "StandaloneApp",
        "primary_key": "app_uuid",
        "fields": [
            {"name": "app_uuid", "type": "string"},
            {"name": "app_name", "type": "string"},
        ],
    },
]


def _isolated_db(tmp_path):
    """Real CMSCore instance, real manifest -- entirely in tmp_path, never
    the real project's storage/mfdb/."""
    root = tmp_path / "site_master"
    mfdb_core.mfdb_core_create_database(root_dir=str(root), db_name="test_site_master", entities=_MINIMAL_ENTITIES)
    return CMSCore.CMSCore(str(root / "104a.mfdb.bejson"))


def _auth_headers():
    creds = base64.b64encode(f"admin:{os.environ['CMS_PASSWORD']}".encode()).decode()
    return {"Authorization": f"Basic {creds}"}


class TestAppDeleteUUIDValidation:
    def _isolated_apps_dir(self, tmp_path, monkeypatch):
        apps_dir = tmp_path / "standalone_apps"
        apps_dir.mkdir()
        monkeypatch.setattr(content, "APPS_STORAGE", str(apps_dir))
        monkeypatch.setattr(content, "db", _isolated_db(tmp_path))
        return apps_dir

    def test_traversal_payload_does_not_delete_sibling_directory(self, tmp_path, monkeypatch):
        apps_dir = self._isolated_apps_dir(tmp_path, monkeypatch)
        canary = tmp_path / "canary_dir"
        canary.mkdir()
        (canary / "important.txt").write_text("must survive")

        client = admin.app.test_client()
        resp = client.post("/apps/delete/..", headers=_auth_headers())

        # Pre-fix this returned a 500 mid-shutil.rmtree after already
        # wiping the target's contents. Post-fix it must reject before
        # ever touching the filesystem.
        assert resp.status_code in (302, 400)
        assert canary.exists()
        assert (canary / "important.txt").exists()

    def test_encoded_slash_traversal_also_rejected(self, tmp_path, monkeypatch):
        apps_dir = self._isolated_apps_dir(tmp_path, monkeypatch)
        canary = tmp_path / "canary_dir2"
        canary.mkdir()
        (canary / "important.txt").write_text("must survive")

        client = admin.app.test_client()
        resp = client.post("/apps/delete/..%2Fcanary_dir2", headers=_auth_headers())

        assert canary.exists()
        assert (canary / "important.txt").exists()

    def test_serve_app_rejects_non_uuid(self, tmp_path, monkeypatch):
        self._isolated_apps_dir(tmp_path, monkeypatch)
        client = admin.app.test_client()
        resp = client.get("/apps/view/..", headers=_auth_headers())
        assert resp.status_code == 400

    def test_serve_app_rejects_garbage_uuid(self, tmp_path, monkeypatch):
        self._isolated_apps_dir(tmp_path, monkeypatch)
        client = admin.app.test_client()
        resp = client.get("/apps/view/not-a-real-uuid", headers=_auth_headers())
        assert resp.status_code == 400

    def test_legitimate_uuid_shaped_delete_is_not_blocked_by_validation(self, tmp_path, monkeypatch):
        """A syntactically valid (but non-existent) UUID must pass the
        validation step and reach the normal 'not found' path, not get
        rejected as if it were malformed."""
        self._isolated_apps_dir(tmp_path, monkeypatch)
        client = admin.app.test_client()
        real_shaped_uuid = "12345678-1234-5678-1234-567812345678"
        resp = client.post(f"/apps/delete/{real_shaped_uuid}", headers=_auth_headers())
        # Should redirect (flash "App deleted" even if nothing matched --
        # delete_record on a no-op match is harmless), not 400.
        assert resp.status_code == 302
