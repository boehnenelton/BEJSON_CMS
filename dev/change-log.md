# BEJSON_CMS Change Log

## [18.38-PKG147] - 2026-11-12

### Added
- **2-Tier Modular Skeleton Scope Architecture**:
  - Global Shell (`Global_Skeleton.html`) vs. Local Body slot mapping in `BEJSON_CMS_Publisher.py`.
  - Created `resources/templates/Home_Bulletin_Skeleton.html` supporting both text announcement links and 16:9 responsive YouTube video embeds.
  - Adaptive category dock strip (`{{category_bar_above_html}}` / `{{category_bar_below_html}}`) with single-row horizontal scrolling and mobile portrait overflow protection.
  - Homepage feed suppression toggle (`home_feed_enabled` flag and `home_category_bar_position` selector) for minimalist custom landing page compilation.
  - Asynchronous background server management tool `server_manager.py` with Termux clipboard synchronization and Android Activity Manager Chrome dispatch (`am start -n com.android.chrome/...`).
  - Unit test suite `tests/test_bejson_cms_skeleton_and_bulletin.py` (8 new tests, 108 total passing).
  - Cataloged future roadmap proposal #11 for Featured Card Carousel & GitHub Repo Stage (`Home_Carousel_Skeleton.html`) in `suggestions.md`, `notes_tool` (`not_024`), and architecture reports.

### Fixed
- **Dark/Light Theme Token Contrast Alignment**:
  - Bound category pills and buttons to `font-family: var(--font-main)` ('Inter', sans-serif).
  - Aligned unresolvable `--card-bg` references to semantic theme tokens `var(--bg-card, var(--card-bg))` and `var(--border-color)` across `light.css`, `dark.css`, `Category_Skeleton.html`, and `Home_Skeleton.html`.

## [18.38-PKG146] - 2026-11-10

### Changed (vendored libs)
- Google Search-free, versions bumped: `bejson_gemini` 2.5.1, `bejson_groq` 3.1.1, `bejson_openrouter` 3.2.1, `chat_gemini_engine` 1.0.1, `chat_interactions_engine` 1.2.1, `gemini_standard_profiles` 4.0.1, `Core_bejson_schema` 2.3.5. Code identical to libraries_104 and CLI_AI copies.
- From CLI_AI PKG57: `ai_constants` 1.3.0, `ai_context_bubble` 2.2.1, `bejson_ollamalocal`, `lib_ai_model_registry` (2 new OllamaLocal models). `ai_dispatch` 1.8.2.

### Open
- `lib_bejson_Core_bejson_env.py`: CMS has `DEFINITIONS_FILE` support the other trees lack; owner decision pending.

## [18.37-PKG145] - 2026-11-09

### Changed (vendored libs, user-approved)
- `lib_bejson_AI_bejson_litertlm.py` 1.0.0 -> 1.1.0, `lib_ai_model_registry.py` (OllamaLocal/LiteRTLM services) from libraries_104.
- `lib_bejson_AI_ai_dispatch.py` -> 1.8.2: routes `ollamalocal` and `litertlm`.
- `lib_bejson_AI_chat_gemini_engine.py`: header no longer claims Google Search (header only).

### Not changed
- Google Search stays out of the CMS libs; master/CLI_AI copies of those files were not adopted.
- `lib_bejson_Core_bejson_env.py`: CMS has `DEFINITIONS_FILE` support the other trees lack; owner decision pending.

## [18.36-PKG144] - 2026-11-09

### Added
- `cms-manage.py` (v18.13): `page set-author AUTHOR` bulk re-author with `--uuid/--category/--type/--current-author/--since/--title-contains`, `--all`, `--dry-run`, `--publish`. Requires an existing AuthorProfile. 5 tests. README usage added.

## [18.35-PKG143] - 2026-11-08

### Added
- Built-in **Anonymous** author, seeded by `BEJSON_CMS_System.py` (v18.25) at startup/after reset and on demand by `cms-manage.py` (v18.12).

### Changed
- `page add`, `quick-post`, `page import --html/--app` and `page md-import` default to Anonymous (previously empty / Leethaxor69 / boehnenelton2024). An explicit author with no AuthorProfile now logs a warning.

### Open
- Bulk re-author command and Publisher author cards/pages: packages 144/145. Job system (vendored) still defaults to boehnenelton2024.

## [18.34-PKG142] - 2026-11-08

