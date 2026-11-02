# BEJSON_CMS Change Log

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
