"""
File:            src/web/BEJSON_CMS_FileBrowser.py
Library:         BEJSON_CMS_FileBrowser
Family:          BEJSON_CMS
Description:     Server-side (Python) file browser + picker backend. Replaces every
                 browser-native file picker (<input type="file">, FileReader,
                 showOpenFilePicker) in the CMS.

                 WHY THIS EXISTS: opening the browser's native file chooser on Android
                 pushes the browser/app to the background; the OS then kills the
                 backgrounded process and the CMS import "freezes". Here the browsing
                 happens inside the page: the picker modal calls /fb/api/list, which
                 reads the device's filesystem from the Flask process itself, so the
                 page never leaves the foreground. The picker returns absolute SERVER
                 paths; the import routes then copy/read those paths directly (no
                 multipart upload through the browser at all).

                 SECURITY MODEL (every pick passes resolve_pick()):
                   * paths are realpath()-resolved, so symlinks cannot escape;
                   * the resolved path must sit under a browse ROOT (storage volumes,
                     home, project, plus config.json "filebrowser_roots");
                   * anything under a ".env/secure" directory is denied (secrets);
                   * extension allowlist per "kind" and a per-kind size cap;
                   * requests must be loopback + same-origin unless
                     CMS_FILEBROWSER_ALLOW_REMOTE=1 (the browse API exposes the
                     device's filesystem, so it is local-only by default).

                 This module does NOT import BEJSON_CMS_Shared (no circular imports);
                 it is registered as a blueprint in the Admin app and in both Page
                 Editor apps (they are separate Flask processes).
Version:         18.29
Library_Version: 1
Date:            2026-10-11
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
RELATIONAL_ID:   ac396970-9b1a-467b-b9a4-f22174b0cfaf
"""

import os
import json
import hashlib
import logging
import mimetypes
import threading
from pathlib import Path

from flask import Blueprint, request, jsonify, send_file, send_from_directory, abort, has_request_context

VERSION = "18.29"
LOGGER = logging.getLogger("bejson_cms.filebrowser")

SCRIPT_PATH = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_PATH.parent.parent
ASSET_DIR = SCRIPT_PATH / "fb_assets"
CONFIG_PATH = PROJECT_ROOT / "config.json"
THUMB_CACHE_DIR = PROJECT_ROOT / "storage" / "tmp" / "fb_thumbs"

# <link>/<script> tags injected into the <head> of every app that uses the picker.
PICKER_HEAD_TAGS = (
    f'<link rel="stylesheet" href="/fb/assets/becss-filepicker.css?v={VERSION}">'
    f'<script src="/fb/assets/becss-filepicker.js?v={VERSION}" defer></script>'
)

# ─── Kinds: what each picker flavour may select ──────────────────────────────
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico"}
VIDEO_EXTENSIONS = {".mp4", ".webm"}
AUDIO_EXTENSIONS = {".mp3", ".ogg"}
DOCUMENT_EXTENSIONS = {".pdf"}
HTML_EXTENSIONS = {".html", ".htm"}
ZIP_EXTENSIONS = {".zip"}
MARKDOWN_EXTENSIONS = {".md", ".txt", ".markdown"}
KEY_EXTENSIONS = {".bejson"}
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".html", ".htm", ".css", ".json", ".xml", ".sh", ".bash",
    ".txt", ".md", ".csv", ".sql", ".yaml", ".yml", ".ini", ".cfg", ".toml", ".c",
    ".cpp", ".java", ".rb", ".go", ".rs",
}

# kind -> allowed extensions (None = any file)
KIND_EXTENSIONS = {
    "image": IMAGE_EXTENSIONS,
    "video": VIDEO_EXTENSIONS,
    "audio": AUDIO_EXTENSIONS,
    "document": DOCUMENT_EXTENSIONS,
    "media": IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS | DOCUMENT_EXTENSIONS,
    "html": HTML_EXTENSIONS,
    "zip": ZIP_EXTENSIONS,
    "app": HTML_EXTENSIONS | ZIP_EXTENSIONS,
    "code": CODE_EXTENSIONS,
    "markdown": MARKDOWN_EXTENSIONS,
    "keys": KEY_EXTENSIONS,
    "any": None,
}

