"""
SCRIPT_NAME:    BEJSON_CMS_Publisher
SCRIPT_VERSION: 16.4
RELATIONAL_ID:  b386633b-f4ea-4910-9f37-aa2f7acc7ae6
AUTHOR:         Elton Boehnen
CHANGE (2026-08-05): Variable naming remediation pass (Part 2/Part 3 items
13,14,27,31,34,35,36,37,43,44,45) - renamed generic single/short-letter
locals (out, css, env, apps, cats, body, link, text, path, unit, line, cmd)
to self-describing PascalCase names per Sec 3.3. No logic changes.
CHANGE (2026-07-07): Fixed the admin dashboard forcing horizontal scroll.
Root cause: three spots display a raw absolute path (output_dir, SKEL_DIR,
STYLESHEETS_DIR) inside <code> tags with no word-break - a long unbroken
path (no spaces to wrap at) forces its container wider than the viewport.
One of the three is also the last cell in a table row, where a CSS rule
(td:last-child{white-space:nowrap}) actively blocks wrapping regardless of
word-break, so that one needed an inline white-space:normal override too
(inline style beats the external rule). In this sandbox the paths are
short (~30 chars) so the overflow doesn't show, but on the actual Android
deployment (long storage paths, extracted folder names) they're easily
long enough to trigger it - confirmed the mechanism even without
reproducing the visual symptom here.
CHANGE (2026-07-07): Added _generate_excerpt() - pages had no feed summary
because the only description source was an optional meta_description field
nothing in the UI sets, so it was always empty. Falls back to a 30-word
auto-excerpt of the actual page content with a trailing "..." when
truncated. Also fixed app-card images looking zoomed-in/cropped compared
to pages: both used identical object-fit:cover, but app images are
typically square icons vs. pages' wide banners, so cover cropped them
hard. App-type cards now use object-fit:contain instead.
CHANGE (2026-07-07): Removed a 61-line dead _CSS_SHARED assignment (367-427)
that was fully shadowed by a second assignment 8 lines later (475) before
ever being read - confirmed via full-file usage scan, only 2 reads exist
(both after line 475). Also fixed a real bug in the surviving block: the
CSS property "box-box: border-box" is not valid CSS (should be
"box-sizing"), meaning every published site built by this tool had that
line silently do nothing.
DESCRIPTION:    Flask conversion merging:
                  - BEJSON_Web_Publisher.py  (Tkinter GUI removed)
                  - Cleanup_Tool.py          (Tkinter GUI removed)
                  - BEJSON_Skeleton_Builder  (SkeletonBuilder class kept, __main__ block removed)

                HTML Skeleton files (HTML_Skeletons/*.html) stay separate on disk, unchanged.
                Stylesheet files (Stylesheets/*.css) are exported on first launch.
                  - light.css  : default light theme (copy to build your own)
                  - dark.css   : dark theme alternative
                Selected stylesheet is copied to output/style.css on each build.
                BEJSON database structures are never modified.
                Page editing functionality removed — publisher is build-only.

REQUIRES (same directory or on sys.path):
    BEJSON_Standard_Lib.py
    BEJSON_Extended_Lib.py
    HTML_Skeletons/   <- directory of skeleton HTML files
    Stylesheets/      <- auto-created with light.css + dark.css on launch

RUNS ON: http://localhost:5001
"""

import os
import re
import json
import random
import shutil
import threading
import http.server
import socketserver
import subprocess
from datetime import datetime
from flask import Flask, request, redirect, url_for, jsonify, render_template_string

# ==============================================================================
# CLOUDFLARE CONFIG
# ==============================================================================
CF_KEYS = {"ACCOUNT_ID": "", "API_TOKEN": ""}
CF_KEYS_PATH = os.path.expanduser("~/.env/cloudflare_keys.bejson")
if os.path.exists(CF_KEYS_PATH):
    try:
        with open(CF_KEYS_PATH, "r") as f:
            cf_data = json.load(f)
            CF_KEYS = {row[0]: row[1] for row in cf_data["Values"]}
    except Exception:
        pass

# ==============================================================================
# PATHS  (identical to the originals)
# ==============================================================================

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STORAGE_ROOT = os.path.join(PROJECT_ROOT, "storage")
MFDB_DIR = os.path.join(STORAGE_ROOT, "mfdb")
MANIFEST_PATH = os.path.join(MFDB_DIR, "site_master", "104a.mfdb.bejson")
PAGES_DB_DIR = os.path.join(MFDB_DIR, "pages_db")
APPS_STORAGE = os.path.join(MFDB_DIR, "standalone_apps")
ASSETS_SRC = os.path.join(MFDB_DIR, "assets")
EXPORTS_DIR = os.path.join(STORAGE_ROOT, "exports")
DEFAULT_OUT_DIR = os.path.join(STORAGE_ROOT, "builds")

# Must match BEJSON_CMS_Shared.py's DEFAULT_FEATURED_IMAGE exactly -- duplicated
# here rather than imported, matching this file's existing standalone-constant
# pattern (it already recomputes PROJECT_ROOT etc. independently rather than
# importing from the blueprint apps). If the seeded default image filename
# ever changes, update it in both places.
DEFAULT_FEATURED_IMAGE = "default_page_image.webp"

RESOURCES_ROOT = os.path.join(PROJECT_ROOT, "resources")
SKEL_DIR = os.path.join(RESOURCES_ROOT, "templates")
STYLESHEETS_DIR = os.path.join(RESOURCES_ROOT, "styles")

for d in [MFDB_DIR, PAGES_DB_DIR, APPS_STORAGE, ASSETS_SRC, EXPORTS_DIR, DEFAULT_OUT_DIR, SKEL_DIR, STYLESHEETS_DIR]:
    os.makedirs(d, exist_ok=True)

# Import BEJSON Libraries
# Import New MFDB Orchestrator
import sys
# (Duplicate PROJECT_ROOT removed by patch_cms.py)
LIB_DIR = os.path.join(PROJECT_ROOT, "src", "lib")
if LIB_DIR not in sys.path:
    sys.path.append(LIB_DIR)
import lib_bejson_CMS_cms_core as CMSCore
import lib_bejson_CMS_cms_ports as CMSPorts

CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")
PUBLISHER_PORT = CMSPorts.get_port(CONFIG_PATH, "publisher_port", "CMS_PUBLISHER_PORT")

# ==============================================================================
# FLASK APP
# ==============================================================================

app = Flask(__name__)
db = CMSCore.CMSCore(MANIFEST_PATH)

from BEJSON_CMS_Shared import _check_auth, _unauthorized


@app.before_request
def _enforce_auth_everywhere():
    # SECURITY FIX: this standalone app (factory reset, live publish/build,
    # preview server control) had zero authentication -- every route
    # completely open, including /reset/confirm which wipes the live
    # database. Matches the same before_request gate BEJSON_CMS_Admin.py
    # already enforces on its four blueprints.
    Request_Basic_Auth_Header = request.authorization
    if not Request_Basic_Auth_Header or not _check_auth(Request_Basic_Auth_Header.username, Request_Basic_Auth_Header.password):
        return _unauthorized()


def _safe_slug(value, fallback="unknown"):
    """Guard against None values becoming the literal string 'None' in path components."""
    if value is None or str(value).lower() == "none" or str(value).strip() == "":
        return fallback
    return str(value).strip()

if os.path.exists(MANIFEST_PATH): db.mount()
app.secret_key = os.environ.get('CMS_SECRET_KEY') or os.urandom(24).hex()  # Set CMS_SECRET_KEY env var

# ==============================================================================
# GLOBAL RUNTIME STATE
# ==============================================================================

_state = {
    "output_dir":    DEFAULT_OUT_DIR,
    "build_log":     [],
    "build_running": False,
    "srv_running":   False,
    "srv_port":      8000,
    "httpd":         None,
    "stylesheet":    "light.css",
}

# ==============================================================================
# SKELETON BUILDER
# Ported directly from BEJSON_Skeleton_Builder.py — SkeletonBuilder class.
# __main__ / tkinter blocks removed. Logic is 100% identical.
# Skeletons are written to HTML_Skeletons/ on disk, never embedded.
# ==============================================================================

OUTPUT_DIR = SKEL_DIR   # mirrors the original module-level constant

class SkeletonBuilder:
    def __init__(self, force=False):
        self.force = force
        self._ensure_output_dir()

    def _ensure_output_dir(self):
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
        except OSError:
            pass

    def build_all_skeletons(self):
        try:
            self.build_global_skeleton()
            self.build_article_skeleton()
            self.build_app_skeleton()
            self.build_home_skeleton()
            self.build_category_skeleton()
            self.build_author_skeleton()
            self.build_apps_feed_skeleton()
            return True, f"Successfully built 7 skeletons in:\n{OUTPUT_DIR}"
        except Exception as e:
            return False, str(e)

    def build_global_skeleton(self):
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{page_title}} | {{site_title}}</title>
    <meta name="description" content="{{seo_description}}">
    <meta name="author" content="{{seo_author}}">
    <meta property="og:title" content="{{page_title}}">
    <meta property="og:description" content="{{seo_description}}">
    <meta property="og:image" content="{{seo_image}}">
    <meta property="og:type" content="website">
    <meta property="og:url" content="{{current_url}}">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&family=Source+Code+Pro&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="{{rel_prefix}}style.css">
