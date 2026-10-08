#!/usr/bin/env python3
"""
SCRIPT_NAME:    BEJSON_CMS_PageEditorV2
SCRIPT_VERSION: 18.8
RELATIONAL_ID:  8a4ff525-7b7b-4ac5-8720-585974579d54
AUTHOR:         Elton Boehnen
CHANGE (2026-09-25): PKG142 -- api_generate_plan()/api_execute_task() (the
/api/tasking/* routes) used to each do their own single-shot
requests.post() against Gemini -- no retry, no model fallback on 429/503,
only one key attempt ever. Per Elton: "take a look at the AI system in
place in the react system, use it to architect the python CMS version AI
system" -- both routes now call lib_cms_persona_writer.py's new
generate_with_fallback(), which ports the React CMS's server.ts
/api/gemini/generate proxy's model-cascade + token-budget architecture
(full detail in that file's own pkg142 changelog entry). Both routes now
also return model_used, and a failure response carries a structured
status + retry_delay instead of a bare error string. Verified live
through the real Flask routes with a mocked HTTP layer: successful
generation, markdown-fence stripping on execute_task still works, and a
429 failure surfaces the correctly-parsed retry_delay through the actual
JSON response.
CHANGE (2026-09-21): PKG141 -- found continuing the sweep after pkg140
(user: "anything else"/"go", kept auditing rather than stopping): a
DIFFERENT bug class from the SVG work, same instinct to keep checking
sibling code. api_upload_context()'s file.filename is client-controlled
(the multipart Content-Disposition header) and werkzeug's FileStorage.
save() does not sanitize it -- confirmed directly that a filename like
"../../../../tmp/x" resolved clean outside CONTEXT_DIR entirely before
this fix. Gated behind the same auth as every route in this app, but an
authenticated user still shouldn't get arbitrary-path file writes from a
filename field. Fixed with secure_filename() plus bejson_safe_join()
(already used for this file's /assets/ routes) as a second layer.
Verified live: the exact traversal filename that escaped before the fix
now writes safely inside CONTEXT_DIR under a collapsed-safe name, and
confirmed nothing was written to the traversal target; a legitimate
upload still works unchanged. Swept every other file.filename/upload site
in the codebase for the same pattern (BEJSON_CMS_Media.py,
BEJSON_CMS_Content.py, BEJSON_CMS_PageEditor.py) -- all already either
use secure_filename(), write to a fixed non-user-controlled path, or
never write the upload to disk at all (read into memory only). This was
the only real gap.
CHANGE (2026-09-20): PKG140 -- found while continuing the sweep right after
pkg139 shipped: BEJSON_CMS_Media.py's serve_asset()/upload-handler CSP+
sanitization work had a sibling gap in THIS file -- serve_asset_v2() and
serve_thumb_v2() are separate route implementations serving the exact
same physical ASSETS_DIR files, and neither had picked up the CSP header
serve_asset() got. Fixed both the same way. Verified live via Flask test
client: a real sanitized SVG served through both /assets/<file> and
/assets/thumb/<file> in this app now carries the CSP header; a non-SVG
asset is unaffected either way.
CHANGE (2026-09-16): PKG137 -- api_save() (add+update in one function) now
resolves category/author name to their live UUIDs and writes
page_cat_uuid/page_author_uuid alongside the existing name fields on every
save. Verified live: create resolved the correct UUIDs, a follow-up edit
re-resolved them correctly.
CHANGE (2026-09-13): PKG135 -- "give them all uuids" (Elton). /api/category/
add's Category add_record() call now includes a real cat_uuid -- it
didn't, so every category created via this endpoint was landing with
cat_uuid: None. Verified live via Flask test client against real data.
DESCRIPTION:    Editor v2 with Stabilized Sidebar, Tasking Workflow, and Gemini Config.
                Unified with CMS Data Model and Storage Format.
CHANGE (2026-08-06): PKG74 - added an Insert PDF button next to the
existing Media button. Opens its own modal (separate from the Image
picker so PDFs don't clutter/break that grid's thumbnails) fed by the
new /api/media/list_pdf route - lists uploaded PDF MediaAsset rows and
ExternalMedia rows tagged type=pdf, plus a manual URL tab for a one-off
external link. Inserts the same bej-pdf-wrap <object> embed used by
BEJSON_CMS_PageEditor.py's PDF Viewer template, directly at the cursor
in the html_body textarea (existing Image picker's "Copy Tag" flow was
left untouched).
CHANGE (2026-07-07): Added a Media Library picker - this app previously had
no media browsing at all (no ASSETS_DIR, no asset-serving routes). New:
a Media button opens a modal grid gallery of the shared Media Library;
click an image to select it, then Copy Image Tag or Rename (display name
only, physical filename never changes). New routes: /assets/<filename>,
/assets/thumb/<filename>, /api/media/list, /api/media/rename. Verified
with real data via Flask's test client, including a live rename round-trip.
CHANGE (2026-07-07): /api/save unconditionally included item_type and
external_url in every update payload (hardcoded "page"/None) - since
update_record() only touches fields it's given, this silently converted
any external-link page back to a normal page and wiped its URL on every
save through this editor. New pages still default those fields sensibly;
updates now omit them entirely so they're preserved. Verified with a live
round-trip test (external-link page survives a V2 edit intact).
"""

from flask import Flask, render_template_string, request, redirect, flash, jsonify, send_file, Response
from werkzeug.utils import secure_filename
import os, re, uuid, json, sys, html as _html, io
from datetime import datetime

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False
    # api_generate_plan()/api_execute_task() check this flag and return a
    # clean JSON error instead of letting a bare `import requests` inside
    # the function body raise an unhandled ModuleNotFoundError -> 500.

# --- BEJSON Core Pathing ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB_DIR = os.path.join(PROJECT_ROOT, "src", "lib")
if LIB_DIR not in sys.path: sys.path.append(LIB_DIR)
import lib_bejson_CMS_cms_core as CMSCore
import lib_bejson_CMS_cms_ports as CMSPorts
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")
PAGEEDITORV2_PORT = CMSPorts.get_port(CONFIG_PATH, "pageeditorv2_port", "CMS_PAGEEDITORV2_PORT")
ADMIN_PORT = CMSPorts.get_port(CONFIG_PATH, "admin_port", "CMS_ADMIN_PORT")
import lib_cms_persona_writer
from lib_bejson_Core_bejson_env import resolve_path

# --- Config ---
MFDB_DIR = os.path.join(PROJECT_ROOT, "storage", "mfdb")
MANIFEST_PATH = os.path.join(MFDB_DIR, "site_master", "104a.mfdb.bejson")
PAGES_DB_DIR = os.path.join(MFDB_DIR, "pages_db")
ASSETS_DIR = os.path.join(MFDB_DIR, "assets")
THUMBS_DIR = os.path.join(ASSETS_DIR, "_thumbs")
CONTEXT_DIR = os.path.join(PROJECT_ROOT, "Context")
os.makedirs(CONTEXT_DIR, exist_ok=True)

GEMINI_KEYS_PATH = os.path.expanduser("~/.env/gemini_keys.bejson")
MODEL_REGISTRY_PATH = resolve_path("{INTERNAL_STORAGE}/Admin/resources/Schemas/gemini_model_registry.104a.bejson")
STORAGE_CONFIG_PATH = resolve_path("{INTERNAL_STORAGE}/Admin/resources/Flask_Components/Component-File_Selector/config/path_config.104a.bejson")

# =============================================================================
# APP INITIALIZATION
# =============================================================================

app = Flask(__name__)
app.secret_key = os.environ.get('CMS_SECRET_KEY') or os.urandom(24).hex()  # Set CMS_SECRET_KEY env var in production

from BEJSON_CMS_Shared import _check_auth, _unauthorized
from lib_bejson_Core_bejson_path_guard import bejson_safe_join


@app.before_request
def _enforce_auth_everywhere():
    # SECURITY FIX: this standalone editor had zero authentication -- every
    # route completely open. Matches the same before_request gate
    # BEJSON_CMS_Admin.py enforces on its blueprints.
    Request_Basic_Auth_Header = request.authorization
    if not Request_Basic_Auth_Header or not _check_auth(Request_Basic_Auth_Header.username, Request_Basic_Auth_Header.password):
        return _unauthorized()

