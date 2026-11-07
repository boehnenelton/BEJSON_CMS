"""
Library:         BEJSON_CMS_Content
Family:          BEJSON_CMS
Description:     Content Cube: Page/Link CRUD, Category management, Author profiles, Standalone Apps, HTML import pipeline. Uses CMSCore (lib_bejson_CMS_cms_core), the same data layer as the rest of the Flask app — NOT lib_bejson_CMS_cms_mfdb (that manager is CLI-only, used by cms-manage.py, and is a different schema/data layer).
Version:         18.30
Library_Version: 61
Date:            2026-11-03
RELATIONAL_ID:   e83a1d92-4b67-4c18-9f05-7a2b5e8d1c43
"""

VERSION = 1830

import os
import gc
import json
import uuid
import re
import time
import shutil
import logging
import zipfile
import html as _html_escape
from datetime import datetime
from flask import Blueprint, request, redirect, flash, send_file, jsonify
from werkzeug.utils import secure_filename

from BEJSON_CMS_Shared import (
    db, R, get_breadcrumbs, get_image_assets, require_auth,
    PAGES_DB_DIR, ASSETS_DIR, APPS_STORAGE, DEFAULT_FEATURED_IMAGE, SCRIPT_PATH,
    UPLOAD_TMP,
)
from BEJSON_CMS_FileBrowser import resolve_picks, PickError
from lib_bejson_Core_bejson_path_guard import safe_extract_zip
from lib_bejson_Core_bejson_core import bejson_core_get_field_map, bejson_core_atomic_write
from lib_bejson_CMS_md2html import convert_markdown_to_cms_article
import lib_bejson_CMS_bks_blog_jobs as BKSJobs
import lib_bejson_AI_ai_writing as AIWriting

try:
    from bs4 import BeautifulSoup
    _BS4_OK = True
except ImportError:
    _BS4_OK = False

content_cube = Blueprint('content', __name__)

@content_cube.route('/content')
def content_hub():
    html = '''
    <div class="page-header"><h1>Content Management</h1><p>Manage all your website content</p></div>
    <div class="grid grid-3">
        <a href="/pages" class="card" style="text-decoration:none;color:inherit;"><div style="text-align:center;padding:20px;"><div style="font-size:3rem;margin-bottom:15px;">&#128196;</div><h3>Pages</h3><p style="color:var(--text-secondary);">Create and edit pages</p></div></a>
        <a href="/jobs" class="card" style="text-decoration:none;color:inherit;"><div style="text-align:center;padding:20px;"><div style="font-size:3rem;margin-bottom:15px;">&#9997;&#65039;</div><h3>AI Writer</h3><p style="color:var(--text-secondary);">4-part structured writing plans, Context Bubble engine, merge &amp; overwrite</p></div></a>
        <a href="/links" class="card" style="text-decoration:none;color:inherit;"><div style="text-align:center;padding:20px;"><div style="font-size:3rem;margin-bottom:15px;">&#128279;</div><h3>External Links</h3><p style="color:var(--text-secondary);">Manage external link references</p></div></a>
        <a href="/categories" class="card" style="text-decoration:none;color:inherit;"><div style="text-align:center;padding:20px;"><div style="font-size:3rem;margin-bottom:15px;">&#128193;</div><h3>Categories</h3><p style="color:var(--text-secondary);">Organize content by category</p></div></a>
        <a href="/import" class="card" style="text-decoration:none;color:inherit;"><div style="text-align:center;padding:20px;"><div style="font-size:3rem;margin-bottom:15px;">&#128229;</div><h3>HTML / MD Import</h3><p style="color:var(--text-secondary);">Import HTML or Markdown articles</p></div></a>
    </div>'''
    return R(html, breadcrumbs=get_breadcrumbs(request.path), active_section='content')


@content_cube.route('/pages')
def pages_list():
    db.mount()
    items = db.get_records("PageRecord")
    categories = db.get_records("Category")
    
    pages = [p for p in items if p.get('page_type') != 'external_link']
    links = [p for p in items if p.get('page_type') == 'external_link']

    html = '''
    <div class="page-header"><h1>Pages</h1><p>Manage your website pages and articles</p></div>
    <div class="tabs">
        <button class="tab active" data-tab="tab-pages">Pages ({{ pages|length }})</button>
        <button class="tab" data-tab="tab-links">External Links ({{ links|length }})</button>
        <button class="tab" data-tab="tab-categories">Categories ({{ categories|length }})</button>
    </div>
    <div id="tab-pages" class="tab-content active">
        <div class="toolbar"><a href="/pages/new" class="btn btn-primary">+ New Page</a>
        <div class="search-box"><input type="text" class="form-control" placeholder="Search pages..." onkeyup="filterTable(this, \'pages-table\')"></div></div>
        <div class="card">{% if pages %}<div class="table-container"><table id="pages-table"><thead><tr><th>Edit</th><th>Title</th><th>Category</th><th>Author</th><th>Type</th><th>Date</th><th>Actions</th></tr></thead><tbody>
        {% for p in pages %}<tr><td><a href="/edit/{{ p.page_uuid }}" class="btn btn-primary btn-sm">Edit</a></td><td>{{ p.page_title }}</td><td>{{ p.page_cat_name or \'Uncategorized\' }}</td><td>{{ p.page_author_name or \'—\' }}</td><td><span class="badge badge-page">{{ p.page_type or \'page\' }}</span></td><td>{{ p.page_created_at or \'N/A\' }}</td>
        <td><form method="post" action="/pages/duplicate/{{ p.page_uuid }}" style="display:inline;"><button type="submit" class="btn btn-secondary btn-sm">Duplicate</button></form> <form method="post" action="/pages/delete/{{ p.page_uuid }}" style="display:inline;" onsubmit="return confirm(\'Delete this page?\')"><button type="submit" class="btn btn-danger btn-sm">Delete</button></form></td></tr>{% endfor %}
        </tbody></table></div>{% else %}<div class="empty-state"><h3>No pages yet</h3><a href="/pages/new" class="btn btn-primary">Create your first page</a></div>{% endif %}</div>
    </div>
    <div id="tab-links" class="tab-content">
        <div class="toolbar"><a href="/links/new" class="btn btn-primary">+ Add External Link</a></div>
        <div class="card">{% if links %}<div class="table-container"><table><thead><tr><th>Label</th><th>URL</th><th>Category</th><th>Actions</th></tr></thead><tbody>
        {% for l in links %}<tr><td>&#128279; {{ l.page_title }}</td><td><a href="{{ l.page_external_url }}" target="_blank" style="color:var(--accent);">{{ l.page_external_url[:60] if l.page_external_url else \'\' }}</a></td><td>{{ l.page_cat_name or \'Uncategorized\' }}</td>
        <td><form method="post" action="/pages/delete/{{ l.page_uuid }}" style="display:inline;" onsubmit="return confirm(\'Delete this page?\')"><button type="submit" class="btn btn-danger btn-sm">Delete</button></form></td></tr>{% endfor %}
        </tbody></table></div>{% else %}<div class="empty-state"><h3>No external links</h3></div>{% endif %}</div>
    </div>
    <div id="tab-categories" class="tab-content">
        <div class="toolbar">
            <form action="/categories/add" method="POST" style="display:flex;gap:10px;flex:1;">
                <input type="text" name="cat_name" class="form-control" placeholder="New category name..." required>
                <button type="submit" class="btn btn-primary">Add Category</button>
            </form>
        </div>
        <div class="card"><div class="table-container"><table><thead><tr><th>Category Name</th><th>Slug</th><th>Actions</th></tr></thead><tbody>
        {% for c in categories %}<tr><td>{{ c.cat_name }}</td><td><code style="background:var(--bg-secondary);padding:2px 8px;border-radius:4px;">{{ c.cat_slug }}</code></td>
        <td>{% if c.cat_name != \'Uncategorized\' %}<form method="post" action="/categories/delete/{{ c.cat_name }}" style="display:inline;" onsubmit="return confirm(\'Delete category?\')"><button type="submit" class="btn btn-danger btn-sm">Delete</button></form>{% endif %}</td></tr>{% endfor %}
        </tbody></table></div></div>
    </div>'''
    return R(html, pages=pages, links=links, categories=categories,
             breadcrumbs=get_breadcrumbs(request.path), active_section='content')


@content_cube.route('/pages/new', methods=['GET', 'POST'])
def page_new():
    db.mount()
    categories = db.get_records("Category")
    authors = db.get_records("AuthorProfile")

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        category = request.form.get('category', '').strip()
        author = request.form.get('author', '')
        if not title:
            return "Title required", 400
        if not category:
            return "Category required", 400
        new_uuid = str(uuid.uuid4())
        slug = re.sub(r'[^a-z0-9]', '-', title.lower()).strip('-')
        featured_diagram = request.form.get('page_featured_diagram', '').strip()
        db.mount()
        db.add_record("PageRecord", {"page_uuid": new_uuid, "page_title": title, "page_slug": slug,
            "page_cat_name": category, "page_type": "page", "page_created_at": datetime.now().strftime("%Y-%m-%d"),
            "page_external_url": None, "page_author_name": author, "page_featured_img": DEFAULT_FEATURED_IMAGE,
            "page_featured_diagram": featured_diagram})
        
        pfile = os.path.join(PAGES_DB_DIR, f"{new_uuid}.json")
        New_Page_Content_Doc = {
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
                ["Content", None, f"<h2>{title}</h2><p>Start writing your content here...</p>", "", ""]
            ]
        }
        tmp = pfile + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(New_Page_Content_Doc, f, indent=2)
        os.replace(tmp, pfile)  # atomic write, matching cms-manage.py's pattern -- a crash mid-write must never leave a partial/corrupt content file
        
        return redirect(f'/edit/{new_uuid}')

    all_media_for_new = db.get_records("MediaAsset")
    diagram_assets_for_new = [
        a for a in all_media_for_new
        if (a.get('asset_mime_type') or '').lower() == 'application/vnd.bejson.diagram+json'
        or (a.get('asset_filename') or '').lower().endswith(('.diag.json', '.json', '.bejson'))
    ]
    html = '''
    <div class="page-header"><h1>Create New Page</h1><p>Add a new page to your website</p></div>
    <form method="POST" class="card">
        <div class="form-group"><label class="form-label">Page Title *</label><input type="text" name="title" class="form-control" required autofocus></div>
        <div class="grid grid-2">
            <div class="form-group"><label class="form-label">Category *</label><select name="category" class="form-control" required><option value="" disabled selected>-- Select Category --</option>{% for c in categories %}<option value="{{ c.cat_name }}">{{ c.cat_name }}</option>{% endfor %}</select></div>
            <div class="form-group"><label class="form-label">Author</label><select name="author" class="form-control"><option value="">-- Select author --</option>{% for a in authors %}<option value="{{ a.author_display_name }}">{{ a.author_display_name }}</option>{% endfor %}</select></div>
        </div>
        <div class="form-group">
            <label class="form-label">Header Diagram (Above Page Content / Below Featured Image)</label>
            <select name="page_featured_diagram" class="form-control">
                <option value="">-- No Header Diagram --</option>
                {% for d in diagram_assets %}<option value="{{ d.asset_filename }}">📊 {{ d.asset_original_name or d.asset_filename }}</option>{% endfor %}
            </select>
        </div>
        <div style="display:flex;gap:10px;margin-top:30px;"><button type="submit" class="btn btn-primary">Create Page</button><a href="/pages" class="btn btn-secondary">Cancel</a></div>
    </form>'''
    return R(html, categories=categories, authors=authors, diagram_assets=diagram_assets_for_new,
             breadcrumbs=get_breadcrumbs(request.path), active_section='content')


@content_cube.route('/api/md2html', methods=['POST'])
@require_auth
def api_md2html():
    payload = request.get_json(silent=True) or {}
    md_text = payload.get('markdown', '')
    fallback_title = payload.get('fallback_title', 'Untitled Document')
    parsed = convert_markdown_to_cms_article(md_text, fallback_title)
    wrapped_html = f'<article class="bejson-cms-article">\n{parsed["html_body"]}\n</article>'
    return jsonify({
        "ok": True,
        "success": True,
        "title": parsed["title"],
        "slug": parsed["slug"],
        "html": wrapped_html,
        "html_body": wrapped_html,
        "excerpt": parsed["excerpt"],
    })


