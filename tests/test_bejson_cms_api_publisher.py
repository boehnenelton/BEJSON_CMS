"""
Name:           test_bejson_cms_api_publisher.py
Description:    Verification test suite for independent BEJSON_CMS_APIPublisher service,
                verifying CMS database reading, Blogger/Substack configuration,
                group key normalization, cross-platform lineage correlation, and REST endpoints.
Version:        1.0.0
Date Created:   2026-11-24
Author Credit:  Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
RELATIONAL_ID:  2a3b4c5d-6e7f-8091-a2b3-c4d5e6f70819
License:        PolyForm-Noncommercial-1.0.0
"""

import base64
import os
import sys
from pathlib import Path
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_LIB = os.path.join(PROJECT_ROOT, "src", "lib")
SRC_WEB = os.path.join(PROJECT_ROOT, "src", "web")
for path_entry in (SRC_LIB, SRC_WEB):
    if path_entry not in sys.path:
        sys.path.insert(0, path_entry)

import BEJSON_CMS_APIPublisher as api_pub


def _basic_auth_headers():
    user_name = os.environ.get("CMS_USER", "admin")
    user_pass = os.environ.get("CMS_PASSWORD", "changeme")
    encoded_token = base64.b64encode(f"{user_name}:{user_pass}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {encoded_token}"}


def test_normalize_group_key():
    """Verify group key normalization removes noise and formats slug-like keys."""
    assert api_pub.normalize_group_key("The Zero-SQL BEJSON CMS Architecture") == "the-zero-sql-bejson-cms-architecture"
    assert api_pub.normalize_group_key("Polyglot Part 1: BEJSON 104 Core Across Python, JS, TS, and Bash!") == "polyglot-part-1-bejson-104-core-across-python-js-ts-and-bash"
    assert api_pub.normalize_group_key("") == ""


def test_blogger_config_resolution():
    """Verify get_blogger_config extracts necessary OAuth fields without raising."""
    cfg = api_pub.get_blogger_config()
    assert isinstance(cfg, dict)
    assert "blog_id" in cfg
    assert "client_id" in cfg
    assert "client_secret" in cfg
    assert "refresh_token" in cfg
    assert "api_key" in cfg


def test_substack_config_resolution():
    """Verify get_substack_config extracts session and subdomain fields."""
    cfg = api_pub.get_substack_config()
    assert isinstance(cfg, dict)
    assert "session_sid" in cfg
    assert "subdomain" in cfg
    assert "base_url" in cfg


def test_read_cms_posts():
    """Verify reading CMS database posts extracts records with tracking metadata."""
    posts = api_pub.read_cms_posts()
    assert isinstance(posts, list)
    assert len(posts) > 0

    first_post = posts[0]
    assert "cms_uuid" in first_post
    assert "title" in first_post
    assert "slug" in first_post
    assert "group_key" in first_post
    assert "canonical_path" in first_post
    assert first_post["platform"] == "cms"


def test_correlate_lineage_matching():
    """Verify correlate_lineage clusters matching content across platforms."""
    mock_cms = [
        {"cms_uuid": "uuid-1", "title": "Article One", "slug": "article-one", "group_key": "article-one", "platform": "cms"},
        {"cms_uuid": "uuid-2", "title": "Article Two", "slug": "article-two", "group_key": "article-two", "platform": "cms"},
    ]
    mock_blogger = [
        {"blogger_id": "b-1", "title": "Article One", "url": "https://blog.test/1", "group_key": "article-one", "platform": "blogger"},
        {"blogger_id": "b-3", "title": "Article Three", "url": "https://blog.test/3", "group_key": "article-three", "platform": "blogger"},
    ]
    mock_substack = [
        {"substack_id": "s-1", "title": "Article One", "slug": "article-one", "url": "https://sub.test/1", "group_key": "article-one", "platform": "substack"},
    ]

    lineage = api_pub.correlate_lineage(mock_cms, mock_blogger, mock_substack)
    assert len(lineage) == 3

    # Find Article One in lineage
    art1 = next(item for item in lineage if item["group_key"] == "article-one")
    assert art1["cms"] is not None
    assert art1["blogger"] is not None
    assert art1["substack"] is not None
    assert set(art1["syndicated_to"]) == {"cms", "blogger", "substack"}

    # Find Article Two (only on CMS)
    art2 = next(item for item in lineage if item["group_key"] == "article-two")
    assert art2["cms"] is not None
    assert art2["blogger"] is None
    assert art2["substack"] is None
    assert art2["syndicated_to"] == ["cms"]

    # Find Article Three (only on Blogger)
    art3 = next(item for item in lineage if item["group_key"] == "article-three")
    assert art3["cms"] is None
    assert art3["blogger"] is not None
    assert art3["syndicated_to"] == ["blogger"]


def test_flask_dashboard_and_api_routes():
    """Verify independent Flask app routes respond with expected JSON/HTML."""
    client = api_pub.app.test_client()

    # Dashboard GET
    resp = client.get("/", headers=_basic_auth_headers())
    assert resp.status_code == 200
    html_text = resp.get_data(as_text=True)
    assert "API Publisher" in html_text
    assert "Cross-Platform Content Lineage" in html_text

    # Status API GET
    resp_status = client.get("/api/status", headers=_basic_auth_headers())
    assert resp_status.status_code == 200
    data_status = resp_status.get_json()
    assert data_status["status"] == "online"
    assert "counts" in data_status
    assert data_status["counts"]["cms_posts"] > 0

    # CMS API GET
    resp_cms = client.get("/api/cms", headers=_basic_auth_headers())
    assert resp_cms.status_code == 200
    data_cms = resp_cms.get_json()
    assert data_cms["count"] > 0
    assert len(data_cms["posts"]) == data_cms["count"]
