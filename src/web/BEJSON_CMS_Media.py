"""
Library:         BEJSON_CMS_Media
Family:          BEJSON_CMS
Description:     Media Cube: gallery, uploads, background thumbnail worker, external media links. In-process serial worker thread by design (no multiprocessing) — see comment block below.
Version:         18.32
Library_Version: 58
Date:            2026-09-20
RELATIONAL_ID:   78da8c87-9b66-4843-9d80-df1412affdb6
CHANGE (2026-09-20): PKG140 -- found while continuing the sweep right after
pkg139 shipped: the CSP/upload-sanitization work only covered serve_asset()
and the upload handler. Two more gaps in the SAME file, same attack class:
(1) serve_thumb()'s fallback path (serves the raw original when no
thumbnail exists yet -- which for .svg is ALWAYS, since .svg is not in
_THUMBABLE_EXT) had no CSP header, even though the gallery view's <img>
tags always request /assets/thumb/<file> for every asset row regardless of
type -- this was a live, reachable path, not theoretical. Fixed with the
same header logic as serve_asset(). (2) assets_replace() -- overwriting an
existing asset's content while keeping the same stored filename -- never
sanitized at all, for any extension, meaning "replace" was an entirely
separate, unprotected write path to the same files the upload handler had
just been locked down: someone could overwrite an already-sanitized SVG's
content with raw malicious bytes under the same filename. Fixed to run the
same sanitize_svg() check when the existing file's extension is .svg.
Verified live: created a real SVG asset, replaced it with a payload
containing <script>+onload= cookie exfiltration, confirmed the on-disk
content came out completely inert (down to a bare <svg/>); confirmed
serve_thumb()'s fallback now sends the CSP header for a real SVG request.
Also confirmed a non-.svg asset is completely unaffected by either change.
CHANGE (2026-09-20): PKG139 -- SVG re-enabled (Elton's call, resolving audit
H-3 -- disabled since pkg133 pending a sanitizer). ".svg" added back to
ALLOWED_ASSET_EXTENSIONS. Upload path now runs every .svg through the new
lib_bejson_Core_svg_sanitizer.sanitize_svg() (stdlib-only, strict
allowlist) before writing to disk -- a file that fails sanitization is
rejected outright, no partial/unsafe version is ever saved. serve_asset()
adds Content-Security-Policy: script-src 'none'; sandbox; on .svg
responses as defense in depth on top of upload-time sanitization.
Live-verified through the real Flask upload route, not just the sanitizer
library's own unit tests: a malicious SVG (<script> + onload= cookie
exfiltration) came out the other end on disk completely inert; a
genuinely broken file was correctly rejected with nothing written or
queued; confirmed the CSP header is actually present on a served .svg
response. All test assets cleaned up after, live data confirmed back to
its 4-asset baseline.
CHANGE (2026-09-13): PKG135 -- "give them all uuids" (Elton). MediaAsset's
upload-commit add_record() call now includes a real asset_uuid -- it
didn't, so every uploaded asset was landing with asset_uuid: None. Rename/
delete for MediaAsset deliberately left keyed by asset_filename (not
converted to asset_uuid) -- asset_filename is already a stable,
collision-free identifier (uuid.hex-based, generated once at upload and
never changed by rename, per the pkg133 H-2 audit finding), so this isn't
the same bug class as AuthorProfile/Category; the new asset_uuid field
exists for future FK use (e.g. a video/document page type referencing a
specific asset by stable ID) rather than fixing an active identity bug
here.
CHANGE (2026-09-12): PKG133 -- external audit remediation (H-2, H-3). H-2:
the external-links table and YouTube-card "Copy URL" buttons still
interpolated extmedia_url raw into an inline onclick="copyAssetPath('...')"
string -- html.escape() alone doesn't make a value safe inside inline
event-handler JS source, since the browser decodes entities in an
attribute value before running onclick as JS (same bug class as the
pkg123/pkg124 rename/lightbox fixes; these two call sites were missed by
both passes). Converted both to data-url + the existing document.body
delegation handler (added a .copy-url-btn branch). H-3: removed ".svg"
from ALLOWED_ASSET_EXTENSIONS -- serve_asset() does send_file() with no
content inspection, so an uploaded SVG carrying <script>/on*= payloads was
served back verbatim (stored XSS); no sanitizer exists. Zero-risk fix per
audit; re-add once sanitization/CSP is implemented.
CHANGE (2026-08-06): PKG74 - added "PDF" as a selectable Type on the
External Media Link form (was Image/Video/Other only), so an external
PDF URL can be tagged and picked up by the new Insert-PDF picker in
BEJSON_CMS_PageEditor.py / BEJSON_CMS_PageEditorV2.py. Also fixed the
gallery row thumbnail for non-image assets (PDF, mp4, mp3, etc.) - it
was pointing an <img> tag at /assets/thumb/<file>, which for a
non-thumbable file falls back to serving the raw original bytes as an
"image" (broken icon in the browser). Now renders a file-type badge
(📄/🎬/🎵/📦) instead for any extension outside _THUMBABLE_EXT.
"""

import os
import re
import gc
import time
import uuid
import hashlib
import threading as _threading
import queue as _queue
import html as _html_escape
import logging
from pathlib import Path
from datetime import datetime
from flask import Blueprint, request, redirect, flash, send_file, jsonify
from werkzeug.utils import secure_filename

from BEJSON_CMS_Shared import (
    db, R, get_breadcrumbs, require_auth,
    ASSETS_DIR, THUMBS_DIR,
)
from lib_bejson_Core_bejson_path_guard import bejson_safe_join
from lib_bejson_Core_svg_sanitizer import sanitize_svg

