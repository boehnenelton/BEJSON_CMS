"""
Name:           test_lib_bejson_Core_bejson_path_guard.py
Description:    Tests for path-traversal protection and storage path resolution.
Version:        1.0
Date:           2026-07-05
Author:         Elton Boehnen (written by Claude)
RELATIONAL_ID:  a1b2c3d4-e5f6-4708-9a1b-2c3d4e5f6071
"""
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "lib"))

import lib_bejson_Core_bejson_path_guard as path_guard


class TestBejsonSafeJoin:
    def test_joins_within_base_dir(self):
        with tempfile.TemporaryDirectory() as base:
            result = path_guard.bejson_safe_join(base, "sub", "file.txt")
            assert result.startswith(os.path.realpath(base))
            assert result.endswith(os.path.join("sub", "file.txt"))

    def test_rejects_traversal_above_base(self):
        with tempfile.TemporaryDirectory() as base:
            with pytest.raises(ValueError):
                path_guard.bejson_safe_join(base, "..", "..", "etc", "passwd")

    def test_rejects_absolute_escape_via_dotdot_chain(self):
        with tempfile.TemporaryDirectory() as base:
            with pytest.raises(ValueError):
                path_guard.bejson_safe_join(base, "a", "..", "..", "b")


class TestResolveStoragePath:
    def test_returns_storage_root_when_path_empty(self, monkeypatch):
        monkeypatch.setenv("BEJSON_STORAGE_ROOT", "/tmp/bejson_root")
        assert path_guard.resolve_storage_path("") == "/tmp/bejson_root"

    def test_falls_back_to_home_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("BEJSON_STORAGE_ROOT", raising=False)
        result = path_guard.resolve_storage_path("")
        assert result == os.path.expanduser("~")

    def test_rewrites_legacy_hardcoded_prefix(self, monkeypatch):
        monkeypatch.setenv("BEJSON_STORAGE_ROOT", "/tmp/bejson_root")
        result = path_guard.resolve_storage_path("/storage/emulated/0/mfdb/file.bejson")
        assert result == "/tmp/bejson_root/mfdb/file.bejson"

    def test_passes_through_normal_relative_path(self, monkeypatch):
        monkeypatch.setenv("BEJSON_STORAGE_ROOT", "/tmp/bejson_root")
        assert path_guard.resolve_storage_path("data/file.bejson") == "data/file.bejson"


class TestEscapesRoot:
    def test_simple_relative_path_is_safe(self):
        assert path_guard._bejson_mfdb_escapes_root("data/category.bejson") is False

    def test_single_dotdot_within_depth_is_safe(self):
        assert path_guard._bejson_mfdb_escapes_root("data/../104a.mfdb.bejson") is False

    def test_dotdot_escaping_above_root_is_unsafe(self):
        assert path_guard._bejson_mfdb_escapes_root("../104a.mfdb.bejson") is True

    def test_deeply_nested_escape_is_unsafe(self):
        assert path_guard._bejson_mfdb_escapes_root("a/../../b") is True

    def test_windows_style_separators_are_normalized(self):
        assert path_guard._bejson_mfdb_escapes_root("..\\104a.mfdb.bejson") is True

    def test_current_dir_segments_do_not_affect_depth(self):
        assert path_guard._bejson_mfdb_escapes_root("./data/./file.bejson") is False
