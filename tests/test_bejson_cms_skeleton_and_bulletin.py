"""
Name:           test_bejson_cms_skeleton_and_bulletin.py
Description:    Verification suite for the 2-Tier Modular Skeleton System and
                unified Home_Bulletin_Skeleton.html (Standard Announcement Bulletin
                and Video Featured Bulletin modes) in BEJSON_CMS_Publisher.py.
Version:        1.0.0
Date Created:   2026-11-12
Author Credit:  Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
RELATIONAL_ID:  7c4e9a12-3b8d-4f60-9c21-8e5a7d3b1f04
"""

import base64
import json
import os
import sys

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_LIB = os.path.join(PROJECT_ROOT, "src", "lib")
SRC_WEB = os.path.join(PROJECT_ROOT, "src", "web")
for path_entry in (SRC_LIB, SRC_WEB):
    if path_entry not in sys.path:
        sys.path.insert(0, path_entry)

import lib_bejson_Core_mfdb_core as mfdb_core
import lib_bejson_CMS_cms_core as cms_core_mod
import BEJSON_CMS_Publisher as publisher_mod


def _basic_auth_headers():
    user_name = os.environ.get("CMS_USER", "admin")
    user_pass = os.environ.get("CMS_PASSWORD", "changeme")
    encoded_token = base64.b64encode(f"{user_name}:{user_pass}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {encoded_token}"}


