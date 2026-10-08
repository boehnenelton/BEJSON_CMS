# Security & Architecture Notes

Findings that don't belong in `architecture.md` (which describes intended
design) — bugs and structural gaps discovered during real testing, per
System Development Policy §1.2. Each entry states how it was verified, not
assumed.

---

## `BEJSON_CMS_PageEditorV2.py` — `/api/context/upload` path traversal via unsanitized filename (found + fixed pkg141)

**Severity:** Medium — arbitrary file write. `file.filename` is
client-controlled (the multipart `Content-Disposition` header), and
werkzeug's `FileStorage.save()` does not sanitize it before joining it
onto a directory path. Gated behind the same Basic Auth every route in
this app enforces (`_enforce_auth_everywhere`), so not exploitable
unauthenticated — but an authenticated user of the CMS shouldn't be able
to write files outside the intended `Context/` directory via a crafted
filename, and if any other bug ever exposes this route to a
lower-privilege caller, this becomes a much bigger problem.

**Confirmed directly, not assumed:** `os.path.join(CONTEXT_DIR,
"../../../../tmp/x")` resolves clean outside `CONTEXT_DIR` entirely —
checked with `os.path.abspath()` before writing any fix.

**Fix:** `secure_filename()` (werkzeug) plus `bejson_safe_join()` — the
same path guard this file already uses for its `/assets/` routes — as a
second layer rather than trusting `secure_filename()` alone.

**Verified:** sent the exact traversal filename that escaped before the
fix through the real Flask route; confirmed nothing was written at the
traversal target and the upload landed safely inside `CONTEXT_DIR` under
a collapsed-safe name instead. Confirmed a legitimate upload is
unaffected. Then swept every other `file.filename`/upload site in the
codebase (`BEJSON_CMS_Media.py`, `BEJSON_CMS_Content.py`,
`BEJSON_CMS_PageEditor.py`) for the same pattern — all already either use
`secure_filename()`, write to a fixed non-user-controlled path, or never
write the upload to disk at all (read into memory only). This was the
only real instance.

---

## `src/cms-manage.py` operates on data completely disconnected from the live site (found pkg78, unresolved)

**Severity:** High — every data command in this CLI silently succeeds
against the wrong dataset instead of erroring, which is worse than a crash.

**What's wrong:** `cms-manage.py` uses `MFDB_CMS_Manager`
(`lib_bejson_CMS_cms_mfdb.py`), a *different* data-access layer than the one
all 6 Flask apps use (`CMSCore`, `lib_bejson_CMS_cms_core.py`). The manager
reads/writes `storage/workspace/db_global/` and `storage/workspace/db_content/`,
populated only by extracting `global_master.mfdb.zip` /
`content_master.mfdb.zip` via `mount_system()`. Neither archive exists
anywhere in this project. `mount_system()` does not error when they're
missing — it silently bootstraps a brand-new **empty** workspace instead.
Asset storage paths don't overlap either: the manager uses `storage/assets/`,
the live Flask apps use `storage/mfdb/assets/`.

**How this was verified (not assumed):** ran `python3 cms-manage.py mount`,
then `python3 cms-manage.py category list` — returned only the bootstrap
default `["Uncategorized"]`. Queried the actual live site at the same moment
via `CMSCore` (what all 6 Flask apps really serve) — returned
`["Uncategorized", "BEJSON"]`. The `BEJSON` category, and every page under
it, is invisible to the CLI. Confirmed via `find` that no `.zip` archive
exists anywhere under the project root.

**Why it wasn't fixed as part of the pkg78 CLI update:** fixing individual
CLI commands (the actual scope of that change — see `.bejson_project.json`
pkg78 entry) doesn't touch this; it's a structural decision about which data
layer `cms-manage.py` should use at all — bridge the two, point the manager
at the live paths directly, or deprecate the archive/workspace model
entirely. That's Elton's call, not something to silently redesign as a side
effect of an unrelated change (Zero Guessing / Permission Rule, policy §2.1).

**Status:** flagged, not fixed. Re-checked after the pkg78 library update
(`lib_bejson_CMS_cms_mfdb.py` v2.1.5 → v2.1.6) — that update fixes a real
data-loss bug in `mount_system()`'s lock-file handling (see
`.bejson_project.json` pkg78 changelog entry for the reproduction and fix
detail) but does **not** touch the workspace-vs-live-data path structure.
The disconnect described above is still present in v2.1.6.

