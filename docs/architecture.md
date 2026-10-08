# Architecture

## Components

**BEJSON_CMS_Admin.py** — the registered Flask entry point. Imports and
registers four Blueprints with no URL prefix (routes are flat/absolute, e.g.
`/pages`, not `/content/pages`), plus a global `before_request` auth hook so
every admin route requires authentication (a real gap — roughly 48 of ~50
routes had none — closed in a full sweep).

- **System cube** (`BEJSON_CMS_System.py`) — dashboard stats, `SiteConfig`
  key/value editing, factory reset (`/reset`, `/reset/confirm`), the
  `_ensure_uncategorized_category()` and `_seed_default_brand_and_author()`
  self-heal routines that run on every startup so a permanent
  `Uncategorized` category and a default author/brand-asset set survive even
  a full wipe.
- **Content cube** (`BEJSON_CMS_Content.py`) — `PageRecord` CRUD + duplicate,
  `Category` CRUD, `StandaloneApp` CRUD (ZIP-extract with a 300MB
  uncompressed-size guard checked from the ZIP's central directory, no
  decompression needed), `AuthorProfile` CRUD, and the HTML-import pipeline
  (preview → confirm → per-item processing via `/api/import/process_item`).
- **Media cube** (`BEJSON_CMS_Media.py`) — `MediaAsset`/`ExternalMedia` CRUD.
  Uploads stream straight to disk, then a job dict is queued; a single serial
  background worker (`_asset_worker`) does hashing/dedup/DB-registration/
  thumbnailing one file at a time, sleeping and calling `gc.collect()`
  between jobs to bound peak memory on constrained hardware.
- **Interface cube** (`BEJSON_CMS_Interface.py`) — the CMS's own home page,
  `NavLink`/`SocialLink`/`AdUnit` config, and the `/publish` trigger that
  hands off to `BEJSON_CMS_Publisher.py`.

**BEJSON_CMS_PageEditor.py** ("V1") and **BEJSON_CMS_PageEditorV2.py** ("V2")
are separate standalone Flask apps, not Blueprints of the Admin app. Both
read/write the same page-content contract (name-based field-map lookups, not
fixed positional indices) and are confirmed cross-compatible — a page created
in one loads and saves correctly in the other. V2 is API-driven (JSON
endpoints under `/api/*`) and under active separate development; V1 is the
older server-rendered form-based editor. Both include AI generation features
that call `lib_cms_persona_writer.py` to layer an `AI_Profile`'s system
instruction on top of required task formatting when an author/persona is
selected. V2's `/api/tasking/*` routes generate through
`PersonaWriter.generate_with_fallback()` (pkg142) -- a model-cascade +
token-budget architecture ported from the companion React CMS's
server-side Gemini proxy: a 429 (quota)/503 (overloaded) response rotates
to the next key and, once a model's keys are exhausted, the next model in
a fixed fallback list, rather than failing on the first error. The two
CMS codebases' generation behavior is intentionally kept in sync this way
rather than diverging.

**BEJSON_CMS_ProfileManager.py** ("Persona Hub") manages `AI_Profile` records
(25 fields — internal voice/tone/domain/creativity settings for AI page
generation). It upserts a matching `AuthorProfile` row so the persona name
is selectable as a byline, but never copies the persona's internal
description into the public `auth_bio` field — those are deliberately
decoupled so AI-flavored internal notes never leak onto the live site.

**BEJSON_CMS_Publisher.py** is the static-site generator. It reads every
entity through `CMSCore`, dispatches page body rendering to polymorphic
strategy renderers (`BEJSON_CMS_Renderers.py` — supporting `StandardPageRenderer`,
`VideoPageRenderer`, `DocumentPageRenderer`), renders the `resources/templates/*.html`
skeletons, generates per-page excerpts (`_generate_excerpt()` — falls back
to a 30-word plain-text excerpt when no meta description is set), filters ad
units by `ad_zone`, and writes the complete output to `storage/builds/`
(`index.html`, `style.css`, `category/<slug>/`, `page/<category>/<slug>/`,
`apps/`, `assets/`).

## Canonical Naming Taxonomy & Schema Architecture

All live database entities adhere to a single source of truth defined in `src/lib/lib_bejson_CMS_taxonomy.py`:
- **Canonical Field Prefixes**: Every entity's fields use explicit snake_case tags:
  - `PageRecord` → `page_` (`page_uuid`, `page_title`, `page_slug`, `page_cat_name`, `page_type`, `page_author_name`, `page_featured_img`, `page_created_at`, `page_external_url`, `page_cat_uuid`, `page_author_uuid`)
  - `AuthorProfile` → `author_` (`author_uuid`, `author_display_name`, `author_bio`, `author_avatar_url`)
  - `MediaAsset` → `asset_` (`asset_uuid`, `asset_filename`, `asset_original_name`, `asset_file_hash`, `asset_file_size`, `asset_mime_type`, `asset_uploaded_at`)
  - `ExternalMedia` → `extmedia_` (`extmedia_uuid`, `extmedia_name`, `extmedia_type`, `extmedia_url`, `extmedia_created_at`)
  - `Category` → `cat_` (`cat_uuid`, `cat_name`, `cat_slug`)
  - `AdUnit` → `ad_` (`ad_uuid`, `ad_name`, `ad_banner_url`, `ad_target_url`, `ad_zone`, `ad_active`)
  - `NavLink` → `nav_` (`nav_uuid`, `nav_display_label`, `nav_target_url`)
  - `SiteConfig` → `sys_` (`sys_uuid`, `sys_key`, `sys_value`)
  - `SocialLink` → `social_` (`social_uuid`, `social_platform_name`, `social_target_url`)
  - `StandaloneApp` → `app_` (`app_uuid`, `app_name`, `app_slug`, `app_description`, `app_entry_file`, `app_featured_img`)
