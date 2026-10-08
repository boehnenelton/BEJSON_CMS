# Changelog

Full, unabridged change history (every verification step, every file touched)
lives in `.bejson_project.json` at the project root — this file is a
readable summary. Newest at top, oldest at bottom.

## pkg143 — Library sync against CLI_AI-V16-PKG30

Scanned every file in the newest CLI_AI zip (nested archives included) against the CMS's `src/lib`. Two real updates: the validator (2.1.0 → 2.2.1, a corrective release) and `source_env()` in the env library (adds JSON secure-env loading, no `exec` for `.json`). Left alone on purpose: `path_guard`, where the CMS is *ahead* of the zip and overwriting would break zip-extraction safety. The rest were identical or not successors. The decisions are tabled in `docs/architecture.md`.

## pkg142 — Python CMS generation ported from the React CMS's architecture

The React CMS's server-side Gemini proxy was ahead of the Python CMS: it
falls back across models on a 429/503, trims oversized prompts before
sending, and reports a retry delay. The Python CMS's `/api/tasking/*`
routes did one raw request with no retry at all. Ported the React design
into `PersonaWriter.generate_with_fallback()` and pointed both routes at
it. Adapted rather than copied where the architectures differ — the React
version rotates keys client-side and models server-side; here both happen
in the one Flask process.

Caught one regression of my own before shipping: the first draft made
`requests` a hard import, which would have stopped the whole page editor
from starting anywhere `requests` isn't installed. Fixed.

Tested against a mocked HTTP layer only — not against real Gemini.

## pkg141 — Path traversal in PageEditorV2's context-file upload

Continued the sweep instinct from pkg139/140, this time into a different
bug class entirely: `/api/context/upload` used the raw client-supplied
filename to build a save path, which werkzeug doesn't sanitize on its
own — a crafted filename could write outside the intended directory.
Confirmed the escape directly before fixing, fixed with the same
sanitization/safe-join pattern already used elsewhere in the same file,
then swept every other upload site in the codebase for the same pattern.
This was the only instance.

## pkg140 — Closing the remaining SVG gaps pkg139 missed

Kept auditing the SVG sanitization work right after shipping it instead
of treating it as done. Found three more places the same attack class
could slip through: the thumbnail fallback route (which is the *only*
route an SVG's raw bytes are ever served through, since SVGs never get
thumbnailed), the asset-replace endpoint (a second write path that never
sanitized at all), and a second Flask app with its own duplicate copies
of both serving routes. All three fixed the same way as the original fix
and verified with a real malicious payload run through each path.

## pkg139 — The three deferred judgment calls, decided

Elton decided the three items pkg138 flagged as needing an opinion, not a
unilateral fix.

**SVG uploads:** build a sanitizer, re-enable. New stdlib-only sanitizer
(`lib_bejson_Core_svg_sanitizer.py`) — strict allowlist, everything not
explicitly known-safe gets dropped rather than selectively filtered.
Tested against 13 real attack payloads (including an actual XXE check,
not an assumed one) before it ever touched the upload path, then verified
end to end through the real upload route: a malicious file comes out the
other side completely inert, a broken one gets rejected outright. Added a
CSP header on served SVGs as a second layer on top of that.

**`mount`/`commit`/`repack`:** removed entirely. They were deprecated
escape hatches into an old disconnected data model, long superseded by
`backup`/`restore`. The read-only diagnostic in `status` that reports on
that legacy layer stays, in case anything outside this CLI still touches
it directly.

**`app_created_at`:** added. App cards were showing the site's build date
instead of when the app was actually created, because the field never
existed. Existing apps get backfilled with a single shared timestamp
(the date this field was added, since there's no real creation date to
recover) — new apps get their real date going forward.

## pkg138 — Deferred-item sweep