try:
    from PIL import Image
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

ALLOWED_ASSET_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg',
                              '.pdf', '.mp4', '.mp3', '.ogg', '.webm', '.ico'}
# SVG re-added (pkg139, Elton: "build sanitizer + re-enable" -- resolves
# audit H-3, open since pkg133). Every .svg upload is now run through
# lib_bejson_Core_svg_sanitizer.sanitize_svg() before being written to
# disk -- see the upload handler below. A file that fails sanitization
# (doesn't parse, isn't an <svg> document) is rejected outright, not
# saved in any form.

media_cube = Blueprint('media', __name__)

# ─── Background thumbnail engine ────────────────────────────────────────────
# =============================================================================
# MEDIA LIBRARY — memory-conscious thumbnail engine
# Rebuilt from scratch (v18.9). Root cause of the original freezes turned out
# to be Pydroid3-specific memory/battery-management crashes on the user's
# device (confirmed resolved by switching to Termux + wakelock) — not purely
# a code bug. Rebuilding anyway with deliberately low peak-memory design so
# it stays safe on constrained devices generally:
#   - No multiprocessing. Forking duplicates this whole process's memory
#     footprint at fork time — the worst possible thing to do when memory is
#     already tight. A single serial background THREAD is used instead
#     (shares memory, no copy, still keeps the request thread non-blocking).
#   - PIL draft() mode: for JPEG, this tells the decoder to decode at a
#     reduced DCT scale (1/2, 1/4, 1/8) DURING decode, so a large photo is
#     never fully decoded at full resolution in memory at all.
#   - Hard pixel-count cap checked from the header (Image.open() only reads
#     header bytes, no pixel decode) before any decode is attempted.
#   - Uploads are streamed straight to disk via Werkzeug's f.save(); this
#     code never calls f.read() on a whole upload.
#   - Hashing reads in fixed-size chunks; never loads a whole file into RAM.
# =============================================================================
THUMB_SIZE = 320
_THUMB_MAX_SOURCE_PIXELS = 40_000_000  # ~40MP header-check cap; skip thumbnailing anything larger rather than risk a big decode
_THUMBABLE_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}

def _yt_id_from_url(raw: str) -> str | None:
    """Same extraction rule as ytIdFromUrlV2() in BEJSON_CMS_PageEditorV2.py's
    JS -- kept identical on purpose so a link that embeds correctly there
    also gets a correct thumbnail here, and vice versa. Accepts either a
    bare 11-char video ID or a full watch/share/embed URL."""
    raw = (raw or "").strip()
    if re.match(r'^[A-Za-z0-9_-]{11}$', raw):
        return raw
    m = re.search(r'(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{11})', raw)
    return m.group(1) if m else None

def _get_file_hash(filepath) -> str:
    """Chunked SHA-256 — never loads the whole file into memory."""
    File_Hash_Accumulator = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            File_Hash_Accumulator.update(chunk)
    return File_Hash_Accumulator.hexdigest()

def _make_thumbnail(filename: str) -> bool:
    if not _PIL_OK:
        return False
    src = ASSETS_DIR / filename
    Thumbnail_Destination_Path = THUMBS_DIR / (Path(filename).stem + ".jpg")
    if not src.exists() or src.suffix.lower() not in _THUMBABLE_EXT:
        return False
    try:
        Source_Image = Image.open(src)
        width, height = Source_Image.size  # header-only peek, no pixel decode yet
        if width * height > _THUMB_MAX_SOURCE_PIXELS:
            logging.warning(f"[THUMB] Skipping {filename}: {width}x{height} exceeds pixel cap")
            Source_Image.close()
            return False
        Source_Image.draft('RGB', (THUMB_SIZE, THUMB_SIZE))  # JPEG fast path; harmless no-op for other formats
        Source_Image = Source_Image.convert('RGB')
        Source_Image.thumbnail((THUMB_SIZE, THUMB_SIZE))
        Source_Image.save(Thumbnail_Destination_Path, 'JPEG', quality=72)
        Source_Image.close()
        return True
    except Exception as e:
        logging.error(f"[THUMB] Failed for {filename}: {e}")
        return False

_asset_process_queue = _queue.Queue()
_ASSET_PROCESS_DELAY_SECONDS = 0.4  # brief pause between items — lets the OS/GC reclaim
                                     # memory from the just-finished item before the next
                                     # one starts, instead of bursting through a whole
                                     # batch back-to-back.

def _process_uploaded_asset(job: dict) -> None:
    """Runs on the single serial _asset_worker thread. One file at a time:
    hash (chunked, memory-safe), dedup check, DB registration, thumbnail.
    Never more than one file's worth of this work is in memory at once."""
    stored_name = job["stored_name"]
    dest_path = ASSETS_DIR / stored_name
    if not dest_path.exists():
        return
    try:
        file_hash = _get_file_hash(dest_path)  # chunked read, memory-safe
        existing = db.get_records("MediaAsset")
        if any(a.get('asset_file_hash') == file_hash for a in existing):
            dest_path.unlink(missing_ok=True)
            logging.info(f"[ASSETS] Discarded duplicate upload: {job.get('original_name')}")
            return

        fsize = dest_path.stat().st_size
        db.add_record("MediaAsset", {
            "asset_uuid": str(uuid.uuid4()),
            "asset_filename": stored_name,
            "asset_original_name": job["asset_original_name"],
            "asset_file_hash": file_hash,
            "asset_file_size": fsize,
            "asset_mime_type": job.get("asset_mime_type") or "application/octet-stream",
            "asset_uploaded_at": datetime.utcnow().isoformat(),
        }, sync_count=False)

        if Path(stored_name).suffix.lower() in _THUMBABLE_EXT:
            _make_thumbnail(stored_name)

        # Sync the manifest fsync once per drained batch, not once per file —
        # the moment the queue is empty, this was the last item in the
        # current batch, so it's the right point to persist the count.
        if _asset_process_queue.empty():
            db.sync_manifest_count("MediaAsset")
    except Exception as e:
        logging.error(f"[ASSETS] Failed processing {job.get('original_name')}: {e}")