@app.after_request
def add_cors_headers(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,PUT,POST,DELETE,OPTIONS")
    return response

db = CMSCore.CMSCore(MANIFEST_PATH)
writer = lib_cms_persona_writer.PersonaWriter(MANIFEST_PATH)

# =============================================================================
# STORAGE & CONTEXT LOGIC
# =============================================================================

def load_storage_config():
    if not os.path.exists(STORAGE_CONFIG_PATH): return {}
    try:
        with open(STORAGE_CONFIG_PATH, "r") as f: return json.load(f)
    except: return {}

def save_storage_config(data):
    os.makedirs(os.path.dirname(STORAGE_CONFIG_PATH), exist_ok=True)
    temp_path = STORAGE_CONFIG_PATH + ".tmp"
    with open(temp_path, "w") as f: json.dump(data, f, indent=2)
    os.replace(temp_path, STORAGE_CONFIG_PATH)

@app.route("/api/storage/config", methods=["GET", "POST"])
def api_storage_config():
    if request.method == "POST":
        data = request.json
        config = load_storage_config()
        new_values = []
        for row in config.get("Values", []):
            label = row[0]
            if label in data:
                new_values.append([label, data[label]["path"], data[label]["enabled"]])
            else: new_values.append(row)
        config["Values"] = new_values
        save_storage_config(config)
        return jsonify({"ok": True})
    
    config = load_storage_config()
    paths = {v[0]: {"path": v[1], "enabled": v[2]} for v in config.get("Values", [])}
    return jsonify({"ok": True, "paths": paths})

@app.route("/api/storage/list_files")
def api_list_files():
    config = load_storage_config()
    enabled_path = next((v[1] for v in config.get("Values", []) if v[2]), os.path.expanduser("~"))
    try:
        files = sorted([f for f in os.listdir(enabled_path) if os.path.isfile(os.path.join(enabled_path, f))])
        return jsonify({"ok": True, "files": files, "path": enabled_path})
    except Exception as e: return jsonify({"ok": False, "error": str(e)})

@app.route("/api/context/list")
def api_list_context():
    files = [f for f in os.listdir(CONTEXT_DIR) if os.path.isfile(os.path.join(CONTEXT_DIR, f))]
    return jsonify({"ok": True, "files": files})

@app.route("/api/context/upload", methods=["POST"])
def api_upload_context():
    try:
        file = request.files.get("file")
        if not file: return jsonify({"ok": False, "error": "No file"})
        # SECURITY FIX (pkg141): file.filename is client-controlled (the
        # multipart Content-Disposition header) and werkzeug's
        # FileStorage.save() does NOT sanitize it -- a filename like
        # "../../../../etc/cron.d/x" resolved outside CONTEXT_DIR entirely
        # (confirmed: os.path.join + the traversal segments walks right out
        # before this fix). Gated behind the same auth as every other route
        # in this app, but an authenticated user still shouldn't be able to
        # write arbitrary files via a crafted filename. bejson_safe_join is
        # already used for the /assets/ routes in this same file; reused
        # here for the same guarantee rather than trusting secure_filename()
        # alone.
        safe_filename = secure_filename(file.filename)
        if not safe_filename:
            return jsonify({"ok": False, "error": "Invalid filename"})
        dest_path = bejson_safe_join(CONTEXT_DIR, safe_filename)
        file.save(dest_path)
        return jsonify({"ok": True, "msg": f"Uploaded {safe_filename}"})
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid filename"})
    except Exception as e: return jsonify({"ok": False, "error": str(e)})

def get_context_content(filenames):
    config = load_storage_config()
    enabled_path = next((v[1] for v in config.get("Values", []) if v[2]), CONTEXT_DIR)
    content = ""
    for f in filenames:
        path = os.path.join(enabled_path, f)
        if not os.path.exists(path): path = os.path.join(CONTEXT_DIR, f)
        if os.path.exists(path):
            try:
                with open(path, "r") as f_in: 
                    text = f_in.read()
                    content += f"\n--- REFERENCE FILE: {f} ---\n{text}\n"
            except: pass
    return content

# =============================================================================
# GEMINI & TASKING API
# =============================================================================

def get_gemini_models():
    if not os.path.exists(MODEL_REGISTRY_PATH): return []
    try:
        with open(MODEL_REGISTRY_PATH, 'r') as f: reg = json.load(f)
        fields = [f['name'] for f in reg['Fields']]
        return [dict(zip(fields, row)) for row in reg['Values']]
    except: return []

@app.route("/api/ping")
def api_ping():
    return jsonify({"ok": True, "msg": "PONG"})

@app.route('/api/settings/models')
def api_get_models():
    return jsonify({"ok": True, "models": get_gemini_models()})

@app.route('/api/tasking/generate_plan', methods=['POST'])
def api_generate_plan():
    data = request.json
    prompt = data.get('prompt')
    model = data.get('model', 'gemini-2.5-flash')
    profile_name = data.get('profile_name')  # optional AI_Profile persona name
    if not prompt: return jsonify({"ok": False, "error": "Prompt required"})

    plan_format_inst = "You are an expert content architect. Break down the request into a JSON array of objects: [{\"title\": \"...\", \"prompt\": \"...\"}]"

    # Connect to author profiles: if a persona is selected, its assembled
    # voice/tone (same helper BEJSON_CMS_ProfileManager.py's personas are
    # built from) shapes the plan on top of the required JSON-array
    # formatting constraint, which always applies regardless of persona.
    persona = writer.get_persona(profile_name) if profile_name else None
    if persona:
        plan_sys_inst = writer.assemble_system_instruction(persona) + "\n\n" + plan_format_inst
        temperature = float(persona.get("persona_creativity", 0.7))
    else:
        plan_sys_inst = plan_format_inst
        temperature = 0.7

    if not _REQUESTS_AVAILABLE:
        return jsonify({"ok": False, "error": "The 'requests' package is not installed -- pip install requests --break-system-packages"})

    # PKG142: was a single-shot requests.post() with no retry, no model
    # fallback on 429/503, and only one key attempt total -- ported from
    # the React CMS's server.ts /api/gemini/generate proxy, see
    # lib_cms_persona_writer.py's pkg142 changelog entry for the full
    # architecture. generate_with_fallback() already applies the SAME
    # token-budget trim as the React version before sending.
    result = writer.generate_with_fallback(
        f"Build a plan for: {prompt}",
        system_instruction=plan_sys_inst,
        model=model,
        generation_config={"response_mime_type": "application/json", "temperature": temperature},
    )
    if not result["ok"]:
        return jsonify({"ok": False, "error": result["error"], "status": result["status"], "retry_delay": result["retry_delay"]})
    try:
        tasks = json.loads(result["text"])
    except (json.JSONDecodeError, TypeError) as e:
        return jsonify({"ok": False, "error": f"Model returned non-JSON content: {e}"})
    return jsonify({"ok": True, "tasks": tasks, "model_used": result["model_used"]})

@app.route('/api/tasking/execute_task', methods=['POST'])
def api_execute_task():
    data = request.json
    task_title, task_prompt, full_plan = data.get('title'), data.get('prompt'), data.get('full_plan', [])
    model = data.get('model', 'gemini-2.5-flash')
    profile_name = data.get('profile_name')  # optional AI_Profile persona name
    if not task_prompt: return jsonify({"ok": False, "error": "Prompt required"})

    plan_context = "\n".join([f"- {t['title']}" for t in full_plan])
    format_inst = f"Document Plan:\n{plan_context}\n\nTask: {task_title}\nOutput ONLY clean HTML body content. No ``` tags."

    # Same persona connection as generate_plan above -- the persona's voice
    # shapes the writing, the format constraint (clean HTML, no fences)
    # always applies on top of it regardless of persona.
    persona = writer.get_persona(profile_name) if profile_name else None
    if persona:
        exec_sys_inst = writer.assemble_system_instruction(persona) + "\n\n" + format_inst
        gen_config = {
            "temperature": float(persona.get("persona_creativity", 0.7)),
            "maxOutputTokens": int(persona.get("persona_max_tokens", 8192)),
        }
    else:
        exec_sys_inst = format_inst
        gen_config = {}

    if not _REQUESTS_AVAILABLE:
        return jsonify({"ok": False, "error": "The 'requests' package is not installed -- pip install requests --break-system-packages"})

    # PKG142: same fix as api_generate_plan() above -- see that route's
    # comment and lib_cms_persona_writer.py's pkg142 changelog entry.
    result = writer.generate_with_fallback(
        task_prompt,
        system_instruction=exec_sys_inst,
        model=model,
        generation_config=gen_config or None,
        timeout=120,
    )
    if not result["ok"]:
        return jsonify({"ok": False, "error": result["error"], "status": result["status"], "retry_delay": result["retry_delay"]})
    content = result["text"].strip()
    if content.startswith("```"): content = re.sub(r'^```html?\n?|\n?```$', '', content)
    return jsonify({"ok": True, "content": content, "model_used": result["model_used"]})

# =============================================================================
# CMS INTEGRATION API
# =============================================================================

def _get_page_body_v1(page_uuid):
    """Read html_body from pages_db/<uuid>.json — returns empty string if missing."""
    import lib_bejson_Core_bejson_core as Core
    pfile = os.path.join(PAGES_DB_DIR, f"{page_uuid}.json")
    if not os.path.exists(pfile): return ""
    try:
        with open(pfile, 'r') as f: data = json.load(f)
        field_map = Core.bejson_core_get_field_map(data)
        p_idx   = field_map.get("Record_Type_Parent", -1)
        hb_idx  = field_map.get("html_body", -1)
        for row in data.get("Values", []):
            if p_idx != -1 and hb_idx != -1 and row[p_idx] == "Content":
                return row[hb_idx] or ""
        return ""
    except: return ""

@app.route('/api/get/<uuid>')
def api_get(uuid):
    db.mount()
    pages = db.get_records("PageRecord")
    p = next((x for x in pages if x['page_uuid'] == uuid), None)
    if not p: return jsonify({"ok": False})
    content = _get_page_body_v1(uuid)
    return jsonify({"ok": True, "page": p, "content": content})

@app.route('/api/save', methods=['POST'])
def api_save():
    data = request.json
    uuid_val = data.get('page_uuid') or str(uuid.uuid4())
    title    = data.get('title', 'Untitled')
    author   = data.get('author')
    cat      = data.get('category', 'Uncategorized')
    content  = data.get('content', '')
    tpl_key  = data.get('template_key', 'blank')
    featured_video = (data.get('featured_video_url') or '').strip() or None
    
    db.mount()
    existing = next((x for x in db.get_records("PageRecord") if x['page_uuid'] == uuid_val), None)

    # NEW (pkg137): resolve category/author name to their live UUIDs,
    # kept in sync alongside page_cat_name/page_author_name on every
    # write, same as every other PageRecord write site this pass.
    cat_uuid = next((c.get("cat_uuid") for c in db.get_records("Category") if c.get("cat_name") == cat), None)
    author_uuid = next((a.get("author_uuid") for a in db.get_records("AuthorProfile") if a.get("author_display_name") == author), None) if author else None

    if existing:
        # Update: only touch the fields this editor actually edits. item_type
        # and external_url are deliberately omitted - update_record() only
        # writes the keys it's given, so leaving these out preserves
        # whatever was already there. Including them unconditionally here
        # used to silently convert any external-link page back to a normal
        # page and wipe its URL on every single save via this editor.
        rec = {
            "page_title":   title,
            "page_slug":    re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-'),
            "page_cat_name": cat,
            "page_author_name": author,
            "page_template_key": tpl_key,
            "page_featured_video_url": featured_video,
            "page_cat_uuid": cat_uuid,
            "page_author_uuid": author_uuid,
        }
        db.update_record("PageRecord", "page_uuid", uuid_val, rec)
    else:
        rec = {
            "page_uuid":    uuid_val,
            "page_title":   title,
            "page_slug":    re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-'),
            "page_cat_name": cat,
            "page_type": "page",
            "page_created_at":   datetime.now().strftime("%Y-%m-%d"),
            "page_external_url": None,
            "page_author_name": author,
            "page_featured_img": None,
            "page_template_key": tpl_key,
            "page_featured_video_url": featured_video,
            "page_cat_uuid": cat_uuid,
            "page_author_uuid": author_uuid,
        }
        db.add_record("PageRecord", rec)
    
    # --- Content file in BEJSON 104db format ---
    pfile = os.path.join(PAGES_DB_DIR, f"{uuid_val}.json")
    os.makedirs(PAGES_DB_DIR, exist_ok=True)
    
    content_doc = {
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
            ["Content", None, content, "", ""]
        ]
    }
    with open(pfile, 'w') as f: json.dump(content_doc, f, indent=2)
    return jsonify({"ok": True})

