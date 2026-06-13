#!/usr/bin/env python3
"""
SCRIPT_NAME:    Flask_Page_Editor_v2
SCRIPT_VERSION: 16.0
AUTHOR:         Elton Boehnen
DESCRIPTION:    Editor v2 with Stabilized Sidebar, Tasking Workflow, and Gemini Config.
"""

from flask import Flask, render_template_string, request, redirect, flash, jsonify, send_file
import os, re, uuid, json, sys, html as _html, io
from datetime import datetime

# --- BEJSON Core Pathing ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB_DIR = os.path.join(PROJECT_ROOT, "src", "lib")
if LIB_DIR not in sys.path: sys.path.append(LIB_DIR)
import lib_cms_core as CMSCore
import lib_persona_writer
from lib_bejson_env import resolve_path

# --- Config ---
MFDB_DIR = os.path.join(PROJECT_ROOT, "storage", "mfdb")
MANIFEST_PATH = os.path.join(MFDB_DIR, "site_master", "104a.mfdb.bejson")
PAGES_DB_DIR = os.path.join(MFDB_DIR, "pages_db")
CONTEXT_DIR = os.path.join(PROJECT_ROOT, "Context")
os.makedirs(CONTEXT_DIR, exist_ok=True)

# --- Python API Logic ---

# --- Storage & Context Component Logic ---
STORAGE_CONFIG_PATH = "" + os.path.dirname(os.path.dirname(os.path.dirname(PROJECT_ROOT))) + "/resources/Flask_Components/Component-File_Selector/config/path_config.104a.bejson"

def load_storage_config():
    if not os.path.exists(STORAGE_CONFIG_PATH): return {}
    with open(STORAGE_CONFIG_PATH, "r") as f: return json.load(f)

def save_storage_config(data):
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
        # Check both the enabled path and the default Context dir
        path = os.path.join(enabled_path, f)
        if not os.path.exists(path): path = os.path.join(CONTEXT_DIR, f)
        
        if os.path.exists(path):
            try:
                with open(path, "r") as f_in: 
                    text = f_in.read()
                    content += f"
--- REFERENCE FILE: {f} ---
{text}
"
            except: pass
    return content


GEMINI_KEYS_PATH = os.path.expanduser("~/.env/gemini_keys.bejson")
MODEL_REGISTRY_PATH = resolve_path("{INTERNAL_STORAGE}/Admin/resources/Schemas/gemini_model_registry.104a.bejson")

app = Flask(__name__)

