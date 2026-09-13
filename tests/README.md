# Tests

Pytest suite, started 2026-07-05 per the full-scope report's recommendation
to begin with the highest-blast-radius files first. Expanded 2026-09-04
per the P1 audit item ("Add integration tests for Admin auth hook +
CMSCore CRUD cycles") plus a permanent regression guard for a real
incident that session (see the pkg128 changelog entry / the app-uuid
test's own docstring for the full story).

Run with: `pip install pytest --break-system-packages && pytest tests/ -v`

Covers:
- `lib_bejson_Core_bejson_path_guard.py` — path traversal protection, storage path resolution
- `lib_bejson_Core_mfdb_validator.py` — manifest/entity validation, including the NEW-08 path-traversal remediation, run against a temp copy of the real live database (never touches the actual `storage/mfdb/`)
- `lib_bejson_CMS_cms_core.py` — full CRUD round-trip (add/get/update/delete), against a throw-away MFDB built fresh per test
- `BEJSON_CMS_Admin.py` — the global `before_request` auth hook, across a representative sample of routes on every registered blueprint, both rejection paths (no auth, wrong password, wrong username) and the acceptance path
- `BEJSON_CMS_Content.py` — `app_delete()`/`serve_app()` UUID validation, the permanent regression test for a real `app_uuid=".."` destructive-deletion bug found and fixed this session

Every Flask-app test isolates filesystem/DB state via `monkeypatch` on the
app module's own path/db constants (`APPS_STORAGE`, `db`, etc.) rather
than environment variables — `CMS_DATA_ROOT` is **not** respected by any
web app in this project, only by `cms-manage.py`. Learned this the hard
way; see the app-uuid test file's docstring.

Not yet covered: the other 4 web apps' routes (PageEditor, PageEditorV2,
Publisher, ProfileManager), the CLI (`cms-manage.py`), and the Publisher
build pipeline. Still not a complete suite, but the highest-value gaps
(auth, CRUD, and a real found vulnerability) are now closed.