</head>
<body>
    <header class="site-header">
        <div class="container">
            <div class="nav-wrap">
                <a href="{{rel_prefix}}index.html" class="logo">{{site_title}}</a>
                <nav>
                    <ul class="nav-menu" id="main-nav">
                        <li><a href="{{rel_prefix}}index.html">Home</a></li>
                        <li class="nav-dropdown">
                            <a href="#">Categories <span class="chevron">▼</span></a>
                            <ul class="dropdown-content">
                                {{sidebar_categories}}
                            </ul>
                        </li>
                        <li><a href="{{rel_prefix}}apps/index.html">Applications</a></li>
                        {{custom_nav_links}}
                    </ul>
                </nav>
                <button class="mobile-menu-toggle" onclick="toggleMenu()">&#9776;</button>
            </div>
        </div>
    </header>
    
    <div class="container main-layout">
        <main class="main-content">
            {{main_content_injection}}
        </main>
        <aside class="sidebar">
            <div class="sidebar-collapsible active" id="collapse-explore">
                <button class="collapse-trigger" onclick="toggleCollapse('collapse-explore')">
                    Explore <span class="chevron">▼</span>
                </button>
                <div class="collapse-content">
                    <ul class="category-list">
                        {{sidebar_categories}}
                    </ul>
                </div>
            </div>

            <div class="sidebar-collapsible" id="collapse-social">
                <button class="collapse-trigger" onclick="toggleCollapse('collapse-social')">
                    Connect <span class="chevron">▼</span>
                </button>
                <div class="collapse-content" style="padding: 20px;">
                    <div class="social-links-sidebar">
                        {{social_media_links}}
                    </div>
                </div>
            </div>
        </aside>
    </div>

    <footer class="site-footer">
        <div class="container">
            <div class="footer-content">
                <div class="copyright">&copy; {{current_year}} <strong>{{site_title}}</strong></div>
                <div class="footer-links" style="display:flex; gap:20px;">
                    <a href="{{rel_prefix}}index.html">Home</a>
                    <a href="{{rel_prefix}}apps/index.html">Apps</a>
                </div>
            </div>
        </div>
    </footer>
    <div id="lightbox" class="lightbox">
        <span class="lightbox-close">&times;</span>
        <img class="lightbox-content" id="lightbox-img">
    </div>
    <script>
        function toggleMenu() {
            const nav = document.getElementById('main-nav');
            nav.classList.toggle('active');
        }

        function toggleCollapse(id) {
            const el = document.getElementById(id);
            el.classList.toggle('active');
        }

        const lightbox = document.getElementById('lightbox');
        const lightboxImg = document.getElementById('lightbox-img');
        const closeBtn = document.querySelector('.lightbox-close');
        document.querySelectorAll('.article-body img, .article-featured-image, .card-img').forEach(img => {
            img.onclick = function(){
                lightbox.style.display = "flex";
                lightboxImg.src = this.src;
            }
        });
        closeBtn.onclick = function() { lightbox.style.display = "none"; }
        lightbox.onclick = function(e) { if(e.target !== lightboxImg) lightbox.style.display = "none"; }
    </script>
</body>
</html>"""
        self._write_file("Global_Skeleton.html", html)

    def build_article_skeleton(self):
        html = """<article>
    <header class="article-header">
        <div class="article-meta">{{category}} &bull; {{timestamp}}</div>
        <h1 class="article-title">{{article_title}}</h1>
    </header>
    {{featured_image_html}}
    <div class="article-body">{{article_body}}</div>
    
    {{related_content_section}}
</article>"""
        self._write_file("Article_Skeleton.html", html)

    def build_app_skeleton(self):
        html = """<article>
    <header class="article-header">
        <span class="article-meta">Application</span>
        <h1 class="article-title">{{app_name}}</h1>
        <p style="color:#666;">{{category}} &bull; {{timestamp}}</p>
    </header>
    <div class="article-body">
        <div style="background:#F9F9F9; border:1px solid #EEE; padding:20px; margin-bottom:40px;">
            <h3 style="margin-top:0;">Source Code</h3>
            <textarea style="width:100%; height:150px; background:#fff; border:1px solid #ddd; padding:10px; font-family:monospace;" readonly>{{app_source_code}}</textarea>
            <button style="margin-top:10px; background:var(--accent-color); color:white; border:none; padding:10px 20px; font-weight:bold; cursor:pointer;" onclick="navigator.clipboard.writeText(this.previousElementSibling.value)">COPY SOURCE</button>
        </div>
        <hr style="border:0; border-top:1px solid #eee; margin:30px 0;">
        <h3>Documentation</h3>
        <div>{{doc_body}}</div>
    </div>
    
    {{related_content_section}}
</article>"""
        self._write_file("App_Skeleton.html", html)

    def build_home_skeleton(self):
        html = """<div class="home-hero">
    <div class="hero-content">
        <span class="hero-tag">Welcome to the future of content</span>
        <h1 class="hero-title">{{site_title}}</h1>
        <p class="hero-desc">{{site_description}}</p>
    </div>
</div>

<div class="section-divider">
    <h2 class="section-label">Latest Discoveries</h2>
    <div class="label-line"></div>
</div>

<div class="grid">
    {{content_grid}}
</div>

<style>
.home-hero { padding: 120px 0 80px; text-align: left; border-bottom: 1px solid var(--border-color); margin-bottom: 60px; }
.hero-tag { display: inline-block; padding: 6px 12px; background: var(--accent-color); color: white; font-size: 0.7rem; font-weight: 900; text-transform: uppercase; letter-spacing: 2px; border-radius: 2px; margin-bottom: 25px; }
.hero-title { font-size: clamp(3rem, 8vw, 6rem); font-weight: 900; line-height: 0.9; letter-spacing: -4px; color: var(--text-main); margin-bottom: 30px; }
.hero-desc { font-size: 1.4rem; color: var(--text-muted); max-width: 700px; line-height: 1.4; }
.section-divider { display: flex; align-items: center; gap: 20px; margin-bottom: 40px; }
.section-label { font-size: 0.8rem; font-weight: 900; text-transform: uppercase; letter-spacing: 3px; color: var(--accent-color); white-space: nowrap; }
.label-line { height: 1px; background: var(--border-color); flex: 1; }
</style>"""
        self._write_file("Home_Skeleton.html", html)

    def build_category_skeleton(self):
        html = """<div>
    <header class="article-header">
        <span class="article-meta">Browsing Category</span>
        <h1 class="article-title">{{category_name}}</h1>
        <p class="article-meta" style="color:#666; text-transform:none;">{{category_description}}</p>
    </header>
    <div class="grid">{{content_grid}}</div>
</div>"""
        self._write_file("Category_Skeleton.html", html)

    def build_author_skeleton(self):
        html = """<div class="author-profile">
    <div style="text-align:center; padding:40px; background:#F8F9FA; margin-bottom:40px;">
        {{author_img_html}}
        <h1 style="font-size:2.5rem; font-weight:900; margin:15px 0;">{{author_name}}</h1>
        <p style="max-width:600px; margin:0 auto; color:#555;">{{author_bio}}</p>
    </div>
    <h2 style="margin-bottom:20px; color:var(--accent-color); font-weight:800;">Posts by {{author_name}}</h2>
    <div class="grid">{{content_grid}}</div>
</div>"""
        self._write_file("Author_Skeleton.html", html)

    def build_apps_feed_skeleton(self):
        html = """<div class="section-header">
    <h1 class="article-title">Applications</h1>
    <p class="hero-desc" style="margin-top:-10px; margin-bottom:40px;">Professional web tools and standalone interactive experiences.</p>
</div>
<div class="grid">{{content_grid}}</div>"""
        self._write_file("Apps_Feed_Skeleton.html", html)

    def _write_file(self, filename, content):
        path = os.path.join(OUTPUT_DIR, filename)
        if os.path.exists(path) and not self.force:
            # Skeleton exists, do not overwrite unless forced
            return
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)


# ==============================================================================
# STYLESHEET MANAGER
# Writes light.css and dark.css to Stylesheets/ on first launch.
# Users copy and customise these to build their own themes.
# ==============================================================================

_LIGHT_ROOT = """\
:root {
    --bg-body: #FFFFFF;
    --bg-nav: #FFFFFF;
    --bg-card: #FFFFFF;
    --bg-footer: #F8F9FA;
    --text-main: #121212;
    --text-muted: #555555;
    --accent-color: #DE2626;
    --border-color: #E5E5E5;
    --card-border: #EEEEEE;
    --shadow-hover: 0 10px 30px rgba(0,0,0,0.08);
    --font-main: 'Inter', sans-serif;
    --container-width: 1100px;
    --radius: 0px;
    --code-bg: #F4F4F4;
    --code-text: #111111;
    --img-placeholder: #f0f0f0;
    --social-bg: #FFFFFF;
    --social-border: #DDDDDD;
}
"""

_DARK_ROOT = """\
:root {
    --bg-body: #050505;
    --bg-nav: rgba(10, 10, 10, 0.8);
    --bg-card: #0F0F0F;
    --bg-footer: #080808;
    --text-main: #FFFFFF;
    --text-muted: #888888;
    --accent-color: #DE2626;
    --border-color: #1A1A1A;
    --card-border: #151515;
    --shadow-hover: 0 20px 40px rgba(0,0,0,0.6);
    --font-main: 'Inter', sans-serif;
    --container-width: 1200px;
    --radius: 4px;
    --code-bg: #0A0A0A;
    --code-text: #E0E0E0;
    --img-placeholder: #111111;
    --social-bg: #121212;
    --social-border: #222222;
}
"""

_CSS_SHARED = """\
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: var(--font-main); background-color: var(--bg-body); color: var(--text-main); line-height: 1.6; min-height: 100vh; display: flex; flex-direction: column; font-size: 16px; overflow-x: hidden; -webkit-font-smoothing: antialiased; }
a { color: inherit; text-decoration: none; transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1); }
a:hover { color: var(--accent-color); }
ul { list-style: none; }
img { max-width: 100%; height: auto; display: block; }

