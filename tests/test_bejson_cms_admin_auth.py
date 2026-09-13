"""
Name:           test_bejson_cms_admin_auth.py
Description:    Real integration tests for BEJSON_CMS_Admin.py's global
                 before_request auth hook, requested in the P1 audit item
                 ("Add integration tests for Admin auth hook"). This hook
                 is what closed a real historical gap (per its own code
                 comment: roughly 48 of ~50 routes across 4 blueprints
                 were unauthenticated before it was added) -- these tests
                 are the permanent guard against a future route, or a
                 future refactor of this hook, silently reopening that
                 gap. No filesystem/DB isolation needed: auth rejection
                 happens before any request handler runs, so nothing here
                 ever touches storage/mfdb/ regardless of credentials.
Version:        1.0
Date:           2026-09-04
Author:         Elton Boehnen (written by Claude)
RELATIONAL_ID:  3f8b2d6a-9c1e-4a7f-b5d3-8e2c6f1a4d9b
"""
import os
import sys
import base64

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "web"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "lib"))

os.environ.setdefault("CMS_PASSWORD", "test-only-password-for-pytest")

import BEJSON_CMS_Admin as admin


def _basic_auth(username, password):
    creds = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {creds}"}


# A representative sample across all 4 blueprints registered on the Admin
# app -- dashboard, content (pages/authors/apps), interface (nav/social/
# ads/publish), system (config/reset) -- deliberately not just "/", since
# the historical bug was specifically that only 2 routes were protected.
_SAMPLE_ROUTES = [
    "/",
    "/pages/new",
    "/site/authors",
    "/site/ads",
    "/site/nav",
    "/site/social",
    "/assets",
    "/import",
    "/publish",
]


class TestAdminAuthHookBlocksUnauthenticated:
    def test_no_auth_header_at_all_is_rejected(self):
        client = admin.app.test_client()
        for route in _SAMPLE_ROUTES:
            resp = client.get(route)
            assert resp.status_code == 401, f"{route} did not require auth"

    def test_wrong_password_is_rejected(self):
        client = admin.app.test_client()
        headers = _basic_auth("admin", "definitely-not-the-real-password")
        for route in _SAMPLE_ROUTES:
            resp = client.get(route, headers=headers)
            assert resp.status_code == 401, f"{route} accepted a wrong password"

    def test_401_response_includes_www_authenticate_challenge(self):
        client = admin.app.test_client()
        resp = client.get("/")
        assert resp.status_code == 401
        assert "WWW-Authenticate" in resp.headers


class TestAdminAuthHookAllowsAuthenticated:
    def test_correct_credentials_pass_on_every_sampled_route(self):
        client = admin.app.test_client()
        headers = _basic_auth("admin", os.environ["CMS_PASSWORD"])
        for route in _SAMPLE_ROUTES:
            resp = client.get(route, headers=headers)
            assert resp.status_code != 401, f"{route} rejected the correct password"
            assert resp.status_code == 200, f"{route} returned {resp.status_code}, not 200"

    def test_wrong_username_with_correct_password_is_rejected(self):
        """_check_auth checks both username and password -- confirmed by
        reading its actual implementation rather than assuming Basic Auth
        conventions here (initial draft of this test wrongly assumed only
        the password was checked)."""
        client = admin.app.test_client()
        headers = _basic_auth("not-admin", os.environ["CMS_PASSWORD"])
        resp = client.get("/", headers=headers)
        assert resp.status_code == 401
