# BEJSON CMS

A personal, self-hosted CMS built on BEJSON/MFDB storage instead of SQL. Every
page, category, author, ad, nav link, and media record lives as rows inside a
single MFDB manifest (`storage/mfdb/site_master/104a.mfdb.bejson`) backed by
one BEJSON 104 entity file per table. Five Flask apps edit that data; a sixth
publisher renders it out to a static, dependency-free HTML site.

## Features

- **Blueprint admin app** (`BEJSON_CMS_Admin.py`) — pages, categories, media
  library, standalone apps, authors, nav/social/ad config, HTML import, and a
  publish trigger, split into four Blueprints (System / Content / Media /
  Interface) registered from one thin entry point.
- **Canonical Prefix Taxonomy & Strategy Renderers** — all 10 live entity tables
  use canonical prefix tags (`page_`, `author_`, `asset_`, `extmedia_`, `ad_`, `cat_`, `nav_`, `sys_`, `social_`, `app_`) and synthetic UUID primary keys (`<prefix>_uuid`). Static rendering features a polymorphic strategy pattern (`BEJSON_CMS_Renderers.py`) for Standard, Video, and Document page types.
- **Two page editors** — `BEJSON_CMS_PageEditor.py` ("V1") and
  `BEJSON_CMS_PageEditorV2.py` ("V2", API-driven, in active development) — both
  read/write the same page content contract and are cross-compatible.
- **AI Persona Hub** (`BEJSON_CMS_ProfileManager.py`) — maintains `AI_Profile`
  records that shape system instructions used by the page editors' AI
  generation features, kept separate from the public-facing `AuthorProfile`
  bio shown on the live site.
- **Static publisher** (`BEJSON_CMS_Publisher.py`) — renders the full MFDB
  content set into `storage/builds/` as a static site (dark/light themes,
  category/page/app feeds, ad zones, generated excerpts, polymorphic page type rendering).
- **Single-service launcher** (`cms_launcher.sh`) — kills any other running
  CMS service before starting the requested one, keeping RAM usage low on
  constrained devices (Termux/Pydroid3 on Android).
- **MediaAsset-backed Media Library** — paginated gallery, hash-dedup upload
  queue (single serial worker, low peak memory), bulk delete, replace,
  external-media links, tap-to-zoom lightbox.

## Installation

```bash
# Python 3.10+, Flask required. No other services (no SQL server) needed.
pip install flask --break-system-packages
```

No build step — this is a flat Python/Flask project. Clone or unzip it
anywhere; every script self-locates its own root via `SCRIPT_PATH`.

## Usage

Start the admin app (recommended entry point on Android/Termux):

```bash
python3 pydroid_start.py
# → launches src/web/BEJSON_CMS_Admin.py on http://127.0.0.1:5001
```

Or launch any individual service directly through the modular launcher, which
ensures only one Flask process runs at a time:

```bash
./cms_launcher.sh admin       # BEJSON_CMS_Admin.py      :5001
./cms_launcher.sh editor      # BEJSON_CMS_PageEditor.py
./cms_launcher.sh editorv2    # BEJSON_CMS_PageEditorV2.py
./cms_launcher.sh publisher   # BEJSON_CMS_Publisher.py
./cms_launcher.sh profiles    # BEJSON_CMS_ProfileManager.py
```

Manage content headlessly (no Flask server required) with `cms-manage.py` or
the standalone CLI shipped in Anthropic's `bejson-cms-manager` skill:

```bash
python3 src/cms-manage.py status
python3 bejson_cms_cli.py --project . add-page --title "New Post" \
    --category BEJSON --html-file body.html
```

Publish the live database to a static site:

```
Open BEJSON_CMS_Publisher.py's web UI (Interface > Publish) and click Build,
or POST to its /build route. Output lands in storage/builds/.
```

Set `CMS_PASSWORD` before exposing any service beyond localhost — it defaults
to `changeme` and prints a loud startup warning if left unset.

## Project Structure

```
src/web/            Six Flask apps (Admin + its 4 Blueprints, PageEditor,
                     PageEditorV2, ProfileManager, Publisher)
src/lib/             CMSCore + BEJSON/MFDB core libraries, cli/ standalone tools
storage/mfdb/         Live database: site_master manifest + entity files,
                     pages_db/ (per-page content), assets/, standalone_apps/
storage/builds/       Generated static site output (regenerated on publish)
storage/tmp/          Import staging + service logs (wiped on factory reset)
resources/            HTML skeleton templates + dark/light stylesheets +
                     seeded default brand assets
docs/                 This documentation set
tests/                pytest suite (path guard + MFDB validator coverage)
```

## License

This project is licensed under PolyForm Noncommercial 1.0.0 — free for
personal, educational, research, and non-commercial use. Commercial use
requires a separate agreement with the copyright holder. See `LICENSE`.
