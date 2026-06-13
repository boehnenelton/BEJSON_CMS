import os
import sys
import json
from flask import Flask, request, redirect, render_template_string

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(PROJECT_ROOT, 'src', 'lib'))
import lib_cms_core as CMSCore

MANIFEST_PATH = os.path.join(PROJECT_ROOT, 'storage', 'mfdb', 'site_master', '104a.mfdb.bejson')
app = Flask(__name__)
app.secret_key = 'profile-key'
db = CMSCore.CMSCore(MANIFEST_PATH)

_T = """
<!DOCTYPE html><html><head><title>Persona Hub</title>
<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800;900&display=swap' rel='stylesheet'>
<style>
    :root{ --bg:#000; --c:#161616; --acc:#1DA1F2; --f:#fff; --m:#71767B; --b:#2F3336; }
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
                <div style='font-weight:900;'>{{p.Name}} <span style='color:var(--m)'>@{{p.Archetype}}</span></div>
                <a href='/edit/{{p.Name}}' class='btn-out' style='text-decoration:none; border-radius:15px;'>Edit</a>
            </div>
            <p style='margin:10px 0; font-size:0.95rem;'>{{p.Persona}}</p>
            <div style='color:var(--m); font-size:0.75rem; font-family:monospace; background:#0a0a0a; padding:10px; border-radius:4px;'>{{p.SystemInstruction[:150]}}...</div>
        </div>{% endfor %}
        <hr style='border:0; border-top:1px solid var(--b); margin:30px 0;'>
        <div id='form' class='card'>
            <h3 style='margin-bottom:10px;'>{{ "Edit" if ep else "Create" }} Persona</h3>
            <form action='/save' method='POST'>
                <input name='name' id='n' placeholder='Display Name' required {{ "readonly" if ep else "" }}>
                <input name='archetype' id='a' placeholder='Archetype (e.g. Rebel, Architect)'>
                <textarea name='bio' id='b' rows='3' placeholder='Persona Bio (Public)'></textarea>
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
        document.getElementById('n').value="{{ep.Name}}";
        document.getElementById('a').value="{{ep.Archetype}}";
        document.getElementById('b').value="{{ep.Persona}}";
        document.getElementById('i').value=`{{ep.SystemInstruction|safe}}`;
        document.getElementById('form').scrollIntoView();
    {% endif %}</script>
</body></html>"""

@app.route('/')
def index(): return render_template_string(_T, profiles=db.get_records('AI_Profile'))

@app.route('/edit/<n>')
def edit(n):
    p = next((x for x in db.get_records('AI_Profile') if x['Name']==n), None)
    return render_template_string(_T, profiles=db.get_records('AI_Profile'), ep=p)

@app.route('/save', methods=['POST'])
def save():
    n=request.form.get('name'); a=request.form.get('archetype'); b=request.form.get('bio'); i=request.form.get('inst')
    r={'Record_Type_Parent':'AI_Profile','Name':n,'Archetype':a,'Persona':b,'SystemInstruction':i,'Active':True,'MaxResponseTokens':8192,'Creativity':0.7}
    existing=next((x for x in db.get_records('AI_Profile') if x['Name']==n), None)
    if existing: db.update_record('AI_Profile','Name',n,r)
    else:
        db.add_record('AI_Profile',r)
        db.add_record('AuthorProfile',{'Record_Type_Parent':'AuthorProfile','auth_name':n,'auth_bio':b})
    # Sync Manifest
    try:
        with open(MANIFEST_PATH, 'r') as f: m = json.load(f)
        for v in m['Values']:
            if v[0] == 'AI_Profile': v[3] = len(db.get_records('AI_Profile'))
            if v[0] == 'AuthorProfile': v[3] = len(db.get_records('AuthorProfile'))
        with open(MANIFEST_PATH, 'w') as f: json.dump(m, f, indent=2)
    except: pass
    return redirect('/')

if __name__ == '__main__': app.run(host='0.0.0.0', port=5004)
