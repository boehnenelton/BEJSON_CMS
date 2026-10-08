"""
SCRIPT_NAME:    BEJSON_CMS_ProfileManager
SCRIPT_VERSION: 1.2
DATE:           2026-09-13
RELATIONAL_ID:  f031ed87-45b1-4c62-9e97-ad436cfbb446
AUTHOR:         Elton Boehnen
DESCRIPTION:    Persona Hub - manages AI_Profile records (BEJSON 104 persona
                 format). Standalone admin app, port 5004.
CHANGE (2026-09-13): PKG135 -- "give them all uuids" (Elton). AI_Profile
went from persona_name-keyed to UUID-keyed. /edit/<n> and /delete/<n>
routes converted to /edit/<u> and /delete/<u> (persona_uuid); save() now
carries a hidden `uuid` form field (empty on create, ep.persona_uuid on
edit) and keys update_record()/add_record() off it instead of re-matching
on the submitted name every time -- the name input was already readonly
during edit so this never produced a wrong result in practice, but it
meant AI_Profile had no identity that would survive a rename if that
readonly restriction were ever lifted. delete() looks up the persona's
name before deleting (still needed for the PageRecord.page_author_name
cascade below it, which stays name-based by design -- that FK was NOT
converted this pass, a separate, larger decision). Also fixed the
linked-AuthorProfile auto-create in save() to include a real author_uuid
-- it didn't, so every persona-triggered AuthorProfile row was landing
with author_uuid: None, defeating the whole point (caught live, not by
inspection: ran the full add/edit/delete cycle via Flask test client
against real data and found the stray None row in authorprofile.bejson
afterward, cleaned it up). Verified live end to end.
"""

import os
import sys
import uuid
from flask import Flask, request, redirect, render_template_string

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(PROJECT_ROOT, 'src', 'lib'))
import lib_bejson_CMS_cms_core as CMSCore
import lib_bejson_CMS_cms_ports as CMSPorts
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")
PROFILES_PORT = CMSPorts.get_port(CONFIG_PATH, "profiles_port", "CMS_PROFILES_PORT")

MANIFEST_PATH = os.path.join(PROJECT_ROOT, 'storage', 'mfdb', 'site_master', '104a.mfdb.bejson')
app = Flask(__name__)
app.secret_key = os.environ.get('CMS_SECRET_KEY') or os.urandom(24).hex()  # Set CMS_SECRET_KEY env var in production
db = CMSCore.CMSCore(MANIFEST_PATH)

from BEJSON_CMS_Shared import _check_auth, _unauthorized


@app.before_request
def _enforce_auth_everywhere():
    # SECURITY FIX: this standalone app (create/delete personas) had zero
    # authentication -- every route completely open. Matches the same
    # before_request gate BEJSON_CMS_Admin.py enforces on its blueprints.
    Request_Basic_Auth_Header = request.authorization
    if not Request_Basic_Auth_Header or not _check_auth(Request_Basic_Auth_Header.username, Request_Basic_Auth_Header.password):
        return _unauthorized()


