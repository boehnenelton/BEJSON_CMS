# Changelog

Full, unabridged change history (every verification step, every file touched)
lives in `.bejson_project.json` at the project root — this file is a
readable summary. Newest at top, oldest at bottom.

## pkg117 — Second external audit: path-traversal fix, reset parity, tracker repair (properly, this time)

- **H-1, security**: `Media.py` and `PageEditorV2.py`'s asset/thumbnail
  serving routes bypassed the project's own path guard. Confirmed
  genuinely exploitable *before* fixing it —
  `/assets/../../../.bejson_project.json` returned this project's own
  tracker file contents with valid auth, not a theoretical gap. Fixed
  with `bejson_safe_join()` (the CMS's own library — fixed without
  hesitation per explicit instruction); re-ran the same attack afterward
  and got a clean 404 with nothing leaked, plus confirmed legitimate
  asset/thumbnail serving still works exactly as before.
- **H-2**: the web factory reset and the CLI factory reset diverged — the
  web reset never seeded `SiteConfig` at all, so a fresh web-reset install
  published with a hardcoded fallback title/description/base_url that had
  nothing to do with the actual site. Added `_seed_default_site_config()`
  to `System.py` as the single source of truth (matching the CLI's
  existing defaults exactly), wired into every reset path — System.py's
  own lifecycle, `factory_reset_confirm()`, and Publisher's reset (which
  already delegates to System.py). Also closed the CLI's `builds/`/
  `tmp/html_imports` wipe gap for parity — deliberately *not* wiping
  `exports/` there, since that's where the CLI's own mandatory safety
  backup for the same reset just landed. Verified on all 3 reset paths
  (Admin, Publisher, CLI) and confirmed a real publish shows the real
  site title/URL flowing through, not the hardcoded fallback.
- **C-3**: `cms-manage.py asset delete` had an argparse `dest` mismatch —
  crashed on every invocation. Fixed, verified with a real add-then-delete
  round trip confirming both the DB record and the file on disk were
  actually removed.
- **C-2**: checked whether `db.commit()` exists on `CMSCore` (the audit
  worried every author/nav/social/ad save might 500) — it exists, it's a
  documented no-op, all 4 flagged routes tested live with no failures.
- **Tracker repair, properly this time**: Elton supplied the actual
  pristine pkg72.zip and pkg74.zip package snapshots. Cross-checked the
  pkg116 tracker repair against them and confirmed the full original
  narratives had genuinely survived intact — the real flaw was a lazy
  truncated-echo summary left in the third cell. Replaced with a proper
  distinct summary for both rows.
- Restructured `CHANGELOG.md` itself: merged two out-of-order pkg116
  sections into one, replaced the false "brought current" claim with a
  real pkg82–111 backfill drawn from actual tracker entries instead of
  just asserting it was done.

## pkg116 — Tracker integrity repair, security fixes, changelog genuinely backfilled

- Repaired 3 malformed rows in `.bejson_project.json`'s `Values` array found
  by external audit: two rows (pkg73/pkg74) had their fields misaligned —
  the literal string `"change_log"` sat in the change-log slot while the
  real narrative had been shifted into the change-notes slot — moved back
  into the correct position. One row (pkg106) was missing its third cell
  entirely, a genuine BEJSON positional-integrity violation; repaired by
  appending a cell that notes the claim in that row was later found false
  and corrected (pkg112), rather than deleting the history.
- This file was 34 packages stale (stopped at pkg81) — genuinely backfilled
  through pkg82–115 below, not just claimed current (an earlier version of
  this entry made that claim without actually doing it — caught by
  external audit; corrected here).
- Cross-checked the pkg73/pkg74 repair above against the actual pristine
  pkg72/pkg74 package snapshots (Elton supplied both): confirmed the full
  original narratives were genuinely recovered intact into the right cell,
  not lost — the real flaw was leaving the third cell as a lazy truncated
  echo instead of a proper distinct summary. Fixed.