_MB = 1024 * 1024
# Per-kind size caps. Imports no longer pass through Flask's MAX_CONTENT_LENGTH
# (nothing is uploaded), so the cap lives here instead.
KIND_MAX_BYTES = {
    "image": 100 * _MB, "video": 500 * _MB, "audio": 200 * _MB, "document": 200 * _MB,
    "media": 500 * _MB, "html": 25 * _MB, "zip": 300 * _MB, "app": 300 * _MB,
    "code": 2 * _MB, "markdown": 2 * _MB, "keys": 1 * _MB, "any": 500 * _MB,
}

THUMBABLE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
THUMB_SIZE = 160
THUMB_MAX_SOURCE_PIXELS = 40_000_000
THUMB_CACHE_MAX_FILES = 600
THUMB_CACHE_PRUNE_COUNT = 150

MAX_SCAN_ENTRIES = 20000      # directory entries examined per listing
DEFAULT_PAGE_LIMIT = 200
MAX_PAGE_LIMIT = 500
MAX_PICKS_PER_REQUEST = 500

# Names probed under each storage root to build one-tap shortcuts (names only,
# never absolute paths - they are joined onto roots resolved at runtime).
SHORTCUT_FOLDER_NAMES = ("Download", "Downloads", "DCIM", "Pictures", "Documents", "Movies", "Music")

# OS mount boundary that holds removable volumes on Android. Overridable so no
# path is hard-wired: CMS_FILEBROWSER_STORAGE_MOUNTS=/a:/b (os.pathsep-separated).
_DEFAULT_STORAGE_MOUNTS = ("/storage",)

filebrowser_cube = Blueprint("filebrowser", __name__, url_prefix="/fb")


class PickError(ValueError):
    """A picked path was rejected. Message is safe to show to the user."""


class BrowseDenied(PickError):
    """The request itself is not allowed to use the file browser."""


# ─── Kind helpers ────────────────────────────────────────────────────────────
def classify_extension(extension: str) -> str:
    """Icon class for the picker UI."""
    ext = (extension or "").lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in DOCUMENT_EXTENSIONS:
        return "document"
    if ext in HTML_EXTENSIONS:
        return "html"
    if ext in ZIP_EXTENSIONS:
        return "zip"
    if ext in KEY_EXTENSIONS:
        return "keys"
    if ext in MARKDOWN_EXTENSIONS:
        return "markdown"
    if ext in CODE_EXTENSIONS:
        return "code"
    return "other"


def guess_mime(path) -> str:
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"


# ─── Request guard ───────────────────────────────────────────────────────────
_LOOPBACK_ADDRESSES = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}


def assert_request_allowed() -> None:
    """The browse API exposes the device filesystem: local + same-origin only."""
    if not has_request_context():
        return
    if os.environ.get("CMS_FILEBROWSER_ALLOW_REMOTE") != "1":
        if (request.remote_addr or "") not in _LOOPBACK_ADDRESSES:
            raise BrowseDenied(
                "The file browser only works from the device running the CMS. "
                "Set CMS_FILEBROWSER_ALLOW_REMOTE=1 to allow remote use."
            )
    if request.headers.get("Sec-Fetch-Site", "") == "cross-site":
        raise BrowseDenied("Cross-site requests are not allowed.")


# ─── Roots ───────────────────────────────────────────────────────────────────
def _flatten_paths_document(document) -> dict:
    """Leniently read the canonical env store (paths.json): either a plain
    {NAME: path} object or a BEJSON 104a doc with [name, value, ...] rows."""
    flat = {}
    if not isinstance(document, dict):
        return flat
    if isinstance(document.get("Fields"), list) and isinstance(document.get("Values"), list):
        for row in document["Values"]:
            if isinstance(row, list) and len(row) >= 2 and isinstance(row[0], str) and isinstance(row[1], str):
                flat[row[0].strip().upper()] = row[1].strip()
        return flat
    for key, value in document.items():
        if isinstance(value, str):
            flat[str(key).strip().upper()] = value.strip()
        elif isinstance(value, dict):
            for inner_key, inner_value in value.items():
                if isinstance(inner_value, str):
                    flat[str(inner_key).strip().upper()] = inner_value.strip()
    return flat