_T = """
<!DOCTYPE html><html><head><title>Persona Hub</title>
<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800;900&display=swap' rel='stylesheet'>
<style>
    :root{ --bg:#000; --c:#161616; --acc:#DE2626; --f:#fff; --m:#71767B; --b:#2F3336; }
    *{box-sizing:border-box; margin:0; padding:0;}
    body{background:var(--bg); color:var(--f); font-family:'Inter',sans-serif;}
    .nav{border-bottom:1px solid var(--b); padding:15px; display:flex; justify-content:space-between; position:sticky; top:0; background:rgba(0,0,0,0.8); backdrop-filter:blur(8px);}
    .container{max-width:600px; margin:auto; padding:20px;}
    .card{background:var(--c); border:1px solid var(--b); border-radius:12px; padding:15px; margin-bottom:15px;}
    input, textarea{width:100%; background:#000; border:1px solid var(--b); padding:10px; color:#fff; margin:10px 0; border-radius:4px; font-family:inherit;}
    button{background:var(--acc); color:#fff; border:none; padding:10px 20px; border-radius:20px; font-weight:800; cursor:pointer;}
    .btn-out{background:transparent; border:1px solid var(--b); color:var(--m); font-size:0.8rem; padding:5px 12px;}
</style></head><body>
    <div class='nav'><b>BEJSON.Persona</b> <button onclick='document.getElementById("form").scrollIntoView({behavior:"smooth"})'>+ New</button></div>
    <div class='container'>
        {% for p in profiles %}<div class='card'>
            <div style='display:flex; justify-content:space-between;'>
                <div style='font-weight:900;'>{{p.persona_name}} <span style='color:var(--m)'>@{{p.persona_archetype}}</span></div>
                <div style='display:flex; gap:6px;'>
                    <a href='/edit/{{p.persona_uuid}}' class='btn-out' style='text-decoration:none; border-radius:15px;'>Edit</a>
                    <form method='post' action='/delete/{{p.persona_uuid}}' style='display:inline;' onsubmit='return confirm("Delete this persona? Pages already using it as author will fall back to the default author.")'>
                        <button type='submit' class='btn-out' style='border-radius:15px; color:#f4212e; border-color:#f4212e;'>Delete</button>
                    </form>
                </div>
            </div>
            <p style='margin:10px 0; font-size:0.95rem;'>{{p.persona_bio}}</p>
            <div style='color:var(--m); font-size:0.75rem; font-family:monospace; background:#0a0a0a; padding:10px; border-radius:4px;'>{{p.persona_system_instruction[:150]}}...</div>
        </div>{% endfor %}
        <hr style='border:0; border-top:1px solid var(--b); margin:30px 0;'>
        <div id='form' class='card'>
            <h3 style='margin-bottom:10px;'>{{ "Edit" if ep else "Create" }} Persona</h3>
            <form action='/save' method='POST'>
                <input type='hidden' name='uuid' value="{{ ep.persona_uuid if ep else '' }}">
                <input name='name' id='n' placeholder='Display Name' required {{ "readonly" if ep else "" }}>
                <input name='archetype' id='a' placeholder='Archetype (e.g. Rebel, Architect)'>
                <textarea name='bio' id='b' rows='3' placeholder='Persona / Voice Description (INTERNAL -- shapes the AI, never shown publicly)'></textarea>
                <div style='margin:-4px 0 10px 0; font-size:0.8rem; color:var(--m);'>The public author bio shown on the exported site is edited separately, at Site &rsaquo; Authors -- not here.</div>
                <textarea name='inst' id='i' rows='6' placeholder='System Instruction (Internal)' style='font-family:monospace; font-size:0.85rem;'></textarea>
                <div style='display:flex; gap:10px; margin-top:10px;'>
                    <button type='submit'>Save Profile</button>
                    {% if ep %}<a href='/' style='color:var(--m); padding:10px; text-decoration:none;'>Cancel</a>{% endif %}
                </div>
            </form>
        </div>
    </div>
    <script>
    {% if ep %}
        document.getElementById('n').value="{{ep.persona_name}}";
        document.getElementById('a').value="{{ep.persona_archetype}}";
        document.getElementById('b').value="{{ep.persona_bio}}";
        document.getElementById('i').value=`{{ep.persona_system_instruction|safe}}`;
        document.getElementById('form').scrollIntoView();
    {% endif %}</script>
</body></html>"""

@app.route('/')
def index(): return render_template_string(_T, profiles=db.get_records('AI_Profile'))

@app.route('/edit/<u>')
def edit(u):
    p = next((x for x in db.get_records('AI_Profile') if x['persona_uuid']==u), None)
    return render_template_string(_T, profiles=db.get_records('AI_Profile'), ep=p)