- **Security (from a second external audit pass, same package)**: a real,
  exploitable path-traversal vulnerability in the asset/thumbnail serving
  routes (`Media.py`, `PageEditorV2.py`) — confirmed by actually attacking
  it (`/assets/../../../.bejson_project.json` returned this project's own
  tracker file contents with valid auth), not just read as a theoretical
  gap. Fixed using the project's own `bejson_safe_join()` path guard;
  re-ran the same attack afterward and confirmed a clean 404 with nothing
  leaked, plus confirmed legitimate asset serving still works.
- `cms-manage.py asset delete` had an argparse `dest` mismatch
  (`args.filename` vs. the actual `args.asset_filename`) — crashed on
  every invocation. Fixed and live-tested: added a real asset, deleted it
  via the CLI, confirmed both the DB record and the file on disk were
  actually removed.
- Checked `db.commit()`, flagged by the audit as possibly undocumented/
  missing on `CMSCore` (would mean every author/nav/social/ad save 500s):
  confirmed it exists as a documented no-op, and live-tested all 4 routes
  the audit named — none failed. Correctly flagged by the auditor as
  unverifiable from a static chunk review; resolved as a non-issue by
  actually running it.
- **Publisher output bug**: every published page was rendering a
  duplicated title and a nested `<article>` inside `<article>` — the page
  renderers were built as full-article emitters but used as body-only
  fragments by the skeleton template, which already provides its own
  wrapper and title. Fixed all 3 renderers to return body-only fragments;
  verified by actually publishing a page and confirming exactly one
  `<article>` tag and one title in the output.
- **Standalone apps**: entry-file and featured-image form fields were
  silently discarded on create and reset to defaults on every edit, in
  three separate call sites (`app_new`, `app_edit`, `serve_app`) — a form
  field named `app_entry_file`/`app_featured_img` was being read back
  under the old pre-migration names. Fixed all three; verified with a full
  create → edit → serve round trip using a real non-default entry file and
  a real image.
- **Multi-file-code editor template**: dead on arrival — missing
  `import zipfile` meant the "Generate ZIP download" feature (checked by
  default) always failed. Fixed; verified by actually generating a ZIP and
  reading its contents back.
- **Zip-slip path traversal**: app-bundle upload (both create and edit)
  and the CLI's `restore` command extracted uploaded ZIPs with no
  path-traversal guard — a crafted archive could write outside the
  intended destination. Added a shared `safe_extract_zip()` helper to
  `lib_bejson_Core_bejson_path_guard.py` that validates every member
  before extracting anything (atomic rejection, not partial extraction),
  wired into all 3 call sites. Verified by actually building a malicious
  ZIP with a `../../../` member and confirming it's rejected at the full
  HTTP-route level with nothing written outside the project tree, then
  confirming a legitimate nested-directory ZIP still extracts correctly.
- **Publisher factory reset**: was structurally broken — wiped the live
  database but never re-initialized it (recovery only happened by
  accident, whenever the Admin app was next launched), referenced a
  `BEJSON_Manager.py` file that doesn't exist in the project, and didn't
  clear `storage/tmp/html_imports` the way the Admin-side reset already
  did. Fixed to match Admin's reset exactly: re-bootstraps the database,
  clears the same targets, corrected the success message. Verified live:
  confirmed a leftover file was actually wiped and the database was
  actually rebuilt (not just empty folders) after reset.
- Also fixed in this pass: a CLI command writing a timestamp under the
  wrong field name (`page_created_at` instead of `extmedia_created_at`),
  a Cloudflare project-name fallback silently broken by positional dict
  access instead of the mandated Field Map Cache, a dead fallback
  referencing retired field names, and a CLI asset-add command that never
  synced the manifest record count after registering a new asset.
- **Explicitly not fixed, flagged instead of guessed at**: the dead AI
  Multi-Page Builder in PageEditor V1 references a `CMSAIBuilder` class
  that doesn't exist anywhere in this codebase under any name — that's a
  "build the real feature or remove the UI" decision, not a bug fix, so
  it's flagged for Elton rather than resolved unilaterally. Same for
  Publisher dating every standalone app as "today" — `StandaloneApp` has
  no creation-date field in the canonical schema; adding one is itself a
  schema change.

