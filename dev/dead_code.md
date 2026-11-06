# Dead Code Log — BEJSON_CMS

## 2026-10-25 (pkg130)

1. **`_safe_slug(value, fallback="unknown")` in `src/web/BEJSON_CMS_Publisher.py` (lines 147–151)**
   - **Reason for Removal**: Verified zero callers across the entire repository via AST and grep scans (`EFF_01_DEAD_CODE`).
   - **Action**: Removed function definition, added inline documentation comment in `src/web/BEJSON_CMS_Publisher.py`, and logged in `.bejson_project.json`.

2. **Duplicate `src/lib/cli/bejson_server.py` implementation (lines 1–648)**
   - **Reason for Consolidation**: Byte-identical duplicate of `src/lib/bejson_server.py` (9 duplicate functions/classes flagged as `EFF_02_DUPLICATE_CODE_BLOCKS` and `EFF_07_DUPLICATE_ASSET_STORAGE`).
   - **Action**: Replaced full copy in `src/lib/cli/bejson_server.py` with a thin re-export wrapper delegating to `src/lib/bejson_server.py`.

3. **Duplicate `_enforce_auth_everywhere()` across 5 web apps**
   - **Locations**: `src/web/BEJSON_CMS_Admin.py`, `src/web/BEJSON_CMS_PageEditor.py`, `src/web/BEJSON_CMS_PageEditorV2.py`, `src/web/BEJSON_CMS_ProfileManager.py`, `src/web/BEJSON_CMS_Publisher.py`.
   - **Action**: Consolidated into `enforce_auth_everywhere()` and `register_auth_guard(flask_app)` in `src/web/BEJSON_CMS_Shared.py`.

4. **Duplicate `/assets/<path:filename>` and `/assets/thumb/<path:filename>` route handlers**
   - **Locations**: `src/web/BEJSON_CMS_Media.py` (`serve_asset`, `serve_thumb`) and `src/web/BEJSON_CMS_PageEditorV2.py` (`serve_asset_v2`, `serve_thumb_v2`).
   - **Action**: Consolidated into `serve_shared_asset(filename)` and `serve_shared_thumb(filename)` in `src/web/BEJSON_CMS_Shared.py` and bound via `add_url_rule()`.