Went through every doc and source file for outstanding TODOs and
"pending Elton's call" markers. Most turned out to already be resolved —
just stale documentation, corrected. Two real bugs fixed: the admin app's
`<title>` tag was dead Jinja syntax that never actually changed per page,
and a logging handler could duplicate itself on a module reload. Also
moved two imports out of Publisher's per-page loop where they were
needlessly re-executed on every iteration.

Four genuine judgment calls surfaced along the way — not fixed, presented
separately since they're product decisions, not bugs: SVG upload
sanitization (currently just disabled), whether to keep the deprecated
`mount`/`commit` CLI commands, three unused template files that might be
forward-looking scaffolding, and a missing `app_created_at` field.

## pkg137 — CLI additions (find/export/import/merge) + PageRecord FK identity

Two pieces, following up on pkg136's proposal list and "keep making
everything uuid based."

Built the 3 remaining CLI ideas: `find` (fuzzy name→UUID lookup across
every entity type), `export`/`import` (JSON/CSV round-trip, always
generates fresh UUIDs on import and skips duplicates rather than creating
them), and `category merge`. The proposed `--json` flag was dropped —
every `list` command already outputs JSON.

Then extended pkg135's UUID work into the one thing it deliberately left
alone: `PageRecord.page_cat_name`/`page_author_name`. Added
`page_cat_uuid`/`page_author_uuid`, kept in sync automatically across
every place a page gets created or edited, in every app and the CLI. This
is additive, not a rewrite — every existing render and permalink path
still reads the name fields exactly as before. A page now carries a real,
stable identity link to its category and author, immune to the
rename/collision class of bug, without touching how the site actually
renders. Found and fixed a real leftover schema inconsistency from pkg135
along the way.

Every piece verified live against real data with cleanup after — not
mocked, not just compiled.

## pkg136 — Advanced CLI streamlining: rename commands + doctor

Following pkg135's UUID work, added `cms-manage.py author rename` and
`category rename` — the latter also fixed a real pre-existing bug found
while building it: `category update` changed the category's display name
but never touched the pages already in it, silently orphaning them.
Both new commands cascade the rename everywhere it's referenced and
refuse collisions. `category rename` also won't let you rename away from
"Uncategorized" — doing so would fight the system's own self-heal logic.

Also added `doctor`, a health-check command: orphaned category/author
references on pages, and case-insensitive duplicate names across every
entity that identifies itself by name. Exits non-zero if it finds
anything, so it's usable in a script.

Every piece verified live against real data — add→rename→cascade→cleanup,
and `doctor` was fed real orphans and real duplicates on purpose to
confirm it actually catches them, not just that it runs.

## pkg135 — "Give them all UUIDs": Category, AuthorProfile, MediaAsset, NavLink, SiteConfig, SocialLink, AI_Profile

Resolved the open architectural question flagged since pkg119: these 7
entities were name-keyed with no UUID. Elton's call — inject one into all
of them. Ran the already-prepared `tools/migrate_taxonomy.py` live for the
first time (after a real backup), which surfaced and fixed a genuine bug
in the tool itself (it wrote two custom keys the project's own strict
validator forbids). Converted every CRUD path across the web apps and the
CLI to use the new UUIDs for add/edit/delete identity, and along the way
found a whole class of latent bug: several `add_record()` calls weren't
including the new field at all, which would have written `None` as the
"unique" ID — the exact problem UUIDs exist to prevent. All fixed;
confirmed live with a full sweep (0 of 11 real rows have a missing UUID).

Deliberately not touched: `PageRecord`'s name-based category/author FKs
(a separate, much larger decision), and `MediaAsset`'s filename-based
rename/delete (its filename was already a stable, collision-free ID).

Everything in this entry was verified against real, live project data —
add→edit→delete round-trips via actual Flask test clients and the real
CLI, not mocks — and the full 39-case test suite passed throughout.

## pkg134 — CLI/web disconnect on AuthorProfile duplicate-checking