## pkg112–115 — Taxonomy remediation, external-audit fix rounds, PDF/YouTube insert parity

- **pkg112**: discovered and reported (not papered over) that prior docs had
  falsely claimed a full taxonomy field-name migration was verified. Found
  and fixed real live-data-reading bugs across `System`/`Content`/
  `PageEditor` V1/`PageEditorV2`/`Publisher` — broken site config, ads,
  nav, social links, sitemap category URLs, app permalinks, and media
  pickers were all silently reading pre-migration field names. Deleted 3
  contradictory stale planning docs, replaced with
  `docs/taxonomy_remediation_plan.md`. Also reported an undocumented
  pkg108→111 version-number jump with unrecoverable provenance rather than
  guessing at it.
- **pkg113**: external-audit follow-up. Verified the audit's own claims
  against the live sandbox first (several were false — `src/lib/` was
  actually present, several "missing" docs actually existed). Fixed 13
  confirmed real bugs (a missing `import random` causing a crash on any
  active ad, an edit-page form silently discarding image/author/category
  changes on every save, a completely broken external-media add flow, a
  JS syntax error that killed an entire inline `<script>` block, a
  triple-redundant DB init sequence, an unlocked manifest-sync race). Added
  HTTP Basic Auth to the 4 standalone apps that had none — most
  importantly the one with the database-wiping factory-reset route.
- **pkg114**: self-audit of the pkg113 work at Elton's request — re-ran
  every fix as a real standalone subprocess with genuine HTTP requests,
  not just the test client. Found and fixed 3 small things pkg113 itself
  left behind, plus one bigger stale-status issue: `cms-manage.py`'s own
  `status` command and a supporting doc were still describing a pkg80
  intermediate state that pkg81 had already resolved.
- **pkg115**: feature request — PDF and (follow-up) YouTube video links
  should insert into a page like an image, not force manual URL entry.
  Two of the three page editors already had this working correctly once
  the pkg113 field-name fixes landed; the actual gap was the main Content
  editor having no PDF/YouTube picker at all. Added parity across all
  three editors, verified live with real uploaded PDFs and saved video
  links, including executing the actual served JS under Node against a
  mocked DOM to confirm correct embed HTML.

## pkg82–111 — Blueprint split hardening, CLI data-layer reconnection, taxonomy migration start (backfilled pkg116)

Real summary drawn from `.bejson_project.json`'s own per-package entries for
this range, replacing the false "brought current" claim an earlier version
of this file made without actually doing the work. Package-number-to-entry
mapping beyond what's explicitly stated below is approximate — the tracker
rows for this range don't all carry an explicit `pkgNN:` prefix the way
pkg107+ entries do.

- **Editor V2 stabilization**: fixed a sidebar/toolbar total-breakage
  regression; added `advanced_launcher.py` and
  `lib_bejson_CMS_cms_ports.py` (config.json-backed port resolution,
  replacing hardcoded ports across all 5 apps).
- **CLI reconnection (pkg78–81 range)**: `cms-manage.py` was found
  completely disconnected from the live site's data — commands wrote to an
  orphaned workspace the running Flask apps never read. Full report in
  `docs/CLI_Data_Layer_Disconnect_Report.md`, then systematic conversion of
  every entity command to the real `CMSCore` data layer, live-verified with
  a cross-system test (a category added via CLI appearing in the running
  Admin UI — the first time CLI and site shared data in this project's
  history).
- **`asset optimize`** implemented (live PNG→WebP conversion with
  `pages_db` reference patching) and `page import --app` (embed a
  StandaloneApp as a real page).
- **Naming Taxonomy migration, Phases 1–5**: the field-name migration this
  project has referenced ever since — `category_name`→`cat_name`,
  `auth_name`→`author_display_name`, `config_key`→`sys_key`, and the rest
  of the prefix-based rename across every entity. Phases 1–4 (planning
  through live data migration) completed and verified in this range; the
  Phase 5 "blueprint refactoring complete" claim made at the end of this
  range was **later found false** (pkg112) — several blueprints were still
  reading pre-migration field names months after this claim shipped. See
  pkg112 above for the correction and pkg116's audit-fix round above for
  the last of the stragglers found.

