#!/usr/bin/env python3
"""
SCRIPT_NAME:    Flask_Page_Editor
SCRIPT_VERSION: 16.0
RELATION_ID:    91cb1c5f-9b58-4e21-a0cb-cae11d0e4c31
AUTHOR:         Elton Boehnen
EMAIL:          boehnenelton2024@gmail.com
GITHUB:         github.com/boehnenelton
SITE:           https://boehnenelton2024.pages.dev
DESCRIPTION:    Dedicated page creation and editing tool for the BEJSON CMS.
                Refactored to use BEJSON_Standard_Lib & BEJSON_Extended_Lib.

RUNS ON: http://localhost:5003
"""

from flask import Flask, render_template_string, request, redirect, url_for, flash, jsonify, Response
import json
import os
import re
import uuid
import sys
import html as _html_mod
import random
import threading
import base64
import urllib.request
import urllib.error
from datetime import datetime
from queue import Queue, Empty
from werkzeug.utils import secure_filename

# Import BEJSON Libraries
# Import New MFDB Orchestrator
import sys
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB_DIR = os.path.join(PROJECT_ROOT, "src", "lib")
if LIB_DIR not in sys.path:
    sys.path.append(LIB_DIR)
import lib_cms_core as CMSCore

# =============================================================================
# APP
# =============================================================================

app = Flask(__name__)
app.config['SECRET_KEY'] = 'CHANGE-THIS-TO-A-SECURE-RANDOM-STRING'  # TODO: Replace with a strong secret key before deploying
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024

# =============================================================================
# AI CONFIG & POLICY (Gemini-Usage-Policy.md)
# =============================================================================

AI_MODELS = [
    "gemini-3-flash-preview", "gemini-flash-lite-latest", "gemini-flash-latest",
    "gemini-2.5", "gemini-2.5-pro", "gemini-3-pro-preview", "gemini-3.1-pro-preview"
]

# =============================================================================
# PATH CONFIGURATION (Clean Root Architecture)
# =============================================================================

# (Duplicate PROJECT_ROOT removed by patch_cms.py)

# Storage Domains
STORAGE_ROOT = os.path.join(PROJECT_ROOT, "storage")
MFDB_DIR = os.path.join(STORAGE_ROOT, "mfdb")
MANIFEST_PATH = os.path.join(MFDB_DIR, "site_master", "104a.mfdb.bejson")
PAGES_DB_DIR = os.path.join(MFDB_DIR, "pages_db")

ASSETS_DIR = os.path.join(MFDB_DIR, "assets")
APPS_STORAGE = os.path.join(MFDB_DIR, "standalone_apps")
EXPORTS_DIR = os.path.join(STORAGE_ROOT, "exports")
PUBLISH_DIR = os.path.join(STORAGE_ROOT, "builds")
UPLOAD_TMP  = os.path.join(STORAGE_ROOT, "tmp", "html_imports")
CONTEXT_DIR = os.path.join(STORAGE_ROOT, "tmp", "Context")
PROFILES_DIR = os.path.join(PROJECT_ROOT, "resources", "profiles")

# Resources Domain
RESOURCES_ROOT = os.path.join(PROJECT_ROOT, "resources")
TEMPLATE_DIR = os.path.join(RESOURCES_ROOT, "templates")

for d in [MFDB_DIR, PAGES_DB_DIR, ASSETS_DIR, APPS_STORAGE, EXPORTS_DIR, PUBLISH_DIR, UPLOAD_TMP, TEMPLATE_DIR, CONTEXT_DIR, PROFILES_DIR]:
    os.makedirs(d, exist_ok=True)

db = CMSCore.CMSCore(MANIFEST_PATH)
if os.path.exists(MANIFEST_PATH): db.mount()


# =============================================================================
# BEJSON LIB  (embedded — identical logic to Flask_CMS.py)
# =============================================================================

