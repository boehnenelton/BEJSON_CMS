"""
Library:      lib_html3_widgets.py
Family:       HTML3
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      3.0.0 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-29
Description:  Modular BECSS-compliant widgets for HTML3.
"""

import html as html_mod
import os
import re
import uuid
from pathlib import Path

VERSION = "3.0.0"
SCRIPT_NAME = "lib_html3_widgets.py"
RELATIONAL_ID = "9e4d3c2b-1f8a-4e8a-9d6c-4f4b5a6c7d8e"
ES5_SAFE = True

# Widget Size Standards (Fixed Grid PX)
W_SMALL = (220, 200)
W_MEDIUM = (580, 300)
W_LARGE = (1180, 400)

def html_widget(content, title="WIDGET", size="small", container_id=None):
    """BECSS Widget Container."""
    cid = container_id or f"widget_{uuid.uuid4().hex[:12]}"
    
    if size == "large": width, height = W_LARGE
    elif size == "medium": width, height = W_MEDIUM
    else: width, height = W_SMALL
    
    style = f'width: {width}px; height: {height}px; min-width: {width}px; min-height: {height}px;'
    
    return f"""
    <div id="{cid}" class="c-widget" style="{style}">
        <div class="c-widget__header">
            <span>{html_mod.escape(title)}</span>
            <span style="opacity: 0.5;">[{size.upper()}]</span>
        </div>
        <div class="c-widget__body">
            {content}
        </div>
    </div>
    """

def html_gallery(dir_path, url_prefix="", recursive=False, container_id=None):
    """BECSS Image Gallery Grid."""
    cid = container_id or f"gallery_{uuid.uuid4().hex[:12]}"
    path = Path(dir_path)
    if not path.exists() or not path.is_dir():
        return f'<div class="c-card" style="border-style: dashed; opacity: 0.5; text-align: center; padding: 40px;">GALLERY SOURCE NOT FOUND: {dir_path}</div>'
    
    extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg')
    pattern = "**/*" if recursive else "*"
    items = ""
    
    # Normalize url_prefix (remove trailing slash if present)
    prefix = url_prefix.rstrip("/")
    
    found_any = False
    for img in sorted(path.glob(pattern)):
        if img.suffix.lower() in extensions:
            found_any = True
            # Build clean source path
            src = f"{prefix}/{img.name}" if prefix else img.name
            items += f"""
            <div class="c-gallery-item" onclick="openLightbox('{src}', '{html_mod.escape(img.name)}')">
                <img src="{src}" alt="{img.name}" loading="lazy" onerror="this.src='https://placehold.co/400x300?text=Missing+Image'">
                <div class="c-gallery-item__label">{img.name}</div>
            </div>"""
            
    if not found_any:
        return f'<div class="c-card" style="border-style: dashed; opacity: 0.5; text-align: center; padding: 40px;">NO IMAGES FOUND IN: {path.name}/</div>'
        
    return f'<div id="{cid}" class="c-gallery-grid">{items}</div>'


def html_video_grid(videos, container_id=None):
    """BECSS Video Grid."""
    cid = container_id or f"vgrid_{uuid.uuid4().hex[:12]}"
    items = ""
    for vid in videos:
        url = vid.get('url', '')
        title = vid.get('title', 'Video')
        
        embed_url = url
        if "youtube.com/watch" in url:
            vid_id = re.search(r'v=([^&]+)', url)
            if vid_id: embed_url = f"https://www.youtube.com/embed/{vid_id.group(1)}"
        elif "youtu.be/" in url:
            vid_id = url.split("youtu.be/")[1]
            embed_url = f"https://www.youtube.com/embed/{vid_id}"

        items += f"""
        <div class="c-video-card">
            <div class="c-video-card__header">{html_mod.escape(title)}</div>
            <div class="c-video-card__embed">
                <iframe src="{embed_url}" allowfullscreen loading="lazy"></iframe>
            </div>
        </div>"""

    return f'<div id="{cid}" class="c-video-grid">{items}</div>'

def html_info_box(title, content, link_url=None, link_label="View More", container_id=None, escape_content=False):
    """BECSS Info Box."""
    cid = container_id or f"infobox_{uuid.uuid4().hex[:12]}"
    link_html = f"""<a href="{link_url}" class="c-info-box__link">{link_label}</a>""" if link_url else ""
    display_content = html_mod.escape(content) if escape_content else content

    return f"""
    <div id="{cid}" class="c-info-box">
        <h3 class="c-info-box__title">
            <span class="c-info-box__dot"></span>
            {html_mod.escape(title)}
        </h3>
        <div class="c-info-box__content">{display_content}</div>
        {link_html}
    </div>
    """