### Fixed
- `cms-manage.py` (v18.11): `page add` and `quick-post` now write `page_created_at` as `YYYY-MM-DD`, matching every other writer. The Publisher renders the raw value, so CLI posts previously displayed a time. Existing timestamped rows not migrated; same-day ordering on the dashboard falls back to manifest order.

## [18.33-PKG141] - 2026-11-08

### Fixed
- `AGENTS.md`: test count 21 -> 91 (+ note on the 2 pre-existing failures); `PageEditorV2.py` map row marked deprecated/removed. Docs only.

## [18.32-PKG140] - 2026-11-08

### Fixed
- **`src/cms-manage.py` (v18.10) aligned with CMSCore**:
  - `page md-import` no longer calls `md2html.import_markdown_file_to_cms()` (direct `pagerecord.bejson` + manifest edits, `104a`/`PageContent` content file). It now writes through CMSCore via `_import_markdown_file()`, reusing only md2html's pure converter; directory mode defers the manifest sync (`sync_count=False` + one `sync_manifest_count()`).
  - New `_checked_add()` guard: CMSCore silently drops keys the live entity lacks and still returns `True`; every cms-manage add now refuses and names the missing fields (empty-valued unknown keys allowed).
  - New `_create_page()`: content file written before the PageRecord row, removed again if the row write fails. Used by `page add`, `quick-post`, `page import --html/--app`, `page md-import`.
  - `page update --type` is now applied; `update_record()` failure is reported instead of printing success.
  - `status` reads the live manifest and per-entity counts via CMSCore instead of the disconnected `MFDB_CMS_Manager`.
  - `page md-import` warns when the target category does not exist.

### Added
- `tests/test_cms_manage_core_alignment.py` (9 tests, throw-away MFDB only).
- `dev/checklist-20261108-052725.md`.

### Verification
- Suite: 89 passed, 2 failed. The same 2 (`test_bejson_cms_profile_manager.py` t5, t8) fail identically on the untouched uploaded ZIP (80 passed, 2 failed).

### Open (not changed)
- `md2html.import_markdown_file_to_cms()` / `batch_import_markdown_directory()` now have no callers (vendored, left in place).
- Live `104db` content-file shape (Content.py, PageEditor.py, bks_blog_jobs.py, cms-manage) fails `lib_bejson_Core_bejson_validator` (`meta_title missing Record_Type_Parent`).
- `CMS_DATA_ROOT` is honoured by cms-manage but not by `BEJSON_CMS_Shared.py`; `--publish` with an override publishes the project's own storage.

## [18.31-PKG139] - 2026-11-06

### Added
- **Consolidation & Clean Article Reset**:
  - Consolidated drift across development repositories, anchoring `/storage/emulated/0/Admin/Dev/Repos/BEJSON_CMS` as the sole canonical master repository.
  - Reset articles to exclusively host the 6 new deep-dive books/articles written in the `Leethaxor69` persona:
    1. *The Elite Hacker's No-BS Guide to BEJSON & MFDB Architecture* (`7573cc7d-8b2d-4c23-8007-98beb8db8328`)
    2. *BEJSON 105 & MFDB 1.40: The Identity Era & Cryptographic Integrity Masterclass* (`b9161aaf-c14c-4f5a-a444-9ff7399687b0`)
    3. *The Polyglot Parity Bible: BEJSON 104 Core Across Python, JS, TS, and Bash* (`7513e7fe-f937-4eaf-9908-96224251b66f`)
    4. *The Polyglot Parity Bible Part II: BEJSON 105 Core & MFDB v1.40 Across Python, JS, TS, and Bash* (`ebe88c9c-47bd-47a4-9f8d-35463bd523f1`)
    5. *The Polyglot Parity Bible Part III: Inside the BEJSON 104 Core AI Family* (`d0dc2f5b-ab44-47a1-ba62-fcf566309907`)
    6. *Shadow Link's Awakening: Dissecting the Zero-Hardcoded BEJSON 105 React Action-RPG Engine* (`89b6ebfa-ad88-4521-a700-bf6f43d2ac37`)
  - Integrated `Leethaxor69` AI profile into `ai_profile.bejson` matching the 24-field zero-leakage schema.
- **Rapid CLI Tooling**:
  - Upgraded `src/cms-manage.py` (v18.9) with atomic `quick-post`, $O(1)$ `page append`, headless `publish`, and optional category auto-slugs.
  - Added standalone `src/lib/cli/cms_quick_poster.py` (v100) utility.
