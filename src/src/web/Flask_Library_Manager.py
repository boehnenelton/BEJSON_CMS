import os
import sys
import json
import uuid
import hashlib
from datetime import datetime
from flask import Flask, request, redirect, render_template_string, flash, jsonify

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(PROJECT_ROOT, 'src', 'lib'))
import lib_cms_core as CMSCore

MANIFEST_PATH = os.path.join(PROJECT_ROOT, 'storage', 'mfdb', 'site_master', '104a.mfdb.bejson')
LIBS_SOURCE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(PROJECT_ROOT))), "libraries")

app = Flask(__name__)
app.secret_key = 'bejson-library-manager-key'
db = CMSCore.CMSCore(MANIFEST_PATH)

def get_file_checksum(path):
    try:
        md5 = hashlib.md5()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                md5.update(chunk)
        return md5.hexdigest()
    except: return None

def parse_lib_header(path):
    meta = {"name": os.path.basename(path), "version": "1.0.0", "status": "Stable", "description": ""}
    try:
        with open(path, 'r') as f:
            content = f.read(2000) # Read first 2KB
            # Look for "Library:", "Version:", "Status:", "Description:"
            name_m = re.search(r"Library:\s+([^\n]+)", content)
            if name_m: meta["name"] = name_m.group(1).strip()
            
            ver_m = re.search(r"Version:\s+([^\n]+)", content)
            if ver_m: meta["version"] = ver_m.group(1).strip()
            
            stat_m = re.search(r"Status:\s+([^\n]+)", content)
            if stat_m: meta["status"] = stat_m.group(1).strip()
            
            desc_m = re.search(r"Description:\s+([^\n]+(?:\n\s+[^\n]+)*)", content)
            if desc_m: meta["description"] = desc_m.group(1).strip()
    except: pass
    return meta

import re