def _slug(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')

def _get_categories():
    if not os.path.exists(MANIFEST_PATH):
        return [{'category_name': 'Uncategorized', 'category_slug': 'uncategorized'}]
    db.mount()
    cats = db.get_records("Category")
    
    return cats or [{'category_name': 'Uncategorized', 'category_slug': 'uncategorized'}]

def _get_pages():
    if not os.path.exists(MANIFEST_PATH):
        return []
    db.mount()
    pages = db.get_records("PageRecord")
    
    return sorted(pages, key=lambda p: p.get('created_at', ''), reverse=True)

def _get_page_body(page_uuid):
    """Read html_body from pages_db/<uuid>.json — returns empty string if missing."""
    import lib_bejson_core as Core
    pfile = os.path.join(PAGES_DB_DIR, f"{page_uuid}.json")
    if not os.path.exists(pfile):
        return ""
    try:
        import json
        with open(pfile, 'r') as f:
            data = json.load(f)
        recs    = data.get("Values", [])
        field_map = Core.bejson_core_get_field_map(data)
        p_idx   = field_map.get("Record_Type_Parent", -1)
        hb_idx  = field_map.get("html_body", -1)
        
        for row in recs:
            if p_idx != -1 and hb_idx != -1 and row[p_idx] == "Content":
                return row[hb_idx] or ""
        return ""
    except Exception:
        return ""

def _write_page_record(page_uuid, title, category, author, body_html, is_new=True, featured_img=None, template_key='blank'):
    """
    Write a PageRecord to master DB and write/update the pages_db content file.
    Exactly mirrors how Flask_CMS.py creates pages.
    Now idempotent: checks for existing title to reuse UUID and preserve data.
    """
    import lib_bejson_core as Core
    page_slug = _slug(title)
    today     = datetime.now().strftime("%Y-%m-%d")

    existing_pages = db.get_records("PageRecord")
    existing_page = next((p for p in existing_pages if p.get('page_uuid') == page_uuid), None)
    
    if is_new:
        db.add_record("PageRecord", {
            "page_uuid":    page_uuid,
            "page_title":   title,
            "page_slug":    page_slug,
            "category_ref": category,
            "item_type":    "page",
            "created_at":   today,
            "external_url": None,
            "author_ref":   author,
            "featured_img": featured_img,
            "template_key": template_key,
        })
    else:
        updates = {
            "page_title":   title,
            "page_slug":    page_slug,
            "category_ref": category,
            "author_ref":   author,
            "template_key": template_key,
        }
        if featured_img is not None:
            updates["featured_img"] = featured_img
            
        db.update_record("PageRecord", "page_uuid", page_uuid, updates)
    
    # --- Per-page content file ---
    pfile = os.path.join(PAGES_DB_DIR, f"{page_uuid}.json")
    import json
    if not os.path.exists(pfile):
        data = {
            "Format": "BEJSON",
            "Format_Version": "104db",
            "Format_Creator": "Elton Boehnen",
            "Records_Type": ["PageMeta", "Content"],
            "Fields": [
                {"name": "Record_Type_Parent", "type": "string"},
                {"name": "meta_title", "type": "string"},
                {"name": "html_body", "type": "string"},
                {"name": "markdown_body", "type": "string"},
                {"name": "source_code", "type": "string"}
            ],
            "Values": [
                ["PageMeta", title, None, None, None],
                ["Content", None, body_html, "", ""]
            ]
        }
        with open(pfile, 'w') as f:
            json.dump(data, f, indent=2)
    else:
        try:
            with open(pfile, 'r') as f:
                data = json.load(f)
            field_map = Core.bejson_core_get_field_map(data)
            p_idx   = field_map.get("Record_Type_Parent", -1)
            hb_idx  = field_map.get("html_body", -1)
            mt_idx  = field_map.get("meta_title", -1)
            for row in data.get("Values", []):
                if p_idx != -1 and hb_idx != -1 and row[p_idx] == "Content":
                    row[hb_idx] = body_html
                if p_idx != -1 and mt_idx != -1 and row[p_idx] == "PageMeta":
                    row[mt_idx] = title
            with open(pfile, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print("Save error:", e)

# =============================================================================
# PAGE TEMPLATES
# =============================================================================

TEMPLATES = {
    "blank": {
        "label": "Blank Page",
        "icon":  "📄",
        "desc":  "Start from scratch with an empty HTML body.",
        "html":  "<p></p>",
    },
    "article": {
        "label": "Article",
        "icon":  "📰",
        "desc":  "Standard article layout with intro, sections, and a conclusion.",
        "html":  """\
<p>
  Introduction paragraph — write a brief overview of what this article covers.
</p>

<h2>Section One</h2>
<p>
  Body text for section one. Replace this placeholder with your content.
</p>

<h2>Section Two</h2>
<p>
  Body text for section two. You can add as many sections as needed.
</p>

<h2>Section Three</h2>
<p>
  Body text for section three.
</p>

<h2>Conclusion</h2>
<p>
  Wrap up the article here with key takeaways or a call to action.
</p>""",
    },
    "youtube": {
        "label": "YouTube Embed",
        "icon":  "▶️",
        "desc":  "Responsive video embed with title, description, and optional notes.",
        "html":  """\
<p>
  Brief description of what this video covers.
</p>

<div class="bej-video-wrap" style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;max-width:100%;margin:30px 0;">
  <iframe
    src="https://www.youtube.com/embed/VIDEO_ID_HERE"
    title="Video Title"
    frameborder="0"
    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
    allowfullscreen
    style="position:absolute;top:0;left:0;width:100%;height:100%;">
  </iframe>
</div>

<h2>About This Video</h2>
<p>
  Add notes, a transcript excerpt, or additional context about the video below.
</p>

<h2>Key Points</h2>
<p>
  Summarise the important takeaways from the video content here.
</p>""",
    },
    "code": {
        "label": "Code Showcase",
        "icon":  "💻",
        "desc":  "Display source code with syntax-highlighted blocks and documentation.",
        "html":  """\
<p>
  Description of what this code does and what problem it solves.
</p>

<h2>Source Code</h2>
<div class="bej-code-block">
<pre><code>
# Paste or type your source code here
# Use the "Attach Code File" button in the toolbar to auto-fill from a file

def example():
    print("Hello, BEJSON!")
</code></pre>
</div>

<h2>How It Works</h2>
<p>
  Explain the logic, key functions, or algorithms used in the code above.
</p>

<h2>Usage</h2>
<div class="bej-code-block">
<pre><code>
# Example usage
example()
</code></pre>
</div>

<h2>Requirements</h2>
<p>
  List any dependencies, Python version requirements, or setup steps here.
</p>""",
    },
    "tutorial": {
        "label": "Tutorial / How-To",
        "icon":  "📋",
        "desc":  "Step-by-step guide with numbered steps, code blocks, and tips.",
        "html":  """\
<p>
  Overview: what the reader will learn and what they need before starting.
</p>

<h2>Prerequisites</h2>
<p>
  List what the reader needs before following this tutorial.
</p>

<h2>Step 1 — Setup</h2>
<p>
  Describe the first step clearly.
</p>
<div class="bej-code-block">
<pre><code>
# Step 1 command or code example
pip install example-package
</code></pre>
</div>

<h2>Step 2 — Configuration</h2>
<p>
  Describe the second step.
</p>
<div class="bej-code-block">
<pre><code>
# Step 2 example
config = {"key": "value"}
</code></pre>
</div>

<h2>Step 3 — Running It</h2>
<p>
  Describe how to run or execute the result.
</p>
<div class="bej-code-block">
<pre><code>
python3 your_script.py
</code></pre>
</div>

<h2>Troubleshooting</h2>
<p>
  Common errors and how to fix them.
</p>

<h2>Next Steps</h2>
<p>
  Suggest what the reader can explore or build on from here.
</p>""",
    },

    "image_gallery": {
        "label": "Image Gallery",
        "icon":  "🖼️",
        "desc":  "Lightbox-enabled image gallery with captions and grid layout.",
        "html":  """\
<p>
  A short description of this image collection or gallery.
</p>

<h2>Gallery</h2>

<!-- Image gallery grid — each bej-gallery-item opens in lightbox -->
<div class="bej-gallery" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:20px;margin:30px 0;">

  <figure class="bej-gallery-item" style="margin:0;cursor:zoom-in;">
    <img src="../../../assets/IMAGE_FILENAME_1.jpg"
         alt="Image description 1"
         style="width:100%;height:200px;object-fit:cover;border-radius:4px;"
         onclick="this.closest('figure').querySelector('figcaption') && openLightbox(this.src)">
    <figcaption style="font-size:.82rem;color:#666;padding:8px 0;text-align:center;">Caption for image 1</figcaption>
  </figure>

  <figure class="bej-gallery-item" style="margin:0;cursor:zoom-in;">
    <img src="../../../assets/IMAGE_FILENAME_2.jpg"
         alt="Image description 2"
         style="width:100%;height:200px;object-fit:cover;border-radius:4px;">
    <figcaption style="font-size:.82rem;color:#666;padding:8px 0;text-align:center;">Caption for image 2</figcaption>
  </figure>

  <figure class="bej-gallery-item" style="margin:0;cursor:zoom-in;">
    <img src="../../../assets/IMAGE_FILENAME_3.jpg"
         alt="Image description 3"
         style="width:100%;height:200px;object-fit:cover;border-radius:4px;">
    <figcaption style="font-size:.82rem;color:#666;padding:8px 0;text-align:center;">Caption for image 3</figcaption>
  </figure>

</div>

<p style="font-size:.85rem;color:#888;margin-top:10px;">
  Click any image to view full size.
</p>

<h2>About This Gallery</h2>
<p>
  Add any additional context, credits, or description about the images here.
</p>""",
    },

    "pdf_viewer": {
        "label": "PDF Viewer",
        "icon":  "📑",
        "desc":  "Embedded PDF document with inline viewer and download fallback.",
        "html":  """\
<p>
  Description of the document — what it covers and why it is useful.
</p>

<!-- Responsive PDF embed — replace PDF_FILENAME.pdf with your file in assets/ -->
<div class="bej-pdf-wrap" style="width:100%;margin:30px 0;border:1px solid #e5e5e5;border-radius:4px;overflow:hidden;">
  <object
    data="../../../assets/PDF_FILENAME.pdf"
    type="application/pdf"
    style="width:100%;height:820px;display:block;">
    <!-- Fallback for browsers that cannot render inline PDFs -->
    <div style="padding:40px;text-align:center;background:#f8f8f8;">
      <p style="font-size:1.1rem;margin-bottom:16px;">
        Your browser cannot display this PDF inline.
      </p>
      <a href="../../../assets/PDF_FILENAME.pdf"
         download
         style="display:inline-block;padding:12px 28px;background:#DE2626;color:#fff;font-weight:700;text-decoration:none;border-radius:4px;">
        ⬇ Download PDF
      </a>
    </div>
  </object>
</div>

<div style="margin-top:16px;display:flex;gap:14px;flex-wrap:wrap;align-items:center;">
  <a href="../../../assets/PDF_FILENAME.pdf"
     download
     style="display:inline-block;padding:10px 22px;background:#DE2626;color:#fff;font-weight:700;text-decoration:none;border-radius:4px;font-size:.9rem;">
    ⬇ Download PDF
  </a>
  <a href="../../../assets/PDF_FILENAME.pdf"
     target="_blank"
     style="display:inline-block;padding:10px 22px;border:1px solid #ccc;color:#333;font-weight:700;text-decoration:none;border-radius:4px;font-size:.9rem;">
    ↗ Open in New Tab
  </a>
</div>

<h2>Document Details</h2>
<p>
  Add any relevant metadata here — author, publication date, version, number of pages, etc.
</p>""",
    },

    "review": {
        "label": "Review",
        "icon":  "⭐",
        "desc":  "Product, app, or service review with star rating, pros/cons, and verdict.",
        "html":  """\
<p>
  One-paragraph introduction — what you are reviewing and your overall first impression.
</p>

<!-- Star rating block -->
<div class="bej-rating" style="display:flex;align-items:center;gap:14px;background:#f8f8f8;padding:18px 22px;margin:24px 0;border-left:4px solid #DE2626;">
  <div style="font-size:2rem;letter-spacing:2px;">★★★★☆</div>
  <div>
    <div style="font-size:1.4rem;font-weight:900;">4 / 5</div>
    <div style="font-size:.85rem;color:#666;margin-top:2px;">Overall Rating</div>
  </div>
</div>

<h2>Overview</h2>
<p>
  Describe the product, app, or service being reviewed. Include version, price, platform, and any key context the reader needs.
</p>

<h2>What I Tested</h2>
<p>
  Describe your testing conditions — how long you used it, what tasks you performed, and on what hardware or environment.
</p>

<h2>Pros</h2>
<ul style="list-style:none;padding:0;margin:0 0 24px;">
  <li style="padding:8px 0 8px 0;border-bottom:1px solid #eee;display:flex;gap:10px;"><span style="color:#16a34a;font-weight:700;flex-shrink:0;">✓</span> Strength one — explain why this matters.</li>
  <li style="padding:8px 0 8px 0;border-bottom:1px solid #eee;display:flex;gap:10px;"><span style="color:#16a34a;font-weight:700;flex-shrink:0;">✓</span> Strength two.</li>
  <li style="padding:8px 0 8px 0;border-bottom:1px solid #eee;display:flex;gap:10px;"><span style="color:#16a34a;font-weight:700;flex-shrink:0;">✓</span> Strength three.</li>
</ul>

<h2>Cons</h2>
<ul style="list-style:none;padding:0;margin:0 0 24px;">
  <li style="padding:8px 0 8px 0;border-bottom:1px solid #eee;display:flex;gap:10px;"><span style="color:#DE2626;font-weight:700;flex-shrink:0;">✗</span> Weakness one — explain impact.</li>
  <li style="padding:8px 0 8px 0;border-bottom:1px solid #eee;display:flex;gap:10px;"><span style="color:#DE2626;font-weight:700;flex-shrink:0;">✗</span> Weakness two.</li>
</ul>

<h2>Performance</h2>
<p>
  Discuss speed, reliability, or any measurable benchmarks that are relevant to this review.
</p>

<h2>Verdict</h2>
<div style="background:#f8f8f8;border-left:4px solid #DE2626;padding:20px 24px;margin:24px 0;">
  <strong style="display:block;font-size:1.1rem;margin-bottom:8px;">Bottom Line</strong>
  <p style="margin:0;">
    Your final summary verdict — who should buy/use this and who should skip it.
  </p>
</div>

<p>
  <strong>Best for:</strong> Audience description.<br>
  <strong>Not for:</strong> Who should avoid it.
</p>""",
    },

    "multi_youtube": {
        "label": "Multi-Video Page",
        "icon":  "🎬",
        "desc":  "Grid of multiple YouTube embeds — playlist, series, or curated collection.",
        "html":  "",
    },
    "youtube_video": {
        "label": "YouTube Video",
        "icon":  "🎥",
        "desc":  "Standalone YouTube video with title and description.",
        "html":  "",
    },

    "github_project": {
        "label": "GitHub Project",
        "icon":  "🐙",
        "desc":  "Project showcase page with repo stats, install instructions, and feature list.",
        "html":  """\
<p>
  One-paragraph summary of the project — what it does, the problem it solves, and who it is for.
</p>

<!-- Project header card -->
<div class="bej-project-header" style="background:#f8f8f8;border:1px solid #e5e5e5;border-radius:6px;padding:24px 28px;margin:24px 0;display:flex;flex-wrap:wrap;gap:20px;align-items:flex-start;">
  <div style="flex:1;min-width:200px;">
    <div style="font-size:1.4rem;font-weight:900;margin-bottom:6px;">project-name</div>
    <div style="font-size:.9rem;color:#555;margin-bottom:14px;">Short tagline — one sentence.</div>
    <div style="display:flex;gap:10px;flex-wrap:wrap;">
      <a href="https://github.com/USERNAME/REPO"
         target="_blank"
         style="display:inline-flex;align-items:center;gap:6px;padding:8px 16px;background:#24292e;color:#fff;font-weight:700;font-size:.85rem;text-decoration:none;border-radius:4px;">
        🐙 View on GitHub
      </a>
      <a href="https://github.com/USERNAME/REPO/archive/refs/heads/main.zip"
         style="display:inline-flex;align-items:center;gap:6px;padding:8px 16px;border:1px solid #ccc;color:#333;font-weight:700;font-size:.85rem;text-decoration:none;border-radius:4px;">
        ⬇ Download ZIP
      </a>
    </div>
  </div>
  <div style="display:flex;gap:24px;flex-wrap:wrap;font-size:.85rem;">
    <div style="text-align:center;">
      <div style="font-size:1.5rem;font-weight:900;color:#DE2626;">⭐ 0</div>
      <div style="color:#888;">Stars</div>
    </div>
    <div style="text-align:center;">
      <div style="font-size:1.5rem;font-weight:900;color:#DE2626;">🍴 0</div>
      <div style="color:#888;">Forks</div>
    </div>
    <div style="text-align:center;">
      <div style="font-size:1.5rem;font-weight:900;color:#DE2626;">v1.0</div>
      <div style="color:#888;">Version</div>
    </div>
  </div>
</div>

<h2>Features</h2>
<ul style="list-style:none;padding:0;margin:0 0 24px;">
  <li style="padding:8px 0;border-bottom:1px solid #eee;display:flex;gap:10px;"><span style="color:#DE2626;font-weight:700;flex-shrink:0;">→</span> Feature one — brief explanation.</li>
  <li style="padding:8px 0;border-bottom:1px solid #eee;display:flex;gap:10px;"><span style="color:#DE2626;font-weight:700;flex-shrink:0;">→</span> Feature two.</li>
  <li style="padding:8px 0;border-bottom:1px solid #eee;display:flex;gap:10px;"><span style="color:#DE2626;font-weight:700;flex-shrink:0;">→</span> Feature three.</li>
  <li style="padding:8px 0;border-bottom:1px solid #eee;display:flex;gap:10px;"><span style="color:#DE2626;font-weight:700;flex-shrink:0;">→</span> Feature four.</li>
  </ul>

  <h2>Installation</h2>
  <div class="bej-code-block">
  <pre><code>
  # Clone the repo
  git clone https://github.com/USERNAME/REPO.git
  cd REPO

  # Install dependencies (Python example) pip install -r requirements.txt </code></pre> </div>  <h2>Usage</h2> <div class="bej-code-block"> <pre><code> # Basic usage example python3 main.py  # With options python3 main.py --flag value </code></pre> </div>  <h2>Requirements</h2> <p>   List language versions, OS compatibility, or system dependencies here. </p>  <h2>File Structure</h2> <div class="bej-code-block"> <pre><code> REPO/ ├── main.py          # Entry point ├── requirements.txt ├── README.md └── src/     ├── module_a.py     └── module_b.py </code></pre> </div>  <h2>License</h2> <p>   State the license (e.g. MIT, Apache 2.0, GPL) and link to the LICENSE file on GitHub. </p>  <h2>Contributing</h2> <p>   Describe how others can contribute — pull requests, issue reports, coding standards. </p>""",
    },

    "multi_file_code": {
        "label": "Code Project (Multi-File)",
        "icon":  "💻",
        "desc":  "Showcase full code projects with tabbed files and a ZIP download.",
        "html":  "<!-- DYNAMIC_CODE_EDITOR -->",
    },
  }

# =============================================================================
# BASE HTML SHELL
# =============================================================================

_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>{{ page_title }} — BEJSON Page Editor</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&family=Source+Code+Pro&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0f0f0f;--panel:#161616;--card:#1c1c1c;--acc:#DE2626;
  --border:#2a2a2a;--fg:#f0f0f0;--muted:#888;--green:#16a34a;
  --sb-w:230px;
}
*{box-sizing:border-box;margin:0;padding:0;}
html,body{height:100%;}
body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--fg);font-size:15px;overflow-x:hidden;}
a{color:var(--acc);text-decoration:none;} a:hover{opacity:.8;text-decoration:underline;}
strong, b{color:var(--acc);font-weight:700;}
em, i{color:var(--acc);opacity:.9;}

#sb-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:90;}
#sb-overlay.show{display:block;}

