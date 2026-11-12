"""
Name:           test_cms_manage_core_alignment.py
Description:    Regression tests for src/cms-manage.py alignment with CMSCore:
                schema guard (no silent field drops), two-part page write
                ordering/rollback, md-import routed through CMSCore with the
                live 104db content-file shape, and page update --type.
                Every test builds its own throw-away MFDB in tmp_path and
                redirects cms-manage's path helpers there -- never touches
                the real storage/mfdb/.
Version:        1.0
Date:           2026-11-08
Author:         Elton Boehnen (written by Claude)
RELATIONAL_ID:  8a4fd128-7097-4108-a7bb-9a02307314ef
"""
import argparse
import importlib.util
import json
import os
import sys

import pytest

PROJECT_SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, os.path.join(PROJECT_SRC, "lib"))

import lib_bejson_Core_mfdb_core as mfdb_core
import lib_bejson_CMS_cms_core as CMSCore

PAGE_FIELDS = [
    "page_uuid", "page_title", "page_slug", "page_cat_name", "page_type",
    "page_created_at", "page_external_url", "page_author_name", "page_featured_img",
    "page_template_key", "page_featured_video_url", "page_topical_links", "page_featured_diagram",
]
LIVE_CONTENT_SHAPE = ("104db", ["PageMeta", "Content"],
                      ["Record_Type_Parent", "meta_title", "html_body", "markdown_body", "source_code"])


