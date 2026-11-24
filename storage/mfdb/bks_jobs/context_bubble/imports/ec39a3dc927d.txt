# Libraries_105 Agent Directive — What To Use, Exactly
**Name:** Libraries_105 Agent Directive  
**Description:** Mandatory instructions for any AI agent that writes code against Elton Boehnen's `libraries_105` (BEJSON 105 / MFDB v1.40 ecosystem). Tells the agent which library feature to call for every common job, per language, and which documented examples are wrong.  
**Version:** `VERSION = 10101` (v1.0.1)  
**Date Created:** 2026-11-08  
**Author Credit:** Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton  
**RELATIONAL_ID:** `e03e4ea7-414e-4180-88ed-79ebc832d0f2`  
**Scope:** Python (`Lib_PY`), JavaScript (`Lib_JS`), TypeScript (`Lib_TS`), Bash (`Lib_SH`)  
**Verification:** Every Python recipe below was executed against the shipped library. JS and Bash recipes were spot-checked as noted. Anything marked **(unverified)** was read from source, not run.

---

## 0. How to Use This Document

You are an agent. Before you write any code that reads, writes, locks, validates, logs, or sandboxes BEJSON data:

1. Find the job in §3 (capability matrix) or §4–§8 (recipes).
2. Call the library function named there. **Do not write your own version.**
3. If the matrix says a language has a gap (❌ / ⚠️), say so to the user and use the stated fallback. Do not silently re-implement.
4. Run the checklist in §11 before you deliver.

**Source of truth order:** (1) the library source files, (2) this directive, (3) `clarification.md`, (4) `README.md`. The README is **not** reliable (see §1).

---

## 1. Known-Wrong Documentation (Do Not Copy)

These are in the shipped docs and are false. Agents that trust them produce code that crashes or invents APIs.

| Where | Claim | Reality |
|---|---|---|
| `README.md` (fixed in V5.9.5-PKG118; rows below describe the pre-fix text) Python quickstart | `from lib_bejson_Core_bejson_core_105 import bejson_core_105_parse_document, bejson_core_105_insert_record, bejson_core_105_get_field_map` | **No such module or functions in Python.** (`...core_105` exists only in TypeScript.) Use `bejson_core_load_file`, `bejson_core_add_record_105`, `bejson_core_get_field_map` from `lib_bejson_Core_bejson_core` |
| `README.md` JS quickstart | `bejson_core_parse_bejson(path)` | **Does not exist.** Read the file with `fs.readFileSync` + `JSON.parse`, then use `bejson_core_get_field_map` |
| `README.md` | `mfdb_validator_check_referential_integrity(...)` returns `{is_valid, errors}` | Python returns a **list** of findings; empty list = clean |
| `README.md` | Manifest named `105a.mfdb.bejson`; structural errors "E90–E95" | The manifest is always **`104a.mfdb.bejson`**. Codes 90–114 were **removed** (Core errors v2.9.0). There is no E90–E95 |
| `README.md` | "Exact functional parity across Python, JS, TS, Bash" | Not true. See §3: JS/TS have no PID lock; JS lacks `define_field`; TS has no MFDB record CRUD; Bash has no 105 doc-level CRUD |
| `BEJSON_Crash_Course_105-V3.md`, `GEMINI.md`, other prose | May describe behavior from earlier releases | Verify against source before relying on it |

If a doc and the source disagree, **the source wins** and you report the discrepancy.

---

## 2. Hard Rules (Never Violate)