@app.after_request
def add_cors_headers(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,PUT,POST,DELETE,OPTIONS")
    return response

app.secret_key = 'editor-v2-ultimate-key'
db = CMSCore.CMSCore(MANIFEST_PATH)
writer = lib_persona_writer.PersonaWriter(MANIFEST_PATH)

# --- Python API Logic ---

# --- Storage & Context Component Logic ---
STORAGE_CONFIG_PATH = "" + os.path.dirname(os.path.dirname(os.path.dirname(PROJECT_ROOT))) + "/resources/Flask_Components/Component-File_Selector/config/path_config.104a.bejson"

def load_storage_config():
    if not os.path.exists(STORAGE_CONFIG_PATH): return {}
    with open(STORAGE_CONFIG_PATH, "r") as f: return json.load(f)

def save_storage_config(data):
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

@app.route('/api/get/<uuid>')
def api_get(uuid):
    db.mount()
    pages = db.get_records("PageRecord")
    p = next((x for x in pages if x['page_uuid'] == uuid), None)
    if not p: return jsonify({"ok": False})
    path = os.path.join(PAGES_DB_DIR, f"{uuid}.json")
    try:
        with open(path, 'r') as f: content = json.load(f).get('html_content', '')
        return jsonify({"ok": True, "page": p, "content": content})
    except: return jsonify({"ok": False})

@app.route('/api/save', methods=['POST'])
def api_save():
    data = request.json
    uuid_val = data.get('page_uuid') or str(uuid.uuid4())
    title, author, cat, content = data.get('title'), data.get('author'), data.get('category'), data.get('content')
    
    db.mount()
    existing = next((x for x in db.get_records("PageRecord") if x['page_uuid'] == uuid_val), None)
    
    rec = {
        "Record_Type_Parent": "PageRecord", "page_uuid": uuid_val, "page_title": title,
        "author_ref": author, "category_ref": cat, "created_at": datetime.now().isoformat(),
        "item_type": "page", "slug": title.lower().replace(" ", "-")
    }
    
    if existing: db.update_record("PageRecord", "page_uuid", uuid_val, rec)
    else: db.add_record("PageRecord", rec)
    
    os.makedirs(PAGES_DB_DIR, exist_ok=True)
    with open(os.path.join(PAGES_DB_DIR, f"{uuid_val}.json"), 'w') as f:
        json.dump({"html_content": content}, f, indent=2)
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
    db.add_record("Category", {"Record_Type_Parent": "Category", "category_name": name})
    return jsonify({"ok": True})


@app.route('/api/settings/export_keys')
def api_export_keys():
    try:
        import subprocess
        subprocess.run(["python3", resolve_path("{INTERNAL_STORAGE}/Admin/tools/gemini_key_manager.py"), "--export", resolve_path("{INTERNAL_STORAGE}/Admin/storage/tmp/gemini_keys_export.bejson")], check=True)
        return jsonify({"ok": True, "msg": "Template exported to " + os.path.dirname(os.path.dirname(os.path.dirname(PROJECT_ROOT))) + "/storage/tmp/gemini_keys_export.bejson"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route('/api/settings/import_keys', methods=['POST'])
def api_import_keys():
    try:
        file = request.files.get('file')
        if not file: return jsonify({"ok": False, "error": "No file uploaded"})
        tmp_path = resolve_path("{INTERNAL_STORAGE}/Admin/storage/tmp/import_keys_upload.bejson")
        os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
        file.save(tmp_path)
        import subprocess
        subprocess.run(["python3", resolve_path("{INTERNAL_STORAGE}/Admin/tools/gemini_key_manager.py"), "--import-keys", tmp_path], check=True)
        return jsonify({"ok": True, "msg": "Keys imported successfully."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route('/api/debug_keys')
def debug_keys():
    import os
    path = os.path.expanduser("~/.env/gemini_keys.bejson")
    exists = os.path.exists(path)
    return jsonify({
        "path": path,
        "exists": exists,
        "keys": writer.api_keys,
        "cwd": os.getcwd()
    })

# --- UI Definitions ---

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

        /* --- THE ULTIMATE SIDEBAR --- */
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

        /* --- Main UI --- */
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
        .flex-row { display: flex; gap: 15px; align-items: center; }
        
        .status-bar { margin-top: 15px; display: flex; justify-content: space-between; font-size: 0.7rem; font-family: var(--mono); color: var(--muted); }
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
            <div class="fg">
                <label>Page Title</label>
                <input type="text" id="edit_title" placeholder="Untitled">
            </div>
            <div class="fg">
                <label>Author</label>
                <select id="edit_author">
                    {% for a in authors %}<option value="{{a.auth_name}}">{{a.auth_name}}</option>{% endfor %}
                </select>
            </div>
            <textarea id="html_body"></textarea>
            <div class="status-bar" style="margin-top: 15px;">
                <div>SYSTEM: <span style="color:var(--acc);">READY</span></div>
            </div>
            <div class="status-bar" style="margin-top: 5px;">
                <div id="status_msg">IDLE</div>
            </div>
        </div>
    </div>

    
    <div id="t-context" class="tab-content">
        <div class="editor-wrap">
            <h2>Context & Attachments</h2>
            <p style="color:var(--muted); margin-bottom:20px;">Configure storage and attach context files.</p>
            
            <div id="path-config-root" style="background:#080808; padding:20px; border-radius:12px; border:1px solid var(--border); position:relative; margin-bottom:25px;">
                <div id="status-dot" style="position:absolute; top:20px; right:20px; width:8px; height:8px; border-radius:50%; background:#2ecc71; opacity:0; transition:opacity 0.3s;"></div>
                <h3 style="margin-bottom:15px; font-size:1rem;">Storage Path Configuration</h3>
                <div id="storage-radios" style="display:flex; gap:20px; margin-bottom:15px;"></div>
                <input type="text" id="path-input" oninput="autoSaveStorage()" 
                       style="background:#000; border:1px solid var(--border); color:#fff; padding:12px; border-radius:8px; font-family:var(--mono); font-size:0.85rem; margin-bottom:15px;">
                
                <div style="display:flex; align-items:center; gap:10px; border-top:1px solid var(--border); padding-top:20px;">
                    <span style="font-size:0.7rem; color:var(--muted); font-weight:800; text-transform:uppercase;">Quick Import</span>
                    <button class="btn btn-black btn-sm" onclick="loadStorageFiles()">Scan Path</button>
                    <button class="btn btn-black btn-sm">FOLDER</button>
                    <button class="btn btn-black btn-sm">ZIP</button>
                </div>
            </div>

            <div class="editor-wrap" style="background:rgba(255,255,255,0.02); border-style:dashed;">
                <h4 style="margin-bottom:15px;">Available Files</h4>
                <div id="attachment_list" style="display:flex; flex-wrap:wrap; gap:10px; min-height:40px; margin-bottom:15px;"></div>
                <p style="font-size:0.7rem; color:var(--muted);">Select files to use as context for AI generation.</p>
            </div>
        </div>
    </div>

    <div id="t-tasking" class="tab-content">
        <div class="editor-wrap">
            <h2>AI Content Architect</h2>
            <p style="color:var(--muted); margin-bottom:20px;">Build and execute multi-tiered content plans.</p>
            <textarea id="task_prompt" style="min-height:150px; margin-bottom:20px;" placeholder="What are we building today?"></textarea>
            <div class="flex-row" style="margin-bottom:10px;">
                <button class="btn btn-green" onclick="generateTaskPlan()">Generate Plan</button>
                <button class="btn" onclick="runTaskingPlan()">Execute All</button>
                <button class="btn btn-black" onclick="importPlanToEditor()">Import to Editor</button>
            </div>
            <div style="margin-bottom:30px;">
                <span id="task_status" style="color:var(--muted); font-size:0.8rem; font-family:var(--mono);">IDLE</span>
            </div>
            <div id="task_container" style="display:flex; flex-direction:column; gap:15px;"></div>
        </div>
    </div>

    <div id="t-settings" class="tab-content">
        <div class="editor-wrap">
            <h2>System Config</h2>
            <div class="fg" style="margin-top:20px;">
                <label>Active Model</label>
                <select id="model_select"></select>
            </div>
                        <button class="btn btn-black" onclick="loadModels()">Refresh Registry</button>
            <div class="fg" style="margin-top:20px;">
                <label>Key Registry Management</label>
                <div class="flex-row">
                    <button class="btn btn-black" onclick="exportKeyTemplate()">Export Template</button>
                    <input type="file" id="key_import_file" accept=".bejson" style="max-width:250px;">
                    <button class="btn btn-black" onclick="importKeys()">Import Keys</button>
                </div>
                <div id="key_status" style="margin-top:10px; font-size:0.8rem; font-family:var(--mono); color:var(--acc);"></div>
            </div>
        </div>
    </div>
</div>

<div id="newModal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.9); z-index:9000; align-items:center; justify-content:center;">
    <div class="editor-wrap" style="width:400px;">
        <h3>New Asset</h3>
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
let isDirty = false;

function toggleMenu() {
    const menu = document.getElementById('s-menu');
    const overlay = document.getElementById('m-overlay');
    menu.classList.toggle('open');
    overlay.classList.toggle('active');
}

function showTab(id) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-link').forEach(l => l.classList.remove('active'));
    document.getElementById('t-' + id).classList.add('active');
    document.getElementById('l-' + id).classList.add('active');
    if(id === 'settings') loadModels(); initStorage();
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
        document.getElementById('edit_author').value = data.page.author_ref;
        document.getElementById('html_body').value = data.content;
        document.getElementById('status_msg').innerText = 'LOADED';
        isDirty = false;
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
    
    const res = await fetch('/api/save', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({page_uuid: uuid, title, author, category: cat, content})
    });
    if((await res.json()).ok) { alert('Saved!'); location.reload(); }
}

function openNewModal() { document.getElementById('newModal').style.display = 'flex'; }
function closeModal() { document.getElementById('newModal').style.display = 'none'; }
function createNewDraft() {
    const title = document.getElementById('modal_input').value;
    document.getElementById('hidden_uuid').value = '';
    document.getElementById('edit_title').value = title;
    document.getElementById('html_body').value = DEFAULT_HTML;
    closeModal();
}


async function exportKeyTemplate() {
    const status = document.getElementById('key_status');
    status.innerText = 'EXPORTING...';
    try {
        const res = await fetch('/api/settings/export_keys');
        const data = await res.json();
        status.innerText = data.ok ? data.msg : 'ERROR: ' + data.error;
    } catch(err) {
        console.error(err); status.innerText = 'ERROR: ' + err.message;
    }
}

async function importKeys() {
    const fileInput = document.getElementById('key_import_file');
    const status = document.getElementById('key_status');
    if(!fileInput.files.length) { status.innerText = 'SELECT A FILE FIRST'; return; }
    
    status.innerText = 'IMPORTING...';
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    
    try {
        const res = await fetch('/api/settings/import_keys', { method: 'POST', body: formData });
        const data = await res.json();
        status.innerText = data.ok ? data.msg : 'ERROR: ' + data.error;
    } catch(err) {
        console.error(err); status.innerText = 'ERROR: ' + err.message;
    }
}

async function loadModels() {
    const res = await fetch('/api/settings/models');
    const data = await res.json();
    const sel = document.getElementById('model_select');
    sel.innerHTML = '';
    data.models.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m.model_id; opt.textContent = m.model_name;
        sel.appendChild(opt);
    });
}


// Storage & Context Logic
let storagePaths = {};
let currentStorageType = "Internal";
let storageSaveTimeout;
let activeAttachments = [];

async function initStorage() {
    const res = await fetch('/api/storage/config');
    const data = await res.json();
    if(data.ok) {
        storagePaths = data.paths;
        renderStorageUI();
    }
}

function renderStorageUI() {
    const cont = document.getElementById('storage-radios');
    if(!cont) return;
    cont.innerHTML = '';
    Object.keys(storagePaths).forEach(type => {
        if(storagePaths[type].enabled) {
            const checked = type === currentStorageType ? 'checked' : '';
            cont.innerHTML += `<label style="display:flex; align-items:center; gap:8px; cursor:pointer; font-size:0.8rem;">
                <input type="radio" name="storage" value="${type}" ${checked} onchange="switchStorageType('${type}')"> ${type}
            </label>`;
            if(checked) document.getElementById('path-input').value = storagePaths[type].path;
        }
    });
}

function switchStorageType(type) {
    storagePaths[currentStorageType].path = document.getElementById('path-input').value;
    currentStorageType = type;
    document.getElementById('path-input').value = storagePaths[type].path;
    saveStorage();
}

function autoSaveStorage() {
    clearTimeout(storageSaveTimeout);
    storageSaveTimeout = setTimeout(saveStorage, 500);
}

async function saveStorage() {
    storagePaths[currentStorageType].path = document.getElementById('path-input').value;
    const dot = document.getElementById('status-dot');
    dot.style.opacity = '1';
    const res = await fetch('/api/storage/config', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(storagePaths)
    });
    if(res.ok) setTimeout(() => dot.style.opacity = '0', 1000);
}