def _asset_worker():
    while True:
        try:
            Queued_Asset_Job = _asset_process_queue.get()
            if Queued_Asset_Job is None:
                break
            _process_uploaded_asset(Queued_Asset_Job)
            _asset_process_queue.task_done()
        except Exception as e:
            logging.error(f"[ASSETS] worker loop error: {e}")
        finally:
            # Explicit reclaim before picking up the next queued item, rather
            # than waiting for Python's automatic GC cycle to get around to it.
            gc.collect()
            time.sleep(_ASSET_PROCESS_DELAY_SECONDS)

_threading.Thread(target=_asset_worker, daemon=True).start()

# ─── Routes ──────────────────────────────────────────────────────────────────
ASSETS_PER_PAGE = 24

@media_cube.route('/assets/<path:filename>')
def serve_asset(filename):
    try:
        safe_path = bejson_safe_join(str(ASSETS_DIR), filename)
    except ValueError:
        return "Not found", 404
    response = send_file(safe_path)
    if filename.lower().endswith('.svg'):
        # Defense in depth alongside upload-time sanitization (pkg139): even
        # a sanitized SVG is still parsed and rendered as a document by the
        # browser (not a flat raster image), so a strict CSP here means a
        # sanitizer gap or a future regression doesn't automatically become
        # an executable one -- inline scripts/handlers still won't run even
        # if one somehow made it through.
        response.headers['Content-Security-Policy'] = "script-src 'none'; sandbox;"
        response.headers['Content-Type'] = 'image/svg+xml'
    return response


@media_cube.route('/assets/thumb/<path:filename>')
def serve_thumb(filename):
    try:
        safe_name = bejson_safe_join(str(THUMBS_DIR), Path(filename).stem + ".jpg")
        safe_orig = bejson_safe_join(str(ASSETS_DIR), filename)
    except ValueError:
        return "Not found", 404
    if os.path.exists(safe_name):
        return send_file(safe_name)
    response = send_file(safe_orig)  # fallback: original, until thumb generation catches up
    if filename.lower().endswith('.svg'):
        # Same CSP defense-in-depth as serve_asset() (pkg139) -- SVG is
        # never in _THUMBABLE_EXT, so this fallback is the ONLY path an
        # SVG is ever served through when requested via /assets/thumb/,
        # which the gallery view (below) always does for every asset row
        # regardless of type. Found and fixed same-session as the original
        # SVG re-enable, before it shipped as an inconsistency between the
        # two routes that serve the same files.
        response.headers['Content-Security-Policy'] = "script-src 'none'; sandbox;"
        response.headers['Content-Type'] = 'image/svg+xml'
    return response


@media_cube.route('/assets/list.json', methods=['GET'])
def assets_list_json():
    # Used by the "upload new image" control on the page-edit screen: after
    # POSTing to /assets/upload (which queues the file for async background
    # processing), the edit page polls this to detect when the new filename
    # actually appears, then adds/selects it in the Featured Image dropdown
    # without a full page reload (which would lose unsaved HTML edits).
    # BUGFIX (2026-08-02): was reading get_assets() -- a raw os.listdir() of
    # ASSETS_DIR -- which is a different source of truth than the MediaAsset
    # database the rest of the media library (and the Insert Image picker)
    # actually uses. Switched to db.get_records("MediaAsset") so this stays
    # in sync with everything else instead of being able to see files the
    # DB doesn't know about (or vice versa).
    db.mount()
    assets = db.get_records("MediaAsset")
    return jsonify({"files": [
        {"asset_filename": a.get("asset_filename"), "asset_original_name": a.get("asset_original_name") or a.get("asset_filename")}
        for a in assets
    ]})