**Update, pkg80:** investigated further and found the disconnect is worse
than a path mismatch — `MFDB_CMS_Manager`'s schemas for Category,
AuthorProfile, NavLink, SiteConfig, and the Page/PageContent model all
diverge from the live entities in field count, field names, and/or key
strategy (AuthorProfile especially: UUID-keyed vs. the live entity's
name-keyed, no-UUID-at-all shape). Full findings and the entity-by-entity
compatibility table: `docs/CLI_Data_Layer_Disconnect_Report.md`. Remediation
started pkg80: `cms-manage.py`'s `status`, `category`, `navlink`, and
`config` commands now use `CMSCore` directly against the real live manifest
(`get_db()`, new alongside the existing disconnected `get_manager()`) —
verified with a real cross-system test: a category added via the CLI
appeared in the live, running Admin web UI. `author`, `page`, `asset`,
`app`, `ad`, `backup`, `restore`, `mount`, `commit` are unchanged, still on
the old disconnected manager, pending the design decisions listed in the
report.

**Update, pkg81:** completed the remaining conversion. `author` (now
name-keyed, matching the live `AuthorProfile` schema exactly — it has no
UUID field), `ad`, `app`, `asset` (+ `add-external`/`delete-external`/
`list-external`), and `page` (`add`/`update`/`delete`/`import --html`) all
now use `CMSCore` against the real live manifest. `page` implements the
real two-part write contract: a `PageRecord` row via `CMSCore` plus a
standalone `pages_db/<uuid>.json` content file, written atomically
(temp+`os.replace`) and read/updated via Field Map Cache lookups
(`bejson_core_get_field_map`), matching `BEJSON_CMS_Content.py` exactly —
no positional indexing, per the BEJSON Usage policy. `backup`/`restore`
were redefined as real live-data zip export/import
(`storage/mfdb/{site_master,pages_db,assets,standalone_apps}`), with an
automatic safety backup taken before any restore. `mount`/`commit` are
deprecated with explicit messaging (they only ever touched the disconnected
workspace); `factory-reset` now says plainly that it doesn't touch live
data and points at the real web UI instead. `db list` rebuilt against a
`CMSCore` entity map. `page import --app` and `asset optimize` are
deliberately left unconverted — flagged in their own error messages —
because their live write shape/target path hasn't been verified against
real code yet; guessing at either risks silent data corruption.

**Verification (real live data, not synthetic):** full add/update/delete
cycles run for author, ad, app, asset, external-media, and page against the
actual live manifest and `storage/mfdb/`, each confirmed via `db list`
before/after and cleaned up afterward. `page update`'s body/title write
confirmed correct in the real `pages_db/<uuid>.json` file. A live cross-
system check — same class of proof used for `category` in pkg80 — added an
author via the CLI, then booted the real `BEJSON_CMS_Admin.py` Flask app
(HTTP Basic Auth) and confirmed the CLI-added author rendered at the actual
`/site/authors` route; deleted afterward, author list confirmed back to its
original 3 entries. `backup` produced a real 47-file zip of live data;
`restore` was tested in an isolated copy of `storage/` (never touching real
data) by deleting all `pages_db/*.json` files and confirming `restore`
correctly recovered all 5. Full `py_compile` sweep across every `.py` file
in the project: clean.

**Status:** fully remediated. Remaining gap from earlier entries --
`mount`/`commit` as legacy escape hatches, pending Elton's call -- is
resolved: removed entirely at pkg139 (Elton: "remove entirely"). See
"Correction, pkg139" below.

**Correction, pkg139:** the "Status" line above used to list `mount`/
`commit` as remaining, explicitly-labeled legacy escape hatches, pending
Elton's call on whether the disconnected workspace model had any
remaining use. Elton's call: remove them. Done -- `cmd_mount`/
`cmd_commit`, their argparse subparsers, and their dispatch-table entries
are gone; `mount`/`commit`/`repack` are no longer valid commands at all
(verified: both now correctly error as an unrecognized command).
`get_manager()`/`MFDB_CMS_Manager` itself was NOT removed -- `cmd_status`
still reports on the legacy workspace read-only (Mounted/Dirty Changes),
in case something outside this CLI still touches that archive directly;
its printed NOTE was updated so it no longer references the now-gone
commands. Verified `status` still runs clean with the corrected message.