# =============================================================================
# MEDIA LIBRARY — shares the same physical ASSETS_DIR as Flask_CMS.py, so
# anything uploaded there (and its thumbnails) is immediately visible here.
# This app doesn't generate thumbnails itself; if one doesn't exist yet
# (Flask_CMS.py's background worker hasn't gotten to it), the original file
# is served instead - same fallback pattern Flask_CMS.py's own /assets/thumb
# route uses.
# =============================================================================

@app.route('/assets/<path:filename>')
def serve_asset_v2(filename):
    try:
        safe_path = bejson_safe_join(str(ASSETS_DIR), filename)
    except ValueError:
        return "Not found", 404
    response = send_file(safe_path)
    if filename.lower().endswith('.svg'):
        # Same CSP defense-in-depth as BEJSON_CMS_Media.py's serve_asset()
        # (pkg139) -- this is a SEPARATE route serving the SAME physical
        # ASSETS_DIR files, so it needed the identical fix, not inherited
        # automatically from the other file. Found in the same sweep that
        # added it there, before shipping as an inconsistency between the
        # two apps' serving of identical files.
        response.headers['Content-Security-Policy'] = "script-src 'none'; sandbox;"
        response.headers['Content-Type'] = 'image/svg+xml'
    return response

@app.route('/assets/thumb/<path:filename>')
def serve_thumb_v2(filename):
    stem = os.path.splitext(filename)[0]
    try:
        safe_thumb = bejson_safe_join(str(THUMBS_DIR), stem + ".jpg")
        safe_orig = bejson_safe_join(str(ASSETS_DIR), filename)
    except ValueError:
        return "Not found", 404
    if os.path.exists(safe_thumb):
        return send_file(safe_thumb)
    response = send_file(safe_orig)
    if filename.lower().endswith('.svg'):
        response.headers['Content-Security-Policy'] = "script-src 'none'; sandbox;"
        response.headers['Content-Type'] = 'image/svg+xml'
    return response

@app.route('/api/media/list')
def api_media_list():
    db.mount()
    assets = db.get_records("MediaAsset")
    assets.sort(key=lambda a: a.get('asset_uploaded_at') or '', reverse=True)
    return jsonify({"ok": True, "files": [
        {"filename": a.get("asset_filename"), "original_name": a.get("asset_original_name") or a.get("asset_filename"),
         "file_size": a.get("asset_file_size") or 0}
        for a in assets
    ]})

@app.route('/api/media/list_pdf')
def api_media_list_pdf():
    """Combined list for the Insert PDF modal: uploaded MediaAsset rows
    ending in .pdf, plus ExternalMedia rows tagged media_type == 'pdf'.
    Each item carries a ready-to-use `src` (relative ../../../assets/<file>
    for an uploaded asset, the raw absolute URL for an external link)."""
    db.mount()
    items = []
    try:
        for a in db.get_records("MediaAsset"):
            fname = a.get("asset_filename") or ""
            if fname.lower().endswith(".pdf"):
                items.append({
                    "kind": "asset",
                    "label": a.get("asset_original_name") or fname,
                    "src": f"../../../assets/{fname}",
                })
    except Exception:
        pass
    try:
        for ext in db.get_records("ExternalMedia"):
            if (ext.get("extmedia_type") or "").lower() == "pdf":
                url = ext.get("extmedia_url") or ""
                if url:
                    items.append({
                        "kind": "external",
                        "label": ext.get("extmedia_name") or url,
                        "src": url,
                    })
    except Exception:
        pass
    items.sort(key=lambda i: i["label"].lower())
    return jsonify({"ok": True, "items": items})

@app.route('/api/media/list_video')
def api_media_list_video():
    """Feeds the Insert YouTube modal's Saved Links tab: ExternalMedia rows
    tagged extmedia_type == 'video'. No MediaAsset side to this one --
    YouTube videos are never uploaded files, only saved external links."""
    db.mount()
    items = []
    try:
        for ext in db.get_records("ExternalMedia"):
            if (ext.get("extmedia_type") or "").lower() == "video":
                url = ext.get("extmedia_url") or ""
                if url:
                    items.append({
                        "label": ext.get("extmedia_name") or url,
                        "url": url,
                    })
    except Exception:
        pass
    items.sort(key=lambda i: i["label"].lower())
    return jsonify({"ok": True, "items": items})

@app.route('/api/media/rename', methods=['POST'])
def api_media_rename():
    data = request.json or {}
    filename = data.get('filename', '').strip()
    new_name = data.get('new_name', '').strip()
    if not filename or not new_name:
        return jsonify({"ok": False, "error": "filename and new_name are required"})
    db.mount()
    ok = db.update_record("MediaAsset", "asset_filename", filename, {"asset_original_name": new_name})
    return jsonify({"ok": ok})

@app.route('/api/delete/<uuid_val>', methods=['POST'])
def api_delete(uuid_val):
    db.mount()
    if db.delete_record("PageRecord", "page_uuid", uuid_val):
        path = os.path.join(PAGES_DB_DIR, f"{uuid_val}.json")
        if os.path.exists(path): os.remove(path)
        return jsonify({"ok": True})
    return jsonify({"ok": False})

@app.route('/api/category/add', methods=['POST'])
def api_add_cat():
    name = request.json.get('name')
    if not name: return jsonify({"ok": False})
    db.mount()
    db.add_record("Category", {"cat_uuid": str(uuid.uuid4()), "cat_name": name, "cat_slug": name.lower().replace(" ","-")})
    return jsonify({"ok": True})