AuthorProfile has no UUID field — `author_display_name` is the primary key
everywhere, so nothing catches two rows that differ only by case unless
every write path checks for that itself. Both web paths (`manage_authors()`
in the Content Cube, and Persona Hub's persona→author sync) already
compared names case-insensitively before adding; `cms-manage.py`'s
`author add` compared them case-sensitively. Net effect: adding an author
from the CLI whose name differed only in case from an existing web-created
author silently created a second, disconnected row instead of being
rejected as a duplicate.

Made `cmd_author_add()` case-insensitive to match. Verified live against
the real (not synthetic) `authorprofile.bejson`: a case-variant re-add is
now correctly rejected, a genuinely new name still adds/deletes cleanly,
and live data was restored to its original state afterward. Full 39-case
test suite unaffected.

## pkg133 — Full audit remediation (external report against pkg132)

All HIGH and MEDIUM findings from the submitted audit fixed and verified;
LOW findings left as-is per the audit's own no-action/pending-decision
framing.

- **H-1** (manifest drift): `AI_Profile`'s manifest `primary_key` was still
  `"Name"` after the pkg132 field rename — the app code itself already
  declared `persona_name` correctly, only the manifest's live row was stale.
  One-cell fix in `104a.mfdb.bejson`.
- **H-2** (XSS, missed by 2 prior fix passes): two `copyAssetPath()` inline
  `onclick` sites in the Media Library (external-links table, YouTube cards)
  were still vulnerable to the same escaped-quote breakout bug already fixed
  elsewhere at pkg123/pkg124 — converted to `data-url` + the existing
  delegated click handler.
- **H-3** (stored XSS via SVG): removed `.svg` from the allowed upload
  extensions — no sanitizer exists, and asset serving does zero content
  inspection.
- **M-1 through M-5**: hardened two `KeyError`-risk direct dict indices in
  the Publisher to `.get()`, made an app-feed mapping's category exclusion
  explicit, resynced the embedded stylesheet fallback to byte-match the
  real shipped CSS, added `AI_Profile` to the migration tool's file map
  (already present in the audit tool's), and removed a dead duplicate
  `SiteConfig` key.

Verified via import smoke-tests on every touched module, a byte-diff
confirming the resynced CSS fallback matches the shipped files exactly,
and the full existing 39-case pytest suite (39/39, unchanged).

## pkg132 — AI_Profile schema migration: 25 fields renamed to match project taxonomy

`AI_Profile` was the one entity in this project still using PascalCase
"CrammedFieldNames" (`Name`, `SystemInstruction`, `EmotionalExpression_Enabled`...)
— deliberately, per a prior decision to stay compatible with an external
tool, `BEProfiler.py`. Confirmed with Elton that compatibility no longer
matters, then renamed all 25 fields to `persona_`-prefixed snake_case,
matching every other entity in this project.

- Every real field reference updated across `System.py` (both schema
  definitions), `BEJSON_CMS_ProfileManager.py` (found 3 references an
  initial pass missed due to template whitespace), `BEJSON_CMS_PageEditorV2.py`
  (3, not 2), and `lib_cms_persona_writer.py` (the actual prompt-assembly
  logic — the highest-stakes part of this migration).
- Live data migrated directly (0 rows existed, so purely a Fields-array
  rename, nothing to transform).
- `AI_Profile` added to the taxonomy registry and the audit tool's entity
  list — previously explicitly excluded as "out of scope."
- Verified with a full real create → edit → delete cycle through
  ProfileManager, plus direct testing of the persona-writer's prompt
  assembly against real (test) data.

## pkg131 — P1 test coverage + P2 items: last of the two-report audit's findings

- **P1**: pytest suite grew from 21 to 39 tests. New coverage: full
  `CMSCore` CRUD round-trip, the Admin app's global auth hook (tested
  across every registered blueprint, not just `/`), and a permanent
  regression test for the `app_delete()` incident earlier this session —
  proves the exact attack that once wiped real data now fails safely,
  without over-rejecting legitimate requests.
- **P2**: investigated both remaining items. The legacy-file warning
  mechanism is staying — it's not a packaging bug to fix, it's a real
  runtime safety net for something no packaging change can prevent (a new
  ZIP extracted on top of an old project directory on your own device).
  The Gemini key manager's stderr noise was real — fixed by capturing
  subprocess output instead of letting it leak to the console, while
  still surfacing it in the JSON error for genuine failures.

This closes out every item from both audit reports delivered this
session — several turned out to need real investigation rather than
blind fixes, and a few (ISSUES.txt, the "zombie" CLI commands, this
P0 factory-reset concern) turned out to already be resolved or never
true, matching a pattern that held throughout this whole remediation
pass: verify first, always.

## pkg130 — Both P0 audit items: stale claims, but real findings while checking

Neither of the first audit report's P0 items held up against real code —
same pattern as several other findings this session that turned out to
already be fixed or never actually true.

- **Factory reset**: the cited `ISSUES.txt` doesn't exist anymore (deleted
  at pkg120 after its real root cause was fixed). Verified the underlying
  concern live anyway — a real reset test with real non-default data
  confirmed everything genuinely gets wiped. Found a real gap while
  checking: `MediaAsset`/`ExternalMedia` only existed in the migration
  path, not in the fresh-install bootstrap itself. Fixed and verified
  with an isolated test.