@content_cube.route('/edit/<page_uuid>', methods=['GET', 'POST'])
def edit_content(page_uuid):
    pfile = os.path.join(PAGES_DB_DIR, f"{page_uuid}.json")
    if not os.path.exists(pfile):
        return "Content file not found", 404
    db.mount()
    pages = db.get_records("PageRecord")
    page = next((p for p in pages if p['page_uuid'] == page_uuid), None)
    
    if not page:
        return "Page not found", 404

    if request.method == 'POST':
        html_content = request.form.get('html_content', '')
        markdown_content = request.form.get('markdown_content', None)
        convert_md_on_save = request.form.get('convert_md_on_save') == 'on'
        title = request.form.get('title', page['page_title'])
        featured_img = request.form.get('page_featured_img', page.get('page_featured_img', ''))
        featured_diagram = request.form.get('page_featured_diagram', page.get('page_featured_diagram', ''))
        author = request.form.get('page_author_name', page.get('page_author_name', ''))
        category = request.form.get('page_cat_name', page.get('page_cat_name', ''))
        page_type = request.form.get('page_type', page.get('page_type', 'page'))

        if markdown_content and (convert_md_on_save or not html_content.strip()):
            parsed_md = convert_markdown_to_cms_article(markdown_content, title)
            html_content = f'<article class="bejson-cms-article">\n{parsed_md["html_body"]}\n</article>'

        # Update content file
        try:
            with open(pfile, "r") as f: data = json.load(f)
            field_map = bejson_core_get_field_map(data)
            p_idx = field_map.get("Record_Type_Parent", -1)
            h_idx = field_map.get("html_body", -1)
            md_idx = field_map.get("markdown_body", -1)
            m_idx = field_map.get("meta_title", -1)
            for row in data.get("Values", []):
                if p_idx != -1:
                    if row[p_idx] == "Content":
                        if h_idx != -1:
                            row[h_idx] = html_content
                        if md_idx != -1 and markdown_content is not None:
                            row[md_idx] = markdown_content
                    if row[p_idx] == "PageMeta" and m_idx != -1:
                        row[m_idx] = title
            bejson_core_atomic_write(pfile, data)
        except Exception as err: print(f"Content write error: {err}")

        # Update Master Record
        db.update_record("PageRecord", "page_uuid", page_uuid, {
            "page_title": title,
            "page_featured_img": featured_img,
            "page_featured_diagram": featured_diagram,
            "page_author_name": author,
            "page_cat_name": category,
            "page_type": page_type,
            "page_is_standalone_flag": (page_type == "page"),
        })
        flash("Changes saved successfully!", "success")
        return redirect(f"/edit/{page_uuid}")

    # GET - Load content
    html_content = ""
    markdown_content = ""
    try:
        with open(pfile, "r") as f: data = json.load(f)
        field_map = bejson_core_get_field_map(data)
        p_idx = field_map.get("Record_Type_Parent", -1)
        h_idx = field_map.get("html_body", -1)
        md_idx = field_map.get("markdown_body", -1)
        for row in data.get("Values", []):
            if p_idx != -1 and row[p_idx] == "Content":
                if h_idx != -1:
                    html_content = row[h_idx] or ""
                if md_idx != -1:
                    markdown_content = row[md_idx] or ""
                break
    except Exception: pass
    
    db.mount()
    media_assets = db.get_records("MediaAsset")
    media_assets.sort(key=lambda a: a.get('asset_uploaded_at') or '', reverse=True)
    diagram_assets = [
        a for a in media_assets
        if (a.get('asset_mime_type') or '').lower() == 'application/vnd.bejson.diagram+json'
        or (a.get('asset_filename') or '').lower().endswith(('.diag.json', '.json', '.bejson'))
    ]
    image_media_assets = [
        a for a in media_assets
        if a not in diagram_assets and not (a.get('asset_filename') or '').lower().endswith('.pdf')
    ]
    pdf_assets = [a for a in media_assets if (a.get('asset_filename') or '').lower().endswith('.pdf')]
    pdf_links = [e for e in db.get_records("ExternalMedia") if (e.get('extmedia_type') or '').lower() == 'pdf']
    video_links = [e for e in db.get_records("ExternalMedia") if (e.get('extmedia_type') or '').lower() == 'video']
    categories = db.get_records("Category")
    authors = db.get_records("AuthorProfile")

    html = '''
    <div class="page-header"><h1>Edit: {{ page.page_title }}</h1><p>UUID: {{ page_uuid }}</p></div>
    <form method="POST">
        <div class="card">
            <div class="form-group"><label class="form-label">Title</label><input type="text" name="title" id="page-title-input" class="form-control" value="{{ page.page_title }}"></div>
            <div class="grid grid-2">
                <div class="form-group">
                    <label class="form-label">Featured Image</label>
                    <select name="page_featured_img" id="featured_img_select" class="form-control">
                        <option value="">-- No image --</option>
                        {% for a in image_media_assets %}<option value="{{ a.asset_filename }}" {% if a.asset_filename == page.page_featured_img and page.page_featured_img and page.page_featured_img != 'None' %}selected{% endif %}>{{ a.asset_original_name or a.asset_filename }}</option>{% endfor %}
                    </select>
                    <div style="display:flex; align-items:center; gap:8px; margin-top:8px;">
                        <input type="file" id="featured_img_upload" accept="image/*" style="flex:1; font-size:0.8rem;">
                        <button type="button" class="btn btn-secondary btn-sm" onclick="uploadFeaturedImage()">&#8593; Upload New</button>
                    </div>
                    <div id="featured_img_upload_status" style="font-size:0.8rem; color:var(--text-secondary); margin-top:4px;"></div>
                    <div id="featured_img_preview" style="margin-top:8px;">{% if page.page_featured_img and page.page_featured_img != 'None' %}<img src="/assets/{{ page.page_featured_img }}" style="max-height:80px;border-radius:6px;border:1px solid var(--border);" alt="current">{% endif %}</div>
                </div>
                <div class="form-group">
                    <label class="form-label">Header Diagram (Above Page Content / Below Featured Image)</label>
                    <select name="page_featured_diagram" id="featured_diagram_select" class="form-control">
                        <option value="">-- No Header Diagram --</option>
                        {% for d in diagram_assets %}<option value="{{ d.asset_filename }}" {% if d.asset_filename == page.page_featured_diagram and page.page_featured_diagram and page.page_featured_diagram != 'None' %}selected{% endif %}>📊 {{ d.asset_original_name or d.asset_filename }}</option>{% endfor %}
                    </select>
                    <div style="display:flex; align-items:center; gap:8px; margin-top:8px;">
                        <input type="file" id="featured_diagram_upload" accept=".json,.bejson,.html" style="flex:1; font-size:0.8rem;">
                        <button type="button" class="btn btn-secondary btn-sm" onclick="uploadFeaturedDiagram()">&#8593; Validate &amp; Upload Diagram</button>
                    </div>
                    <div id="featured_diagram_upload_status" style="font-size:0.8rem; color:var(--text-secondary); margin-top:4px;"></div>
                    <div id="featured_diagram_preview_link" style="margin-top:6px;">
                        {% if page.page_featured_diagram and page.page_featured_diagram != 'None' %}
                        <a href="/assets/diagram/preview/{{ page.page_featured_diagram }}" target="_blank" class="btn btn-secondary btn-sm">📊 Preview &amp; Validate Selected Header Diagram</a>
                        {% endif %}
                    </div>
                </div>
                <div class="form-group">
                    <label class="form-label">Author</label>
                    <select name="page_author_name" class="form-control">
                        <option value="">-- Select author --</option>
                        {% for a in authors %}<option value="{{ a.author_display_name }}" {% if a.author_display_name == page.page_author_name %}selected{% endif %}>{{ a.author_display_name }}</option>{% endfor %}
                    </select>
                </div>
                <div class="form-group"><label class="form-label">Category</label><select name="page_cat_name" class="form-control">{% for c in categories %}<option value="{{ c.cat_name }}" {% if c.cat_name == page.page_cat_name %}selected{% endif %}>{{ c.cat_name }}</option>{% endfor %}</select></div>
                <div class="form-group">
                    <label class="form-label">Page Type</label>
                    <select name="page_type" class="form-control">
                        <option value="page" {% if (page.page_type or 'page') == 'page' %}selected{% endif %}>page</option>
                        <option value="blog" {% if page.page_type == 'blog' %}selected{% endif %}>blog</option>
                        <option value="article" {% if page.page_type == 'article' %}selected{% endif %}>article</option>
                    </select>
                </div>
            </div>
        </div>
        <div class="card">
            <div class="card-header">
                <span class="card-title">&#128221; Markdown Source (MD_To_HTML)</span>
                <div style="display:flex;align-items:center;gap:10px;">
                    <label style="font-size:0.8rem;color:var(--text-secondary);display:flex;align-items:center;gap:6px;margin:0;cursor:pointer;">
                        <input type="checkbox" name="convert_md_on_save" id="convert_md_on_save" style="accent-color:var(--accent);"> Re-compile HTML on Save
                    </label>
                    <button type="button" class="btn btn-primary btn-sm" onclick="convertMarkdownToHtml()">&#9889; Convert Markdown &rarr; HTML</button>
                </div>
            </div>
            <textarea id="md-editor" name="markdown_content" class="editor-area" style="min-height:180px;" placeholder="Paste or author Markdown here (supports GFM tables, callouts > [!NOTE], task lists, and syntax fenced code)..."></textarea>
            <div id="md2html-status" style="font-size:0.8rem;color:var(--text-secondary);margin-top:6px;"></div>
        </div>
        <div class="card">
            <div class="card-header"><span class="card-title">HTML Content Editor</span><div><button type="button" class="btn btn-secondary btn-sm" onclick="openModal(\'asset-modal\')">&#128444; Insert Image</button> <button type="button" class="btn btn-secondary btn-sm" onclick="openModal(\'diagram-insert-modal\')">📊 Insert Diagram</button> <button type="button" class="btn btn-secondary btn-sm" onclick="openModal(\'pdf-insert-modal\')">&#128196; Insert PDF</button> <button type="button" class="btn btn-secondary btn-sm" onclick="openModal(\'yt-insert-modal\')">&#9654; Insert YouTube</button></div></div>
            <div class="editor-toolbar"><button type="button" onclick="insertTag(\'h2\')">H2</button><button type="button" onclick="insertTag(\'h3\')">H3</button><button type="button" onclick="insertTag(\'p\')">P</button><button type="button" onclick="insertTag(\'b\')">Bold</button><button type="button" onclick="insertTag(\'br\')">Break</button><button type="button" onclick="insertTag(\'a\')">Link</button></div>
            <textarea id="html-editor" name="html_content" class="editor-area"></textarea>
            <script>
            document.addEventListener('DOMContentLoaded',function(){
                document.getElementById('html-editor').value={{ html_content | tojson }};
                document.getElementById('md-editor').value={{ markdown_content | tojson }};
            });
            async function convertMarkdownToHtml() {
                var mdText = document.getElementById('md-editor').value;
                var statusEl = document.getElementById('md2html-status');
                var titleInput = document.getElementById('page-title-input');
                if (!mdText.trim()) {
                    statusEl.textContent = 'Enter Markdown content first.';
                    return;
                }
                statusEl.textContent = 'Converting Markdown to style-agnostic CMS HTML...';
                try {
                    var res = await fetch('/api/md2html', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            markdown: mdText,
                            fallback_title: titleInput ? titleInput.value : 'Untitled Document'
                        })
                    });
                    var data = await res.json();
                    if (data.success) {
                        document.getElementById('html-editor').value = data.html_body;
                        statusEl.style.color = '#10b981';
                        statusEl.textContent = 'Converted Markdown into <article class="bejson-cms-article"> HTML!';
                    } else {
                        statusEl.style.color = '#ef4444';
                        statusEl.textContent = 'Conversion failed.';
                    }
                } catch (e) {
                    statusEl.style.color = '#ef4444';
                    statusEl.textContent = 'Error converting Markdown: ' + e;
                }
            }
            </script>
            <script>
            function uploadFeaturedImage() {
                var input = document.getElementById('featured_img_upload');
                var statusEl = document.getElementById('featured_img_upload_status');
                if (!input.files || !input.files[0]) {
                    statusEl.textContent = 'Choose a file first.';
                    return;
                }
                var select = document.getElementById('featured_img_select');
                var before = new Set();
                for (var i = 0; i < select.options.length; i++) { before.add(select.options[i].value); }

                var fd = new FormData();
                fd.append('files', input.files[0]);
                statusEl.textContent = 'Uploading...';

                fetch('/assets/upload', { method: 'POST', body: fd })
                    .then(function() {
                        statusEl.textContent = 'Processing...';
                        pollForNewAsset(before, 0);
                    })
                    .catch(function() { statusEl.textContent = 'Upload failed.'; });
            }

            function pollForNewAsset(before, attempt) {
                var statusEl = document.getElementById('featured_img_upload_status');
                if (attempt > 15) {
                    statusEl.textContent = 'Still processing -- reload the page in a moment and select it from the dropdown.';
                    return;
                }
                fetch('/assets/list.json')
                    .then(function(r) { return r.json(); })
                    .then(function(data) {
                        var newFile = (data.files || []).find(function(f) { return !before.has(f.asset_filename); });
                        if (newFile) {
                            var select = document.getElementById('featured_img_select');
                            var opt = document.createElement('option');
                            opt.value = newFile.asset_filename;
                            opt.textContent = newFile.asset_original_name || newFile.asset_filename;
                            opt.selected = true;
                            select.appendChild(opt);
                            select.value = newFile.asset_filename;
                            document.getElementById('featured_img_preview').innerHTML =
                                '<img src="/assets/' + newFile.asset_filename + '" style="max-height:80px;border-radius:6px;border:1px solid var(--border);" alt="new">';
                            statusEl.textContent = 'Uploaded and selected.';
                            document.getElementById('featured_img_upload').value = '';
                        } else {
                            setTimeout(function() { pollForNewAsset(before, attempt + 1); }, 600);
                        }
                    })
                    .catch(function() { statusEl.textContent = 'Could not check upload status.'; });
            }

            function uploadFeaturedDiagram() {
                var input = document.getElementById('featured_diagram_upload');
                var statusEl = document.getElementById('featured_diagram_upload_status');
                if (!input.files || !input.files[0]) {
                    statusEl.textContent = 'Choose a .json, .bejson, or .html diagram file first.';
                    return;
                }
                var select = document.getElementById('featured_diagram_select');
                var before = new Set();
                for (var i = 0; i < select.options.length; i++) { before.add(select.options[i].value); }

                var fd = new FormData();
                fd.append('files', input.files[0]);
                statusEl.textContent = 'Validating & uploading diagram...';

                fetch('/assets/upload', { method: 'POST', body: fd })
                    .then(function() {
                        statusEl.textContent = 'Processing validated diagram...';
                        pollForNewDiagram(before, 0);
                    })
                    .catch(function() { statusEl.textContent = 'Diagram upload failed.'; });
            }

            function pollForNewDiagram(before, attempt) {
                var statusEl = document.getElementById('featured_diagram_upload_status');
                if (attempt > 15) {
                    statusEl.textContent = 'Validation failed or still processing -- check Media Library for error details.';
                    return;
                }
                fetch('/api/media/diagrams')
                    .then(function(r) { return r.json(); })
                    .then(function(data) {
                        var newDiag = (data.diagrams || []).find(function(d) { return !before.has(d.asset_filename); });
                        if (newDiag) {
                            var select = document.getElementById('featured_diagram_select');
                            var opt = document.createElement('option');
                            opt.value = newDiag.asset_filename;
                            opt.textContent = '📊 ' + (newDiag.asset_original_name || newDiag.asset_filename);
                            opt.selected = true;
                            select.appendChild(opt);
                            select.value = newDiag.asset_filename;
                            document.getElementById('featured_diagram_preview_link').innerHTML =
                                '<a href="/assets/diagram/preview/' + newDiag.asset_filename + '" target="_blank" class="btn btn-secondary btn-sm">📊 Preview &amp; Validate Selected Header Diagram</a>';
                            statusEl.style.color = '#10b981';
                            statusEl.textContent = 'Passed 104 Validation and selected as Header Diagram!';
                            document.getElementById('featured_diagram_upload').value = '';
                        } else {
                            setTimeout(function() { pollForNewDiagram(before, attempt + 1); }, 600);
                        }
                    })
                    .catch(function() { statusEl.textContent = 'Could not check diagram upload status.'; });
            }

            function insertInlineDiagramComponent(filename) {
                fetch('/api/media/diagram/render_inline/' + encodeURIComponent(filename))
                    .then(function(r) { return r.json(); })
                    .then(function(data) {
                        if (!data.success || !data.inline_html) {
                            alert('Diagram validation failed: ' + (data.error || 'Unknown error'));
                            return;
                        }
                        var ta = document.getElementById('html-editor');
                        var start = ta.selectionStart || ta.value.length;
                        var end = ta.selectionEnd || ta.value.length;
                        ta.value = ta.value.substring(0, start) + '\\n' + data.inline_html + '\\n' + ta.value.substring(end);
                        closeModal('diagram-insert-modal');
                    })
                    .catch(function(err) { alert('Failed to render inline diagram: ' + err); });
            }
            </script>
        </div>
        <div style="display:flex;gap:10px;margin-top:20px;"><button type="submit" class="btn btn-primary">&#128190; Save Changes</button><a href="/pages" class="btn btn-secondary">&#8592; Back to Pages</a></div>
    </form>
    <div id="asset-modal" class="modal-overlay" onclick="if(event.target===this)closeModal(\'asset-modal\')"><div class="modal"><div class="modal-header"><h3>Select Image</h3><button class="close-btn" onclick="closeModal(\'asset-modal\')">&times;</button></div><div class="modal-body"><div class="asset-grid">{% for a in image_media_assets %}<div class="asset-item" onclick="insertImage(\'{{ a.asset_filename }}\')"><img src="/assets/{{ a.asset_filename }}" alt="{{ a.asset_original_name or a.asset_filename }}" loading="lazy"><div class="asset-name">{{ a.asset_original_name or a.asset_filename }}</div></div>{% endfor %}</div></div></div></div>
    <div id="diagram-insert-modal" class="modal-overlay" onclick="if(event.target===this)closeModal(\'diagram-insert-modal\')">
      <div class="modal">
        <div class="modal-header"><h3>Insert Interactive 3-Tab Diagram Component</h3><button class="close-btn" onclick="closeModal(\'diagram-insert-modal\')">&times;</button></div>
        <div class="modal-body">
          <p style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:12px;">Click a validated diagram below to inject its self-contained 3-tab HTML component at the cursor position (or use the <strong>Header Diagram</strong> dropdown above to place it at the top of the page below the Featured Image).</p>
          {% if diagram_assets %}
          <div class="asset-grid">
            {% for d in diagram_assets %}
            <div class="asset-item" onclick="insertInlineDiagramComponent(\'{{ d.asset_filename }}\')" style="cursor:pointer;padding:14px;text-align:center;">
              <div style="font-size:2rem;">📊</div>
              <div class="asset-name">{{ d.asset_original_name or d.asset_filename }}</div>
            </div>
            {% endfor %}
          </div>
          {% else %}
          <div style="padding:20px;text-align:center;color:var(--text-secondary);font-size:.85rem;">No diagrams uploaded yet — use the Header Diagram uploader above or upload under Media Library.</div>
          {% endif %}
        </div>
      </div>
    </div>
    <div id="pdf-insert-modal" class="modal-overlay" onclick="if(event.target===this)closeModal(\'pdf-insert-modal\')">
      <div class="modal">
        <div class="modal-header"><h3>Insert PDF</h3><button class="close-btn" onclick="closeModal(\'pdf-insert-modal\')">&times;</button></div>
        <div class="modal-body">
          <div style="display:flex;border-bottom:1px solid var(--border);margin-bottom:14px;">
            <button type="button" class="pdf-src-tab-cc active" id="pdfTabLibraryCC" onclick="pdfShowTabCC(\'library\')" style="flex:1;padding:8px 12px;background:transparent;border:none;border-bottom:2px solid var(--accent);color:var(--text);font-size:.85rem;font-weight:700;cursor:pointer;">From Media Library</button>
            <button type="button" class="pdf-src-tab-cc" id="pdfTabUrlCC" onclick="pdfShowTabCC(\'url\')" style="flex:1;padding:8px 12px;background:transparent;border:none;border-bottom:2px solid transparent;color:var(--text-secondary);font-size:.85rem;font-weight:700;cursor:pointer;">External URL</button>
          </div>
          <div id="pdfPaneLibraryCC">
            {% if pdf_assets or pdf_links %}
            <div class="asset-grid">
              {% for a in pdf_assets %}<div class="asset-item picker-insert-item" data-action="pdf" data-url="../../../assets/{{ a.asset_filename }}" data-label="{{ a.asset_original_name or a.asset_filename }}" style="cursor:pointer;padding:14px;text-align:center;"><div style="font-size:2rem;">&#128196;</div><div class="asset-name">{{ a.asset_original_name or a.asset_filename }}</div></div>{% endfor %}
              {% for e in pdf_links %}<div class="asset-item picker-insert-item" data-action="pdf" data-url="{{ e.extmedia_url }}" data-label="{{ e.extmedia_name or e.extmedia_url }}" style="cursor:pointer;padding:14px;text-align:center;"><div style="font-size:2rem;">&#128279;</div><div class="asset-name">{{ e.extmedia_name or e.extmedia_url }}</div></div>{% endfor %}
            </div>
            {% else %}
            <div style="padding:20px;text-align:center;color:var(--text-secondary);font-size:.85rem;">No PDFs yet — upload one under Media Library, or use the External URL tab.</div>
            {% endif %}
          </div>
          <div id="pdfPaneUrlCC" style="display:none;">
            <div class="form-group"><label class="form-label">PDF URL</label><input type="url" id="pdfExternalUrlCC" class="form-control" placeholder="https://example.com/file.pdf"></div>
            <button type="button" class="btn btn-primary btn-sm" onclick="insertPdfFromUrlCC()">Insert</button>
          </div>
        </div>
      </div>
    </div>
    <div id="yt-insert-modal" class="modal-overlay" onclick="if(event.target===this)closeModal('yt-insert-modal')">
      <div class="modal">
        <div class="modal-header"><h3>Insert YouTube Video</h3><button class="close-btn" onclick="closeModal('yt-insert-modal')">&times;</button></div>
        <div class="modal-body">
          <div style="display:flex;border-bottom:1px solid var(--border);margin-bottom:14px;">
            <button type="button" class="pdf-src-tab-cc active" id="ytTabLibraryCC" onclick="ytShowTabCC('library')" style="flex:1;padding:8px 12px;background:transparent;border:none;border-bottom:2px solid var(--accent);color:var(--text);font-size:.85rem;font-weight:700;cursor:pointer;">From Saved Links</button>
            <button type="button" class="pdf-src-tab-cc" id="ytTabUrlCC" onclick="ytShowTabCC('url')" style="flex:1;padding:8px 12px;background:transparent;border:none;border-bottom:2px solid transparent;color:var(--text-secondary);font-size:.85rem;font-weight:700;cursor:pointer;">Paste URL / ID</button>
          </div>
          <div id="ytPaneLibraryCC">
            {% if video_links %}
            <div class="asset-grid">
              {% for e in video_links %}<div class="asset-item picker-insert-item" data-action="yt" data-url="{{ e.extmedia_url }}" data-label="{{ e.extmedia_name or e.extmedia_url }}" style="cursor:pointer;padding:14px;text-align:center;"><div style="font-size:2rem;">&#9654;</div><div class="asset-name">{{ e.extmedia_name or e.extmedia_url }}</div></div>{% endfor %}
            </div>
            {% else %}
            <div style="padding:20px;text-align:center;color:var(--text-secondary);font-size:.85rem;">No saved video links yet — add one under Media Library, or use the Paste URL/ID tab.</div>
            {% endif %}
          </div>
          <div id="ytPaneUrlCC" style="display:none;">
            <div class="form-group"><label class="form-label">YouTube URL or Video ID</label><input type="url" id="ytExternalUrlCC" class="form-control" placeholder="https://www.youtube.com/watch?v=dQw4w9WgXcQ"></div>
            <button type="button" class="btn btn-primary btn-sm" onclick="insertYtFromUrlCC()">Insert</button>
          </div>
        </div>
      </div>
    </div>'''
    breadcrumbs = [{'label': 'Content', 'href': '/content'}, {'label': 'Pages', 'href': '/pages'}, {'label': page['page_title'], 'href': None}]
    return R(html, page=page, page_uuid=page_uuid, html_content=html_content, markdown_content=markdown_content, media_assets=media_assets,
             image_media_assets=image_media_assets, diagram_assets=diagram_assets,
             pdf_assets=pdf_assets, pdf_links=pdf_links, video_links=video_links,
             categories=categories, authors=authors, breadcrumbs=breadcrumbs, active_section='content')


