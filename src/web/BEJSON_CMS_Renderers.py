"""
Library:        BEJSON_CMS_Renderers
Family:         BEJSON_CMS
Description:    Strategy Pattern Renderers for Polymorphic Page Types (Standard, Video, Document).
                See Section 5 of CMS Naming Taxonomy & Extensibility Architecture Specification.
Version:        1.1.0
Author:         Elton Boehnen
Date:           2026-11-24
RELATIONAL_ID:  dbc538fb-1a03-4f12-9d70-951c1ab1cbc1
"""

from typing import Dict, Any, List, Optional
import html as _html_mod
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


def _parse_labeled_links(raw_value: Any) -> List[Dict[str, str]]:
    """Parses newline-separated 'Label | URL' or plain URL strings into link dicts."""
    if not raw_value:
        return []
    if isinstance(raw_value, list):
        items = raw_value
    else:
        items = str(raw_value).splitlines()
    parsed: List[Dict[str, str]] = []
    for entry in items:
        if isinstance(entry, dict):
            url = str(entry.get("url", "")).strip()
            label = str(entry.get("label", "") or url).strip()
            if url:
                parsed.append({"label": label, "url": url})
            continue
        cleaned = str(entry).strip()
        if not cleaned:
            continue
        if "|" in cleaned:
            label_part, url_part = cleaned.split("|", 1)
            label = label_part.strip() or url_part.strip()
            url = url_part.strip()
        else:
            label = cleaned
            url = cleaned
        if url:
            parsed.append({"label": label, "url": url})
    return parsed