- **"Zombie" CLI commands**: both `page import --app` and `asset
  optimize` are already fully implemented, not broken placeholders.
  Found a real adjacent gap instead: `page import`'s own `add_record`
  calls were missing two fields already fixed everywhere else. Fixed.

## pkg129 — Remaining MEDIUM/LOW items from the two-report audit

All verified against real code first; several turned out larger than
reported (L-6 had 2 broken sites not 1, L-8 had 6 dead calls not 4, H-1
last round had 3 sites not 2 — checking rather than trusting report counts
keeps paying off).

- **M-2, M-3, M-5, L-7**: CLI page-type default fixed; duplicating a page
  no longer drops its featured video; import-flow hidden inputs and the
  category dropdown now properly escaped.
- **L-1, L-2**: all 4 page-creation paths (CLI, New Page, external Link,
  HTML import) now explicitly write the same complete field set.
- **L-3, L-4, L-5**: three more hardcoded stale values fixed (a launcher
  port, a dev-only PDF path, an editor footer) — all now resolve for
  real instead of being frozen at whatever they were when first written.
- **L-6**: 2 unescaped `alt` attributes in Publisher — verified with a
  real crafted page title through a real build, checking the actual
  generated HTML on disk.
- **L-8**: 6 dead no-op `db.commit()` calls removed after confirming
  `commit()` is a documented no-op in `CMSCore`.

## pkg128 — Two audit reports: real security fixes, plus a data-loss incident during testing

**Incident, disclosed in full:** while verifying an audit finding, a test
believed to be isolated (via a `CMS_DATA_ROOT` override) actually deleted
the real project's entire live `storage/mfdb/` directory — that env var
turns out not to be respected anywhere in the web layer, only by the CLI.
Caught and fully restored within the same turn from the already-delivered
`pkg127.zip`; verified byte-identical against the restored data. All
further destructive testing this pass used a full project copy in `/tmp`
instead.

- **M-4** (found via that incident): `app_delete()` had no validation on
  `app_uuid` — a single authenticated POST with `app_uuid=".."` recursively
  deletes the *entire* `mfdb/` tree, not just one app's folder. Far more
  severe than either audit rated it. Fixed with the same UUID validation
  `serve_app_static()` already used correctly; re-verified the exact same
  attack now fails safely.
- **H-1**: 3 picker onclick sites in `Content.py` (one more than either
  audit found) rebuilt as `data-*` + delegation.