**Correction, pkg138:** the line above used to also list `asset optimize`
as needing its live write shape verified. Checked directly this session --
it's already fully converted and correct, not a gap. Live-tested end to
end: created a real PNG MediaAsset row, ran `asset optimize --dry-run`
(correctly previewed with no changes made), then for real -- confirmed the
PNG converted to WebP on disk, the MediaAsset row's filename/mime/size/hash
all updated correctly, and `asset_uuid` (pkg135) was correctly preserved
through the update (it's keyed by `asset_filename`, not touched by this
command, so preservation was automatic -- confirmed rather than assumed).
Cleaned up after; live data confirmed back to its original 4-asset baseline.

**Correction, pkg113:** the entry above (written pkg81) said `page import
--app` was left unconverted. Checked directly this session — it wasn't;
it already uses `get_db()`/`CMSCore` with fully canonical field names.
Live-tested end to end: inserted a real `StandaloneApp` record, ran
`page import --app <uuid>`, confirmed the resulting `PageRecord` row and
`pages_db/<uuid>.json` content file were both correct (real iframe embed
markup, canonical fields throughout), cleaned up after. Also fixed
`cmd_status`'s own printed NOTE text, which still described the pkg80
intermediate state (naming `author`/`page`/`asset`/`app`/`ad` as
disconnected) — corrected to match current reality.

**Update, pkg134:** the pkg81 conversion made `author` name-keyed to match
the live schema, but only converted the data-access layer — it didn't
check whether the *duplicate-detection logic* itself matched the web's.
It didn't: `cmd_author_add()` compared `author_display_name` with an exact
(`==`) match, while both web-side author-creation paths
(`BEJSON_CMS_Content.py`'s `manage_authors()`,
`BEJSON_CMS_ProfileManager.py`'s persona→author sync) already compare
case-insensitively. Since `AuthorProfile` still has no UUID field —
`author_display_name` is the only key that exists — a case-only variant
added via the CLI (e.g. `"JANE DOE"` when `"Jane Doe"` already existed
from the web UI) would silently create a second, disconnected row with
nothing left to catch the collision. Elton reported this as "a disconnect
between the CLI and the author features."

Fix: made `cmd_author_add()`'s duplicate check case-insensitive, matching
both web paths. **Verified live** against the real (not synthetic)
`authorprofile.bejson`: confirmed no case-duplicate already existed before
touching anything; re-running `author add` with a case-variant of the
existing author is now correctly rejected; a genuinely new name still
adds and deletes cleanly; live data confirmed back to its original
single-row state afterward. `cmd_author_update()`/`cmd_author_delete()`
left untouched — a case-mismatched update/delete fails safely with "not
found" today, which isn't this bug's failure mode (silent duplication),
so out of scope here.

**Status:** the CLI/live-data structural disconnect remains substantially
remediated (per pkg81/pkg113). This entry is a narrower, separate finding:
one remaining behavioral inconsistency between the CLI and web write paths
for the one entity (`AuthorProfile`) that's still name-keyed rather than
UUID-keyed — worth keeping in mind if any of the other 5 name-keyed
entities (`Category`, `MediaAsset`, `NavLink`, `SiteConfig`, `SocialLink`,
per `docs/taxonomy_remediation_plan.md`) grow a second write path with its
own duplicate-check logic.

---

## `BEJSON_CMS_Media.py` — two `copyAssetPath` onclick sites missed by the pkg123/pkg124 delegation fixes (found + fixed pkg133)

**Severity:** High — same exploitable-quote bug class as pkg123 #7 (author
names) and pkg124 H-1 (rename/lightbox), confirmed by an external audit;
two call sites survived both prior passes.

**What's wrong:** the external-links table's and the YouTube tab's "Copy
URL" buttons built `onclick="copyAssetPath('{html.escape(extmedia_url)}')"`.
`html.escape()` turns a literal `'` into `&#39;`, but the browser decodes
that entity back to a raw `'` before running the `onclick` attribute as JS
— an `extmedia_url` containing a single quote breaks out of the string
argument.

**Fix:** both sites now use `data-url="{html.escape(...)}"` plus the
existing `document.body` delegated click handler (added a `.copy-url-btn`
branch), matching the pattern already used correctly for rename/lightbox
in the same file.

**Verified:** rendered a crafted URL containing `');alert(1);//` through
the actual f-string template — confirmed it lands only inside the
HTML-escaped `data-url` attribute value, never inside executable JS source.

---

## `BEJSON_CMS_Media.py` — SVG upload allowed with no sanitization (found + fixed pkg133, sanitizer built + re-enabled pkg139, remaining serve/replace gaps closed pkg140)