class ProjectPageRenderer(PageTypeRenderer):
    """Renders project pages with featured YouTube video, GitHub, Gemini Notepad, and asset links."""

    def render(self, page_data: Dict[str, Any], meta_data: Optional[Dict[str, Any]] = None) -> str:
        meta = meta_data or {}
        body = page_data.get('html_body') or page_data.get('page_body_html') or ''

        # 1. Featured Video (16:9 responsive YouTube embed)
        fv_url = meta.get('project_featured_video_url') or page_data.get('page_featured_video_url') or ''
        vid = _yt_id_from_url(fv_url) if fv_url else None
        video_html = ""
        if vid:
            safe_title = _html_mod.escape(str(page_data.get('page_title', 'Project Featured Video')))
            video_html = f"""
<div class="bej-video-wrap" style="max-width:800px;margin:0 auto 32px;">
  <div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;border-radius:var(--border-radius,4px);border:1px solid var(--border-color,#E0E0E0);background:#000;">
    <iframe
      src="https://www.youtube.com/embed/{vid}"
      title="{safe_title}"
      frameborder="0"
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
      allowfullscreen
      style="position:absolute;top:0;left:0;width:100%;height:100%;">
    </iframe>
  </div>
</div>"""

        # 2. Structured Project Links & Assets
        raw_gh = str(meta.get('project_github_url') or '').strip()
        github_url = re.sub(r'\.git/?$', '', raw_gh, flags=re.IGNORECASE) if raw_gh else ''
        gemini_url = str(meta.get('project_gemini_notepad_url') or '').strip()
        bejson_era = str(meta.get('project_bejson_era') or '').strip()
        featured_links = _parse_labeled_links(meta.get('project_featured_links'))
        youtube_links = _parse_labeled_links(meta.get('project_youtube_links'))
        asset_links = _parse_labeled_links(meta.get('project_asset_links'))

        primary_buttons: List[str] = []
        for feat_link in featured_links:
            primary_buttons.append(
                f'<a href="{_html_mod.escape(feat_link["url"])}" target="_blank" rel="noopener noreferrer" '
                f'style="display:inline-flex;align-items:center;gap:6px;padding:9px 16px;background:var(--primary-color,#DE2626);'
                f'color:#FFFFFF;border:1px solid var(--primary-color,#DE2626);border-radius:var(--border-radius,4px);text-decoration:none;font-weight:600;font-size:0.88rem;">'
                f'&#11088; {_html_mod.escape(feat_link["label"])}</a>'
            )
        if github_url:
            primary_buttons.append(
                f'<a href="{_html_mod.escape(github_url)}" target="_blank" rel="noopener noreferrer" '
                f'style="display:inline-flex;align-items:center;gap:6px;padding:9px 16px;background:var(--social-bg,var(--bg-card,#F0F0F0));'
                f'color:var(--text-color,#111111);border:1px solid var(--social-border,var(--border-color,#DDDDDD));border-radius:var(--border-radius,4px);text-decoration:none;font-weight:600;font-size:0.88rem;">'
                f'&#128187; GitHub Repository</a>'
            )
        if gemini_url:
            primary_buttons.append(
                f'<a href="{_html_mod.escape(gemini_url)}" target="_blank" rel="noopener noreferrer" '
                f'style="display:inline-flex;align-items:center;gap:6px;padding:9px 16px;background:var(--primary-color,#DE2626);'
                f'color:#FFFFFF;border:1px solid var(--primary-color,#DE2626);border-radius:var(--border-radius,4px);text-decoration:none;font-weight:600;font-size:0.88rem;">'
                f'&#128221; Public Gemini Notepad</a>'
            )

        extra_lists_html = ""
        if youtube_links:
            yt_items = "".join(
                f'<li style="margin-bottom:6px;"><a href="{_html_mod.escape(lnk["url"])}" target="_blank" rel="noopener noreferrer" '
                f'style="color:var(--primary-color,#DE2626);text-decoration:underline;">&#9654; {_html_mod.escape(lnk["label"])}</a></li>'
                for lnk in youtube_links
            )
            extra_lists_html += f"""
            <div style="margin-top:14px;">
              <div style="font-size:0.78rem;text-transform:uppercase;letter-spacing:0.6px;color:var(--text-muted,#666666);margin-bottom:6px;font-weight:700;">Project YouTube Links</div>
              <ul style="margin:0;padding-left:18px;list-style:none;">{yt_items}</ul>
            </div>"""

        if asset_links:
            asset_items = "".join(
                f'<li style="margin-bottom:6px;"><a href="{_html_mod.escape(lnk["url"])}" target="_blank" rel="noopener noreferrer" '
                f'style="color:var(--primary-color,#DE2626);text-decoration:underline;">&#128279; {_html_mod.escape(lnk["label"])}</a></li>'
                for lnk in asset_links
            )
            extra_lists_html += f"""
            <div style="margin-top:14px;">
              <div style="font-size:0.78rem;text-transform:uppercase;letter-spacing:0.6px;color:var(--text-muted,#666666);margin-bottom:6px;font-weight:700;">Project Assets &amp; Links</div>
              <ul style="margin:0;padding-left:18px;list-style:none;">{asset_items}</ul>
            </div>"""

        era_badge_html = ""
        if bejson_era in ("104", "105"):
            era_bg = "#DE2626" if bejson_era == "105" else "#111111"
            era_badge_html = (
                f'<span style="font-family:monospace;font-size:0.72rem;font-weight:700;'
                f'padding:2px 8px;border-radius:3px;background:{era_bg};color:#FFFFFF;">'
                f'BEJSON {bejson_era} &middot; NoSQL</span>'
            )

        gh_stats_html = ""
        gh_stats = meta.get("project_github_stats")
        if isinstance(gh_stats, dict) and gh_stats.get("full_name"):
            stat_items = [
                ("Stars", str(gh_stats.get("stars", 0))),
                ("Forks", str(gh_stats.get("forks", 0))),
                ("Issues", str(gh_stats.get("open_issues", 0))),
            ]
            if gh_stats.get("language"):
                stat_items.append(("Lang", str(gh_stats["language"])))
            if gh_stats.get("license"):
                stat_items.append(("License", str(gh_stats["license"])))
            if gh_stats.get("pushed_at"):
                stat_items.append(("Updated", str(gh_stats["pushed_at"])[:10]))
            pills = "".join(
                f'<span style="display:inline-flex;align-items:center;gap:4px;padding:4px 9px;'
                f'background:var(--bg-body,#FFFFFF);border:1px solid var(--border-color,#DDDDDD);'
                f'border-radius:3px;font-family:monospace;font-size:0.76rem;color:var(--text-color,#111111);">'
                f'<strong style="color:var(--primary-color,#DE2626);">{_html_mod.escape(lbl)}:</strong> '
                f'{_html_mod.escape(val)}</span>'
                for lbl, val in stat_items
            )
            gh_stats_html = (
                f'<div class="project-github-stats" style="margin-top:12px;padding-top:12px;'
                f'border-top:1px solid var(--border-color,#E0E0E0);">'
                f'<div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.6px;'
                f'color:var(--text-muted,#666666);font-weight:700;margin-bottom:8px;">'
                f'GitHub Telemetry &middot; {_html_mod.escape(str(gh_stats["full_name"]))}</div>'
                f'<div style="display:flex;flex-wrap:wrap;gap:6px;">{pills}</div></div>'
            )

        links_card_html = ""
        if primary_buttons or extra_lists_html or era_badge_html or gh_stats_html:
            buttons_row = (
                f'<div style="display:flex;flex-wrap:wrap;gap:10px;">{"".join(primary_buttons)}</div>'
                if primary_buttons else ""
            )
            links_card_html = f"""
<div class="project-links-card" style="background:var(--bg-card,#F8F8F8);border:1px solid var(--card-border,var(--border-color,#E0E0E0));border-radius:var(--border-radius,4px);padding:18px 20px;margin-bottom:28px;">
  <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:10px;">
    <span style="font-size:0.75rem;text-transform:uppercase;letter-spacing:0.8px;color:var(--primary-color,#DE2626);font-weight:700;">Project Resources</span>
    {era_badge_html}
  </div>
  {buttons_row}
  {gh_stats_html}
  {extra_lists_html}
</div>"""

        return f"{video_html}{links_card_html}{body}"


