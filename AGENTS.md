# AGENTS.md

## Build / Lint / Test / Run

No build step (flat Python/Flask project, no compiler/bundler).

```bash
# Run the full pytest suite (21 cases: path-guard traversal protection,
# MFDB manifest/entity validation) — operates on a temp copy, never touches
# the live storage/mfdb/ tree directly:
cd tests && python3 -m pytest -v

# Syntax check any file before shipping it:
python3 -m py_compile src/web/BEJSON_CMS_Admin.py

# Full smoke-test (syntax is not enough — a NameError from a missing import
# only surfaces on actual import, not py_compile):
python3 -c "import sys; sys.path.insert(0,'src/web'); import BEJSON_CMS_Admin"

# Run a service directly:
python3 src/web/BEJSON_CMS_Admin.py
```

No linter/formatter config is present in this project — match the existing
style in the file you're editing rather than introducing a new one.

## Code Style & Conventions

- **Library naming standard**: `lib_bejson_<Family>_<name>.py` for every file
  under `src/lib/` (e.g. `lib_bejson_Core_bejson_core.py`,
  `lib_bejson_CMS_cms_core.py`). Existing files predating this standard are
  NOT renamed in place — see Library Immutability below.
- **Snake_case** for all Python variables/functions/fields. **PascalCase**
  only for BEJSON 104a custom top-level headers.
- **Self-describing variable names** are required in all new code — no
  single-letter locals. This was retrofitted across the whole `src/web/`
  tree; do not reintroduce short names in new code.
- **File headers**: every script/module carries a header block — `Library`,
  `Family`, `Description`, `Version`, `Date`, `RELATIONAL_ID` (a UUID4 that
  changes on every real edit, acting as a recency fingerprint). Bump the
  header version and mint a fresh `RELATIONAL_ID` on every functional change,
  not on doc-only or logging-only changes.
- **Library Immutability**: files under `src/lib/` are treated as vendored
  and are not edited casually. A fix is only applied there after the bug is
  independently verified (reproduced, not just read), and it gets documented
  in `docs/` with a dedicated note, per the project's own established
  practice (see historical entries preserved in `.bejson_project.json`).

## Architectural Rules

- **BEJSON positional integrity**: every entity's `Fields` order must match
  `Values` order exactly. New fields are appended to the END of the array —
  never inserted mid-array — or every existing row's positional indexing
  breaks.
- **CMSCore is the only DB interface** application code should use
  (`get_records` / `add_record` / `update_record` / `delete_record` /
  `get_field_map` / `sync_manifest_count`). Never read `storage/mfdb/**`
  files directly — positional field order is an implementation detail
  `CMSCore` already resolves by field name.
- **`update_record()` does a partial merge** — only keys present in the
  `updates` dict are touched. Never pass a field "just to be safe" unless you
  intend to overwrite it; a past bug (external-link pages silently converted
  back to normal pages) came from exactly this mistake.
- **Two-part page write**: a page is a `PageRecord` row in the manifest PLUS
  a standalone 104db content file at `storage/mfdb/pages_db/<uuid>.json`.
  Both are required — writing one without the other produces a 404 or an
  empty page.
- **`sync_count=False` + a single `sync_manifest_count()` call** for any loop
  that writes multiple records in one request — per-record fsync was the
  root cause of a real freeze bug on constrained Android hardware.
- **Media Library is deliberately low-peak-memory**: single serial background
  worker (no multiprocessing — forking duplicates the whole process's memory
  footprint under pressure), PIL `draft()` mode for large JPEGs, header-only
  pixel-count caps before any decode, streamed uploads, chunked hashing,
  server-side pagination. Do not "optimize" this back toward parallelism.
- **Public author bio vs. internal AI persona are separate entities** —
  `AuthorProfile.auth_bio` (shown on the live site) must never be
  auto-populated from `AI_Profile`'s internal voice/persona description.

## Directory Map

| Path | Contents |
|---|---|
| `src/web/BEJSON_CMS_Admin.py` | Thin entry point — registers the 4 Blueprints, starts Flask |
| `src/web/BEJSON_CMS_Shared.py` | Shared constants, path resolution, template rendering (`R()`), auth |
| `src/web/BEJSON_CMS_System.py` | Dashboard, site config, factory reset |
| `src/web/BEJSON_CMS_Content.py` | Pages, categories, apps, authors, HTML import |
| `src/web/BEJSON_CMS_Media.py` | Media Library (upload/gallery/delete/replace/external links) |
| `src/web/BEJSON_CMS_Interface.py` | Home, nav/social/ad config, publish trigger |
| `src/web/BEJSON_CMS_PageEditor.py` | Standalone "V1" page editor with AI generation |
| `src/web/BEJSON_CMS_PageEditorV2.py` | Standalone "V2" API-driven page editor (active development) |
| `src/web/BEJSON_CMS_ProfileManager.py` | AI Persona Hub (`AI_Profile` records) |
| `src/web/BEJSON_CMS_Publisher.py` | Static site generator, reads MFDB, writes `storage/builds/` |
| `src/lib/lib_bejson_CMS_cms_core.py` | `CMSCore` — the only DB interface application code should call |
| `src/lib/lib_bejson_Core_*` | BEJSON/MFDB core: parsing, validation, atomic writes, path guarding |
| `src/lib/lib_cms_persona_writer.py` | Assembles AI system instructions from `AI_Profile` records |
| `src/lib/cli/` | Standalone CLI tools (chunker, ebook/showcase builders) — real `__main__` entry points, not dead code |
| `storage/mfdb/site_master/` | The manifest + per-entity BEJSON 104 files (the actual database) |
| `storage/mfdb/pages_db/` | One 104db content file per page/post, keyed by `page_uuid` |
| `resources/templates/` | Jinja2/HTML skeleton templates for both the admin UI and the published site |
| `resources/styles/` | `dark.css` / `light.css`, synced into `storage/builds/style.css` on publish |
| `tests/` | pytest suite — operates on temp copies only, never the live database |