**Severity:** High — stored XSS. `ALLOWED_ASSET_EXTENSIONS` permitted
`.svg`, and `serve_asset()` does `send_file()` with zero content
inspection. An uploaded SVG can carry `<script>`/`on*=` payloads and gets
served back verbatim. A code comment acknowledged the risk ("sanitize SVG
content before serving") but no sanitizer was ever implemented.

**Fix (pkg133):** removed `.svg` from `ALLOWED_ASSET_EXTENSIONS` — the
zero-risk immediate option per the audit, since no sanitizer existed.

**Resolution (pkg139, Elton: "build sanitizer + re-enable"):** built
`lib_bejson_Core_svg_sanitizer.py` -- a stdlib-only (no new dependency,
matching this project's Termux/Pydroid3-friendly conventions) strict
allowlist sanitizer using `xml.etree.ElementTree`. Only explicitly
known-safe elements/attributes/namespaces survive; `<script>`, `<style>`,
`<foreignObject>`, `<image>`, SMIL animation elements, `on*=` handlers,
and non-local `href`/`xlink:href` values are all dropped unconditionally,
not selectively filtered. `.svg` re-added to `ALLOWED_ASSET_EXTENSIONS`;
every upload now runs through the sanitizer before being written to
disk, and a file that fails (doesn't parse, isn't an `<svg>` document) is
rejected outright. `serve_asset()` additionally sends
`Content-Security-Policy: script-src 'none'; sandbox;` on `.svg`
responses as defense in depth on top of sanitization.

**Verified:** ran 13 real attack payloads against the sanitizer directly
before trusting it — `<script>`, `onload=`/`onclick=`, `foreignObject`
with embedded `<script>`, `javascript:` hrefs, CSS-based XSS via
`style=`, SMIL `<animate onbegin=...>`, an external `<image>` reference,
and an actual XXE payload (confirmed via a direct, separate check that
Python's stdlib expat parser genuinely refuses the external entity —
didn't just assume this from documentation). A legitimate icon SVG
survives sanitization intact and renders identically. Then verified
through the real Flask upload route end to end, not just the sanitizer's
own unit-level tests: a malicious SVG (`<script>` + `onload=` cookie
exfiltration) came out the other end on disk completely inert; a
genuinely broken/unparseable file was correctly rejected with nothing
written to disk or queued for processing; confirmed the CSP header is
actually present on a served `.svg` HTTP response, not just intended.
All test assets cleaned up after; live data confirmed back to its
original 4-asset baseline.

**Correction, pkg140:** the pkg139 fix above only covered
`BEJSON_CMS_Media.py`'s `serve_asset()` and the upload handler. Continuing
the same sweep immediately after pkg139 shipped found three more gaps in
the same attack class, same file plus one sibling file:

1. `serve_thumb()`'s fallback path (serves the raw original when no
   thumbnail exists yet) had no CSP header. For `.svg` this fallback is
   the ONLY path ever taken -- `.svg` is not in `_THUMBABLE_EXT`, and the
   gallery view's `<img>` tags always request `/assets/thumb/<file>` for
   every asset row regardless of type, so this was a live, reachable gap,
   not a theoretical one.
2. `assets_replace()` (overwrite an existing asset's content under the
   same stored filename) never sanitized at all, for any extension --
   meaning "replace" was a second, completely unprotected write path to
   the same files the upload handler had just been locked down for:
   someone could overwrite an already-sanitized SVG with raw malicious
   content under the same filename.
3. `BEJSON_CMS_PageEditorV2.py` has its OWN separate implementations of
   both `serve_asset`/`serve_thumb` (as `serve_asset_v2`/`serve_thumb_v2`)
   serving the exact same physical files -- neither had picked up the CSP
   header either, since they're a separate route registration in a
   separate Flask app, not something that inherits from the other file's
   fix automatically.

All three fixed the same way as the original pkg139 fix (CSP header on
serve paths, `sanitize_svg()` on the write path). Verified live: created
a real SVG asset, replaced it via `assets_replace()` with a payload
containing `<script>` + `onload=` cookie exfiltration, confirmed the
on-disk content came out completely inert; confirmed both files'
`serve_thumb`/`serve_thumb_v2` fallback now sends the CSP header for a
real SVG request; confirmed a non-`.svg` asset is unaffected by any of
the three changes. All test data cleaned up after.

---

*Add new entries above this line, newest first. Each entry should state
what was actually run/observed to confirm the finding, not just what the
code appears to do on read-through.*