@content_cube.route('/pages/delete/<page_uuid>', methods=['POST'])
def delete_page(page_uuid):
    db.mount()
    deleted = db.delete_record("PageRecord", "page_uuid", page_uuid)
    
    if deleted:
        pfile = os.path.join(PAGES_DB_DIR, f"{page_uuid}.json")
        if os.path.exists(pfile):
            os.remove(pfile)
        flash('Page deleted.', 'success')
    else:
        flash('Error: page could not be deleted from database.', 'error')
    return redirect('/pages')


@content_cube.route('/pages/duplicate/<page_uuid>', methods=['POST'])
def duplicate_page(page_uuid):
    # Common CMS convenience feature this project didn't have at all: clone
    # an existing page (record + real content) as a starting point for a
    # similar one, rather than building from scratch every time.
    db.mount()
    pages = db.get_records("PageRecord")
    source = next((p for p in pages if p.get("page_uuid") == page_uuid), None)
    if not source:
        flash('Page not found.', 'error')
        return redirect('/pages')
    if source.get('page_type') == 'external_link':
        flash('External links cannot be duplicated -- add a new one instead.', 'error')
        return redirect('/pages')

    new_uuid = str(uuid.uuid4())
    new_title = f"Copy of {source.get('page_title', '')}"
    base_slug = re.sub(r'[^a-z0-9]', '-', new_title.lower()).strip('-')
    existing_slugs = {p.get('page_slug') for p in pages}
    slug = base_slug
    Duplicate_Slug_Suffix_Counter = 2
    while slug in existing_slugs:
        slug = f"{base_slug}-{Duplicate_Slug_Suffix_Counter}"
        Duplicate_Slug_Suffix_Counter += 1

    db.add_record("PageRecord", {
        "page_uuid": new_uuid, "page_title": new_title, "page_slug": slug,
        "page_cat_name": source.get("page_cat_name"), "page_type": source.get("page_type", "page"),
        "page_created_at": datetime.now().strftime("%Y-%m-%d"), "page_external_url": None,
        "page_author_name": source.get("page_author_name"), "page_featured_img": source.get("page_featured_img"),
        "page_featured_diagram": source.get("page_featured_diagram", ""),
        "page_template_key": source.get("page_template_key"),
    })

    src_file = os.path.join(PAGES_DB_DIR, f"{page_uuid}.json")
    new_file = os.path.join(PAGES_DB_DIR, f"{new_uuid}.json")
    if os.path.exists(src_file):
        with open(src_file, 'r') as f:
            content_data = json.load(f)
        # Update the copy's own PageMeta title to match; leave the actual
        # body content (html_body/markdown_body/source_code) untouched --
        # that's the whole point of duplicating.
        content_field_map_cache = bejson_core_get_field_map(content_data) if content_data.get("Fields") else {}
        parent_type_col_idx = content_field_map_cache.get("Record_Type_Parent", 0)
        title_idx = content_field_map_cache.get("meta_title", -1)
        for row in content_data.get("Values", []):
            if row and row[parent_type_col_idx] == "PageMeta" and title_idx != -1:
                row[title_idx] = new_title
        bejson_core_atomic_write(new_file, content_data)

    flash(f'Duplicated as "{new_title}". Edit the copy below.', 'success')
    return redirect(f'/edit/{new_uuid}')


@content_cube.route('/links')
def links_list():
    db.mount()
    links = [p for p in db.get_records("PageRecord") if p.get('page_type') == 'external_link']
    
    html = '''
    <div class="page-header"><h1>External Links</h1><p>Manage external link references</p></div>
    <div class="toolbar"><a href="/links/new" class="btn btn-primary">+ Add External Link</a></div>
    <div class="card">{% if links %}<div class="table-container"><table><thead><tr><th>Label</th><th>URL</th><th>Category</th><th>Actions</th></tr></thead><tbody>
    {% for l in links %}<tr><td>&#128279; {{ l.page_title }}</td><td><a href="{{ l.page_external_url }}" target="_blank" style="color:var(--accent);">{{ l.page_external_url[:60] if l.page_external_url else \'\' }}</a></td><td>{{ l.page_cat_name or \'Uncategorized\' }}</td>
    <td><form method="post" action="/pages/delete/{{ l.page_uuid }}" style="display:inline;" onsubmit="return confirm(\'Delete this page?\')"><button type="submit" class="btn btn-danger btn-sm">Delete</button></form></td></tr>{% endfor %}
    </tbody></table></div>{% else %}<div class="empty-state"><h3>No external links</h3><p>Add links to external resources</p><br><a href="/links/new" class="btn btn-primary">Add Link</a></div>{% endif %}</div>'''
    return R(html, links=links, breadcrumbs=get_breadcrumbs(request.path), active_section='content')


@content_cube.route('/links/new', methods=['GET', 'POST'])
def link_new():
    db.mount()
    categories = db.get_records("Category")
    
    if request.method == 'POST':
        label = request.form.get('label', '').strip()
        Submitted_External_Link_Url = request.form.get('url', '').strip()
        category = request.form.get('category', 'Uncategorized')
        if not label or not Submitted_External_Link_Url:
            flash('Label and URL are required.', 'error')
            return redirect('/links/new')
        new_uuid = str(uuid.uuid4())
        slug = re.sub(r'[^a-z0-9]', '-', label.lower()).strip('-')
        db.mount()
        db.add_record("PageRecord", {"page_uuid": new_uuid, "page_title": label, "page_slug": slug,
            "page_cat_name": category, "page_type": "external_link", "page_external_url": Submitted_External_Link_Url,
            "page_created_at": datetime.now().strftime("%Y-%m-%d"), "page_author_name": "", "page_featured_img": ""})
        
        flash('External link added.', 'success')
        return redirect('/links')
    html = '''
    <div class="page-header"><h1>Add External Link</h1></div>
    <form method="POST" class="card">
        <div class="form-group"><label class="form-label">Label *</label><input type="text" name="label" class="form-control" required autofocus></div>
        <div class="form-group"><label class="form-label">URL *</label><input type="url" name="url" class="form-control" required placeholder="https://"></div>
        <div class="form-group"><label class="form-label">Category</label><select name="category" class="form-control">{% for c in categories %}<option value="{{ c.cat_name }}">{{ c.cat_name }}</option>{% endfor %}</select></div>
        <div style="display:flex;gap:10px;margin-top:20px;"><button type="submit" class="btn btn-primary">Add Link</button><a href="/links" class="btn btn-secondary">Cancel</a></div>
    </form>'''
    return R(html, categories=categories, breadcrumbs=get_breadcrumbs(request.path), active_section='content')


@content_cube.route('/categories')
def categories_list():
    db.mount()
    categories = db.get_records("Category")
    
    html = '''
    <div class="page-header"><h1>Categories</h1><p>Organize your content by category</p></div>
    <div class="toolbar">
        <form action="/categories/add" method="POST" style="display:flex;gap:10px;flex:1;">
            <input type="text" name="cat_name" class="form-control" placeholder="New category name..." required>
            <button type="submit" class="btn btn-primary">Add Category</button>
        </form>
    </div>
    <div class="card"><div class="table-container"><table><thead><tr><th>Category Name</th><th>Slug</th><th>Actions</th></tr></thead><tbody>
    {% for c in categories %}<tr><td>{{ c.cat_name }}</td><td><code style="background:var(--bg-secondary);padding:2px 8px;border-radius:4px;">{{ c.cat_slug }}</code></td>
    <td>{% if c.cat_name != \'Uncategorized\' %}<form method="post" action="/categories/delete/{{ c.cat_name }}" style="display:inline;" onsubmit="return confirm(\'Delete category?\')"><button type="submit" class="btn btn-danger btn-sm">Delete</button></form>{% endif %}</td></tr>{% endfor %}
    </tbody></table></div></div>'''
    return R(html, categories=categories, breadcrumbs=get_breadcrumbs(request.path), active_section='content')


@content_cube.route('/categories/add', methods=['POST'])
def categories_add():
    name = request.form.get('cat_name', '').strip()
    if name:
        slug = re.sub(r'[^a-z0-9]', '-', name.lower()).strip('-')
        db.mount()
        exists = any(c.get('cat_name', '').lower() == name.lower() for c in db.get_records("Category"))
        if not exists:
            db.add_record("Category", {"cat_name": name, "cat_slug": slug})
            flash(f'Category "{name}" added.', 'success')
        else:
            flash(f'Category "{name}" already exists.', 'error')
    return redirect('/categories')


@content_cube.route("/categories/delete/<name>", methods=['POST'])
def categories_delete(name):
    if name == "Uncategorized":
        flash("Cannot delete Uncategorized.", "error")
        return redirect("/categories")
    
    # Delete the category
    db.delete_record("Category", "cat_name", name)
    
    # Reassign pages to Uncategorized using orchestrator
    pages = db.get_records("PageRecord")
    for p in pages:
        if p.get("page_cat_name") == name:
            db.update_record("PageRecord", "page_uuid", p["page_uuid"], {"page_cat_name": "Uncategorized"})
            
    flash(f"Category '{name}' deleted. Pages reassigned to Uncategorized.", "success")
    return redirect("/categories")


# =============================================================================
# ROUTES — ASSETS (Media Library — rebuilt v18.9, memory-conscious)
# =============================================================================

ASSETS_PER_PAGE = 24


@content_cube.route('/apps')
def apps_list():
    db.mount()
    Standalone_App_Records = db.get_records("StandaloneApp")
    
    html = '''
    <div class="page-header"><h1>Applications</h1><p>Manage standalone HTML/JS applications</p></div>
    <div class="toolbar"><a href="/apps/new" class="btn btn-primary">+ Import App</a></div>
    <div class="grid">{% for a in apps %}<div class="card"><div style="display:flex;justify-content:space-between;align-items:start;"><div><h3 style="margin-bottom:10px;">{{ a.app_name }}</h3><p style="color:var(--text-secondary);font-size:0.9rem;">{{ a.app_description or \'No description\' }}</p><p style="color:var(--text-secondary);font-size:0.8rem;margin-top:10px;">Slug: <code>{{ a.app_slug }}</code></p></div>{% if a.app_featured_img %}<img src="/assets/{{ a.app_featured_img }}" style="width:80px;height:80px;object-fit:cover;border-radius:6px;">{% endif %}</div><div style="margin-top:20px;display:flex;gap:10px;"><a href="/apps/edit/{{ a.app_uuid }}" class="btn btn-primary btn-sm">Edit</a><a href="/apps/view/{{ a.app_uuid }}" class="btn btn-secondary btn-sm">View</a><form method="post" action="/apps/delete/{{ a.app_uuid }}" style="display:inline;" onsubmit="return confirm(\'Delete app?\')"><button type="submit" class="btn btn-danger btn-sm">Delete</button></form></div></div>{% endfor %}</div>
    {% if not apps %}<div class="card empty-state"><h3>No applications yet</h3><p>Import HTML files or ZIP archives</p><br><a href="/apps/new" class="btn btn-primary">Import App</a></div>{% endif %}'''
    return R(html, apps=Standalone_App_Records, breadcrumbs=get_breadcrumbs(request.path), active_section='apps')


