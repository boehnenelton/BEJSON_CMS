# Security & Architecture Notes

Findings that don't belong in `architecture.md` (which describes intended
design) — bugs and structural gaps discovered during real testing, per
System Development Policy §1.2. Each entry states how it was verified, not
assumed.

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

**Status:** substantially remediated. Remaining gaps: `asset optimize`
still needs its live write shape verified before conversion; `mount`/
`commit` remain as explicitly-labeled legacy escape hatches (`--force`)
rather than being removed outright, pending Elton's call on whether the
disconnected workspace model has any remaining use.

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

---

*Add new entries above this line, newest first. Each entry should state
what was actually run/observed to confirm the finding, not just what the
code appears to do on read-through.*