1. **Never modify any file in `libraries_105`.** Core is frozen. Wrap it; do not patch it.
2. **Never reimplement** locking, atomic writes, field-map caching, validation, env parsing, path guarding, or logging. Use the library.
3. **Never use positional indices** (`row[3]`) or hardcoded offsets. Always `field_map[name]` from `bejson_core_get_field_map(doc)`.
4. **Never declare `record_uuid` as a Field in a 105/105a/105db document.** It is implicit (row index 0) and added for you. `bejson_core_add_record_105` takes values **without** it.
5. **Never hand-write `field_uuid` values.** Use `bejson_core_define_field` (or `mfdb_core_create_entity_file(..., format_version="105")`).
6. **Never write a BEJSON file with `open(path, "w")` / `fs.writeFileSync` / `>`.** Use `bejson_core_atomic_write` (PY, SH) or a temp-file + rename (JS/TS, §4).
7. **Never write a shared BEJSON file without a lock** where a lock exists (PY, SH). Read-modify-write goes **inside** the lock.
8. **Never name your MFDB manifest anything but `104a.mfdb.bejson`.** Entity files may be Format `105`; the manifest stays `104a`.
9. **Never use `print()` for logging in production Python.** Use `logging` + the Standards handler (§8.1).
10. **Never invent error codes in a range another family owns.** See §9.
11. **Never add a persisted `_bejson_field_map`** to files you write. It is an in-memory cache; the library strips and rebuilds it.
12. **Never hard-code filesystem paths.** Resolve through env/config (§2.1).

### 2.1 Setup & Imports (Verified)

