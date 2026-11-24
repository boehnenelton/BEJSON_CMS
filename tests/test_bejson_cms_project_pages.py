"""
Name:           test_bejson_cms_project_pages.py
Description:    Verification suite for dedicated Project Pages (page_type='project'),
                ProjectPageRenderer, Projects_Feed_Skeleton.html, Admin /projects CRUD,
                and static Publisher /projects/index.html generation.
Version:        1.0.0
Date Created:   2026-11-24
Author Credit:  Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
RELATIONAL_ID:  8001f552-b9cc-44a4-a93b-b38925d8b0de
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

import BEJSON_CMS_Admin as admin_mod
import BEJSON_CMS_Publisher as publisher_mod
import BEJSON_CMS_Renderers as renderers_mod
import BEJSON_CMS_Shared as shared_mod


def _basic_auth_headers():
    user_name = os.environ.get("CMS_USER", "admin")
    user_pass = os.environ.get("CMS_PASSWORD", "changeme")
    encoded_token = base64.b64encode(f"{user_name}:{user_pass}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {encoded_token}"}


def test_project_page_renderer_registered_and_renders_assets():
    """Verify ProjectPageRenderer renders featured video, GitHub, Gemini Notepad, and asset links."""
    assert "project" in renderers_mod.RENDERER_REGISTRY

    rendered = renderers_mod.render_page(
        "project",
        {
            "page_title": "BEJSON Flow",
            "html_body": "<p>Visual flow engine.</p>",
            "page_featured_video_url": "https://www.youtube.com/watch?v=h7WtEqdrKm8",
        },
        meta_data={
            "project_github_url": "https://github.com/boehnenelton/BEJSON_Flow.git",
            "project_bejson_era": "104",
            "project_gemini_notepad_url": "https://gemini.google.com/share/notepad-123",
            "project_featured_links": "Play Live | https://sword-slasher.pages.dev",
            "project_youtube_links": "Walkthrough | https://youtu.be/dQw4w9WgXcQ",
            "project_asset_links": "Live Demo | https://boehnenelton2024.pages.dev/flow",
        },
    )

    assert "https://www.youtube.com/embed/h7WtEqdrKm8" in rendered
    assert "https://github.com/boehnenelton/BEJSON_Flow\"" in rendered
    assert ".git\"" not in rendered
    assert "BEJSON 104" in rendered
    assert "https://gemini.google.com/share/notepad-123" in rendered
    assert "Play Live" in rendered
    assert "https://sword-slasher.pages.dev" in rendered
    assert "Walkthrough" in rendered
    assert "https://youtu.be/dQw4w9WgXcQ" in rendered
    assert "Live Demo" in rendered
    assert "https://boehnenelton2024.pages.dev/flow" in rendered
    assert "<p>Visual flow engine.</p>" in rendered


def test_projects_feed_skeleton_registered_and_present():
    """Verify Projects_Feed_Skeleton.html exists and active_projects_skeleton slot is registered."""
    skel_path = os.path.join(PROJECT_ROOT, "resources", "templates", "Projects_Feed_Skeleton.html")
    assert os.path.exists(skel_path)
    assert "active_projects_skeleton" in publisher_mod.SKELETON_SLOT_DEFINITIONS
    assert publisher_mod.DEFAULT_SKELETON_SITE_CONFIG["active_projects_skeleton"] == "Projects_Feed_Skeleton.html"
    assert "Projects_Feed_Skeleton.html" in publisher_mod.SKELETON_DISPLAY_LABELS


def test_admin_projects_nav_and_routes():
    """Verify Projects section is in NAV_SECTIONS and /projects routes respond."""
    assert "projects" in shared_mod.NAV_SECTIONS
    assert shared_mod.NAV_SECTIONS["projects"]["href"] == "/projects"

    client = admin_mod.app.test_client()
    resp_list = client.get("/projects", headers=_basic_auth_headers())
    assert resp_list.status_code == 200
    assert "Projects" in resp_list.get_data(as_text=True)

    resp_new = client.get("/projects/new", headers=_basic_auth_headers())
    assert resp_new.status_code == 200
    html_new = resp_new.get_data(as_text=True)
    assert "project_github_url" in html_new
    assert "project_gemini_notepad_url" in html_new
    assert "project_featured_links" in html_new
    assert "addFeaturedLinkRow" in html_new
    assert "project_youtube_links" in html_new
    assert "project_asset_links" in html_new
    assert "page_featured_video_url" in html_new


def test_global_skeleton_contains_projects_nav():
    """Verify Global_Skeleton.html includes Projects nav dropdown and {{nav_projects}}."""
    global_skel_path = os.path.join(PROJECT_ROOT, "resources", "templates", "Global_Skeleton.html")
    with open(global_skel_path, "r", encoding="utf-8") as file_handle:
        content = file_handle.read()
    assert "projects/index.html" in content
    assert "{{nav_projects}}" in content


def test_github_stats_extraction_and_zero_token_leak():
    """Verify GitHub owner/repo extraction from featured links, static stats render, and zero token leak."""
    owner_repo = publisher_mod._extract_github_owner_repo({
        "project_github_url": "",
        "project_featured_links": "Source Repo | https://github.com/boehnenelton/BEJSON_105.git",
    })
    assert owner_repo == ("boehnenelton", "BEJSON_105")

    fake_secret = "ghp_SUPERSECRETTOKEN1234567890"
    rendered = renderers_mod.render_page(
        "project",
        {"page_title": "BEJSON 105", "html_body": "<p>Body</p>"},
        meta_data={
            "project_github_url": "https://github.com/boehnenelton/BEJSON_105.git",
            "project_bejson_era": "105",
            "project_github_stats": {
                "full_name": "boehnenelton/BEJSON_105",
                "stars": 12,
                "forks": 3,
                "open_issues": 1,
                "language": "Python",
                "license": "PolyForm-Noncommercial-1.0.0",
                "pushed_at": "2026-11-24T00:00:00Z",
            },
        },
    )
    assert "GitHub Telemetry" in rendered
    assert "boehnenelton/BEJSON_105" in rendered
    assert "12" in rendered
    assert fake_secret not in rendered


def test_compact_horizontal_project_link_strip_and_github_hub():
    """Verify compact horizontally scrolling link strip, GitHub Hub nav, and stats cache round-trip."""
    import BEJSON_CMS_GitHub as gh_mod
    assert "github" in shared_mod.NAV_SECTIONS
    assert shared_mod.NAV_SECTIONS["github"]["href"] == "/github"
    strip = renderers_mod.render_project_link_strip(
        "BEJSON_105",
        "../../../projects/bejson-105/index.html",
        {
            "project_bejson_era": "105",
            "project_github_url": "https://github.com/boehnenelton/BEJSON_105.git",
            "project_featured_links": "Benchmark | https://bejson-metrics.pages.dev",
            "project_github_stats": {"full_name": "boehnenelton/BEJSON_105", "stars": 7, "forks": 2, "is_cached": True},
        },
    )
    assert "overflow-x:auto" in strip
    assert "flex-wrap:nowrap" in strip
    assert "BEJSON 105" in strip
    assert "https://github.com/boehnenelton/BEJSON_105\"" in strip
    assert ".git\"" not in strip
    assert "Benchmark" in strip
    assert "(Cached)" in strip