@content_cube.route('/apps/new', methods=['GET', 'POST'])
def app_new():
    assets = get_image_assets()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        Submitted_App_Description = request.form.get('desc', '')
        entry_file = request.form.get('app_entry_file', 'index.html')
        app_image = request.form.get('app_featured_img', '')
        if not name:
            return "App name required", 400
        uploaded_file = request.files.get('app_file')
        new_uuid = str(uuid.uuid4())
        slug = re.sub(r'[^a-z0-9]', '-', name.lower()).strip('-')
        app_dir = os.path.join(APPS_STORAGE, new_uuid)
        os.makedirs(app_dir, exist_ok=True)
        _t0 = time.perf_counter()
        if uploaded_file and uploaded_file.filename:
            filename = secure_filename(uploaded_file.filename)
            if filename.endswith('.zip'):
                zip_path = os.path.join(app_dir, 'temp.zip')
                _t_save0 = time.perf_counter()
                uploaded_file.save(zip_path)
                _t_save1 = time.perf_counter()
                with zipfile.ZipFile(zip_path, 'r') as z:
                    _MAX_EXTRACTED_BYTES = 300 * 1024 * 1024  # 300MB — generous for a small app bundle, guards against a decompression bomb
                    _total_uncompressed = sum(i.file_size for i in z.infolist())
                    if _total_uncompressed > _MAX_EXTRACTED_BYTES:
                        os.remove(zip_path)
                        flash(f'App ZIP rejected — {_total_uncompressed // (1024*1024)}MB uncompressed exceeds the {_MAX_EXTRACTED_BYTES // (1024*1024)}MB safety cap.', 'error')
                        return redirect('/apps/new')
                    try:
                        safe_extract_zip(z, app_dir)
                    except ValueError as _e:
                        os.remove(zip_path)
                        shutil.rmtree(app_dir, ignore_errors=True)
                        flash(f'App ZIP rejected — contains a member that would extract outside the app folder ({_e}).', 'error')
                        return redirect('/apps/new')
                _t_extract1 = time.perf_counter()
                os.remove(zip_path)
                gc.collect()
                logging.debug(f"[IMPORT] app_new zip_save_ms={(_t_save1-_t_save0)*1000:.1f} "
                              f"zip_extract_ms={(_t_extract1-_t_save1)*1000:.1f}")
            else:
                uploaded_file.save(os.path.join(app_dir, filename))
                entry_file = filename
        db.mount()
        _t_add0 = time.perf_counter()
        db.add_record("StandaloneApp", {"app_uuid": new_uuid, "app_name": name, "app_slug": slug,
            "app_description": Submitted_App_Description, "app_entry_file": entry_file, "app_featured_img": app_image})
        logging.debug(f"[IMPORT] app_new add_record_ms={(time.perf_counter()-_t_add0)*1000:.1f} "
                      f"total_ms={(time.perf_counter()-_t0)*1000:.1f}")
        
        flash(f'App "{name}" imported.', 'success')
        return redirect('/apps')
    html = '''
    <div class="page-header"><h1>Import Application</h1><p>Add a standalone application</p></div>
    <form method="POST" enctype="multipart/form-data" class="card" id="appForm">
        <div class="form-group"><label class="form-label">App Name *</label><input type="text" name="name" class="form-control" required></div>
        <div class="form-group"><label class="form-label">Description</label><textarea name="desc" class="form-control"></textarea></div>
        <div class="form-group">
            <label class="form-label">Entry File (e.g., index.html)</label>
            <div style="display:flex;gap:10px;">
                <select name="app_entry_file" id="entryFileSelect" class="form-control" style="flex:1;">
                    <option value="index.html">index.html</option>
                </select>
                <input type="text" id="entryFileText" class="form-control" style="flex:1;display:none;" placeholder="Or type manually...">
                <button type="button" class="btn btn-secondary" onclick="toggleEntryMode()">Edit Manually</button>
            </div>
        </div>
        <div class="form-group"><label class="form-label">Featured Image</label><select name="app_featured_img" class="form-control"><option value="">-- No image --</option>{% for a in assets %}<option value="{{ a }}">{{ a }}</option>{% endfor %}</select></div>
        <div class="form-group">
            <label class="form-label">App File (HTML or ZIP) *</label>
            <div style="display:flex;gap:10px;">
                <input type="file" name="app_file" id="appFileInput" class="form-control" accept=".html,.htm,.zip" required onchange="handleFileChange()">
                <button type="button" class="btn btn-secondary" id="scanBtn" onclick="scanZip()" style="display:none;">Scan ZIP</button>
            </div>
        </div>
        <div style="display:flex;gap:10px;margin-top:30px;"><button type="submit" class="btn btn-primary">Import App</button><a href="/apps" class="btn btn-secondary">Cancel</a></div>
    </form>
    <script>
    function toggleEntryMode() {
        const sel = document.getElementById('entryFileSelect');
        const txt = document.getElementById('entryFileText');
        if (sel.style.display === 'none') {
            sel.style.display = 'block';
            txt.style.display = 'none';
            sel.name = 'app_entry_file';
            txt.name = '';
        } else {
            sel.style.display = 'none';
            txt.style.display = 'block';
            sel.name = '';
            txt.name = 'app_entry_file';
        }
    }

    function handleFileChange() {
        const fileIn = document.getElementById('appFileInput');
        const scanBtn = document.getElementById('scanBtn');
        const sel = document.getElementById('entryFileSelect');
        
        if (fileIn.files.length > 0) {
            const file = fileIn.files[0];
            if (file.name.toLowerCase().endsWith('.zip')) {
                scanBtn.style.display = 'block';
            } else {
                scanBtn.style.display = 'none';
                // Auto-populate for single HTML
                if (file.name.toLowerCase().match(/\\.html?$/)) {
                    sel.innerHTML = `<option value="${file.name}">${file.name}</option>`;
                }
            }
        }
    }

    async function scanZip() {
        const fileIn = document.getElementById('appFileInput');
        if (fileIn.files.length === 0) return;
        
        const formData = new FormData();
        formData.append('app_file', fileIn.files[0]);
        
        const scanBtn = document.getElementById('scanBtn');
        scanBtn.disabled = true;
        scanBtn.textContent = 'Scanning...';
        
        try {
            const res = await fetch('/api/apps/scan_zip', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            if (data.success) {
                const sel = document.getElementById('entryFileSelect');
                sel.innerHTML = '';
                if (data.files.length === 0) {
                    sel.innerHTML = '<option value="index.html">No HTML files found (default: index.html)</option>';
                } else {
                    data.files.forEach(f => {
                        const opt = document.createElement('option');
                        opt.value = f;
                        opt.textContent = f;
                        if (f.toLowerCase() === 'index.html') opt.selected = true;
                        sel.appendChild(opt);
                    });
                }
            } else {
                alert('Scan failed: ' + data.error);
            }
        } catch (e) {
            alert('Error scanning ZIP: ' + e);
        } finally {
            scanBtn.disabled = false;
            scanBtn.textContent = 'Scan ZIP';
        }
    }
    </script>'''
    return R(html, assets=assets, breadcrumbs=get_breadcrumbs(request.path), active_section='apps')


@content_cube.route('/apps/edit/<app_uuid>', methods=['GET', 'POST'])
def app_edit(app_uuid):
    db.mount()
    apps = db.get_records("StandaloneApp")
    app_data = next((a for a in apps if a['app_uuid'] == app_uuid), None)
    if not app_data:
        flash('App not found.', 'error')
        return redirect('/apps')

    assets = get_image_assets()
    app_dir = os.path.join(APPS_STORAGE, app_uuid)

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        Submitted_App_Description = request.form.get('desc', '')
        entry_file = request.form.get('app_entry_file', app_data.get('app_entry_file', 'index.html')).strip()
        app_image = request.form.get('app_featured_img', '')
        if not name:
            return "App name required", 400

        uploaded_file = request.files.get('app_file')
        if uploaded_file and uploaded_file.filename:
            # Replacing the app payload: wipe the old files and re-extract, same
            # logic as app_new(), so a wrong upload can be fully corrected.
            if os.path.exists(app_dir):
                shutil.rmtree(app_dir)
            os.makedirs(app_dir, exist_ok=True)
            filename = secure_filename(uploaded_file.filename)
            if filename.endswith('.zip'):
                zip_path = os.path.join(app_dir, 'temp.zip')
                uploaded_file.save(zip_path)
                with zipfile.ZipFile(zip_path, 'r') as z:
                    _MAX_EXTRACTED_BYTES = 300 * 1024 * 1024
                    _total_uncompressed = sum(i.file_size for i in z.infolist())
                    if _total_uncompressed > _MAX_EXTRACTED_BYTES:
                        os.remove(zip_path)
                        flash(f'App ZIP rejected — {_total_uncompressed // (1024*1024)}MB uncompressed exceeds the {_MAX_EXTRACTED_BYTES // (1024*1024)}MB safety cap.', 'error')
                        return redirect(f'/apps/edit/{app_uuid}')
                    try:
                        safe_extract_zip(z, app_dir)
                    except ValueError as _e:
                        os.remove(zip_path)
                        flash(f'App ZIP rejected — contains a member that would extract outside the app folder ({_e}).', 'error')
                        return redirect(f'/apps/edit/{app_uuid}')
                os.remove(zip_path)
                gc.collect()
            else:
                uploaded_file.save(os.path.join(app_dir, filename))
                entry_file = filename

        db.update_record("StandaloneApp", "app_uuid", app_uuid, {
            "app_name": name, "app_description": Submitted_App_Description, "app_entry_file": entry_file, "app_featured_img": app_image,
        })
        flash(f'App "{name}" updated.', 'success')
        return redirect('/apps')

    image_options = '<option value="">-- No image --</option>' + "".join(
        f'<option value="{a}" {"selected" if a == app_data.get("app_featured_img") else ""}>{a}</option>' for a in assets
    )
    html = f'''
    <div class="page-header"><h1>Edit Application</h1><p>Update this application\\'s details, image, or replace its file</p></div>
    <form method="POST" enctype="multipart/form-data" class="card">
        <div class="form-group"><label class="form-label">App Name *</label><input type="text" name="name" class="form-control" value="{_html_escape.escape(app_data.get("app_name",""))}" required></div>
        <div class="form-group"><label class="form-label">Description</label><textarea name="desc" class="form-control">{_html_escape.escape(app_data.get("app_description") or "")}</textarea></div>
        <div class="form-group">
            <label class="form-label">Entry File (e.g., index.html)</label>
            <input type="text" name="app_entry_file" class="form-control" value="{_html_escape.escape(app_data.get("app_entry_file","index.html"))}">
        </div>
        <div class="form-group"><label class="form-label">Featured Image</label><select name="app_featured_img" class="form-control">{image_options}</select></div>
        <div class="form-group">
            <label class="form-label">Replace App File (optional — HTML or ZIP)</label>
            <input type="file" name="app_file" class="form-control" accept=".html,.htm,.zip">
            <p style="color:var(--text-secondary);font-size:.8rem;margin-top:6px;">Leave blank to keep the currently imported file(s). Uploading a new file replaces everything currently stored for this app.</p>
        </div>
        <div style="display:flex;gap:10px;margin-top:30px;"><button type="submit" class="btn btn-primary">Save Changes</button><a href="/apps" class="btn btn-secondary">Cancel</a></div>
    </form>'''
    return R(html, breadcrumbs=get_breadcrumbs(request.path), active_section='apps')