.container { width: 100%; max-width: var(--container-width); margin: 0 auto; padding: 0 30px; }

.site-header { background: var(--bg-nav); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); color: var(--text-main); height: 80px; display: flex; align-items: center; position: sticky; top: 0; z-index: 100; border-bottom: 1px solid var(--border-color); }
.nav-wrap { display: flex; justify-content: space-between; align-items: center; width: 100%; }
.logo { font-weight: 900; font-size: 1.6rem; color: var(--text-main); letter-spacing: -1.5px; text-transform: uppercase; }
.logo span { color: var(--accent-color); }
.nav-menu { display: flex; gap: 40px; align-items: center; }
.nav-menu a { color: var(--text-main); font-weight: 700; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1.5px; opacity: 0.7; }
.nav-menu a:hover { opacity: 1; color: var(--accent-color); }

.nav-dropdown { position: relative; }
.nav-dropdown .chevron { font-size: 0.6rem; margin-left: 5px; opacity: 0.5; vertical-align: middle; }
.dropdown-content { position: absolute; top: 100%; left: 0; background: var(--bg-card); border: 1px solid var(--border-color); min-width: 220px; box-shadow: var(--shadow-hover); opacity: 0; visibility: hidden; transform: translateY(10px); transition: all 0.3s ease; z-index: 1000; padding: 15px 0; border-radius: var(--radius); }
.nav-dropdown:hover .dropdown-content { opacity: 1; visibility: visible; transform: translateY(0); }
.dropdown-content li a { display: block; padding: 10px 25px; font-size: 0.8rem; text-transform: none; opacity: 0.8; letter-spacing: 0.5px; }
.dropdown-content li a:hover { background: rgba(222, 38, 38, 0.1); opacity: 1; color: var(--accent-color); padding-left: 30px; }

.main-layout { display: flex; gap: 60px; margin-top: 40px; }
.main-content { flex: 1; min-width: 0; text-align: left; }
.sidebar { width: 320px; flex-shrink: 0; text-align: left; }

/* Collapsible Sidebar Styles */
.sidebar-collapsible { margin-bottom: 30px; border: 1px solid var(--border-color); border-radius: var(--radius); background: var(--bg-card); overflow: hidden; }
.collapse-trigger { width: 100%; padding: 15px 20px; background: none; border: none; color: var(--accent-color); font-weight: 900; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 2px; display: flex; justify-content: space-between; align-items: center; cursor: pointer; transition: background 0.3s; }
.collapse-trigger:hover { background: rgba(222, 38, 38, 0.05); }
.collapse-trigger .chevron { transition: transform 0.3s ease; font-size: 0.6rem; }
.sidebar-collapsible.active .collapse-trigger .chevron { transform: rotate(180deg); }
.collapse-content { max-height: 0; overflow: hidden; transition: max-height 0.4s cubic-bezier(0, 1, 0, 1); background: var(--bg-body); }
.sidebar-collapsible.active .collapse-content { max-height: 1000px; transition: max-height 0.4s cubic-bezier(1, 0, 1, 0); }
.category-list { padding: 10px 0; }
.category-list li a { display: block; padding: 12px 20px; font-weight: 700; font-size: 0.85rem; border-bottom: 1px solid var(--border-color); opacity: 0.8; }
.category-list li:last-child a { border-bottom: none; }
.category-list a:hover { opacity: 1; color: var(--accent-color); background: rgba(255,255,255,0.02); padding-left: 25px; }

.card { background: var(--bg-card); border: 1px solid var(--card-border); border-radius: var(--radius); display: flex; flex-direction: column; transition: all 0.3s ease; height: 100%; overflow: hidden; text-align: left; }
.card:hover { transform: translateY(-8px); border-color: var(--accent-color); box-shadow: var(--shadow-hover); }
.card-img-container { width: 100%; height: 220px; background: var(--img-placeholder); overflow: hidden; position: relative; border-bottom: 1px solid var(--border-color); }
.card-img { width: 100%; height: 100%; object-fit: cover; transition: transform 0.6s cubic-bezier(0.165, 0.84, 0.44, 1); }
.card:hover .card-img { transform: scale(1.08); }
.card-content { padding: 30px; flex: 1; display: flex; flex-direction: column; }
.card-type { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 2px; color: var(--accent-color); font-weight: 900; margin-bottom: 12px; }
.card h3 { margin-bottom: 12px; font-size: 1.4rem; line-height: 1.2; color: var(--text-main); font-weight: 800; }
.card-meta { margin-top: auto; font-size: 0.8rem; color: var(--text-muted); padding-top: 20px; border-top: 1px solid var(--border-color); display: flex; justify-content: space-between; }

.article-header { margin-bottom: 50px; }
.article-title { font-size: clamp(2.5rem, 6vw, 4rem); line-height: 1; margin-bottom: 20px; color: var(--text-main); font-weight: 900; letter-spacing: -2px; }
.article-meta { color: var(--accent-color); font-size: 0.85rem; font-weight: 800; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 15px; display: block; }
.article-body { font-size: 1.2rem; line-height: 1.8; color: rgba(255,255,255,0.9); }
.article-body h2 { margin-top: 60px; margin-bottom: 25px; font-size: 2.2rem; font-weight: 900; color: #FFF; letter-spacing: -1px; }
.article-body p { margin-bottom: 30px; }

.sidebar-widget { margin-bottom: 50px; }
.widget-title { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 3px; color: var(--accent-color); font-weight: 900; margin-bottom: 25px; display: flex; align-items: center; gap: 15px; }
.widget-title::after { content: ""; height: 1px; background: var(--border-color); flex: 1; }
.category-list li { margin-bottom: 12px; }
.category-list a { display: block; padding: 10px 15px; background: var(--bg-card); border: 1px solid var(--border-color); font-weight: 700; font-size: 0.9rem; border-radius: var(--radius); }
.category-list a:hover { background: var(--accent-color); border-color: var(--accent-color); color: white; transform: translateX(5px); }

.site-footer { background: var(--bg-footer); color: var(--text-muted); padding: 80px 0; border-top: 1px solid var(--border-color); margin-top: auto; }
.footer-content { display: flex; justify-content: space-between; align-items: center; }
.copyright strong { color: var(--text-main); }

.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 40px; }

@media (max-width: 1024px) {
    .main-layout { flex-direction: column; }
    .sidebar { width: 100%; order: 2; }
}
"""


def _write_default_stylesheets():
    """Write light.css and dark.css to Stylesheets/ only if they don't already exist."""
    os.makedirs(STYLESHEETS_DIR, exist_ok=True)
    light_path = os.path.join(STYLESHEETS_DIR, "light.css")
    dark_path  = os.path.join(STYLESHEETS_DIR, "dark.css")
    if not os.path.exists(light_path):
        with open(light_path, 'w', encoding='utf-8') as f:
            f.write(_LIGHT_ROOT + _CSS_SHARED)
        print(f"[STYLESHEETS] Written: {light_path}")
    if not os.path.exists(dark_path):
        with open(dark_path, 'w', encoding='utf-8') as f:
            f.write(_DARK_ROOT + _CSS_SHARED)
        print(f"[STYLESHEETS] Written: {dark_path}")


def _list_stylesheets():
    """Return list of .css filenames from STYLESHEETS_DIR."""
    if not os.path.exists(STYLESHEETS_DIR):
        return []
    return sorted(f for f in os.listdir(STYLESHEETS_DIR) if f.endswith('.css'))


# ==============================================================================
# WEB PUBLISHER — build helpers
# Ported verbatim from BEJSON_Web_Publisher.WebPublisher methods.
# ==============================================================================

def _log(msg):
    Formatted_Log_Line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    _state["build_log"].append(Formatted_Log_Line)
    print(Formatted_Log_Line)


def _apply_tags(html, tags):
    if not html: return ""
    for k, v in tags.items():
        val = str(v) if v is not None and v != "None" else ""
        html = html.replace(f"{{{{{k}}}}}", val)
    return html