_T = """
<!DOCTYPE html><html><head><title>Library Manager</title>
<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800;900&display=swap' rel='stylesheet'>
<style>
    :root{ --bg:#0b0b0b; --c:#161616; --acc:#00FF41; --f:#fff; --m:#71767B; --b:#2F3336; }
    *{box-sizing:border-box; margin:0; padding:0;}
    body{background:var(--bg); color:var(--f); font-family:'Inter',sans-serif; display:flex; height:100vh;}
    .sidebar{width:300px; border-right:1px solid var(--b); background:var(--c); display:flex; flex-direction:column;}
    .main{flex:1; overflow-y:auto; padding:30px;}
    .nav-header{padding:20px; border-bottom:1px solid var(--b); font-weight:900; letter-spacing:1px; text-transform:uppercase; display:flex; justify-content:space-between; align-items:center;}
    .family-tree{flex:1; overflow-y:auto; padding:10px;}
    .family-item{padding:8px 12px; border-radius:8px; cursor:pointer; font-size:0.9rem; display:flex; justify-content:space-between; align-items:center; margin-bottom:2px;}
    .family-item:hover{background:rgba(255,255,255,0.05);}
    .family-item.active{background:var(--acc); color:#000; font-weight:800;}
    .card{background:var(--c); border:1px solid var(--b); border-radius:12px; padding:20px; margin-bottom:20px;}
    .grid{display:grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap:20px;}
    .lib-card{background:#000; border:1px solid var(--b); border-radius:12px; padding:15px; position:relative;}
    .badge{font-size:0.65rem; font-weight:900; padding:2px 8px; border-radius:4px; text-transform:uppercase;}
    .b-sh{background:#f1c40f; color:#000;} .b-py{background:#3498db; color:#fff;} .b-js{background:#f39c12; color:#000;}
    input, textarea, select{width:100%; background:#000; border:1px solid var(--b); padding:10px; color:#fff; margin:10px 0; border-radius:8px; font-family:inherit;}
    button{background:var(--acc); color:#000; border:none; padding:10px 20px; border-radius:8px; font-weight:800; cursor:pointer;}
    .btn-grey{background:var(--b); color:var(--f); padding:10px 20px; border-radius:8px; text-decoration:none; font-weight:800; display:inline-block;}
</style></head><body>
    <div class='sidebar'>
        <div class='nav-header'>Families <button onclick='showAddFamily()' style='padding:4px 8px; font-size:0.8rem;'>+</button></div>
        <div class='family-tree'>
            <div class='family-item {{ "active" if not active_family }}' onclick="window.location.href='/'">All Libraries</div>
            {% for f in families %}
                <div class='family-item {{ "active" if active_family == f.family_id }}' onclick="window.location.href='?f={{f.family_id}}'">
                    <span>{{ f.name }}</span>
                    <span style='color:var(--m); font-size:0.7rem;'>/{{f.slug}}</span>
                </div>
            {% endfor %}
        </div>
        <div style='padding:20px; border-top:1px solid var(--b);'>
            <button onclick="syncLibraries()" style='width:100%; background:var(--f);'>Sync Source</button>
        </div>
    </div>
    <div class='main'>
        <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:30px;'>
            <div>
                <h1 style='font-size:2.5rem; font-weight:900;'>{{ family_name if active_family else "Global Registry" }}</h1>
                <p style='color:var(--m);'>{{ family_desc if active_family else "All registered BEJSON libraries." }}</p>
            </div>
            <button onclick="showAddLib()">+ Register Library</button>
        </div>

        {% with messages = get_flashed_messages() %}{% for m in messages %}<div class='card' style='border-color:var(--acc); color:var(--acc);'>{{m}}</div>{% endfor %}{% endwith %}

        <div class='grid'>
            {% for l in libraries %}
            <div class='lib-card'>
                <div style='display:flex; justify-content:space-between;'>
                    <span class='badge b-{{l.language}}'>{{l.language}}</span>
                    <span style='color:var(--m); font-size:0.8rem;'>v{{l.version}}</span>
                </div>
                <h3 style='margin:10px 0;'>{{l.name}}</h3>
                <p style='color:var(--m); font-size:0.85rem; height:60px; overflow:hidden;'>{{l.description or "No description provided in header."}}</p>
                <div style='font-size:0.7rem; color:#444; margin-top:10px;'>{{ l.checksum[:16] }}...</div>
                <div style='margin-top:15px; display:flex; gap:10px;'>
                    <button style='flex:1; font-size:0.75rem;' onclick="editLib('{{l.lib_id}}')">Manage</button>
                    <a href='#' class='btn-grey' style='padding:8px;' title='View Source'>&lt;/&gt;</a>
                </div>
            </div>
            {% endfor %}
        </div>
        {% if not libraries %}
        <div class='card' style='text-align:center; padding:50px; color:var(--m);'>
            <h3>No libraries found in this family.</h3>
            <p>Click "Sync Source" or manually register a library.</p>
        </div>
        {% endif %}
    </div>

    <!-- Modals -->
    <div id='modal' style='display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.8); z-index:1000; align-items:center; justify-content:center;'>
        <div class='card' style='width:400px; border-top: 4px solid var(--acc);'>
            <h2 id='modal-title'>Add Item</h2>
            <form id='modal-form' action='/save' method='POST'>
                <input type='hidden' name='type' id='item-type'>
                <input type='hidden' name='id' id='item-id'>
                <div id='form-fields'></div>
                <div style='display:flex; gap:10px; margin-top:15px;'>
                    <button type='submit'>Save Changes</button>
                    <button type='button' class='btn-grey' onclick="document.getElementById('modal').style.display='none'">Cancel</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        function showAddFamily() {
            document.getElementById('modal').style.display='flex';
            document.getElementById('modal-title').innerText = 'New Family';
            document.getElementById('item-type').value = 'family';
            document.getElementById('form-fields').innerHTML = `
                <input name='name' placeholder='Family Name' required>
                <input name='slug' placeholder='Slug (lowercase)' required>
                <select name='parent'><option value=''>No Parent (Root)</option>
                {% for f in families %}<option value='{{f.family_id}}'>{{f.name}}</option>{% endfor %}
                </select>
                <textarea name='desc' placeholder='Description' rows='3'></textarea>
            `;
        }
        function showAddLib() {
            document.getElementById('modal').style.display='flex';
            document.getElementById('modal-title').innerText = 'Register Library';
            document.getElementById('item-type').value = 'library';
            document.getElementById('form-fields').innerHTML = `
                <input name='name' placeholder='Library Name' required>
                <input name='slug' placeholder='Slug' required>
                <select name='family_id'><option value=''>Uncategorized</option>
                {% for f in families %}<option value='{{f.family_id}}' {{'selected' if active_family == f.family_id}}>{{f.name}}</option>{% endfor %}
                </select>
                <input name='version' placeholder='Version (e.g. 1.5.0)'>
                <select name='language'><option value='py'>Python</option><option value='js'>JavaScript</option><option value='sh'>Shell</option></select>
            `;
        }
        function syncLibraries() {
            if(confirm("Scan " + {{ LIBS_SOURCE_DIR|tojson }} + " for new libraries?")) {
                window.location.href = '/sync';
            }
        }
    </script>
</body></html>"""