def _read_env_paths_store() -> dict:
    candidates = []
    explicit = os.environ.get("BEJSON_PATHS_JSON")
    if explicit:
        candidates.append(Path(explicit))
    for base_variable in ("BEJSON_STORAGE_ROOT", "EXTERNAL_STORAGE"):
        base = os.environ.get(base_variable)
        if base:
            candidates.append(Path(base) / ".env" / "user" / "paths.json")
    for candidate in candidates:
        try:
            if candidate.is_file():
                with open(candidate, "r", encoding="utf-8") as handle:
                    return _flatten_paths_document(json.load(handle))
        except (OSError, ValueError) as error:
            LOGGER.warning("[FB] could not read paths store %s: %s", candidate, error)
    return {}


def _read_extra_roots_from_config() -> list:
    """config.json (BEJSON 104a ScriptConfig): optional row
    ["filebrowser_roots", ["/some/dir", ...], "..."] adds browse roots."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            document = json.load(handle)
        field_names = [str(f.get("name", "")).strip() for f in document.get("Fields", [])]
        name_index = field_names.index("setting_name")
        value_index = field_names.index("setting_value")
        for row in document.get("Values", []):
            if str(row[name_index]).strip() == "filebrowser_roots":
                value = row[value_index]
                if isinstance(value, str):
                    value = [value]
                return [str(item) for item in value if isinstance(item, str)]
    except (OSError, ValueError, IndexError, AttributeError):
        pass
    return []


def _storage_mount_directories() -> list:
    raw = os.environ.get("CMS_FILEBROWSER_STORAGE_MOUNTS")
    return [m for m in raw.split(os.pathsep) if m] if raw else list(_DEFAULT_STORAGE_MOUNTS)


def get_browse_roots() -> list:
    """Browsable roots as [{id, label, path, shortcuts}], resolved at runtime."""
    candidates = []  # (label, raw path)
    env_store = _read_env_paths_store()
    for key, label in (("INTERNAL_STORAGE", "Internal storage"), ("SD_CARD", "SD card"),
                       ("ADMIN", "Admin"), ("PROJECT_ROOT", "Home")):
        if env_store.get(key):
            candidates.append((label, env_store[key]))
    if os.environ.get("EXTERNAL_STORAGE"):
        candidates.append(("Internal storage", os.environ["EXTERNAL_STORAGE"]))
    if os.environ.get("BEJSON_STORAGE_ROOT"):
        candidates.append(("Storage", os.environ["BEJSON_STORAGE_ROOT"]))
    for mount in _storage_mount_directories():
        internal = os.path.join(mount, "emulated", "0")
        if os.path.isdir(internal):
            candidates.append(("Internal storage", internal))
        try:
            with os.scandir(mount) as entries:
                for entry in entries:
                    if entry.name in ("self", "emulated") or entry.name.startswith("."):
                        continue
                    if entry.is_dir():
                        candidates.append((f"SD card / USB ({entry.name})", entry.path))
        except OSError:
            pass
    candidates.append(("Home", os.environ.get("HOME") or os.path.expanduser("~")))
    candidates.append(("CMS project", str(PROJECT_ROOT)))
    for extra in _read_extra_roots_from_config():
        candidates.append((f"Custom ({os.path.basename(extra.rstrip(os.sep)) or extra})", extra))

    roots, seen = [], set()
    for label, raw in candidates:
        try:
            real = os.path.realpath(os.path.expanduser(raw))
        except (OSError, ValueError):
            continue
        if real in seen or not os.path.isdir(real):
            continue
        seen.add(real)
        shortcuts = []
        for folder_name in SHORTCUT_FOLDER_NAMES:
            folder_path = os.path.join(real, folder_name)
            if os.path.isdir(folder_path):
                shortcuts.append({"label": folder_name, "path": folder_path})
        roots.append({
            "id": hashlib.sha1(real.encode("utf-8")).hexdigest()[:10],
            "label": label, "path": real, "shortcuts": shortcuts,
        })
    return roots


# ─── Path safety ─────────────────────────────────────────────────────────────
def _is_under(child: str, parent: str) -> bool:
    try:
        return os.path.commonpath([child, parent]) == parent
    except ValueError:
        return False


def _hits_secret_directory(real_path: str) -> bool:
    parts = [p.lower() for p in Path(real_path).parts]
    return any(parts[i] == ".env" and parts[i + 1] == "secure" for i in range(len(parts) - 1))


def is_path_allowed(real_path: str, roots=None, allow_secure: bool = False) -> bool:
    if not allow_secure and _hits_secret_directory(real_path):
        return False
    for root in (roots if roots is not None else get_browse_roots()):
        if _is_under(real_path, root["path"]):
            return True
    return False


def resolve_pick(raw_path, kind: str, max_bytes=None) -> Path:
    """Validate ONE picked file path and return its resolved Path.
    Raises PickError (user-safe message) on any violation."""
    assert_request_allowed()
    if kind not in KIND_EXTENSIONS:
        raise PickError(f"Unknown pick kind '{kind}'.")
    if not isinstance(raw_path, str) or not raw_path.strip() or "\x00" in raw_path:
        raise PickError("No file path supplied.")
    candidate = raw_path.strip()
    if not os.path.isabs(candidate):
        raise PickError("File path must be absolute.")
    real = os.path.realpath(candidate)
    if not is_path_allowed(real, allow_secure=(kind == "keys")):
        raise PickError(f"'{os.path.basename(real)}' is outside the browsable locations.")
    if not os.path.isfile(real):
        raise PickError(f"'{os.path.basename(real)}' is not a file.")
    allowed = KIND_EXTENSIONS[kind]
    extension = os.path.splitext(real)[1].lower()
    if allowed is not None and extension not in allowed:
        raise PickError(f"'{os.path.basename(real)}': file type {extension or '(none)'} is not allowed here.")
    limit = max_bytes if max_bytes else KIND_MAX_BYTES.get(kind)
    try:
        size = os.path.getsize(real)
    except OSError as error:
        raise PickError(f"Cannot read '{os.path.basename(real)}': {error.strerror or error}")
    if limit and size > limit:
        raise PickError(f"'{os.path.basename(real)}' is {size // _MB} MB; the limit here is {limit // _MB} MB.")
    return Path(real)


def resolve_picks(raw_paths, kind: str, max_bytes=None):
    """Validate many picks. Returns (valid_paths, errors[{path, error}])."""
    assert_request_allowed()
    if not isinstance(raw_paths, (list, tuple)):
        raise PickError("Expected a list of file paths.")
    if len(raw_paths) > MAX_PICKS_PER_REQUEST:
        raise PickError(f"Too many files in one import (max {MAX_PICKS_PER_REQUEST}).")
    valid, errors, seen = [], [], set()
    for raw in raw_paths:
        try:
            path = resolve_pick(raw, kind, max_bytes=max_bytes)
        except PickError as error:
            errors.append({"path": raw if isinstance(raw, str) else "", "error": str(error)})
            continue
        if str(path) in seen:
            continue
        seen.add(str(path))
        valid.append(path)
    return valid, errors


def parse_path_list(raw_value) -> list:
    """Hidden-form-field helper: accepts a JSON array or newline-separated paths."""
    text = (raw_value or "").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            return [p for p in parsed if isinstance(p, str)]
        except ValueError:
            pass
    return [line.strip() for line in text.splitlines() if line.strip()]


def copy_file_chunked(source_path, destination_path, chunk_size: int = 1024 * 1024) -> int:
    """Stream-copy (never reads a whole file into RAM). Returns bytes copied."""
    copied = 0
    with open(source_path, "rb") as source, open(destination_path, "wb") as destination:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            destination.write(chunk)
            copied += len(chunk)
    return copied


class PickedFile:
    """Duck-types the bits of werkzeug's FileStorage that the legacy import code
    uses (.filename, .read(), .save()) so server-path imports can reuse it."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.filename = self.path.name
        self.content_type = guess_mime(self.path)

    def read(self) -> bytes:
        with open(self.path, "rb") as handle:
            return handle.read()

    def save(self, destination) -> None:
        copy_file_chunked(self.path, destination)