@media_cube.route('/assets', methods=['GET'])
def assets_gallery():
    db.mount()
    all_assets = db.get_records("MediaAsset")
    all_assets.sort(key=lambda a: a.get('asset_uploaded_at') or '', reverse=True)

    page = max(1, int(request.args.get('page', 1) or 1))
    total = len(all_assets)
    total_pages = max(1, (total + ASSETS_PER_PAGE - 1) // ASSETS_PER_PAGE)
    page = min(page, total_pages)
    start = (page - 1) * ASSETS_PER_PAGE
    page_assets = all_assets[start:start + ASSETS_PER_PAGE]

    externals = db.get_records("ExternalMedia")
    # Split out YouTube links into their own tab -- this codebase's
    # ExternalMedia 'video' type has only ever meant YouTube (see
    # api_media_list_video() in BEJSON_CMS_PageEditorV2.py: "YouTube videos
    # are never uploaded files, only saved external links"), but they were
    # previously mixed into the same flat Links table as PDFs and everything
    # else, making them hard to find and manage separately.
    youtube_links = [e for e in externals if (e.get('extmedia_type') or '').lower() == 'video']
    other_externals = [e for e in externals if (e.get('extmedia_type') or '').lower() != 'video']
    pending_count = _asset_process_queue.qsize()

    rows = ''
    for a in page_assets:
        fname = a.get('asset_filename', '')
        display_name = _html_escape.escape(a.get('asset_original_name') or fname)
        size_kb = f"{(a.get('asset_file_size') or 0) / 1024:.1f} KB"
        ext = Path(fname).suffix.lower()
        if ext in _THUMBABLE_EXT:
            thumb_html = f'<img src="/assets/thumb/{fname}" loading="lazy" class="media-row-thumb lightbox-trigger" data-src="/assets/{fname}" data-caption="{display_name}">'
        else:
            # Non-thumbable asset (PDF, video, audio, etc.) - the thumb route
            # would otherwise fall back to serving the raw original as an
            # <img> src, which just renders as a broken image icon. Show a
            # type badge instead and open the raw file directly on click.
            badge = {'.pdf': '📄', '.mp4': '🎬', '.webm': '🎬', '.mp3': '🎵', '.ogg': '🎵'}.get(ext, '📦')
            thumb_html = f'<div class="media-row-thumb media-row-thumb-badge" onclick="event.stopPropagation(); window.open(\'/assets/{fname}\', \'_blank\');" title="{ext} file">{badge}</div>'
        rows += f'''
        <div class="media-row" data-filename="{fname}">
          <div class="media-row-header" onclick="toggleMediaRow(this)">
            <input type="checkbox" class="media-select" value="{fname}" onclick="event.stopPropagation(); updateBulkToolbar();">
            {thumb_html}
            <span class="media-row-name">{display_name}</span>
            <span class="media-row-size">{size_kb}</span>
            <span class="media-row-chevron">&#9656;</span>
          </div>
          <div class="media-row-details">
            <button type="button" class="btn btn-secondary btn-sm" onclick="copyAssetPath('/assets/{fname}')">Copy Path</button>
            <button type="button" class="btn btn-secondary btn-sm rename-asset-btn" data-fname="{fname}" data-name="{display_name}">Rename</button>
            <form method="post" action="/assets/replace/{fname}" enctype="multipart/form-data" class="media-replace-form">
              <input type="file" name="file" required>
              <button type="submit" class="btn btn-secondary btn-sm">Replace</button>
            </form>
            <form method="post" action="/assets/delete/{fname}" onsubmit="return confirm('Remove this file?')">
              <button type="submit" class="btn btn-danger btn-sm">Remove</button>
            </form>
          </div>
        </div>'''

    ext_rows = ''
    for e in other_externals:
        e_name = _html_escape.escape(e.get('extmedia_name') or '')
        ext_rows += f'''
        <tr>
          <td>{e_name}</td>
          <td><a href="{_html_escape.escape(e.get('extmedia_url','') or '')}" target="_blank" style="color:var(--accent);">{_html_escape.escape((e.get('extmedia_url') or '')[:60])}</a></td>
          <td>{_html_escape.escape(e.get('extmedia_type') or '')}</td>
          <td>
            <button type="button" class="btn btn-secondary btn-sm copy-url-btn" data-url="{_html_escape.escape(e.get('extmedia_url','') or '')}">Copy URL</button>
            <button type="button" class="btn btn-secondary btn-sm rename-ext-btn" data-uuid="{e.get('extmedia_uuid','')}" data-name="{e_name}">Rename</button>
            <form method="post" action="/assets/external/delete/{e.get('extmedia_uuid','')}" style="display:inline;" onsubmit="return confirm('Delete this link?')">
              <button type="submit" class="btn btn-danger btn-sm">Delete</button>
            </form>
          </td>
        </tr>'''

    yt_cards = ''
    for e in youtube_links:
        e_name = _html_escape.escape(e.get('extmedia_name') or '')
        vid = _yt_id_from_url(e.get('extmedia_url', ''))
        thumb = f'https://img.youtube.com/vi/{vid}/hqdefault.jpg' if vid else ''
        thumb_html = (
            f'<img src="{thumb}" loading="lazy" class="yt-card-thumb yt-thumb-link" data-url="{_html_escape.escape(e.get("extmedia_url","") or "")}">'
            if vid else
            '<div class="yt-card-thumb yt-card-thumb-badge" title="Could not extract a video ID from this URL">&#9654;</div>'
        )
        yt_cards += f'''
        <div class="yt-card">
          {thumb_html}
          <div class="yt-card-body">
            <span class="yt-card-name">{e_name}</span>
            <div class="yt-card-actions">
              <button type="button" class="btn btn-secondary btn-sm copy-url-btn" data-url="{_html_escape.escape(e.get('extmedia_url','') or '')}">Copy URL</button>
              <button type="button" class="btn btn-secondary btn-sm rename-ext-btn" data-uuid="{e.get('extmedia_uuid','')}" data-name="{e_name}">Rename</button>
              <form method="post" action="/assets/external/delete/{e.get('extmedia_uuid','')}" style="display:inline;" onsubmit="return confirm('Delete this video link?')">
                <button type="submit" class="btn btn-danger btn-sm">Delete</button>
              </form>
            </div>
          </div>
        </div>'''

    pagination = ''
    if total_pages > 1:
        for p in range(1, total_pages + 1):
            active = 'btn-primary' if p == page else 'btn-secondary'
            pagination += f'<a href="/assets?page={p}" class="btn {active} btn-sm" style="margin-right:4px;">{p}</a>'

    processing_banner = ''
    if pending_count > 0:
        processing_banner = (
            '<div class="alert" style="background:rgba(222,38,38,0.08); border:1px solid var(--accent); '
            'color:var(--text-main); display:flex; align-items:center; gap:10px;">'
            '<span class="spinner" style="width:16px;height:16px;border:2px solid var(--border);'
            'border-top-color:var(--accent);border-radius:50%;display:inline-block;'
            'animation:spin 0.8s linear infinite;"></span> '
            'Processing ' + str(pending_count) + ' uploaded file(s) — this page will refresh automatically.</div>'
            '<style>@keyframes spin { to { transform: rotate(360deg); } }</style>'
            '<script>setTimeout(function(){ location.reload(); }, 2000);</script>'
        )

    html = f'''
    <div class="page-header"><h1>Media Library</h1><p>{total} file(s) &mdash; page {page} of {total_pages}</p></div>

    <div class="media-tabs">
      <button type="button" class="media-tab active" id="tab-btn-files" onclick="switchMediaTab('files')">Files</button>
      <button type="button" class="media-tab" id="tab-btn-youtube" onclick="switchMediaTab('youtube')">YouTube{(' (' + str(len(youtube_links)) + ')') if youtube_links else ''}</button>
      <button type="button" class="media-tab" id="tab-btn-links" onclick="switchMediaTab('links')">Links{(' (' + str(len(other_externals)) + ')') if other_externals else ''}</button>
    </div>

    <div id="tab-panel-files" class="media-tab-panel">
      <div class="card">
        <div class="card-header"><span class="card-title">Upload Files</span></div>
        <form method="post" action="/assets/upload" enctype="multipart/form-data">
          <input type="file" name="files" multiple accept="image/*,.pdf,.mp4,.mp3,.ogg,.webm" class="form-control" style="margin-bottom:12px;">
          <button type="submit" class="btn btn-primary">Upload</button>
        </form>
      </div>

      {processing_banner}

      <div class="media-toolbar">
        <label class="media-select-all-label">
          <input type="checkbox" id="select-all-media" onclick="toggleSelectAllMedia(this)"> Select All
        </label>
        <span id="bulk-selected-count">0 selected</span>
        <form method="post" action="/assets/bulk_delete" id="bulk-delete-form" onsubmit="return confirm('Delete the selected files?')">
          <input type="hidden" name="filenames" id="bulk-delete-filenames">
          <button type="submit" class="btn btn-danger btn-sm" id="bulk-delete-btn" disabled>Delete Selected</button>
        </form>
      </div>

      <div class="media-list">
        {rows if rows else '<div class="card empty-state"><p>No files uploaded yet.</p></div>'}
      </div>
      <div style="margin-bottom:30px;">{pagination}</div>
    </div>

    <div id="tab-panel-youtube" class="media-tab-panel" style="display:none;">
      <div class="card">
        <div class="card-header"><span class="card-title">Add YouTube Video</span></div>
        <form method="post" action="/assets/external/add" onsubmit="return prepYtSubmit(this)">
          <div class="form-group"><label class="form-label">Name / Title</label><input type="text" name="extmedia_name" class="form-control" required></div>
          <div class="form-group"><label class="form-label">YouTube URL or Video ID</label><input type="text" name="extmedia_url" id="yt-add-url" class="form-control" placeholder="https://www.youtube.com/watch?v=... or the 11-character ID" required></div>
          <input type="hidden" name="extmedia_type" value="video">
          <button type="submit" class="btn btn-primary">Add Video</button>
        </form>
      </div>
      <div class="yt-card-grid">
        {yt_cards if yt_cards else '<div class="card empty-state"><p>No YouTube videos added yet.</p></div>'}
      </div>
    </div>

    <div id="tab-panel-links" class="media-tab-panel" style="display:none;">
      <div class="card">
        <div class="card-header"><span class="card-title">Add External Media Link</span></div>
        <form method="post" action="/assets/external/add">
          <div class="form-group"><label class="form-label">Name</label><input type="text" name="extmedia_name" class="form-control" required></div>
          <div class="form-group"><label class="form-label">URL</label><input type="url" name="extmedia_url" class="form-control" required></div>
          <div class="form-group"><label class="form-label">Type</label>
            <select name="extmedia_type" class="form-control">
              <option value="image">Image</option>
              <option value="video">Video</option>
              <option value="pdf">PDF</option>
              <option value="other">Other</option>
            </select>
          </div>
          <button type="submit" class="btn btn-primary">Add Link</button>
        </form>
      </div>
      <div class="card">
        <div class="table-container"><table><thead><tr><th>Name</th><th>URL</th><th>Type</th><th>Actions</th></tr></thead>
        <tbody>{ext_rows if ext_rows else "<tr><td colspan='4'>No external links yet.</td></tr>"}</tbody></table></div>
      </div>
    </div>

    <div id="media-lightbox" class="media-lightbox" onclick="closeLightbox()">
      <span class="media-lightbox-close" onclick="closeLightbox()">&times;</span>
      <img id="media-lightbox-img" src="" alt="">
      <div id="media-lightbox-caption" class="media-lightbox-caption"></div>
    </div>

    <style>
    .media-tabs {{ display:flex; gap:4px; margin:20px 0 16px; border-bottom:1px solid var(--border); }}
    .media-tab {{ background:none; border:none; padding:10px 18px; font-size:.9rem; font-weight:600; color:var(--text-secondary); cursor:pointer; border-bottom:2px solid transparent; }}
    .media-tab.active {{ color:var(--accent); border-bottom-color:var(--accent); }}
    .yt-card-grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(220px, 1fr)); gap:16px; margin-top:20px; }}
    .yt-card {{ background:var(--bg-secondary); border:1px solid var(--border); border-radius:8px; overflow:hidden; }}
    .yt-card-thumb {{ width:100%; aspect-ratio:16/9; object-fit:cover; display:block; cursor:pointer; background:#000; }}
    .yt-card-thumb-badge {{ display:flex; align-items:center; justify-content:center; font-size:2rem; color:var(--muted); cursor:default; }}
    .yt-card-body {{ padding:10px 12px; }}
    .yt-card-name {{ display:block; font-size:.85rem; font-weight:600; margin-bottom:8px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
    .yt-card-actions {{ display:flex; gap:6px; flex-wrap:wrap; }}
    .media-toolbar {{ display:flex; align-items:center; gap:16px; margin:20px 0 12px; padding:10px 14px; background:var(--bg-secondary); border-radius:8px; border:1px solid var(--border); }}
    .media-select-all-label {{ display:flex; align-items:center; gap:6px; font-size:.85rem; cursor:pointer; }}
    #bulk-selected-count {{ font-size:.8rem; color:var(--text-secondary); }}
    .media-list {{ display:flex; flex-direction:column; gap:10px; margin-bottom:20px; }}
    .media-row {{ border:1px solid var(--border); border-radius:8px; background:var(--bg-secondary); overflow:hidden; }}
    .media-row-header {{ display:flex; align-items:center; gap:12px; padding:10px 14px; cursor:pointer; }}
    .media-row-thumb {{ width:44px; height:44px; object-fit:cover; border-radius:6px; background:var(--bg-body); flex-shrink:0; cursor:zoom-in; }}
    .media-row-thumb-badge {{ display:flex; align-items:center; justify-content:center; font-size:1.3rem; cursor:pointer; }}
    .media-row-name {{ flex:1; font-size:.85rem; word-break:break-all; }}
    .media-row-size {{ font-size:.75rem; color:var(--text-secondary); white-space:nowrap; }}
    .media-row-chevron {{ transition:transform 0.15s; color:var(--text-secondary); }}
    .media-row.expanded .media-row-chevron {{ transform:rotate(90deg); }}
    .media-row-details {{ display:none; padding:0 14px 14px 70px; gap:10px; flex-wrap:wrap; align-items:center; }}
    .media-row.expanded .media-row-details {{ display:flex; }}
    .media-replace-form {{ display:flex; align-items:center; gap:6px; }}
    .media-replace-form input[type=file] {{ max-width:180px; font-size:.78rem; }}
    .media-lightbox {{ display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.9); z-index:9999; text-align:center; cursor:zoom-out; }}
    .media-lightbox.open {{ display:flex; flex-direction:column; align-items:center; justify-content:center; }}
    .media-lightbox img {{ max-width:92vw; max-height:82vh; object-fit:contain; box-shadow:0 0 40px rgba(0,0,0,0.6); }}
    .media-lightbox-caption {{ color:#fff; margin-top:14px; font-size:.9rem; word-break:break-all; padding:0 20px; }}
    .media-lightbox-close {{ position:absolute; top:16px; right:24px; color:#fff; font-size:2.2rem; line-height:1; cursor:pointer; }}
    </style>

    <script>
    function switchMediaTab(name) {{
        document.getElementById('tab-panel-files').style.display = (name === 'files') ? '' : 'none';
        document.getElementById('tab-panel-youtube').style.display = (name === 'youtube') ? '' : 'none';
        document.getElementById('tab-panel-links').style.display = (name === 'links') ? '' : 'none';
        document.getElementById('tab-btn-files').classList.toggle('active', name === 'files');
        document.getElementById('tab-btn-youtube').classList.toggle('active', name === 'youtube');
        document.getElementById('tab-btn-links').classList.toggle('active', name === 'links');
    }}
    function ytIdFromUrl(raw) {{
        // Same rule as BEJSON_CMS_PageEditorV2.py's ytIdFromUrlV2() and
        // this file's own _yt_id_from_url() -- kept identical on purpose.
        raw = raw.trim();
        if (/^[A-Za-z0-9_-]{{11}}$/.test(raw)) return raw;
        const m = raw.match(/(?:v=|youtu\\.be\\/|embed\\/)([A-Za-z0-9_-]{{11}})/);
        return m ? m[1] : null;
    }}
    function prepYtSubmit(form) {{
        const raw = document.getElementById('yt-add-url').value;
        if (!ytIdFromUrl(raw)) {{
            alert('Could not find a YouTube video ID in that URL. Paste the full watch URL or just the 11-character ID.');
            return false;
        }}
        return true;
    }}
    function toggleMediaRow(headerEl) {{
        headerEl.parentElement.classList.toggle('expanded');
    }}
    function toggleSelectAllMedia(checkbox) {{
        document.querySelectorAll('.media-select').forEach(cb => cb.checked = checkbox.checked);
        updateBulkToolbar();
    }}
    function updateBulkToolbar() {{
        var checked = Array.from(document.querySelectorAll('.media-select:checked'));
        document.getElementById('bulk-selected-count').textContent = checked.length + ' selected';
        document.getElementById('bulk-delete-btn').disabled = checked.length === 0;
        document.getElementById('bulk-delete-filenames').value = checked.map(cb => cb.value).join(',');
    }}
    function copyAssetPath(path) {{
        var ta = document.createElement('textarea');
        ta.value = path;
        document.body.appendChild(ta);
        ta.select();
        try {{ document.execCommand('copy'); }} catch (e) {{}}
        document.body.removeChild(ta);
    }}
    function renameAsset(filename, currentName) {{
        var name = prompt('Display name:', currentName);
        if (name === null || name.trim() === '') return;
        var form = document.createElement('form');
        form.method = 'POST';
        form.action = '/assets/rename/' + encodeURIComponent(filename);
        var input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'original_name';
        input.value = name;
        form.appendChild(input);
        document.body.appendChild(form);
        form.submit();
    }}
    function renameExternalLink(mediaUuid, currentName) {{
        var name = prompt('Link name:', currentName);
        if (name === null || name.trim() === '') return;
        var form = document.createElement('form');
        form.method = 'POST';
        form.action = '/assets/external/rename/' + encodeURIComponent(mediaUuid);
        var input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'media_name';
        input.value = name;
        form.appendChild(input);
        document.body.appendChild(form);
        form.submit();
    }}
    function openLightbox(fullSrc, caption) {{
        document.getElementById('media-lightbox-img').src = fullSrc;
        document.getElementById('media-lightbox-caption').textContent = caption || '';
        document.getElementById('media-lightbox').classList.add('open');
    }}
    // Event delegation via data-* attributes, not inline onclick string
    // interpolation -- same fix as pkg123's manage_authors() author-name
    // bug: HTML-escaping a name is not enough to make it safe inside inline
    // event-handler JS source, since the browser decodes entities in
    // attribute values before running the onclick as JS. Delegated once
    // here rather than per-row, so it also covers rows added later without
    // re-binding.
    document.body.addEventListener('click', function(ev) {{
        var t = ev.target.closest('.lightbox-trigger, .rename-asset-btn, .rename-ext-btn, .yt-thumb-link, .copy-url-btn');
        if (!t) return;
        if (t.classList.contains('lightbox-trigger')) {{
            ev.stopPropagation();
            openLightbox(t.dataset.src, t.dataset.caption);
        }} else if (t.classList.contains('rename-asset-btn')) {{
            renameAsset(t.dataset.fname, t.dataset.name);
        }} else if (t.classList.contains('rename-ext-btn')) {{
            renameExternalLink(t.dataset.uuid, t.dataset.name);
        }} else if (t.classList.contains('yt-thumb-link')) {{
            window.open(t.dataset.url, '_blank');
        }} else if (t.classList.contains('copy-url-btn')) {{
            copyAssetPath(t.dataset.url);
        }}
    }}, true);
    function closeLightbox() {{
        document.getElementById('media-lightbox').classList.remove('open');
        document.getElementById('media-lightbox-img').src = '';
    }}
    </script>'''
    return R(html, breadcrumbs=get_breadcrumbs(request.path), active_section='assets')


@media_cube.route('/assets/upload', methods=['POST'])
def assets_upload():
    db.mount()
    files = request.files.getlist('files')
    if not files or not files[0].filename:
        flash('Please select at least one file.', 'error')
        return redirect('/assets')

    queued_count = 0
    skipped_count = 0

    for f in files:
        if not f.filename:
            continue
        Uploaded_File_Extension = Path(f.filename).suffix.lower()
        if Uploaded_File_Extension not in ALLOWED_ASSET_EXTENSIONS:
            flash(f'"{f.filename}" skipped — file type not allowed.', 'error')
            skipped_count += 1
            continue

        stored_name = f"{uuid.uuid4().hex}{Uploaded_File_Extension}"
        dest_path = ASSETS_DIR / stored_name
        try:
            if Uploaded_File_Extension == '.svg':
                # SVGs are sanitized, not streamed straight through -- this
                # requires reading the whole file into memory (unlike every
                # other extension here), but SVGs are icons/logos/diagrams,
                # never large enough for that to matter in practice.
                raw = f.read()
                sanitized = sanitize_svg(raw)
                if sanitized is None:
                    flash(f'"{f.filename}" skipped — not a valid/safe SVG file.', 'error')
                    skipped_count += 1
                    continue
                with open(dest_path, 'wb') as out:
                    out.write(sanitized)
            else:
                f.save(str(dest_path))  # streams straight to disk — never reads whole file into memory
            _asset_process_queue.put({
                "stored_name": stored_name,
                "asset_original_name": f.filename,
                "asset_mime_type": f.content_type,
            })
            queued_count += 1
        except Exception as e:
            flash(f'Error saving "{f.filename}": {e}', 'error')
            skipped_count += 1

    if queued_count:
        flash(f'{queued_count} file(s) queued for processing.' + (f' Skipped {skipped_count}.' if skipped_count else ''), 'success')
    elif skipped_count:
        flash(f'No files queued — {skipped_count} skipped.', 'error')

    return redirect('/assets')


@media_cube.route('/assets/delete/<path:filename>', methods=['POST'])
def assets_delete(filename):
    db.mount()
    filename = secure_filename(filename)
    matches = [a for a in db.get_records("MediaAsset") if a.get('asset_filename') == filename]
    if not matches:
        flash('File not found in Media Library.', 'error')
        return redirect('/assets')

    try:
        (ASSETS_DIR / filename).unlink(missing_ok=True)
        (THUMBS_DIR / (Path(filename).stem + ".jpg")).unlink(missing_ok=True)
    except Exception as e:
        logging.error(f"[ASSETS] Failed to delete file {filename}: {e}")

    Media_Record_Delete_Succeeded = db.delete_record("MediaAsset", "asset_filename", filename)
    if not Media_Record_Delete_Succeeded:
        flash('File deleted from disk, but the database record could not be removed — see log.', 'error')
    else:
        flash('File deleted.', 'success')
    return redirect('/assets')


@media_cube.route('/assets/bulk_delete', methods=['POST'])
def assets_bulk_delete():
    filenames = [f for f in (request.form.get('filenames', '') or '').split(',') if f]
    if not filenames:
        flash('No files selected.', 'error')
        return redirect('/assets')

    db.mount()
    deleted_count = 0
    for raw_name in filenames:
        filename = secure_filename(raw_name)
        try:
            (ASSETS_DIR / filename).unlink(missing_ok=True)
            (THUMBS_DIR / (Path(filename).stem + ".jpg")).unlink(missing_ok=True)
        except Exception as e:
            logging.error(f"[ASSETS] Bulk delete failed to remove file {filename}: {e}")
        if db.delete_record("MediaAsset", "asset_filename", filename):
            deleted_count += 1

    flash(f'Deleted {deleted_count} of {len(filenames)} selected file(s).',
          'success' if deleted_count == len(filenames) else 'error')
    return redirect('/assets')


@media_cube.route('/assets/replace/<path:filename>', methods=['POST'])
def assets_replace(filename):
    """Replaces the file's actual content while keeping the same stored
    filename and MediaAsset record - any page content already referencing
    /assets/<filename> keeps pointing at the same place, now showing the
    new file. Re-hashes, re-sizes, and regenerates the thumbnail."""
    db.mount()
    filename = secure_filename(filename)
    existing = next((a for a in db.get_records("MediaAsset") if a.get('asset_filename') == filename), None)
    if not existing:
        flash('File not found in Media Library.', 'error')
        return redirect('/assets')

    f = request.files.get('file')
    if not f or not f.filename:
        flash('Please choose a replacement file.', 'error')
        return redirect('/assets')

    ext = Path(filename).suffix.lower()
    dest_path = ASSETS_DIR / filename
    try:
        if ext == '.svg':
            # Same sanitization as the upload path (pkg139) -- without
            # this, "replace" was a way to overwrite an already-sanitized
            # SVG's content with unsanitized raw bytes under the same
            # stored filename, completely bypassing the upload-time check.
            # Found in the same sweep that added sanitization to upload,
            # before shipping as a second, unprotected write path to the
            # same files.
            raw = f.read()
            sanitized = sanitize_svg(raw)
            if sanitized is None:
                flash('Replacement file is not a valid/safe SVG — not replaced.', 'error')
                return redirect('/assets')
            with open(dest_path, 'wb') as out:
                out.write(sanitized)
        else:
            f.save(str(dest_path))  # overwrites in place, same stored filename
        file_hash = _get_file_hash(dest_path)
        db.update_record("MediaAsset", "asset_filename", filename, {
            "asset_file_hash": file_hash,
            "asset_file_size": dest_path.stat().st_size,
            "asset_mime_type": f.content_type or existing.get("asset_mime_type", ""),
            "asset_uploaded_at": datetime.utcnow().isoformat(),
        })
        if ext in _THUMBABLE_EXT:
            _make_thumbnail(filename)
        flash('File replaced.', 'success')
    except Exception as e:
        logging.error(f"[ASSETS] Replace failed for {filename}: {e}")
        flash(f'Replace failed: {e}', 'error')
    return redirect('/assets')


@media_cube.route('/assets/rename/<path:filename>', methods=['POST'])
def assets_rename(filename):
    """Renames the display name only — the physical stored filename never
    changes, so any page content already referencing /assets/<filename>
    keeps working."""
    db.mount()
    filename = secure_filename(filename)
    new_name = request.form.get('original_name', '').strip()
    if not new_name:
        flash('Name cannot be empty.', 'error')
        return redirect('/assets')

    ok = db.update_record("MediaAsset", "asset_filename", filename, {"asset_original_name": new_name})
    flash('Renamed.' if ok else 'Rename failed — file not found.', 'success' if ok else 'error')
    return redirect('/assets')


@media_cube.route('/assets/external/add', methods=['POST'])
def assets_external_add():
    db.mount()
    media_name = request.form.get('extmedia_name', '').strip()
    media_url = request.form.get('extmedia_url', '').strip()
    media_type = request.form.get('extmedia_type', 'other')
    if not media_name or not media_url:
        flash('Name and URL are required.', 'error')
        return redirect('/assets')

    db.add_record("ExternalMedia", {
        "extmedia_uuid": str(uuid.uuid4()),
        "extmedia_name": media_name,
        "extmedia_type": media_type,
        "extmedia_url": media_url,
        "extmedia_created_at": datetime.utcnow().isoformat(),
    })
    flash('External link added.', 'success')
    return redirect('/assets')


@media_cube.route('/assets/external/delete/<media_uuid>', methods=['POST'])
def assets_external_delete(media_uuid):
    db.mount()
    ok = db.delete_record("ExternalMedia", "extmedia_uuid", media_uuid)
    flash('Link deleted.' if ok else 'Delete failed — link not found.', 'success' if ok else 'error')
    return redirect('/assets')


@media_cube.route('/assets/external/rename/<media_uuid>', methods=['POST'])
def assets_external_rename(media_uuid):
    # Gives external links the same rename capability regular media files
    # already had via /assets/rename/<filename>.
    db.mount()
    new_name = request.form.get('media_name', '').strip()
    if not new_name:
        flash('Name cannot be empty.', 'error')
        return redirect('/assets')
    ok = db.update_record("ExternalMedia", "extmedia_uuid", media_uuid, {"extmedia_name": new_name})
    flash('Link renamed.' if ok else 'Rename failed — link not found.', 'success' if ok else 'error')
    return redirect('/assets')


# =============================================================================
# ROUTES — APPLICATIONS
# =============================================================================

