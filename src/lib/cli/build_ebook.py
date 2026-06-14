"""
Library:      build_ebook.py
Family:       Core
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.1.0 OFFICIAL (Loud Failures)
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-22
Description:  Specialized generator for e-book formatted outputs.
REMEDIATED:   Removed silent import hijacking. Fails loudly on missing dependencies.
"""

import os
import sys
import json
import html as html_mod
from pathlib import Path

# Add current py dir to sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

LIB_PY_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if LIB_PY_DIR not in sys.path:
    sys.path.append(LIB_PY_DIR)

try:
    from HTML import html_page, html_save as html_write, html_brutal_table as html_table
except ImportError as e:
    print(f"CRITICAL BUILD FAILURE: Missing HTML generation dependencies. {e}")
    sys.exit(1)

def build_ebook():
    lib_root = os.environ.get("BEJSON_LIB_ROOT", os.path.dirname(os.path.abspath(__file__)))
    manifest_path = os.path.join(lib_root, "library_manifest.bejson")
    output_root = os.path.join(lib_root, "doc")
    
    os.makedirs(output_root, exist_ok=True)
    
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    with open(manifest_path, 'r') as f:
        manifest = json.load(f)

    fields = manifest.get("Fields", [])
    values = manifest.get("Values", [])
    f_idx = {f["name"]: i for i, f in enumerate(fields)}
    
    runtimes = ["py", "sh", "js"]
    for rt in runtimes:
        os.makedirs(os.path.join(output_root, rt), exist_ok=True)

    nav_data = []
    for row in values:
        name = row[f_idx["name"]]
        lib_id = row[f_idx["id"]]
        rt_dir = "py" if name.endswith(".py") else "sh" if name.endswith(".sh") else "js"
        nav_data.append({
            "name": name, "id": lib_id, "rt": rt_dir,
            "filename": f"{os.path.splitext(name)[0]}.html"
        })

    for item in nav_data:
        row = next(r for r in values if r[f_idx["id"]] == item["id"])
        name, rt_dir, target_filename = item["name"], item["rt"], item["filename"]
        path, description, functions = row[f_idx["path"]], row[f_idx["description"]], row[f_idx["functions"]]
        
        print(f"Building: {rt_dir}/{name}")
        
        if not os.path.exists(path):
            raise FileNotFoundError(f"Source file missing: {path}")

        with open(path, 'r') as cf:
            code_content = cf.read()

        page_nav = [("Home", "../index.html")]
        for nav_item in nav_data:
            url = nav_item["filename"] if nav_item["rt"] == rt_dir else f"../{nav_item['rt']}/{nav_item['filename']}"
            page_nav.append((nav_item["name"], url))

        body = f"""
        <article class="lib-reference">
            <header class="lib-header">
                <span class="badge badge-{rt_dir}">{rt_dir.upper()}</span>
                <h1>{html_mod.escape(name)}</h1>
                <p>{html_mod.escape(description)}</p>
            </header>
            <section>
                <h2>API</h2>
                <ul>{"".join(f"<li><code>{html_mod.escape(fn)}</code></li>" for fn in functions)}</ul>
            </section>
            <section>
                <h2>Code</h2>
                <pre><code>{html_mod.escape(code_content)}</code></pre>
            </section>
        </article>"""
        
        full_html = html_page(title=f"Ref: {name}", content=body, nav_links=page_nav, dark=True)
        html_write(full_html, os.path.join(output_root, rt_dir, target_filename))

    # Index
    index_nav = [("Home", "index.html")] + [(n["name"], f"{n['rt']}/{n['filename']}") for n in nav_data]
    table_headers = ["Type", "Name", "Desc"]
    table_rows = []
    for item in nav_data:
        row = next(r for r in values if r[f_idx["id"]] == item["id"])
        link = f'<a href="{item["rt"]}/{item["filename"]}">{html_mod.escape(item["name"])}</a>'
        table_rows.append([item["rt"].upper(), link, html_mod.escape(row[f_idx["description"]])])

    index_body = f"<h1>Index</h1>{html_table(table_headers, table_rows, escape=False)}"
    index_html = html_page(title="Library Index", content=index_body, nav_links=index_nav, dark=True)
    html_write(index_html, os.path.join(output_root, "index.html"))

if __name__ == "__main__":
    build_ebook()