@content_cube.route('/api/apps/scan_zip', methods=['POST'])
@require_auth
def api_apps_scan_zip():
    file = request.files.get('app_file')
    if not file or not file.filename.endswith('.zip'):
        return jsonify({"success": False, "error": "No ZIP file uploaded"})
    
    html_files = []
    try:
        with zipfile.ZipFile(file, 'r') as z:
            # Same 300MB uncompressed-size guard as app_new()/app_edit() —
            # this endpoint was missing it, letting a crafted ZIP enumerate
            # an unbounded number of entries before any size check ran.
            _MAX_EXTRACTED_BYTES = 300 * 1024 * 1024
            _total_uncompressed = sum(i.file_size for i in z.infolist())
            if _total_uncompressed > _MAX_EXTRACTED_BYTES:
                return jsonify({"success": False, "error": f"ZIP rejected — {_total_uncompressed // (1024*1024)}MB uncompressed exceeds the {_MAX_EXTRACTED_BYTES // (1024*1024)}MB safety cap."})
            for info in z.infolist():
                if info.filename.lower().endswith(('.html', '.htm')):
                    html_files.append(info.filename)
        return jsonify({"success": True, "files": sorted(html_files)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@content_cube.route('/apps/delete/<app_uuid>', methods=['POST'])
def app_delete(app_uuid):
    # Confirmed live (2026-08-25): app_uuid was used unvalidated in
    # os.path.join() then shutil.rmtree() -- a request with app_uuid=".."
    # resolves app_dir to APPS_STORAGE's own parent and recursively
    # deletes everything inside it (the entire mfdb/ tree: site_master,
    # pages_db, assets, standalone_apps), not just one app's folder.
    # Reproduced and confirmed destructive in an isolated test copy before
    # this fix -- validate before any path use, same as serve_app_static().
    try:
        uuid.UUID(app_uuid)
    except ValueError:
        flash('Invalid app ID.', 'error')
        return redirect('/apps')

    db.mount()
    db.delete_record("StandaloneApp", "app_uuid", app_uuid)
    
    app_dir = os.path.join(APPS_STORAGE, app_uuid)
    if os.path.exists(app_dir):
        shutil.rmtree(app_dir)
    flash('App deleted.', 'success')
    return redirect('/apps')


@content_cube.route('/apps/view/<app_uuid>')
def serve_app(app_uuid):
    # Same class of issue as app_delete() above: app_uuid reached
    # os.path.join()/os.path.exists() with no validation. Lower severity
    # here (no delete), but a crafted app_uuid could still probe file
    # existence outside APPS_STORAGE. Validate for consistency with
    # serve_app_static(), which already does this correctly.
    try:
        uuid.UUID(app_uuid)
    except ValueError:
        return "Invalid app ID", 400

    app_dir = os.path.join(APPS_STORAGE, app_uuid)
    if not os.path.exists(app_dir):
        return "App not found", 404
    db.mount()
    apps = db.get_records("StandaloneApp")
    
    app_data = next((a for a in apps if a['app_uuid'] == app_uuid), None)
    if not app_data:
        return "App not found in database", 404
    entry_file = app_data.get('app_entry_file', 'index.html')
    entry_path = os.path.join(app_dir, entry_file)
    if not os.path.exists(entry_path):
        return "Entry file not found", 404
    return send_file(entry_path)


@content_cube.route('/apps/view/<app_uuid>/<path:filename>')
def serve_app_static(app_uuid, filename):
    # Validate app_uuid is a proper UUID to prevent path traversal
    try:
        uuid.UUID(app_uuid)
    except ValueError:
        return 'Invalid app ID', 400
    safe_root = os.path.realpath(APPS_STORAGE)
    file_path = os.path.realpath(os.path.join(APPS_STORAGE, app_uuid, filename))
    if not file_path.startswith(safe_root + os.sep):
        return 'Access denied', 403
    if os.path.exists(file_path):
        return send_file(file_path)
    return 'File not found', 404


# =============================================================================
# ROUTES — SITE CONFIG
# =============================================================================


@content_cube.route('/site/authors', methods=['GET', 'POST'])
def manage_authors():
    db.mount()
    if request.method == 'POST':
        action = request.form.get('action', 'add')
        if action == 'add':
            name = request.form.get('author_display_name', '').strip()
            Submitted_Author_Bio  = request.form.get('author_bio', '')
            Submitted_Author_Image_Filename  = request.form.get('author_avatar_url', '')
            if name:
                existing = any(a.get('author_display_name', '').lower() == name.lower() for a in db.get_records("AuthorProfile"))
                if existing:
                    flash(f'An author named "{name}" already exists.', 'error')
                else:
                    db.add_record("AuthorProfile", {"author_display_name": name, "author_bio": Submitted_Author_Bio, "author_avatar_url": Submitted_Author_Image_Filename})
                    db.commit()
                    flash(f'Author "{name}" added.', 'success')
        elif action == 'edit':
            name = request.form.get('author_display_name', '').strip()
            Submitted_Author_Bio  = request.form.get('author_bio', '')
            Submitted_Author_Image_Filename  = request.form.get('author_avatar_url', '')
            db.update_record("AuthorProfile", "author_display_name", name, {"author_bio": Submitted_Author_Bio, "author_avatar_url": Submitted_Author_Image_Filename})
            db.commit()
            flash(f'Author "{name}" updated.', 'success')
        elif action == 'delete':
            name = request.form.get('author_display_name', '')
            db.delete_record("AuthorProfile", "author_display_name", name)
            db.commit()
            flash('Author deleted.', 'success')
        return redirect('/site/authors')

    authors = db.get_records("AuthorProfile")
    assets  = get_image_assets()

    html = '''
    <style>
        .author-edit-panel { display:none; margin-top:12px; padding:12px; background:rgba(0,0,0,0.3); border-radius:6px; border:1px solid var(--border); }
        /* Author row: classic flex-overflow bug -- the text block had no
           min-width:0 so it never shrank/wrapped and collided with the
           Edit/Delete buttons on narrow screens instead of wrapping under
           them. Fixed pkg77. */
        .author-row { display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:10px; }
        .author-row-info { display:flex; gap:12px; align-items:center; min-width:0; flex:1 1 200px; }
        .author-row-info .author-name-bio { min-width:0; overflow-wrap:break-word; }
        .author-row-info .author-name-bio strong { overflow-wrap:break-word; word-break:break-word; }
        .author-row-actions { display:flex; gap:6px; flex-shrink:0; }
        @media (max-width: 480px) {
            .author-row-actions { width:100%; justify-content:flex-end; }
        }
    </style>
    <div class="page-header"><h1>Manage Authors</h1><p>Manage author profiles for your site</p></div>
    <div class="grid grid-2">
        <div class="card">
            <div class="card-header"><span class="card-title">Add New Author</span></div>
            <form method="POST">
                <input type="hidden" name="action" value="add">
                <div class="form-group"><label class="form-label">Author Name *</label><input type="text" name="author_display_name" class="form-control" required></div>
                <div class="form-group"><label class="form-label">Bio</label><textarea name="author_bio" class="form-control" rows="3"></textarea></div>
                <div class="form-group"><label class="form-label">Profile Image</label>
                    <select name="author_avatar_url" class="form-control"><option value="">-- No image --</option>{% for a in assets %}<option value="{{ a }}">{{ a }}</option>{% endfor %}</select>
                </div>
                <button type="submit" class="btn btn-primary">Add Author</button>
            </form>
        </div>
        <div class="card">
            <div class="card-header"><span class="card-title">Existing Authors ({{ authors|length }})</span></div>
            {% for auth in authors %}
            {% set aid = auth.author_display_name | replace(\' \', \'_\') %}
            <div style="padding:15px;background:var(--bg-secondary);margin-bottom:10px;border-radius:8px;">
                <div class="author-row">
                    <div class="author-row-info">
                        {% if auth.author_avatar_url %}
                        <img src="/assets/{{ auth.author_avatar_url }}" style="width:48px;height:48px;border-radius:50%;object-fit:cover;border:2px solid var(--border);flex-shrink:0;">
                        {% else %}
                        <div style="width:48px;height:48px;border-radius:50%;background:var(--border);display:flex;align-items:center;justify-content:center;font-size:1.3rem;flex-shrink:0;">👤</div>
                        {% endif %}
                        <div class="author-name-bio">
                            <strong>{{ auth.author_display_name }}</strong>
                            <p style="margin-top:3px;color:var(--text-secondary);font-size:0.85rem;">{{ auth.author_bio[:80] if auth.author_bio else \'No bio\' }}</p>
                        </div>
                    </div>
                    <div class="author-row-actions">
                        <button class="btn btn-secondary btn-sm toggle-edit-btn" data-aid="{{ aid }}" type="button">Edit</button>
                        <form method="POST" style="display:inline;">
                            <input type="hidden" name="action" value="delete">
                            <input type="hidden" name="author_display_name" value="{{ auth.author_display_name }}">
                            <button type="submit" class="btn btn-danger btn-sm" onclick="return confirm(\'Delete author?\')">Delete</button>
                        </form>
                    </div>
                </div>
                <div id="edit-{{ aid }}" class="author-edit-panel">
                    <form method="POST">
                        <input type="hidden" name="action" value="edit">
                        <input type="hidden" name="author_display_name" value="{{ auth.author_display_name }}">
                        <div class="form-group"><label class="form-label" style="font-size:0.8rem;">Bio</label>
                            <textarea name="author_bio" class="form-control" rows="3">{{ auth.author_bio or \'\'  }}</textarea>
                        </div>
                        <div class="form-group"><label class="form-label" style="font-size:0.8rem;">Profile Image</label>
                            <select name="author_avatar_url" class="form-control">
                                <option value="">-- No image --</option>
                                {% for a in assets %}<option value="{{ a }}" {% if a == auth.author_avatar_url %}selected{% endif %}>{{ a }}</option>{% endfor %}
                            </select>
                        </div>
                        <div style="display:flex;gap:8px;">
                            <button type="submit" class="btn btn-primary btn-sm">Save</button>
                            <button type="button" class="btn btn-secondary btn-sm toggle-edit-btn" data-aid="{{ aid }}">Cancel</button>
                        </div>
                    </form>
                </div>
            </div>
            {% else %}<div class="empty-state"><h3>No authors yet</h3></div>{% endfor %}
        </div>
    </div>
    <script>
        // Event delegation via data-aid, not inline onclick string interpolation --
        // an author name containing a raw quote (e.g. O'Brien) previously broke
        // out of the onclick JS-string context once the browser HTML-decoded the
        // attribute value (HTML-escaping a name is not enough to make it safe
        // inside inline event-handler JS source; a data attribute read via
        // .dataset never has this problem, since it's never parsed as JS source).
        document.querySelectorAll(\'.toggle-edit-btn\').forEach(function(btn) {
            btn.addEventListener(\'click\', function() { toggleEdit(btn.dataset.aid); });
        });
        function toggleEdit(aid) {
            var el = document.getElementById(\'edit-\' + aid);
            if (el) el.style.display = el.style.display === \'block\' ? \'none\' : \'block\';
        }
    </script>'''
    return R(html, authors=authors, assets=assets, breadcrumbs=get_breadcrumbs(request.path), active_section='site')


# =============================================================================
# ROUTES — AD MANAGER (integrated from BEJSON_Ad_Manager.py)
# =============================================================================


def _strip_word_html(soup):
    """
    Remove Microsoft Word HTML artefacts from a BeautifulSoup tree.
    Targets: o:p tags, MsoXxx classes, mso- inline styles, Word section divs,
    empty paragraphs left by Word, and Word-generated footer boilerplate.
    """
    # Remove <o:p> tags (Word XML namespace leftovers)
    for tag in soup.find_all('o:p'):
        tag.decompose()

    # Remove any tag whose class list contains a "Mso" class
    for tag in soup.find_all(True):
        classes = tag.get('class', [])
        if any('Mso' in c for c in classes):
            tag.unwrap()  # keep inner text, drop the wrapper

    # Remove inline mso- styles but keep the element
    for tag in soup.find_all(True, style=True):
        style = tag.get('style', '')
        if 'mso-' in style:
            # Strip only the mso-* declarations, leave other styles
            cleaned = '; '.join(
                p for p in style.split(';') if 'mso-' not in p.lower()
            ).strip().strip(';')
            if cleaned:
                tag['style'] = cleaned
            else:
                del tag['style']

    # Remove Word section divs
    for tag in soup.find_all('div', id=re.compile(r'WordSection|Section\d', re.I)):
        tag.unwrap()
    for tag in soup.find_all('div', class_=re.compile(r'WordSection|Section\d', re.I)):
        tag.unwrap()

    # Remove footer / boilerplate elements that contain only Word/AI watermark text
    _WATERMARK_PATTERNS = re.compile(
        r'(microsoft\s+word|generated\s+by|created\s+with|renderer:|'
        r'claude\s+ai|gemini\s+ai|openai|chatgpt|copilot)',
        re.I
    )
    for tag in soup.find_all(['footer', 'div', 'p', 'span']):
        Tag_Preview_Text = tag.get_text(strip=True)
        # Only remove short boilerplate nodes (< 200 chars) matching watermark patterns
        if Tag_Preview_Text and len(Tag_Preview_Text) < 200 and _WATERMARK_PATTERNS.search(Tag_Preview_Text):
            # Make sure it doesn't contain meaningful body content
            if not tag.find(['h1', 'h2', 'h3', 'ul', 'ol', 'table']):
                tag.decompose()

    # Remove div.meta watermark containers
    for tag in soup.find_all('div', class_='meta'):
        tag.decompose()

    return soup


def extract_from_html(html_bytes):
    """
    Parse an HTML document and return (title, body_html, preview_text).
    Strips scripts, styles, Word artefacts, and AI watermarks.
    Requires beautifulsoup4; falls back to raw text extraction if unavailable.
    """
    if not _BS4_OK:
        Imported_Html_Raw_Bytes = html_bytes.decode('utf-8', errors='replace')
        title = re.search(r'<title[^>]*>(.*?)</title>', Imported_Html_Raw_Bytes, re.I | re.S)
        title = title.group(1).strip() if title else 'Imported Page'
        body  = re.sub(r'<[^>]+>', ' ', Imported_Html_Raw_Bytes)
        body  = re.sub(r'\s+', ' ', body).strip()
        return title, f'<p>{body[:50000]}</p>', body[:200]

    soup = BeautifulSoup(html_bytes, 'html.parser')

    # --- Title ---
    title_tag = soup.find('title')
    title = title_tag.get_text(strip=True) if title_tag else ''
    if not title:
        h1 = soup.find('h1')
        title = h1.get_text(strip=True) if h1 else 'Imported Page'

    # --- Body ---
    Parsed_Body_Tag = soup.find('body') or soup

    # Remove noise elements
    for tag in Parsed_Body_Tag.find_all(['script', 'style', 'noscript', 'link', 'meta']):
        tag.decompose()

    # Strip Word HTML artefacts + AI watermarks
    Cleaned_Body_Html = _strip_word_html(Parsed_Body_Tag)

    # Ensure all tables are enclosed in horizontal scroll containers (zero page widening)
    for table_tag in Cleaned_Body_Html.find_all("table"):
        parent_tag = table_tag.parent
        if not (parent_tag and parent_tag.name == "div" and any(cls in parent_tag.get("class", []) for cls in ("table-container", "table-responsive", "table-scroll-container"))):
            wrapper_div = soup.new_tag("div", **{"class": "table-container"})
            table_tag.wrap(wrapper_div)

    body_html = Cleaned_Body_Html.decode_contents().strip()

    # Preview text
    preview = re.sub(r'\s+', ' ', Cleaned_Body_Html.get_text(separator=' ', strip=True))[:200]

    return title, body_html, preview


def extract_from_import_file(filename, raw_bytes):
    """
    Extract (title, body_html, preview_text, markdown_body, file_kind) from either
    a Markdown (.md/.markdown) or HTML (.html/.htm) file.
    """
    lower_name = (filename or '').lower()
    if lower_name.endswith(('.md', '.markdown')):
        md_text = raw_bytes.decode('utf-8', errors='replace')
        stem = os.path.splitext(os.path.basename(filename))[0]
        fallback_title = stem.replace('_', ' ').replace('-', ' ').title() or 'Imported Article'
        parsed = convert_markdown_to_cms_article(md_text, fallback_title)
        wrapped_html = f'<article class="bejson-cms-article">\n{parsed["html_body"]}\n</article>'
        preview_text = parsed.get('excerpt') or parsed.get('title') or ''
        return parsed['title'], wrapped_html, preview_text[:200], md_text, 'markdown'
    else:
        title, body_html, preview_text = extract_from_html(raw_bytes)
        return title, body_html, preview_text, '', 'html'


def _create_import_page(title, category, body_html, author='', sync_count=True, markdown_body='', page_type='page'):
    """Register a new PageRecord in the master DB and write the page content file.

    sync_count: pass False when calling this in a loop over multiple files;
    callers must then call db.sync_manifest_count("PageRecord") once after
    the loop finishes to avoid one manifest fsync per imported page.
    """
    _t0 = time.perf_counter()
    new_uuid = str(uuid.uuid4())
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    normalized_type = page_type if page_type in ('page', 'blog', 'article') else 'page'

    db.mount()
    _t_add0 = time.perf_counter()
    db.add_record("PageRecord", {
        "page_uuid":    new_uuid,
        "page_title":   title,
        "page_slug":    slug,
        "page_cat_name": category,
        "page_type":    normalized_type,
        "page_created_at":   datetime.now().strftime("%Y-%m-%d"),
        "page_external_url": None,
        "page_author_name":   author,
        "page_featured_img": DEFAULT_FEATURED_IMAGE,
        "page_is_standalone_flag": (normalized_type == "page"),
    }, sync_count=sync_count)
    _t_add1 = time.perf_counter()
    

    # Write per-page content file
    pfile = os.path.join(PAGES_DB_DIR, f"{new_uuid}.json")
    # Create content file using standardized BEJSON 104db structure
    content_doc = {
        "Format": "BEJSON", "Format_Version": "104db", "Format_Creator": "Elton Boehnen",
        "Records_Type": ["PageMeta", "Content"],
        "Fields": [
            {"name": "Record_Type_Parent", "type": "string"},
            {"name": "meta_title", "type": "string", "Record_Type_Parent": "PageMeta"},
            {"name": "html_body", "type": "string", "Record_Type_Parent": "Content"},
            {"name": "markdown_body", "type": "string", "Record_Type_Parent": "Content"},
            {"name": "source_code", "type": "string", "Record_Type_Parent": "Content"}
        ],
        "Values": [
            ["PageMeta", title, None, None, None],
            ["Content", None, body_html, markdown_body or "", ""]
        ]
    }
    _t_file0 = time.perf_counter()
    tmp = pfile + ".tmp"
    with open(tmp, "w") as f:
        json.dump(content_doc, f, indent=2)
    os.replace(tmp, pfile)  # atomic write, matching cms-manage.py's pattern
    _t_file1 = time.perf_counter()
    logging.debug(
        f"[IMPORT] _create_import_page title={title!r} type={normalized_type} sync_count={sync_count} "
        f"add_record_ms={(_t_add1-_t_add0)*1000:.1f} content_file_write_ms={(_t_file1-_t_file0)*1000:.1f} "
        f"total_ms={(time.perf_counter()-_t0)*1000:.1f}"
    )
    return new_uuid


@content_cube.route('/import', methods=['GET'])
def import_index():
    db.mount()
    cats = db.get_records("Category")
    authors = db.get_records("AuthorProfile")

    if not cats:
        cats = [{'cat_name': 'Uncategorized', 'cat_slug': 'uncategorized'}]

    bs4_warn = '' if _BS4_OK else '''
    <div class="alert alert-error" style="margin-bottom:20px;">
      ⚠ <strong>beautifulsoup4</strong> is not installed.
      Install it with <code>pip install beautifulsoup4</code> for full HTML parsing.
      Markdown (.md) and basic HTML extraction will still work without it.
    </div>'''

    html = f'''
    {bs4_warn}
    <div class="page-header"><h1>HTML &amp; Markdown Import</h1>
    <p>Upload Markdown (<code>.md</code>) or HTML (<code>.html</code>) drops and import them as native CMS articles or pages. Markdown files are converted to style-agnostic <code>&lt;article class="bejson-cms-article"&gt;</code> HTML with responsive tables, callouts, and code blocks.</p></div>
    <form action="/import/preview" method="POST" enctype="multipart/form-data">
      <div class="card">
        <div class="card-header"><span class="card-title">📂 Select HTML or Markdown Files</span></div>
        <div id="dropZone" onclick="document.getElementById('fileInput').click()"
             style="border:2px dashed var(--border);border-radius:8px;padding:48px 24px;text-align:center;cursor:pointer;transition:.2s;"
             ondragover="event.preventDefault();this.style.borderColor='var(--accent)'"
             ondragleave="this.style.borderColor='var(--border)'"
             ondrop="event.preventDefault();this.style.borderColor='var(--border)';document.getElementById('fileInput').files=event.dataTransfer.files;showFiles(document.getElementById('fileInput'))">
          <div style="font-size:2.5rem;margin-bottom:12px;">📄</div>
          <p style="color:var(--text-secondary);margin-bottom:14px;">Click to browse or drag &amp; drop <code>.md</code>, <code>.markdown</code>, <code>.html</code>, or <code>.htm</code> files</p>
          <input type="file" id="fileInput" name="html_files" multiple accept=".html,.htm,.md,.markdown"
                 style="display:none" onchange="showFiles(this)">
          <span class="btn btn-secondary">Browse Files</span>
        </div>
        <div id="fileList" style="margin-top:16px;"></div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">⚙️ Import Settings</span></div>
        <div class="grid-2" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;">
          <div class="form-group">
            <label class="form-label">Target Category *</label>
            <select name="category" class="form-control" required>
              <option value="" disabled selected>-- Select Target Category --</option>
              {"".join(f'<option value="{c["cat_name"]}">{c["cat_name"]}</option>' for c in cats)}
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Author (optional)</label>
            <select name="author" class="form-control"><option value="">-- Select author --</option>
              {"".join(f'<option value="{_html_escape.escape(a["author_display_name"])}">{_html_escape.escape(a["author_display_name"])}</option>' for a in authors)}
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Page Type</label>
            <select name="page_type" class="form-control">
              <option value="blog" selected>blog (Article / Post)</option>
              <option value="article">article</option>
              <option value="page">page (Standalone Page)</option>
            </select>
          </div>
        </div>
        <div class="form-group" style="display:flex;align-items:center;gap:12px;margin-top:16px;">
          <input type="checkbox" name="skip_preview" id="skip_preview" style="width:20px;height:20px;accent-color:var(--accent);">
          <label for="skip_preview" style="margin:0;font-size:.95rem;font-weight:700;">Direct Import (Skip Preview)</label>
        </div>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;">
        <button type="submit" class="btn btn-primary">🔍 Preview &amp; Review →</button>
      </div>
    </form>
    <script>
    function showFiles(inp) {{
      const list = document.getElementById('fileList');
      list.innerHTML = '';
      if (!inp.files.length) return;
      const hdr = document.createElement('p');
      hdr.style = 'font-size:.85rem;color:var(--text-secondary);margin-bottom:8px;font-weight:600;';
      hdr.textContent = inp.files.length + ' file(s) selected:';
      list.appendChild(hdr);
      for (const f of inp.files) {{
        const isMd = f.name.toLowerCase().endsWith('.md') || f.name.toLowerCase().endsWith('.markdown');
        const badge = isMd ? '<span class="badge" style="background:var(--accent);color:#fff;padding:2px 6px;border-radius:4px;font-size:0.7rem;margin-left:8px;">MD</span>' : '<span class="badge" style="background:var(--border);color:var(--text-primary);padding:2px 6px;border-radius:4px;font-size:0.7rem;margin-left:8px;">HTML</span>';
        const item = document.createElement('div');
        item.style = 'background:var(--bg-secondary);border:1px solid var(--border);border-radius:8px;padding:14px 18px;margin-bottom:10px;display:flex;align-items:center;gap:14px;';
        item.innerHTML = '<span style="font-size:1.4rem;">' + (isMd ? '📝' : '📄') + '</span><div><div style="font-weight:600;font-size:.9rem;">' + f.name + badge + '</div><div style="font-size:.78rem;color:var(--text-secondary);">' + (f.size/1024).toFixed(1) + ' KB</div></div>';
        list.appendChild(item);
      }}
    }}
    </script>'''
    return R(html, breadcrumbs=get_breadcrumbs(request.path), active_section='content')


@content_cube.route('/import/preview', methods=['POST'])
def import_preview():
    files    = request.files.getlist('html_files')
    category = request.form.get('category', '').strip()
    author   = request.form.get('author', '').strip()
    page_type = request.form.get('page_type', 'blog').strip() or 'blog'
    skip_preview = request.form.get('skip_preview') == 'on'

    if not category:
        flash('Target category is required for import.', 'error')
        return redirect('/import')

    if not files or not files[0].filename:
        flash('Please select at least one HTML or Markdown file.', 'error')
        return redirect('/import')

    if skip_preview:
        success_count = 0
        _batch_t0 = time.perf_counter()
        logging.debug(f"[IMPORT] file_import skip_preview START file_count={len(files)}")
        for f in files:
            if not f.filename: continue
            _file_t0 = time.perf_counter()
            try:
                _t_read0 = time.perf_counter()
                raw = f.read()
                _t_read1 = time.perf_counter()
                title, body_html, _, md_body, _ = extract_from_import_file(f.filename, raw)
                _t_extract1 = time.perf_counter()
                _create_import_page(title, category, body_html, author, sync_count=False, markdown_body=md_body, page_type=page_type)
                success_count += 1
                logging.debug(
                    f"[IMPORT] file_import FILE filename={f.filename} "
                    f"read_ms={(_t_read1-_t_read0)*1000:.1f} extract_ms={(_t_extract1-_t_read1)*1000:.1f} "
                    f"file_total_ms={(time.perf_counter()-_file_t0)*1000:.1f}"
                )
            except Exception as e:
                flash(f'Error importing {f.filename}: {e}', 'error')
                logging.debug(f"[IMPORT] file_import FILE ERROR filename={f.filename} "
                              f"file_total_ms={(time.perf_counter()-_file_t0)*1000:.1f} error={e}")
        if success_count > 0:
            _t_sync0 = time.perf_counter()
            db.sync_manifest_count("PageRecord")
            logging.debug(f"[IMPORT] file_import final sync_manifest_count_ms={(time.perf_counter()-_t_sync0)*1000:.1f}")
        logging.debug(f"[IMPORT] file_import skip_preview END success={success_count} "
                      f"batch_total_ms={(time.perf_counter()-_batch_t0)*1000:.1f}")
        flash(f'Successfully imported {success_count} page(s).', 'success')
        return redirect('/pages')

    previews = []
    for f in files:
        if not f.filename:
            continue
        fname = secure_filename(f.filename)
        if not fname.lower().endswith(('.html', '.htm', '.md', '.markdown')):
            flash(f'{fname} skipped — not an HTML or Markdown file.', 'error')
            continue
        try:
            raw = f.read()
            # Cap BS4 parsing at 2 MB — larger files freeze Flask's single
            # thread on Android; the full bytes are still saved to disk.
            _MAX_PARSE = 2 * 1024 * 1024
            parse_bytes = raw[:_MAX_PARSE]
            title, _, preview_text, _, file_kind = extract_from_import_file(fname, parse_bytes)
            tmp_path = os.path.join(UPLOAD_TMP, fname)
            with open(tmp_path, 'wb') as fh:
                fh.write(raw)
            previews.append({
                'fname':   fname,
                'title':   title,
                'preview': preview_text,
                'size':    f'{len(raw)/1024:.1f} KB',
                'kind':    file_kind,
            })
        except Exception as e:
            flash(f'Could not parse {f.filename}: {e}', 'error')

    if not previews:
        flash('No valid HTML or Markdown files found.', 'error')
        return redirect('/import')

    rows = ''
    for p in previews:
        icon = '📝' if p.get('kind') == 'markdown' else '📄'
        rows += f'''
        <div class="card">
          <div class="card-header"><span class="card-title">{icon} {p["fname"]} <span style="font-weight:400;font-size:.8rem;color:var(--text-secondary);">({p["size"]} &middot; {p.get("kind", "html").upper()})</span></span></div>
          <input type="hidden" name="fnames" value="{p["fname"]}">
          <div class="grid-2" style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
            <div class="form-group">
              <label class="form-label">Page Title</label>
              <input type="text" name="title_{p["fname"]}" value="{_html_escape.escape(p['title'])}" class="form-control">
            </div>
            <div class="form-group" style="display:flex;align-items:center;gap:12px;padding-top:28px;">
              <input type="checkbox" name="include_{p["fname"]}" id="inc_{p["fname"]}"
                     style="width:20px;height:20px;accent-color:var(--accent);" checked>
              <label for="inc_{p["fname"]}" style="margin:0;font-size:.95rem;">Include this file</label>
            </div>
          </div>
          <div class="form-group">
            <label class="form-label">Content Preview</label>
            <div style="background:var(--bg-secondary);border:1px solid var(--border);border-radius:8px;padding:12px 16px;font-size:.82rem;color:var(--text-secondary);line-height:1.6;font-style:italic;">{_html_escape.escape(p["preview"])}{"…" if len(p["preview"])==200 else ""}</div>
          </div>
        </div>'''

    html = f'''
    <div class="page-header"><h1>Review Import</h1>
    <p>Confirm titles and check which files to import, then click Import All.</p></div>
    <form action="/import/confirm" method="POST">
      <input type="hidden" name="category"  value="{_html_escape.escape(category)}">
      <input type="hidden" name="author"    value="{_html_escape.escape(author)}">
      <input type="hidden" name="page_type" value="{_html_escape.escape(page_type)}">
      {rows}
      <div class="card" style="padding:16px 22px;">
        <span style="color:var(--text-secondary);font-size:.85rem;">Category:</span>
        <strong style="margin-left:8px;">{_html_escape.escape(category)}</strong>
        &nbsp;&nbsp;
        <span style="color:var(--text-secondary);font-size:.85rem;">Author:</span>
        <strong style="margin-left:8px;">{_html_escape.escape(author) if author else "—"}</strong>
        &nbsp;&nbsp;
        <span style="color:var(--text-secondary);font-size:.85rem;">Type:</span>
        <strong style="margin-left:8px;">{_html_escape.escape(page_type)}</strong>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:4px;">
        <button type="submit" class="btn btn-primary">🚀 Import to CMS</button>
        <a href="/import" class="btn btn-secondary">← Start Over</a>
      </div>
    </form>'''
    return R(html, breadcrumbs=get_breadcrumbs(request.path), active_section='content')


@content_cube.route('/import/confirm', methods=['POST'])
def import_confirm():
    category  = request.form.get('category', 'Uncategorized')
    author    = request.form.get('author', '').strip()
    page_type = request.form.get('page_type', 'blog').strip() or 'blog'
    fnames    = request.form.getlist('fnames')

    import_queue = []
    for fname in fnames:
        if not request.form.get(f'include_{fname}'):
            continue
        title = request.form.get(f'title_{fname}', '').strip() or fname
        import_queue.append({'fname': fname, 'title': title})

    if not import_queue:
        flash('No files selected for import.', 'error')
        return redirect('/import')

    html = f'''
    <div class="page-header"><h1>Processing Import Queue</h1>
    <p>Please wait while your files are being imported into the CMS.</p></div>
    
    <div class="card" style="padding:30px;">
        <div id="import-progress-container">
            <div style="display:flex;justify-content:space-between;margin-bottom:10px;">
                <span id="progress-status" style="font-weight:700;color:var(--accent);">Initializing...</span>
                <span id="progress-percent">0%</span>
            </div>
            <div style="height:10px;background:var(--bg-secondary);border-radius:5px;overflow:hidden;margin-bottom:25px;border:1px solid var(--border);">
                <div id="progress-bar" style="height:100%;width:0%;background:var(--accent);transition:width 0.3s ease;"></div>
            </div>
        </div>
        
        <div id="import-log" style="background:var(--bg-secondary);border:1px solid var(--border);border-radius:8px;padding:15px;max-height:300px;overflow-y:auto;font-family:monospace;font-size:.85rem;line-height:1.6;">
            <!-- Process logs will appear here -->
        </div>
        
        <div id="completion-actions" style="display:none;margin-top:30px;gap:10px;">
            <a href="/pages" class="btn btn-primary">View All Pages ↗</a>
            <a href="/import" class="btn btn-secondary">Import More</a>
        </div>
    </div>

    <script>
    const queue = {json.dumps(import_queue).replace('</', '<\\/')};
    const category = "{_html_escape.escape(category)}";
    const author = "{_html_escape.escape(author)}";
    const page_type = "{_html_escape.escape(page_type)}";
    const log = document.getElementById('import-log');
    const bar = document.getElementById('progress-bar');
    const pct = document.getElementById('progress-percent');
    const status = document.getElementById('progress-status');
    const actions = document.getElementById('completion-actions');

    async function processQueue() {{
        let successCount = 0;
        let failCount = 0;
        
        for(let i=0; i < queue.length; i++) {{
            const item = queue[i];
            const p = Math.round(((i) / queue.length) * 100);
            bar.style.width = p + "%";
            pct.textContent = p + "%";
            status.textContent = "Importing: " + item.title + "...";
            
            const entry = document.createElement('div');
            entry.style.marginBottom = "5px";
            entry.innerHTML = `<span style="color:var(--accent)">[PROCESS]</span> Attempting to import "${{item.title}}"...`;
            log.appendChild(entry);
            log.scrollTop = log.scrollHeight;

            try {{
                const res = await fetch('/api/import/process_item', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        fname: item.fname,
                        title: item.title,
                        category: category,
                        author: author,
                        page_type: page_type
                    }})
                }});
                const data = await res.json();
                
                if(data.success) {{
                    successCount++;
                    entry.innerHTML = `<span style="color:#10b981">[SUCCESS]</span> Imported "${{item.title}}" successfully.`;
                }} else {{
                    failCount++;
                    entry.innerHTML = `<span style="color:#ef4444">[ERROR]</span> Failed to import "${{item.title}}": ${{data.error}}`;
                }}
            }} catch(e) {{
                failCount++;
                entry.innerHTML = `<span style="color:#ef4444">[CRITICAL]</span> Connection error importing "${{item.title}}": ${{e}}`;
            }}
        }}
        
        bar.style.width = "100%";
        pct.textContent = "100%";
        status.textContent = "Import Complete!";
        status.style.color = "#10b981";
        
        const finalEntry = document.createElement('div');
        finalEntry.style.marginTop = "15px";
        finalEntry.style.fontWeight = "bold";
        finalEntry.style.borderTop = "1px solid var(--border)";
        finalEntry.style.paddingTop = "10px";
        finalEntry.innerHTML = `FINISHED: ${{successCount}} successful, ${{failCount}} failed.`;
        log.appendChild(finalEntry);
        log.scrollTop = log.scrollHeight;
        
        actions.style.display = "flex";
    }}

    document.addEventListener('DOMContentLoaded', processQueue);
    </script>
    '''
    return R(html, breadcrumbs=get_breadcrumbs(request.path), active_section='content')


@content_cube.route('/api/import/process_item', methods=['POST'])
@require_auth
def api_import_process_item():
    Parsed_Request_Body = request.json or {}
    fname = Parsed_Request_Body.get('fname')
    title = Parsed_Request_Body.get('title')
    category = Parsed_Request_Body.get('category')
    author = Parsed_Request_Body.get('author')
    page_type = Parsed_Request_Body.get('page_type', 'blog')

    tmp_path = os.path.join(UPLOAD_TMP, fname)
    if not category:
        return jsonify({"success": False, "error": "Category is missing"})
    if not os.path.exists(tmp_path):
        return jsonify({"success": False, "error": "Temporary file missing"})

    try:
        with open(tmp_path, 'rb') as fh:
            raw = fh.read()
        extracted_title, body_html, _, md_body, _ = extract_from_import_file(fname, raw)
        final_title = title or extracted_title
        del raw  # release the full file bytes promptly
        new_uuid = _create_import_page(final_title, category, body_html, author, markdown_body=md_body, page_type=page_type)
        os.remove(tmp_path)
        gc.collect()
        return jsonify({"success": True, "uuid": new_uuid})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# =============================================================================
# BKS-1 STANDARDIZED 4-PART BLOG POST JOB SYSTEM (/jobs & /api/bks/*)
# =============================================================================

@content_cube.route('/jobs')
@require_auth
def bks_jobs_studio():
    db.mount()
    pages = [p for p in db.get_records("PageRecord") if p.get("page_type") != "external_link"]
    categories = db.get_records("Category")
    authors = db.get_records("AuthorProfile")
    html = '''
    <div class="page-header">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
            <div>
                <h1>AI Writer</h1>
                <p>Plan and execute 4-part technical publications with 48k Context Bubble, Author Persona Precedence, and seamless CMS publishing</p>
            </div>
            <span id="bks_job_badge" class="badge badge-page" style="font-size:0.8rem;padding:6px 12px;">No Active Job</span>
        </div>
    </div>

    <div class="card" style="margin-bottom:20px;">
        <div class="grid grid-2" style="gap:16px;margin-bottom:16px;">
            <div class="form-group" style="margin-bottom:0;">
                <label class="form-label">Saved BKS-1 Blog Post Jobs</label>
                <div style="display:flex;gap:8px;">
                    <select id="bks_job_select" class="form-control" onchange="if(this.value) loadBksJob(this.value)">
                        <option value="">-- New 4-Part Blog Post Job --</option>
                    </select>
                    <button type="button" class="btn btn-secondary btn-sm" onclick="refreshBksBootstrap()">&#8635;</button>
                </div>
            </div>
            <div class="form-group" style="margin-bottom:0;">
                <label class="form-label">Target Post to Overwrite on Approve</label>
                <select id="bks_target_page" class="form-control">
                    <option value="">-- Create New CMS Post on Approve --</option>
                    {% for p in pages %}<option value="{{ p.page_uuid }}">[Overwrite] {{ p.page_title }} ({{ p.page_cat_name or 'Uncategorized' }})</option>{% endfor %}
                </select>
            </div>
        </div>

        <div class="grid grid-3" style="gap:16px;margin-bottom:16px;">
            <div class="form-group" style="margin-bottom:0;">
                <label class="form-label">Blog Post Job Template (BookType)</label>
                <select id="bks_template_select" class="form-control"></select>
            </div>
            <div class="form-group" style="margin-bottom:0;">
                <label class="form-label">AI Provider (CLI_AI 48)</label>
                <select id="bks_provider_select" class="form-control" onchange="syncBksModelOptions()"></select>
            </div>
            <div class="form-group" style="margin-bottom:0;">
                <label class="form-label">AI Model</label>
                <select id="bks_model_select" class="form-control"></select>
            </div>
        </div>

        <div class="grid grid-3" style="gap:16px;margin-bottom:16px;">
            <div class="form-group" style="margin-bottom:0;">
                <label class="form-label">Blog Post Title</label>
                <input type="text" id="bks_title" class="form-control" placeholder="e.g. Zero-Dependency Local-First Architectures with BEJSON 104">
            </div>
            <div class="form-group" style="margin-bottom:0;">
                <label class="form-label">Category</label>
                <select id="bks_category" class="form-control">
                    {% for c in categories %}<option value="{{ c.cat_name }}">{{ c.cat_name }}</option>{% endfor %}
                </select>
            </div>
            <div class="form-group" style="margin-bottom:0;">
                <label class="form-label">Author / Voice Persona</label>
                <select id="bks_author" class="form-control">
                    {% for a in authors %}<option value="{{ a.author_display_name }}">{{ a.author_display_name }}</option>{% endfor %}
                </select>
            </div>
        </div>

        <div class="form-group" style="margin-bottom:16px;">
            <label class="form-label">Topic / Thesis / Architectural Brief</label>
            <textarea id="bks_topic" class="form-control" style="min-height:100px;" placeholder="Describe the blog post topic, key arguments, code examples, and target audience..."></textarea>
        </div>

        <details id="bks_context_bubble_details" open style="margin-bottom:16px;border:1px solid var(--border);border-radius:8px;padding:12px 14px;background:var(--bg-secondary);">
            <summary style="cursor:pointer;list-style:none;outline:none;user-select:none;">
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
                    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
                        <span class="badge badge-page">CONTEXT BUBBLE</span>
                        <strong style="font-size:0.9rem;">Pre-Prompt Context Bubble Files (Study &amp; Learn Silently)</strong>
                    </div>
                    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                        <span id="bks_ctx_badge" style="font-family:monospace;font-size:0.78rem;color:var(--text-secondary);">0 ACTIVE | 0 CHARS</span>
                        <button type="button" class="btn btn-secondary btn-sm" onclick="event.stopPropagation();openBksContextFilePicker()">+ Select Context Files</button>
                    </div>
                </div>
            </summary>
            <div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border);">
                <div style="font-size:0.78rem;color:var(--text-secondary);margin-bottom:10px;line-height:1.5;overflow-wrap:break-word;">
                    <strong>Injected Directive:</strong> <span id="bks_ctx_directive_text">BACKGROUND -- study and learn from this reference material and absorb it silently. Never reference, mention, acknowledge, or admit that this context exists; if it influences anything you produce, write strictly in your own words, never as a copy, quote, or citation of this material.</span>
                </div>
                <div id="bks_ctx_files_list" style="display:flex;flex-direction:column;gap:8px;margin-bottom:10px;"></div>
                <details style="margin-top:8px;">
                    <summary style="cursor:pointer;font-size:0.78rem;font-weight:700;color:var(--text-secondary);user-select:none;">Preview Assembled Context Bubble Block</summary>
                    <div style="margin-top:8px;">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                            <span style="font-size:0.75rem;color:var(--text-secondary);">Prepended before prompt on Plan &amp; Part execution</span>
                            <div style="display:flex;gap:6px;">
                                <button type="button" class="btn btn-secondary btn-sm" style="font-size:0.7rem;padding:3px 8px;" onclick="selectAllText('bks_ctx_preview_box')">Select All</button>
                                <button type="button" class="btn btn-secondary btn-sm" style="font-size:0.7rem;padding:3px 8px;" onclick="copyText('bks_ctx_preview_box', this)">Copy</button>
                            </div>
                        </div>
                        <textarea id="bks_ctx_preview_box" class="form-control" readonly style="min-height:110px;font-family:monospace;font-size:0.78rem;white-space:pre-wrap;word-wrap:break-word;overflow-wrap:break-word;" placeholder="No active context files selected."></textarea>
                    </div>
                </details>
            </div>
        </details>

        <div class="toolbar-row" style="display:flex;flex-direction:row;flex-wrap:nowrap;overflow-x:auto;-webkit-overflow-scrolling:touch;gap:10px;align-items:center;padding-bottom:6px;margin-bottom:4px;scrollbar-width:thin;">
            <button type="button" class="btn btn-primary" style="flex-shrink:0;white-space:nowrap;" onclick="generateBksPlan()">1. Generate Plan</button>
            <button type="button" class="btn btn-secondary" style="flex-shrink:0;white-space:nowrap;" onclick="saveBksPlanEdits()">Save Plan Edits</button>
            <button type="button" class="btn btn-primary" style="flex-shrink:0;white-space:nowrap;" onclick="runNextBksPart()">2a. Run Next Part</button>
            <button type="button" class="btn btn-primary" style="flex-shrink:0;white-space:nowrap;" onclick="runAllBksParts()">2b. Run All &amp; Merge</button>
            <button type="button" class="btn btn-secondary" style="flex-shrink:0;white-space:nowrap;" onclick="mergeBksParts()">Re-Merge Parts</button>
            <button type="button" class="btn btn-primary" style="background:#059669;border-color:#059669;flex-shrink:0;white-space:nowrap;" onclick="approveAndOverwriteTargetPost()">3. Approve &amp; Overwrite</button>
            <span id="bks_status_msg" style="margin-left:auto;font-family:monospace;font-size:0.85rem;color:var(--text-secondary);flex-shrink:0;white-space:nowrap;">READY</span>
        </div>
    </div>

    <div id="bks_parts_container" style="display:flex;flex-direction:column;gap:14px;margin-bottom:24px;"></div>

    <div id="bks_merged_panel" class="card" style="display:none;">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:16px;">
            <div>
                <h3 style="margin-bottom:4px;">Merged 4-Part Blog Post Preview</h3>
                <p style="color:var(--text-secondary);font-size:0.85rem;margin:0;">Unified 4-part Markdown + BEJSON CMS Article HTML ready to overwrite target post on approval</p>
            </div>
            <div style="display:flex;gap:10px;">
                <button type="button" class="btn btn-primary" style="background:#059669;border-color:#059669;" onclick="approveAndOverwriteTargetPost()">&#10003; Approve &amp; Overwrite Target Post</button>
            </div>
        </div>
        <div class="grid grid-2" style="gap:16px;">
            <div>
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                    <label class="form-label" style="margin:0;">Merged 4-Part Markdown</label>
                    <div style="display:flex;gap:6px;">
                        <button type="button" class="btn btn-secondary btn-sm" onclick="selectAllText('bks_merged_md')">Select All</button>
                        <button type="button" class="btn btn-secondary btn-sm" onclick="copyText('bks_merged_md', this)">Copy</button>
                    </div>
                </div>
                <textarea id="bks_merged_md" class="form-control" style="min-height:320px;font-family:monospace;font-size:0.82rem;white-space:pre-wrap;word-wrap:break-word;overflow-wrap:break-word;"></textarea>
            </div>
            <div>
                <label class="form-label">Rendered CMS Article HTML Preview</label>
                <div id="bks_merged_html_preview" class="table-container" style="min-height:320px;max-height:480px;overflow-y:auto;overflow-x:auto;max-width:100%;background:var(--bg-secondary);border:1px solid var(--border);border-radius:8px;padding:16px;white-space:normal;overflow-wrap:break-word;"></div>
            </div>
        </div>
    </div>

    <script>
    let currentBksJobSlug = '';
    let currentBksDetail = null;
    let currentPlan = [];
    let bksProviderModels = {};

    async function refreshBksBootstrap() {
        const res = await fetch('/api/bks/bootstrap');
        const data = await res.json();
        if(!data.ok) return;

        const tplSel = document.getElementById('bks_template_select');
        const prevTpl = tplSel.value || 'blog_post_4part';
        tplSel.innerHTML = '';
        (data.templates || []).forEach(t => {
            const opt = document.createElement('option');
            opt.value = t.type_id;
            opt.innerText = `${t.display_name} (${t.default_chapter_count} parts, ~${t.target_words_per_chapter}w/part)`;
            tplSel.appendChild(opt);
        });
        if([...tplSel.options].some(o => o.value === prevTpl)) tplSel.value = prevTpl;

        bksProviderModels = (data.ai && data.ai.models_by_provider) ? data.ai.models_by_provider : {};
        const provSel = document.getElementById('bks_provider_select');
        const prevProv = provSel.value || (data.ai && data.ai.default_provider) || 'geminirest';
        provSel.innerHTML = '';
        ((data.ai && data.ai.providers) || ['geminirest', 'gemini', 'groq', 'openrouter', 'openai']).forEach(p => {
            const opt = document.createElement('option');
            opt.value = p;
            opt.innerText = p.toUpperCase();
            provSel.appendChild(opt);
        });
        provSel.value = prevProv;
        syncBksModelOptions((data.ai && data.ai.default_model) || '');

        const jobSel = document.getElementById('bks_job_select');
        const prevJob = currentBksJobSlug || jobSel.value;
        jobSel.innerHTML = '<option value="">-- New 4-Part Blog Post Job --</option>';
        (data.jobs || []).forEach(j => {
            const opt = document.createElement('option');
            opt.value = j.job_slug;
            opt.innerText = `[${j.status.toUpperCase()}] ${j.job_name} (${j.accepted_parts || 0}/${j.chapter_count || 4} parts)`;
            jobSel.appendChild(opt);
        });
        if(prevJob && [...jobSel.options].some(o => o.value === prevJob)) jobSel.value = prevJob;

        if(data.context_bubble) {
            renderBksContextBubble(data.context_bubble);
        }

        const authorSel = document.getElementById('bks_author');
        if(authorSel && !authorSel._bksListenerAttached) {
            authorSel._bksListenerAttached = true;
            authorSel.addEventListener('change', async function() {
                try {
                    const res = await fetch('/api/bks/context_files?author=' + encodeURIComponent(this.value));
                    const d = await res.json();
                    if(d.ok) renderBksContextBubble(d);
                } catch(e) {}
            });
        }
    }

    function renderBksContextBubble(ctxState) {
        if(!ctxState) return;
        const badge = document.getElementById('bks_ctx_badge');
        if(badge) {
            const usedTok = ctxState.used_tokens || 0;
            const maxTok = ctxState.max_context_tokens || 48000;
            const activeFiles = ctxState.enabled_count || 0;
            badge.innerText = `48k Max Tokens | 15% Author Persona (~7.2k tok) | 85% Context Files (~40.8k tok) | ${activeFiles} Active (${usedTok}/${maxTok} tok)`;
        }
        const dirEl = document.getElementById('bks_ctx_directive_text');
        if(dirEl) {
            dirEl.innerHTML = `<strong>Context Files (85%):</strong> ${ctxState.directive || ''}<br><strong style="margin-top:4px;display:inline-block;">Author Persona & Directives (15%):</strong> ${ctxState.author_directive || 'Author persona and writing instructions strictly override any contradictory profile instructions.'}`;
        }
        const prevBox = document.getElementById('bks_ctx_preview_box');
        if(prevBox) {
            prevBox.value = ctxState.bubble_preview || ctxState.bubble_text || '';
        }
        const listEl = document.getElementById('bks_ctx_files_list');
        if(!listEl) return;
        listEl.innerHTML = '';
        const files = ctxState.files || [];
        if(!files.length) {
            listEl.innerHTML = '<div style="font-size:0.8rem;color:var(--text-secondary);padding:6px 0;">No context files imported yet. Click "+ Select Context Files" to pick reference files from device storage.</div>';
            return;
        }
        files.forEach(f => {
            const row = document.createElement('div');
            row.style = 'display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;padding:8px 12px;background:var(--bg-card);border:1px solid var(--border);border-radius:6px;';
            const left = document.createElement('label');
            left.style = 'display:flex;align-items:center;gap:10px;cursor:pointer;flex:1;min-width:180px;margin:0;overflow-wrap:break-word;';
            const chk = document.createElement('input');
            chk.type = 'checkbox';
            chk.checked = !!f.enabled;
            chk.style = 'width:18px;height:18px;accent-color:var(--accent);flex-shrink:0;';
            chk.onchange = () => toggleBksContextFile(f.file_id);
            const nameSpan = document.createElement('span');
            nameSpan.style = 'font-weight:600;font-size:0.85rem;word-break:break-word;';
            nameSpan.innerText = f.filename;
            left.appendChild(chk);
            left.appendChild(nameSpan);

            const right = document.createElement('div');
            right.style = 'display:flex;align-items:center;gap:8px;flex-shrink:0;';
            const meta = document.createElement('span');
            meta.style = 'font-family:monospace;font-size:0.75rem;color:var(--text-secondary);';
            meta.innerText = `${f.char_count || 0} chars`;
            const delBtn = document.createElement('button');
            delBtn.type = 'button';
            delBtn.className = 'btn btn-danger btn-sm';
            delBtn.style = 'font-size:0.72rem;padding:3px 8px;';
            delBtn.innerText = 'Remove';
            delBtn.onclick = () => deleteBksContextFile(f.file_id);
            right.appendChild(meta);
            right.appendChild(delBtn);

            row.appendChild(left);
            row.appendChild(right);
            listEl.appendChild(row);
        });
    }

    async function openBksContextFilePicker() {
        if(!window.CMSFilePicker) {
            alert('File picker script is still loading. Please try again.');
            return;
        }
        const picked = await window.CMSFilePicker.open({
            kind: 'code',
            multiple: true,
            title: 'Select Context Bubble Reference Files',
            subtitle: 'Select .md, .txt, .bejson, .json, .py, .js, or .html files to study silently before writing',
            confirmLabel: 'Import to Context Bubble'
        });
        if(!picked || !picked.paths || !picked.paths.length) return;
        const curAuthor = (document.getElementById('bks_author') || {}).value || '';
        document.getElementById('bks_status_msg').innerText = 'IMPORTING CONTEXT FILES...';
        const res = await fetch('/api/bks/context_files/import_pick', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({paths: picked.paths, author: curAuthor})
        });
        const data = await res.json();
        if(data.ok) {
            renderBksContextBubble(data);
            document.getElementById('bks_status_msg').innerText = `IMPORTED ${(data.imported || []).length} CONTEXT FILE(S)`;
        } else {
            alert('Context import failed: ' + (data.error || 'Unknown error'));
        }
    }

    async function toggleBksContextFile(fileId) {
        const curAuthor = (document.getElementById('bks_author') || {}).value || '';
        const res = await fetch('/api/bks/context_files/toggle', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({file_id: fileId, author: curAuthor})
        });
        const data = await res.json();
        if(data.ok) renderBksContextBubble(data);
    }

    async function deleteBksContextFile(fileId) {
        const curAuthor = (document.getElementById('bks_author') || {}).value || '';
        const res = await fetch('/api/bks/context_files/delete', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({file_id: fileId, author: curAuthor})
        });
        const data = await res.json();
        if(data.ok) renderBksContextBubble(data);
    }

    function syncBksModelOptions(preferredModel) {
        const prov = document.getElementById('bks_provider_select').value || 'geminirest';
        const modSel = document.getElementById('bks_model_select');
        const prevMod = preferredModel || modSel.value;
        modSel.innerHTML = '';
        const list = bksProviderModels[prov] || [];
        if(!list.length) {
            const opt = document.createElement('option');
            opt.value = 'gemini-2.5-flash';
            opt.innerText = 'Default Model';
            modSel.appendChild(opt);
            return;
        }
        list.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m.model_id;
            opt.innerText = `${m.friendly_name} (${m.model_id})`;
            modSel.appendChild(opt);
        });
        if(prevMod && [...modSel.options].some(o => o.value === prevMod)) modSel.value = prevMod;
    }

    async function loadBksJob(jobSlug) {
        if(!jobSlug) return;
        document.getElementById('bks_status_msg').innerText = 'LOADING JOB...';
        const res = await fetch('/api/bks/job/' + encodeURIComponent(jobSlug));
        const data = await res.json();
        if(data.ok) {
            applyBksJobDetail(data);
            document.getElementById('bks_status_msg').innerText = 'JOB LOADED';
        }
    }

    function applyBksJobDetail(data) {
        currentBksDetail = data;
        currentBksJobSlug = data.job_slug;
        const jobSel = document.getElementById('bks_job_select');
        if(jobSel && [...jobSel.options].some(o => o.value === data.job_slug)) jobSel.value = data.job_slug;
        if(data.book) {
            document.getElementById('bks_title').value = data.book.title || '';
            document.getElementById('bks_topic').value = data.book.topic || data.book.thesis || '';
            if(data.book.book_type_id) document.getElementById('bks_template_select').value = data.book.book_type_id;
        }
        if(data.link) {
            if(data.link.target_page_uuid) document.getElementById('bks_target_page').value = data.link.target_page_uuid;
            if(data.link.category_name) document.getElementById('bks_category').value = data.link.category_name;
            if(data.link.author_name) document.getElementById('bks_author').value = data.link.author_name;
        }
        const badge = document.getElementById('bks_job_badge');
        if(badge && data.book) {
            badge.innerText = `JOB: ${data.job_slug} | ${(data.book.status || 'planned').toUpperCase()}`;
        }
        currentPlan = (data.chapters || []).map((c, idx) => ({
            index: c.index || (idx + 1),
            title: c.title,
            brief: c.brief,
            status: c.status,
            content: c.body_md || '',
            actual_words: c.actual_words || 0,
            target_words: c.target_words || 450
        }));
        renderBksParts();
        renderMergedPreview(data.merged_md || '', data.merged_html || '');
    }

    function renderBksParts() {
        const cont = document.getElementById('bks_parts_container');
        cont.innerHTML = '';
        currentPlan.forEach((t, i) => {
            const partIdx = t.index || (i + 1);
            const card = document.createElement('div');
            card.className = 'card';
            card.style.marginBottom = '12px';
            const isCompleted = t.status === 'accepted';
            card.innerHTML = `
                <details ${isCompleted ? '' : 'open'} style="width:100%;">
                    <summary style="cursor:pointer;list-style:none;outline:none;user-select:none;">
                        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;padding:4px 0;">
                            <div style="display:flex;align-items:center;gap:10px;flex:1;min-width:200px;">
                                <span class="badge badge-page" style="flex-shrink:0;">PART ${partIdx}/4</span>
                                <input type="text" id="bks-part-title-${i}" class="form-control" value="${(t.title || '').replace(/"/g, '&quot;')}" style="font-weight:700;flex:1;min-width:0;" onclick="event.stopPropagation();">
                            </div>
                            <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
                                <span id="bks-part-status-${i}" style="font-family:monospace;font-size:0.8rem;">${(t.status || 'planned').toUpperCase()} (${t.actual_words || 0}/${t.target_words || 450}w)</span>
                                <button type="button" class="btn btn-primary btn-sm" onclick="event.stopPropagation();runSingleBksPart(${partIdx}, ${i})">&#9654; Run Part ${partIdx}</button>
                            </div>
                        </div>
                    </summary>
                    <div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border);">
                        <div class="form-group" style="margin-bottom:10px;">
                            <label class="form-label" style="font-size:0.75rem;">Part ${partIdx} Brief &amp; Instructions</label>
                            <textarea id="bks-part-brief-${i}" class="form-control" style="min-height:60px;font-size:0.85rem;white-space:pre-wrap;word-wrap:break-word;">${t.brief || ''}</textarea>
                        </div>
                        <div>
                            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                                <label class="form-label" style="font-size:0.75rem;margin:0;">Part ${partIdx} Generated Markdown (${(t.content || '').length} chars)</label>
                                <div style="display:flex;gap:6px;">
                                    <button type="button" class="btn btn-secondary btn-sm" style="font-size:0.7rem;padding:3px 8px;" onclick="selectAllText('bks-part-body-${i}')">Select All</button>
                                    <button type="button" class="btn btn-secondary btn-sm" style="font-size:0.7rem;padding:3px 8px;" onclick="copyText('bks-part-body-${i}', this)">Copy</button>
                                </div>
                            </div>
                            <textarea id="bks-part-body-${i}" class="form-control" style="min-height:140px;font-family:monospace;font-size:0.82rem;white-space:pre-wrap;word-wrap:break-word;">${t.content || ''}</textarea>
                        </div>
                    </div>
                </details>
            `;
            cont.appendChild(card);
        });
    }

    function collectPartEditsFromDom() {
        const parts = [];
        for(let i=0; i<currentPlan.length; i++) {
            const titleEl = document.getElementById(`bks-part-title-${i}`);
            const briefEl = document.getElementById(`bks-part-brief-${i}`);
            const bodyEl = document.getElementById(`bks-part-body-${i}`);
            parts.push({
                index: currentPlan[i].index || (i + 1),
                title: titleEl ? titleEl.value : currentPlan[i].title,
                brief: briefEl ? briefEl.value : currentPlan[i].brief,
                body_md: bodyEl ? bodyEl.value : (currentPlan[i].content || '')
            });
        }
        return parts;
    }

    async function generateBksPlan() {
        const topic = document.getElementById('bks_topic').value;
        const title = document.getElementById('bks_title').value;
        if(!topic && !title) { alert('Enter a Topic or Blog Post Title first.'); return; }
        document.getElementById('bks_status_msg').innerText = 'GENERATING 4-PART PLAN...';
        const res = await fetch('/api/bks/create_plan', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                topic: topic || title,
                title: title,
                book_type_id: document.getElementById('bks_template_select').value || 'blog_post_4part',
                provider: document.getElementById('bks_provider_select').value || 'geminirest',
                model_id: document.getElementById('bks_model_select').value,
                target_page_uuid: document.getElementById('bks_target_page').value,
                category_name: document.getElementById('bks_category').value,
                author_name: document.getElementById('bks_author').value
            })
        });
        const data = await res.json();
        if(data.ok) {
            await refreshBksBootstrap();
            applyBksJobDetail(data);
            document.getElementById('bks_status_msg').innerText = '4-PART PLAN READY';
        } else {
            alert('Error: ' + (data.error || 'Unknown error'));
        }
    }

    async function saveBksPlanEdits() {
        if(!currentBksJobSlug) return;
        const res = await fetch('/api/bks/update_plan', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                job_slug: currentBksJobSlug,
                title: document.getElementById('bks_title').value,
                topic: document.getElementById('bks_topic').value,
                target_page_uuid: document.getElementById('bks_target_page').value,
                provider: document.getElementById('bks_provider_select').value,
                model_id: document.getElementById('bks_model_select').value,
                category_name: document.getElementById('bks_category').value,
                author_name: document.getElementById('bks_author').value,
                parts: collectPartEditsFromDom()
            })
        });
        const data = await res.json();
        if(data.ok) applyBksJobDetail(data);
    }

    async function runSingleBksPart(partIndex, domIdx) {
        if(!currentBksJobSlug) {
            await generateBksPlan();
            if(!currentBksJobSlug) return;
        } else {
            await saveBksPlanEdits();
        }
        const st = document.getElementById(`bks-part-status-${domIdx}`);
        if(st) st.innerText = 'WRITING VIA CLI_AI 48...';
        document.getElementById('bks_status_msg').innerText = `WRITING PART ${partIndex}/4...`;
        const res = await fetch('/api/bks/execute_part', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                job_slug: currentBksJobSlug,
                part_index: partIndex,
                provider: document.getElementById('bks_provider_select').value || 'geminirest',
                model_id: document.getElementById('bks_model_select').value,
                author_name: document.getElementById('bks_author').value
            })
        });
        const data = await res.json();
        if(data.ok && data.detail) {
            applyBksJobDetail(data.detail);
            await refreshBksBootstrap();
            document.getElementById('bks_status_msg').innerText = `PART ${partIndex} COMPLETED`;
        } else {
            alert('Part execution error: ' + (data.error || 'Unknown error'));
        }
    }

    async function runNextBksPart() {
        if(!currentBksJobSlug) {
            await generateBksPlan();
            if(!currentBksJobSlug) return;
        }
        const nextIdx = currentPlan.findIndex(p => p.status !== 'accepted');
        const targetIdx = nextIdx >= 0 ? nextIdx : 0;
        await runSingleBksPart(currentPlan[targetIdx].index || (targetIdx + 1), targetIdx);
    }

    async function runAllBksParts() {
        if(!currentBksJobSlug) {
            await generateBksPlan();
            if(!currentBksJobSlug) return;
        } else {
            await saveBksPlanEdits();
        }
        for(let i=0; i<currentPlan.length; i++) {
            await runSingleBksPart(currentPlan[i].index || (i + 1), i);
        }
        await mergeBksParts();
        document.getElementById('bks_status_msg').innerText = 'ALL 4 PARTS EXECUTED & MERGED';
    }

    async function mergeBksParts() {
        if(!currentBksJobSlug) return;
        await saveBksPlanEdits();
        const res = await fetch('/api/bks/merge', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({job_slug: currentBksJobSlug})
        });
        const data = await res.json();
        if(data.ok) {
            if(data.detail) applyBksJobDetail(data.detail);
            renderMergedPreview(data.merged_md || '', data.merged_html || '');
            document.getElementById('bks_status_msg').innerText = '4 PARTS MERGED';
        }
    }

    function renderMergedPreview(mergedMd, mergedHtml) {
        const panel = document.getElementById('bks_merged_panel');
        if(!mergedMd && !mergedHtml) { panel.style.display = 'none'; return; }
        panel.style.display = 'block';
        document.getElementById('bks_merged_md').value = mergedMd || '';
        document.getElementById('bks_merged_html_preview').innerHTML = mergedHtml || '';
    }

    async function approveAndOverwriteTargetPost() {
        if(!currentBksJobSlug) { alert('No active BKS-1 Blog Post Job to approve.'); return; }
        await saveBksPlanEdits();
        const target_page_uuid = document.getElementById('bks_target_page').value;
        const title = document.getElementById('bks_title').value;
        const msg = target_page_uuid
            ? `Approve merged 4-part post and OVERWRITE target post (${target_page_uuid})?`
            : `Approve merged 4-part post and create new CMS post "${title}"?`;
        if(!confirm(msg)) return;
        document.getElementById('bks_status_msg').innerText = 'APPROVING & OVERWRITING TARGET POST...';
        const res = await fetch('/api/bks/approve', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                job_slug: currentBksJobSlug,
                target_page_uuid: target_page_uuid,
                title: title,
                category_name: document.getElementById('bks_category').value,
                author_name: document.getElementById('bks_author').value
            })
        });
        const data = await res.json();
        if(data.ok) {
            document.getElementById('bks_status_msg').innerText = 'APPROVED & TARGET POST OVERWRITTEN';
            if(confirm(`Approved! Target post "${data.title}" (${data.target_page_uuid}) was overwritten with the merged 4-part post (${data.word_count} words). Open in Page Editor now?`)) {
                window.location.href = '/edit/' + data.target_page_uuid;
            } else {
                await refreshBksBootstrap();
                await loadBksJob(currentBksJobSlug);
            }
        } else {
            alert('Approve failed: ' + (data.error || 'Unknown error'));
        }
    }

    function selectAllText(targetId) {
        const el = document.getElementById(targetId);
        if (!el) return;
        el.focus();
        el.select();
        el.setSelectionRange(0, 99999);
    }

    async function copyText(targetId, btnElement) {
        const el = document.getElementById(targetId);
        if (!el) return;
        try {
            await navigator.clipboard.writeText(el.value || el.innerText);
            const originalText = btnElement.innerText;
            btnElement.innerText = "Copied!";
            setTimeout(() => {
                btnElement.innerText = originalText;
            }, 1500);
        } catch(err) {
            console.error("Copy failed", err);
        }
    }

    document.addEventListener('DOMContentLoaded', refreshBksBootstrap);
    </script>
    '''
    return R(html, pages=pages, categories=categories, authors=authors,
             breadcrumbs=get_breadcrumbs(request.path), active_section='content')


@content_cube.route('/api/bks/bootstrap', methods=['GET'])
@require_auth
def content_api_bks_bootstrap():
    try:
        BKSJobs.cms_bks_bootstrap()
        templates = BKSJobs.cms_bks_list_templates()
        jobs = BKSJobs.cms_bks_list_jobs()
        ai_info = AIWriting.ai_writing_get_providers_and_models()
        author = request.args.get("author")
        ctx_state = BKSJobs.cms_bks_get_context_bubble_state(author=author)
        db.mount()
        pages = [p for p in db.get_records("PageRecord") if p.get("page_type") != "external_link"]
        return jsonify({
            "ok": True,
            "templates": templates,
            "jobs": jobs,
            "ai": ai_info,
            "context_bubble": ctx_state,
            "pages": pages,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@content_cube.route('/api/bks/context_files', methods=['GET'])
@require_auth
def content_api_bks_context_files_list():
    try:
        author = request.args.get("author")
        return jsonify(BKSJobs.cms_bks_get_context_bubble_state(author=author))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@content_cube.route('/api/bks/context_files/import_pick', methods=['POST'])
@require_auth
def content_api_bks_context_files_import_pick():
    try:
        d = request.json or {}
        raw_paths = d.get("paths") or []
        author = (d.get("author") or "").strip() or None
        valid_paths, pick_errors = resolve_picks(raw_paths, "any")
        if not valid_paths and pick_errors:
            return jsonify({"ok": False, "error": pick_errors[0].get("error") or "No valid files picked", "errors": pick_errors}), 400
        res = BKSJobs.cms_bks_import_context_paths(paths_list=valid_paths, author=author)
        if pick_errors:
            res["pick_errors"] = pick_errors
        return jsonify(res)
    except PickError as pe:
        return jsonify({"ok": False, "error": str(pe)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@content_cube.route('/api/bks/context_files/toggle', methods=['POST'])
@require_auth
def content_api_bks_context_files_toggle():
    try:
        d = request.json or {}
        file_id = (d.get("file_id") or "").strip()
        author = (d.get("author") or "").strip() or None
        if not file_id:
            return jsonify({"ok": False, "error": "file_id is required"}), 400
        res = BKSJobs.cms_bks_toggle_context_file(file_id=file_id, author=author)
        return jsonify(res), (200 if res.get("ok") else 404)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@content_cube.route('/api/bks/context_files/delete', methods=['POST'])
@require_auth
def content_api_bks_context_files_delete():
    try:
        d = request.json or {}
        file_id = (d.get("file_id") or "").strip()
        author = (d.get("author") or "").strip() or None
        if not file_id:
            return jsonify({"ok": False, "error": "file_id is required"}), 400
        res = BKSJobs.cms_bks_delete_context_file(file_id=file_id, author=author)
        return jsonify(res), (200 if res.get("ok") else 404)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@content_cube.route('/api/bks/job/<job_slug>', methods=['GET'])
@require_auth
def content_api_bks_get_job(job_slug):
    try:
        detail = BKSJobs.cms_bks_get_job_detail(job_slug)
        return jsonify(detail)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@content_cube.route('/api/bks/create_plan', methods=['POST'])
@require_auth
def content_api_bks_create_plan():
    try:
        d = request.json or {}
        detail = BKSJobs.cms_bks_create_blog_job(
            topic=d.get("topic") or d.get("prompt") or d.get("title") or "Untitled Blog Post",
            title=d.get("title") or "",
            book_type_id=d.get("book_type_id") or "blog_post_4part",
            target_page_uuid=d.get("target_page_uuid") or "",
            category_name=d.get("category_name") or "Uncategorized",
            author_name=d.get("author_name") or "Elton Boehnen",
            template_key=d.get("template_key") or "blank",
            provider=d.get("provider") or "geminirest",
            model_id=d.get("model_id") or None,
            use_ai_plan=bool(d.get("use_ai_plan", True)),
        )
        return jsonify(detail)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@content_cube.route('/api/bks/update_plan', methods=['POST'])
@require_auth
def content_api_bks_update_plan():
    try:
        d = request.json or {}
        job_slug = d.get("job_slug") or ""
        if not job_slug:
            return jsonify({"ok": False, "error": "job_slug is required"}), 400
        detail = BKSJobs.cms_bks_update_job_metadata_and_plan(
            job_slug,
            title=d.get("title"),
            topic=d.get("topic"),
            target_page_uuid=d.get("target_page_uuid"),
            category_name=d.get("category_name"),
            author_name=d.get("author_name"),
            template_key=d.get("template_key"),
            provider=d.get("provider"),
            model_id=d.get("model_id"),
            parts=d.get("parts"),
        )
        return jsonify(detail)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@content_cube.route('/api/bks/execute_part', methods=['POST'])
@require_auth
def content_api_bks_execute_part():
    try:
        d = request.json or {}
        job_slug = d.get("job_slug") or ""
        part_index = int(d.get("part_index") or 1)
        res = BKSJobs.cms_bks_execute_part(
            job_slug,
            part_index,
            provider=d.get("provider") or None,
            model_id=d.get("model_id") or None,
            author_name=d.get("author_name") or None,
            custom_instructions=d.get("custom_instructions") or "",
        )
        return jsonify(res)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@content_cube.route('/api/bks/execute_all', methods=['POST'])
@require_auth
def content_api_bks_execute_all():
    try:
        d = request.json or {}
        job_slug = d.get("job_slug") or ""
        res = BKSJobs.cms_bks_execute_all_parts(
            job_slug,
            provider=d.get("provider") or None,
            model_id=d.get("model_id") or None,
            author_name=d.get("author_name") or None,
        )
        return jsonify(res)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@content_cube.route('/api/bks/merge', methods=['POST'])
@require_auth
def content_api_bks_merge():
    try:
        d = request.json or {}
        job_slug = d.get("job_slug") or ""
        res = BKSJobs.cms_bks_merge_parts(job_slug)
        res["detail"] = BKSJobs.cms_bks_get_job_detail(job_slug)
        return jsonify(res)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@content_cube.route('/api/bks/approve', methods=['POST'])
@require_auth
def content_api_bks_approve():
    try:
        d = request.json or {}
        job_slug = d.get("job_slug") or ""
        res = BKSJobs.cms_bks_approve_and_overwrite_post(
            job_slug,
            target_page_uuid=d.get("target_page_uuid"),
            title=d.get("title"),
            category_name=d.get("category_name"),
            author_name=d.get("author_name"),
            template_key=d.get("template_key"),
            merged_md_override=d.get("merged_md"),
            merged_html_override=d.get("merged_html"),
        )
        return jsonify(res)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================================
# FACTORY RESET  (merged from Cleanup_Tool.py)
# =============================================================================


