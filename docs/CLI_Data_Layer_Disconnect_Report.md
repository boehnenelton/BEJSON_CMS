# Report: `cms-manage.py` Is Disconnected From — And Schema-Incompatible With — the Live CMS

**Date:** 2026-08-08
**Severity:** High (at time of writing — see status update below)
**Status:** ⚠️ **SUPERSEDED, pkg81.** This report describes the pkg80
mid-remediation state (`status`/`category`/`navlink`/`config` converted,
`author`/`page`/`asset`/`app`/`ad`/`backup`/`restore`/`mount`/`commit`
still disconnected). All of those were converted in pkg81, and `cmd_status`'s
own output text was corrected in pkg113 to stop describing this stale state.
Current status, kept up to date: `docs/security-notes.md`. This file is
kept only for the entity-by-entity field-shape compatibility table in §2
below, which has lasting reference value; everything else here is history,
not current state.

---

## 1. Summary

`src/cms-manage.py`, the project's own CLI toolkit, does not manage the CMS
you actually run. It reads and writes a completely separate copy of the
database, in a different location, and — this is the part that wasn't known
when this was first flagged at pkg78 — **using different, incompatible
schemas** for essentially every entity checked. This is not a "wrong folder"
bug. Every write path in the CLI, if it were pointed at the live database
without further changes, would either fail outright (BEJSON's positional
field-count integrity would reject a mismatched row) or — in the worse case —
write a wrong-shaped row that silently corrupts live data the next time a
Flask app reads it.

## 2. How the two systems differ

The live CMS (all 6 Flask apps: Admin's 4 Blueprints, both page editors, the
Publisher, the Persona Hub) uses `CMSCore` (`lib_bejson_CMS_cms_core.py`)
against one manifest:

```
storage/mfdb/site_master/104a.mfdb.bejson
```

`cms-manage.py` uses a different class, `MFDB_CMS_Manager`
(`lib_bejson_CMS_cms_mfdb.py`), against a **workspace** populated by
extracting `.zip` archives:

```
storage/workspace/db_global/104a.mfdb.bejson    (from global_master.mfdb.zip)
storage/workspace/db_content/104a.mfdb.bejson   (from content_master.mfdb.zip)
```

Neither archive exists anywhere in this project. `mount_system()` doesn't
error when they're missing — it silently bootstraps a brand-new **empty**
workspace instead, which is how this went unnoticed: every command still
"works," it just works against a private empty universe.

That much was known at pkg78. What's new this session, from actually reading
`MFDB_CMS_Manager`'s method bodies rather than assuming its schema matches
the live one, is that **the two systems disagree about the shape of almost
every entity they both claim to manage:**

| Entity | Live schema (`CMSCore` / real Flask apps) | `MFDB_CMS_Manager`'s schema |
|---|---|---|
| Category | `category_name, category_slug` (2 fields) | `name, slug, description, feed_type` (4 fields) — writes `[name, slug, description, feed_type]` |
| AuthorProfile | `auth_name, auth_bio, auth_img` (3 fields, **name-keyed**, no UUID) | `author_uuid, name, bio, image_url` (4 fields, **UUID-keyed**) — `update_author()`/`delete_author()` both look up by `author_uuid`, a field that doesn't exist in the live entity at all |
| NavLink | `nav_label, nav_url` (2 fields) | `label, url, order` (3 fields) — writes `[label, url, order]` |
| SiteConfig | `config_key, config_value` (2 fields) | `config_key, config_value, description` (3 fields) |
| Page content | One `PageRecord` row (10 fields) + a standalone `pages_db/<uuid>.json` content file, **not** an entity in any manifest | A `Page` entity row **and** a separate `PageContent` entity row, both inside `content_manifest` — a different manifest than Category/Author/NavLink/SiteConfig, which live in `global_manifest` |

Every single entity checked diverges — in field count, field names, key
strategy, or all three. The Page/PageContent case is the most serious: it
isn't a field-shape mismatch, it's a completely different storage
*mechanism* (two manifest-backed entities vs. one manifest row + one
standalone file).

## 3. How this was verified

Not by reading code and assuming — by running it and, separately, by reading
every method body actually invoked by each CLI command before touching
anything:

- Ran `python3 cms-manage.py mount`, then `category list` — got back only
  the bootstrap default `["Uncategorized"]`.
- Queried the real live site at the same moment via `CMSCore` directly —
  got back `["Uncategorized", "BEJSON"]`, i.e. a real category (and every
  page under it) that the CLI cannot see at all.
