# Tests

Minimal pytest suite, started 2026-07-05 per the full-scope report's
recommendation to begin with the highest-blast-radius files first.

Run with: `pip install pytest --break-system-packages && pytest tests/ -v`

Covers so far:
- `lib_bejson_Core_bejson_path_guard.py` — path traversal protection, storage path resolution
- `lib_bejson_Core_mfdb_validator.py` — manifest/entity validation, including the NEW-08 path-traversal remediation, run against a temp copy of the real live database (never touches the actual `storage/mfdb/`)

Not yet covered: everything else. This is a start, not a complete suite.