@app.route('/api/settings/export_keys')
def api_export_keys():
    try:
        import subprocess
        # Simplified path for export - using project root/storage/tmp
        out_path = os.path.join(PROJECT_ROOT, "storage", "tmp", "gemini_keys_export.bejson")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        # capture_output instead of letting stderr leak straight to this
        # app's own console -- if gemini_key_manager.py isn't present at
        # this path (expected off the original authoring device), python3
        # itself writes a "can't open file" message to stderr before
        # exiting non-zero; check=True turns that into a clean caught
        # CalledProcessError either way, but without capture_output the
        # noise still hits the real console first. Captured stderr is
        # included in the JSON error so a genuine script failure (not just
        # a missing-file case) still surfaces useful diagnostic text.
        result = subprocess.run(["python3", resolve_path("{INTERNAL_STORAGE}/Admin/tools/gemini_key_manager.py"), "--export", out_path], check=True, capture_output=True, text=True)
        return jsonify({"ok": True, "msg": f"Template exported to {out_path}"})
    except subprocess.CalledProcessError as e:
        return jsonify({"ok": False, "error": (e.stderr or str(e)).strip()[-500:]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route('/api/settings/import_keys', methods=['POST'])
def api_import_keys():
    try:
        file = request.files.get('file')
        if not file: return jsonify({"ok": False, "error": "No file uploaded"})
        tmp_path = os.path.join(PROJECT_ROOT, "storage", "tmp", "import_keys_upload.bejson")
        os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
        file.save(tmp_path)
        import subprocess
        result = subprocess.run(["python3", resolve_path("{INTERNAL_STORAGE}/Admin/tools/gemini_key_manager.py"), "--import-keys", tmp_path], check=True, capture_output=True, text=True)
        return jsonify({"ok": True, "msg": "Keys imported successfully."})
    except subprocess.CalledProcessError as e:
        return jsonify({"ok": False, "error": (e.stderr or str(e)).strip()[-500:]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route('/api/debug_keys')
def debug_keys():
    return jsonify({
        "path": GEMINI_KEYS_PATH,
        "exists": os.path.exists(GEMINI_KEYS_PATH),
        "keys_loaded": len(writer.api_keys),
        "cwd": os.getcwd()
    })

# =============================================================================
# UI RENDERING
# =============================================================================

DEFAULT_HTML = """<section class="content-block">
    <h1>New Content</h1>
    <p>Writing with BEJSON Editor v2...</p>
</section>"""

_SHELL = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BEJSON Editor v2</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Inter:wght@400;600;900&display=swap" rel="stylesheet">
    <style>
        :root { --bg: #050505; --card: #0c0c0c; --border: #1a1a1a; --acc: #de2626; --fg: #fff; --muted: #666; --font: 'Inter', sans-serif; --mono: 'JetBrains Mono', monospace; }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: var(--bg); color: var(--fg); font-family: var(--font); line-height: 1.6; min-height: 100vh; overflow-x: hidden; }
        
        .header { height: 60px; background: #000; border-bottom: 1px solid var(--border); display: flex; align-items: center; padding: 0 80px; position: sticky; top: 0; z-index: 1000; }
        .logo { font-weight: 900; letter-spacing: -1px; font-size: 1.2rem; }
        .logo span { color: var(--acc); }

        .hamburger { 
            position: fixed; top: 15px; left: 20px; width: 30px; height: 22px; 
            cursor: pointer; z-index: 100001; display: flex; flex-direction: column; justify-content: space-between;
            background: rgba(0,0,0,0.3); padding: 5px; border-radius: 4px;
        }
        .hamburger div { width: 100%; height: 2px; background: #fff; border-radius: 1px; transition: 0.3s; }

        .side-menu { 
            position: fixed; top: 0; left: -320px; width: 300px; height: 100vh; 
            background: #080808; border-right: 1px solid var(--border); z-index: 100000; 
            transition: left 0.3s cubic-bezier(0.4, 0, 0.2, 1); padding: 80px 0 20px;
            box-shadow: 10px 0 30px rgba(0,0,0,0.5);
        }
        .side-menu.open { left: 0; }
        
        .menu-overlay {
            position: fixed; inset: 0; background: rgba(0,0,0,0.8); z-index: 99999;
            display: none; opacity: 0; transition: opacity 0.3s;
        }
        .menu-overlay.active { display: block; opacity: 1; }

        .side-menu a { 
            display: block; padding: 15px 30px; color: var(--muted); font-weight: 800; 
            text-transform: uppercase; font-size: 0.8rem; text-decoration: none; border-left: 4px solid transparent;
        }
        .side-menu a:hover, .side-menu a.active { color: #fff; background: rgba(222,38,38,0.1); border-left-color: var(--acc); }

        .container { max-width: 1100px; margin: 30px auto; padding: 0 20px; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .editor-wrap { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 25px; }
        
        .fg { display: flex; flex-direction: column; gap: 8px; margin-bottom: 20px; }
        label { font-size: 0.7rem; font-weight: 900; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; }
        input, select, textarea { background: #000; border: 1px solid var(--border); color: #fff; padding: 12px; border-radius: 8px; font-family: inherit; width: 100%; }
        textarea { min-height: 500px; font-family: var(--mono); font-size: 0.9rem; resize: vertical; }

        .btn { background: var(--acc); color: #fff; border: none; padding: 12px 24px; border-radius: 8px; font-weight: 900; cursor: pointer; text-transform: uppercase; font-size: 0.8rem; }
        .btn-black { background: #1a1a1a; border: 1px solid var(--border); }
        .btn-green { background: #059669; }
        .btn-kill { background: #991b1b; }
        .btn-sm { padding: 8px 16px; font-size: 0.7rem; }
        .flex-row { display: flex; gap: 15px; align-items: center; }

        /* Toolbar/button-bar rows: scroll horizontally on overflow instead of
           clipping or squishing buttons off-screen -- added pkg77, was the
           cause of Save/Delete etc. getting cut off at narrow widths. */
        .toolbar-row {
            display: flex;
            gap: 12px;
            align-items: center;
            flex-wrap: nowrap;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            scrollbar-width: thin;
            padding-bottom: 6px;
            margin-bottom: -2px;
        }
        .toolbar-row::-webkit-scrollbar { height: 4px; }
        .toolbar-row::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
        .toolbar-row > .btn, .toolbar-row > button { flex-shrink: 0; }
        .toolbar-row > label { flex-shrink: 0; white-space: nowrap; }

        /* Form-field-pair rows (selects/inputs, not buttons): stack instead
           of squishing on narrow screens. */
        @media (max-width: 620px) {
            .flex-row:not(.toolbar-row) { flex-wrap: wrap; }
            .flex-row:not(.toolbar-row) > .fg { min-width: 100%; }
        }
        
        .status-bar { margin-top: 15px; display: flex; justify-content: space-between; font-size: 0.7rem; font-family: var(--mono); color: var(--muted); }
        
        .task-card { background:#000; border:1px solid var(--border); border-radius:8px; padding:15px; margin-bottom:10px; }
        .task-title { font-weight:700; color:var(--acc); margin-bottom:10px; font-size:0.9rem; }
        
        .attachment-pill { padding:6px 12px; background:#111; border:1px solid var(--border); border-radius:20px; font-size:0.75rem; cursor:pointer; }
        .attachment-pill.selected { border-color:var(--acc); background:rgba(222,38,38,0.1); }

        .media-modal-overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.75); z-index:3000; align-items:center; justify-content:center; }
        .media-modal-overlay.open { display:flex; }
        .media-modal-box { background:var(--card); border:1px solid var(--border); border-radius:12px; width:92%; max-width:960px; max-height:85vh; display:flex; flex-direction:column; overflow:hidden; }
        .media-modal-head { display:flex; justify-content:space-between; align-items:center; padding:16px 20px; border-bottom:1px solid var(--border); }
        .media-modal-head h3 { margin:0; font-size:1rem; }
        .media-modal-close { background:none; border:none; color:var(--muted); font-size:1.4rem; cursor:pointer; line-height:1; }
        .media-modal-grid { flex:1; overflow-y:auto; padding:20px; display:grid; grid-template-columns:repeat(auto-fill,minmax(130px,1fr)); gap:14px; }
        .media-modal-item { cursor:pointer; border-radius:8px; overflow:hidden; border:2px solid transparent; background:#000; aspect-ratio:1; position:relative; }
        .media-modal-item img { width:100%; height:100%; object-fit:cover; display:block; }
        .media-modal-item.selected { border-color:var(--acc); box-shadow:0 0 0 2px rgba(222,38,38,0.4); }
        .media-modal-item .fname { position:absolute; bottom:0; left:0; right:0; background:rgba(0,0,0,0.75); color:#fff; font-size:0.65rem; padding:4px 6px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .media-modal-actions { display:flex; gap:10px; padding:14px 20px; border-top:1px solid var(--border); align-items:center; }
        .media-modal-actions .selected-name { flex:1; font-size:0.8rem; color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .pdf-src-tab-v2 { flex:1; padding:8px 12px; background:transparent; border:none; border-bottom:2px solid transparent; color:var(--muted); font-size:.8rem; font-weight:700; cursor:pointer; }
        .pdf-src-tab-v2.active { color:var(--acc); border-bottom-color:var(--acc); }
    </style>
</head>
<body>

<div class="hamburger" id="h-btn" onclick="toggleMenu()">
    <div></div><div></div><div></div>
</div>

<div class="header">
    <div class="logo">BEJSON<span>_EDITOR_V2</span></div>
</div>

<div id="m-overlay" class="menu-overlay" onclick="toggleMenu()"></div>
<div id="s-menu" class="side-menu">
    <a href="#" onclick="showTab('editor')" class="tab-link active" id="l-editor">Editor Engine</a>
    <a href="#" onclick="showTab('tasking')" class="tab-link" id="l-tasking">Tasking Hub</a>
    <a href="#" onclick="showTab('context')" class="tab-link" id="l-context">Context & Attachments</a>
    <a href="#" onclick="showTab('settings')" class="tab-link" id="l-settings">System Config</a>
    <a href="{{ admin_url }}" style="margin-top:auto; border-top:1px solid var(--border);">Back to CMS</a>
</div>

<div class="container">
    {% with msgs = get_flashed_messages() %}{% for m in msgs %}<div style="padding:15px; background:rgba(222,38,38,0.1); border:1px solid var(--acc); color:var(--acc); border-radius:8px; margin-bottom:20px;">{{m}}</div>{% endfor %}{% endwith %}

    <div id="t-editor" class="tab-content active">
        <div class="editor-wrap">
            <div class="flex-row" style="margin-bottom:20px;">
                <div class="fg" style="flex:1;">
                    <label>Filter</label>
                    <select id="catSelect" onchange="filterPages()">
                        <option value="all">All Categories</option>
                        {% for c in categories %}<option value="{{c.cat_name}}">{{c.cat_name}}</option>{% endfor %}
                    </select>
                </div>
                <div class="fg" style="flex:1;">
                    <label>Target Page</label>
                    <select id="pageSelect">
                        <option value="">-- Select --</option>
                        {% for p in pages %}<option value="{{p.page_uuid}}" data-cat="{{p.page_cat_name}}">{{p.page_title}}</option>{% endfor %}
                    </select>
                </div>
            </div>
            <div class="flex-row toolbar-row" style="margin-bottom:25px;">
                <button class="btn btn-green" onclick="openNewModal()">New</button>
                <button class="btn btn-black" onclick="handleLoad()">Load</button>
                <button class="btn" onclick="savePage()">Save</button>
                <button class="btn btn-kill" onclick="deletePage()">Delete</button>
            </div>
            <div class="grid2" style="display:grid; grid-template-columns:1fr 1fr; gap:15px;">
                <div class="fg">
                    <label>Page Title</label>
                    <input type="text" id="edit_title" placeholder="Untitled">
                </div>
                <div class="fg">
                    <label>Template</label>
                    <select id="edit_template">
                        <option value="blank">Blank</option>
                        <option value="article">Article</option>
                        <option value="youtube_video">YouTube Video</option>
                        <option value="image_gallery">Gallery</option>
                        <option value="code">Code</option>
                    </select>
                </div>
            </div>
            <div class="grid2" style="display:grid; grid-template-columns:1fr 1fr; gap:15px;">
                <div class="fg">
                    <label>Author</label>
                    <select id="edit_author">
                        {% for a in authors %}<option value="{{a.author_display_name}}">{{a.author_display_name}}</option>{% endfor %}
                    </select>
                </div>
                <div class="fg">
                    <label>Category</label>
                    <select id="edit_category">
                        {% for c in categories %}<option value="{{c.cat_name}}">{{c.cat_name}}</option>{% endfor %}
                    </select>
                </div>
            </div>
            <div class="fg">
                <div class="flex-row toolbar-row" style="justify-content:space-between; margin-bottom:8px;">
                    <label style="margin:0;">Featured Video</label>
                    <button type="button" class="btn btn-secondary btn-sm" onclick="toggleFeaturedVideoPanel()">Choose...</button>
                </div>
                <div id="featured-video-current" style="font-size:.8rem; color:var(--muted); margin-bottom:6px;">None selected</div>
                <div id="featured-video-panel" style="display:none; max-height:220px; overflow-y:auto; border:1px solid var(--border); border-radius:6px; padding:10px; background:var(--bg-secondary);">
                    <label style="display:flex; align-items:center; gap:8px; padding:4px 0; cursor:pointer;">
                        <input type="radio" name="featured_video_radio" value="" checked onchange="setFeaturedVideo('', 'None')">
                        <span>None</span>
                    </label>
                    <div id="featured-video-list"><span style="font-size:.8rem; color:var(--muted);">Loading saved videos...</span></div>
                </div>
                <input type="hidden" id="edit_featured_video_url" value="">
            </div>
            <div class="fg">
                <div class="flex-row toolbar-row" style="justify-content:space-between; margin-bottom:8px;">
                    <label style="margin:0;">Content</label>
                    <button type="button" class="btn btn-black btn-sm" onclick="openMediaPickerV2()">&#128247; Media</button>
                    <button type="button" class="btn btn-black btn-sm" onclick="openPdfPickerV2()">&#128196; PDF</button>
                    <button type="button" class="btn btn-black btn-sm" onclick="openYtPickerV2()">&#9654; YouTube</button>
                </div>
                <textarea id="html_body"></textarea>
            </div>
            <div class="status-bar" style="margin-top: 15px;">
                <div>SYSTEM: <span id="sys_status" style="color:var(--acc);">READY</span></div>
                <div id="status_msg">IDLE</div>
            </div>
        </div>
    </div>

    <div id="t-context" class="tab-content">
        <div class="editor-wrap">
            <h2>Context & Attachments</h2>
            <div id="path-config-root" style="background:#080808; padding:20px; border-radius:12px; border:1px solid var(--border); position:relative; margin-bottom:25px; margin-top:20px;">
                <h3 style="margin-bottom:15px; font-size:1rem;">Storage Path Configuration</h3>
                <div id="storage-radios" style="display:flex; gap:20px; margin-bottom:15px;"></div>
                <input type="text" id="path-input" oninput="autoSaveStorage()" style="font-family:var(--mono); font-size:0.85rem;">
                <div style="display:flex; align-items:center; gap:10px; border-top:1px solid var(--border); padding-top:20px; margin-top:15px;">
                    <button class="btn btn-black btn-sm" onclick="loadStorageFiles()">Scan Path</button>
                </div>
            </div>
            <div class="editor-wrap" style="background:rgba(255,255,255,0.02); border-style:dashed;">
                <h4 style="margin-bottom:15px;">Available Files</h4>
                <div id="attachment_list" style="display:flex; flex-wrap:wrap; gap:10px; min-height:40px;"></div>
            </div>
        </div>
    </div>

    <div id="t-tasking" class="tab-content">
        <div class="editor-wrap">
            <h2>AI Content Architect</h2>
            <textarea id="task_prompt" style="min-height:150px; margin-bottom:20px; margin-top:20px;" placeholder="What are we building today?"></textarea>
            <div class="flex-row toolbar-row" style="margin-bottom:20px;">
                <button class="btn btn-green" onclick="generateTaskPlan()">Generate Plan</button>
                <button class="btn" id="exec-btn" onclick="runTaskingPlan()">Execute All</button>
                <button class="btn btn-black" onclick="importPlanToEditor()">Import to Editor</button>
            </div>
            <div id="task_container"></div>
        </div>
    </div>

    <div id="t-settings" class="tab-content">
        <div class="editor-wrap">
            <h2>System Config</h2>
            <div class="fg" style="margin-top:20px;">
                <label>Active Model</label>
                <select id="model_select"></select>
            </div>
            <div class="fg">
                <label>Key Registry</label>
                <div class="flex-row toolbar-row">
                    <button class="btn btn-black btn-sm" onclick="exportKeyTemplate()">Export</button>
                    <input type="file" id="key_import_file" accept=".bejson" style="max-width:200px; padding:5px; flex-shrink:0;">
                    <button class="btn btn-black btn-sm" onclick="importKeys()">Import</button>
                </div>
            </div>
        </div>
    </div>
</div>

<div id="newModal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.9); z-index:9000; align-items:center; justify-content:center;">
    <div class="editor-wrap" style="width:400px;">
        <h3>New Page</h3>
        <input type="text" id="modal_input" placeholder="Title..." style="margin:20px 0;">
        <div class="flex-row toolbar-row">
            <button class="btn" onclick="createNewDraft()">Create</button>
            <button class="btn btn-black" onclick="closeModal()">Cancel</button>
        </div>
    </div>
</div>

<input type="hidden" id="hidden_uuid">

<script>
const DEFAULT_HTML = `{{ default_html|safe }}`;
let currentPlan = [];

function toggleMenu() {
    document.getElementById('s-menu').classList.toggle('open');
    document.getElementById('m-overlay').classList.toggle('active');
}

function showTab(id) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-link').forEach(l => l.classList.remove('active'));
    document.getElementById('t-' + id).classList.add('active');
    document.getElementById('l-' + id).classList.add('active');
    if(id === 'settings') loadModels();
    if(id === 'context') initStorage();
    toggleMenu();
}

function filterPages() {
    const cat = document.getElementById('catSelect').value;
    const opts = document.getElementById('pageSelect').options;
    for(let i=1; i < opts.length; i++) {
        opts[i].style.display = (cat === 'all' || opts[i].getAttribute('data-cat') === cat) ? 'block' : 'none';
    }
}

async function loadPageData(uuid) {
    const res = await fetch('/api/get/' + uuid);
    const data = await res.json();
    if(data.ok) {
        document.getElementById('hidden_uuid').value = uuid;
        document.getElementById('edit_title').value = data.page.page_title;
        document.getElementById('edit_author').value = data.page.page_author_name || '';
        document.getElementById('edit_category').value = data.page.page_cat_name || 'Uncategorized';
        document.getElementById('edit_template').value = data.page.page_template_key || 'blank';
        document.getElementById('edit_featured_video_url').value = data.page.page_featured_video_url || '';
        document.getElementById('featured-video-current').textContent = data.page.page_featured_video_url
            ? ('Selected: ' + data.page.page_featured_video_url) : 'None selected';
        _featuredVideoLoaded = false;
        document.getElementById('featured-video-panel').style.display = 'none';
        document.getElementById('html_body').value = data.content;
        document.getElementById('status_msg').innerText = 'LOADED';
    }
}

function handleLoad() {
    const uuid = document.getElementById('pageSelect').value;
    if(uuid) loadPageData(uuid);
}

async function savePage() {
    const uuid = document.getElementById('hidden_uuid').value;
    const title = document.getElementById('edit_title').value;
    const author = document.getElementById('edit_author').value;
    const cat = document.getElementById('edit_category').value;
    const content = document.getElementById('html_body').value;
    const template_key = document.getElementById('edit_template').value;
    const featured_video_url = document.getElementById('edit_featured_video_url').value;
    
    if(!title) { alert('Title required'); return; }

    const res = await fetch('/api/save', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({page_uuid: uuid, title, author, category: cat, content, template_key, featured_video_url})
    });
    if((await res.json()).ok) { alert('Saved!'); location.reload(); }
}

function openNewModal() { document.getElementById('newModal').style.display = 'flex'; }
function closeModal() { document.getElementById('newModal').style.display = 'none'; }
function createNewDraft() {
    const title = document.getElementById('modal_input').value;
    if(!title) return;
    document.getElementById('hidden_uuid').value = '';
    document.getElementById('edit_title').value = title;
    document.getElementById('edit_category').value = 'Uncategorized';
    document.getElementById('edit_featured_video_url').value = '';
    document.getElementById('featured-video-current').textContent = 'None selected';
    document.getElementById('featured-video-panel').style.display = 'none';
    _featuredVideoLoaded = false;
    document.getElementById('html_body').value = DEFAULT_HTML;
    closeModal();
}

async function deletePage() {
    const uuid = document.getElementById('hidden_uuid').value;
    if(!uuid || !confirm('Delete permanently?')) return;
    const res = await fetch('/api/delete/' + uuid, {method: 'POST'});
    if((await res.json()).ok) location.reload();
}

async function loadModels() {
    const res = await fetch('/api/settings/models');
    const data = await res.json();
    const sel = document.getElementById('model_select');
    sel.innerHTML = '';
    data.models.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m.model_id; opt.innerText = m.friendly_name;
        sel.appendChild(opt);
    });
}

// AI Tasking Logic
async function generateTaskPlan() {
    const prompt = document.getElementById('task_prompt').value;
    const model = document.getElementById('model_select').value;
    // Connects AI generation to author profiles: whichever author is
    // selected for this page also drives the persona/voice used to
    // generate it (AuthorProfile.auth_name matches AI_Profile.Name).
    const profile_name = document.getElementById('edit_author').value;
    if(!prompt) return;
    document.getElementById('status_msg').innerText = 'GENERATING PLAN...';
    const res = await fetch('/api/tasking/generate_plan', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({prompt, model, profile_name})
    });
    const data = await res.json();
    if(data.ok) {
        currentPlan = data.tasks;
        renderPlan();
        document.getElementById('status_msg').innerText = 'PLAN READY';
    }
}

function renderPlan() {
    const cont = document.getElementById('task_container');
    cont.innerHTML = '';
    currentPlan.forEach((t, i) => {
        const div = document.createElement('div');
        div.className = 'task-card';
        div.innerHTML = `<div class="task-title">${t.title}</div><div id="task-res-${i}" style="font-size:0.75rem; color:var(--muted);">Pending...</div>`;
        cont.appendChild(div);
    });
}

async function runTaskingPlan() {
    const model = document.getElementById('model_select').value;
    const profile_name = document.getElementById('edit_author').value;
    for(let i=0; i<currentPlan.length; i++) {
        const t = currentPlan[i];
        document.getElementById(`task-res-${i}`).innerText = 'EXECUTING...';
        const res = await fetch('/api/tasking/execute_task', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({title: t.title, prompt: t.prompt, full_plan: currentPlan, model, profile_name})
        });
        const data = await res.json();
        if(data.ok) {
            currentPlan[i].content = data.content;
            document.getElementById(`task-res-${i}`).innerText = 'COMPLETED';
            document.getElementById(`task-res-${i}`).style.color = '#059669';
        }
    }
}

function importPlanToEditor() {
    let combined = "";
    currentPlan.forEach(t => {
        if(t.content) combined += `<h2>${t.title}</h2>\n${t.content}\n\n`;
    });
    document.getElementById('html_body').value = combined;
    showTab('editor');
}

// Storage Component
let storagePaths = {};
async function initStorage() {
    const res = await fetch('/api/storage/config');
    const data = await res.json();
    storagePaths = data.paths;
    renderStorageRadios();
    loadAttachmentList();
}

function renderStorageRadios() {
    const cont = document.getElementById('storage-radios');
    cont.innerHTML = '';
    for(const [label, info] of Object.entries(storagePaths)) {
        const div = document.createElement('div');
        div.innerHTML = `<label style="display:flex; align-items:center; gap:8px; cursor:pointer; text-transform:none;">
            <input type="radio" name="spath" value="${label}" ${info.enabled?'checked':''} onchange="setStorage('${label}')"> ${label}
        </label>`;
        cont.appendChild(div);
    }
}

async function setStorage(label) {
    for(let k in storagePaths) storagePaths[k].enabled = (k === label);
    document.getElementById('path-input').value = storagePaths[label].path;
    await fetch('/api/storage/config', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify(storagePaths)
    });
}

async function loadAttachmentList() {
    const res = await fetch('/api/context/list');
    const data = await res.json();
    const cont = document.getElementById('attachment_list');
    cont.innerHTML = '';
    data.files.forEach(f => {
        const pill = document.createElement('div');
        pill.className = 'attachment-pill';
        pill.innerText = f;
        cont.appendChild(pill);
    });
}

window.onload = () => {
    loadModels();
};

// =============================================================================
// MEDIA PICKER — grid gallery of the shared Media Library. Click an image to
// select it (highlight), then Copy Tag or Rename from the action bar below
// the grid. Rename only changes the display name (original_name) - the
// physical stored filename never changes, so anything already referencing
// it keeps working, matching Flask_CMS.py's own Media Library behavior.
// =============================================================================
var _mediaPickerSelected = null;

function openMediaPickerV2() {
    document.getElementById('media-modal-v2').classList.add('open');
    loadMediaGridV2();
}

function closeMediaPickerV2() {
    document.getElementById('media-modal-v2').classList.remove('open');
    _mediaPickerSelected = null;
    updateMediaActionBarV2();
}

function loadMediaGridV2() {
    const grid = document.getElementById('media-modal-grid-v2');
    grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--muted);">Loading…</div>';
    fetch('/api/media/list').then(r => r.json()).then(d => {
        grid.innerHTML = '';
        if (!d.ok || !d.files || !d.files.length) {
            grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--muted);">Media library is empty.</div>';
            return;
        }
        d.files.forEach(f => {
            const item = document.createElement('div');
            item.className = 'media-modal-item';
            item.dataset.filename = f.filename;
            item.innerHTML = '<img src="/assets/thumb/' + f.filename + '" loading="lazy">' +
                '<div class="fname">' + f.original_name + '</div>';
            item.onclick = () => selectMediaItemV2(f.filename, f.original_name, item);
            grid.appendChild(item);
        });
    });
}

function selectMediaItemV2(filename, originalName, el) {
    document.querySelectorAll('.media-modal-item.selected').forEach(x => x.classList.remove('selected'));
    el.classList.add('selected');
    _mediaPickerSelected = { filename: filename, original_name: originalName };
    updateMediaActionBarV2();
}

function updateMediaActionBarV2() {
    const bar = document.getElementById('media-modal-actions-v2');
    const nameEl = document.getElementById('media-modal-selected-name-v2');
    if (_mediaPickerSelected) {
        bar.style.display = 'flex';
        nameEl.textContent = _mediaPickerSelected.original_name;
    } else {
        bar.style.display = 'none';
    }
}

function copyMediaTagV2() {
    if (!_mediaPickerSelected) return;
    const tag = '<img src="/assets/' + _mediaPickerSelected.filename + '" alt="' + _mediaPickerSelected.original_name + '">';
    const ta = document.createElement('textarea');
    ta.value = tag;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (e) {}
    document.body.removeChild(ta);
    document.getElementById('status_msg').textContent = 'Image tag copied to clipboard';
}

function renameMediaV2() {
    if (!_mediaPickerSelected) return;
    const newName = prompt('New display name:', _mediaPickerSelected.original_name);
    if (newName === null || newName.trim() === '') return;
    fetch('/api/media/rename', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: _mediaPickerSelected.filename, new_name: newName })
    }).then(r => r.json()).then(d => {
        if (d.ok) {
            _mediaPickerSelected.original_name = newName;
            updateMediaActionBarV2();
            loadMediaGridV2();
        } else {
            alert('Rename failed: ' + (d.error || 'unknown error'));
        }
    });
}

// =============================================================================
// PDF PICKER — separate from the Image media picker above (that grid always
// renders <img> thumbs, which breaks for non-image assets). Lists uploaded
// PDFs + saved External Media Links tagged type=pdf, or a one-off pasted
// URL, then inserts the bej-pdf-wrap <object> embed directly into the
// html_body textarea at the current cursor position.
// =============================================================================
var _pdfSelectedV2 = null;

function openPdfPickerV2() {
    _pdfSelectedV2 = null;
    document.getElementById('pdf-modal-selected-name-v2').textContent = '';
    pdfShowTabV2('library');
    document.getElementById('pdf-modal-v2').classList.add('open');
    loadPdfListV2();
}

function closePdfPickerV2() {
    document.getElementById('pdf-modal-v2').classList.remove('open');
}

function pdfShowTabV2(which) {
    const libTab = document.getElementById('pdfTabLibraryV2'), urlTab = document.getElementById('pdfTabUrlV2');
    const libPane = document.getElementById('pdfPaneLibraryV2'), urlPane = document.getElementById('pdfPaneUrlV2');
    if (which === 'library') {
        libTab.classList.add('active'); urlTab.classList.remove('active');
        libPane.style.display = 'block'; urlPane.style.display = 'none';
    } else {
        urlTab.classList.add('active'); libTab.classList.remove('active');
        urlPane.style.display = 'block'; libPane.style.display = 'none';
    }
}

function loadPdfListV2() {
    const pane = document.getElementById('pdfPaneLibraryV2');
    fetch('/api/media/list_pdf').then(r => r.json()).then(d => {
        pane.innerHTML = '';
        if (!d.ok || !d.items || !d.items.length) {
            pane.innerHTML = '<div style="text-align:center;color:var(--muted);font-size:.85rem;">No PDFs yet — upload one via Media, or use the External URL tab.</div>';
            return;
        }
        d.items.forEach(item => {
            const row = document.createElement('div');
            row.style = 'padding:8px 4px;cursor:pointer;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;font-size:.85rem;';
            row.innerHTML = '<span>' + (item.kind === 'external' ? '&#128279;' : '&#128196;') + '</span>'
                + '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + item.label + '</span>';
            row.onclick = () => {
                pane.querySelectorAll('div').forEach(r => r.style.background = '');
                row.style.background = 'rgba(222,38,38,0.12)';
                _pdfSelectedV2 = { src: item.src, label: item.label };
                document.getElementById('pdf-modal-selected-name-v2').textContent = item.label;
            };
            pane.appendChild(row);
        });
    });
}

function insertPdfV2() {
    const usingUrl = document.getElementById('pdfPaneUrlV2').style.display !== 'none';
    const caption = document.getElementById('pdfCaptionV2').value.trim();
    let src, label;
    if (usingUrl) {
        src = document.getElementById('pdfExternalUrlV2').value.trim();
        if (!src) { alert('Enter a PDF URL first.'); return; }
        label = caption || src;
    } else {
        if (!_pdfSelectedV2) { alert('Select a PDF from the list, or switch to the External URL tab.'); return; }
        src = _pdfSelectedV2.src;
        label = caption || _pdfSelectedV2.label;
    }
    const captionHtml = caption
        ? '\\n<p style="font-size:.9rem;color:#666;margin-top:10px;text-align:center;">' + caption + '</p>'
        : '';
    const snippet = '\\n<div class="bej-pdf-wrap" style="width:100%;margin:30px 0;border:1px solid #e5e5e5;border-radius:4px;overflow:hidden;">\\n'
        + '  <object data="' + src + '" type="application/pdf" style="width:100%;height:820px;display:block;">\\n'
        + '    <div style="padding:40px;text-align:center;background:#f8f8f8;">\\n'
        + '      <p style="font-size:1.1rem;margin-bottom:16px;">Your browser cannot display this PDF inline.</p>\\n'
        + '      <a href="' + src + '" download style="display:inline-block;padding:12px 28px;background:#DE2626;color:#fff;font-weight:700;text-decoration:none;border-radius:4px;">⬇ Download PDF</a>\\n'
        + '    </div>\\n'
        + '  </object>\\n'
        + '</div>' + captionHtml + '\\n';
    const ta = document.getElementById('html_body');
    const pos = ta.selectionStart;
    ta.setRangeText(snippet, pos, pos, 'end');
    ta.focus();
    closePdfPickerV2();
    document.getElementById('pdfExternalUrlV2').value = '';
    document.getElementById('pdfCaptionV2').value = '';
    _pdfSelectedV2 = null;
}

// ── YouTube picker (same "Saved Links / Paste URL" pattern as PDF) ──
var _ytSelectedV2 = null;

function openYtPickerV2() {
    _ytSelectedV2 = null;
    document.getElementById('yt-modal-selected-name-v2').textContent = '';
    ytShowTabV2('library');
    document.getElementById('yt-modal-v2').classList.add('open');
    loadYtListV2();
}

function closeYtPickerV2() {
    document.getElementById('yt-modal-v2').classList.remove('open');
}

function ytShowTabV2(which) {
    const libTab = document.getElementById('ytTabLibraryV2'), urlTab = document.getElementById('ytTabUrlV2');
    const libPane = document.getElementById('ytPaneLibraryV2'), urlPane = document.getElementById('ytPaneUrlV2');
    if (which === 'library') {
        libTab.classList.add('active'); urlTab.classList.remove('active');
        libPane.style.display = 'block'; urlPane.style.display = 'none';
    } else {
        urlTab.classList.add('active'); libTab.classList.remove('active');
        urlPane.style.display = 'block'; libPane.style.display = 'none';
    }
}

function loadYtListV2() {
    const pane = document.getElementById('ytPaneLibraryV2');
    fetch('/api/media/list_video').then(r => r.json()).then(d => {
        pane.innerHTML = '';
        if (!d.ok || !d.items || !d.items.length) {
            pane.innerHTML = '<div style="text-align:center;color:var(--muted);font-size:.85rem;">No saved video links yet — add one via Media &rarr; Links (type: Video), or use the Paste URL/ID tab.</div>';
            return;
        }
        d.items.forEach(item => {
            const row = document.createElement('div');
            row.style = 'padding:8px 4px;cursor:pointer;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;font-size:.85rem;';
            row.innerHTML = '<span>&#9654;</span>'
                + '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + item.label + '</span>';
            row.onclick = () => {
                pane.querySelectorAll('div').forEach(r => r.style.background = '');
                row.style.background = 'rgba(222,38,38,0.12)';
                _ytSelectedV2 = { url: item.url, label: item.label };
                document.getElementById('yt-modal-selected-name-v2').textContent = item.label;
            };
            pane.appendChild(row);
        });
    });
}

function ytIdFromUrlV2(raw) {
    raw = raw.trim();
    if (/^[A-Za-z0-9_-]{11}$/.test(raw)) return raw;
    const m = raw.match(/(?:v=|youtu\\.be\\/|embed\\/)([A-Za-z0-9_-]{11})/);
    return m ? m[1] : null;
}

function insertYtV2() {
    const usingUrl = document.getElementById('ytPaneUrlV2').style.display !== 'none';
    const caption = document.getElementById('ytCaptionV2').value.trim();
    let raw, label;
    if (usingUrl) {
        raw = document.getElementById('ytExternalUrlV2').value.trim();
        if (!raw) { alert('Enter a YouTube URL or ID first.'); return; }
        label = caption || raw;
    } else {
        if (!_ytSelectedV2) { alert('Select a saved video from the list, or switch to the Paste URL/ID tab.'); return; }
        raw = _ytSelectedV2.url;
        label = caption || _ytSelectedV2.label;
    }
    const vid = ytIdFromUrlV2(raw);
    if (!vid) { alert('Could not extract a YouTube video ID from that URL. Try pasting the full watch URL or just the 11-character ID.'); return; }
    const captionHtml = caption
        ? '\\n<p style="font-size:.9rem;color:#666;margin-top:10px;text-align:center;font-style:italic;">' + caption + '</p>'
        : '';
    const snippet = '\\n<div class="bej-video-wrap" style="max-width:800px;margin:40px auto;">\\n'
        + '  <div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;border-radius:8px;border:1px solid #333;background:#000;">\\n'
        + '    <iframe\\n'
        + '      src="https://www.youtube.com/embed/' + vid + '"\\n'
        + '      title="' + (caption || 'YouTube Video') + '"\\n'
        + '      frameborder="0"\\n'
        + '      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"\\n'
        + '      allowfullscreen\\n'
        + '      style="position:absolute;top:0;left:0;width:100%;height:100%;">\\n'
        + '    </iframe>\\n'
        + '  </div>' + captionHtml + '\\n'
        + '</div>\\n';
    const ta = document.getElementById('html_body');
    const pos = ta.selectionStart;
    ta.setRangeText(snippet, pos, pos, 'end');
    ta.focus();
    closeYtPickerV2();
    document.getElementById('ytExternalUrlV2').value = '';
    document.getElementById('ytCaptionV2').value = '';
    _ytSelectedV2 = null;
}

// ── Featured Video (radio-select, separate from in-body Insert) ──
let _featuredVideoLoaded = false;
function toggleFeaturedVideoPanel() {
    const panel = document.getElementById('featured-video-panel');
    const showing = panel.style.display !== 'none';
    panel.style.display = showing ? 'none' : '';
    if (!showing && !_featuredVideoLoaded) loadFeaturedVideoOptions();
}
function loadFeaturedVideoOptions() {
    _featuredVideoLoaded = true;
    fetch('/api/media/list_video').then(r => r.json()).then(items => {
        const list = document.getElementById('featured-video-list');
        if (!items || !items.length) {
            list.innerHTML = '<span style="font-size:.8rem; color:var(--muted);">No saved YouTube videos yet -- add one via the Media Library\\'s YouTube tab.</span>';
            return;
        }
        const currentUrl = document.getElementById('edit_featured_video_url').value;
        list.innerHTML = '';
        items.forEach(function(item, i) {
            const id = 'fv-radio-' + i;
            const row = document.createElement('label');
            row.style = 'display:flex; align-items:center; gap:8px; padding:4px 0; cursor:pointer;';
            const checked = (item.url === currentUrl) ? 'checked' : '';
            row.innerHTML = '<input type="radio" name="featured_video_radio" id="' + id + '" ' + checked + '>'
                + '<span>' + item.label.replace(/</g, '&lt;') + '</span>';
            row.querySelector('input').addEventListener('change', function() { setFeaturedVideo(item.url, item.label); });
            list.appendChild(row);
        });
    }).catch(() => {
        document.getElementById('featured-video-list').innerHTML = '<span style="font-size:.8rem; color:#f87171;">Failed to load saved videos.</span>';
    });
}
function setFeaturedVideo(url, label) {
    document.getElementById('edit_featured_video_url').value = url;
    document.getElementById('featured-video-current').textContent = url ? ('Selected: ' + label) : 'None selected';
}
</script>

<div id="media-modal-v2" class="media-modal-overlay" onclick="if(event.target===this) closeMediaPickerV2()">
    <div class="media-modal-box">
        <div class="media-modal-head">
            <h3>Media Library</h3>
            <button type="button" class="media-modal-close" onclick="closeMediaPickerV2()">&times;</button>
        </div>
        <div id="media-modal-grid-v2" class="media-modal-grid"></div>
        <div id="media-modal-actions-v2" class="media-modal-actions" style="display:none;">
            <span id="media-modal-selected-name-v2" class="selected-name"></span>
            <button type="button" class="btn btn-black btn-sm" onclick="renameMediaV2()">Rename</button>
            <button type="button" class="btn btn-sm" onclick="copyMediaTagV2()">Copy Image Tag</button>
        </div>
    </div>
</div>

<div id="pdf-modal-v2" class="media-modal-overlay" onclick="if(event.target===this) closePdfPickerV2()">
    <div class="media-modal-box" style="max-width:520px;">
        <div class="media-modal-head">
            <h3>Insert PDF</h3>
            <button type="button" class="media-modal-close" onclick="closePdfPickerV2()">&times;</button>
        </div>
        <div style="padding:16px 20px 0;display:flex;gap:0;border-bottom:1px solid var(--border);">
            <button type="button" class="pdf-src-tab-v2 active" id="pdfTabLibraryV2" onclick="pdfShowTabV2('library')">Library</button>
            <button type="button" class="pdf-src-tab-v2" id="pdfTabUrlV2" onclick="pdfShowTabV2('url')">External URL</button>
        </div>
        <div id="pdfPaneLibraryV2" style="padding:16px 20px;max-height:320px;overflow-y:auto;">
            <div style="text-align:center;color:var(--muted);font-size:.85rem;">Loading…</div>
        </div>
        <div id="pdfPaneUrlV2" style="display:none;padding:16px 20px;">
            <label style="font-size:.75rem;color:var(--muted);display:block;margin-bottom:6px;">PDF URL</label>
            <input type="url" id="pdfExternalUrlV2" placeholder="https://example.com/document.pdf" style="width:100%;">
        </div>
        <div style="padding:0 20px 16px;">
            <label style="font-size:.75rem;color:var(--muted);display:block;margin-bottom:6px;">Caption (optional)</label>
            <input type="text" id="pdfCaptionV2" placeholder="Document title or description" style="width:100%;">
        </div>
        <div id="pdf-modal-actions-v2" class="media-modal-actions">
            <span id="pdf-modal-selected-name-v2" class="selected-name"></span>
            <button type="button" class="btn btn-sm" onclick="insertPdfV2()">Insert at Cursor</button>
        </div>
    </div>
</div>

<div id="yt-modal-v2" class="media-modal-overlay" onclick="if(event.target===this) closeYtPickerV2()">
    <div class="media-modal-box" style="max-width:520px;">
        <div class="media-modal-head">
            <h3>Insert YouTube Video</h3>
            <button type="button" class="media-modal-close" onclick="closeYtPickerV2()">&times;</button>
        </div>
        <div style="padding:16px 20px 0;display:flex;gap:0;border-bottom:1px solid var(--border);">
            <button type="button" class="pdf-src-tab-v2 active" id="ytTabLibraryV2" onclick="ytShowTabV2('library')">Saved Links</button>
            <button type="button" class="pdf-src-tab-v2" id="ytTabUrlV2" onclick="ytShowTabV2('url')">Paste URL / ID</button>
        </div>
        <div id="ytPaneLibraryV2" style="padding:16px 20px;max-height:320px;overflow-y:auto;">
            <div style="text-align:center;color:var(--muted);font-size:.85rem;">Loading…</div>
        </div>
        <div id="ytPaneUrlV2" style="display:none;padding:16px 20px;">
            <label style="font-size:.75rem;color:var(--muted);display:block;margin-bottom:6px;">YouTube URL or Video ID</label>
            <input type="url" id="ytExternalUrlV2" placeholder="https://www.youtube.com/watch?v=dQw4w9WgXcQ" style="width:100%;">
        </div>
        <div style="padding:0 20px 16px;">
            <label style="font-size:.75rem;color:var(--muted);display:block;margin-bottom:6px;">Caption (optional)</label>
            <input type="text" id="ytCaptionV2" placeholder="Video title or description" style="width:100%;">
        </div>
        <div id="yt-modal-actions-v2" class="media-modal-actions">
            <span id="yt-modal-selected-name-v2" class="selected-name"></span>
            <button type="button" class="btn btn-sm" onclick="insertYtV2()">Insert at Cursor</button>
        </div>
    </div>
</div>
</body>
</html>
"""

@app.route('/')
def main_v2():
    db.mount()
    authors = db.get_records("AuthorProfile")
    cats    = db.get_records("Category")
    pages   = db.get_records("PageRecord")
    return render_template_string(_SHELL, 
                                   categories=cats, 
                                   authors=authors, 
                                   pages=pages,
                                   default_html=DEFAULT_HTML,
                                   admin_url=f"http://localhost:{ADMIN_PORT}/")

if __name__ == "__main__":
    _legacy = [f for f in ["Flask_CMS.py", "Flask_CMS_Publisher.py", "Flask_Page_Editor.py",
                            "Flask_Profile_Manager.py", "Page_Editor_v2.py"]
               if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), f))]
    if _legacy:
        print(f"\n    !! WARNING: old pre-rename file(s) still present: {', '.join(_legacy)} -- delete them, they are unmaintained leftovers from before the Blueprint split.\n")
    # Port resolved via config.json (pageeditorv2_port) / CMS_PAGEEDITORV2_PORT env.
    app.run(host="0.0.0.0", port=PAGEEDITORV2_PORT, debug=False)