- Confirmed via `find` that no `.zip` archive exists anywhere under the
  project root, so `mount_system()`'s "already have real archives" branch
  has never actually run in this project — every mount to date has taken
  the empty-bootstrap path.
- Read `add_category()`, `add_author()`/`update_author()`/`delete_author()`,
  `add_nav_link()`, `add_global_config()`, and `update_page()`/
  `delete_page()` directly, line by line, and compared each row shape / key
  field against the corresponding live `.bejson` manifest file's `Fields`
  list (not against older documentation, which itself turned out to be
  stale in places this session).

## 4. Impact

- Every `cms-manage.py` data command silently operates on a disconnected,
  effectively-empty dataset. None of it reflects, or can modify, the real
  site.
- If someone had previously tried to "fix" this by simply repointing the
  manager's paths at the live manifest locations — the obvious first
  instinct, and the one this investigation initially assumed would be the
  fix — every write command would have produced malformed rows on the first
  real use: wrong field count against BEJSON's positional-integrity model,
  wrong field names, and for authors specifically, a lookup key
  (`author_uuid`) that doesn't exist in the real entity at all.
- The CLI's `backup`/`restore`/`mount`/`commit` commands are built entirely
  around the `.zip`-archive model and have no equivalent concept in the live
  system (which has no archive step at all — `CMSCore` writes straight to
  the manifest). These commands need a decision, not a mapping.

## 5. Remediation

The only safe fix is switching `cms-manage.py` off `MFDB_CMS_Manager` and
onto `CMSCore` — the same data-access layer every Flask app already uses —
entity by entity, translating each command's semantics to match the real
schema rather than assuming a path swap is enough.

**Started this session** (verified working against live data, detailed
below in the delivered package's changelog):
- `status`
- `category` (add / update / delete / list) — straightforward: live schema
  is a strict subset of the old one (drops `description`/`feed_type`, which
  the live `Category` entity has no field for)
- `navlink` (add / delete / list) — same pattern, drops the unsupported
  `order` field
- `config` (set / list) — same pattern, drops `description`

**Deliberately not touched yet — each needs a decision, not just code:**
- **`author`** — the old CLI's `update`/`delete` are UUID-keyed; the real
  entity is name-keyed with no UUID field at all. Options: (a) key CLI
  author commands by name instead, matching the live entity exactly, or
  (b) add a `auth_uuid` field to the live `AuthorProfile` schema so both
  models can agree — that's a schema migration touching every Flask route
  that already reads `AuthorProfile`, not a CLI-only change. Recommend (a)
  unless there's a reason the live schema needs a UUID that hasn't come up
  yet.
- **`page`** — the real content model splits a page across a manifest row
  (`PageRecord`) and a standalone JSON file (`pages_db/<uuid>.json`, the
  two-part write contract documented in the `bejson-cms-manager` skill).
  The old CLI assumed both title and body lived in manifest-backed entities
  (`Page` + `PageContent`). This is the biggest of the three — it's not a
  field rename, it's matching an entirely different write contract.
- **`asset`** / **`app`** / **`ad`** — not yet audited to the same depth as
  the four above; likely have their own field-shape gaps and should be
  checked with the same method (read the manager's method body, diff
  against the live manifest's actual `Fields` list) before converting,
  rather than assumed compatible because they weren't flagged yet.
- **`backup`** / **`restore`** / **`mount`** / **`commit`** — archive-model
  concepts with no live-system equivalent. Needs a product decision: keep a
  backup/restore concept at all (and if so, define what it means against a
  manifest with no archive step), or drop these commands.

## 6. What shipped this session

`get_manager()` was replaced with a `get_db()` helper returning a `CMSCore`
instance pointed at the real `storage/mfdb/site_master/104a.mfdb.bejson`.
`cmd_status`, the `category` and `navlink` command groups, and `config
set`/`config list` were rewritten against `CMSCore`'s actual API
(`get_records`/`add_record`/`update_record`/`delete_record`) and the real
field names. Every rewritten command was tested against the live project
data, not just import-checked — see the delivered package's
`.bejson_project.json` changelog entry for the exact verification steps.
The remaining commands (`author`, `page`, `asset`, `app`, `ad`, `backup`,
`restore`, `mount`, `commit`) still call `MFDB_CMS_Manager` exactly as
before — **still disconnected, unchanged, not made worse** — pending the
decisions in §5.
