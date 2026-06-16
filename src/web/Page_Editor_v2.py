#!/usr/bin/env python3
"""
SCRIPT_NAME:    Flask_Page_Editor_v2
SCRIPT_VERSION: 18.0
AUTHOR:         Elton Boehnen
DESCRIPTION:    Editor v2 with Stabilized Sidebar, Tasking Workflow, and Gemini Config.
                Unified with CMS Data Model and Storage Format.
"""

from flask import Flask, render_template_string, request, redirect, flash, jsonify, send_file, Response
import os, re, uuid, json, sys, html as _html, io
from datetime import datetime

# --- BEJSON Core Pathing ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB_DIR = os.path.join(PROJECT_ROOT, "src", "lib")
if LIB_DIR not in sys.path: sys.path.append(LIB_DIR)
import lib_cms_core as CMSCore
import lib_cms_persona_writer
from lib_bejson_env import resolve_path

# --- Config ---
MFDB_DIR = os.path.join(PROJECT_ROOT, "storage", "mfdb")
MANIFEST_PATH = os.path.join(MFDB_DIR, "site_master", "104a.mfdb.bejson")
PAGES_DB_DIR = os.path.join(MFDB_DIR, "pages_db")
CONTEXT_DIR = os.path.join(PROJECT_ROOT, "Context")
os.makedirs(CONTEXT_DIR, exist_ok=True)

GEMINI_KEYS_PATH = os.path.expanduser("~/.env/gemini_keys.bejson")
MODEL_REGISTRY_PATH = resolve_path("{INTERNAL_STORAGE}/Admin/resources/Schemas/gemini_model_registry.104a.bejson")
STORAGE_CONFIG_PATH = resolve_path("{INTERNAL_STORAGE}/Admin/resources/Flask_Components/Component-File_Selector/config/path_config.104a.bejson")

# =============================================================================
# APP INITIALIZATION
# =============================================================================

app = Flask(__name__)
app.secret_key = 'editor-v2-ultimate-key'

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
        file.save(os.path.join(CONTEXT_DIR, file.filename))
        return jsonify({"ok": True, "msg": f"Uploaded {file.filename}"})
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
    if not prompt: return jsonify({"ok": False, "error": "Prompt required"})
    
    plan_sys_inst = "You are an expert content architect. Break down the request into a JSON array of objects: [{\"title\": \"...\", \"prompt\": \"...\"}]"
    key = writer._get_key()
    if not key: return jsonify({"ok": False, "error": "No API keys found"})
    
    import requests
    payload = {
        "contents": [{"parts": [{"text": f"Build a plan for: {prompt}"}]}],
        "system_instruction": {"parts": [{"text": plan_sys_inst}]},
        "generationConfig": {"response_mime_type": "application/json"}
    }
    try:
        res = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}", json=payload, timeout=90)
        res.raise_for_status()
        tasks = json.loads(res.json()["candidates"][0]["content"]["parts"][0]["text"])
        return jsonify({"ok": True, "tasks": tasks})
    except Exception as e: return jsonify({"ok": False, "error": str(e)})

@app.route('/api/tasking/execute_task', methods=['POST'])
def api_execute_task():
    data = request.json
    task_title, task_prompt, full_plan = data.get('title'), data.get('prompt'), data.get('full_plan', [])
    model = data.get('model', 'gemini-2.5-flash')
    if not task_prompt: return jsonify({"ok": False, "error": "Prompt required"})
    
    plan_context = "\n".join([f"- {t['title']}" for t in full_plan])
    exec_sys_inst = f"Document Plan:\n{plan_context}\n\nTask: {task_title}\nOutput ONLY clean HTML body content. No ``` tags."
    key = writer._get_key()
    if not key: return jsonify({"ok": False, "error": "No API keys found"})
    
    import requests
    payload = {"contents": [{"parts": [{"text": task_prompt}]}], "system_instruction": {"parts": [{"text": exec_sys_inst}]}}
    try:
        res = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}", json=payload, timeout=120)
        res.raise_for_status()
        content = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        if content.startswith("```"): content = re.sub(r'^```html?\n?|\n?```$', '', content)
        return jsonify({"ok": True, "content": content})
    except Exception as e: return jsonify({"ok": False, "error": str(e)})

# =============================================================================
# CMS INTEGRATION API
# =============================================================================