# ─── Listing ─────────────────────────────────────────────────────────────────
def _stat_pair(entry):
    try:
        info = entry.stat()
        return info.st_size, info.st_mtime
    except OSError:
        return 0, 0.0


def _crumbs_for(real_dir: str, roots: list):
    best = None
    for root in roots:
        if _is_under(real_dir, root["path"]) and (best is None or len(root["path"]) > len(best["path"])):
            best = root
    if best is None:
        return None, []
    crumbs = [{"name": best["label"], "path": best["path"]}]
    relative = os.path.relpath(real_dir, best["path"])
    if relative != ".":
        running = best["path"]
        for part in relative.split(os.sep):
            running = os.path.join(running, part)
            crumbs.append({"name": part, "path": running})
    return best, crumbs


def list_directory(real_dir: str, kind: str, show_hidden=False, show_all=False, query="",
                   sort="name", descending=False, offset=0, limit=DEFAULT_PAGE_LIMIT) -> dict:
    allowed = KIND_EXTENSIONS.get(kind)
    query = (query or "").strip().lower()
    roots = get_browse_roots()
    directories, files, scanned, truncated = [], [], 0, False
    with os.scandir(real_dir) as iterator:
        for entry in iterator:
            scanned += 1
            if scanned > MAX_SCAN_ENTRIES:
                truncated = True
                break
            name = entry.name
            if not show_hidden and name.startswith("."):
                continue
            if query and query not in name.lower():
                continue
            try:
                is_directory = entry.is_dir()
                if entry.is_symlink():
                    target = os.path.realpath(entry.path)
                    if not is_path_allowed(target, roots):
                        continue
                if is_directory:
                    directories.append(entry)
                    continue
                if not entry.is_file():
                    continue
            except OSError:
                continue
            extension = os.path.splitext(name)[1].lower()
            if allowed is not None and extension not in allowed and not show_all:
                continue
            files.append(entry)

    directories.sort(key=lambda e: e.name.casefold())
    if sort in ("date", "size"):
        stats = {e.path: _stat_pair(e) for e in files}
        index = 1 if sort == "date" else 0
        files.sort(key=lambda e: (stats[e.path][index], e.name.casefold()), reverse=descending)
    else:
        files.sort(key=lambda e: e.name.casefold(), reverse=descending)

    ordered = directories + files
    page = ordered[offset:offset + limit]
    directory_paths = {entry.path for entry in directories}
    entries = []
    for entry in page:
        size, modified = _stat_pair(entry)
        is_directory = entry.path in directory_paths
        extension = "" if is_directory else os.path.splitext(entry.name)[1].lower()
        entries.append({
            "name": entry.name,
            "path": entry.path,
            "is_dir": is_directory,
            "size": 0 if is_directory else size,
            "modified": modified,
            "ext": extension,
            "class": "folder" if is_directory else classify_extension(extension),
            "selectable": (not is_directory) and (allowed is None or extension in allowed),
            "thumb": (not is_directory) and extension in THUMBABLE_EXTENSIONS,
        })

    root, crumbs = _crumbs_for(real_dir, roots)
    parent = ""
    if root is not None and real_dir != root["path"]:
        parent = os.path.dirname(real_dir)
    return {
        "ok": True, "path": real_dir, "parent": parent, "crumbs": crumbs, "kind": kind,
        "total": len(ordered), "offset": offset, "limit": limit,
        "has_more": offset + limit < len(ordered), "truncated": truncated, "entries": entries,
    }