.sb{position:fixed;top:0;left:0;height:100%;width:var(--sb-w);background:var(--panel);border-right:1px solid var(--border);display:flex;flex-direction:column;z-index:100;transition:transform .25s ease;}
.sb-logo{padding:18px 16px;border-bottom:2px solid var(--acc);font-size:1.15rem;font-weight:900;letter-spacing:-1px;color:#fff;flex-shrink:0;}
.sb-logo span{color:var(--acc);}
.sb-logo small{font-size:.65rem;font-weight:400;color:var(--muted);display:block;margin-top:2px;letter-spacing:.5px;}
.sb nav{flex:1;overflow-y:auto;}
.sb nav a{display:flex;align-items:center;gap:10px;padding:12px 16px;color:var(--muted);font-size:.88rem;font-weight:600;transition:.15s;border-left:3px solid transparent;}
.sb nav a:hover{color:#fff;background:rgba(222,38,38,.1);}
.sb nav a.on{color:#fff;background:rgba(222,38,38,.15);border-left-color:var(--acc);}
.sb-sect{padding:10px 16px 4px;font-size:.65rem;text-transform:uppercase;letter-spacing:1px;color:#444;font-weight:700;}
.sb-foot{padding:12px 16px;font-size:.68rem;color:#444;border-top:1px solid var(--border);flex-shrink:0;}

.topbar{position:fixed;top:0;left:var(--sb-w);right:0;height:52px;background:var(--panel);border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 20px;gap:14px;z-index:80;}
.topbar h2{font-size:.93rem;font-weight:800;color:var(--acc);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.hamburger{display:none;background:none;border:none;color:var(--fg);font-size:1.4rem;cursor:pointer;padding:4px 6px;line-height:1;flex-shrink:0;}

.main{margin-left:var(--sb-w);margin-top:52px;min-height:calc(100vh - 52px);display:flex;flex-direction:column;}
.content{padding:22px;width:100%;max-width:1100px;}

.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:20px;margin-bottom:16px;}
.card-hd{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid var(--border);gap:10px;flex-wrap:wrap;}
.card-hd h3{font-size:.93rem;font-weight:700;}

.btn{display:inline-flex;align-items:center;gap:6px;padding:9px 16px;border:none;border-radius:6px;font-family:inherit;font-weight:700;font-size:.82rem;cursor:pointer;text-decoration:none;transition:.15s;white-space:nowrap;touch-action:manipulation;}
.btn-red{background:var(--acc);color:#fff;} .btn-red:hover{background:#b91c1c;}
.btn-grey{background:#2a2a2a;color:#ccc;border:1px solid var(--border);} .btn-grey:hover{background:#333;}
.btn-green{background:var(--green);color:#fff;} .btn-green:hover{background:#15803d;}
.btn-sm{padding:6px 11px;font-size:.76rem;}
.btn:disabled{opacity:.4;cursor:default;}
.btn-row{display:flex;gap:10px;flex-wrap:wrap;margin-top:4px;}

label{display:block;margin-bottom:5px;font-size:.8rem;font-weight:600;color:var(--muted);}
input[type=text],input[type=url],select,textarea{
  width:100%;padding:10px 13px;background:#111;border:1px solid var(--border);
  border-radius:6px;color:#fff;font-family:inherit;font-size:.95rem;
  -webkit-appearance:none;
}
input:focus,textarea:focus,select:focus{outline:none;border-color:var(--acc);}
.fg{margin-bottom:14px;}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px;}
.grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;}

/* ── EDITOR ── */
.editor-wrap{border:1px solid var(--border);border-radius:8px;overflow:hidden;}
.editor-toolbar{background:#111;border-bottom:1px solid var(--border);padding:10px 12px;display:flex;gap:6px;flex-wrap:wrap;align-items:center;}
.tb-btn{background:#1e1e1e;border:1px solid var(--border);color:#ccc;border-radius:5px;padding:6px 11px;font-family:'Source Code Pro',monospace;font-size:.76rem;cursor:pointer;transition:.15s;white-space:nowrap;}
.tb-btn:hover{background:var(--acc);color:#fff;border-color:var(--acc);}
.tb-sep{width:1px;height:22px;background:var(--border);flex-shrink:0;margin:0 2px;}
.editor-area{width:100%;min-height:480px;padding:16px;background:#0a0a0a;border:none;color:#e8e8e8;font-family:'Source Code Pro',monospace;font-size:.85rem;line-height:1.7;resize:vertical;display:block;}

/* ── TEMPLATE CARDS ── */
.tpl-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px;margin-top:8px;}
.tpl-card{background:#111;border:2px solid var(--border);border-radius:8px;padding:20px 18px;cursor:pointer;transition:.2s;text-align:center;}
.tpl-card:hover{border-color:var(--acc);background:rgba(222,38,38,.05);}
.tpl-card.selected{border-color:var(--acc);background:rgba(222,38,38,.1);}
.tpl-card .tpl-icon{font-size:2rem;margin-bottom:10px;}
.tpl-card .tpl-label{font-size:.9rem;font-weight:700;margin-bottom:6px;}
.tpl-card .tpl-desc{font-size:.75rem;color:var(--muted);line-height:1.5;}

/* ── PAGE LIST ── */
table{width:100%;border-collapse:collapse;}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--border);font-size:.86rem;}
th{font-size:.68rem;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);}
tr:hover{background:rgba(255,255,255,.02);}
td:last-child{white-space:nowrap;}
.badge{display:inline-block;padding:3px 8px;border-radius:4px;font-size:.68rem;font-weight:700;text-transform:uppercase;}
.b-page{background:#1e3a5f;color:#60a5fa;}
.b-cat{background:#1e2a1e;color:#86efac;}

/* ── ALERTS ── */
.alert{padding:12px 16px;border-radius:6px;margin-bottom:16px;font-size:.88rem;}
.a-ok{background:rgba(34,197,94,.1);border:1px solid rgba(34,197,94,.25);color:#4ade80;}
.a-err{background:rgba(220,38,38,.1);border:1px solid rgba(220,38,38,.3);color:#f87171;}

/* ── MODAL ── */
.modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:200;align-items:center;justify-content:center;}
.modal-bg.open{display:flex;}
.modal{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:24px;width:100%;max-width:520px;}
.modal h3{font-size:1rem;font-weight:700;margin-bottom:14px;color:var(--acc);}
.modal .fg{margin-bottom:12px;}

/* ── MOBILE ── */
@media(max-width:700px){
  :root{--sb-w:230px;}
  .sb{transform:translateX(calc(-1 * var(--sb-w)));}
  .sb.open{transform:translateX(0);}
  .topbar{left:0;}
  .main{margin-left:0;}
  .hamburger{display:block;}
  .grid2,.grid3{grid-template-columns:1fr;}
  .content{padding:14px;}
  .card{padding:14px;}
  .editor-area{min-height:320px;}
  .tpl-grid{grid-template-columns:1fr 1fr;}
  input[type=text],input[type=url],select{font-size:16px;}
}
</style>
</head>
<body>
<div id="sb-overlay" onclick="closeSb()"></div>
<div class="sb" id="sidebar">
  <div class="sb-logo">BEJSON<span>.</span><small>Page Editor v16.0</small></div>
    <nav>
    <div class="sb-sect">Editor</div>
    <a href="/"      class="{{ 'on' if active=='list'   else '' }}">&#9783; All Pages</a>
    <a href="/new"   class="{{ 'on' if active=='new'    else '' }}">&#43; New Page</a>
    <a href="#" onclick="openAiModal()">&#129302; AI Multi-Page Builder</a>
    <div class="sb-sect">Next Gen</div>
    <a href="/v2" style="color:var(--green);">&#128640; Try Editor V2 (Beta)</a>
    <div class="sb-sect">Tools</div>
    <a href="http://localhost:5001" target="_blank">&#8599; Open CMS</a>
    <a href="http://localhost:5001/publish" target="_blank">&#9654; Open Publisher</a>
  </nav>
  <div class="sb-foot">port 5003 &mdash; same Data/ dir as CMS</div>
</div>
<div class="topbar">
  <button class="hamburger" onclick="toggleSb()">&#9776;</button>
  <h2>{{ page_title }}</h2>
  {% if extra_buttons %}{{ extra_buttons | safe }}{% endif %}
</div>
<div class="main">
  <div class="content">
    {% with msgs = get_flashed_messages(with_categories=true) %}
      {% if msgs %}{% for cat, msg in msgs %}
      <div class="alert {{ 'a-ok' if cat == 'success' else 'a-err' }}">{{ msg }}</div>
      {% endfor %}{% endif %}
    {% endwith %}
    {{ body | safe }}
  </div>
</div>
<!-- ── AI MULTI-PAGE MODAL ── -->
<div class="modal-bg" id="aiModal">
  <div class="modal" style="max-width: 600px;">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
      <h3 style="margin:0;">&#129302; AI Multi-Page Builder</h3>
      <div id="ai-status-pill" style="font-family:'Source Code Pro'; font-size:.65rem; padding:3px 8px; border-radius:4px; background:var(--border); color:var(--muted);">IDLE</div>
    </div>

    <div id="ai-step-1">
      <div class="fg">
        <label>What would you like to build? (e.g. "A 4-page tutorial on Python decorators")</label>
        <textarea id="ai-prompt" placeholder="Describe the document or project..." style="min-height:100px;"></textarea>
      </div>
      
      <div class="grid2">
        <div class="fg">
          <label>Model</label>
          <select id="ai-model">
            {% for m in ai_models %}
            <option value="{{ m }}">{{ m }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="fg">
          <label>AI Profile (optional)</label>
          <select id="ai-profile">
            <option value="">Default CMS Writer</option>
            <!-- Loaded via JS -->
          </select>
        </div>
      </div>

      <div class="grid2">
        <div class="fg">
          <label>Category</label>
          <input type="text" id="ai-category" value="AI Generated">
        </div>
        <div class="fg">
          <label>Author</label>
          <input type="text" id="ai-author" value="Gemini Builder">
        </div>
      </div>

      <div class="fg">
        <label>Context Files ({{ context_dir }})</label>
        <div id="ai-context-list" style="max-height:120px; overflow-y:auto; background:#111; border:1px solid var(--border); border-radius:6px; padding:8px; display:flex; flex-direction:column; gap:5px;">
          <!-- Loaded via JS -->
          <span style="font-size:.75rem; color:var(--muted);">Loading context...</span>
        </div>
      </div>

      <div class="btn-row">
        <button type="button" class="btn btn-red" id="btn-gen-plan" onclick="generateAiPlan()">Generate Plan</button>
        <button type="button" class="btn btn-grey" onclick="closeModal('aiModal')">Cancel</button>
      </div>
    </div>

    <div id="ai-step-2" style="display:none;">
      <div class="card" style="background:#111; margin-bottom:15px;">
        <div class="card-hd" style="border:none; margin-bottom:5px;"><h3>Proposed Plan</h3></div>
        <div id="ai-plan-list" style="font-size:.85rem; max-height:250px; overflow-y:auto;">
          <!-- Plan steps here -->
        </div>
      </div>
      <div class="btn-row">
        <button type="button" class="btn btn-red" id="btn-build-pages" onclick="buildAiPages()">Build All Pages</button>
        <button type="button" class="btn btn-grey" onclick="resetAiModal()">Back</button>
      </div>
    </div>

    <div id="ai-step-3" style="display:none;">
      <div class="card" style="background:#111; margin-bottom:15px;">
        <div class="card-hd" style="border:none; margin-bottom:5px;"><h3>Building Pages...</h3></div>
        <div id="ai-progress-list" style="font-size:.85rem; max-height:250px; overflow-y:auto;">
          <!-- Progress here -->
        </div>
      </div>
      <div id="ai-final-actions" style="display:none;">
        <div class="alert a-ok">✅ All pages created successfully!</div>
        <div class="btn-row">
          <button type="button" class="btn btn-red" onclick="location.reload()">Refresh Page List</button>
          <button type="button" class="btn btn-grey" onclick="closeModal('aiModal')">Close</button>
        </div>
      </div>
    </div>

  </div>
</div>

<script>
...
function closeSb(){document.getElementById('sidebar').classList.remove('open');document.getElementById('sb-overlay').classList.remove('show');}
...
// AI Multi-Page Builder Logic
var _currentAiPlan = null;

function openAiModal() {
  openModal('aiModal');
  loadAiContext();
  loadAiProfiles();
}

function resetAiModal() {
  document.getElementById('ai-step-1').style.display = 'block';
  document.getElementById('ai-step-2').style.display = 'none';
  document.getElementById('ai-step-3').style.display = 'none';
  setAiStatus('IDLE', 'muted');
}

function setAiStatus(msg, colorClass) {
  const pill = document.getElementById('ai-status-pill');
  pill.textContent = msg;
  pill.style.background = colorClass === 'red' ? 'var(--acc)' : 'var(--border)';
  pill.style.color = colorClass === 'red' ? '#fff' : 'var(--muted)';
}

function loadAiProfiles() {
  const sel = document.getElementById('ai-profile');
  fetch('/api/ai/profiles').then(r => r.json()).then(d => {
    // Keep the default option
    const def = sel.options[0];
    sel.innerHTML = '';
    sel.appendChild(def);
    if(d.profiles) {
      d.profiles.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.filename;
        opt.textContent = p.name;
        sel.appendChild(opt);
      });
    }
  });
}

function loadAiContext() {
  const list = document.getElementById('ai-context-list');
  fetch('/api/ai/context').then(r => r.json()).then(d => {
    list.innerHTML = '';
    if(!d.files || !d.files.length) {
      list.innerHTML = '<span style="font-size:.75rem; color:var(--muted);">No files in Context/</span>';
      return;
    }
    d.files.forEach(f => {
      const row = document.createElement('div');
      row.style = 'display:flex; align-items:center; gap:8px; font-size:.75rem;';
      row.innerHTML = `<input type="checkbox" ${f.enabled ? 'checked' : ''} onchange="toggleAiContext('${f.filename}')"> <span>${f.filename}</span>`;
      list.appendChild(row);
    });
  });
}

function toggleAiContext(filename) {
  fetch('/api/ai/context/toggle', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({filename: filename})
  });
}

function generateAiPlan() {
  const prompt = document.getElementById('ai-prompt').value.trim();
  const model = document.getElementById('ai-model').value;
  const profile = document.getElementById('ai-profile').value;
  if(!prompt) { alert('Please enter a prompt.'); return; }

  setAiStatus('SENDING', 'red');
  document.getElementById('btn-gen-plan').disabled = true;

  fetch('/api/ai/generate_plan', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({prompt: prompt, model: model, profile: profile})
  }).then(r => r.json()).then(d => {
    if(d.ok) {
      listenToAiStream(d.job_id, (ev) => {
        if(ev.type === 'plan_ready') {
          _currentAiPlan = ev.plan;
          renderAiPlan(ev.plan);
          document.getElementById('ai-step-1').style.display = 'none';
          document.getElementById('ai-step-2').style.display = 'block';
        }
        if(ev.type === 'status') setAiStatus(ev.code, 'red');
        if(ev.type === 'complete') {
          document.getElementById('btn-gen-plan').disabled = false;
          setAiStatus('IDLE', 'muted');
        }
        if(ev.type === 'error') {
          alert('Error: ' + ev.message);
          document.getElementById('btn-gen-plan').disabled = false;
        }
      });
    }
  });
}

function renderAiPlan(plan) {
  const list = document.getElementById('ai-plan-list');
  list.innerHTML = '';
  plan.forEach(s => {
    const item = document.createElement('div');
    item.style = 'padding:10px; border-bottom:1px solid var(--border);';
    item.innerHTML = `<div style="font-weight:700; color:var(--acc);">Step ${s.step}: ${s.title}</div><div style="font-size:.75rem; color:var(--muted);">${s.description}</div>`;
    list.appendChild(item);
  });
}

function buildAiPages() {
  if(!_currentAiPlan) return;
  const model = document.getElementById('ai-model').value;
  const profile = document.getElementById('ai-profile').value;
  const category = document.getElementById('ai-category').value;
  const author = document.getElementById('ai-author').value;

  document.getElementById('ai-step-2').style.display = 'none';
  document.getElementById('ai-step-3').style.display = 'block';
  document.getElementById('ai-progress-list').innerHTML = '';
  document.getElementById('ai-final-actions').style.display = 'none';

  fetch('/api/ai/generate_pages', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({plan: _currentAiPlan, model: model, profile: profile, category: category, author: author})
  }).then(r => r.json()).then(d => {
    if(d.ok) {
      listenToAiStream(d.job_id, (ev) => {
        if(ev.type === 'status') {
          setAiStatus(ev.code, 'red');
          if(ev.message) {
            const p = document.createElement('div');
            p.style = 'font-size:.7rem; color:var(--muted); margin-top:5px;';
            p.textContent = '> ' + ev.message;
            document.getElementById('ai-progress-list').appendChild(p);
          }
        }
        if(ev.type === 'page_created') {
          const p = document.createElement('div');
          p.style = 'font-weight:700; color:var(--green); margin-top:5px;';
          p.textContent = `✓ Created: ${ev.title}`;
          document.getElementById('ai-progress-list').appendChild(p);
        }
        if(ev.type === 'complete') {
          setAiStatus('IDLE', 'muted');
          document.getElementById('ai-final-actions').style.display = 'block';
        }
        if(ev.type === 'error') {
          const p = document.createElement('div');
          p.style = 'font-weight:700; color:var(--acc); margin-top:5px;';
          p.textContent = `✗ Error: ${ev.message}`;
          document.getElementById('ai-progress-list').appendChild(p);
        }
      });
    }
  });
}

function listenToAiStream(jobId, onEvent) {
  const es = new EventSource('/api/ai/stream/' + jobId);
  es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if(data.type === 'ping') return;
    onEvent(data);
    if(data.type === 'complete' || data.type === 'error') es.close();
  };
  es.onerror = () => es.close();
}
</script>
</body>
</html>"""


def _page(title, active, body, extra_buttons=""):
    return render_template_string(
        _SHELL,
        page_title=title, active=active, body=body,
        extra_buttons=extra_buttons,
        ai_models=AI_MODELS,
        context_dir=CONTEXT_DIR
    )


def _multi_code_editor_html():
    """Dynamic multi-file code editor UI with multi-file upload support."""
    return """
<div id="multi-code-editor">
  <p style="font-size:.82rem;color:var(--muted);margin-bottom:14px;">
    Add multiple code files. Enter a filename and the source code for each.
    You can also <b>upload multiple files at once</b> to populate this list.
  </p>
  
  <div class="fg" style="max-width:600px;">
    <label>Project Introduction / Description</label>
    <textarea name="code_intro" placeholder="Explain what this project does..." style="min-height:80px;"></textarea>
  </div>

  <div class="fg">
    <label>Bulk Upload Files</label>
    <input type="file" id="code-bulk-upload" multiple class="btn btn-grey btn-sm" style="width:auto;padding:5px;" onchange="handleBulkUpload(event)">
  </div>

  <div id="code-file-rows">
    <!-- Rows injected by JS -->
  </div>

  <div style="margin-top:12px;display:flex;gap:10px;">
    <button type="button" class="btn btn-grey btn-sm" onclick="addCodeFileRow()">+ Add File Manually</button>
    <label style="display:inline-flex;align-items:center;gap:8px;font-size:.8rem;color:var(--muted);margin:0;">
      <input type="checkbox" name="include_zip" checked value="true"> Generate ZIP download for this project
    </label>
  </div>
</div>

<script>
var _codeFileCount = 0;

function addCodeFileRow(filename, content){
  _codeFileCount++;
  var n = _codeFileCount;
  var row = document.createElement('div');
  row.id = 'cfrow-'+n;
  row.className = 'card';
  row.style = 'margin-bottom:10px;padding:15px;background:#111;';
  row.innerHTML = `
    <div style="display:flex;gap:10px;margin-bottom:10px;align-items:center;">
      <input type="text" name="cf_name_${n}" placeholder="filename.py" value="${filename||''}" style="flex:1;" required>
      <button type="button" onclick="removeCodeFileRow(${n})" style="background:#3a0a0a;color:#f87171;border:1px solid #7f1d1d;border-radius:4px;padding:5px 10px;cursor:pointer;font-size:.8rem;">✕</button>
    </div>
    <textarea name="cf_content_${n}" placeholder="Paste code here..." style="font-family:monospace;min-height:150px;">${content||''}</textarea>
  `;
  document.getElementById('code-file-rows').appendChild(row);
}

function removeCodeFileRow(n){
  var el = document.getElementById('cfrow-'+n);
  if(el) el.remove();
}

function handleBulkUpload(event){
  const files = event.target.files;
  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    const reader = new FileReader();
    reader.onload = (e) => {
      addCodeFileRow(file.name, e.target.result);
    };
    reader.readAsText(file);
  }
}

// Start with one empty row
addCodeFileRow();
</script>
"""

def _gallery_editor_html(existing_html=""):
    """Gallery dynamic editor — upgraded with visual asset picker."""
    return """
<div id="gallery-editor">
  <div class="card" style="padding:15px;border-style:dashed;margin-bottom:20px;">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
      <h3 style="font-size:.9rem;margin:0;">Gallery Images</h3>
      <button type="button" class="btn btn-primary btn-sm" onclick="openMediaPicker('gallery')">&#128194; Open Media Library</button>
    </div>
    <p style="font-size:.8rem;color:var(--muted);">Add images from your media library. Drag to reorder (coming soon).</p>
    <div id="gallery-rows" style="margin-top:15px;">
      <!-- rows injected by JS -->
    </div>
    <button type="button" class="btn btn-grey btn-sm" style="margin-top:10px;width:100%;" onclick="addGalleryRow()">+ Add Empty Slot</button>
  </div>
  <div class="fg" style="max-width:480px;">
    <label>Gallery Introduction</label>
    <input type="text" name="gallery_intro" placeholder="Optional context or description for this gallery...">
  </div>
</div>

<!-- Media Picker Modal -->
<div id="media-picker-modal" class="modal-overlay" style="display:none;z-index:2000;" onclick="if(event.target===this)closeMediaPicker()">
  <div class="modal" style="max-width:900px;width:90%;max-height:85vh;">
    <div class="modal-header">
      <h3 id="media-picker-title">Select Media</h3>
      <button type="button" class="close-btn" onclick="closeMediaPicker()">&times;</button>
    </div>
    <div class="modal-body">
      <div id="media-picker-grid" class="asset-grid" style="grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:15px;">
        <!-- Assets loaded here -->
      </div>
    </div>
  </div>
</div>

<script>
var _galleryCount = 0;
var _activePickerTarget = null;

function openMediaPicker(target){
  _activePickerTarget = target;
  document.getElementById('media-picker-modal').style.display = 'flex';
  loadMediaPickerAssets();
}

function closeMediaPicker(){
  document.getElementById('media-picker-modal').style.display = 'none';
}

function loadMediaPickerAssets(){
  const grid = document.getElementById('media-picker-grid');
  grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:40px;">Loading library...</div>';
  
  fetch('/list_assets').then(r=>r.json()).then(d=>{
    grid.innerHTML = '';
    if(!d.files || !d.files.length){
      grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--muted);">Media library is empty.</div>';
      return;
    }
    d.files.forEach(f => {
      const isImg = /\\.(jpg|jpeg|png|gif|webp|svg)$/i.test(f);
      const div = document.createElement('div');
      div.className = 'asset-item';
      div.style = 'cursor:pointer;position:relative;border-radius:6px;overflow:hidden;border:1px solid var(--border);background:var(--card);aspect-ratio:1;';
      div.onclick = () => selectMediaFile(f);
      
      if(isImg){
        div.innerHTML = '<img src="/assets/'+f+'" style="width:100%;height:100%;object-fit:cover;" loading="lazy">';
      } else {
        div.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;font-size:2rem;">📄</div>';
      }
      div.innerHTML += '<div style="position:absolute;bottom:0;left:0;right:0;background:rgba(0,0,0,0.7);color:#fff;font-size:0.65rem;padding:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+f+'</div>';
      grid.appendChild(div);
    });
  });
}

function selectMediaFile(f){
  if(_activePickerTarget === 'gallery'){
    addGalleryRow(f);
  } else if(_activePickerTarget === 'featured'){
    document.querySelector('select[name="featured_img"]').value = f;
  }
  closeMediaPicker();
}

function addGalleryRow(fname){
  _galleryCount++;
  var n = _galleryCount;
  var row = document.createElement('div');
  row.id = 'grow-'+n;
  row.className = 'card';
  row.style = 'display:flex;gap:12px;align-items:center;margin-bottom:12px;padding:10px;background:var(--bg);';
  row.innerHTML = '<div style="width:60px;height:60px;background:var(--card);border-radius:4px;display:flex;align-items:center;justify-content:center;overflow:hidden;flex-shrink:0;">'
    + (fname ? '<img src="/assets/'+fname+'" style="width:100%;height:100%;object-fit:cover;">' : '<span style="color:var(--muted);font-size:1.5rem;">?</span>')
    + '</div>'
    + '<div style="flex:1;">'
    + '  <input type="text" name="gallery_file_'+n+'" placeholder="filename.jpg" value="'+(fname||'')+'" style="width:100%;margin-bottom:5px;font-family:monospace;font-size:.85rem;" required>'
    + '  <input type="text" name="gallery_caption_'+n+'" placeholder="Add a caption..." style="width:100%;font-size:.85rem;">'
    + '</div>'
    + '<button type="button" onclick="removeGalleryRow('+n+')" style="background:#3a0a0a;color:#f87171;border:1px solid #7f1d1d;border-radius:4px;padding:8px 12px;cursor:pointer;font-size:1rem;flex-shrink:0;">✕</button>';
  document.getElementById('gallery-rows').appendChild(row);
}

function removeGalleryRow(n){
  var el = document.getElementById('grow-'+n);
  if(el) el.remove();
}
</script>
"""


def _youtube_editor_html(existing_html=""):
    """Single YouTube video editor."""
    return """
<div id="youtube-editor">
  <div class="card" style="padding:20px;background:var(--bg);border-style:dashed;">
    <div class="fg">
      <label>YouTube Video URL or ID *</label>
      <input type="text" name="yt_url" placeholder="https://www.youtube.com/watch?v=... or VIDEO_ID" required>
    </div>
    <div class="fg" style="margin-top:15px;">
      <label>Video Caption / Description</label>
      <input type="text" name="yt_caption" placeholder="A short description for this video...">
    </div>
  </div>
</div>
"""


def _multivideo_editor_html(existing_html=""):
    """Multi-video dynamic editor — add/remove YouTube URL + label rows."""
    return """
<div id="multivideo-editor">
  <p style="font-size:.82rem;color:var(--muted);margin-bottom:14px;">
    Enter YouTube URLs or video IDs. Add a label for each video.
    The embed grid is generated on save.
  </p>
  <div class="fg" style="max-width:600px;">
    <label>Page Introduction (optional)</label>
    <input type="text" name="video_intro" placeholder="Introduction to this video collection.">
  </div>
  <div style="font-size:.75rem;color:var(--muted);margin-bottom:10px;display:grid;grid-template-columns:1fr 2fr 30px;gap:10px;padding:0 4px;">
    <span>YouTube URL / ID</span><span>Label</span><span></span>
  </div>
  <div id="video-rows"></div>
  <div style="margin-top:12px;">
    <button type="button" class="btn btn-grey btn-sm" onclick="addVideoRow()">+ Add Video</button>
  </div>
</div>
<script>
var _videoCount = 0;
function addVideoRow(url, label){
  _videoCount++;
  var n = _videoCount;
  var row = document.createElement('div');
  row.id = 'vrow-'+n;
  row.style = 'display:grid;grid-template-columns:1fr 2fr 30px;gap:10px;margin-bottom:10px;align-items:center;';
  row.innerHTML = '<input type="url" name="video_url_'+n+'" placeholder="https://youtu.be/..." value="'+(url||'')+'">'
    + '<input type="text" name="video_label_'+n+'" placeholder="Video title" value="'+(label||'')+'">'
    + '<button type="button" onclick="removeVideoRow('+n+')" style="background:#3a0a0a;color:#f87171;border:1px solid #7f1d1d;border-radius:4px;padding:5px 8px;cursor:pointer;font-size:.8rem;">✕</button>';
  document.getElementById('video-rows').appendChild(row);
}
function removeVideoRow(n){
  var el = document.getElementById('vrow-'+n);
  if(el) el.remove();
}
addVideoRow();
addVideoRow();
addVideoRow();
</script>"""


def _code_editor_html(existing_source="", existing_md=""):
    """Code showcase editor with source textarea + optional markdown attach tab."""
    return f"""
<div id="code-editor">
  <div class="fg">
    <label>Description (optional)</label>
    <input type="text" name="code_desc" placeholder="What does this code do?">
  </div>
  <div style="display:flex;gap:14px;flex-wrap:wrap;margin-bottom:14px;">
    <div class="fg" style="flex:1;min-width:180px;">
      <label>Source File Name (for tab label)</label>
      <input type="text" name="code_filename" placeholder="main.py">
    </div>
    <div class="fg" style="flex:1;min-width:180px;">
      <label>Markdown File Name (for tab label)</label>
      <input type="text" name="md_filename" placeholder="README.md">
    </div>
  </div>

  <!-- Tab headers -->
  <div style="display:flex;gap:0;border-bottom:2px solid var(--acc);">
    <button type="button" id="code-tab-src" onclick="switchCodeTab('src')"
      style="padding:8px 18px;background:var(--acc);color:#fff;border:none;font-weight:700;cursor:pointer;font-size:.85rem;">
      Source Code
    </button>
    <button type="button" id="code-tab-md" onclick="switchCodeTab('md')"
      style="padding:8px 18px;background:#1e1e1e;color:#aaa;border:none;font-weight:700;cursor:pointer;font-size:.85rem;">
      Markdown File
    </button>
  </div>

  <!-- Source pane -->
  <div id="code-pane-src">
    <textarea name="source_code_raw" id="source_code_raw"
      class="editor-area" style="min-height:380px;" spellcheck="false"
      placeholder="Paste or type your source code here...">{existing_source}</textarea>
    <div style="margin-top:8px;">
      <label>Or upload a code file:</label>
      <input type="file" id="codeFileInputInline"
             accept=".py,.js,.ts,.html,.htm,.css,.json,.xml,.sh,.bash,.txt,.md,.csv,.sql,.yaml,.yml,.ini,.cfg,.toml,.c,.cpp,.java,.rb,.go,.rs"
             style="background:#111;border:1px solid var(--border);border-radius:6px;padding:8px;color:#ccc;width:100%;margin-top:6px;">
      <button type="button" class="btn btn-grey btn-sm" style="margin-top:6px;" onclick="loadCodeFileInline()">Load File into Editor</button>
      <div id="code-load-status" style="font-size:.78rem;color:var(--muted);margin-top:4px;"></div>
    </div>
  </div>

  <!-- Markdown pane -->
  <div id="code-pane-md" style="display:none;">
    <textarea name="markdown_raw" id="markdown_raw"
      class="editor-area" style="min-height:380px;" spellcheck="false"
      placeholder="Paste Markdown content here, or attach a .md file below...">{existing_md}</textarea>
    <div style="margin-top:8px;">
      <label>Or upload a Markdown file:</label>
      <input type="file" id="mdFileInput" accept=".md,.txt,.markdown"
             style="background:#111;border:1px solid var(--border);border-radius:6px;padding:8px;color:#ccc;width:100%;margin-top:6px;">
      <button type="button" class="btn btn-grey btn-sm" style="margin-top:6px;" onclick="loadMdFile()">Load File into Editor</button>
      <div id="md-load-status" style="font-size:.78rem;color:var(--muted);margin-top:4px;"></div>
    </div>
  </div>
</div>
<script>
function switchCodeTab(which){{
  if(which==='src'){{
    document.getElementById('code-pane-src').style.display='block';
    document.getElementById('code-pane-md').style.display='none';
    document.getElementById('code-tab-src').style.background='var(--acc)';
    document.getElementById('code-tab-src').style.color='#fff';
    document.getElementById('code-tab-md').style.background='#1e1e1e';
    document.getElementById('code-tab-md').style.color='#aaa';
  }} else {{
    document.getElementById('code-pane-src').style.display='none';
    document.getElementById('code-pane-md').style.display='block';
    document.getElementById('code-tab-src').style.background='#1e1e1e';
    document.getElementById('code-tab-src').style.color='#aaa';
    document.getElementById('code-tab-md').style.background='var(--acc)';
    document.getElementById('code-tab-md').style.color='#fff';
  }}
}}
function loadCodeFileInline(){{
  var input = document.getElementById('codeFileInputInline');
  var status = document.getElementById('code-load-status');
  if(!input.files.length){{ status.textContent='Select a file first.'; return; }}
  var file = input.files[0];
  var fd = new FormData(); fd.append('code_file', file);
  fetch('/upload_code',{{method:'POST',body:fd}})
    .then(r=>r.json()).then(d=>{{
      if(d.ok){{
        // Strip the bej-code-block wrapper for the raw editor
        var raw = d.snippet.replace(/<div class="bej-code-block">[\\s\\S]*?<pre><code>\\n?/,'').replace(/\\n?<\\/code><\\/pre>\\n<\\/div>\\n?/,'');
        document.getElementById('source_code_raw').value = raw;
        status.textContent='✓ ' + d.filename + ' loaded.';
        status.style.color='#4ade80';
      }} else {{
        status.textContent='✗ ' + d.error;
        status.style.color='#f87171';
      }}
    }});
}}
function loadMdFile(){{
  var input = document.getElementById('mdFileInput');
  var status = document.getElementById('md-load-status');
  if(!input.files.length){{ status.textContent='Select a file first.'; return; }}
  var file = input.files[0];
  var fd = new FormData(); fd.append('md_file', file);
  fetch('/upload_markdown',{{method:'POST',body:fd}})
    .then(r=>r.json()).then(d=>{{
      if(d.ok){{
        document.getElementById('markdown_raw').value = d.content;
        status.textContent='✓ ' + d.filename + ' loaded.';
        status.style.color='#4ade80';
      }} else {{
        status.textContent='✗ ' + d.error;
        status.style.color='#f87171';
      }}
    }});
}}
</script>"""


# =============================================================================
# AI JOB QUEUE & CONTEXT HELPERS
# =============================================================================

AI_JOB_QUEUES = {}

def _ai_push(job_id, event):
    if job_id in AI_JOB_QUEUES:
        AI_JOB_QUEUES[job_id].put(event)

def _get_context_files():
    if not os.path.exists(CONTEXT_DIR):
        os.makedirs(CONTEXT_DIR, exist_ok=True)
    files = []
    for f in sorted(os.listdir(CONTEXT_DIR)):
        if os.path.isfile(os.path.join(CONTEXT_DIR, f)):
            files.append(f)
    return files

def _get_ai_profiles():
    profiles = []
    if not os.path.exists(PROFILES_DIR): return []
    for f in sorted(os.listdir(PROFILES_DIR)):
        if f.endswith('.bejson'):
            try:
                with open(os.path.join(PROFILES_DIR, f), 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
                if data.get('Values') and len(data['Values']) > 0:
                    fields = {fi['name']: i for i, fi in enumerate(data['Fields'])}
                    row = data['Values'][0]
                    profiles.append({
                        "filename": f,
                        "name": row[fields['Name']],
                        "persona": row[fields['Persona']],
                        "system": row[fields['SystemInstruction']]
                    })
            except: pass
    return profiles

# In-memory context toggle state
AI_CONTEXT_STATE = {}

def _load_context_parts():
    parts = []
    for f, enabled in AI_CONTEXT_STATE.items():
        if enabled:
            fpath = os.path.join(CONTEXT_DIR, f)
            if os.path.exists(fpath):
                try:
                    with open(fpath, 'r', encoding='utf-8', errors='replace') as fh:
                        content = fh.read()
                    parts.append({"text": f"[CONTEXT FILE: {f}]\n{content}"})
                except: pass
    return parts

# =============================================================================
# ROUTE — PAGE LIST
# =============================================================================

@app.route('/')
def r_list():
    pages = _get_pages()
    rows  = ""
    for p in pages:
        del_form = (
            f"<form method='POST' action='/delete/{p['page_uuid']}' style='display:inline;' "
            f"onsubmit=\"return confirm('Delete this page?')\">"
            f"<button class='btn btn-sm' style='background:#3a0a0a;color:#f87171;border:1px solid #7f1d1d;'>Delete</button>"
            f"</form>"
        )
        rows += (
            f"<tr>"
            f"<td><a href='/edit/{p['page_uuid']}' style='color:var(--fg);font-weight:600;'>{p['page_title']}</a></td>"
            f"<td><span class='badge b-cat'>{p.get('category_ref','—')}</span></td>"
            f"<td style='color:var(--muted);'>{p.get('created_at','')}</td>"
            f"<td style='color:var(--muted);'>{p.get('author_ref','') or '—'}</td>"
            f"<td><a href='/edit/{p['page_uuid']}' class='btn btn-grey btn-sm'>Edit</a> {del_form}</td>"
            f"</tr>"
        )

    body = f"""
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;flex-wrap:wrap;gap:10px;">
      <div>
        <div style="font-size:1.4rem;font-weight:900;color:var(--acc);">{len(pages)}</div>
        <div style="font-size:.78rem;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;">Total Pages</div>
      </div>
      <a href="/new" class="btn btn-red">&#43; New Page</a>
    </div>
    <div class="card">
      <div class="card-hd"><h3>All Pages</h3></div>
      {"<div style='overflow-x:auto;'><table><thead><tr><th>Title</th><th>Category</th><th>Created</th><th>Author</th><th></th></tr></thead><tbody>" + rows + "</tbody></table></div>"
        if pages else "<p style='color:var(--muted);text-align:center;padding:30px 0;'>No pages yet. <a href='/new'>Create the first one.</a></p>"}
    </div>"""
    return _page("All Pages", "list", body)


# =============================================================================
# ROUTE — NEW PAGE  (template chooser)
# =============================================================================

@app.route('/new')
def _get_assets():
    if not os.path.exists(ASSETS_DIR):
        return []
    try:
        files = [f for f in os.listdir(ASSETS_DIR) if not f.startswith(".")]
        files.sort()
        return files
    except:
        return []

def r_new():
    cats = _get_categories()
    assets = _get_assets()

    tpl_cards = ""
    for key, tpl in TEMPLATES.items():
        tpl_cards += (
            f"<div class='tpl-card' id='tpl-{key}' onclick=\"selectTemplate('{key}')\">"
            f"<div class='tpl-icon'>{tpl['icon']}</div>"
            f"<div class='tpl-label'>{tpl['label']}</div>"
            f"<div class='tpl-desc'>{tpl['desc']}</div>"
            f"</div>"
        )

    # Build JSON map of template HTML for JS injection (non-dynamic templates only)
    _dynamic_tpls = {'image_gallery', 'multi_youtube', 'youtube_video', 'code', 'multi_file_code'}
    tpl_json = json.dumps({k: v['html'] for k, v in TEMPLATES.items() if k not in _dynamic_tpls})

    cat_opts = "".join(
        f"<option value='{c['category_name']}'>{c['category_name']}</option>"
        for c in cats
    )

    asset_opts = "".join(
        f"<option value='{a}'>{a}</option>"
        for a in assets
    )

    gallery_editor_html  = _gallery_editor_html()
    youtube_editor_html  = _youtube_editor_html()
    multivideo_editor_html = _multivideo_editor_html()
    code_editor_html     = _code_editor_html()
    multi_code_editor_html = _multi_code_editor_html()

    body = f"""
    <form method="POST" action="/save" id="pageForm" enctype="multipart/form-data">
      <input type="hidden" name="action"    value="create">
      <input type="hidden" name="page_uuid" value="{uuid.uuid4()}">
      <input type="hidden" name="template_key" id="template_key" value="blank">

      <!-- Template chooser -->
      <div class="card">
        <div class="card-hd"><h3>1. Choose a Template</h3></div>
        <div class="tpl-grid">{tpl_cards}</div>
      </div>

      <!-- Page meta -->
      <div class="card">
        <div class="card-hd"><h3>2. Page Details</h3></div>
        <div class="grid3">
          <div class="fg" style="grid-column:1/3;">
            <label>Page Title *</label>
            <input type="text" name="page_title" id="page_title" required placeholder="My Awesome Page">
          </div>
          <div class="fg">
            <label>Category</label>
            <select name="category">{cat_opts}</select>
          </div>
        </div>
        <div class="grid2">
          <div class="fg">
            <label>Author (optional)</label>
            <input type="text" name="author" placeholder="Leave blank to skip">
          </div>
          <div class="fg">
            <label>Featured Image</label>
            <select name="featured_img">
              <option value="">-- No image --</option>
              {asset_opts}
            </select>
          </div>
        </div>
      </div>

      <!-- Content editor — dynamic based on template type -->
      <div class="card">
        <div class="card-hd"><h3>3. Page Content</h3></div>

        <!-- Standard HTML editor (default / most templates) -->
        <div id="editor-standard">
          {_editor_html("html_body", "", include_modals=True)}
        </div>

        <!-- Gallery dynamic editor -->
        <div id="editor-gallery" style="display:none;">
          {gallery_editor_html}
        </div>

        <!-- YouTube dynamic editor -->
        <div id="editor-youtube" style="display:none;">
          {youtube_editor_html}
        </div>

        <!-- Multi-video dynamic editor -->
        <div id="editor-multivideo" style="display:none;">
          {multivideo_editor_html}
        </div>

        <!-- Code showcase dynamic editor -->
        <div id="editor-code" style="display:none;">
          {code_editor_html}
        </div>

        <!-- Multi-file Code dynamic editor -->
        <div id="editor-multi-code" style="display:none;">
          {multi_code_editor_html}
        </div>
      </div>

      <div class="btn-row">
        <button type="submit" class="btn btn-red">&#10003; Save &amp; Create Page</button>
        <a href="/" class="btn btn-grey">Cancel</a>
      </div>
    </form>

    <script>
    const TEMPLATES = {tpl_json};
    const DYNAMIC_EDITORS = {{
      'image_gallery':  'gallery',
      'youtube_video':  'youtube',
      'multi_youtube':  'multivideo',
      'code':           'code',
      'multi_file_code': 'multi-code'
    }};

    function selectTemplate(key) {{
      // Visual selection
      document.querySelectorAll('.tpl-card').forEach(c => c.classList.remove('selected'));
      document.getElementById('tpl-' + key).classList.add('selected');
      document.getElementById('template_key').value = key;

      // Switch editor panel
      var dynKey = DYNAMIC_EDITORS[key];
      ['standard','gallery','youtube','multivideo','code','multi-code'].forEach(function(n){{
        var el = document.getElementById('editor-'+n);
        if(el) el.style.display = 'none';
      }});
      if(dynKey){{
        var el = document.getElementById('editor-'+dynKey);
        if(el) el.style.display = 'block';
      }} else {{
        document.getElementById('editor-standard').style.display = 'block';
        var ta = document.getElementById('html_body');
        ta.value = TEMPLATES[key] || '';
      }}
    }}

    // Auto-select blank on load
    selectTemplate('blank');
    </script>"""

    return _page("New Page", "new", body)


# =============================================================================
# ROUTE — EDIT PAGE
# =============================================================================

@app.route('/edit/<page_uuid>')
def r_edit(page_uuid):
    pages = _get_pages()
    page  = next((p for p in pages if p['page_uuid'] == page_uuid), None)
    if not page:
        flash('Page not found.', 'error')
        return redirect('/')

    cats    = _get_categories()
    assets  = _get_assets()
    content = _get_page_body(page_uuid)
    safe_c  = _html_mod.escape(content)
    tpl_key = page.get('template_key', 'blank')

    cat_opts = "".join(
        f"<option value='{c['category_name']}' {'selected' if c['category_name'] == page.get('category_ref') else ''}>{c['category_name']}</option>"
        for c in cats
    )

    asset_opts = "".join(
        f"<option value='{a}' {'selected' if a == page.get('featured_img') else ''}>{a}</option>"
        for a in assets
    )

    # Build JSON map of template HTML for JS injection (non-dynamic templates only)
    _dynamic_tpls = {'image_gallery', 'multi_youtube', 'youtube_video', 'code', 'multi_file_code'}
    tpl_json = json.dumps({k: v['html'] for k, v in TEMPLATES.items() if k not in _dynamic_tpls})

    gallery_editor_html  = _gallery_editor_html()
    youtube_editor_html  = _youtube_editor_html()
    multivideo_editor_html = _multivideo_editor_html()
    code_editor_html     = _code_editor_html()
    multi_code_editor_html = _multi_code_editor_html()

    body = f"""
    <form method="POST" action="/save" id="pageForm">
      <input type="hidden" name="action"    value="update">
      <input type="hidden" name="page_uuid" value="{page_uuid}">
      <input type="hidden" name="template_key" id="template_key" value="{tpl_key}">

      <!-- Page meta -->
      <div class="card">
        <div class="card-hd"><h3>Page Details</h3></div>
        <div class="grid3">
          <div class="fg" style="grid-column:1/3;">
            <label>Page Title *</label>
            <input type="text" name="page_title" id="page_title" required value="{_html_mod.escape(page.get('page_title',''))}">
          </div>
          <div class="fg">
            <label>Category</label>
            <select name="category">{cat_opts}</select>
          </div>
        </div>
        <div class="grid2">
          <div class="fg">
            <label>Author</label>
            <input type="text" name="author" value="{_html_mod.escape(page.get('author_ref','') or '')}">
          </div>
          <div class="fg">
            <label>Featured Image</label>
            <select name="featured_img">
              <option value="">-- No image --</option>
              {asset_opts}
            </select>
          </div>
        </div>
        <p style="font-size:.75rem;color:var(--muted);margin-top:6px;">
          Created: {page.get('created_at','—')} &nbsp;|&nbsp; UUID: <code style="color:#666;">{page_uuid}</code>
        </p>
      </div>

      <!-- Content editor — dynamic based on template type -->
      <div class="card">
        <div class="card-hd"><h3>Page Content</h3></div>

        <!-- Standard HTML editor (default / most templates) -->
        <div id="editor-standard">
          {_editor_html("html_body", safe_c, include_modals=True)}
        </div>

        <!-- Gallery dynamic editor -->
        <div id="editor-gallery" style="display:none;">
          {gallery_editor_html}
        </div>

        <!-- YouTube dynamic editor -->
        <div id="editor-youtube" style="display:none;">
          {youtube_editor_html}
        </div>

        <!-- Multi-video dynamic editor -->
        <div id="editor-multivideo" style="display:none;">
          {multivideo_editor_html}
        </div>

        <!-- Code showcase dynamic editor -->
        <div id="editor-code" style="display:none;">
          {code_editor_html}
        </div>

        <!-- Multi-file Code dynamic editor -->
        <div id="editor-multi-code" style="display:none;">
          {multi_code_editor_html}
        </div>
      </div>

      <div class="btn-row">
        <button type="submit" class="btn btn-red">&#10003; Save Changes</button>
        <a href="/" class="btn btn-grey">Cancel</a>
        <form method="POST" action="/delete/{page_uuid}" style="display:inline;"
              onsubmit="return confirm('Delete this page permanently?')">
          <button class="btn btn-sm" style="background:#3a0a0a;color:#f87171;border:1px solid #7f1d1d;">&#128465; Delete Page</button>
        </form>
      </div>
    </form>

    <script>
    const TEMPLATES = {tpl_json};
    const DYNAMIC_EDITORS = {{
      'image_gallery':  'gallery',
      'youtube_video':  'youtube',
      'multi_youtube':  'multivideo',
      'code':           'code',
      'multi_file_code': 'multi-code'
    }};

    function selectTemplate(key) {{
      // Update hidden input
      document.getElementById('template_key').value = key;

      // Switch editor panel
      var dynKey = DYNAMIC_EDITORS[key];
      ['standard','gallery','youtube','multivideo','code','multi-code'].forEach(function(n){{
        var el = document.getElementById('editor-'+n);
        if(el) el.style.display = 'none';
      }});
      
      if(dynKey){{
        var el = document.getElementById('editor-'+dynKey);
        if(el) el.style.display = 'block';
      }} else {{
        document.getElementById('editor-standard').style.display = 'block';
      }}
    }}

    // Auto-select based on record on load
    window.addEventListener('load', function() {{
        selectTemplate('{tpl_key}');
    }});
    </script>"""

    return _page(
        f"Edit — {page.get('page_title','...')}",
        "list",
        body,
        extra_buttons=f"<a href='/' class='btn btn-grey btn-sm'>&#8592; All Pages</a>"
    )


# =============================================================================
# ROUTE — SAVE  (create or update)
# =============================================================================

@app.route('/save', methods=['POST'])
def r_save():
    if not os.path.exists(MANIFEST_PATH):
        flash('Master DB not found. Open the CMS first to initialise the database.', 'error')
        return redirect('/')

    action       = request.form.get('action', 'create')
    page_uuid    = request.form.get('page_uuid', '').strip()
    title        = request.form.get('page_title', '').strip()
    category     = request.form.get('category', 'Uncategorized')
    author       = request.form.get('author', '').strip()
    featured_img = request.form.get('featured_img', '').strip()
    tpl_type     = request.form.get('template_key', 'blank')

    # --- Determine final html_body based on editor mode ---
    if tpl_type == 'image_gallery':
        body_html = _build_gallery_html(request.form)
    elif tpl_type == 'youtube_video':
        body_html = _build_youtube_html(request.form)
    elif tpl_type == 'multi_youtube':
        body_html = _build_multivideo_html(request.form)
    elif tpl_type == 'code':
        body_html = _build_code_html(request.form)
    elif tpl_type == 'multi_file_code':
        body_html = _build_multi_code_html(request.form)
    else:
        body_html = request.form.get('html_body', '')

    if not title:
        flash('Page title is required.', 'error')
        return redirect(request.referrer or '/')

    if not page_uuid:
        page_uuid = str(uuid.uuid4())

    try:
        _write_page_record(
            page_uuid    = page_uuid,
            title        = title,
            category     = category,
            author       = author,
            body_html    = body_html,
            is_new       = (action == 'create'),
            featured_img = featured_img,
            template_key = tpl_type
        )
        verb = "created" if action == 'create' else "updated"
        flash(f'✅ Page "{title}" {verb} successfully.', 'success')
    except Exception as e:
        flash(f'Error saving page: {e}', 'error')
        return redirect(request.referrer or '/')

    return redirect(f'/edit/{page_uuid}')


# =============================================================================
# ROUTE — AI API
# =============================================================================

@app.route('/api/ai/profiles')
def api_ai_profiles():
    return jsonify({"profiles": _get_ai_profiles()})

@app.route('/api/ai/context')
def api_ai_context():
    files = _get_context_files()
    data = []
    for f in files:
        data.append({"filename": f, "enabled": AI_CONTEXT_STATE.get(f, False)})
    return jsonify({"files": data})

@app.route('/api/ai/context/toggle', methods=['POST'])
def api_ai_context_toggle():
    data = request.json or {}
    filename = data.get('filename')
    if filename:
        AI_CONTEXT_STATE[filename] = not AI_CONTEXT_STATE.get(filename, False)
    return jsonify({"ok": True, "filename": filename, "enabled": AI_CONTEXT_STATE.get(filename)})

@app.route('/api/ai/generate_plan', methods=['POST'])
def api_ai_generate_plan():
    data = request.json or {}
    prompt = data.get('prompt', '').strip()
    model = data.get('model', AI_MODELS[0])
    profile_f = data.get('profile')
    
    if not prompt: return jsonify({"ok": False, "error": "Prompt required"}), 400
    
    job_id = str(uuid.uuid4())
    AI_JOB_QUEUES[job_id] = Queue()
    
    def _run():
        try:
            builder = ExtLib.CMSAIBuilder.setup_gemini(model=model)
            if not builder:
                _ai_push(job_id, {"type": "error", "message": "Failed to initialize Gemini Builder."})
                return

            sys_inst = None
            if profile_f:
                profs = _get_ai_profiles()
                p = next((x for x in profs if x['filename'] == profile_f), None)
                if p: sys_inst = p['system']

            plan = builder.generate_plan(prompt, profile_system=sys_inst, emit=lambda ev: _ai_push(job_id, ev))
            if plan:
                _ai_push(job_id, {"type": "plan_ready", "plan": plan})
            else:
                _ai_push(job_id, {"type": "error", "message": "Failed to generate plan."})
        except Exception as e:
            _ai_push(job_id, {"type": "error", "message": str(e)})
        finally:
            _ai_push(job_id, {"type": "complete"})
            
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "job_id": job_id})

@app.route('/api/ai/generate_pages', methods=['POST'])
def api_ai_generate_pages():
    data = request.json or {}
    plan = data.get('plan', [])
    model = data.get('model', AI_MODELS[0])
    profile_f = data.get('profile')
    category = data.get('category', 'AI Generated')
    author = data.get('author', 'Gemini')
    
    if not plan: return jsonify({"ok": False, "error": "Plan required"}), 400
    
    job_id = str(uuid.uuid4())
    AI_JOB_QUEUES[job_id] = Queue()
    
    def _run():
        try:
            builder = ExtLib.CMSAIBuilder.setup_gemini(model=model)
            if not builder:
                _ai_push(job_id, {"type": "error", "message": "Failed to initialize Gemini Builder."})
                return

            ctx_parts = _load_context_parts()
            sys_inst = None
            if profile_f:
                profs = _get_ai_profiles()
                p = next((x for x in profs if x['filename'] == profile_f), None)
                if p: sys_inst = p['system']

            def writer_cb(step, content):
                page_uuid = str(uuid.uuid4())
                _write_page_record(
                    page_uuid=page_uuid,
                    title=step['title'],
                    category=category,
                    author=author,
                    body_html=content,
                    is_new=True
                )

            builder.build_pages(
                plan, category, author, 
                profile_system=sys_inst, 
                context_parts=ctx_parts, 
                emit=lambda ev: _ai_push(job_id, ev),
                page_writer_callback=writer_cb
            )
        except Exception as e:
            _ai_push(job_id, {"type": "error", "message": str(e)})
        finally:
            _ai_push(job_id, {"type": "complete"})
            
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "job_id": job_id})

@app.route('/api/ai/stream/<job_id>')
def api_ai_stream(job_id):
    def generate():
        q = AI_JOB_QUEUES.get(job_id)
        if not q: return
        while True:
            try:
                ev = q.get(timeout=30)
                yield f"data: {json.dumps(ev)}\n\n"
                if ev.get('type') in ['complete', 'error']:
                    break
            except Empty:
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        AI_JOB_QUEUES.pop(job_id, None)
    return Response(generate(), mimetype='text/event-stream', headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# =============================================================================
# ROUTE — DELETE
# =============================================================================

@app.route('/delete/<page_uuid>', methods=['POST'])
def r_delete(page_uuid):
    if not os.path.exists(MANIFEST_PATH):
        flash('Master DB not found.', 'error')
        return redirect('/')

    # Read title before deleting for flash message
    db.mount()
    pages = db.get_records("PageRecord")
    page  = next((p for p in pages if p['page_uuid'] == page_uuid), None)
    title = page['page_title'] if page else page_uuid
    db.delete_record("PageRecord", "page_uuid", page_uuid)
    

    # Remove content file
    pfile = os.path.join(PAGES_DB_DIR, f"{page_uuid}.json")
    if os.path.exists(pfile):
        os.remove(pfile)

    flash(f'Page "{title}" deleted.', 'success')
    return redirect('/')


# =============================================================================
# ROUTE — CODE FILE UPLOAD (AJAX)
# Returns escaped file content as JSON for the editor to insert
# =============================================================================

@app.route('/upload_code', methods=['POST'])
def r_upload_code():
    f = request.files.get('code_file')
    if not f or not f.filename:
        return jsonify({'ok': False, 'error': 'No file received'})
    fname = secure_filename(f.filename)
    ext   = os.path.splitext(fname)[1].lower()
    # Accept text-like files
    allowed = {'.py','.js','.ts','.html','.htm','.css','.json','.xml','.sh',
               '.bash','.txt','.md','.csv','.sql','.yaml','.yml','.ini',
               '.cfg','.toml','.c','.cpp','.java','.rb','.go','.rs'}
    if ext not in allowed:
        return jsonify({'ok': False, 'error': f'File type {ext} not supported. Use: {", ".join(sorted(allowed))}'})
    try:
        raw = f.read().decode('utf-8', errors='replace')
        # Escape for HTML embedding
        escaped = _html_mod.escape(raw)
        snippet = (
            f'\n<div class="bej-code-block">\n'
            f'<pre><code>\n{escaped}\n</code></pre>\n'
            f'</div>\n'
        )
        return jsonify({'ok': True, 'snippet': snippet, 'filename': fname})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


# =============================================================================
# ROUTE — MARKDOWN FILE UPLOAD (AJAX)
# Returns raw markdown content for the editor to store
# =============================================================================

@app.route('/upload_markdown', methods=['POST'])
def r_upload_markdown():
    f = request.files.get('md_file')
    if not f or not f.filename:
        return jsonify({'ok': False, 'error': 'No file received'})
    fname = secure_filename(f.filename)
    ext   = os.path.splitext(fname)[1].lower()
    if ext not in {'.md', '.txt', '.markdown'}:
        return jsonify({'ok': False, 'error': 'Only .md / .markdown / .txt files accepted'})
    try:
        raw = f.read().decode('utf-8', errors='replace')
        return jsonify({'ok': True, 'content': raw, 'filename': fname})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


# =============================================================================
# ROUTE — LIST ASSETS (AJAX)
# Returns list of image files in the assets directory
# =============================================================================

@app.route('/list_assets')
def r_list_assets():
    img_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.avif'}
    if not os.path.exists(ASSETS_DIR):
        return jsonify({'ok': True, 'files': []})
    try:
        files = [
            f for f in os.listdir(ASSETS_DIR)
            if os.path.splitext(f)[1].lower() in img_exts
        ]
        files.sort()
        return jsonify({'ok': True, 'files': files})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


# =============================================================================
# DYNAMIC EDITOR HTML BUILDERS
# Convert form data from dynamic editors into publishable HTML
# =============================================================================

def _build_gallery_html(form):
    """Build gallery HTML from gallery_file_* and gallery_caption_* form fields."""
    intro = form.get('gallery_intro', '').strip()
    items_html = ""
    for i in range(1, 21): # Support up to 20 images
        fname   = form.get(f'gallery_file_{i}', '').strip()
        caption = form.get(f'gallery_caption_{i}', '').strip()
        if not fname:
            continue
        cap_html = f'<figcaption style="font-size:.85rem;color:var(--accent-color);font-weight:700;padding:10px 0;text-align:center;background:rgba(222,38,38,0.05);">{_html_mod.escape(caption)}</figcaption>' if caption else ''
        items_html += f"""
  <figure class="bej-gallery-item" style="margin:0;cursor:zoom-in;border:1px solid var(--border-color);border-radius:4px;overflow:hidden;transition:transform 0.3s ease;background:var(--bg-card);">
    <img src="../../../assets/{_html_mod.escape(fname)}"
         alt="{_html_mod.escape(caption or fname)}"
         style="width:100%;height:220px;object-fit:cover;display:block;">
    {cap_html}
  </figure>"""

    if not items_html:
        return '<p>No images selected.</p>'

    intro_html = f'<div style="margin-bottom:30px;font-size:1.1rem;line-height:1.6;border-left:4px solid var(--accent-color);padding-left:20px;">{_html_mod.escape(intro)}</div>\n\n' if intro else ''
    return f"""{intro_html}
<div class="section-divider" style="margin-bottom:30px;"><h2 class="section-label">Gallery</h2><div class="label-line"></div></div>
<div class="bej-gallery" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:30px;margin:30px 0;">{items_html}
</div>
<p style="font-size:.8rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:1px;text-align:center;">&mdash; Click any image to expand &mdash;</p>
<style>.bej-gallery-item:hover {{ transform: translateY(-5px); border-color: var(--accent-color); box-shadow: var(--shadow-hover); }}</style>"""


def _build_youtube_html(form):
    """Build single YouTube embed HTML."""
    url     = form.get('yt_url', '').strip()
    caption = form.get('yt_caption', '').strip()
    
    if not url:
        return '<p>No video selected.</p>'
        
    # Extract ID
    vid_id = url
    if 'v=' in url:
        vid_id = url.split('v=')[1].split('&')[0]
    elif 'youtu.be/' in url:
        vid_id = url.split('youtu.be/')[1].split('?')[0]
    elif '/embed/' in url:
        vid_id = url.split('/embed/')[1].split('?')[0]

    cap_html = f'<p style="font-size:.9rem;color:var(--text-muted);margin-top:15px;text-align:center;font-style:italic;">{_html_mod.escape(caption)}</p>' if caption else ''
    
    return f"""
<div class="bej-video-wrap" style="max-width:800px;margin:40px auto;">
  <div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;border-radius:8px;border:1px solid var(--border-color);background:#000;">
    <iframe src="https://www.youtube.com/embed/{vid_id}" 
            frameborder="0" 
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
            allowfullscreen
            style="position:absolute;top:0;left:0;width:100%;height:100%;"></iframe>
  </div>
  {cap_html}
</div>
"""


def _build_multivideo_html(form):
    """Build multi-video HTML from video_url_* and video_label_* form fields."""
    intro = form.get('video_intro', '').strip()
    videos_html = ""
    for i in range(1, 21):
        raw_url = form.get(f'video_url_{i}', '').strip()
        label   = form.get(f'video_label_{i}', '').strip() or f'Video {i}'
        if not raw_url:
            continue
        # Extract video ID
        vid = re.search(r'(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{11})', raw_url)
        vid_id = vid.group(1) if vid else (raw_url if re.match(r'^[A-Za-z0-9_-]{11}$', raw_url) else None)
        if not vid_id:
            continue
        videos_html += f"""
  <div class="bej-video-item">
    <div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;border-radius:4px;">
      <iframe src="https://www.youtube.com/embed/{vid_id}"
              title="{_html_mod.escape(label)}"
              frameborder="0"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowfullscreen
              style="position:absolute;top:0;left:0;width:100%;height:100%;"></iframe>
    </div>
    <h3 style="margin-top:14px;font-size:1.05rem;">{_html_mod.escape(label)}</h3>
  </div>"""

    if not videos_html:
        return '<p>No valid YouTube URLs provided.</p>'

    intro_html = f'<p>{_html_mod.escape(intro)}</p>\n\n' if intro else ''
    return f"""{intro_html}<div class="bej-video-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:32px;margin:30px 0;">{videos_html}
</div>"""


def _build_code_html(form):
    """Build code showcase HTML from source_code_raw and markdown_raw form fields."""
    source   = form.get('source_code_raw', '').strip()
    md_raw   = form.get('markdown_raw', '').strip()
    desc     = form.get('code_desc', '').strip()
    filename = form.get('code_filename', '').strip() or 'source'
    md_fname = form.get('md_filename', '').strip() or 'README.md'

    desc_html = f'<p>{_html_mod.escape(desc)}</p>\n\n' if desc else ''
    src_escaped = _html_mod.escape(source) if source else '# Paste your source code here'

    # Build tab structure if markdown is present
    if md_raw:
        md_escaped = _html_mod.escape(md_raw)
        return f"""{desc_html}<div class="bej-code-tabs" style="margin:24px 0;">
  <div style="display:flex;gap:0;border-bottom:2px solid #DE2626;margin-bottom:0;">
    <button onclick="bejTab(this,'bej-src')" class="bej-tab-btn" style="padding:8px 18px;background:#DE2626;color:#fff;border:none;font-weight:700;cursor:pointer;font-size:.85rem;">{_html_mod.escape(filename)}</button>
    <button onclick="bejTab(this,'bej-md')" class="bej-tab-btn" style="padding:8px 18px;background:#1e1e1e;color:#aaa;border:none;font-weight:700;cursor:pointer;font-size:.85rem;">{_html_mod.escape(md_fname)}</button>
  </div>
  <div id="bej-src" class="bej-tab-pane">
    <div class="bej-code-block"><pre><code>{src_escaped}</code></pre></div>
  </div>
  <div id="bej-md" class="bej-tab-pane" style="display:none;">
    <pre style="background:var(--code-bg);color:var(--code-text);padding:20px;overflow-x:auto;font-size:.88rem;white-space:pre-wrap;">{md_escaped}</pre>
  </div>
</div>
<script>
function bejTab(btn,paneid){{
  document.querySelectorAll('.bej-tab-btn').forEach(function(b){{b.style.background='#1e1e1e';b.style.color='#aaa';}});
  document.querySelectorAll('.bej-tab-pane').forEach(function(p){{p.style.display='none';}});
  btn.style.background='#DE2626';btn.style.color='#fff';
  document.getElementById(paneid).style.display='block';
}}
</script>"""
    else:
        return f"""{desc_html}<div class="bej-code-block"><pre><code>{src_escaped}</code></pre></div>"""


# =============================================================================
# EDITOR HTML COMPONENT
# Renders the toolbar + textarea + modals.  Reused by both /new and /edit.
# =============================================================================

def _build_multi_code_html(form):
    """Build multi-file code showcase HTML with tabs and optional ZIP download."""
    intro = form.get('code_intro', '').strip()
    include_zip = form.get('include_zip') == 'true'
    
    files = {}
    # Extract files from form (cf_name_N, cf_content_N)
    # We don't know the exact count but we can iterate through the form keys
    for key in form.keys():
        if key.startswith('cf_name_'):
            idx = key.split('_')[-1]
            fname = form.get(f'cf_name_{idx}', '').strip()
            content = form.get(f'cf_content_{idx}', '').strip()
            if fname:
                files[fname] = content

    if not files:
        return '<p>No code files provided.</p>'

    # 1. Generate ZIP if requested
    zip_link_html = ""
    if include_zip:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name = f"project_{timestamp}.zip"
        zip_path = os.path.join(ASSETS_DIR, zip_name)
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for fname, content in files.items():
                    zf.writestr(fname, content)
            zip_link_html = f"""
<div style="margin:20px 0;padding:15px;background:#f8f8f8;border:1px solid #e5e5e5;border-radius:6px;display:flex;align-items:center;justify-content:space-between;">
  <div>
    <strong style="display:block;font-size:1.1rem;">Project Source Bundle</strong>
    <span style="font-size:.85rem;color:#666;">Full project files in a single archive.</span>
  </div>
  <a href="../../../assets/{zip_name}" download class="btn" style="background:#24292e;color:#fff;padding:10px 20px;border-radius:4px;font-weight:700;text-decoration:none;">⬇ Download ZIP</a>
</div>"""
        except Exception as e:
            zip_link_html = f"<p style='color:#DE2626;'>Error generating ZIP: {e}</p>"

    # 2. Build Tabbed Interface
    tabs_html = ""
    panes_html = ""
    for i, (fname, content) in enumerate(files.items()):
        pane_id = f"mc-pane-{i}"
        active_btn = "background:#DE2626;color:#fff;" if i == 0 else "background:#1e1e1e;color:#aaa;"
        active_display = "block" if i == 0 else "none"
        
        tabs_html += f'<button type="button" onclick="mcTab(this,\'{pane_id}\')" class="mc-tab-btn" style="padding:8px 18px;{active_btn}border:none;font-weight:700;cursor:pointer;font-size:.85rem;white-space:nowrap;">{_html_mod.escape(fname)}</button>'
        panes_html += f'<div id="{pane_id}" class="mc-tab-pane" style="display:{active_display};"><div class="bej-code-block"><pre><code>{_html_mod.escape(content)}</code></pre></div></div>'

    intro_html = f'<p>{_html_mod.escape(intro)}</p>\n\n' if intro else ''
    
    return f"""{intro_html}
<div class="mc-code-viewer" style="margin:24px 0;">
  <div style="display:flex;gap:0;border-bottom:2px solid #DE2626;overflow-x:auto;scrollbar-width:thin;">
    {tabs_html}
  </div>
  <div style="border:1px solid #2a2a2a;border-top:none;">
    {panes_html}
  </div>
</div>
{zip_link_html}
<script>
function mcTab(btn,paneid){{
  var viewer = btn.closest('.mc-code-viewer');
  viewer.querySelectorAll('.mc-tab-btn').forEach(function(b){{b.style.background='#1e1e1e';b.style.color='#aaa';}});
  viewer.querySelectorAll('.mc-tab-pane').forEach(function(p){{p.style.display='none';}});
  btn.style.background='#DE2626';btn.style.color='#fff';
  document.getElementById(paneid).style.display='block';
}}
</script>"""


def _editor_html(field_name, current_value, include_modals=True):
    """Return the full editor widget HTML string."""

    toolbar = """
    <div class="editor-toolbar">
      <button type="button" class="tb-btn" onclick="ins('<h2>','</h2>')">H2</button>
      <button type="button" class="tb-btn" onclick="ins('<h3>','</h3>')">H3</button>
      <button type="button" class="tb-btn" onclick="ins('<p>','</p>')">¶ P</button>
      <div class="tb-sep"></div>
      <button type="button" class="tb-btn" onclick="ins('<strong>','</strong>')"><b>B</b></button>
      <button type="button" class="tb-btn" onclick="ins('<em>','</em>')"><i>I</i></button>
      <div class="tb-sep"></div>
      <button type="button" class="tb-btn" onclick="ins('<code>','</code>')">&#96;code&#96;</button>
      <button type="button" class="tb-btn" onclick="insBlock('<div class=\\'bej-code-block\\'>\\n<pre><code>','</code></pre>\\n</div>')">pre</button>
      <div class="tb-sep"></div>
      <button type="button" class="tb-btn" onclick="insLine('<hr style=\\'border:0;border-top:1px solid #eee;margin:30px 0;\\'>')">—HR</button>
      <button type="button" class="tb-btn" onclick="insLink()">&#128279; Link</button>
      <div class="tb-sep"></div>
      <button type="button" class="tb-btn btn-yt"  onclick="openModal('ytModal')">&#9654; YouTube</button>
      <button type="button" class="tb-btn btn-code" onclick="openModal('codeModal')">&#128190; Code File</button>
    </div>"""

    textarea = f"""
    <textarea id="{field_name}" name="{field_name}"
              class="editor-area"
              spellcheck="false">{current_value}</textarea>"""

    modals = ""
    if include_modals:
        modals = """
<!-- ── YOUTUBE MODAL ── -->
<div class="modal-bg" id="ytModal">
  <div class="modal">
    <h3>&#9654; Insert YouTube Video</h3>
    <div class="fg">
      <label>YouTube URL or Video ID</label>
      <input type="url" id="ytUrl" placeholder="https://www.youtube.com/watch?v=dQw4w9WgXcQ"
             style="font-size:.88rem;">
    </div>
    <div class="fg">
      <label>Caption / Title (optional)</label>
      <input type="text" id="ytCaption" placeholder="Video title or description">
    </div>
    <div class="btn-row">
      <button type="button" class="btn btn-red" onclick="insertYouTube()">Insert</button>
      <button type="button" class="btn btn-grey" onclick="closeModal('ytModal')">Cancel</button>
    </div>
  </div>
</div>

<!-- ── CODE FILE MODAL ── -->
<div class="modal-bg" id="codeModal">
  <div class="modal">
    <h3>&#128190; Attach Code File</h3>
    <p style="color:var(--muted);font-size:.82rem;margin-bottom:14px;">
      Select a .py / .js / .txt / .html or any text-based source file.
      Its contents will be inserted as a syntax-highlighted block.
    </p>
    <div class="fg">
      <label>Select File</label>
      <input type="file" id="codeFileInput"
             accept=".py,.js,.ts,.html,.htm,.css,.json,.xml,.sh,.bash,.txt,.md,.csv,.sql,.yaml,.yml,.ini,.cfg,.toml,.c,.cpp,.java,.rb,.go,.rs"
             style="background:#111;border:1px solid var(--border);border-radius:6px;padding:10px;color:#ccc;width:100%;">
    </div>
    <div id="codeFileStatus" style="font-size:.8rem;color:var(--muted);margin-bottom:12px;"></div>
    <div class="btn-row">
      <button type="button" class="btn btn-red" id="codeInsertBtn" onclick="insertCodeFile()">Insert</button>
      <button type="button" class="btn btn-grey" onclick="closeModal('codeModal')">Cancel</button>
    </div>
  </div>
</div>

<script>
// ── Modal helpers ──
function openModal(id){document.getElementById(id).classList.add('open');}
function closeModal(id){document.getElementById(id).classList.remove('open');}
document.querySelectorAll('.modal-bg').forEach(function(m){
  m.addEventListener('click',function(e){if(e.target===m)m.classList.remove('open');});
});

// ── Textarea insertion helpers ──
function getTA(){return document.getElementById('html_body');}

function ins(open, close){
  const ta=getTA(), s=ta.selectionStart, e=ta.selectionEnd;
  const sel=ta.value.substring(s,e);
  const rep=open+(sel||'text here')+close;
  ta.setRangeText(rep, s, e, 'end');
  ta.focus();
}

function insBlock(open, close){
  const ta=getTA(), s=ta.selectionStart, e=ta.selectionEnd;
  const sel=ta.value.substring(s,e);
  const rep='\\n'+open+'\\n'+(sel||'// code here')+'\\n'+close+'\\n';
  ta.setRangeText(rep, s, e, 'end');
  ta.focus();
}

function insLine(tag){
  const ta=getTA(), s=ta.selectionStart;
  const rep='\\n'+tag+'\\n';
  ta.setRangeText(rep, s, s, 'end');
  ta.focus();
}

function insLink(){
  const url = prompt('URL:', 'https://');
  if(!url) return;
  const label = prompt('Link text:', 'Click here') || url;
  ins('<a href="'+url+'">', '</a>');
  // Replace the placeholder
  const ta=getTA();
  ta.value = ta.value.replace('<a href="'+url+'">text here</a>',
                              '<a href="'+url+'">'+label+'</a>');
  ta.focus();
}

// ── YouTube insertion ──
function ytIdFromUrl(raw){
  raw = raw.trim();
  // Already an ID (11 chars, no slash)
  if(/^[A-Za-z0-9_-]{11}$/.test(raw)) return raw;
  const m = raw.match(/(?:v=|youtu\\.be\\/|embed\\/)([A-Za-z0-9_-]{11})/);
  return m ? m[1] : null;
}

function insertYouTube(){
  const raw     = document.getElementById('ytUrl').value.trim();
  const caption = document.getElementById('ytCaption').value.trim();
  const vid     = ytIdFromUrl(raw);
  if(!vid){
    alert('Could not extract a YouTube video ID from that URL. Try pasting the full watch URL or just the 11-character ID.');
    return;
  }
  const captionHtml = caption
    ? '\\n<p style="font-size:.9rem;color:#666;margin-top:10px;text-align:center;">'+caption+'</p>'
    : '';
  const snippet = `
<div class="bej-video-wrap" style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;max-width:100%;margin:30px 0;">
  <iframe
    src="https://www.youtube.com/embed/${vid}"
    title="${caption || 'YouTube Video'}"
    frameborder="0"
    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
    allowfullscreen
    style="position:absolute;top:0;left:0;width:100%;height:100%;">
  </iframe>
</div>${captionHtml}
`;
  const ta=getTA(), pos=ta.selectionStart;
  ta.setRangeText(snippet, pos, pos, 'end');
  ta.focus();
  closeModal('ytModal');
  document.getElementById('ytUrl').value = '';
  document.getElementById('ytCaption').value = '';
}

// ── Code file insertion ──
function insertCodeFile(){
  const input = document.getElementById('codeFileInput');
  const status = document.getElementById('codeFileStatus');
  if(!input.files.length){
    status.textContent = 'Please select a file first.';
    status.style.color = '#f87171';
    return;
  }
  const file = input.files[0];
  status.textContent = 'Uploading ' + file.name + '…';
  status.style.color = 'var(--muted)';

  const fd = new FormData();
  fd.append('code_file', file);

  fetch('/upload_code', {method:'POST', body: fd})
    .then(r => r.json())
    .then(data => {
      if(data.ok){
        const ta = getTA(), pos = ta.selectionStart;
        ta.setRangeText(data.snippet, pos, pos, 'end');
        ta.focus();
        status.textContent = '✓ ' + data.filename + ' inserted.';
        status.style.color = '#4ade80';
        setTimeout(() => closeModal('codeModal'), 800);
        input.value = '';
      } else {
        status.textContent = '✗ ' + data.error;
        status.style.color = '#f87171';
      }
    })
    .catch(err => {
      status.textContent = '✗ Upload failed: ' + err;
      status.style.color = '#f87171';
    });
}
</script>"""

    return f"""
    <div class="editor-wrap">
      {toolbar}
      {textarea}
    </div>
    {modals}
    <p style="font-size:.75rem;color:var(--muted);margin-top:8px;">
      Write raw HTML. Use the toolbar buttons to insert elements at the cursor position.
    </p>"""


# =============================================================================
# ERROR HANDLER
# =============================================================================

@app.errorhandler(404)
def not_found(e):
    body = """<div style="text-align:center;padding:60px 0;">
    <div style="font-size:4rem;color:var(--acc);font-weight:900;">404</div>
    <p style="color:var(--muted);margin:12px 0 20px;">Page not found.</p>
    <a href="/" class="btn btn-grey">&#8592; Back</a>
    </div>"""
    return _page("404", "", body), 404


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    print("""
============================================================
  BEJSON Page Editor  v14.0
------------------------------------------------------------
  Dedicated page creation & editing tool.

  Templates (10):
    Blank, Article, YouTube Embed,
    Code Showcase, Tutorial / How-To,
    Image Gallery, PDF Viewer, Review,
    Multi-Video Page, GitHub Project

  Dynamic Editors:
    Gallery     → asset browser, up to 10 images
    Multi-Video → add/remove YouTube URL rows
    Code        → tabbed source + Markdown editor

  Features:
    - HTML editor with toolbar
    - YouTube URL → responsive iframe insertion
    - Code file attach (.py / .js / .txt / etc.)
      uploaded → inserted as bej-code-block
    - Markdown file attach (Code type)
    - Category + author assignment
    - Full create / edit / delete

  Shares Data/ directory with:
    Flask_CMS.py        (port 5001)
    Flask_CMS_Publisher (port 5001 publisher)

  http://localhost:5003
============================================================""")
    app.run(host='0.0.0.0', port=5003, debug=False)
