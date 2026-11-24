# AGENTS.md — libraries_105

**Name:** AGENTS.md (libraries_105)  
**Description:** Standing instructions for AI agents working in or against the BEJSON 105 / MFDB v1.40 library repository. Place at the repository root. Full detail: `Libraries_105_Agent_Directive-V10101-PKG101.md` (repository root).  
**Version:** `VERSION = 10101`  
**Date Created:** 2026-11-08  
**Author:** Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton  
**RELATIONAL_ID:** `b6d36c67-e789-4c81-9b2b-aa748e76ce34`

---

## What this repo is
Four-language BEJSON Integrity Era runtime: `Lib_PY` (Python ≥ 3.10), `Lib_JS` (Node ≥ 18), `Lib_TS` (TS ≥ 5), `Lib_SH` (Bash ≥ 4.4 + `jq`). Zero third-party runtime dependencies. Formats: BEJSON `104`, `104a`, `104db`, `105`, `105a`, `105db`; MFDB v1.40 (one `104a.mfdb.bejson` manifest + entity files).

## Two audiences — pick yours
1. **You are consuming the libraries** (building an app on them): read §3 onward. Never modify this repo.
2. **You are changing the libraries themselves**: only when the user explicitly asks. Core is frozen by default; follow §7.

## 1. Trust order for facts
1. Library source files. 2. This file. 3. `Libraries_105_Agent_Directive-V10101-PKG101.md`. 4. `clarification.md`. 5. `README.md` (**contains wrong examples**, see §2).

## 2. Known-wrong docs — do not copy
- `README.md` Python quickstart imports `lib_bejson_Core_bejson_core_105` and `bejson_core_105_*` functions: **they do not exist in Python.**
- `README.md` JS quickstart calls `bejson_core_parse_bejson`: **does not exist.** Use `JSON.parse(fs.readFileSync(...))`.
- "E90–E95" structural errors and `105a.mfdb.bejson`: **wrong.** Codes 90–114 were removed; the manifest is always `104a.mfdb.bejson`.
- "Exact parity across all four languages": **false.** See §5.

## 3. Setup
```bash
export ADMIN_LIBRARIES_105="/path/to/libraries_105"
```
Python modules are flat files in family folders; add each family folder you use to `sys.path`:
```python
for family in ("Core", "Standards", "Taxonomies", "Tax_Scaffolds"):
    sys.path.insert(0, str(Path(os.environ["ADMIN_LIBRARIES_105"]) / "Lib_PY" / family))
```
JS: `require(`${process.env.ADMIN_LIBRARIES_105}/Lib_JS/Core/lib_bejson_Core_bejson_core.js`)`. Bash: `source …/Lib_SH/Core/lib_bejson_Core_bejson_core.sh` (from a non-subshell). Never hard-code paths.

## 4. Always use the library — never reimplement
| Job | Python | JS | TS | Bash |
|---|---|---|---|---|
| Stale-safe file lock | `ResilientPIDLock(path, timeout_seconds)` | none | none | `resilient_lock_acquire/release` (basic) |
| Atomic write | `bejson_core_atomic_write` | temp+rename yourself | temp+rename yourself | `bejson_core_atomic_write` |
| Field lookup | `bejson_core_get_field_map(doc)[name]` | same | same | same |
| Add field (stamps `field_uuid`) | `bejson_core_define_field` | `bejson_core_add_field` | `defineField` | — |
| Add row | `bejson_core_add_record_105(doc, values)` | same | `addRecord105` | `mfdb_core_add_entity_record_105` |
| Bulk adds | `with bejson_core_transaction(doc):` | — | — | — |
| Verify 105 | `bejson_core_verify_105_integrity` | same | `verify105Integrity` | — |
| Full validate | `validate_bejson` | `validate_bejson` | `validateDocument` | `bejson_validator_validate_file` |
| 104→105 | `bejson_core_upgrade_to_105` / `_dry_run` | — | `upgradeTo105` (memory only) | — |
| MFDB CRUD (105) | `mfdb_core_add/update/delete_entity_record_105` | same | none | same |
| Logging | Standards `BEJSONLogHandler` | — | — | — |
| Env / paths | `source_env`, `get_env_path`, `bejson_safe_join` | — | — | `bec_core_source_env` |

If a task lands on `—`/`none`, tell the user and state the fallback. Do not fake it.

## 5. Language gaps to state plainly
- **JS/TS have no PID lock** → single-writer only. Route multi-writer work through Python.
- **Bash lock is basic** (no owner token) and needs `jq`.
- **TS has no MFDB entity-record CRUD**; **JS lacks `define_field`**; **JS/TS/Bash lack the 104→105 atomic upgrade tool**.
- `bejson_core_atomic_write` (Python) does not fsync the directory.

## 6. Hard rules for consumers
1. No positional indices; use the field map.
2. `record_uuid` is **implicit** in 105 rows. Never declare it in `Fields`; never pass it to `add_record_105`.
3. Never hand-write `field_uuid`.
4. No raw `open(..., "w")` on BEJSON files. Lock, then read-modify-write, then atomic write, all inside the lock.
5. Do not wrap `mfdb_core_*` calls in your own lock on the same entity file (they lock internally).
6. Manifest is `104a.mfdb.bejson`; entities are Format `105`; pass `mfdb_version="1.40"` (default is `"1.31"`).
7. Enable FK enforcement explicitly: `mfdb_core_enable_ref_integrity`. FK fields declare `fk_target_entity` and `fk_on_delete` (`restrict|cascade|null`).
8. Python logging via `logging` + Standards handler; no `print()`.
9. Pick error codes from free ranges only: **free = 190–199, 390–419, 520+** (520–579 reserved for Agent Core). Owned ranges: Core 1–99, Nesting 130–159, Extension 160–189, AI 200–249, Standards 250–269, Cognition 270–289, BEHTML 300–359, Terminal_Menus 360–389, Diagrams 420–449, Bookmaker 450–479, Lists 480–499, Graphics 500–519.
10. Env paths come from config/secure stores. Deprecated vars (`ADMIN_ROOT`, `BEJSON_STORAGE_ROOT`, `BEJSON_LIB_ROOT`) must not appear in new config.