def _read_skel(name):
    Skeleton_Template_Path = os.path.join(SKEL_DIR, name)
    if os.path.exists(Skeleton_Template_Path):
        with open(Skeleton_Template_Path, 'r', encoding='utf-8') as f:
            return f.read()
    return "<body>Skeleton Missing</body>"

def _get_sidebar_html(categories, rel_prefix):
    html = ""
    for c in categories:
        c_name = c.get('cat_name')
        c_slug = c.get('cat_slug')
        if c_name and c_slug:
            html += f'<li><a href="{rel_prefix}category/{c_slug}/index.html">{c_name}</a></li>'
    return html

def _generate_excerpt(html_content, word_limit=30):
    """Plain-text excerpt from an HTML body: strips tags, collapses
    whitespace, takes the first word_limit words, adds a trailing ellipsis
    if it was actually truncated. Used as the feed-card summary for pages,
    which (unlike apps) have no dedicated description field of their own."""
    if not html_content:
        return ""
    Stripped_Excerpt_Text = re.sub(r'<[^>]+>', ' ', html_content)   # strip tags
    Stripped_Excerpt_Text = re.sub(r'\s+', ' ', Stripped_Excerpt_Text).strip()        # collapse whitespace
    words = Stripped_Excerpt_Text.split(' ')
    if len(words) <= word_limit:
        return Stripped_Excerpt_Text
    return ' '.join(words[:word_limit]) + '...'


def _generate_card_html(item, link, target_attr, label, p_date, p_auth, rel_prefix, desc=""):
    f_img = item.get('page_featured_img')
    fallback_url = f"{rel_prefix}assets/{DEFAULT_FEATURED_IMAGE}"

    # App images are typically square-ish icons/logos, not wide banners like
    # page featured images - object-fit:cover on a square source inside this
    # wide, short card container crops/zooms in hard and can lose the subject
    # entirely. Apps get object-fit:contain instead, so the whole icon is
    # visible (letterboxed against the container background) rather than
    # cropped.
    img_fit_style = "object-fit:contain; background:var(--img-placeholder);" if label == "APP" else ""

    if f_img:
        img_path = f"{rel_prefix}assets/{f_img}"
        img_html = f'<div class="card-img-container"><img src="{img_path}" class="card-img" style="{img_fit_style}" alt="{item.get("page_title", "")}" onerror="this.src=\'{fallback_url}\'"></div>'
    else:
        # Automatically generate text canvas image when no image is assigned
        img_html = f'<div class="card-img-container"><img src="{fallback_url}" class="card-img" style="{img_fit_style}" alt="{item.get("page_title", "")}"></div>'

    desc_html = f'<p class="card-desc" style="font-size:0.85rem; color:var(--text-muted); margin-top:10px; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden;">{desc}</p>' if desc else ""

    return f"""<a href="{link}" class="card"{target_attr}>{img_html}<div class="card-content"><span class="card-type">{label}</span><h3>{item['page_title']}</h3>{desc_html}<div class="card-meta">{p_date}</div></div></a>"""
def _generate_ad_block(ad_units, rel_prefix, zone="sidebar"):
    # BUG FIX: this used to pick a random active ad regardless of ad_zone,
    # even though the admin UI (site/ads) lets you assign header/footer/sidebar
    # per ad and shows a per-zone "Ad Zones Summary" -- the zone was collected
    # and displayed but never actually used to filter placement. This is only
    # ever called for the sidebar widget slot (no header/footer slot exists in
    # any skeleton), so it now filters to zone="sidebar" ads specifically,
    # matching where it's actually rendered.
    active = [a for r in ad_units if (a := r).get('ad_active') and a.get('ad_zone', 'sidebar') == zone]
    if not active: return ""
    Selected_Ad_Unit = random.choice(active)
    return f'''
    <div class="sidebar-widget ad-widget">
        <h3 class="widget-title">Sponsored</h3>
        <a href="{Selected_Ad_Unit.get('ad_target_url', '#')}" target="_blank">
            <img src="{rel_prefix}assets/{Selected_Ad_Unit.get('ad_banner_url')}" style="width:100%; height:auto;">
        </a>
    </div>'''