def html_standalone_widget(html_content, title="Widget", container_id=None):
    """Isolated iframe widget (BECSS normalized)."""
    cid = container_id or f"standalone_widget_{uuid.uuid4().hex[:12]}"
    escaped_content = html_mod.escape(html_content, quote=True)

    return f"""
    <div id="{cid}" class="c-widget" style="width: 100%;">
        <div class="c-widget__header">
            <span>{html_mod.escape(title)}</span>
            <span style="opacity: 0.5;">ISOLATED</span>
        </div>
        <iframe srcdoc="{escaped_content}" style="width: 100%; height: 600px; border: none; display: block;" sandbox="allow-scripts"></iframe>
    </div>
    """

def html_lightbox():
    """BECSS Global Lightbox."""
    return """
    <div id="bejson-lightbox" class="c-lightbox" onclick="this.style.display='none'">
        <span class="c-lightbox__close">&times;</span>
        <img class="c-lightbox__content" id="lightbox-img">
        <div id="lightbox-caption" class="c-lightbox__caption"></div>
    </div>
    <script>
    function openLightbox(src, caption) {
        document.getElementById('bejson-lightbox').style.display = 'block';
        document.getElementById('lightbox-img').src = src;
        // XSS Remediation: Use textContent instead of innerHTML
        document.getElementById('lightbox-caption').textContent = caption;
    }
    </script>
    """

def html_carousel(items, container_id=None, escape_items=True):
    """BECSS Carousel."""
    cid = container_id or f"carousel_{uuid.uuid4().hex[:12]}"
    slides = ""
    for item in items:
        # XSS Remediation: Escape item content by default
        display_item = html_mod.escape(str(item)) if escape_items else item
        slides += f'<div class="c-carousel__slide">{display_item}</div>'
        
    return f"""
    <div id="{cid}" class="c-carousel">
        <div class="c-carousel__track">{slides}</div>
        <div class="c-carousel__controls">
            <button class="c-carousel__btn" onclick="moveCarousel('{cid}', -1)">&lt; PREV</button>
            <button class="c-carousel__btn" onclick="moveCarousel('{cid}', 1)">NEXT &gt;</button>
        </div>
    </div>
    <script>
    if(!window.carouselPos) window.carouselPos = {{}};
    function moveCarousel(id, dir) {{
        var track = document.getElementById(id).querySelector('.c-carousel__track');
        var count = track.children.length;
        if(!window.carouselPos[id]) window.carouselPos[id] = 0;
        window.carouselPos[id] = (window.carouselPos[id] + dir + count) % count;
        track.style.transform = 'translateX(-' + (window.carouselPos[id] * 100) + '%)';
    }}
    </script>
    """


def html_code_block(code, title="Source Code", container_id=None):
    """BECSS Code Block (Integrated bejsonCopy)."""
    cid = container_id or f"code_{uuid.uuid4().hex[:12]}"
    return f"""
    <div id="{cid}" class="c-code-box">
        <div class="c-code-box__header">
            <div class="c-code-box__title">{html_mod.escape(title)}</div>
            <button class="c-code-box__copy" onclick="bejsonCopy('{cid}', this)">COPY</button>
        </div>
        <pre class="c-code-box__pre"><code class="c-code-box__code">{html_mod.escape(code)}</code></pre>
    </div>
    """

def html_dialog(dialog_id, title, content, actions_html="", escape_content=True):
    """BECSS Modal Dialog."""
    display_content = html_mod.escape(content) if escape_content else content
    return f"""
    <div id="{dialog_id}" class="c-dialog-mask">
        <div class="c-dialog">
            <div class="c-dialog__header">
                <span class="c-dialog__title">{html_mod.escape(title)}</span>
                <button class="c-dialog__close" onclick="closeDialog('{dialog_id}')">&times;</button>
            </div>
            <div class="c-dialog__body">{display_content}</div>
            <div class="c-dialog__footer">{actions_html}</div>
        </div>
    </div>
    <script>
    function openDialog(id) {{ document.getElementById(id).style.display = 'block'; }}
    function closeDialog(id) {{ document.getElementById(id).style.display = 'none'; }}
    </script>
    """

def html_load_widget(widget_name, components_dir=None, container_id=None):
    """Loads an external HTML component."""
    if not components_dir:
        components_dir = os.environ.get("CC_COMPONENTS", "Templates/Components")
    
    path = Path(components_dir) / f"{widget_name}.html"
    if not path.exists():
        # XSS Remediation: Escape widget_name and components_dir
        return f"<div>Error: Widget component '{html_mod.escape(widget_name)}' not found in {html_mod.escape(str(components_dir))}</div>"
        
    try:
        content = path.read_text(encoding='utf-8')
        return html_standalone_widget(content, title=widget_name, container_id=container_id)
    except Exception as e:
        # XSS Remediation: Escape error message
        return f"<div>Error loading widget '{html_mod.escape(widget_name)}': {html_mod.escape(str(e))}</div>"