@pytest.fixture()
def isolated_publisher_env(tmp_path, monkeypatch):
    """Create an isolated MFDB, templates dir, and output dir for publisher tests."""
    site_master_dir = tmp_path / "storage" / "mfdb" / "site_master"
    pages_db_dir = tmp_path / "storage" / "mfdb" / "pages_db"
    assets_dir = tmp_path / "storage" / "mfdb" / "assets"
    apps_dir = tmp_path / "storage" / "mfdb" / "standalone_apps"
    builds_dir = tmp_path / "storage" / "builds"
    skel_dir = tmp_path / "resources" / "templates"
    styles_dir = tmp_path / "resources" / "styles"

    for folder in (site_master_dir, pages_db_dir, assets_dir, apps_dir, builds_dir, skel_dir, styles_dir):
        folder.mkdir(parents=True, exist_ok=True)

    mfdb_core.mfdb_core_create_database(
        root_dir=str(site_master_dir),
        db_name="Test CMS Master",
        entities=[
            {
                "name": "SiteConfig",
                "primary_key": "sys_key",
                "fields": [
                    {"name": "sys_key", "type": "string"},
                    {"name": "sys_value", "type": "string"},
                ],
            },
            {
                "name": "Category",
                "primary_key": "cat_slug",
                "fields": [
                    {"name": "cat_name", "type": "string"},
                    {"name": "cat_slug", "type": "string"},
                ],
            },
            {
                "name": "PageRecord",
                "primary_key": "page_uuid",
                "fields": [
                    {"name": "page_uuid", "type": "string"},
                    {"name": "page_title", "type": "string"},
                    {"name": "page_slug", "type": "string"},
                    {"name": "page_cat_name", "type": "string"},
                    {"name": "page_type", "type": "string"},
                    {"name": "page_created_at", "type": "string"},
                    {"name": "page_external_url", "type": "string"},
                    {"name": "page_author_name", "type": "string"},
                    {"name": "page_featured_img", "type": "string"},
                    {"name": "page_template_key", "type": "string"},
                    {"name": "page_featured_video_url", "type": "string"},
                    {"name": "page_topical_links", "type": "string"},
                    {"name": "page_featured_diagram", "type": "string"},
                ],
            },
            {
                "name": "NavLink",
                "primary_key": "nav_display_label",
                "fields": [
                    {"name": "nav_display_label", "type": "string"},
                    {"name": "nav_target_url", "type": "string"},
                ],
            },
            {
                "name": "SocialLink",
                "primary_key": "social_platform_name",
                "fields": [
                    {"name": "social_platform_name", "type": "string"},
                    {"name": "social_target_url", "type": "string"},
                ],
            },
            {
                "name": "StandaloneApp",
                "primary_key": "app_uuid",
                "fields": [
                    {"name": "app_uuid", "type": "string"},
                    {"name": "app_name", "type": "string"},
                    {"name": "app_slug", "type": "string"},
                    {"name": "app_entry_file", "type": "string"},
                    {"name": "app_created_at", "type": "string"},
                    {"name": "app_featured_img", "type": "string"},
                    {"name": "app_description", "type": "string"},
                ],
            },
            {
                "name": "AdUnit",
                "primary_key": "ad_uuid",
                "fields": [
                    {"name": "ad_uuid", "type": "string"},
                    {"name": "ad_name", "type": "string"},
                    {"name": "ad_banner_url", "type": "string"},
                    {"name": "ad_target_url", "type": "string"},
                    {"name": "ad_zone", "type": "string"},
                    {"name": "ad_active", "type": "boolean"},
                ],
            },
            {
                "name": "ExternalMedia",
                "primary_key": "extmedia_uuid",
                "fields": [
                    {"name": "extmedia_uuid", "type": "string"},
                    {"name": "extmedia_name", "type": "string"},
                    {"name": "extmedia_url", "type": "string"},
                    {"name": "extmedia_type", "type": "string"},
                ],
            },
        ],
    )

    manifest_path = str(site_master_dir / "104a.mfdb.bejson")
    test_db = cms_core_mod.CMSCore(manifest_path)
    test_db.add_record("SiteConfig", {"sys_key": "title", "sys_value": "Test BEJSON Portal"})
    test_db.add_record("SiteConfig", {"sys_key": "description", "sys_value": "Zero-SQL Test Portal"})
    test_db.add_record("Category", {"cat_name": "BEJSON", "cat_slug": "bejson"})

    monkeypatch.setattr(publisher_mod, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(publisher_mod, "PAGES_DB_DIR", str(pages_db_dir))
    monkeypatch.setattr(publisher_mod, "ASSETS_SRC", str(assets_dir))
    monkeypatch.setattr(publisher_mod, "APPS_STORAGE", str(apps_dir))
    monkeypatch.setattr(publisher_mod, "SKEL_DIR", str(skel_dir))
    monkeypatch.setattr(publisher_mod, "OUTPUT_DIR", str(skel_dir))
    monkeypatch.setattr(publisher_mod, "STYLESHEETS_DIR", str(styles_dir))
    monkeypatch.setattr(publisher_mod, "db", test_db)
    publisher_mod._state["output_dir"] = str(builds_dir)
    publisher_mod._state["build_running"] = False

    publisher_mod.SkeletonBuilder(force=True).build_all_skeletons()
    return {
        "db": test_db,
        "builds_dir": builds_dir,
        "skel_dir": skel_dir,
    }


def test_skeleton_builder_creates_all_8_skeletons(isolated_publisher_env):
    skel_dir = isolated_publisher_env["skel_dir"]
    expected_skeletons = [
        "Global_Skeleton.html",
        "Article_Skeleton.html",
        "App_Skeleton.html",
        "Home_Skeleton.html",
        "Home_Bulletin_Skeleton.html",
        "Category_Skeleton.html",
        "Author_Skeleton.html",
        "Apps_Feed_Skeleton.html",
    ]
    for skeleton_name in expected_skeletons:
        assert (skel_dir / skeleton_name).exists(), f"Missing skeleton: {skeleton_name}"


def test_slot_discovery_classifies_global_and_local_skeletons(isolated_publisher_env):
    skel_dir = isolated_publisher_env["skel_dir"]
    # Create a partial that must be excluded
    (skel_dir / "Author_Card.html").write_text("<div>Author Card</div>", encoding="utf-8")

    home_options = publisher_mod._list_slot_skeleton_options("active_home_skeleton")
    assert "Home_Skeleton.html" in home_options
    assert "Home_Bulletin_Skeleton.html" in home_options

    global_options = publisher_mod._list_slot_skeleton_options("active_global_skeleton")
    assert global_options == ["Global_Skeleton.html"]

    app_detail_options = publisher_mod._list_slot_skeleton_options("active_app_detail_skeleton")
    assert "App_Skeleton.html" in app_detail_options
    assert "Apps_Feed_Skeleton.html" not in app_detail_options

    author_options = publisher_mod._list_slot_skeleton_options("active_author_skeleton")
    assert "Author_Skeleton.html" in author_options
    assert "Author_Card.html" not in author_options


def test_standard_vs_video_bulletin_tag_compilation(isolated_publisher_env):
    # 1. Standard Bulletin Mode
    standard_conf = {
        "home_bulletin_enabled": "true",
        "home_bulletin_mode": "standard",
        "home_bulletin_badge": "RELEASE",
        "home_bulletin_title": "BEJSON 105 Released",
        "home_bulletin_text": "Full UUIDv4 record integrity.",
        "home_bulletin_link": "blog/bejson/release/index.html",
        "home_bulletin_link_label": "Read Spec",
        "home_bulletin_video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    }
    std_tags = publisher_mod._build_home_bulletin_tags(standard_conf)
    assert std_tags["bulletin_mode"] == "standard"
    assert std_tags["bulletin_badge"] == "RELEASE"
    assert std_tags["bulletin_title"] == "BEJSON 105 Released"
    assert std_tags["bulletin_video_html"] == ""
    assert 'href="blog/bejson/release/index.html"' in std_tags["bulletin_action_html"]
    assert std_tags["bulletin_display_style"] == ""

    # 2. Video Bulletin Mode
    video_conf = dict(standard_conf, home_bulletin_mode="video")
    vid_tags = publisher_mod._build_home_bulletin_tags(video_conf)
    assert vid_tags["bulletin_mode"] == "video"
    assert "https://www.youtube.com/embed/dQw4w9WgXcQ" in vid_tags["bulletin_video_html"]
    assert vid_tags["bulletin_display_style"] == ""

    # 3. Disabled Bulletin
    disabled_conf = dict(standard_conf, home_bulletin_enabled="false")
    dis_tags = publisher_mod._build_home_bulletin_tags(disabled_conf)
    assert dis_tags["bulletin_display_style"] == "display:none;"


def test_end_to_end_build_swaps_standard_and_bulletin_homepages(isolated_publisher_env):
    builds_dir = isolated_publisher_env["builds_dir"]

    # Default build uses Home_Skeleton.html
    publisher_mod._execute()
    index_html = (builds_dir / "index.html").read_text(encoding="utf-8")
    assert "home-bulletin-card" not in index_html

    # Swap to Home_Bulletin_Skeleton.html in standard mode
    publisher_mod._save_skeleton_config({
        "active_home_skeleton": "Home_Bulletin_Skeleton.html",
        "home_bulletin_enabled": "true",
        "home_bulletin_mode": "standard",
        "home_bulletin_badge": "SYSTEM BULLETIN",
        "home_bulletin_title": "Custom Bulletin Headline",
        "home_bulletin_text": "Custom announcement body text.",
        "home_bulletin_link": "category/bejson/index.html",
        "home_bulletin_link_label": "Explore Category",
    })
    publisher_mod._execute()
    bulletin_index_html = (builds_dir / "index.html").read_text(encoding="utf-8")
    assert "home-bulletin-card" in bulletin_index_html
    assert "home-bulletin-mode-standard" in bulletin_index_html
    assert "SYSTEM BULLETIN" in bulletin_index_html
    assert "Custom Bulletin Headline" in bulletin_index_html
    assert "Explore Category" in bulletin_index_html
    assert "youtube.com/embed" not in bulletin_index_html

    # Swap to Video Bulletin mode on the same Home_Bulletin_Skeleton.html
    publisher_mod._save_skeleton_config({
        "active_home_skeleton": "Home_Bulletin_Skeleton.html",
        "home_bulletin_mode": "video",
        "home_bulletin_video_url": "https://youtu.be/M7lc1UVf-VE",
    })
    publisher_mod._execute()
    video_index_html = (builds_dir / "index.html").read_text(encoding="utf-8")
    assert "home-bulletin-mode-video" in video_index_html
    assert "https://www.youtube.com/embed/M7lc1UVf-VE" in video_index_html


def test_publisher_routes_render_tabs_and_persist_skeleton_settings(isolated_publisher_env):
    client = publisher_mod.app.test_client()
    headers = _basic_auth_headers()

    get_resp = client.get("/publish", headers=headers)
    assert get_resp.status_code == 200
    body_text = get_resp.get_data(as_text=True)
    assert "Skeleton &amp; Layout Control Center" in body_text
    assert "Homepage Body (Local)" in body_text
    assert "Global Shell (Global)" in body_text
    assert "Home_Bulletin_Skeleton.html" in body_text

    post_resp = client.post(
        "/publish/skeletons/save",
        data={
            "active_home_skeleton": "Home_Bulletin_Skeleton.html",
            "home_bulletin_enabled": "true",
            "home_bulletin_mode": "video",
            "home_bulletin_badge": "VIDEO PIN",
            "home_bulletin_title": "Architecture Walkthrough",
            "home_bulletin_video_url": "M7lc1UVf-VE",
            "submit_action": "save",
        },
        headers=headers,
    )
    assert post_resp.status_code == 302

    saved_conf = publisher_mod._get_skeleton_config()
    assert saved_conf["active_home_skeleton"] == "Home_Bulletin_Skeleton.html"
    assert saved_conf["home_bulletin_mode"] == "video"
    assert saved_conf["home_bulletin_badge"] == "VIDEO PIN"
    assert saved_conf["home_bulletin_title"] == "Architecture Walkthrough"


def test_home_feed_visibility_toggle(isolated_publisher_env):
    """Verify that home_feed_enabled can hide or show the feed section."""
    env = isolated_publisher_env
    builds_dir = env["builds_dir"]

    # 1. Enabled (Default)
    publisher_mod._save_skeleton_config({
        "active_home_skeleton": "Home_Bulletin_Skeleton.html",
        "home_feed_enabled": "true",
    })
    publisher_mod._execute()
    html_shown = (builds_dir / "index.html").read_text(encoding="utf-8")
    assert '<div class="home-feed-section" style="">' in html_shown
    assert "Latest Entries" in html_shown

    # 2. Disabled (Custom bulletin page without feed)
    publisher_mod._save_skeleton_config({
        "active_home_skeleton": "Home_Bulletin_Skeleton.html",
        "home_feed_enabled": "false",
    })
    publisher_mod._execute()
    html_hidden = (builds_dir / "index.html").read_text(encoding="utf-8")
    assert '<div class="home-feed-section" style="display:none;">' in html_hidden


def test_home_category_bar_dock_strip_positions(isolated_publisher_env):
    """Verify single-row horizontal scroll category dock strip rendering above, below, or hidden."""
    env = isolated_publisher_env
    builds_dir = env["builds_dir"]

    # 1. Below Bulletin
    publisher_mod._save_skeleton_config({
        "active_home_skeleton": "Home_Bulletin_Skeleton.html",
        "home_category_bar_position": "below_bulletin",
    })
    publisher_mod._execute()
    html_below = (builds_dir / "index.html").read_text(encoding="utf-8")
    assert "home-category-bar" in html_below
    assert "home-category-pill" in html_below
    assert "category/bejson/index.html" in html_below
    pos_bulletin = html_below.find("home-bulletin-card")
    pos_cat_bar = html_below.find("home-category-bar-wrap")
    assert pos_bulletin != -1 and pos_cat_bar != -1
    assert pos_bulletin < pos_cat_bar, "Category bar should render AFTER bulletin when positioned below"

    # 2. Above Bulletin
    publisher_mod._save_skeleton_config({
        "active_home_skeleton": "Home_Bulletin_Skeleton.html",
        "home_category_bar_position": "above_bulletin",
    })
    publisher_mod._execute()
    html_above = (builds_dir / "index.html").read_text(encoding="utf-8")
    pos_bulletin_2 = html_above.find("home-bulletin-card")
    pos_cat_bar_2 = html_above.find("home-category-bar-wrap")
    assert pos_bulletin_2 != -1 and pos_cat_bar_2 != -1
    assert pos_cat_bar_2 < pos_bulletin_2, "Category bar should render BEFORE bulletin when positioned above"

    # 3. Hidden / None
    publisher_mod._save_skeleton_config({
        "active_home_skeleton": "Home_Bulletin_Skeleton.html",
        "home_category_bar_position": "none",
    })
    publisher_mod._execute()
    html_none = (builds_dir / "index.html").read_text(encoding="utf-8")
    assert '<div class="home-category-bar-wrap">' not in html_none
    assert '<nav class="home-category-bar"' not in html_none


def test_publisher_routes_persist_feed_and_category_bar_options(isolated_publisher_env):
    """Verify form submission preserves home_feed_enabled and home_category_bar_position."""
    client = publisher_mod.app.test_client()
    headers = _basic_auth_headers()

    get_resp = client.get("/publish", headers=headers)
    assert get_resp.status_code == 200
    body_text = get_resp.get_data(as_text=True)
    assert "Homepage Feed Display" in body_text
    assert "Category Inline Dock Strip Position" in body_text

    post_resp = client.post(
        "/publish/skeletons/save",
        data={
            "active_home_skeleton": "Home_Bulletin_Skeleton.html",
            "home_feed_enabled": "false",
            "home_category_bar_position": "above_bulletin",
        },
        headers=headers,
    )
    assert post_resp.status_code == 302

    saved_conf = publisher_mod._get_skeleton_config()
    assert saved_conf["home_feed_enabled"] == "false"
    assert saved_conf["home_category_bar_position"] == "above_bulletin"

