"""
Name:           test_lib_bejson_Core_mfdb_validator.py
Description:    Tests for MFDB manifest/entity relational validation.
Version:        1.0
Date:           2026-07-05
Author:         Elton Boehnen (written by Claude)
RELATIONAL_ID:  b2c3d4e5-f607-4819-9a1b-2c3d4e5f6172
"""
import os
import sys
import json
import shutil
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "lib"))

import lib_bejson_Core_mfdb_validator as mfdb_validator

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
LIVE_MANIFEST = os.path.join(PROJECT_ROOT, "storage", "mfdb", "site_master", "104a.mfdb.bejson")


@pytest.fixture
def live_manifest_copy():
    """Copy the real live manifest+entities to a temp dir so tests never touch the real database."""
    src_dir = os.path.dirname(LIVE_MANIFEST)
    with tempfile.TemporaryDirectory() as tmp:
        dst_dir = os.path.join(tmp, "site_master")
        shutil.copytree(src_dir, dst_dir)
        yield os.path.join(dst_dir, "104a.mfdb.bejson")


class TestValidateMfdbManifest:
    def test_live_manifest_is_valid(self, live_manifest_copy):
        result = mfdb_validator.validate_mfdb_manifest(live_manifest_copy)
        assert result.valid, f"Live manifest failed validation: {result.errors}"

    def test_missing_manifest_file_is_invalid(self):
        result = mfdb_validator.validate_mfdb_manifest("/nonexistent/path/104a.mfdb.bejson")
        assert result.valid is False
        assert any("not found" in e.lower() for e in result.errors)

    def test_wrong_format_version_is_rejected(self, live_manifest_copy):
        with open(live_manifest_copy, encoding="utf-8") as f:
            doc = json.load(f)
        doc["Format_Version"] = "104"  # wrong - manifests must be 104a
        with open(live_manifest_copy, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        result = mfdb_validator.validate_mfdb_manifest(live_manifest_copy)
        assert result.valid is False

    def test_duplicate_entity_name_is_rejected(self, live_manifest_copy):
        with open(live_manifest_copy, encoding="utf-8") as f:
            doc = json.load(f)
        # duplicate the first entity row to trigger the duplicate-name check
        doc["Values"].append(doc["Values"][0])
        with open(live_manifest_copy, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        result = mfdb_validator.validate_mfdb_manifest(live_manifest_copy)
        assert result.valid is False
        assert any("duplicate" in e.lower() for e in result.errors)


class TestPathTraversalRemediationNew08:
    """Specifically exercises the NEW-08 remediation added in the pkg30 library upgrade."""

    def test_manifest_entry_escaping_root_is_rejected(self, live_manifest_copy):
        with open(live_manifest_copy, encoding="utf-8") as f:
            doc = json.load(f)
        fields = [f["name"] for f in doc["Fields"]]
        fp_idx = fields.index("file_path")
        # tamper the first entity's file_path to attempt an escape above the MFDB root
        doc["Values"][0][fp_idx] = "../../../etc/passwd"
        with open(live_manifest_copy, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        result = mfdb_validator.validate_mfdb_manifest(live_manifest_copy)
        assert result.valid is False
        assert any("traversal" in e.lower() for e in result.errors)


class TestValidateMfdbDatabase:
    def test_live_database_is_fully_valid(self, live_manifest_copy):
        result = mfdb_validator.validate_mfdb_database(live_manifest_copy)
        assert result.valid, f"Live database failed validation: {result.errors}"


class TestCompatibilityWrappers:
    def test_validate_manifest_wrapper_returns_true_on_success(self, live_manifest_copy):
        assert mfdb_validator.mfdb_validator_validate_manifest(live_manifest_copy) is True

    def test_validate_manifest_wrapper_raises_on_failure(self):
        with pytest.raises(mfdb_validator.MFDBValidationError):
            mfdb_validator.mfdb_validator_validate_manifest("/nonexistent/104a.mfdb.bejson")