def _write_sitemap_and_robots(output_dir, base_url, feed_items, categories):
    """Writes sitemap.xml + robots.txt to the build output. New in pkg75 --
    previously neither existed anywhere in the build (confirmed absent in
    the pre-pkg75 feature audit). Called once at the end of _execute(), after
    every page/category/app/home file is already on disk, so nothing here
    can point at a URL that doesn't actually resolve on the published site.
    """
    def _esc(s):
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    base = base_url.rstrip("/")
    urls = [(base + "/", None)]                              # home
    urls.append((f"{base}/apps/", None))                     # apps feed
    for cat in categories:
        c_slug = cat.get("cat_slug") or "uncategorized"
        urls.append((f"{base}/category/{c_slug}/", None))

    for x in feed_items:
        if x["type"] not in ("page", "app"):
            continue                                          # external_link points off-site, not our URL to index
        link = x["link"]
        if link.endswith("index.html"):
            link = link[: -len("index.html")]                 # directory-style clean URL to match how these
        urls.append((f"{base}/{link}", x.get("date")))        # actually resolve on a static host

    sitemap_entries = []
    for loc, lastmod in urls:
        lastmod_tag = f"<lastmod>{_esc(lastmod)}</lastmod>" if lastmod else ""
        sitemap_entries.append(f"  <url><loc>{_esc(loc)}</loc>{lastmod_tag}</url>")

    sitemap_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(sitemap_entries) + "\n"
        "</urlset>\n"
    )
    with open(os.path.join(output_dir, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(sitemap_xml)

    robots_txt = (
        "User-agent: *\n"
        "Allow: /\n\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )
    with open(os.path.join(output_dir, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(robots_txt)


def _generate_related_block(items, current_item, default_author, categories):
    rel_cat = current_item.get('page_cat_name')
    related = [i for i in items if i.get('page_cat_name') == rel_cat and i.get('page_uuid') != current_item.get('page_uuid')]
    if not related: return ""
    
    random.shuffle(related)
    selected = related[:3]
    
    grid_html = ""
    for s in selected:
        cat_obj  = next((c for c in categories if c.get('cat_name') == s.get('page_cat_name')), None)
        cat_slug = cat_obj['cat_slug'] if cat_obj and cat_obj.get('cat_slug') else "uncategorized"
        itype = s.get('page_type', 'page')
        # This is used in Article_Skeleton which is at itype/cat/slug/index.html (3 levels deep)
        Generated_Page_Permalink = f"../../../{itype}/{cat_slug}/{s['page_slug']}/index.html"
        p_date = s.get('page_created_at') or ""
        grid_html += _generate_card_html(s, Generated_Page_Permalink, "", itype.upper(), p_date, default_author, "../../../")
        
    return f"""
    <hr style="border:0; border-top:1px solid #eee; margin:40px 0;">
    <h3 style="margin-bottom:20px; font-weight:800; color:#333;">Related Content</h3>
    <div class="grid">{grid_html}</div>
    """

def _execute():
    """
    Robust build execution using unified tag resolution.
    """
    _log("Initializing Build...")
    try:
        SkeletonBuilder().build_all_skeletons()
    except Exception:
        pass

    output_dir = _state["output_dir"]

    if not os.path.exists(MANIFEST_PATH):
        _log("ERROR: Master DB missing.")
        return
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Copy Assets
    if os.path.exists(ASSETS_SRC):
        dst_assets = os.path.join(output_dir, "assets")
        if os.path.exists(dst_assets):
            shutil.rmtree(dst_assets)
        shutil.copytree(ASSETS_SRC, dst_assets)
        _log("Assets copied.")

    # Copy selected stylesheet
    selected_css = _state.get("stylesheet", "dark.css")
    css_src = os.path.join(STYLESHEETS_DIR, selected_css)
    if not os.path.exists(css_src):
        _write_default_stylesheets()
        css_src = os.path.join(STYLESHEETS_DIR, "dark.css")
    shutil.copy2(css_src, os.path.join(output_dir, "style.css"))
    _log(f"Stylesheet applied: {selected_css}")

    # Load Data
    db.mount()
    site_conf_records = db.get_records("SiteConfig")
    site_conf         = {r["sys_key"]: r["sys_value"] for r in site_conf_records if "sys_key" in r}

    categories      = db.get_records("Category")
    items           = db.get_records("PageRecord")
    nav_records     = db.get_records("NavLink")
    social_records  = db.get_records("SocialLink")
    standalone_apps = db.get_records("StandaloneApp")
    ad_units        = db.get_records("AdUnit")

    site_title     = site_conf.get("title", "boehnenelton2024")
    site_desc      = site_conf.get("description", "Personal project showcase")
    default_author = site_conf.get("creator", "The Architect")
    base_url       = site_conf.get("base_url", "https://boehnenelton2024-blog.pages.dev")

    custom_nav_html = "".join([f"<li><a href='{n.get('nav_target_url', '#')}'>{n.get('nav_display_label', 'Link')}</a></li>" for n in nav_records])
    social_html     = "".join([f"<a href='{s.get('social_target_url', '#')}' target='_blank' class='social-btn'>{s.get('social_platform_name', 'Social')}</a>" for s in social_records])

    wrapper_skel = _read_skel("Global_Skeleton.html")
    feed_items   = []

    # Common tags
    base_tags = {
        "site_title": site_title,
        "site_description": site_desc,
        "current_year": datetime.now().year,
        "social_media_links": social_html,
        "custom_nav_links": custom_nav_html,
    }

    # --- PROCESS PAGES ---
    for item in items:
        itype = item.get("page_type", "page")
        if itype == "external_link":
            ext_url = item.get("page_external_url", "#")
            p_date  = item.get("page_created_at") or datetime.now().strftime("%Y-%m-%d")
            feed_items.append({
                "date": p_date,
                "item": item,
                "link": ext_url,
                "type": "external_link",
                "target_attr": " target='_blank' rel='noopener noreferrer'",
                "desc": ""
            })
            continue

        _log(f"Building Page: {item['page_title']}")
        cat_obj  = next((c for c in categories if c.get("cat_name") == item.get("page_cat_name")), None)
        cat_slug = cat_obj["cat_slug"] if cat_obj and cat_obj.get("cat_slug") else "uncategorized" 

        target_dir = os.path.join(output_dir, itype, cat_slug, item["page_slug"])
        os.makedirs(target_dir, exist_ok=True)

        src_file = os.path.join(PAGES_DB_DIR, f"{item['page_uuid']}.json")
        if not os.path.exists(src_file): continue

        try:
            import lib_bejson_Core_bejson_core as Core
            with open(src_file, "r", encoding="utf-8") as f: js = json.load(f)
            field_map = Core.bejson_core_get_field_map(js)
            idx_html = field_map.get("html_body", -1)
            idx_parent = field_map.get("Record_Type_Parent", 0)
            idx_desc = field_map.get("meta_description", -1)
            
            content_row = next((r for r in js["Values"] if r[idx_parent] == "Content"), None)
            html_body = content_row[idx_html] if content_row and idx_html != -1 else ""
            
            p_desc = ""
            if idx_desc != -1:
                meta_row = next((r for r in js["Values"] if r[idx_parent] == "PageMeta"), None)
                if meta_row: p_desc = meta_row[idx_desc] or ""
            if not p_desc:
                p_desc = _generate_excerpt(html_body)

            p_author = item.get("page_author_name") or default_author
            p_date   = item.get("page_created_at") or datetime.now().strftime("%Y-%m-%d")
            f_img    = item.get("page_featured_img")
            
            # Handle missing or "None" images with the seeded default image
            if not f_img or str(f_img).lower() == "none":
                feat_img_html = f"<img src='../../../assets/{DEFAULT_FEATURED_IMAGE}' class='article-featured-image'>"
            else:
                feat_img_html = f"<img src='../../../assets/{f_img}' class='article-featured-image'>"
            
            related_html = _generate_related_block(items, item, default_author, categories)
            ad_html      = _generate_ad_block(ad_units, "../../../")

            # Render page content via strategy renderer dispatch
            from BEJSON_CMS_Renderers import render_page
            rendered_article_content = render_page(itype, {"page_title": item.get("page_title", ""), "html_body": html_body, "page_external_url": item.get("page_external_url"), "page_featured_img": f_img, "page_featured_video_url": item.get("page_featured_video_url")})

            # Build Page Tags
            page_tags = base_tags.copy()
            page_tags.update({
                "page_title": item.get("page_title", ""),
                "rel_prefix": "../../../",
                "sidebar_categories": _get_sidebar_html(categories, "../../../"),
                "breadcrumb_html": f"<a href='../../../category/{cat_slug}/index.html'>{item.get('page_cat_name', 'Uncategorized')}</a> <span>/</span> {item['page_title']}",
                "seo_description": p_desc or site_desc,
                "seo_author": p_author,
                "seo_image": f"{base_url.rstrip('/')}/assets/{f_img}" if f_img else "",
                "current_url": "",
                # Inner Tags
                "article_title": item.get("page_title", ""),
                "category": item.get("page_cat_name", "Uncategorized"),
                "article_body": rendered_article_content,
                "featured_image_html": feat_img_html,
                "related_content_section": related_html + ad_html,
                "timestamp": f"{p_date} \u2022 {p_author}"
            })

            # Assemble Page
            article_skel = _read_skel("Article_Skeleton.html")
            main_content = _apply_tags(article_skel, page_tags)
            page_tags["main_content_injection"] = main_content
            
            final = _apply_tags(wrapper_skel, page_tags)
            final = _apply_tags(final, page_tags) 

            with open(os.path.join(target_dir, "index.html"), "w", encoding="utf-8") as f: f.write(final)
            feed_items.append({"date": p_date, "item": item, "link": f"{itype}/{cat_slug}/{item['page_slug']}/index.html", "type": "page", "desc": p_desc})
        except Exception as e:
            _log(f"Error processing {item['page_title']}: {e}")

    # --- PROCESS APPS ---
    for sa in standalone_apps:
        src_dir = os.path.join(APPS_STORAGE, sa["app_uuid"])
        dst_dir = os.path.join(output_dir, "apps", sa["app_slug"])
        if os.path.exists(src_dir):
            if os.path.exists(dst_dir): shutil.rmtree(dst_dir)
            shutil.copytree(src_dir, dst_dir)
            Generated_App_Permalink = f"apps/{sa['app_slug']}/{sa.get('app_entry_file', 'index.html')}"
            feed_items.append({"date": sa.get("app_created_at", datetime.now().strftime("%Y-%m-%d")), "item": {"page_title": sa["app_name"], "page_featured_img": sa.get("app_featured_img"), "page_uuid": sa["app_uuid"]}, "link": Generated_App_Permalink, "type": "app", "desc": sa.get("app_description", "")})

    # --- BUILD HOME ---
    _log("Generating Home Feed...")
    recent = sorted(feed_items, key=lambda k: k["date"] or "", reverse=True)[:15]
    home_grid = "".join([_generate_card_html(x["item"], x["link"], x.get("target_attr", ""), x["type"].upper(), x["date"], default_author, "", x.get("desc", "")) for x in recent])
    
    home_tags = base_tags.copy()
    home_tags.update({
        "page_title": "Home",
        "rel_prefix": "",
        "sidebar_categories": _get_sidebar_html(categories, ""),
        "breadcrumb_html": "Dashboard",
        "seo_description": site_desc,
        "seo_author": site_title,
        "seo_image": "",
        "current_url": base_url,
        "content_grid": home_grid + _generate_ad_block(ad_units, "")
    })
    
    home_inner = _apply_tags(_read_skel("Home_Skeleton.html"), home_tags)
    home_tags["main_content_injection"] = home_inner
    
    final = _apply_tags(wrapper_skel, home_tags)
    final = _apply_tags(final, home_tags)
    with open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as f: f.write(final)

    # --- BUILD APPS FEED ---
    _log("Generating Apps Feed...")
    apps_only = [x for x in feed_items if x["type"] == "app"]
    apps_grid = "".join([_generate_card_html(x["item"], x["link"].replace("apps/", ""), "", "APP", x["date"], default_author, "../", x.get("desc", "")) for x in apps_only])
    
    apps_tags = base_tags.copy()
    apps_tags.update({
        "page_title": "Applications",
        "rel_prefix": "../",
        "sidebar_categories": _get_sidebar_html(categories, "../"),
        "breadcrumb_html": "Applications",
        "seo_description": "Web Tools",
        "seo_author": site_title,
        "seo_image": "",
        "current_url": "",
        "content_grid": apps_grid + _generate_ad_block(ad_units, "../")
    })
    
    apps_inner = _apply_tags(_read_skel("Apps_Feed_Skeleton.html"), apps_tags)
    apps_tags["main_content_injection"] = apps_inner
    
    final = _apply_tags(wrapper_skel, apps_tags)
    final = _apply_tags(final, apps_tags)
    os.makedirs(os.path.join(output_dir, "apps"), exist_ok=True)
    with open(os.path.join(output_dir, "apps", "index.html"), "w", encoding="utf-8") as f: f.write(final)

    # --- BUILD CATEGORY FEEDS ---
    for cat in categories:
        c_name = cat.get("cat_name") or cat.get("category_name")
        if not c_name: continue
        c_slug = cat.get("cat_slug") or cat.get("category_slug") or "uncategorized"
        _log(f"Generating Category: {c_name}")
        c_items = [x for x in feed_items if x["type"] in ("page", "external_link") and x["item"].get("page_cat_name") == c_name]
        c_grid = "".join([_generate_card_html(x["item"], x["link"] if x["type"] == "external_link" else f"../../{x['link']}", x.get("target_attr", ""), x["type"].upper(), x["date"], default_author, "../../", x.get("desc", "")) for x in c_items])
        
        cat_tags = base_tags.copy()
        cat_tags.update({
            "page_title": c_name,
            "rel_prefix": "../../",
            "sidebar_categories": _get_sidebar_html(categories, "../../"),
            "breadcrumb_html": f"Category <span>/</span> {c_name}",
            "seo_description": "",
            "seo_author": site_title,
            "seo_image": "",
            "current_url": "",
            "category_name": c_name,
            "category_description": f"Browsing all items in {c_name}.",
            "content_grid": c_grid + _generate_ad_block(ad_units, "../../")
        })
        
        cat_inner = _apply_tags(_read_skel("Category_Skeleton.html"), cat_tags)
        cat_tags["main_content_injection"] = cat_inner
        
        final = _apply_tags(wrapper_skel, cat_tags)
        final = _apply_tags(final, cat_tags)
        cat_dir = os.path.join(output_dir, "category", c_slug)
        os.makedirs(cat_dir, exist_ok=True)
        with open(os.path.join(cat_dir, "index.html"), "w", encoding="utf-8") as f: f.write(final)

    # --- SITEMAP.XML + ROBOTS.TXT ---
    _log("Generating sitemap.xml and robots.txt...")
    _write_sitemap_and_robots(output_dir, base_url, feed_items, categories)

    _log("Build Complete!")


# ==============================================================================
# LOCAL PREVIEW SERVER  (from WebPublisher._start_server / _stop_server)
# ==============================================================================

def _run_preview_server(port):
    output_dir = _state["output_dir"]

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=output_dir, **kwargs)
        def log_message(self, fmt, *args):
            pass  # suppress console noise

    try:
        httpd = socketserver.TCPServer(("", port), Handler)
        httpd.allow_reuse_address = True
        _state["httpd"]       = httpd
        _state["srv_running"] = True
        _state["srv_port"]    = port
        _log(f"Preview server running on http://localhost:{port}")
        httpd.serve_forever()
    except Exception as e:
        _state["srv_running"] = False
        _log(f"Server error: {e}")


def _stop_preview_server():
    if _state.get("httpd"):
        _state["httpd"].shutdown()
        _state["httpd"].server_close()
    _state["httpd"]       = None
    _state["srv_running"] = False
    _log("Preview server stopped.")


# ==============================================================================
# ADMIN UI — shared shell (dark theme matching the original app palette)
# ==============================================================================

_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>{{ page_title }} -- BEJSON Publisher</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&family=Source+Code+Pro&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0f0f0f;--panel:#161616;--card:#1c1c1c;--acc:#DE2626;
  --border:#2a2a2a;--fg:#f0f0f0;--muted:#888;--green:#16a34a;
  --sb-w:220px;
}
*{box-sizing:border-box;margin:0;padding:0;}
html,body{height:100%;}
body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--fg);font-size:15px;overflow-x:hidden;}
a{color:var(--acc);text-decoration:none;} a:hover{opacity:.8;}

/* ── OVERLAY (mobile) ── */
#sb-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:90;}
#sb-overlay.show{display:block;}

/* ── SIDEBAR ── */
.sb{
  position:fixed;top:0;left:0;height:100%;width:var(--sb-w);
  background:var(--panel);border-right:1px solid var(--border);
  display:flex;flex-direction:column;z-index:100;
  transition:transform .25s ease;
}
.sb-logo{padding:18px 16px;border-bottom:2px solid var(--acc);font-size:1.2rem;font-weight:900;letter-spacing:-1px;color:#fff;flex-shrink:0;}
.sb-logo span{color:var(--acc);}
.sb nav{flex:1;overflow-y:auto;}
.sb nav a{display:flex;align-items:center;gap:10px;padding:14px 16px;color:var(--muted);font-size:.9rem;font-weight:600;transition:.15s;border-left:3px solid transparent;}
.sb nav a:hover{color:#fff;background:rgba(222,38,38,.1);}
.sb nav a.on{color:#fff;background:rgba(222,38,38,.15);border-left-color:var(--acc);}
.sb-foot{padding:12px 16px;font-size:.7rem;color:#444;border-top:1px solid var(--border);flex-shrink:0;}

/* ── TOPBAR ── */
.topbar{
  position:fixed;top:0;left:var(--sb-w);right:0;height:52px;
  background:var(--panel);border-bottom:1px solid var(--border);
  display:flex;align-items:center;padding:0 20px;gap:14px;z-index:80;
}
.topbar h2{font-size:.95rem;font-weight:800;color:var(--acc);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.hamburger{display:none;background:none;border:none;color:var(--fg);font-size:1.4rem;cursor:pointer;padding:4px 6px;line-height:1;flex-shrink:0;}

/* ── MAIN CONTENT ── */
.main{margin-left:var(--sb-w);margin-top:52px;min-height:calc(100vh - 52px);display:flex;flex-direction:column;}
.content{padding:22px;max-width:1080px;width:100%;}

/* ── CARDS ── */
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:20px;margin-bottom:16px;}
.card-hd{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid var(--border);gap:10px;flex-wrap:wrap;}
.card-hd h3{font-size:.93rem;font-weight:700;}

/* ── BUTTONS ── */
.btn{display:inline-flex;align-items:center;gap:6px;padding:10px 16px;border:none;border-radius:6px;font-family:inherit;font-weight:700;font-size:.84rem;cursor:pointer;text-decoration:none;transition:.15s;white-space:nowrap;touch-action:manipulation;}
.btn-red{background:var(--acc);color:#fff;} .btn-red:hover{background:#b91c1c;}
.btn-grey{background:#2a2a2a;color:#ccc;border:1px solid var(--border);} .btn-grey:hover{background:#333;}
.btn-green{background:var(--green);color:#fff;} .btn-green:hover{background:#15803d;}
.btn-sm{padding:7px 12px;font-size:.78rem;}
.btn:disabled{opacity:.45;cursor:default;}

/* ── FORMS ── */
.fg{margin-bottom:14px;}
label{display:block;margin-bottom:5px;font-size:.82rem;font-weight:600;color:var(--muted);}
input[type=text],input[type=number],select,textarea{
  width:100%;padding:10px 13px;background:#111;border:1px solid var(--border);
  border-radius:6px;color:#fff;font-family:inherit;font-size:1rem;
  -webkit-appearance:none;
}
input:focus,textarea:focus,select:focus{outline:none;border-color:var(--acc);}
textarea{min-height:420px;font-family:'Source Code Pro',monospace;font-size:.88rem;line-height:1.6;resize:vertical;}

/* ── MISC ── */
.logbox{background:#000;border:1px solid var(--border);border-radius:6px;padding:14px;height:260px;overflow-y:auto;font-family:'Source Code Pro',monospace;font-size:.78rem;color:#00ff00;white-space:pre-wrap;line-height:1.5;}
table{width:100%;border-collapse:collapse;}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--border);font-size:.88rem;}
th{font-size:.7rem;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);}
tr:hover{background:rgba(255,255,255,.02);}
td:last-child{white-space:nowrap;}
.badge{display:inline-block;padding:3px 8px;border-radius:4px;font-size:.68rem;font-weight:700;text-transform:uppercase;}
.b-on{background:#14532d;color:#4ade80;} .b-off{background:#292929;color:#777;}
.alert{padding:12px 16px;border-radius:6px;margin-bottom:16px;font-size:.88rem;line-height:1.5;}
.a-ok{background:rgba(34,197,94,.1);border:1px solid rgba(34,197,94,.25);color:#4ade80;}
.a-err{background:rgba(220,38,38,.1);border:1px solid rgba(220,38,38,.3);color:#f87171;}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px;}
.btn-row{display:flex;gap:10px;flex-wrap:wrap;}

/* ── MOBILE ── */
@media(max-width:700px){
  :root{--sb-w:220px;}
  .sb{transform:translateX(calc(-1 * var(--sb-w)));}
  .sb.open{transform:translateX(0);}
  .topbar{left:0;}
  .main{margin-left:0;}
  .hamburger{display:block;}
  .grid2{grid-template-columns:1fr;}
  .content{padding:14px;}
  .card{padding:16px;}
  /* stack editor split layout */
  .editor-split{flex-direction:column !important;}
  .editor-split > div:first-child{width:100% !important;max-height:200px;}
  /* make tables scrollable */
  .table-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch;}
  /* bigger tap targets */
  .btn{padding:11px 16px;}
  input[type=text],input[type=number],select{font-size:16px;}
}
</style>
</head>
<body>
<div id="sb-overlay" onclick="closeSb()"></div>
<div class="sb" id="sidebar">
  <div class="sb-logo">BEJSON<span>.</span></div>
  <nav>
    <a href="/"        class="{{ 'on' if active=='dash'    else '' }}">&#9711; Dashboard</a>
    <a href="/publish" class="{{ 'on' if active=='publish' else '' }}">&#9654; Publisher</a>
    <a href="/reset"   class="{{ 'on' if active=='reset'   else '' }}">&#9888; Factory Reset</a>
  </nav>
  <div class="sb-foot">Flask port</div>
</div>
<div class="topbar">
  <button class="hamburger" onclick="toggleSb()" aria-label="Menu">&#9776;</button>
  <h2>{{ page_title }}</h2>
</div>
<div class="main">
  <div class="content">
    {% if flash %}<div class="alert {{ flash_cls }}">{{ flash | safe }}</div>{% endif %}
    {{ body | safe }}
  </div>
</div>
<script>
function toggleSb(){
  var sb=document.getElementById('sidebar');
  var ov=document.getElementById('sb-overlay');
  sb.classList.toggle('open');
  ov.classList.toggle('show');
}
function closeSb(){
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sb-overlay').classList.remove('show');
}
// close sidebar on nav link tap (mobile)
document.querySelectorAll('.sb nav a').forEach(function(a){
  a.addEventListener('click',closeSb);
});
</script>
</body>
</html>"""

def _page(title, active, body, flash="", flash_cls="a-ok"):
    return render_template_string(
        _SHELL,
        page_title=title, active=active, body=body,
        flash=flash, flash_cls=flash_cls
    )


# ==============================================================================
# ROUTE: DASHBOARD
# ==============================================================================

@app.route("/")
def r_dashboard():
    db_ok = os.path.exists(MANIFEST_PATH)
    pages = Standalone_App_Count = Category_Count = 0
    if db_ok:
        try:
            db.mount()
            pages = len([r for r in db.get_records("PageRecord") if r.get("page_type") != "external_link"])
            Standalone_App_Count  = len(db.get_records("StandaloneApp"))
            Category_Count  = len(db.get_records("Category"))
        except Exception:
            pass

    assets = 0
    if os.path.exists(ASSETS_SRC):
        assets = len([f for f in os.listdir(ASSETS_SRC) if not f.startswith(".")])

    built = os.path.exists(_state["output_dir"]) and bool(os.listdir(_state["output_dir"]))

    srv_badge = (f"<span class='badge b-on'>:{_state['srv_port']}</span>"
                 if _state["srv_running"] else "<span class='badge b-off'>stopped</span>")

    Dashboard_Page_Html = f"""
    <div class="grid2" style="margin-bottom:18px;">
      <div class="card" style="padding:18px;">
        <div style="font-size:.7rem;text-transform:uppercase;letter-spacing:1px;color:var(--muted);margin-bottom:6px;">Pages</div>
        <div style="font-size:2.4rem;font-weight:900;color:var(--acc);">{pages}</div>
      </div>
      <div class="card" style="padding:18px;">
        <div style="font-size:.7rem;text-transform:uppercase;letter-spacing:1px;color:var(--muted);margin-bottom:6px;">Standalone Apps</div>
        <div style="font-size:2.4rem;font-weight:900;color:var(--acc);">{Standalone_App_Count}</div>
      </div>
      <div class="card" style="padding:18px;">
        <div style="font-size:.7rem;text-transform:uppercase;letter-spacing:1px;color:var(--muted);margin-bottom:6px;">Categories</div>
        <div style="font-size:2.4rem;font-weight:900;color:var(--acc);">{Category_Count}</div>
      </div>
      <div class="card" style="padding:18px;">
        <div style="font-size:.7rem;text-transform:uppercase;letter-spacing:1px;color:var(--muted);margin-bottom:6px;">Assets</div>
        <div style="font-size:2.4rem;font-weight:900;color:var(--acc);">{assets}</div>
      </div>
    </div>
    <div class="card">
      <div class="card-hd"><h3>System Status</h3></div>
      <div class="table-wrap">
      <table>
        <tr><td>Master Database</td>
            <td>{"<span class='badge b-on'>OK</span>" if db_ok else "<span class='badge b-off'>MISSING</span>"}</td></tr>
        <tr><td>Output Directory</td>
            <td><code style="font-size:.8rem;color:#aaa;white-space:normal;word-break:break-all;">{_state["output_dir"]}</code></td></tr>
        <tr><td>Site Built</td>
            <td>{"<span class='badge b-on'>YES</span>" if built else "<span class='badge b-off'>NOT YET</span>"}</td></tr>
        <tr><td>Preview Server</td><td>{srv_badge}</td></tr>
        <tr><td>Skeleton Dir</td>
            <td>{"<span class='badge b-on'>OK</span>" if os.path.exists(SKEL_DIR) else "<span class='badge b-off'>MISSING</span>"}</td></tr>
      </table>
      </div>
    </div>
    <div class="btn-row">
      <a href="/publish" class="btn btn-red">&#9654; Build &amp; Publish</a>
    </div>"""
    return _page("Dashboard", "dash", Dashboard_Page_Html)


# ==============================================================================
# ROUTE: PUBLISHER
# ==============================================================================

@app.route("/publish")
def r_publish():
    built    = os.path.exists(_state["output_dir"]) and bool(os.listdir(_state["output_dir"]))
    building = _state["build_running"]
    srv_on   = _state["srv_running"]
    srv_port = _state["srv_port"]
    out_dir  = _state["output_dir"]

    build_badge = ("<span class='badge b-on'>IDLE</span>" if not building
                   else "<span class='badge' style='background:#7c2d12;color:#fca5a5;'>BUILDING...</span>")
    srv_badge   = (f"<span class='badge b-on'>:{srv_port}</span>" if srv_on
                   else "<span class='badge b-off'>stopped</span>")

    server_controls = f"""
      <form method="POST" action="/publish/server/start" style="display:flex;gap:10px;align-items:flex-end;margin-bottom:10px;">
        <div class="fg" style="margin:0;">
          <label>Port</label>
          <input type="number" name="port" value="{srv_port}" style="width:100px;">
        </div>
        <button class="btn btn-green" {"disabled" if srv_on else ""}>&#9654; Start</button>
      </form>
      {"<form method='POST' action='/publish/server/stop'><button class='btn btn-red'>&#9646;&#9646; Stop Server</button></form>" if srv_on else ""}
      {"<a href='http://localhost:" + str(srv_port) + "' target='_blank' class='btn btn-grey' style='margin-top:8px;display:inline-flex;'>&#127760; Open Browser</a>" if srv_on else ""}
    """

    body = f"""
    <div class="grid2">
      <div>
        <div class="card">
          <div class="card-hd"><h3>Build Site</h3>{build_badge}</div>
          <p style="color:var(--muted);font-size:.88rem;margin-bottom:16px;">
            Reads BEJSON data, assembles HTML using your skeleton files on disk, copies assets.
          </p>
          <form method="POST" action="/publish/build">
            <div class="fg">
              <label>Output Directory</label>
              <input type="text" name="output_dir" value="{out_dir}">
            </div>
            <div class="fg">
              <label>Theme Stylesheet</label>
              <select name="stylesheet">
                {''.join(f'<option value="{f}" {"selected" if f == _state["stylesheet"] else ""}>{f}</option>' for f in _list_stylesheets()) or '<option value="light.css">light.css</option>'}
              </select>
              <p style="font-size:.78rem;color:var(--muted);margin-top:6px;">
                Stylesheets live in <code style="color:#aaa;word-break:break-all;">{STYLESHEETS_DIR}</code>.
                Copy &amp; edit to build custom themes.
              </p>
            </div>
            <button class="btn btn-red" {"disabled" if building else ""}>&#9654; Build Now</button>
          </form>
        </div>
        <div class="card">
          <div class="card-hd">
            <h3>Build Log</h3>
            <button class="btn btn-grey btn-sm" id="btn-poll" onclick="togglePoll()">Auto-refresh</button>
          </div>
          <div class="logbox" id="logbox">{chr(10).join(_state["build_log"][-200:]) or "No build started yet."}</div>
        </div>
      </div>
      <div>
        <div class="card">
          <div class="card-hd"><h3>Preview Server</h3>{srv_badge}</div>
          <p style="color:var(--muted);font-size:.88rem;margin-bottom:16px;">
            Serves the built static site locally for review.
            {"<br><strong style='color:#4ade80;'>Built site detected.</strong>" if built else ""}
          </p>
          {server_controls}
        </div>
        <div class="card">
          <div class="card-hd"><h3>Cloudflare Pages</h3></div>
          <p style="color:var(--muted);font-size:.88rem;margin-bottom:16px;">
            Deploy the built static site directly to Cloudflare Pages.
          </p>
          <form method="POST" action="/publish/cloudflare">
            <div class="fg">
              <label>Project Name</label>
              <input type="text" name="cf_project" placeholder="Enter Cloudflare Project Name" value="boehnenelton2024-blog">
            </div>
            <button class="btn btn-green" {"disabled" if building else ""}>&#9729; Publish to Cloudflare</button>
          </form>
        </div>
        <div class="card">
          <div class="card-hd"><h3>Skeleton Files</h3></div>
          <p style="color:var(--muted);font-size:.85rem;margin-bottom:12px;">
            Live in <code style="font-size:.8rem;color:#aaa;word-break:break-all;">{SKEL_DIR}</code><br>
            Edit them directly to customise layout. Auto-generated only when missing.
          </p>
          <form method="POST" action="/publish/regen">
            <button class="btn btn-grey">&#8635; Force Regenerate</button>
          </form>
        </div>
      </div>
    </div>
    <script>
      let _p = false, _t = null;
      function togglePoll() {{
        _p = !_p;
        document.getElementById('btn-poll').textContent = _p ? 'Stop refresh' : 'Auto-refresh';
        if (_p) doPoll(); else clearTimeout(_t);
      }}
      function doPoll() {{
        fetch('/publish/log').then(r=>r.json()).then(d=>{{
          const el = document.getElementById('logbox');
          el.textContent = d.log.join('\\n');
          el.scrollTop = el.scrollHeight;
          if (_p) _t = setTimeout(doPoll, 1500);
        }});
      }}
    </script>"""
    return _page("Publisher", "publish", body)


@app.route("/publish/build", methods=["POST"])
def r_build():
    Submitted_Output_Directory = request.form.get("output_dir", "").strip()
    if Submitted_Output_Directory:
        _state["output_dir"] = Submitted_Output_Directory
    Submitted_Stylesheet_Choice = request.form.get("stylesheet", "").strip()
    if Submitted_Stylesheet_Choice:
        _state["stylesheet"] = Submitted_Stylesheet_Choice
    if not _state["build_running"]:
        _state["build_running"] = True
        _state["build_log"]     = []
        def _run():
            try:
                _execute()
            finally:
                _state["build_running"] = False
        threading.Thread(target=_run, daemon=True).start()
    return redirect("/publish")


@app.route("/publish/log")
def r_log():
    return jsonify({"log": _state["build_log"][-300:], "running": _state["build_running"]})


@app.route("/publish/server/start", methods=["POST"])
def r_srv_start():
    if not _state["srv_running"]:
        try:
            port = int(request.form.get("port", 8000))
        except ValueError:
            port = 8000
        threading.Thread(target=_run_preview_server, args=(port,), daemon=True).start()
    return redirect("/publish")


@app.route("/publish/server/stop", methods=["POST"])
def r_srv_stop():
    threading.Thread(target=_stop_preview_server, daemon=True).start()
    return redirect("/publish")


@app.route("/publish/regen", methods=["POST"])
def r_regen():
    ok, msg = SkeletonBuilder(force=True).build_all_skeletons()
    return _page("Publisher", "publish",
        '<p style="margin-top:12px;"><a href="/publish" class="btn btn-grey">&#8592; Back</a></p>',
        flash=msg, flash_cls="a-ok" if ok else "a-err")


# ==============================================================================
# ROUTE: FACTORY RESET  (ported from Cleanup_Tool.py)
# Paths and logic identical; tkinter messagebox replaced with HTML confirm.
# ==============================================================================

@app.route("/reset")
def r_reset():
    body = """
    <div class="card" style="max-width:520px;">
      <div class="card-hd"><h3 style="color:var(--acc);">&#9888; Factory Reset</h3></div>
      <p style="line-height:1.8;margin-bottom:18px;">
        This will permanently delete:<br>
        &bull; All pages, articles &amp; categories<br>
        &bull; All images / assets<br>
        &bull; The published static website<br>
        &bull; All ZIP exports<br><br>
        <strong style="color:#f87171;">This cannot be undone.</strong>
      </p>
      <form method="POST" action="/reset/confirm"
            onsubmit="return confirm('Are you absolutely sure? All CMS data will be permanently lost.');">
        <button class="btn btn-red">&#128465; Wipe Everything</button>
        <a href="/" class="btn btn-grey" style="margin-left:10px;">Cancel</a>
      </form>
    </div>"""
    return _page("Factory Reset", "reset", body)


@app.route("/reset/confirm", methods=["POST"])
def r_reset_confirm():
    """Same wipe targets as the Admin factory reset (BEJSON_CMS_System.py
    factory_reset_confirm()), plus the same post-wipe re-bootstrap -- this
    route used to wipe MFDB_DIR/builds/exports and stop, leaving the DB
    unusable until Admin happened to be launched next and rebuilt it by
    accident. It also never cleared storage/tmp/html_imports (the exact
    gap Admin's reset was already fixed for)."""
    UPLOAD_TMP = os.path.join(STORAGE_ROOT, "tmp", "html_imports")
    errors = []

    # Targets identical to Admin's factory_reset_confirm()
    for path in [MFDB_DIR, DEFAULT_OUT_DIR, EXPORTS_DIR, UPLOAD_TMP]:
        if os.path.exists(path):
            try:
                shutil.rmtree(path)
            except Exception as e:
                errors.append(str(e))

    # Re-create empty structure (same folders as original)
    for d in [
        os.path.join(MFDB_DIR, "assets"),
                os.path.join(MFDB_DIR, "Context"),
        os.path.join(MFDB_DIR, "standalone_apps"),
        EXPORTS_DIR,
        UPLOAD_TMP,
    ]:
        try:
            os.makedirs(d, exist_ok=True)
            if "STORAGE_ROOT" in globals(): os.makedirs(STORAGE_ROOT, exist_ok=True)
        except Exception:
            pass

    # Re-initialise a fresh master DB -- same lifecycle System.py runs at its
    # own import time / Admin's own reset route, so a wipe from this app
    # doesn't leave the CMS broken until some other app happens to launch.
    try:
        import BEJSON_CMS_System as _SystemCube
        _SystemCube.init_master_db()
        _SystemCube._migrate_db()
        _SystemCube._ensure_uncategorized_category()
        _SystemCube._seed_default_site_config()
        _SystemCube._seed_default_brand_and_author()
    except Exception as e:
        errors.append(f"Re-bootstrap failed: {e}")

    if errors:
        return _page("Factory Reset", "reset",
            '<p><a href="/" class="btn btn-grey">Back</a></p>',
            flash="Reset completed with errors: " + "; ".join(errors), flash_cls="a-err")

    return _page("Factory Reset", "reset",
        '<p style="margin-top:12px;color:var(--muted);">Fresh database initialised — the default category and brand author are ready.</p>'
        '<p style="margin-top:16px;"><a href="/" class="btn btn-grey">Back to Dashboard</a></p>',
        flash="System reset complete. All data has been wiped.")


# ==============================================================================
# ENTRY POINT
# ==============================================================================


@app.route("/publish/cloudflare", methods=["POST"])
def r_publish_cloudflare():
    project_name = request.form.get("cf_project", "").strip()
    if project_name and not re.match(r'^[a-zA-Z0-9\-]{1,64}$', project_name):
        return jsonify({'error': 'Invalid project name. Use only letters, numbers, and hyphens.'}), 400
    if not project_name:
        # Fallback to site name
        try:
            site_conf = {r["sys_key"]: r["sys_value"] for r in db.get_records("SiteConfig") if "sys_key" in r}
            project_name = site_conf.get("title", "bejson-site")
        except Exception:
            project_name = "bejson-site"

    if not _state["build_running"]:
        _state["build_running"] = True
        _state["build_log"] = []
        _log(f"[Cloudflare] Starting deployment for project: {project_name}")
        
        def _run_deploy():
            try:
                out_dir = _state["output_dir"]
                if not os.path.exists(out_dir) or not os.listdir(out_dir):
                    _log("[Error] Output directory is empty. Run build first.")
                    return

                # Prepare environment
                Cloudflare_Deploy_Subprocess_Env = os.environ.copy()
                Cloudflare_Deploy_Subprocess_Env["CLOUDFLARE_ACCOUNT_ID"] = CF_KEYS.get("ACCOUNT_ID", "")
                Cloudflare_Deploy_Subprocess_Env["CLOUDFLARE_API_TOKEN"] = CF_KEYS.get("API_TOKEN", "")
                
                if not Cloudflare_Deploy_Subprocess_Env["CLOUDFLARE_API_TOKEN"]:
                    _log("[Error] Cloudflare API Token not found in vault.")
                    return

                _log("[Cloudflare] Running wrangler pages publish...")
                Wrangler_Deploy_Command = ["wrangler", "pages", "publish", out_dir, "--project-name", project_name]
                
                process = subprocess.Popen(Wrangler_Deploy_Command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=Cloudflare_Deploy_Subprocess_Env)
                for line in process.stdout:
                    _log(f"[wrangler] {line.strip()}")
                
                process.wait()
                if process.returncode == 0:
                    _log("[Cloudflare] Deployment successful!")
                else:
                    _log(f"[Cloudflare] Deployment failed with code {process.returncode}")
            except Exception as e:
                _log(f"[Cloudflare] Critical Error: {e}")
            finally:
                _state["build_running"] = False

        threading.Thread(target=_run_deploy, daemon=True).start()
    
    return redirect("/publish")

if __name__ == "__main__":
    print(f"""
============================================================
  BEJSON Web Publisher Flask

  Routes:
    /          Dashboard
    /publish   Build + preview server
    /reset     Factory reset

  http://localhost:{PUBLISHER_PORT}
============================================================""")
    # Write skeleton defaults only if files don't already exist
    SkeletonBuilder().build_all_skeletons()
    # Write default stylesheets only if they don't already exist
    _write_default_stylesheets()
    _legacy = [f for f in ["Flask_CMS.py", "Flask_CMS_Publisher.py", "Flask_Page_Editor.py",
                            "Flask_Profile_Manager.py", "Page_Editor_v2.py"]
               if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), f))]
    if _legacy:
        print(f"\n    !! WARNING: old pre-rename file(s) still present: {', '.join(_legacy)} -- delete them, they are unmaintained leftovers from before the Blueprint split.\n")
    # Port resolved via config.json (publisher_port) / CMS_PUBLISHER_PORT env
    # override — see lib_bejson_CMS_cms_ports.py. Default unchanged at 5001.
    app.run(host="0.0.0.0", port=PUBLISHER_PORT, debug=False)