@pytest.fixture()
def cms_manage(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("cms_manage_under_test", os.path.join(PROJECT_SRC, "cms-manage.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    site_master = tmp_path / "storage" / "mfdb" / "site_master"
    mfdb_core.mfdb_core_create_database(
        root_dir=str(site_master), db_name="test_site_master",
        entities=[
            {"name": "PageRecord", "primary_key": "page_uuid",
             "fields": [{"name": n, "type": "string"} for n in PAGE_FIELDS]},
            {"name": "Category", "primary_key": "cat_slug",
             "fields": [{"name": "cat_name", "type": "string"}, {"name": "cat_slug", "type": "string"}]},
            {"name": "AuthorProfile", "primary_key": "author_display_name",
             "fields": [{"name": n, "type": "string"} for n in ("author_display_name", "author_bio", "author_avatar_url")]},
            {"name": "MediaAsset", "primary_key": "asset_filename",
             "fields": [{"name": "asset_filename", "type": "string"}]},
        ])
    manifest_path = str(site_master / "104a.mfdb.bejson")
    pages_db_dir = str(tmp_path / "storage" / "mfdb" / "pages_db")
    monkeypatch.setattr(module, "get_live_manifest_path", lambda: manifest_path)
    monkeypatch.setattr(module, "get_pages_db_dir", lambda: pages_db_dir)
    module.TEST_PAGES_DIR = pages_db_dir
    module.TEST_MANIFEST = manifest_path
    return module


def _content_file(module, page_uuid):
    with open(os.path.join(module.TEST_PAGES_DIR, f"{page_uuid}.json"), encoding="utf-8") as handle:
        return json.load(handle)


def _manifest_count(module, entity_name):
    with open(module.TEST_MANIFEST, encoding="utf-8") as handle:
        manifest = json.load(handle)
    field_map = {f["name"]: i for i, f in enumerate(manifest["Fields"])}
    for row in manifest["Values"]:
        if row[field_map["entity_name"]] == entity_name:
            return row[field_map["record_count"]]
    raise AssertionError(f"{entity_name} not in manifest")


class TestSchemaGuard:
    def test_refuses_unknown_non_empty_field_and_writes_nothing(self, cms_manage):
        db = cms_manage.get_db()
        assert cms_manage._checked_add(db, "Category", {"cat_name": "A", "cat_slug": "a", "cat_bogus": "x"}) is False
        assert db.get_records("Category") == []

    def test_allows_unknown_field_when_value_is_empty(self, cms_manage):
        db = cms_manage.get_db()
        assert cms_manage._checked_add(db, "Category", {"cat_name": "A", "cat_slug": "a", "cat_bogus": ""}) is True
        assert len(db.get_records("Category")) == 1

    def test_refuses_entity_missing_from_schema(self, cms_manage):
        db = cms_manage.get_db()
        assert cms_manage._checked_add(db, "NoSuchEntity", {"x": "1"}) is False


class TestCreatePage:
    def _record(self, page_uuid="u1"):
        return {"page_uuid": page_uuid, "page_title": "T", "page_slug": "t",
                "page_cat_name": "Uncategorized", "page_type": "blog"}

    def test_writes_row_and_live_shape_content_file(self, cms_manage):
        db = cms_manage.get_db()
        assert cms_manage._create_page(db, self._record(), "T", "<p>x</p>", "md") is True
        doc = _content_file(cms_manage, "u1")
        assert (doc["Format_Version"], doc["Records_Type"], [f["name"] for f in doc["Fields"]]) == LIVE_CONTENT_SHAPE
        assert doc["Values"][1][3] == "md"
        assert len(db.get_records("PageRecord")) == 1

    def test_failed_row_write_leaves_no_orphan_content_file(self, cms_manage, monkeypatch):
        db = cms_manage.get_db()
        monkeypatch.setattr(db, "add_record", lambda *args, **kwargs: False)
        assert cms_manage._create_page(db, self._record("u2"), "T", "<p>x</p>") is False
        assert not os.path.exists(os.path.join(cms_manage.TEST_PAGES_DIR, "u2.json"))

    def test_schema_problem_writes_neither_part(self, cms_manage):
        db = cms_manage.get_db()
        record = dict(self._record("u3"), page_bogus="x")
        assert cms_manage._create_page(db, record, "T", "<p>x</p>") is False
        assert not os.path.exists(os.path.join(cms_manage.TEST_PAGES_DIR, "u3.json"))
        assert db.get_records("PageRecord") == []


class TestMarkdownImportUsesCMSCore:
    def _args(self, target, **overrides):
        values = dict(target=str(target), category="Uncategorized", author="Tester", type="blog",
                      featured_img=None, recursive=False, publish=False)
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_single_file_import_matches_live_contract(self, cms_manage, tmp_path):
        md_file = tmp_path / "alpha.md"
        md_file.write_text("# Alpha Post\n\nBody **one**.\n", encoding="utf-8")
        cms_manage.cmd_page_md_import(self._args(md_file))
        db = cms_manage.get_db()
        (record,) = db.get_records("PageRecord")
        assert record["page_title"] == "Alpha Post"
        assert record["page_cat_name"] == "Uncategorized" and record["page_author_name"] == "Tester"
        doc = _content_file(cms_manage, record["page_uuid"])
        assert (doc["Format_Version"], doc["Records_Type"], [f["name"] for f in doc["Fields"]]) == LIVE_CONTENT_SHAPE
        assert "Body" in doc["Values"][1][3]
        assert _manifest_count(cms_manage, "PageRecord") == 1

    def test_directory_import_syncs_manifest_count_once_correctly(self, cms_manage, tmp_path):
        drop_dir = tmp_path / "drops"
        drop_dir.mkdir()
        for name in ("one", "two", "three"):
            (drop_dir / f"{name}.md").write_text(f"# {name.title()} Post\n\ntext\n", encoding="utf-8")
        cms_manage.cmd_page_md_import(self._args(drop_dir))
        assert len(cms_manage.get_db().get_records("PageRecord")) == 3
        assert _manifest_count(cms_manage, "PageRecord") == 3


class TestPageUpdateType:
    def test_type_flag_is_applied(self, cms_manage):
        db = cms_manage.get_db()
        cms_manage._create_page(db, {"page_uuid": "u9", "page_title": "T", "page_slug": "t",
                                     "page_cat_name": "Uncategorized", "page_type": "blog"}, "T", "<p>x</p>")
        cms_manage.cmd_page_update(argparse.Namespace(
            uuid="u9", title="T", category=None, author=None, featured_video=None,
            featured_diagram=None, body=None, type="article"))
        assert db.get_records("PageRecord")[0]["page_type"] == "article"


class TestCreatedAtFormat:
    """Every other PageRecord writer stores YYYY-MM-DD; the Publisher renders the raw string."""
    DATE_ONLY = r"^\d{4}-\d{2}-\d{2}$"

    def test_page_add_and_quick_post_write_date_only(self, cms_manage):
        import re
        cms_manage.cmd_page_add(argparse.Namespace(
            title="Added", category="Uncategorized", type="blog", slug=None, body="<p>x</p>",
            body_file=None, md_file=None, author=None, featured_img=None, featured_video=None,
            featured_diagram=None, publish=False))
        cms_manage.cmd_quick_post(argparse.Namespace(
            title="Quick", category="Uncategorized", author=None, slug=None, body="<p>x</p>",
            body_file=None, md_file=None, featured_img=None, featured_video=None,
            featured_diagram=None, type="blog", publish=False))
        created = [r["page_created_at"] for r in cms_manage.get_db().get_records("PageRecord")]
        assert len(created) == 2
        assert all(re.match(self.DATE_ONLY, value) for value in created), created


class TestAnonymousAuthorDefault:
    def _authors(self, module):
        return [a["author_display_name"] for a in module.get_db().get_records("AuthorProfile")]

    def test_quick_post_and_page_add_default_to_anonymous(self, cms_manage):
        common = dict(category="Uncategorized", slug=None, body="<p>x</p>", body_file=None, md_file=None,
                      featured_img=None, featured_video=None, featured_diagram=None, publish=False)
        cms_manage.cmd_quick_post(argparse.Namespace(title="Q", author=None, type="blog", **common))
        cms_manage.cmd_page_add(argparse.Namespace(title="A", author=None, type="blog", **common))
        pages = cms_manage.get_db().get_records("PageRecord")
        assert [p["page_author_name"] for p in pages] == ["Anonymous", "Anonymous"]
        assert self._authors(cms_manage).count("Anonymous") == 1  # created once, idempotent

    def test_md_import_defaults_to_anonymous(self, cms_manage, tmp_path):
        md_file = tmp_path / "a.md"
        md_file.write_text("# A\n\ntext\n", encoding="utf-8")
        cms_manage.cmd_page_md_import(argparse.Namespace(
            target=str(md_file), category="Uncategorized", author=None, type="blog",
            featured_img=None, recursive=False, publish=False))
        assert cms_manage.get_db().get_records("PageRecord")[0]["page_author_name"] == "Anonymous"

    def test_explicit_author_kept_and_unknown_author_warned(self, cms_manage, caplog):
        db = cms_manage.get_db()
        with caplog.at_level("WARNING", logger="cms-manage"):
            assert cms_manage._author_or_anonymous(db, "Leethaxor69") == "Leethaxor69"
        assert "no AuthorProfile" in caplog.text
        assert "Anonymous" not in self._authors(cms_manage)  # explicit names never create Anonymous


class TestSetAuthor:
    def _seed(self, module):
        db = module.get_db()
        module._checked_add(db, "AuthorProfile", {"author_display_name": "Leethaxor69", "author_bio": "b", "author_avatar_url": ""})
        for uuid_, title, cat, author, created in [
            ("p1", "Old Book", "BEJSON", "Anonymous", "2026-10-01"),
            ("p2", "New Book", "BEJSON", "Anonymous", "2026-11-06"),
            ("p3", "Other", "Projects", "Anonymous", "2026-11-07 01:00:00"),
        ]:
            module._create_page(db, {"page_uuid": uuid_, "page_title": title, "page_slug": uuid_, "page_cat_name": cat,
                                     "page_type": "blog", "page_created_at": created, "page_author_name": author}, title, "<p>x</p>")
        return db

    def _args(self, **overrides):
        values = dict(author="Leethaxor69", uuid=None, category=None, type=None, current_author=None,
                      since=None, title_contains=None, all=False, dry_run=False, publish=False)
        values.update(overrides)
        return argparse.Namespace(**values)

    def _authors(self, db):
        return {p["page_uuid"]: p["page_author_name"] for p in db.get_records("PageRecord")}

    def test_filters_combine_and_only_matches_change(self, cms_manage):
        db = self._seed(cms_manage)
        cms_manage.cmd_page_set_author(self._args(category="BEJSON", since="2026-11-01"))
        assert self._authors(db) == {"p1": "Anonymous", "p2": "Leethaxor69", "p3": "Anonymous"}

    def test_dry_run_writes_nothing(self, cms_manage):
        db = self._seed(cms_manage)
        cms_manage.cmd_page_set_author(self._args(all=True, dry_run=True))
        assert set(self._authors(db).values()) == {"Anonymous"}

    def test_refuses_without_filter_or_all(self, cms_manage):
        db = self._seed(cms_manage)
        cms_manage.cmd_page_set_author(self._args())
        assert set(self._authors(db).values()) == {"Anonymous"}

    def test_refuses_unknown_author_and_all_flag_works(self, cms_manage):
        db = self._seed(cms_manage)
        cms_manage.cmd_page_set_author(self._args(author="Nobody", all=True))
        assert set(self._authors(db).values()) == {"Anonymous"}
        cms_manage.cmd_page_set_author(self._args(all=True))
        assert set(self._authors(db).values()) == {"Leethaxor69"}

    def test_uuid_filter_is_repeatable(self, cms_manage):
        db = self._seed(cms_manage)
        cms_manage.cmd_page_set_author(self._args(uuid=["p1", "p3"]))
        assert self._authors(db) == {"p1": "Leethaxor69", "p2": "Anonymous", "p3": "Leethaxor69"}