## pkg81 — CLI data-layer disconnect: remediation completed

- Converted the remaining `cms-manage.py` entities to `CMSCore` against the
  real live manifest: `author` (rekeyed to name, matching the live
  `AuthorProfile` schema — it has no UUID field), `ad`, `app`, `asset`
  (+ `add-external`/`delete-external`/`list-external`), and `page`.
- `page` now implements the real two-part write contract: a `PageRecord`
  row plus a standalone `pages_db/<uuid>.json` content file, written
  atomically and read/updated via Field Map Cache lookups — no positional
  indexing — matching `BEJSON_CMS_Content.py` exactly.
- `backup`/`restore` rebuilt as real live-data zip export/import
  (`storage/mfdb/{site_master,pages_db,assets,standalone_apps}`), with an
  automatic safety backup taken before any restore.
- `mount`/`commit` deprecated with explicit messaging; `factory-reset`
  message fixed to state plainly it doesn't touch live data.
- `db list` rebuilt against a `CMSCore` entity map.
- Deliberately left unconverted (flagged in their own error messages, not
  guessed at): `page import --app`, `asset optimize`.
- Verified against real live data throughout: full CRUD cycles for every
  converted entity, a live cross-system check (CLI-added author confirmed
  rendering on the real `/site/authors` route in the booted Admin app,
  HTTP Basic Auth), and a real restore-recovery test run in an isolated
  copy of `storage/` so live data was never at risk. Full `py_compile`
  sweep across the project: clean. See `docs/security-notes.md` for the
  complete verification narrative.

## pkg80 — CLI data-layer disconnect: full report + remediation started

- Added `docs/CLI_Data_Layer_Disconnect_Report.md` — full investigation of
  the `cms-manage.py` disconnect first flagged pkg78. Found it's not just a
  storage-path mismatch: `MFDB_CMS_Manager`'s schemas for Category,
  AuthorProfile, NavLink, SiteConfig, and the Page/PageContent storage model
  all diverge from the live schema (field count, field names, and/or key
  strategy — AuthorProfile especially, UUID-keyed vs. the live entity's
  name-keyed shape with no UUID field at all).
- Remediation started: `cms-manage.py`'s `status`, `category`, `navlink`,
  and `config` commands now use `CMSCore` directly against the real live
  manifest instead of the disconnected workspace. Verified with a real
  cross-system test — a category added via the CLI appeared in the live,
  running Admin web UI, the first time in this project's history the CLI
  and the site have shared data.
- `author`, `page`, `asset`, `app`, `ad`, `backup`, `restore`, `mount`,
  `commit` are unchanged — still on the old disconnected manager — pending
  the design decisions the report lays out (see its §5).

## pkg79 — Library sync (11 files) + new security-notes.md

- Replaced 16 files under `src/lib/` with the current versions from Elton's
  general library package (`libraries.zip`): 11 actually changed content
  (`lib_bejson_CMS_cms_core.py`, `lib_bejson_CMS_cms_mfdb.py`,
  `lib_bejson_Core_mfdb_core.py`, `lib_mfdb_chunker_v6.py`,
  `bejson_server.py` + its `cli/` duplicate, `cli/book_builder.py`,
  `cli/build_ebook.py`, `cli/gemini_showcase_intro.py`,
  `cli/showcase/showcase_master.py`), 5 were already identical. Notably
  fixes a real data-loss bug in `lib_bejson_CMS_cms_mfdb.py`'s
  `mount_system()` (v2.1.5 → v2.1.6) — see `.bejson_project.json` for the
  reproduction. 3 files have no counterpart in the library package and were
  deliberately left untouched: `lib_bejson_Core_bejson_path_guard.py`
  (security-critical, no replacement shipped), `lib_bejson_CMS_cms_ports.py`
  (added this project pkg75/76, not part of the general library family),
  `lib_cms_persona_writer.py` (project-specific).