Set `ADMIN_LIBRARIES_105` to the `libraries_105` root. In **Python the modules are flat files inside family folders**, so put each family folder you use on `sys.path` (the README's `PYTHONPATH=Lib_PY` alone is not enough):

```python
import os, sys
from pathlib import Path

LIBRARIES_105_ROOT = Path(os.environ["ADMIN_LIBRARIES_105"])        # or the project's local lib/ copy
for family_folder_name in ("Core", "Standards", "Taxonomies", "Tax_Scaffolds"):   # only what you use
    sys.path.insert(0, str(LIBRARIES_105_ROOT / "Lib_PY" / family_folder_name))

from lib_bejson_Core_bejson_core import (
    ResilientPIDLock, bejson_core_atomic_write, bejson_core_load_file,
    bejson_core_get_field_map, bejson_core_define_field, bejson_core_add_record_105,
    bejson_core_verify_105_integrity, bejson_core_transaction,
)
```

```javascript
// JS (Node >= 18)
const core = require(`${process.env.ADMIN_LIBRARIES_105}/Lib_JS/Core/lib_bejson_Core_bejson_core.js`);
const mfdb = require(`${process.env.ADMIN_LIBRARIES_105}/Lib_JS/Core/lib_bejson_Core_mfdb_core.js`);
```

```typescript
// TS (>= 5.0): import from the compiled/ts-path of Lib_TS/Core
import { parse, serialize } from "./Lib_TS/Core/lib_bejson_Core_bejson_core";
import { defineField, addRecord105, verify105Integrity } from "./Lib_TS/Core/lib_bejson_Core_bejson_core_105";
import { bejson_core_get_field_map } from "./Lib_TS/Core/lib_bejson_Core_bejson_field_map";
```

```bash
# Bash (>= 4.4). jq is REQUIRED and must be installed. Source from the file's own directory.
source "$ADMIN_LIBRARIES_105/Lib_SH/Core/lib_bejson_Core_bejson_core.sh"
source "$ADMIN_LIBRARIES_105/Lib_SH/Core/lib_bejson_Core_mfdb_core.sh"
```

Environment values (keys, paths) come from `source_env()` / `get_env_path()` (§8.4), not hard-coded literals.

---

## 3. Capability Matrix — "I Need To… → Call This"

✅ = use it · ⚠️ = partial/caveat · ❌ = not in that language (use the stated fallback)

| Need | Python | JavaScript | TypeScript | Bash |
|---|---|---|---|---|
| **Per-file process lock (stale-safe)** | ✅ `ResilientPIDLock(path, timeout_seconds)` | ❌ none; single-process synchronous only | ❌ none | ⚠️ `resilient_lock_acquire path [timeout]` / `resilient_lock_release path` (basic: no owner token; reclaim = `kill -0` then `rm -rf`) |
| **Atomic file write** | ✅ `bejson_core_atomic_write(path, doc)` | ⚠️ no public helper; temp file + `fs.renameSync` (§4.3) | ⚠️ none; temp + rename | ✅ `bejson_core_atomic_write` |
| **Load a BEJSON file** | ✅ `bejson_core_load_file(path)` (strips untrusted cache) | ⚠️ `JSON.parse(fs.readFileSync(...))` | ✅ `parse(text)` | ✅ `bejson_core_load_file` |
| **Field-map cache (O(1) by name)** | ✅ `bejson_core_get_field_map(doc)` | ✅ `bejson_core_get_field_map` | ✅ `bejson_core_get_field_map` / `_105` | ✅ `bejson_core_get_field_map` |
| **Create 104/104a/104db doc** | ✅ `bejson_core_create_104/104a/104db` | ❌ build the object, then validate | ✅ `createEmpty104/104a/104db` | ⚠️ build with `jq`, then validate |
| **Add field to 105 doc (stamps `field_uuid`)** | ✅ `bejson_core_define_field` (also `bejson_core_add_field`) | ⚠️ `bejson_core_add_field` only (no `define_field`) | ✅ `defineField` | ❌ |
| **Add row to 105 doc** | ✅ `bejson_core_add_record_105(doc, values)` → returns `record_uuid` | ✅ `bejson_core_add_record_105` → returns `record_uuid` | ✅ `addRecord105` | ❌ (use `mfdb_core_add_entity_record_105`) |
| **Bulk add (one cache rebuild)** | ✅ `with bejson_core_transaction(doc):` | ❌ | ❌ | ❌ |
| **Update one cell by uuid + field name** | ✅ `bejson_core_write_cell` | ✅ `bejson_core_write_cell` | ✅ `writeCell` | ❌ |
| **Delete row / remove field** | ✅ `bejson_core_delete_record`, `bejson_core_remove_field` | ✅ `bejson_core_delete_record` | ✅ `deleteRecord105`, `removeField` | ❌ |
| **Find row by uuid** | ✅ via `bejson_core_resolve_field_index` / loops over map | ✅ `bejson_core_find_row_by_uuid` | ✅ `getRecord` helpers | ❌ |
| **104 → 105 upgrade** | ✅ `bejson_core_upgrade_to_105`, `bejson_core_upgrade_dry_run`, CLI `cli/bejson_upgrade_cli.py` | ❌ | ⚠️ `upgradeTo105` (in-memory only, no backup/swap) | ❌ |
| **Verify 105 integrity** | ✅ `bejson_core_verify_105_integrity(doc)` → `{ok, field_count, record_count, errors}` | ✅ same name | ✅ `verify105Integrity` | ❌ |
| **Full validation** | ✅ `validate_bejson(doc_or_path)`, `bejson_validator_validate_file`, `bejson_validator_get_report` | ✅ `validate_bejson`, `bejson_validator_validate_file` | ✅ `validateDocument`, `assertValid`, `isValid` | ⚠️ `bejson_validator_validate_file` |
| **MFDB create database** | ✅ `mfdb_core_create_database` | ✅ `mfdb_core_create_database` | ⚠️ `createManifest`, `registerEntity` | ✅ `mfdb_core_create_database` |
| **MFDB 105 record CRUD (uuid-addressed, FK-checked)** | ✅ `mfdb_core_add/update/delete_entity_record_105` | ✅ same | ❌ no entity-record CRUD | ✅ same |
| **MFDB query / index / join** | ✅ `mfdb_core_query_entity`, `_build_index`, `_join` | ❌ | ❌ | ❌ |
| **MFDB referential integrity (restrict/cascade/null)** | ✅ `mfdb_core_enable_ref_integrity`, `check_entity_droppable`, `mfdb_validator_check_referential_integrity` | ✅ same family | ✅ `enableRefIntegrity`, `checkFKWrite`, `checkReferentialIntegrity` | ✅ same family |
| **MFDB verify / self-heal** | ✅ `mfdb_core_deep_verify`, `mfdb_core_self_heal`, `mfdb_core_smart_repair` | ✅ `deep_verify`, `self_heal` | ❌ | ❌ |
| **MFDB debug audit log (meta entity)** | ✅ `mfdb_core_enable_debug`, `get_debug_log`, `get_failed_ops`, `debug_summary` | ✅ (Node only) | ✅ `enableDebug`, `getDebugLog` | ✅ |
| **Schema drift detection** | ✅ `mfdb_core_detect_schema_drift` | ✅ | ✅ `detectSchemaDrift` | ✅ |
| **Federation (Master/Slave dropzone)** | ✅ `mfdb_federation_push_config/poll_dropzone/distill_logs`, `mfdb_core_create_connected_slave_entity` | ✅ | ✅ `federationPush…` | ✅ |
| **Nested BEJSON scan/query/mutate** | ✅ `bejson_nesting_*` | ✅ `bejsonNesting*` | ✅ `bejsonNesting*` | ✅ `bejson_nesting_*` |
| **Directory ⇄ chunk archive / MFDB-132 mount/commit** | ✅ `bejson_core_chunking_*`, `MFDB132Archive` | ✅ | ✅ | ✅ `mfdb132_archive_mount/commit/unmount` |
| **Env sourcing (safe parse, never exec)** | ✅ `source_env`, `get_env_path`, `source_env_fill` | ❌ | ❌ | ✅ `bec_core_source_env` |
| **Path-traversal guard / zip-slip-safe extract** | ✅ `bejson_safe_join`, `safe_extract_zip`, `resolve_storage_path` | ⚠️ `secure_zip_validate` | ❌ | ❌ |
| **Record encryption** | ❌ | ⚠️ crypto helpers internal; confirm before use **(unverified)** | ✅ `encryptRecord`, `decryptRecord` | ❌ |
| **Structured logging into BEJSON** | ✅ Standards (`BEJSONLogHandler`, §8.1) | ❌ | ❌ | ❌ |
| **Field naming / taxonomy governance** | ✅ Taxonomies (§8.2) | ❌ | ❌ | ❌ |
| **Scaffolding entities & deployments** | ✅ Tax_Scaffolds (§8.3) | ❌ | ❌ | ❌ |
| **SVG / canvas / animation / diagrams** | ✅ Graphics, Canvas (§8.6) | ✅ `Lib_JS/Graphics`, `Canvas` | ❌ | ❌ |

When a task needs a ❌ cell: **tell the user**, propose the Python tool or the stated fallback, and do not hand-roll a lookalike.

---

## 4. Locking & Atomic Writes — The Part Agents Keep Missing

### 4.1 Python: `ResilientPIDLock` (use it for every shared BEJSON write)
What it is: a mkdir-based lock directory `<path>.lockdir` containing `lock_meta.json` (`pid`, `timestamp`, `token`). It is **token-owned** (release removes only a lock you hold), **reclaims dead owners** safely under a guard directory, and checks liveness with `os.kill(pid, 0)`. It is already used inside every MFDB write in `mfdb_core`, in Taxonomies (`entity_lock`), and in Standards logging. You use it for **your own** BEJSON files:

```python
with ResilientPIDLock("data/notes.105.bejson", timeout_seconds=10):
    doc = bejson_core_load_file("data/notes.105.bejson")       # read INSIDE the lock
    field_map = bejson_core_get_field_map(doc)
    bejson_core_add_record_105(doc, ["title", 1])
    if not bejson_core_atomic_write("data/notes.105.bejson", doc):
        raise RuntimeError("atomic write failed")              # E_ATOMIC_WRITE_FAILED (15)
```
Lock failure raises `OSError` (maps to `E_MFDB_CORE_LOCK_FAILED`, 53).  
**Do not use** `bejson_core_acquire_lock` / `bejson_core_release_lock`: they are the older, simple `.lock` directory with no stale recovery.  
**Do not** call `MFDB`-level functions while *also* holding a lock on the same entity file; `mfdb_core_*` already locks internally (re-entrant acquisition would deadlock until timeout).

Known limits (do not claim otherwise): liveness is PID-existence only, so PID reuse can keep a dead owner's lock alive until its timeout rules apply; `bejson_core_atomic_write` does not fsync the directory and writes with default temp-file permissions.

### 4.2 Bash
```bash
resilient_lock_acquire "$target_file" 10 || { echo "lock timeout" >&2; exit 1; }
# ... read-modify-write ...
bejson_core_atomic_write "$target_file" "$new_content_json"   # 3rd arg "false" skips the automatic backup (default: backup on)
resilient_lock_release "$target_file"
```
This lock has no owner token; treat it as advisory and keep critical sections short. Requires `jq`.

### 4.3 JavaScript / TypeScript (no lock exists)
State plainly to the user: **JS/TS Core has no PID lock; safe only for a single writer process.** If multiple writers are possible, route writes through Python or add an external lock outside the library (and say so). For atomic replacement without a library helper:
```javascript
const fs = require("fs"), path = require("path");
function atomicReplace(filePath, text) {                     // temp file + rename in the same directory
  const tmp = path.join(path.dirname(filePath), `.${path.basename(filePath)}.tmp_${process.pid}`);
  const fd = fs.openSync(tmp, "w"); try { fs.writeSync(fd, text); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
  fs.renameSync(tmp, filePath);
}
```
(Same-directory rename is what `mfdb_core` does internally; its `_atomicWrite` is private.)

---

## 5. Creating, Reading & Writing 105 Documents

### 5.1 Python (verified)
```python
doc = {"Format": "BEJSON", "Format_Version": "105", "Format_Creator": "Elton Boehnen",
       "Records_Type": ["Note"], "Fields": [], "Values": []}
bejson_core_define_field(doc, "note_title", "string")        # stamps field_uuid
bejson_core_define_field(doc, "note_count", "integer")
with bejson_core_transaction(doc):                           # one cache rebuild for the whole batch
    for index in range(3):
        bejson_core_add_record_105(doc, [f"t{index}", index])    # NO record_uuid in values
assert bejson_core_verify_105_integrity(doc)["ok"]

field_map = bejson_core_get_field_map(doc)                   # name -> absolute row index
for row in doc["Values"]:
    title = row[field_map["note_title"]]                     # row[0] is the implicit record_uuid
```
Format options: `105` (data), `105a` (adds custom non-underscore headers), `105db` (multi-entity). `_`-prefixed header keys are reserved and must never be written to disk.

### 5.2 JavaScript (verified)
```javascript
const doc = { Format: "BEJSON", Format_Version: "105", Format_Creator: "Elton Boehnen",
  Records_Type: ["N"], Fields: [{ name: "n_title", type: "string", field_uuid: crypto.randomUUID() }], Values: [] };
const recordUuid = core.bejson_core_add_record_105(doc, ["x"]);          // returns the uuid string
const fieldMap = core.bejson_core_get_field_map(doc);                     // { n_title: 1 }
core.bejson_core_verify_105_integrity(doc);                               // { ok, field_count, record_count, errors }
```
(JS has no `define_field`; generate `field_uuid` yourself with `crypto.randomUUID()` or call `bejson_core_add_field`.)

### 5.3 TypeScript **(unverified)**
`defineField(doc, name, type, opts)` → `addRecord105(doc, values)` → `verify105Integrity(doc)`. Types live in `lib_bejson_Core_bejson_types.ts`.

### 5.4 Upgrading 104 → 105 (Python, atomic with backup)
```python
report = bejson_core_upgrade_dry_run(doc_104, "data/orders.bejson")      # never touches disk
upgraded = bejson_core_upgrade_to_105(doc_104, "data/orders.bejson")     # backs up to Backups/<name>.104.bak, atomic swap
```
CLI: `python3 Lib_PY/Core/cli/bejson_upgrade_cli.py --dry-run <file>`. On failed validation the original is untouched.

---

## 6. MFDB v1.40 (Multi-File Database)

### 6.1 Python (verified end to end)
```python
manifest_path = mfdb_core_create_database(
    "db", "OrdersDB",
    [{"name": "Customer", "file_path": "data/customer.bejson", "primary_key": "record_uuid",
      "format_version": "105", "fields": [{"name": "cust_name", "type": "string"}]},
     {"name": "Order", "file_path": "data/order.bejson", "primary_key": "record_uuid",
      "format_version": "105",
      "fields": [{"name": "order_customer_fk", "type": "string",
                  "fk_target_entity": "Customer", "fk_on_delete": "cascade"},   # restrict | cascade | null
                 {"name": "order_total", "type": "integer"}]}],
    mfdb_version="1.40")                                      # writes db/104a.mfdb.bejson

entity_doc = mfdb_core_add_entity_record_105(manifest_path, "Customer", ["Ann"])
customer_uuid = entity_doc["Values"][-1][0]                    # GOTCHA: it returns the ENTITY DOC, not the uuid
mfdb_core_enable_ref_integrity(manifest_path)
mfdb_core_add_entity_record_105(manifest_path, "Order", [customer_uuid, 5])   # unresolvable FK raises, nothing written
mfdb_core_update_entity_record_105(manifest_path, "Order", order_uuid, "order_total", 9)
mfdb_core_delete_entity_record_105(manifest_path, "Customer", customer_uuid)  # cascades per fk_on_delete, two-phase, rollback on failure

rows = mfdb_core_load_entity(manifest_path, "Customer")        # list of dicts incl. "record_uuid"
verdict = validate_mfdb_database(manifest_path, strict_fk=True)   # object: .valid / .errors / .warnings
findings = mfdb_validator_check_referential_integrity(manifest_path)   # LIST; [] == clean
problems = mfdb_core_deep_verify(manifest_path)                # LIST; [] == clean
drift = mfdb_core_detect_schema_drift(manifest_path)           # DICT; {} == none
```
Rules:
- Use the `*_105` functions for 105 entities; the non-105 CRUD functions are for 104 entities.
- `mfdb_core_*` functions lock internally. Do not wrap them in your own lock on the same entity file.
- Maintenance menu: `mfdb_core_sync_all_counts`, `mfdb_core_self_heal`, `mfdb_core_smart_repair`, `mfdb_core_check_entity_droppable` (before dropping an entity), `mfdb_core_enable_debug` (meta-GUID audit entity; read with `mfdb_core_get_failed_ops`).
- Shared logic in ingestion: `mfdb_core_query_entity(manifest, entity, predicate)`, `mfdb_core_build_index`, `mfdb_core_join` (Python only).

### 6.2 JavaScript
`mfdb_core_create_database`, `mfdb_core_load_entity`, `mfdb_core_add/update/delete_entity_record_105`, ref-integrity enable/check, `mfdb_core_deep_verify`, `mfdb_core_self_heal`, federation and debug functions exist (names in §3). **Single-process only (no lock).** Delete is two-phase with byte-for-byte rollback.

### 6.3 TypeScript
`createManifest`, `registerEntity`, `unregisterEntity`, `syncRecordCount`, ref-integrity checks, federation, debug, drift. **There is no entity-record CRUD in TS**; use Python/JS/Bash for record writes.

### 6.4 Bash
`mfdb_core_create_database`, `mfdb_core_add/remove_entity_record`, `mfdb_core_add/update/delete_entity_record_105`, ref integrity, federation, debug, `mfdb_validator_validate_*`. Requires `jq`.

---

## 7. Validation (Run It Before Delivering Any Data File)

| Task | Python | JS | TS | Bash |
|---|---|---|---|---|
| Validate a BEJSON file/doc | `validate_bejson(doc_or_path)` → `ValidationResult`; `bejson_validator_get_report(...)` for text | `validate_bejson(doc)` / `bejson_validator_validate_file(path)` | `validateDocument(doc)` | `bejson_validator_validate_file path` |
| 105 strict integrity | `bejson_validator_check_105_strict_integrity(doc)` → list | `bejson_validator_check_105_strict_integrity` | `check105StrictIntegrity` | — |
| MFDB manifest / entity / database | `validate_mfdb_manifest`, `validate_mfdb_entity_file`, `validate_mfdb_database(path, strict_fk=True)` | `validate_mfdb_*` | `validateManifest`, `validateEntityFile`, `validateDatabase` | `mfdb_validator_validate_*` |
| Schema infer / validate against schema | `bejson_schema_extract`, `bejson_schema_validate_against(_detailed)`, `bejson_schema_infer_from_data` | — | `BEJSONSchema` | `bejson_schema_*` |

---

## 8. Other Python Families (Use Before Building Your Own)

### 8.1 Standards — Structured Logging (Python only) — **use this instead of ad-hoc logs**
Writes log rows into BEJSON 104a (schema v3) with row cap, period archives, secure-path routing, filtered export, and a standard `logging` handler. Verified:
```python
from lib_bejson_Standards_registry import (bejson_standards_configure_sink, BEJSONLogHandler,
    bejson_standards_read_logs, bejson_standards_export_logs, bejson_standards_flush,
    bejson_standards_audit_log_file)

bejson_standards_configure_sink("logs/app.104a.bejson", row_cap=10000, min_level="INFO")
logger = logging.getLogger("myapp"); logger.setLevel(logging.INFO)
logger.addHandler(BEJSONLogHandler("logs/app.104a.bejson", subsystem="myapp"))
logger.info("started", extra={"event_key": "app.start"})        # per-record extras: event_key, error_code, category, flags, actor, session, secure…
bejson_standards_flush("logs/app.104a.bejson")
bejson_standards_audit_log_file("logs/app.104a.bejson")["passed"]   # True
```
Exports: `bejson_standards_export_logs(path, "json"|"ndjson"|"markdown"|"html", dest)`. Stateful context (`bejson_standards_set_context`) sets subsystem/actor/session once. Redact secrets **before** logging (attach your own `logging.Filter`); the sink does not redact.

### 8.2 Taxonomies — Field-Naming Governance
`bejson_taxonomies_create_taxonomy`, `_check_field_name`, `_build_field_definition`, `_audit_database`, field-UUID ledger (`_resolve_field_uuid`, `_record_rename`, `_retire_field`), reusable field sets (`_define_field_set`, `_new_version`, `_export_field_set`). Use it when a project has a naming standard; do not hand-roll prefix/suffix checks.

### 8.3 Tax_Scaffolds — Entity & Deployment Scaffolding
`bejson_tax_scaffolds_scaffold_entity(ies)`, `_graft_field_set`, `_deploy_master_rebuild` / `_deploy_slave_rebuild`, `_capture_snapshot` + `_deploy_*_prebuilt`, `_create_federation_link` / `_bind_federation_link`, `bejson_tax_scaffolds_core_all_or_nothing(manifest)` (transaction wrapper), `bejson_tax_scaffolds_validator_audit_gate`. Use for multi-entity builds.

### 8.4 Environment & Paths
- `source_env()` parses env files as **data** (never `exec`). JSON (flat object or BEJSON `Values`) or `NAME = literal` lines; names must be UPPER_SNAKE.
- `get_env_path(env_var, default)`, `source_env_fill(...)`.
- `resolve_path(...)` still honors legacy variables (`ADMIN_ROOT`, `BEJSON_STORAGE_ROOT`, `BEJSON_LIB_ROOT`). The owner's current policy lists those as **deprecated**; do not introduce them in new config.
- `bejson_safe_join(base, *parts)` raises `ValueError` on traversal (verified). `safe_extract_zip(zf, dest)` for archives. Use them for every user/agent-supplied path.

### 8.5 Other Core Modules
| Module | Use for |
|---|---|
| `bejson_nesting_scan/query/mutate/flatten/get_path` | Hierarchical/embedded BEJSON (all four languages) |
| `bejson_core_chunking_*`, `MFDB132Archive` | Packaging a directory or MFDB as one document; mount/commit workflows |
| `parse_bejson_104db_doc`, `unpack_bejson_104db_to_dir` | 104db parsing/unpacking |
| `lib_bejson_Core_bejson_parse.py` (`parse_json`, `extract_data`, `save_files`) | Extracting BEJSON from model/LLM text output |
| `BEJSONState` | **Single 104db-file** application state with history (not MFDB); mirrors the JS class |
| `BEJSONProvider`, `BEJSONBackend` | Pad-style paths/index schemas and file backend; their default root is the `{ADMIN_ROOT}` placeholder, so pass an explicit root |

### 8.6 Presentation Families
`Lib_PY/Graphics` (isometric cube SVG, branded slides, row-per-frame animation, GIF/WebM/APNG/MP4 compilation, diagram loader), `Lib_PY/Canvas` (canvas config/frame-sequence 105a docs, HTML templates), `Lib_PY/CMS` (MTV scaffold/validator). Use them instead of rewriting renderers. They enforce the brand palette (white/black/`#DE2626`).

---

## 9. Error-Code Ownership (Do Not Collide)

Ranges claimed across the ecosystem (from the library's own registries):

| Range | Owner |
|---|---|
| 1–99 | Core (incl. 80 `E_FIELD_INTEGRITY_MISMATCH`, 81 `E_FORMAT_UNSUPPORTED`, 82 `E_RECORD_NOT_FOUND`, 84 `E_DUPLICATE_FIELD_NAME`, 85 `E_DUPLICATE_FIELD_UUID`; MFDB 38–72, FK 39/43–47, lock 53) |
| 90–114 | **Removed** (old 105 schema constraints). Not in use |
| 130–159 | Core Nesting |
| 160–189 | Core Extension |
| 200–235 | AI |
| 250–269 | Standards (250–261 assigned) |
| 270–289 | Cognition |
| 300–329 | BEHTML |
| 330–359 | BEHTML_IDE |
| 360–389 | Terminal_Menus |
| 420–449 | Diagrams |
| 450–479 | Bookmaker |
| 480–499 | Lists |
| 500–519 | Graphics |
| **Free to claim** | 190–199, 236–249, 390–419, **520+** |
| **Reserved by the Modern Agent Design** | **520–579** (Agent Core) |

Process exit codes (owner policy): `0` ok · `10` path-picker failure · `20` environment sourcing failure · `30` schema/field-map validation failure.

---

## 10. Gotchas That Cause Real Bugs

1. **`mfdb_core_add_entity_record_105` returns the entity doc in Python** (take `doc["Values"][-1][0]`) **but `{ record_uuid, doc }` in JavaScript**. Neither returns the bare uuid. (Verified by running both, 2026-11-12.)
2. **`bejson_core_get_field_map` indexes include the implicit `record_uuid` offset** in 105 docs (first declared field is index 1 in the row). Never mix with a manual `Fields` index.
3. **`mfdb_core_load_entity` returns dicts** (keyed by field name, plus `record_uuid`); the document functions return lists. Do not index one like the other.
4. **Validators differ in return type:** `validate_*` return result objects; `*_check_referential_integrity`, `*_deep_verify`, `*_check_105_*` return lists; drift returns a dict. Check `== []`/`{}` or `.valid` accordingly.
5. **FK declaration** lives on the field: `fk_target_entity` and `fk_on_delete`. Enable enforcement with `mfdb_core_enable_ref_integrity`; it is off by default.
6. **`_bejson_field_map` is cache only.** It is rebuilt automatically; never persist it and never trust one found in a file.
7. **Bulk writes:** wrap in `bejson_core_transaction(doc)`; otherwise the cache rebuilds per row.
8. **Locks are per-file.** Lock the exact file you write; load it **after** taking the lock.
9. **JS/TS: no lock; Bash: basic lock; Python: resilient lock.** State which you used.
10. **Bash needs `jq`.** If it is missing, say so; do not substitute `sed`/`awk` JSON handling.
11. **README examples are wrong** (§1). Never paste them.
12. **Default `mfdb_version` in `mfdb_core_create_database` is `"1.31"`.** Pass `mfdb_version="1.40"` for the current spec.

---

## 11. Pre-Delivery Checklist (Run Every Time)

- [ ] No file inside `libraries_105` was changed.
- [ ] No custom lock, atomic writer, field-map cache, env parser, path guard, or logger was written where §3 lists a library function.
- [ ] No positional indices; every access goes through `field_map[...]`.
- [ ] No `record_uuid` in `Fields`; no hand-typed `field_uuid`.
- [ ] Every shared write is inside `ResilientPIDLock` (PY) / `resilient_lock_acquire` (SH), or the single-writer limitation is stated (JS/TS).
- [ ] Manifest is `104a.mfdb.bejson`; `mfdb_version="1.40"`; entity files are Format `105`.
- [ ] Output files pass `validate_bejson` / `bejson_core_verify_105_integrity`; MFDBs pass `validate_mfdb_database(..., strict_fk=True)` with `[]` from `mfdb_core_deep_verify`.
- [ ] New error codes come from a free range (§9), not another family's.
- [ ] Logging uses `logging` (+ Standards handler); no `print()`.
- [ ] Paths come from config/env and pass `bejson_safe_join` where user-supplied.
- [ ] Every ❌/⚠️ cell you hit was reported to the user with the fallback you chose.
- [ ] File headers carry Name, Description, `VERSION`, Date, Author credit, and a fresh `RELATIONAL_ID`.

*Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton*
