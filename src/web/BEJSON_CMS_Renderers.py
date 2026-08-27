"""
Library:        BEJSON_CMS_Renderers
Family:         BEJSON_CMS
Description:    Strategy Pattern Renderers for Polymorphic Page Types (Standard, Video, Document).
                See Section 5 of CMS Naming Taxonomy & Extensibility Architecture Specification.
Version:        1.0.0
Author:         Elton Boehnen
Date:           2026-08-11
RELATIONAL_ID:  9a8b7c6d-5e4f-3a2b-1c0d-9e8f7a6b5c4d
"""

from typing import Dict, Any, Optional
import re

def _yt_id_from_url(raw: str) -> Optional[str]:
    """Same extraction rule as BEJSON_CMS_Media.py's _yt_id_from_url() and
    PageEditorV2.py's ytIdFromUrlV2() -- kept identical on purpose, same as
    those two. Duplicated locally rather than imported to avoid coupling
    this renderer module to the web layer."""
    raw = (raw or "").strip()
    if re.match(r'^[A-Za-z0-9_-]{11}$', raw):
        return raw
    m = re.search(r'(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{11})', raw)
    return m.group(1) if m else None

class PageTypeRenderer:
    def render(self, page_data: Dict[str, Any], meta_data: Optional[Dict[str, Any]] = None) -> str:
        raise NotImplementedError("Subclasses must implement render()")

class StandardPageRenderer(PageTypeRenderer):
    def render(self, page_data: Dict[str, Any], meta_data: Optional[Dict[str, Any]] = None) -> str:
        # Body-only fragment: Article_Skeleton.html already provides the
        # outer <article> wrapper and its own <h1 class="article-title">
        # (fed from a separate article_title tag) -- this renderer must not
        # duplicate either, or every published page nests <article> inside
        # <article> with two titles stacked on top of each other.
        body = page_data.get('html_body') or page_data.get('page_body_html') or ''

        # Featured video: a lightweight alternative to the full Video page
        # type (VideoPageRenderer below) -- any standard page can have one
        # via the page_featured_video_url field, no page_type change needed.
        fv_url = page_data.get('page_featured_video_url')
        vid = _yt_id_from_url(fv_url) if fv_url else None
        if vid:
            video_html = f"""
<div class="bej-video-wrap" style="max-width:800px;margin:0 auto 40px;">
  <div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;border-radius:8px;border:1px solid #333;background:#000;">
    <iframe
      src="https://www.youtube.com/embed/{vid}"
      title="{page_data.get('page_title', 'Featured Video')}"
      frameborder="0"
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
      allowfullscreen
      style="position:absolute;top:0;left:0;width:100%;height:100%;">
    </iframe>
  </div>
</div>"""
            return video_html + body
        return body

class VideoPageRenderer(PageTypeRenderer):
    def render(self, page_data: Dict[str, Any], meta_data: Optional[Dict[str, Any]] = None) -> str:
        meta = meta_data or {}
        embed_url = meta.get('video_embed_url') or page_data.get('page_external_url') or ''
        body = page_data.get('html_body') or page_data.get('page_body_html') or ''
        duration = meta.get('video_duration', '')
        duration_html = f"<span class='video-duration'>Duration: {duration}</span>" if duration else ""

        video_player_html = f"""
        <div class='video-player-container' style='margin-bottom:20px; aspect-ratio:16/9; background:#000; border-radius:8px; overflow:hidden;'>
            <iframe src='{embed_url}' style='width:100%; height:100%; border:0;' allowfullscreen></iframe>
        </div>
        """ if embed_url else ""

        return f"""{duration_html}
          {video_player_html}
          {body}"""

class DocumentPageRenderer(PageTypeRenderer):
    def render(self, page_data: Dict[str, Any], meta_data: Optional[Dict[str, Any]] = None) -> str:
        meta = meta_data or {}
        doc_uuid = meta.get('doc_asset_uuid') or ''
        doc_filename = meta.get('doc_filename') or page_data.get('page_featured_img') or ''
        file_size = meta.get('doc_file_size_formatted', '')
        body = page_data.get('html_body') or page_data.get('page_body_html') or ''
        title = page_data.get('page_title', '')

        download_target = f"/assets/{doc_filename}" if doc_filename else f"/assets/download/{doc_uuid}"
        size_label = f" ({file_size})" if file_size else ""

        doc_card_html = f"""
        <div class='doc-download-card' style='background:var(--bg-secondary, #1a1a1a); padding:20px; border-radius:8px; border:1px solid var(--border, #333); margin-bottom:25px; display:flex; justify-content:space-between; align-items:center;'>
          <div>
            <h3 style='margin:0 0 5px 0;'>📄 Download Document</h3>
            <p style='margin:0; color:var(--text-secondary, #aaa); font-size:0.9rem;'>{title}{size_label}</p>
          </div>
          <a href='{download_target}' target='_blank' class='btn btn-primary' style='padding:8px 16px; background:#DE2626; color:#fff; text-decoration:none; border-radius:4px; font-weight:bold;'>Download File</a>
        </div>
        """

        return f"""{doc_card_html}
          {body}"""

RENDERER_REGISTRY: Dict[str, PageTypeRenderer] = {
    'standard': StandardPageRenderer(),
    'page': StandardPageRenderer(),
    'video': VideoPageRenderer(),
    'document': DocumentPageRenderer(),
}

def render_page(page_type: str, page_data: Dict[str, Any], meta_data: Optional[Dict[str, Any]] = None) -> str:
    renderer = RENDERER_REGISTRY.get(page_type.lower(), RENDERER_REGISTRY['standard'])
    return renderer.render(page_data, meta_data)