RENDERER_REGISTRY: Dict[str, PageTypeRenderer] = {
    'standard': StandardPageRenderer(),
    'page': StandardPageRenderer(),
    'video': VideoPageRenderer(),
    'document': DocumentPageRenderer(),
    'project': ProjectPageRenderer(),
}

def render_page(page_type: str, page_data: Dict[str, Any], meta_data: Optional[Dict[str, Any]] = None) -> str:
    renderer = RENDERER_REGISTRY.get(page_type.lower(), RENDERER_REGISTRY['standard'])
    return renderer.render(page_data, meta_data)


def render_project_link_strip(
    project_title: str,
    project_page_href: str,
    meta_data: Optional[Dict[str, Any]] = None,
) -> str:
    """Renders a compact single horizontally scrolling row strip of project links below a post hero."""
    meta = meta_data or {}
    pills: List[str] = []

    era = str(meta.get("project_bejson_era") or "").strip()
    if era in ("104", "105"):
        era_bg = "#DE2626" if era == "105" else "#111111"
        pills.append(
            f'<span style="flex:0 0 auto;white-space:nowrap;padding:5px 9px;border-radius:3px;'
            f'background:{era_bg};color:#FFFFFF;font-family:monospace;font-size:0.74rem;font-weight:700;">'
            f'BEJSON {era}</span>'
        )

    pills.append(
        f'<a href="{_html_mod.escape(project_page_href)}" '
        f'style="flex:0 0 auto;white-space:nowrap;display:inline-flex;align-items:center;gap:5px;'
        f'padding:5px 11px;border-radius:3px;background:var(--primary-color,#DE2626);color:#FFFFFF;'
        f'text-decoration:none;font-size:0.78rem;font-weight:700;">'
        f'&#128736; {_html_mod.escape(project_title)}</a>'
    )

    raw_gh = str(meta.get("project_github_url") or "").strip()
    gh_url = re.sub(r"\.git/?$", "", raw_gh, flags=re.IGNORECASE) if raw_gh else ""
    if gh_url:
        pills.append(
            f'<a href="{_html_mod.escape(gh_url)}" target="_blank" rel="noopener noreferrer" '
            f'style="flex:0 0 auto;white-space:nowrap;display:inline-flex;align-items:center;gap:5px;'
            f'padding:5px 10px;border-radius:3px;background:var(--bg-card,#F4F4F4);color:var(--text-color,#111111);'
            f'border:1px solid var(--border-color,#DDDDDD);text-decoration:none;font-size:0.78rem;font-weight:600;">'
            f'&#128187; GitHub</a>'
        )

    for feat in _parse_labeled_links(meta.get("project_featured_links")):
        pills.append(
            f'<a href="{_html_mod.escape(feat["url"])}" target="_blank" rel="noopener noreferrer" '
            f'style="flex:0 0 auto;white-space:nowrap;display:inline-flex;align-items:center;gap:5px;'
            f'padding:5px 10px;border-radius:3px;background:var(--bg-card,#F4F4F4);color:var(--primary-color,#DE2626);'
            f'border:1px solid var(--primary-color,#DE2626);text-decoration:none;font-size:0.78rem;font-weight:600;">'
            f'&#11088; {_html_mod.escape(feat["label"])}</a>'
        )

    gem_url = str(meta.get("project_gemini_notepad_url") or "").strip()
    if gem_url:
        pills.append(
            f'<a href="{_html_mod.escape(gem_url)}" target="_blank" rel="noopener noreferrer" '
            f'style="flex:0 0 auto;white-space:nowrap;display:inline-flex;align-items:center;gap:5px;'
            f'padding:5px 10px;border-radius:3px;background:var(--bg-card,#F4F4F4);color:var(--text-color,#111111);'
            f'border:1px solid var(--border-color,#DDDDDD);text-decoration:none;font-size:0.78rem;font-weight:600;">'
            f'&#128221; Notepad</a>'
        )

    gh_stats = meta.get("project_github_stats")
    if isinstance(gh_stats, dict) and gh_stats.get("full_name"):
        cached_tag = " (Cached)" if gh_stats.get("is_cached") else ""
        pills.append(
            f'<span style="flex:0 0 auto;white-space:nowrap;padding:5px 9px;border-radius:3px;'
            f'background:var(--bg-card,#F4F4F4);border:1px solid var(--border-color,#DDDDDD);'
            f'font-family:monospace;font-size:0.74rem;color:var(--text-muted,#555555);">'
            f'&#9733; {int(gh_stats.get("stars", 0))} &middot; &#9095; {int(gh_stats.get("forks", 0))}{cached_tag}</span>'
        )

    return (
        '<nav class="project-link-strip" aria-label="Linked Project Resources" '
        'style="display:flex;flex-wrap:nowrap;align-items:center;gap:8px;overflow-x:auto;'
        '-webkit-overflow-scrolling:touch;padding:8px 2px 10px;margin:0 0 22px;'
        'border-bottom:1px solid var(--border-color,#E5E5E5);">'
        + "".join(pills)
        + "</nav>"
    )