async function loadStorageFiles() {
    const res = await fetch('/api/storage/list_files');
    const data = await res.json();
    const cont = document.getElementById('attachment_list');
    cont.innerHTML = '';
    if(data.ok) {
        data.files.forEach(f => {
            const isAttached = activeAttachments.includes(f);
            cont.innerHTML += `<div style="background:var(--bg); border:1px solid var(--border); padding:8px 12px; border-radius:6px; font-size:0.75rem; display:flex; align-items:center; gap:10px;">
                <span>${f}</span>
                <input type="checkbox" onchange="toggleAttachment('${f}')" ${isAttached ? 'checked' : ''}>
            </div>`;
        });
    } else alert(data.error);
}

function toggleAttachment(file) {
    if(activeAttachments.includes(file)) activeAttachments = activeAttachments.filter(a => a !== file);
    else activeAttachments.push(file);
}

// Tasking
async function generateTaskPlan() {
    const prompt = document.getElementById('task_prompt').value;
    const status = document.getElementById('task_status');
    if(status) { status.innerText = 'GENERATING PLAN...'; status.style.color = '#fff'; }
    try {
        const res = await fetch('/api/tasking/generate_plan', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({prompt, model: document.getElementById('model_select').value})
        });
        const data = await res.json();
        if(data.ok) {
            
            const cont = document.getElementById('task_container');
            cont.innerHTML = '';
            data.tasks.forEach((t, i) => {
                cont.innerHTML += `<div class="editor-wrap" id="task-${i}">
                    <b>${t.title}</b>
                    <textarea class="t-prompt" style="min-height:80px; margin-top:10px;">${t.prompt}</textarea>
                    <div class="t-output" style="margin-top:10px; background:#000; padding:10px; font-size:0.8rem; display:none;"></div>
                </div>`;
            });
        } else {
            if(status) { status.innerText = 'ERROR: ' + (data.error || 'Unknown error'); status.style.color = '#991b1b'; }
        }
    } catch(err) {
        if(status) { console.error(err); status.innerText = 'ERROR: ' + err.message; status.style.color = '#991b1b'; }
    }
}