- Added `docs/security-notes.md`, documenting the `cms-manage.py` /
  `MFDB_CMS_Manager` disconnected-data-layer finding from pkg78 (verified:
  the CLI's `category list` after `mount` shows only the bootstrap default,
  while the real live site has an additional real category and pages that
  are invisible to it). Flagged, not fixed — it's a structural decision, not
  a library-swap-fixable bug, and the pkg79 library sync confirmed it's
  still present in the updated library too.
- Checked every doc file in the project for staleness (>1 week old, per
  request) — none qualified; everything is dated one day prior to this pass
  from the earlier factory-reset regeneration. Nothing removed on that basis.

## [Unreleased] — Repo audit (this pass)

- Factory-reset audit: removed 5 orphaned `pages_db/*.json` content files
  with no matching `PageRecord`, a stray duplicate `assets/thumbs/` folder
  (the live one is `assets/_thumbs/`), 2 orphaned `standalone_apps/<uuid>/`
  bundle directories with no matching `StandaloneApp` record, and stale
  `storage/tmp/html_imports/*.html` / `storage/tmp/logs/*.log` artifacts.
  Full detail in `docs/cleanup-log.md`.
- Regenerated the full standard documentation set (this file, `README.md`,
  `AGENTS.md`, `docs/architecture.md`, `docs/usage-guide.md`, `LICENSE`,
  `.gitignore`, `CONTRIBUTING.md`, `SECURITY.md`) from the live, audited
  codebase — old ad-hoc docs (bugfix notes, purge records, variable
  reference, full-scope analysis report) were superseded and removed; their
  substance is preserved in `.bejson_project.json`'s own detailed history.
- Rewrote the four BEJSON-format beginner's-guide pages (`understanding-
  bejson-104`, `-104a`, `-104db`, `understanding-mfdb`) under the BEJSON
  category with expanded, illustrated, human-readable content, replacing the
  prior book-style pages (which embedded large base64 cover images inline).
- Republished the static site to `storage/builds/`.

## pkg1 – pkg72 (2026-07-04 → 2026-08-05) — summary

- **Foundational fixes**: mobile container padding, global font scale,
  metadata/version corrections.
- **Documentation passes**: technical notes, readability review, a full
  19-page scope-and-quality report, a corrected remediation checklist with
  re-verified real numbers.
- **Three purge phases**: removed unused lib files, duplicate template/style
  directories, stray root files — all verified zero-reference before
  deletion.
- **Library naming standard deployment**: 13 (later 14) files migrated to
  `lib_bejson_<Family>_<name>.py`, 41+ import sites rewritten, old flat names
  deleted, full test suite added (21 pytest cases).
- **Category self-heal + Media Library**: fixed a category-edit gap, root-
  caused and fixed a real import/upload freeze (fsync batching → per-manifest
  `RLock` → thumbnail decode timeout → eventual full from-scratch low-memory
  rebuild after confirming the true root cause was device-specific memory
  management, resolved by moving to Termux with a wakelock).
- **Blueprint split**: `Flask_CMS.py` (3,566 lines) split into System /
  Content / Media / Interface Blueprints plus a shared substrate module;
  all five web apps renamed to the `BEJSON_CMS_*` convention.
- **Security sweep**: found and closed a real auth gap (~48 of ~50 admin
  routes had zero auth enforcement) with a single global `before_request`
  hook.
- **AI Persona Hub**: registered the missing `AI_Profile` entity, expanded it
  from 8 to 25 fields, wired both page editors' AI generation to actually use
  personas, then explicitly decoupled the internal AI persona description
  from the public author bio so AI-flavored text can never leak onto the
  live site.
- **UX passes**: author fields converted to real comboboxes everywhere,
  page duplication added, Media Library redesigned as a collapsible list
  with bulk actions and a lightbox, inline image upload from the page-edit
  screen.
- **Variable naming remediation**: 45 cited single-letter/ambiguous locals
  renamed to self-describing names across `src/web/`, scoped strictly to
  files outside `src/lib/` per Library Immutability.

See `.bejson_project.json` → `Values` for the complete, dated, per-file
entry for every item above, including exact verification steps taken.