- **H-2**: a gap in my own earlier delegation fix (the YouTube card
  thumbnail) — added to the existing selector.
- **H-3 + M-1**: `Shared.py`'s `insertYt()`/`insertPdf()` — shared by every
  editor's picker — now HTML-escape both label and URL before attribute
  interpolation, and `insertYt()` is now width-capped to match the
  pattern already used elsewhere.

## pkg127 — YouTube embed width capping + Featured Video (radio toggle)

- **Width capping**: both editors' YouTube insert functions now use the
  same capped, centered, rounded-corner style already established by the
  Multi-Video Page template (`max-width:800px`), instead of stretching to
  fill the full ~1100-1200px article container.
- **Featured Video**: new `page_featured_video_url` field on `PageRecord`
  (properly migrated for existing installs, not just new ones — caught
  that `PageRecord` wasn't even in the migration list before adding the
  field). New "Featured Video" section in Editor V2's page panel — a
  radio list of your saved YouTube links, collapsed by default. Actually
  renders on the published site (above the article body, same capped
  style), not just stored and forgotten. Full CLI support via
  `page add/update --featured-video`.
- Verified end-to-end with real data throughout: a real migration test, a
  real editor save/load round trip, a real Publisher build with the
  actual generated HTML inspected on disk, and all 4 CLI scenarios
  (add, update, clear, and "don't touch if the flag's omitted").

## pkg126 — Library sync (10 files, 2 with real functional changes)

- **`bejson_path_guard.py`**: real security fix — a sibling-directory
  path-traversal bypass in `bejson_safe_join()`. The upstream version had
  dropped `safe_extract_zip()`, which this project has 4 real dependents
  on; merged rather than overwrote, so the fix landed without losing
  anything. Verified with 4 live tests.
- **`bejson_validator.py`**: field-type validation now actually rejects
  non-canonical types instead of silently ignoring them. Checked every
  live schema in this project first — nothing would have broken either
  way, but confirmed before adopting.
- 8 other files: single added `Release_Version: 300` header line each
  (one also got the real code constant) — policy-compliance only, no
  functional change.
- Full verification: all 5 apps booted live, a real CRUD cycle through
  the CLI, a real Publisher build, all clean.

## pkg125 — Fifth external audit: schema-migration gap, atomic writes, dead ports, real fixes throughout

- **M-1**: `PageVideoMetadata`/`PageDocumentMetadata` were missing from
  `_migrate_db()` — a database bootstrapped before these entities existed
  would never gain them without a full factory reset. Fixed and proved with
  a real migration test against a simulated old database.
- **M-3**: Cloudflare publish fallback read a `SiteConfig` key that only
  exists after someone manually resaves the config form once. Switched to
  the key that's always present from first boot.
- **M-4**: two page-content-file writes weren't atomic. Fixed both to match
  the CLI's already-correct temp+`os.replace` pattern.
- **M-5**: a missing `requests` package would crash two AI-task routes with
  a raw 500 instead of a useful error. Fixed with a module-level
  availability check.
- **M-6**: three hardcoded `localhost:5001` links, despite working port
  resolution sitting right next to them in the same files. Fixed all three
  — proved it wasn't cosmetic by overriding the real port env vars and
  confirming the rendered links actually changed.
- **M-7**: brand-asset MIME detection would mis-tag any future `.png` as
  `image/jpeg`. Fixed with real MIME detection, verified with a real PNG.
- **L-3, L-4**: removed a dead field fallback; fixed a real color-palette
  policy violation (ProfileManager was using Twitter blue, not the
  mandated `#DE2626`).
- **L-2** (partial, prioritized by real impact): fixed two startup banners
  that had a stale hardcoded port literally two lines above the correct
  one, and fixed the live Publish page's user-facing text, which told
  users to run a file that hasn't existed since the Flask conversion.