# ─── Thumbnails (serial, memory-conscious - same philosophy as the Media worker) ─
_THUMB_LOCK = threading.Lock()


def _prune_thumb_cache() -> None:
    try:
        cached = sorted(THUMB_CACHE_DIR.glob("*.jpg"), key=lambda p: p.stat().st_mtime)
        if len(cached) > THUMB_CACHE_MAX_FILES:
            for stale in cached[:THUMB_CACHE_PRUNE_COUNT]:
                stale.unlink(missing_ok=True)
    except OSError:
        pass


def build_thumbnail(real_path: str):
    """Return the cached JPEG thumbnail Path for an image, or None."""
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        info = os.stat(real_path)
    except OSError:
        return None
    cache_key = hashlib.sha1(f"{real_path}|{info.st_mtime_ns}|{info.st_size}".encode("utf-8")).hexdigest()
    destination = THUMB_CACHE_DIR / f"{cache_key}.jpg"
    if destination.exists():
        return destination
    with _THUMB_LOCK:  # one decode at a time: never burst memory on a phone
        if destination.exists():
            return destination
        try:
            THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with Image.open(real_path) as source_image:
                width, height = source_image.size  # header-only
                if width * height > THUMB_MAX_SOURCE_PIXELS:
                    return None
                source_image.draft("RGB", (THUMB_SIZE, THUMB_SIZE))
                converted = source_image.convert("RGB")
            converted.thumbnail((THUMB_SIZE, THUMB_SIZE))
            temporary = destination.with_suffix(".tmp")
            converted.save(temporary, "JPEG", quality=70)
            converted.close()
            os.replace(temporary, destination)
            _prune_thumb_cache()
            return destination
        except Exception as error:  # noqa: BLE001 - corrupt images must never 500 the picker
            LOGGER.warning("[FB] thumbnail failed for %s: %s", os.path.basename(real_path), error)
            return None