- **Full Verification**:
  - All 73 tests in `tests/` pass. Static build compiles cleanly across `BEJSON`, `Projects`, and `Uncategorized`.

## [18.31-PKG135] - 2026-11-02

### Added
- **Consistent Graphics 105 Hero Banners & Architectural Blueprints**:
  - Authored canonical 1280x640 Policy §8.1 Tri-Color SVG hero banners (`project_chunker_ecosystem_hero.svg` and `bejson_105_integrity_era_hero.svg`) matching the existing articles (`newagent_runtime_hero.svg`, `bejson_104_telemetry_hero.svg`, `code_as_biological_substrate_hero.svg`, `antigravity_biological_substrate_hero.svg`) with 8-lane quantized geometry, 32px Ry rows, header HUD, 4 peripheral subsystem cards, and central isometric BEJSON cubes.
  - Authored 1280x720 16:9 3-pillar architectural blueprint slides using `lib_bejson_Graphics_graphics_core.render_branding_architecture_slide_svg()` (`project_chunker_architecture_diagram.svg` and `bejson_105_architecture_diagram.svg`).
  - Rendered high-DPI (2x scale) raster PNG captures for all 6 article heroes and 2 architecture diagrams using `lib_bejson_Graphics_graphics_core.render_still_frame()` with `termux_playwright`.
  - Compiled optimized WebP assets for all graphics using PIL.
- **Media Asset & Page Registration**:
  - Registered 24 new media assets (SVGs, PNGs, WebPs) in `storage/mfdb/site_master/data/mediaasset.bejson` with SHA-256 hashes, byte sizes, and MIME types.
  - Updated `pagerecord.bejson` linking `project_chunker_ecosystem_hero.svg` to Article 5 and `bejson_105_integrity_era_hero.svg` to Article 6.
  - Updated `pages_db` for both articles, replacing placeholder references and embedding the architecture blueprint diagrams into Section 2.
- **Static Site Compilation & Playwright Verification**:
  - Re-compiled static site distribution into `storage/builds/` via `BEJSON_CMS_Publisher._execute()`.
  - Verified with Playwright across Desktop (1280px) and Mobile (375px) that all articles render with 0 horizontal overflow.

## [18.31-PKG134] - 2026-11-02

### Fixed
- **Playwright Page Width Blowout & Button Overflow**:
  - Replaced `.toolbar-row` (which had `flex-wrap: nowrap`) in `#t-tasking` with `.workflow-bar` (`flex-wrap: wrap; gap: 10px; align-items: center;`). On mobile screens <= 640px, workflow buttons expand to full container width so labels like `3. Approve & Overwrite Target Post` are never truncated or pushed past the right viewport boundary.
- **Responsive Layout & Grid Collapsing**:
  - Replaced hardcoded inline grid columns (`grid-template-columns: 1fr 1fr` and `grid-template-columns: 1.2fr 0.9fr 1.2fr`) in `BEJSON_CMS_PageEditorV2.py` with responsive utility classes `.editor-grid-2` and `.editor-grid-3`. Added media queries collapsing 3-column rows at `<= 860px` and 2-column rows at `<= 640px`.
  - Tuned `.header` horizontal padding on mobile from 80px down to 20px, and reduced `.editor-wrap` container padding from 25px to 14px on screens `<= 640px` to maximize usable screen real estate.
- **Drawer Menu Trap**:
  - Fixed `showTab(id)` in `BEJSON_CMS_PageEditorV2.py` to call `closeMenu()` instead of `toggleMenu()`. Prevents the 300px sidebar drawer from popping open and covering the viewport when navigating directly or programmatically via Playwright.
- **Plan Card Flex Squishing**:
  - Added `flex-wrap: wrap` and `min-width: 200px` to the Part card header rows in both `BEJSON_CMS_PageEditorV2.py` and `BEJSON_CMS_Content.py` (`/jobs`), preventing the Part title input field from being compressed into an unreadable zero-width box on mobile screens.
- **Article & Preview Horizontal Containment**:
  - Added `overflow-x: auto; max-width: 100%;` to `#bks_merged_html_preview` in both editors.
- **Playwright Verification Suite Fixes**:
  - Updated `storage/tmp/playwright_cms_verify.py` Target 4 tab activator to trigger `showTab('tasking')` cleanly without locator timeouts, and corrected the published article route target to point to the active generated slug. Verified 0-overflow across desktop (1280px), tablet (768px), and mobile (375px) viewports.
