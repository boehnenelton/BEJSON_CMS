"""
Library:      lib_book_builder.py
Family:       System
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.0.1 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-18
Description:  Automated e-book generator from BEJSON source material.
"""

import os
import json
import markdown
from datetime import datetime

class BookBuilder:
    def __init__(self, template_path=None):
        self.template = self._load_default_template()

    def _load_default_template(self):
        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{TITLE}}</title>
    <style>
        :root { --bg: #050b17; --accent: #DE2626; --text: #e2e8f0; --code: #0f172a; }
        body { background: var(--bg); color: var(--text); font-family: 'JetBrains Mono', monospace; line-height: 1.7; padding: 50px; max-width: 900px; margin: auto; }
        .cover { height: 80vh; display: flex; flex-direction: column; justify-content: center; border-bottom: 2px solid var(--accent); margin-bottom: 50px; }
        .cover h1 { font-size: 4rem; color: #fff; margin: 0; }
        .cover p { color: var(--accent); font-size: 1.2rem; }
        .toc { background: rgba(15, 23, 42, 0.5); padding: 30px; border-radius: 12px; border: 1px solid var(--accent); margin-bottom: 80px; }
        .toc h2 { border-bottom: none; margin-top: 0; }
        .toc ul { list-style: none; padding: 0; }
        .toc li { margin-bottom: 10px; }
        .toc a { color: var(--text); text-decoration: none; border-bottom: 1px dashed var(--accent); }
        h1, h2, h3 { color: #fff; border-bottom: 1px solid rgba(222,38,38,0.3); padding-bottom: 10px; margin-top: 50px; }
        pre { background: var(--code); padding: 20px; border-radius: 8px; border: 1px solid #1e293b; overflow-x: auto; }
        code { color: var(--accent); }
        footer { margin-top: 100px; padding-top: 20px; border-top: 1px solid #1e293b; font-size: 0.8rem; color: #64748b; }
        .author-tag { color: var(--accent); font-weight: bold; }
    </style>
</head>
<body>
    <div class="cover">
        <p>{{CATEGORY}}</p>
        <h1>{{TITLE}}</h1>
        <p>By <span class="author-tag">{{AUTHOR}}</span></p>
        <p>{{DATE}}</p>
    </div>
    
    <nav class="toc">
        <h2>Table of Contents</h2>
        {{TOC}}
    </nav>

    <div class="content">
        {{CONTENT}}
    </div>
    
    <footer>
        Standardized Technical Literature | Published via BEJSON Libraries Blogger Pipeline
    </footer>
</body>
</html>"""

    def generate_toc(self, chapters):
        toc_html = "<ul>"
        for i, chap in enumerate(chapters):
            title = chap.get("title", f"Chapter {i+1}")
            anchor = title.lower().replace(" ", "-").replace("&", "and")
            toc_html += f'<li><a href="#{anchor}">{title}</a></li>'
        toc_html += "</ul>"
        return toc_html

    def generate_markdown(self, chapters):
        full_md = []
        for chap in chapters:
            title = chap.get("title")
            content = chap.get("content_md")
            anchor = title.lower().replace(" ", "-").replace("&", "and")
            full_md.append(f'<h1 id="{anchor}">{title}</h1>\n\n{content}\n\n<br><hr>\n')
        return "\n".join(full_md)

    def build_book(self, bejson_path, output_html_path):
        with open(bejson_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        title = data.get("Project_Name", "Technical Manual")
        category = data.get("Category", "Technical Documentation")
        author = data.get("Author", "System Analyst")
        
        # Extract and sort chapters
        fields = [f["name"] for f in data.get("Fields", [])]
        chapters_raw = [v for v in data.get("Values", []) if v[0] == "Chapter"]
        
        chapters = []
        for c in chapters_raw:
            chapters.append(dict(zip(fields, c)))
        
        # Sort by chapter_id if present
        chapters.sort(key=lambda x: int(x.get("chapter_id", 0)))

        toc_content = self.generate_toc(chapters)
        md_content = self.generate_markdown(chapters)
        html_body = markdown.markdown(md_content, extensions=['fenced_code', 'tables'])
        
        final_html = self.template.replace("{{TITLE}}", title) \
                                 .replace("{{CATEGORY}}", category) \
                                 .replace("{{AUTHOR}}", author) \
                                 .replace("{{DATE}}", datetime.now().strftime("%Y-%m-%d")) \
                                 .replace("{{TOC}}", toc_content) \
                                 .replace("{{CONTENT}}", html_body)
                                 
        with open(output_html_path, "w", encoding="utf-8") as f:
            f.write(final_html)
        
        return True

if __name__ == "__main__":
    print("Book Builder Library v2.0.1 OFFICIAL")
