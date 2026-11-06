# Dead Code Log

## pkg119 — AI Multi-Page Builder (BEJSON_CMS_PageEditor.py)

**Removed entirely** — sidebar link, modal HTML, all JS (`openAiModal`,
`resetAiModal`, `setAiStatus`, `loadAiProfiles`, `loadAiContext`,
`toggleAiContext`, `generateAiPlan`, `renderAiPlan`, `buildAiPages`,
`listenToAiStream`), all 6 routes (`/api/ai/profiles`, `/api/ai/context`,
`/api/ai/context/toggle`, `/api/ai/generate_plan`, `/api/ai/generate_pages`,
`/api/ai/stream/<job_id>`), backend helpers (`_ai_push`,
`_get_context_files`, `_get_ai_profiles`, `_load_context_parts`,
`AI_JOB_QUEUES`, `AI_CONTEXT_STATE`), and the `AI_MODELS`/`CONTEXT_DIR`/
`PROFILES_DIR` constants that existed only to support it.

**Reason:** the feature called `ExtLib.CMSAIBuilder.setup_gemini(...)` —
`ExtLib` was never imported anywhere in the file, and no `CMSAIBuilder`
class exists in the project. Every click of "Generate Plan" or "Build All
Pages" would `NameError` behind a visible, reachable UI button. Verified
by direct grep against real code, not assumed from the audit report that
flagged it.

Confirmed via `grep` that every removed symbol had zero references outside
this dead feature before deletion — no shared helper was accidentally
pulled out. Full removal verified live: booted the real Flask app, page
list renders with no trace of the modal/link, `/api/ai/profiles` now 404s,
unrelated routes (`/new`) unaffected.

Rebuilding this as a real Gemini integration (using
`lib_cms_persona_writer.py` + the pattern already used correctly in
PageEditorV2's `/api/tasking/*` routes) is a separately-scoped future task,
not attempted here.

## pkg120 — `get_assets()` (BEJSON_CMS_Shared.py) and `_get_assets()` (BEJSON_CMS_PageEditor.py)

**Removed entirely** — both were raw `os.listdir(ASSETS_DIR)` listings used
to populate image-picker `<select>` dropdowns (Featured Image, Author
Avatar, Ad Banner, and PageEditor's own New/Edit Page image pickers). Any
file physically sitting in `ASSETS_DIR` — an orphan from a failed upload,
a manually copied file, a restored backup, anything not cleanly deleted
through the real Delete button or Factory Reset — stayed visible in every
picker forever, in a pool that never shrank even after the database record
was gone.

**Reason:** confirmed via a real test, not by inspection alone — copied a
real image file directly into `storage/mfdb/assets/` without registering
it in the `MediaAsset` DB (the exact shape of a failed-upload orphan), and
it appeared in the app/author/ad pickers before the fix.

**Fix:** replaced with `get_image_assets()` in `BEJSON_CMS_Shared.py`,
which reads `db.get_records("MediaAsset")` filtered to image MIME types —
the same real data source `edit_content()`'s picker has used correctly
since pkg68. `PageEditor.py` had its own independent copy of the same bug
(not named in the audit that flagged this), fixed the same way locally in
that file. Confirmed via `grep` that both old functions had zero remaining
callers before deletion.
