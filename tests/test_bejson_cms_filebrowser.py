"""
File:           tests/test_bejson_cms_filebrowser.py
Name:           test_bejson_cms_filebrowser.py
Description:    Tests for src/web/BEJSON_CMS_FileBrowser.py -- the in-app,
                 server-side file picker that replaced every native
                 <input type="file"> (the cause of the Android import freeze).
                 Focus is the security model, since the browse API exposes the
                 device filesystem: root containment, symlink escape, secrets
                 directory deny, extension/size gates, local-only guard.
                 Uses tmp dirs only; never touches storage/mfdb/.
Version:        1.0
Date:           2026-10-11
Author:         Elton Boehnen (written by Claude)
RELATIONAL_ID:  e91c47a2-0b5d-4c38-8f6e-2a7d93b1c504
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "web"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "lib"))

import BEJSON_CMS_FileBrowser as fb  # noqa: E402
from flask import Flask  # noqa: E402


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """A fake storage volume registered as the ONLY browse root."""
    root = tmp_path / "storage_root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setenv("HOME", str(root))
    monkeypatch.setenv("EXTERNAL_STORAGE", str(root))
    monkeypatch.setenv("CMS_FILEBROWSER_STORAGE_MOUNTS", str(tmp_path / "no_such_mount"))
    monkeypatch.delenv("BEJSON_STORAGE_ROOT", raising=False)
    monkeypatch.delenv("BEJSON_PATHS_JSON", raising=False)
    monkeypatch.delenv("CMS_FILEBROWSER_ALLOW_REMOTE", raising=False)
    # project root is also a root by design; point it at the sandbox for isolation
    monkeypatch.setattr(fb, "PROJECT_ROOT", root)
    monkeypatch.setattr(fb, "CONFIG_PATH", root / "config.json")
    monkeypatch.setattr(fb, "THUMB_CACHE_DIR", tmp_path / "thumbs")
    return root, outside


@pytest.fixture()
def client(sandbox):
    app = Flask(__name__)
    app.register_blueprint(fb.filebrowser_cube)
    return app.test_client()


# ── roots / containment ──────────────────────────────────────────────────────
def test_roots_resolve_from_environment(sandbox):
    root, _ = sandbox
    paths = [r["path"] for r in fb.get_browse_roots()]
    assert os.path.realpath(root) in paths


def test_pick_inside_root_ok(sandbox):
    root, _ = sandbox
    target = root / "a.png"
    target.write_bytes(b"x")
    assert fb.resolve_pick(str(target), "image") == target.resolve()


def test_pick_outside_root_rejected(sandbox):
    _, outside = sandbox
    target = outside / "a.png"
    target.write_bytes(b"x")
    with pytest.raises(fb.PickError):
        fb.resolve_pick(str(target), "image")


def test_dotdot_traversal_rejected(sandbox):
    root, outside = sandbox
    (outside / "a.png").write_bytes(b"x")
    sneaky = str(root) + os.sep + ".." + os.sep + "outside" + os.sep + "a.png"
    with pytest.raises(fb.PickError):
        fb.resolve_pick(sneaky, "image")


def test_symlink_escape_rejected(sandbox):
    root, outside = sandbox
    (outside / "secret.png").write_bytes(b"x")
    link = root / "link.png"
    os.symlink(outside / "secret.png", link)
    with pytest.raises(fb.PickError):
        fb.resolve_pick(str(link), "image")


def test_env_secure_directory_denied(sandbox):
    root, _ = sandbox
    secure = root / ".env" / "secure"
    secure.mkdir(parents=True)
    key_file = secure / "secureenv_file.json"
    key_file.write_text("{}")
    with pytest.raises(fb.PickError):
        fb.resolve_pick(str(key_file), "any")
    # kind=keys is the one deliberate exception (key registry import) -- and
    # still extension-gated:
    with pytest.raises(fb.PickError):
        fb.resolve_pick(str(key_file), "keys")
    registry = secure / "keys.bejson"
    registry.write_text("{}")
    assert fb.resolve_pick(str(registry), "keys") == registry.resolve()


# ── kind / size / input hygiene ──────────────────────────────────────────────
def test_extension_gate(sandbox):
    root, _ = sandbox
    page = root / "page.html"
    page.write_text("<p>x</p>")
    assert fb.resolve_pick(str(page), "html")
    with pytest.raises(fb.PickError):
        fb.resolve_pick(str(page), "image")
    assert fb.resolve_pick(str(page), "any")


def test_size_cap(sandbox):
    root, _ = sandbox
    big = root / "big.md"
    big.write_bytes(b"a" * 4096)
    with pytest.raises(fb.PickError):
        fb.resolve_pick(str(big), "markdown", max_bytes=1024)


@pytest.mark.parametrize("bad", ["", None, 123, "relative/path.png", "/x\x00y.png"])
def test_bad_input_rejected(sandbox, bad):
    with pytest.raises(fb.PickError):
        fb.resolve_pick(bad, "image")


def test_directory_is_not_a_file(sandbox):
    root, _ = sandbox
    folder = root / "folder.png"
    folder.mkdir()
    with pytest.raises(fb.PickError):
        fb.resolve_pick(str(folder), "image")


def test_unknown_kind(sandbox):
    root, _ = sandbox
    (root / "a.png").write_bytes(b"x")
    with pytest.raises(fb.PickError):
        fb.resolve_pick(str(root / "a.png"), "nonsense")


def test_resolve_picks_dedupes_and_collects_errors(sandbox):
    root, outside = sandbox
    good = root / "g.png"
    good.write_bytes(b"x")
    (outside / "b.png").write_bytes(b"x")
    valid, errors = fb.resolve_picks([str(good), str(good), str(outside / "b.png")], "image")
    assert [p.name for p in valid] == ["g.png"]
    assert len(errors) == 1


def test_parse_path_list():
    assert fb.parse_path_list('["/a/b.html", "/c.html"]') == ["/a/b.html", "/c.html"]
    assert fb.parse_path_list("/a.html\n/b.html\n\n") == ["/a.html", "/b.html"]
    assert fb.parse_path_list("") == []


def test_copy_file_chunked(sandbox, tmp_path):
    root, _ = sandbox
    source = root / "s.bin"
    source.write_bytes(os.urandom(3 * 1024 * 1024 + 17))
    destination = tmp_path / "d.bin"
    assert fb.copy_file_chunked(source, destination, chunk_size=65536) == source.stat().st_size
    assert destination.read_bytes() == source.read_bytes()


# ── listing API ──────────────────────────────────────────────────────────────
def _populate(root):
    (root / "pics").mkdir()
    (root / "pics" / "b.png").write_bytes(b"x")
    (root / "pics" / "a.jpg").write_bytes(b"xx")
    (root / "pics" / "notes.txt").write_text("n")
    (root / "pics" / ".hidden.png").write_bytes(b"x")
    (root / "pics" / "sub").mkdir()


def test_list_filters_by_kind_and_hides_dotfiles(sandbox, client):
    root, _ = sandbox
    _populate(root)
    data = client.get("/fb/api/list", query_string={"path": str(root / "pics"), "kind": "image"}).get_json()
    names = [e["name"] for e in data["entries"]]
    assert names == ["sub", "a.jpg", "b.png"]           # dirs first, then files by name
    assert "notes.txt" not in names and ".hidden.png" not in names
    assert all(e["selectable"] for e in data["entries"] if not e["is_dir"])


def test_list_show_all_marks_unselectable(sandbox, client):
    root, _ = sandbox
    _populate(root)
    data = client.get("/fb/api/list", query_string={"path": str(root / "pics"), "kind": "image", "all": "1"}).get_json()
    notes = next(e for e in data["entries"] if e["name"] == "notes.txt")
    assert notes["selectable"] is False


def test_list_hidden_toggle_and_query(sandbox, client):
    root, _ = sandbox
    _populate(root)
    data = client.get("/fb/api/list", query_string={"path": str(root / "pics"), "kind": "image", "hidden": "1"}).get_json()
    assert ".hidden.png" in [e["name"] for e in data["entries"]]
    data = client.get("/fb/api/list", query_string={"path": str(root / "pics"), "kind": "image", "q": "A."}).get_json()
    assert [e["name"] for e in data["entries"]] == ["a.jpg"]


def test_list_sort_by_size_desc_and_paging(sandbox, client):
    root, _ = sandbox
    _populate(root)
    data = client.get("/fb/api/list", query_string={"path": str(root / "pics"), "kind": "image",
                                                     "sort": "size", "order": "desc"}).get_json()
    assert [e["name"] for e in data["entries"] if not e["is_dir"]] == ["a.jpg", "b.png"]
    page = client.get("/fb/api/list", query_string={"path": str(root / "pics"), "kind": "image",
                                                     "limit": 1}).get_json()
    assert page["has_more"] is True and page["total"] == 3 and len(page["entries"]) == 1


def test_list_outside_root_403(sandbox, client):
    _, outside = sandbox
    response = client.get("/fb/api/list", query_string={"path": str(outside), "kind": "any"})
    assert response.status_code == 403


def test_list_symlink_dir_escape_hidden(sandbox, client):
    root, outside = sandbox
    os.symlink(outside, root / "escape_dir")
    data = client.get("/fb/api/list", query_string={"path": str(root), "kind": "any"}).get_json()
    assert "escape_dir" not in [e["name"] for e in data["entries"]]


def test_list_parent_and_crumbs(sandbox, client):
    root, _ = sandbox
    _populate(root)
    data = client.get("/fb/api/list", query_string={"path": str(root / "pics"), "kind": "any"}).get_json()
    assert data["parent"] == str(root.resolve())
    assert data["crumbs"][-1]["name"] == "pics"
    top = client.get("/fb/api/list", query_string={"path": str(root), "kind": "any"}).get_json()
    assert top["parent"] == ""        # a root's parent is the Locations view


def test_list_empty_path_is_roots_view_and_bad_kind(client):
    assert client.get("/fb/api/list").get_json()["is_roots"] is True
    assert client.get("/fb/api/list", query_string={"path": "/", "kind": "zzz"}).status_code == 400


def test_roots_endpoint_has_kinds(sandbox, client):
    data = client.get("/fb/api/roots").get_json()
    assert data["ok"] and data["roots"] and ".png" in data["kinds"]["image"]


# ── request guard ────────────────────────────────────────────────────────────
def test_remote_requests_blocked_by_default(client):
    response = client.get("/fb/api/roots", environ_overrides={"REMOTE_ADDR": "192.168.1.50"})
    assert response.status_code == 403


def test_remote_allowed_with_env(client, monkeypatch):
    monkeypatch.setenv("CMS_FILEBROWSER_ALLOW_REMOTE", "1")
    assert client.get("/fb/api/roots", environ_overrides={"REMOTE_ADDR": "192.168.1.50"}).status_code == 200


def test_cross_site_blocked(client):
    response = client.get("/fb/api/roots", headers={"Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403


def test_asset_route_whitelist(client):
    assert client.get("/fb/assets/becss-filepicker.js").status_code == 200
    assert client.get("/fb/assets/becss-filepicker.css").status_code == 200
    assert client.get("/fb/assets/../BEJSON_CMS_FileBrowser.py").status_code == 404
    assert client.get("/fb/assets/anything-else.js").status_code == 404


# ── thumbnails ───────────────────────────────────────────────────────────────
def test_thumbnail_generated_and_cached(sandbox, client):
    PIL = pytest.importorskip("PIL.Image")
    root, _ = sandbox
    image_path = root / "t.png"
    PIL.new("RGB", (800, 600), (222, 38, 38)).save(image_path)
    response = client.get("/fb/api/thumb", query_string={"path": str(image_path)})
    assert response.status_code == 200 and response.mimetype == "image/jpeg"
    assert len(list(fb.THUMB_CACHE_DIR.glob("*.jpg"))) == 1
    client.get("/fb/api/thumb", query_string={"path": str(image_path)})
    assert len(list(fb.THUMB_CACHE_DIR.glob("*.jpg"))) == 1      # cache hit, no duplicate


def test_thumbnail_rejects_non_image_and_outside(sandbox, client):
    root, outside = sandbox
    (root / "n.txt").write_text("x")
    (outside / "o.png").write_bytes(b"x")
    assert client.get("/fb/api/thumb", query_string={"path": str(root / "n.txt")}).status_code == 404
    assert client.get("/fb/api/thumb", query_string={"path": str(outside / "o.png")}).status_code == 404


def test_corrupt_image_thumbnail_does_not_500(sandbox, client):
    pytest.importorskip("PIL.Image")
    root, _ = sandbox
    (root / "bad.png").write_bytes(b"not really a png")
    assert client.get("/fb/api/thumb", query_string={"path": str(root / "bad.png")}).status_code == 404