async function runTaskingPlan() {
    const tasks = document.querySelectorAll('#task_container .editor-wrap');
    const full_plan = Array.from(tasks).map(t => ({title: t.querySelector('b').innerText, prompt: t.querySelector('textarea').value}));
    
    for(let i=0; i < tasks.length; i++) {
        const out = tasks[i].querySelector('.t-output');
        out.style.display = 'block'; out.innerText = 'Working...';
        const res = await fetch('/api/tasking/execute_task', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({title: full_plan[i].title, prompt: full_plan[i].prompt, full_plan, model: document.getElementById('model_select').value})
        });
        const data = await res.json();
        if(data.ok) out.innerHTML = data.content;
    }
}

function importPlanToEditor() {
    let html = '';
    document.querySelectorAll('.t-output').forEach(out => html += out.innerHTML + '\\n');
    document.getElementById('html_body').value = html;
    showTab('editor');
}

// Initialize data on load
window.addEventListener('DOMContentLoaded', () => {
    loadModels(); initStorage();
});
</script>
</body></html>"""

@app.route('/')
def r_index():
    db.mount()
    pages = sorted(db.get_records("PageRecord"), key=lambda x: x.get("created_at", ""), reverse=True)
    cats = db.get_records("Category")
    authors = db.get_records("AuthorProfile")
    return render_template_string(_SHELL, pages=pages, categories=cats, authors=authors, default_html=DEFAULT_HTML)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5010, debug=True, use_reloader=False)
