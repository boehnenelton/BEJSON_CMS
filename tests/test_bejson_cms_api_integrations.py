"""
Name:           test_bejson_cms_api_integrations.py
Description:    Verification suite for API Integrations & Syndication section
                (Cloudflare, Google Blogger, Substack) in BEJSON_CMS_Publisher.py.
Version:        1.0.0
Date Created:   2026-11-14
Author Credit:  Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
RELATIONAL_ID:  4f8a32b1-91a7-4e63-b8f2-1d587c69a031
License:        PolyForm-Noncommercial-1.0.0
"""

import base64
import os
import sys

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_LIB = os.path.join(PROJECT_ROOT, "src", "lib")
SRC_WEB = os.path.join(PROJECT_ROOT, "src", "web")
for path_entry in (SRC_LIB, SRC_WEB):
    if path_entry not in sys.path:
        sys.path.insert(0, path_entry)

import BEJSON_CMS_Publisher as publisher_mod


def _basic_auth_headers():
    user_name = os.environ.get("CMS_USER", "admin")
    user_pass = os.environ.get("CMS_PASSWORD", "changeme")
    encoded_token = base64.b64encode(f"{user_name}:{user_pass}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {encoded_token}"}


def test_get_cloudflare_config_resolves():
    """Verify get_cloudflare_config returns dict with project_name and token keys."""
    cfg = publisher_mod.get_cloudflare_config(publisher_mod.db)
    assert isinstance(cfg, dict)
    assert "project_name" in cfg
    assert "account_id" in cfg
    assert "api_token" in cfg


def test_blogger_and_substack_decoupled_from_publisher():
    """Verify get_blogger_config and get_substack_config have been moved out of Publisher."""
    assert not hasattr(publisher_mod, "get_blogger_config")
    assert not hasattr(publisher_mod, "get_substack_config")


def test_publish_dashboard_contains_cloudflare_and_excludes_blogger_substack():
    """Verify /publish dashboard renders Cloudflare Pages and excludes Blogger / Substack."""
    client = publisher_mod.app.test_client()
    resp = client.get("/publish", headers=_basic_auth_headers())
    assert resp.status_code == 200
    html_text = resp.get_data(as_text=True)

    assert "Cloudflare Pages" in html_text
    assert 'action="/publish/cloudflare"' in html_text
    assert 'action="/publish/blogger"' not in html_text
    assert 'action="/publish/substack"' not in html_text


def test_publish_routes_registered():
    """Verify Cloudflare route is registered on Publisher while Blogger and Substack are removed."""
    rules = [rule.rule for rule in publisher_mod.app.url_map.iter_rules()]
    assert "/publish/cloudflare" in rules
    assert "/publish/blogger" not in rules
    assert "/publish/substack" not in rules