## 7. If you are modifying this repo (only when asked)
- Core family is frozen; do not edit it without explicit permission. Apps own their internal libraries.
- Keep cross-language parity where the matrix says ✅; document any gap you create or close in `dev/change-log.md`.
- Every changed file: bump its `VERSION`, new `RELATIONAL_ID`, header with Name/Description/Date/Author. Surgical edits only; match existing style.
- Add or update a test in the family's `tests/` folder for every behavior change. Log adversarial findings in `dev/security-notes.md`.
- Do not claim a README example works until you have run it.

## 8. Test commands
```bash
python3 Lib_PY/Core/tests/test_mfdb_spec_levels_suite.py     # 30 tests
python3 Lib_PY/Standards/tests/test_standards.py
python3 Lib_PY/Taxonomies/tests/test_taxonomies.py
node    Lib_JS/Core/tests/test_mfdb_spec_levels_suite.js
node    Lib_JS/Core/tests/test_phase6_ref_integrity.js
npx tsc -p Lib_TS/tsconfig.json --noEmit
bash    Lib_SH/Core/tests/test_mfdb_spec_levels.sh
# added 2026-11-12
python3 Lib_PY/CMS/tests/test_cms_admin_security.py
python3 Lib_PY/Core/cli/CLI_Doc_Chunker/tests/test_flask_hardening.py   # needs flask; stubs lib_bejson_utility
```
TypeScript tests are compiled, not just type-checked: `cd Lib_TS/Core && tsc --target es2020 --module commonjs --moduleResolution node10 --skipLibCheck --strict --types node --outDir /tmp/ts_out index.ts tests/*.ts` (needs `@types/node`), then run each `/tmp/ts_out/tests/*.js` from inside `/tmp/ts_out/tests`.

Run the relevant suite before reporting a change complete. Last full run (2026-11-12, V5.9.5-PKG118, Python 3.13 / Node 22 / Bash 5 + jq / tsc 5): **50 of 50 test entry points exit 0** (Python 19, JS 10, Bash 9, TS strict compile + 9 compiled test files).

## 9. Gotchas
- `mfdb_core_add_entity_record_105`: **Python returns the entity doc** (new uuid = `doc["Values"][-1][0]`); **JS returns `{ record_uuid, doc }`**. Do not assume the Python shape in JS.
- `mfdb_core_load_entity` returns dicts; document-level functions use lists. Don't mix indexing styles.
- Validators return different shapes: result objects (`validate_*`, `.valid`), lists (`*_deep_verify`, `*_check_referential_integrity`, `*_check_105_*`; `[]` = clean), dict (`detect_schema_drift`; `{}` = none).
- `_bejson_field_map` is an in-memory cache; never persist or trust one from disk.
- Custom headers are allowed in `104a`/`105a`; `_`-prefixed header keys are reserved.

## 10. Before you finish
Run the checklist in `Libraries_105_Agent_Directive-V10101-PKG101.md` §11. Report any language gap or doc discrepancy you hit.

## 11. Governance & Self-Tracking Ledger Invariants (Added 2026-11-17)
- **Self-Tracking MFDB Ledger Synchronization:** Every package bump, new family registration, error code addition, or version anchor update MUST atomically update the `BEJSON/` self-tracking MFDB (`104a.mfdb.bejson`, `data/errors.bejson`, `data/families.bejson`, `data/metadata.bejson`, `data/library_changes.bejson`) and verify `validate_mfdb_database('BEJSON/104a.mfdb.bejson').valid == True`. Never ship a package with a stale `BEJSON/` ledger or duplicate EAV keys in `metadata.bejson`.
- **Cross-Language Core Error & Null Parity:** Core error codes (1–139) and CRUD exception numbers (such as `57 E_MFDB_CORE_DUPLICATE_ENTITY_NAME`) must remain identical across PY, JS, TS, and SH. Null values in typed cells must pass through `_coerceValue` as `null` without throwing `NaN` / `WRITE_TYPE_MISMATCH`.
- **Graphics SVG Palette Enforcement:** `svg_markup` cells in Graphics 105/105a documents must be scanned for embedded hex colors against `AUTHORIZED_PALETTE_HEX` (Policy §8.1 Tri-Color palette).

*Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton*

## Relocated from ~/.gemini/GEMINI.md (2026-11-17)

- **Test Schema Synchronization:** When changing canonical seed registries, defaults, or schemas in BEJSON/MFDB stores, update all test assertions and fixture baselines in the same atomic commit. Tests must not tolerate known assertion drift or magic numbers that diverge from the canonical seed. Skill: `bejson-enforcement-suite-builder`.
- **Metrics Destination:** Benchmarks, test suites, performance metrics, and dashboards for this library resolve their target from `$DEFINITIONS_FILE` (`$ADMIN_LIBRARIES_105`) at `<library root>/dev/metrics/`. No scratch folders outside the definitions tree for canonical deliveries. Updating metrics is an atomic in-place replacement: purge stale unindexed files and keep the series layout `test_series_1`, `test_series_2`, `test_series_3`, `index.html`. Skills: `file-hierarchy-manager`, `bejson-enforcement-suite-builder`.
