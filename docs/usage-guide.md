# Usage Guide

## Admin app routes (BEJSON_CMS_Admin.py, port 5001)

All routes below require authentication (global `before_request` hook) —
default password is `changeme`; set `CMS_PASSWORD` before exposing beyond
localhost.

### Content cube
| Route | Method | Purpose |
|---|---|---|
| `/content` | GET | Content dashboard |
| `/pages` | GET | List all pages |
| `/pages/new` | GET, POST | Create a page (combobox author, hardcoded default featured image) |
| `/edit/<page_uuid>` | GET, POST | Edit a page — title, category, author, HTML body, featured image (upload-new supported inline) |
| `/pages/delete/<page_uuid>` | POST | Delete a page + its content file |
| `/pages/duplicate/<page_uuid>` | POST | Clone a page (new UUID, auto-uniquified slug, "Copy of ..." title); rejects external-link pages |
| `/links`, `/links/new` | GET / GET,POST | External-link "page" items (`page_type == "external_link"`) |
| `/categories`, `/categories/add`, `/categories/delete/<cat_uuid>` | GET / POST / POST | Category CRUD (delete is UUID-keyed as of pkg135) |
| `/apps`, `/apps/new`, `/apps/edit/<app_uuid>`, `/apps/delete/<app_uuid>`, `/apps/view/<app_uuid>[/<path:filename>]` | — | Standalone-app bundle CRUD + serving |
| `/site/authors` | GET, POST | `AuthorProfile` CRUD with case-insensitive duplicate-name check |
| `/import`, `/import/preview`, `/import/confirm`, `/api/import/process_item` | — | HTML batch-import pipeline |

### Media cube
| Route | Method | Purpose |
|---|---|---|
| `/assets` | GET | Paginated gallery (24/page), Files/Links tab switcher |
| `/assets/upload` | POST | Queue file(s) for background processing |
| `/assets/delete/<filename>`, `/assets/bulk_delete` | POST | Delete one or many |
| `/assets/replace/<filename>` | POST | Overwrite content in place, same stored filename |
| `/assets/rename/<filename>` | POST | Display-name only — physical filename never changes |
| `/assets/external/add`, `/delete/<uuid>`, `/rename/<uuid>` | POST | External media link CRUD |
| `/assets/<filename>`, `/assets/thumb/<filename>` | GET | Serve original / thumbnail (falls back to original if no thumbnail exists) |
| `/assets/list.json` | GET | JSON listing, used by the edit-page upload-poll flow |

### Interface cube
| Route | Method | Purpose |
|---|---|---|
| `/` | GET | Admin home |
| `/site/nav`, `/site/social`, `/site/ads` | GET, POST | `NavLink` / `SocialLink` / `AdUnit` config |
| `/publish` | GET | Trigger a static-site build via `BEJSON_CMS_Publisher.py` |

### System cube
| Route | Purpose |
|---|---|
| Dashboard, `SiteConfig` editing, `/reset` + `/reset/confirm` | Stats, config, factory reset (self-heals `Uncategorized` category + default brand/author) |

## Page editors

**V1** (`BEJSON_CMS_PageEditor.py`): `/`, `/new`, `/edit/<page_uuid>`,
`/save`, `/api/ai/*` (profiles, context, generate_plan, generate_pages,
stream), `/delete/<page_uuid>`, `/upload_code`, `/upload_markdown`,
`/list_assets`.

**V2** (`BEJSON_CMS_PageEditorV2.py`): `/`, `/api/storage/config`,
`/api/storage/list_files`, `/api/context/list`, `/api/context/upload`,
`/api/tasking/generate_plan`, `/api/tasking/execute_task`,
`/api/get/<uuid>`, `/api/save`, `/api/media/list`, `/api/media/rename`,
`/api/delete/<uuid>`, `/api/category/add`, `/api/settings/*`.

## ProfileManager ("Persona Hub")

`/`, `/edit/<persona_uuid>`, `/save`, `/delete/<persona_uuid>` — manages
`AI_Profile` records (25 fields: Tone, Archetype, CodeParsing_Languages,
Creativity, etc.) that shape AI-generated page content when a matching
author/persona is selected in either page editor. UUID-keyed as of
pkg135 (previously name-keyed).

## Publisher

`/` — status dashboard for the last build. The actual build is triggered
from the Admin app's `/publish` route or the Publisher's own build endpoint;
output is written to `storage/builds/`.

## CLI tools

```bash
# Headless content management (no Flask server needed):
python3 src/cms-manage.py status
python3 src/cms-manage.py serve <admin|editor|editorv2|profiles|publisher>

# MFDB chunking (pack/unpack a directory tree into one portable BEJSON file):
python3 src/lib/lib_mfdb_chunker_v6.py --help
```

Content-only edits (add a page/category/author without running a Flask
server) are best done through the standalone `bejson_cms_cli.py` shipped in
Anthropic's `bejson-cms-manager` skill — it calls the same `CMSCore` this app
uses, idempotently on slug/name. See that skill's `references/cli_reference.md`
for the full flag list.