- **M-2** confirmed real but left as an open design decision (adding a
  field to a live schema); **L-1** left alone pending your call on whether
  those templates are planned or dead.

## pkg124 — Media Library: dedicated YouTube tab + audit H-1 fixed

- **Feature**: Media Library now has a third tab, "YouTube" — a thumbnail
  grid (real YouTube thumbnails) with its own Add form, separated out from
  the generic Links table. YouTube embedding itself already worked
  (Editor V2's picker); this gives it a clear home instead of being
  buried in a mixed links list. No schema change — existing links show up
  automatically.
- **H-1 (fifth external audit)**: the same class of bug fixed in pkg123
  #7 (raw names in inline `onclick` JS, breakable via HTML-entity
  decoding) was still present in 3 spots in the Media Library — plus a
  4th I introduced myself while building the new tab, copied from the
  vulnerable pattern without noticing. All 4 fixed with `data-*` attributes
  + delegated `addEventListener`. Caught a real regression before shipping:
  the fix needed the event-capture phase, not the default bubble phase, to
  preserve an existing "don't also toggle the row" behavior.

## pkg123 — Fourth external audit: real category-save bug, XSS-adjacent escaping, dead link/code

- **HIGH**: PageEditorV2's Save button was reading the category *filter*
  dropdown (default `"all"`) instead of an actual category field — every
  page saved via V2 while unfiltered got an unresolvable category
  reference. Added a real, separate Category field to the edit panel.
- **MED**: import-queue data embedded raw into a `<script>` block —
  a page title containing `</script>` could break the import UI. Fixed
  with the standard escape.
- **LOW × 4**: dead `/v2` link (now resolves a real cross-service URL via
  the existing ports library), unescaped external-media URL in
  `href`/`onclick`, one genuinely dead variable removed, and author names
  interpolated raw into inline `onclick` handlers — verified exploitable
  live with a real `O'Brien` test author, fixed by moving to `data-`
  attributes read via `.dataset` instead of string-building JS source.
- Confirmed real but deferred (low impact): CLI's non-chunked file hashing,
  untracked ZIP exports, static page `<title>`.

## pkg122 — CLI: `config` now has full CRUD

Added `config delete <key>` — the one gap flagged in pkg121's
verification pass. Confirmed first that no live app code depends on
specific `SiteConfig` keys always existing (`Publisher.py` reads them all
via `.get(key, default)`, never direct indexing), so unrestricted deletion
is safe. Tested a full set → list → delete → list cycle against real live
data; real bootstrap config keys confirmed untouched throughout.
`cms-manage.py` bumped 18.6 → 18.7.

## pkg121 — Full CLI functionality verification (requested directly)

Reviewed `src/cms-manage.py` (v18.5 → v18.6) field-by-field against the
live taxonomy schema — all data writes are in sync. Found and fixed one
real bug this pass surfaced:

- **`page add`/`page import --category` defaulted to `'uncategorized'`**
  (lowercase) but `page_cat_name` stores the category's real NAME
  (`'Uncategorized'`, capitalized) — confirmed live: any page created via
  the CLI without an explicit `--category` got a category reference that
  resolved to nothing at publish time, breaking that page's category
  listing and breadcrumb. Fixed the default; reproduced the bug live
  before the fix and confirmed it was gone after, including a full
  Publisher build with the affected page present.
- Corrected 8 instances of stale argparse help text (said "Category slug"
  / "Author UUID" throughout — the live schema actually needs the
  category's and author's NAME; AuthorProfile has no UUID field at all).
- Flagged, not fixed: `config` has no `delete` subcommand, unlike every
  other entity.

Full functional pass beyond the bug fix: real CRUD cycles against live
data for every entity (author, category, navlink, ad, asset,
external-media, app, page — including both `import --html` and
`import --app`), a real PNG→WebP `asset optimize` conversion, a real
`backup`, and a `restore` tested in an isolated copy so live data was
never at risk.