@app.route('/save', methods=['POST'])
def save():
    Submitted_Persona_Uuid=request.form.get('uuid', '').strip()
    Submitted_Persona_Name=request.form.get('name'); Submitted_Persona_Archetype=request.form.get('archetype'); Submitted_Persona_Bio=request.form.get('bio'); Submitted_Persona_System_Instruction=request.form.get('inst')
    Persona_Record_Payload={'persona_record_type':'AI_Profile','persona_name':Submitted_Persona_Name,'persona_archetype':Submitted_Persona_Archetype,'persona_bio':Submitted_Persona_Bio,'persona_system_instruction':Submitted_Persona_System_Instruction,'persona_active':True,'persona_max_tokens':8192,'persona_creativity':0.7}
    if Submitted_Persona_Uuid:
        # Editing an existing persona: identity comes from the hidden uuid
        # field (set from ep.persona_uuid when the edit form was rendered),
        # not by re-matching on name -- the name input is readonly during
        # edit anyway, but keying the update off a stable UUID rather than
        # re-deriving identity from the submitted name on every save is the
        # actual fix (give-them-all-uuids pass, pkg135): matching by name
        # here was never wrong in practice since it round-tripped the same
        # readonly value, but it meant AI_Profile had no identity that
        # survives a rename if that readonly restriction is ever lifted.
        db.update_record('AI_Profile','persona_uuid',Submitted_Persona_Uuid,Persona_Record_Payload)
    else:
        existing=next((x for x in db.get_records('AI_Profile') if x['persona_name'].lower()==Submitted_Persona_Name.lower()), None)
        if existing:
            db.update_record('AI_Profile','persona_uuid',existing['persona_uuid'],Persona_Record_Payload)
        else:
            Persona_Record_Payload['persona_uuid'] = str(uuid.uuid4())
            db.add_record('AI_Profile',Persona_Record_Payload)

    # This "Persona" bio is internal only -- it shapes the AI's voice, and
    # is never meant to be shown on the published site. It must NOT be
    # copied into AuthorProfile.auth_bio (that field IS shown publicly, on
    # article bylines/feeds). Only ensure the linked AuthorProfile row
    # EXISTS, so the connection holds (author_ref dropdown, AI-generation
    # persona lookup) -- never overwrite auth_bio here. The real public bio
    # is written independently via Site > Authors, which already has its
    # own auth_bio field for exactly this purpose.
    existing_author = next((x for x in db.get_records('AuthorProfile') if x['author_display_name'].lower()==Submitted_Persona_Name.lower()), None)
    if not existing_author:
        db.add_record('AuthorProfile', {'author_uuid': str(uuid.uuid4()), 'author_display_name': Submitted_Persona_Name, 'author_bio': ''})

    # CMSCore.add_record()/update_record() above already sync the manifest
    # record-count safely under its own PID lock (mfdb_core_add_entity_record /
    # mfdb_core_remove_entity_record, sync_count=True by default). The manual
    # unlocked json.load/json.dump manifest rewrite that used to live here was
    # redundant with that and could race against it — removed, not fixed.
    return redirect('/')


@app.route('/delete/<u>', methods=['POST'])
def delete(u):
    # BUG FIX: there was no way to delete a persona at all -- this route
    # didn't exist. Cascades to PageRecord.author_ref the same way
    # categories_delete already does for category_ref elsewhere in this
    # project, reassigning to the default author rather than leaving a
    # dangling reference; does NOT delete the linked AuthorProfile itself
    # (a persona going away shouldn't erase the byline on pages already
    # published under that name).
    persona_record = next((x for x in db.get_records('AI_Profile') if x['persona_uuid']==u), None)
    n = persona_record['persona_name'] if persona_record else None
    db.delete_record('AI_Profile', 'persona_uuid', u)
    DEFAULT_AUTHOR_NAME = "boehnenelton2024"
    pages = db.get_records("PageRecord")
    for p in pages:
        if p.get("page_author_name") == n:
            db.update_record("PageRecord", "page_uuid", p["page_uuid"], {"page_author_name": DEFAULT_AUTHOR_NAME})
    # CMSCore.delete_record() above already syncs the manifest record-count
    # safely under its own PID lock — see note in save() above.
    return redirect('/')

if __name__ == '__main__':
    _legacy = [f for f in ["Flask_CMS.py", "Flask_CMS_Publisher.py", "Flask_Page_Editor.py",
                            "Flask_Profile_Manager.py", "Page_Editor_v2.py"]
               if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), f))]
    if _legacy:
        print(f"\n    !! WARNING: old pre-rename file(s) still present: {', '.join(_legacy)} -- delete them, they are unmaintained leftovers from before the Blueprint split.\n")
    # Port resolved via config.json (profiles_port) / CMS_PROFILES_PORT env.
    app.run(host='0.0.0.0', port=PROFILES_PORT)