@app.route('/')
def index():
    active_family = request.args.get('f')
    families = db.get_records('LibraryFamily')
    libraries = db.get_records('LibraryRecord')
    
    family_desc = ""
    if active_family:
        libraries = [l for l in libraries if l.get('family_id') == active_family]
        f = next((f for f in families if f['family_id'] == active_family), None)
        family_name = f['name'] if f else "Unknown"
        family_desc = f.get('description', '') if f else ""
    else:
        family_name = "Global Registry"
        
    return render_template_string(_T, families=families, libraries=libraries, 
                                 active_family=active_family, family_name=family_name,
                                 family_desc=family_desc, LIBS_SOURCE_DIR=LIBS_SOURCE_DIR)

@app.route('/save', methods=['POST'])
def save():
    t = request.form.get('type')
    if t == 'family':
        rec = {
            'Record_Type_Parent': 'LibraryFamily',
            'family_id': str(uuid.uuid4())[:8],
            'name': request.form.get('name'),
            'parent_family_id': request.form.get('parent'),
            'slug': request.form.get('slug').lower(),
            'description': request.form.get('desc'),
            'icon': ''
        }
        db.add_record('LibraryFamily', rec)
    elif t == 'library':
        rec = {
            'Record_Type_Parent': 'LibraryRecord',
            'lib_id': str(uuid.uuid4())[:8],
            'name': request.form.get('name'),
            'slug': request.form.get('slug'),
            'family_id': request.form.get('family_id'),
            'language': request.form.get('language'),
            'version': request.form.get('version', '1.0.0'),
            'status': 'Stable',
            'created_at': datetime.now().isoformat()
        }
        db.add_record('LibraryRecord', rec)
    
    flash("Entry saved successfully.")
    return redirect('/')

@app.route('/sync')
def sync():
    if not os.path.exists(LIBS_SOURCE_DIR):
        flash(f"Error: Source directory {LIBS_SOURCE_DIR} not found.")
        return redirect('/')
    
    existing_libs = {l['file_path']: l for l in db.get_records('LibraryRecord') if l.get('file_path')}
    files = [f for f in os.listdir(LIBS_SOURCE_DIR) if f.endswith(('.py', '.js', '.sh'))]
    
    added = 0
    updated = 0
    
    for f in files:
        path = os.path.join(LIBS_SOURCE_DIR, f)
        checksum = get_file_checksum(path)
        meta = parse_lib_header(path)
        lang = 'py' if f.endswith('.py') else 'js' if f.endswith('.js') else 'sh'
        
        if f in existing_libs:
            old = existing_libs[f]
            if old.get('checksum') != checksum:
                db.update_record('LibraryRecord', 'lib_id', old['lib_id'], {
                    'version': meta['version'],
                    'status': meta['status'],
                    'checksum': checksum,
                    'description': meta['description'],
                    'last_sync': datetime.now().isoformat()
                })
                updated += 1
        else:
            rec = {
                'Record_Type_Parent': 'LibraryRecord',
                'lib_id': str(uuid.uuid4())[:8],
                'name': meta['name'],
                'slug': f.replace('.', '_'),
                'family_id': '', # Uncategorized
                'language': lang,
                'version': meta['version'],
                'status': meta['status'],
                'last_sync': datetime.now().isoformat(),
                'checksum': checksum,
                'file_path': f,
                'description': meta['description'],
                'created_at': datetime.now().isoformat()
            }
            db.add_record('LibraryRecord', rec)
            added += 1
            
    flash(f"Sync complete. Added {added}, Updated {updated} libraries.")
    return redirect('/')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5006)