## pkg120 — Third external audit, Phase 3: real orphan-picker fix (2 independent copies), ISSUES.txt resolved for real

- **H-1**: fixed all 4 callers the report named (app_new, app_edit,
  manage_authors, manage_ads) — replaced raw `os.listdir()` pickers with
  real `MediaAsset` DB reads via a new `get_image_assets()`. Also found and
  fixed a **second, independent copy of the same bug the report never
  named**: `PageEditor.py` had its own separate, even-less-precise
  `_get_assets()`. Verified with a real orphan file copied straight onto
  disk (not registered in the DB) — confirmed it disappeared from every
  picker after the fix, while real assets stayed visible. Old dead
  functions removed, logged in `docs/dead_code.md`.
- **H-2**: already resolved as a side effect of pkg119's AI-builder removal
  — the file-based half of the "two disconnected AI profile systems" no
  longer exists. No code change needed; confirmed via grep.
- **L-4**: `ISSUES.txt` (deferred in pkg118) removed — re-read its content
  this pass and confirmed it describes exactly the orphan-picker bug just
  fixed. Deferring it until the real fix landed, instead of deleting it
  alongside a report that only claimed the fix, was the right call.

## pkg119 — Third external audit, Phase 2: taxonomy doc correction + dead AI builder removed

- **C-1**: `docs/taxonomy_remediation_plan.md`'s own "ground truth" table
  was independently wrong in the same way as `taxonomy_audit.json` — both
  claimed 6 entities (Category, AuthorProfile, MediaAsset, NavLink,
  SiteConfig, SocialLink) have UUID fields that don't exist live. Corrected
  the doc, re-ran `tools/audit_taxonomy.py` to regenerate an accurate audit
  file. Whether to actually inject those 6 UUIDs is left as an open
  decision — flagged, not resolved. MediaAsset is the one worth deciding
  deliberately given the video/document page-type idea discussed.
- **C-2**: removed the AI Multi-Page Builder entirely (sidebar link, modal,
  all JS, all 6 routes, every supporting helper/constant) rather than
  building the missing `CMSAIBuilder` integration — that's a separately-
  scoped feature build, not a remediation fix. Logged in the new
  `docs/dead_code.md`.

## pkg118 — Third external audit, Phase 1: secrets, imports, ZIP guard, packaging hygiene

A fresh third-party audit report was submitted and independently verified
against real live files before anything was fixed (its severity IDs — C-1,
C-2, C-3, H-1 — are a new numbering, unrelated to pkg117's own C-2/C-3/H-1
labels above). See `.bejson_project.json` for the full verification
narrative.

- **Secrets**: replaced hardcoded Flask `secret_key` values in
  `PageEditor.py`, `ProfileManager.py`, and `PageEditorV2.py` with the same
  random-key pattern `Admin.py` already used correctly.
- **Dead imports**: removed a redundant `import uuid as _uuid_mod` alias
  and 5 redundant nested `import json` calls in `Content.py`, a duplicate
  `import sys` in `PageEditor.py`, and a duplicate local `import random` in
  `Publisher.py`.
- **Security**: added the existing 300MB uncompressed-size guard (already
  used in `app_new()`/`app_edit()`) to `/api/apps/scan_zip`, which was
  missing it.
- **Packaging**: `config.json` (a runtime artifact, auto-created on first
  read) removed from the package; added `.gitignore`.
- Confirmed but deliberately **not yet acted on**: taxonomy UUID mismatch
  (worse than reported — `taxonomy_audit.json` actively asserts UUIDs exist
  on 6 entities that don't) and the dead `ExtLib.CMSAIBuilder` AI builder —
  both need a design decision, not a mechanical fix. Also confirmed but
  deliberately not deleted: `ISSUES.txt` — its symptoms overlap with the
  still-open `get_assets()` raw-listing issue; removing the bug report
  before the real fix would misrepresent it as resolved.

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