# ─── Routes ──────────────────────────────────────────────────────────────────
@filebrowser_cube.before_request
def _guard_filebrowser():
    try:
        assert_request_allowed()
    except BrowseDenied as error:
        response = jsonify({"ok": False, "error": str(error)})
        response.status_code = 403
        return response
    return None


@filebrowser_cube.route("/assets/<path:filename>")
def serve_picker_asset(filename):
    if filename not in ("becss-filepicker.js", "becss-filepicker.css"):
        abort(404)
    response = send_from_directory(str(ASSET_DIR), filename)
    response.headers["Cache-Control"] = "no-cache"
    return response


@filebrowser_cube.route("/api/roots")
def api_roots():
    roots = get_browse_roots()
    hint = ""
    if not any("emulated" in r["path"] or r["label"].startswith(("Internal", "SD")) for r in roots):
        hint = ("No device storage is visible to this process. In Termux run "
                "'termux-setup-storage' once, then restart the CMS.")
    kinds = {name: sorted(exts) if exts else [] for name, exts in KIND_EXTENSIONS.items()}
    return jsonify({"ok": True, "roots": roots, "hint": hint, "kinds": kinds})


@filebrowser_cube.route("/api/list")
def api_list():
    kind = request.args.get("kind", "any")
    if kind not in KIND_EXTENSIONS:
        return jsonify({"ok": False, "error": "Unknown kind."}), 400
    raw_path = request.args.get("path", "")
    try:
        offset = max(0, int(request.args.get("offset", 0)))
        limit = min(MAX_PAGE_LIMIT, max(1, int(request.args.get("limit", DEFAULT_PAGE_LIMIT))))
    except ValueError:
        return jsonify({"ok": False, "error": "Bad paging values."}), 400

    if not raw_path:
        return jsonify({"ok": True, "path": "", "parent": "", "crumbs": [], "kind": kind,
                        "total": 0, "offset": 0, "limit": limit, "has_more": False,
                        "truncated": False, "entries": [], "is_roots": True})

    real = os.path.realpath(raw_path)
    if not is_path_allowed(real):
        return jsonify({"ok": False, "error": "That location is outside the browsable folders."}), 403
    if not os.path.isdir(real):
        return jsonify({"ok": False, "error": "Folder not found."}), 404
    sort = request.args.get("sort", "name")
    try:
        listing = list_directory(
            real, kind,
            show_hidden=request.args.get("hidden") == "1",
            show_all=request.args.get("all") == "1",
            query=request.args.get("q", ""),
            sort=sort if sort in ("name", "date", "size") else "name",
            descending=request.args.get("order") == "desc",
            offset=offset, limit=limit,
        )
    except PermissionError:
        return jsonify({"ok": False, "error": "Android denied access to this folder."}), 403
    except OSError as error:
        LOGGER.warning("[FB] list failed for %s: %s", real, error)
        return jsonify({"ok": False, "error": f"Cannot read folder: {error.strerror or error}"}), 500
    return jsonify(listing)


@filebrowser_cube.route("/api/thumb")
def api_thumb():
    real = os.path.realpath(request.args.get("path", ""))
    extension = os.path.splitext(real)[1].lower()
    if extension not in THUMBABLE_EXTENSIONS or not is_path_allowed(real) or not os.path.isfile(real):
        abort(404)
    thumbnail = build_thumbnail(real)
    if thumbnail is None:
        abort(404)
    response = send_file(str(thumbnail), mimetype="image/jpeg")
    response.headers["Cache-Control"] = "private, max-age=3600"
    return response