- **Synthetic UUID Primary Keys**: Every table contains a synthetic `<prefix>_uuid` RFC 4122 v4 primary key column, resolved by name via Field Map Cache (System Development Policy §6.2) rather than a fixed position — six entities (`Category`, `AuthorProfile`, `MediaAsset`, `NavLink`, `SiteConfig`, `SocialLink`) plus `AI_Profile` had theirs injected after the fact (pkg135, "give them all uuids") rather than present from the schema's original design, so its column position varies by how a given live install got it: first for data migrated directly via `tools/migrate_taxonomy.py`, last for anything backfilled by `BEJSON_CMS_System.py`'s self-heal on boot. Correctness never depends on position either way.
- **`PageRecord`'s `page_cat_uuid`/`page_author_uuid`** (pkg137): a resolvable identity link to the live `Category`/`AuthorProfile` row, kept in sync on every write — NOT yet what rendering, permalinks, or related-content matching actually use. Every read path (`BEJSON_CMS_Publisher.py` included) still matches on `page_cat_name`/`page_author_name`, the plain strings. The two `_uuid` fields are additive, immune to the rename/case-collision class of bug that the plain-string fields aren't, but converting the read paths to resolve through them instead is a separate, larger, not-yet-made decision.

## Data Flow

```
Browser (admin UI)
     │  form POST / fetch
     ▼
Blueprint route (System/Content/Media/Interface)
     │  db.add_record() / update_record() / delete_record()
     ▼
CMSCore (lib_bejson_CMS_cms_core.py)
     │  mfdb_core_add_entity_record() / update_entity_record_bulk()
     ▼
lib_bejson_Core_mfdb_core.py
     │  per-manifest RLock → atomic write (.tmp → fsync → os.replace)
     ▼
storage/mfdb/site_master/104a.mfdb.bejson (manifest)
storage/mfdb/site_master/data/<entity>.bejson (entity file)
```

Page bodies follow a parallel, separate path: `PageRecord` metadata goes
through the flow above, while the actual `html_body` is read/written
directly as a standalone 104db document at
`storage/mfdb/pages_db/<page_uuid>.json` — Flask reads it by UUID at request
time, it is never registered as a CMSCore "entity."

Publishing is a one-way read: `BEJSON_CMS_Publisher.py` reads the live MFDB
tree (never writes back to it) and renders `storage/builds/` from scratch,
combined with the shared stylesheets in `resources/styles/`.

Media upload is asynchronous within a single request/process: the HTTP
request only streams the file to disk and enqueues a job; the actual
hash/dedup/DB-write/thumbnail work happens on the `_asset_worker` background
thread, decoupled from the request so a slow decode can't hang the whole
app (a real, previously-shipped bug — see the seeded project history in
`.bejson_project.json`).

## Upstream library sync status (checked against CLI_AI-V16-PKG30, pkg143)

The Core libraries in `src/lib/` are vendored copies of the same Core
family used by the CLI_AI project. Last full comparison (every file in the
PKG30 zip, including nested archives, not just `lib/`):

| Library | Result |
|---|---|
| `lib_bejson_Core_bejson_validator` | **Updated** 2.1.0 → 2.2.1 (corrective; same rejection behavior, clearer 104a message). |
| `lib_bejson_Core_bejson_env` | **Updated** `source_env()` (adds `secureenv_file.py/.json`, parses `.json` without `exec`). Version stays 2.1.2 upstream. Dormant here: the CMS only imports `resolve_path()`, which is byte-identical. |
| `lib_bejson_Core_bejson_path_guard` | **Kept, CMS ahead.** CMS 1.2.0 has `safe_extract_zip()` (4 call sites); upstream 1.1.0 lacks it. Do NOT overwrite from upstream. |
| `bejson_core`, `bejson_errors`, `mfdb_core`, `mfdb_validator` | Code identical to upstream; the CMS copies carry an extra `Release_Version: 300` header stamp. Nothing to do. |
| `bejson_server`, `gemini_showcase_intro`, `showcase_master` | Identical. |
| `lib_mfdb_chunker_v6` | Not superseded: upstream's `lib_bejson_Core_bejson_chunking` is a different tool. |
| Upstream-only libs (`lib/AI/*`, `bejson_schema`, `104db_parser`, `list_validator`, `provider`, `chunking`) | Deliberately not vendored. The CMS imports none of them; its AI code (`lib_cms_persona_writer.py`) is self-contained. |