def _get_page_body_v1(page_uuid):
    """Read html_body from pages_db/<uuid>.json — returns empty string if missing."""
    import lib_bejson_core as Core
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
    
    db.mount()
    existing = next((x for x in db.get_records("PageRecord") if x['page_uuid'] == uuid_val), None)
    
    rec = {
        "page_uuid":    uuid_val,
        "page_title":   title,
        "page_slug":    re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-'),
        "category_ref": cat,
        "item_type":    "page",
        "created_at":   datetime.now().strftime("%Y-%m-%d"),
        "external_url": None,
        "author_ref":   author,
        "featured_img": None,
        "template_key": tpl_key
    }
    
    if existing:
        # Preserve created_at and featured_img if they exist
        rec["created_at"] = existing.get("created_at", rec["created_at"])
        rec["featured_img"] = existing.get("featured_img")
        db.update_record("PageRecord", "page_uuid", uuid_val, rec)
    else:
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
    db.add_record("Category", {"category_name": name, "category_slug": name.lower().replace(" ","-")})
    return jsonify({"ok": True})

@app.route('/api/settings/export_keys')
def api_export_keys():
    try:
        import subprocess
        # Simplified path for export - using project root/storage/tmp
        out_path = os.path.join(PROJECT_ROOT, "storage", "tmp", "gemini_keys_export.bejson")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        subprocess.run(["python3", resolve_path("{INTERNAL_STORAGE}/Admin/tools/gemini_key_manager.py"), "--export", out_path], check=True)
        return jsonify({"ok": True, "msg": f"Template exported to {out_path}"})
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
        subprocess.run(["python3", resolve_path("{INTERNAL_STORAGE}/Admin/tools/gemini_key_manager.py"), "--import-keys", tmp_path], check=True)
        return jsonify({"ok": True, "msg": "Keys imported successfully."})
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
        
        .status-bar { margin-top: 15px; display: flex; justify-content: space-between; font-size: 0.7rem; font-family: var(--mono); color: var(--muted); }
        
        .task-card { background:#000; border:1px solid var(--border); border-radius:8px; padding:15px; margin-bottom:10px; }
        .task-title { font-weight:700; color:var(--acc); margin-bottom:10px; font-size:0.9rem; }
        
        .attachment-pill { padding:6px 12px; background:#111; border:1px solid var(--border); border-radius:20px; font-size:0.75rem; cursor:pointer; }
        .attachment-pill.selected { border-color:var(--acc); background:rgba(222,38,38,0.1); }
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
    <a href="http://localhost:5001" style="margin-top:auto; border-top:1px solid var(--border);">Back to CMS</a>
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
                        {% for c in categories %}<option value="{{c.category_name}}">{{c.category_name}}</option>{% endfor %}
                    </select>
                </div>
                <div class="fg" style="flex:1;">
                    <label>Target Page</label>
                    <select id="pageSelect">
                        <option value="">-- Select --</option>
                        {% for p in pages %}<option value="{{p.page_uuid}}" data-cat="{{p.category_ref}}">{{p.page_title}}</option>{% endfor %}
                    </select>
                </div>
            </div>
            <div class="flex-row" style="margin-bottom:25px;">
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
            <div class="fg">
                <label>Author</label>
                <select id="edit_author">
                    {% for a in authors %}<option value="{{a.auth_name}}">{{a.auth_name}}</option>{% endfor %}
                </select>
            </div>
            <textarea id="html_body"></textarea>
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
            <div class="flex-row" style="margin-bottom:20px;">
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
                <div class="flex-row">
                    <button class="btn btn-black btn-sm" onclick="exportKeyTemplate()">Export</button>
                    <input type="file" id="key_import_file" accept=".bejson" style="max-width:200px; padding:5px;">
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
        <div class="flex-row">
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
        document.getElementById('edit_author').value = data.page.author_ref || '';
        document.getElementById('edit_template').value = data.page.template_key || 'blank';
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
    const cat = document.getElementById('catSelect').value;
    const content = document.getElementById('html_body').value;
    const template_key = document.getElementById('edit_template').value;
    
    if(!title) { alert('Title required'); return; }

    const res = await fetch('/api/save', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({page_uuid: uuid, title, author, category: cat, content, template_key})
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
    if(!prompt) return;
    document.getElementById('status_msg').innerText = 'GENERATING PLAN...';
    const res = await fetch('/api/tasking/generate_plan', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({prompt, model})
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
    for(let i=0; i<currentPlan.length; i++) {
        const t = currentPlan[i];
        document.getElementById(`task-res-${i}`).innerText = 'EXECUTING...';
        const res = await fetch('/api/tasking/execute_task', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({title: t.title, prompt: t.prompt, full_plan: currentPlan, model})
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
</script>
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
                                   default_html=DEFAULT_HTML)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003, debug=True)
