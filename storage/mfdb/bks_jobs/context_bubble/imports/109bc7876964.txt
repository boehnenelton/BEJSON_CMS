# BEJSON + MFDB Crash Course — 105 Edition

**Document Version:** 105-V1 (written against the parity-patched Core) · **BEJSON Formats:** 105 · 105a · 105db (104-series carried over) · **MFDB Spec:** 1.40 (Ref_Integrity) · **Chunk Packaging:** 1.32
**Format Creator:** Elton Boehnen · [https://boehnenelton2024.pages.dev](https://boehnenelton2024.pages.dev)
**Date:** 2026-10-24

> **How this document was made.** Every rule below was checked against the real `libraries_105` Python Core (`Lib_PY/Core`) by running it, not by copying the older 104-era course. The first pass found that 105 skipped many checks 104 performs. The Core was then patched (the **105↔104 parity patch**: validator 3.4.0, core 3.6.0, upgrade 1.1.0, mfdb_core 3.1.0, mfdb_validator 2.4.0) and this document describes the **patched** behaviour. The bottom section, **Part 4: Reality Audit**, records what was wrong, what the patch fixed, and what is still open.
>
> **Scope.** Python is the reference implementation described in Parts 1–3. As of this edition JavaScript, TypeScript and Shell Core (both `libraries_104` and `libraries_105`) enforce the same validation rules; Part 4.7 lists what each language does and does not cover. The `Taxonomies` and `Tax_Scaffolds` families are out of scope.

**Legend**

| Mark | Meaning |
| :---: | :--- |
| ✅ | Enforced by the library code (a validator or a write function rejects the violation) |
| ⚠️ | Convention only (the code does not stop you) |
| ❌ | Documented or expected, but the code does not check it |

**Versions verified:** `bejson_core` 3.6.0 · `bejson_validator` 3.4.0 · `bejson_upgrade` 1.1.0 · `mfdb_core` 3.1.0 · `mfdb_validator` 2.4.0 · `bejson_chunking` 1.9.1 · `bejson_core_nesting` 0.6.0 · `bejson_errors` 2.9.0. All Core suites pass (91 + 36 + 9 + 29 + 9 + 8 + 14 + 23 + 7 shipped, plus 30 parity tests in `tests/test_105_104_parity_suite.py` and 24 MFDB spec-level tests in `tests/test_mfdb_spec_levels_suite.py`, run for both 104 and 105 databases).

---

## PART 1: BEJSON 105 CRASH COURSE
**(105, 105a, 105db)**

BEJSON 105 is BEJSON 104 plus **identity**. The data layout is still positional (`Fields` order = `Values` order), but now every column and every row carries a UUID:

| 104-series | 105-series adds |
| :--- | :--- |
| Column = `{name, type}` | Column also has a **`field_uuid`** (UUIDv4). It survives renames and reordering. |
| Row = one value per field | Row also has a **`record_uuid`** (UUIDv4) in a **reserved leading column** that `Fields` does not describe. |
| Find a column by name or position | Find a column by name **or** by `field_uuid`; write a cell by `(record_uuid, field_uuid)`. |
| Foreign keys are only a naming convention | A field can **declare** a foreign key (`fk_target_entity`, `fk_on_delete`) that MFDB enforces. |

Everything else (six mandatory keys, `Format_Creator`, the six types, `null` rules, unique field names) is the same as 104.

---

### 1.1 Mandatory keys

```json
{
  "Format": "BEJSON",
  "Format_Version": "105",
  "Format_Creator": "Elton Boehnen",
  "Records_Type": ["SensorReading"],
  "Fields": [ ... ],
  "Values": [ ... ]
}
```

* `Format_Version` is one of `"105"`, `"105a"`, `"105db"` (the validator also still accepts the three 104 values). ✅
* `Format_Creator` must be exactly `"Elton Boehnen"`. ✅
* `Parent_Hierarchy` is the only built-in extra key allowed on `105`/`105db` (used by MFDB entity files). ✅
* Any other top-level key starting with `_` is rejected (reserved for in-memory runtime data such as the field-map cache). ✅

### 1.2 The Field object

```json
{"name": "reading_c", "type": "number", "field_uuid": "a1b2c3d4-0003-4000-8000-000000000003"}
```

* `name` (string) and `type` are required. ✅ Names must be unique within the document. ✅
* `type` must be exactly one of **`string`, `integer`, `number`, `boolean`, `array`, `object`** (lowercase). ✅ There is no `timestamp`, `date` or `uuid` type: store those as `string` (ISO-8601 for time) and express the meaning in the field name, for example `created_timestamp`.
* `field_uuid` must be present on every field and **unique** in the document. ✅
* Optional foreign-key metadata (Part 2.4): `fk_target_entity`, `fk_on_delete` (`restrict` · `cascade` · `null`).
* In `105db` every field except `Record_Type_Parent` also carries `"Record_Type_Parent": "<EntityName>"`. ✅ (the validator rejects a field with no owner).
* Add new fields **only at the end**. Core's `define_field`/`add_field` do this and pad every existing row with `null`.

### 1.3 Row layout and offsets (the one thing you must know)

A `105`/`105a` row has **one more cell than `Fields`**: `record_uuid` is column 0 and every field shifts right by one. A `105db` row keeps the discriminator in column 0 and puts `record_uuid` in column 1.

| Format | Row layout | Row length | `Fields[i]` is at row column |
| :--- | :--- | :---: | :--- |
| 104 / 104a / 104db | `[v0, v1, v2, ...]` | `len(Fields)` | `i` |
| **105 / 105a** | `[record_uuid, v0, v1, v2, ...]` | `len(Fields)+1` | `i + 1` |
| **105db** | `[Record_Type_Parent, record_uuid, v1, v2, ...]` | `len(Fields)+1` | `0` for `i = 0`, otherwise `i + 1` |

Do not do this arithmetic by hand. `bejson_core_get_field_map(doc)` returns **row positions** on every format version:

```python
bejson_core_get_field_map(doc_104)   # {'sensor_id': 0, 'temp': 1}
bejson_core_get_field_map(doc_105)   # {'sensor_id': 1, 'temp': 2}   <- row[idx] is already correct
```

`bejson_core_resolve_field_index(doc, target)` returns the absolute row column for a field given as a name, a `field_uuid`, or `{"name": ..., "field_uuid": ...}` (both must agree, otherwise `E_FIELD_INTEGRITY_MISMATCH`, code 80). It works on 105-series documents only (`E_FORMAT_UNSUPPORTED`, code 81, on a 104 document).

---

### 1.4 The three 105 formats

#### BEJSON 105 — single record type, all six types

```json
{
  "Format": "BEJSON",
  "Format_Version": "105",
  "Format_Creator": "Elton Boehnen",
  "Records_Type": ["SensorReading"],
  "Fields": [
    {"name": "sensor_id",   "type": "string", "field_uuid": "a1b2c3d4-0001-4000-8000-000000000001"},
    {"name": "recorded_at", "type": "string", "field_uuid": "a1b2c3d4-0002-4000-8000-000000000002"},
    {"name": "reading_c",   "type": "number", "field_uuid": "a1b2c3d4-0003-4000-8000-000000000003"},
    {"name": "tags",        "type": "array",  "field_uuid": "a1b2c3d4-0004-4000-8000-000000000004"}
  ],
  "Values": [
    ["9f8e7d6c-0001-4000-8000-000000000001", "S001", "2026-10-24T12:00:00Z", 23.5, ["indoor", "ground"]],
    ["9f8e7d6c-0002-4000-8000-000000000002", "S002", "2026-10-24T12:00:00Z", 19.8, null]
  ]
}
```

* Custom top-level headers are forbidden (only `Parent_Hierarchy`). ✅
* Primary use: MFDB entity files, logs, any homogeneous table.

#### BEJSON 105a — metadata and configuration

```json
{
  "Format": "BEJSON",
  "Format_Version": "105a",
  "Format_Creator": "Elton Boehnen",
  "Server_ID": "WEB-01",
  "Environment": "Production",
  "Retention_Days": 90,
  "Records_Type": ["ConfigParam"],
  "Fields": [
    {"name": "key",       "type": "string",  "field_uuid": "c0000000-0001-4000-8000-000000000001"},
    {"name": "value",     "type": "string",  "field_uuid": "c0000000-0002-4000-8000-000000000002"},
    {"name": "sensitive", "type": "boolean", "field_uuid": "c0000000-0003-4000-8000-000000000003"}
  ],
  "Values": [
    ["d0000000-0001-4000-8000-000000000001", "db_host", "prod-db-01", true],
    ["d0000000-0002-4000-8000-000000000002", "max_threads", "32", false]
  ]
}
```

* Custom top-level headers are allowed (file-level metadata only, `PascalCase`). ✅
* Primitive-only like 104a (`string`, `integer`, `number`, `boolean`): `array`/`object` fields are rejected. ✅
* **MFDB manifests stay `104a`.** A manifest is rejected if it is `105a` (Part 2.1).

#### BEJSON 105db — multi-entity in one file

```json
{
  "Format": "BEJSON",
  "Format_Version": "105db",
  "Format_Creator": "Elton Boehnen",
  "Records_Type": ["Department", "Employee"],
  "Fields": [
    {"name": "Record_Type_Parent", "type": "string", "field_uuid": "d0000000-0000-4000-8000-000000000000"},
    {"name": "dept_name", "type": "string", "Record_Type_Parent": "Department", "field_uuid": "d0000000-0000-4000-8000-000000000001"},
    {"name": "emp_name",  "type": "string", "Record_Type_Parent": "Employee",   "field_uuid": "d0000000-0000-4000-8000-000000000002"}
  ],
  "Values": [
    ["Department", "e1111111-0000-4000-8000-000000000001", "Engineering", null],
    ["Employee",   "e1111111-0000-4000-8000-000000000002", null, "Alice Vance"]
  ]
}
```

* Rules as 104db, plus the 105 layout: discriminator at column 0, `record_uuid` at column 1.
* The validator applies the 104db rules plus the 105 layout: first field is `Record_Type_Parent`, every other field names its owner, `Records_Type` has 2+ entries, each row's discriminator (column 0) is in `Records_Type`, and `record_uuid` sits at column 1. ✅
* `bejson_core_remove_field` refuses to remove `Record_Type_Parent` (`E_FIELD_INTEGRITY_MISMATCH`).
* Same size warning as 104db: padding makes the file grow quickly. For anything larger than a small single-file dataset, use MFDB (Part 2).

---

### 1.5 What `validate_bejson` actually enforces on 105-series

| Check | 104-series | 105-series |
| :--- | :---: | :---: |
| Valid JSON, six mandatory keys, `Format_Creator` | ✅ | ✅ |
| `Format_Version` in the allowed list | ✅ | ✅ |
| Custom-header rules (104/104db/105/105db forbid; 104a/105a allow) | ✅ | ✅ |
| `_`-prefixed keys rejected; persisted `_bejson_field_map` rejected | ✅ | ✅ |
| `Fields` entries have `name` + `type`; type is one of the six | ✅ | ✅ |
| Field names unique | ✅ | ✅ |
| **`field_uuid` present and unique on every field** | n/a | ✅ |
| **`record_uuid` present (non-empty string) and unique, at the right column** | n/a | ✅ |
| Fail-on-Switch: a 104 file re-headered to 105 without UUIDs fails | n/a | ✅ |
| `field_uuid` / `record_uuid` are valid UUIDv4 strings | n/a | ⚠️ warning only (`result.warnings`), never an error |
| **Row length** equals expected (`len(Fields)+1`) | ✅ (`E_RECORD_LENGTH_MISMATCH`, 9) | ✅ |
| **Value type** matches field type (offset-aware, bool excluded from integer/number) | ✅ (`E_TYPE_MISMATCH`, 8) | ✅ |
| `Records_Type` count (1 / 1 / 2+) | ✅ | ✅ (`105`, `105a`: exactly 1; `105db`: 2+) |
| 104a/105a primitives only | ✅ (104a) | ✅ (105a) |
| 104db/105db discriminator rules | ✅ (104db) | ✅ (105db) |

For 105-series the row/type findings are all reported (up to 100, then a "suppressed" note); 104 stops at the first. Row and type errors appear as `[E_RECORD_LENGTH_MISMATCH] ...` / `[E_TYPE_MISMATCH] ...` strings in `ValidationResult.errors`.

---

### 1.6 Creating 105 data

There is **no** `bejson_core_create_105()`. The three supported ways are:

1. **Upgrade an existing 104-series document** (Section 1.8).
2. **Create it inside an MFDB:** `mfdb_core_create_database(..., entities=[{"name": ..., "fields": [...], "format_version": "105"}])` stamps a fresh `field_uuid` on every field and writes an empty `Values` (Part 2).
3. **Build it by hand/script.** Generate every UUID with `uuid.uuid4()`; put `Format_Version` last, then validate.

### 1.7 Working with a 105 document (Python)

```python
from lib_bejson_Core_bejson_core import (
    bejson_core_load_file, bejson_core_atomic_write, bejson_core_get_field_map,
    bejson_core_define_field, bejson_core_add_record_105, bejson_core_write_cell,
    bejson_core_delete_record, bejson_core_remove_field, bejson_core_resolve_field_index,
    bejson_core_verify_105_integrity, bejson_core_transaction)

doc = bejson_core_load_file("sensors.bejson")      # 105 docs come back with the field map already built
fm  = bejson_core_get_field_map(doc)               # {'sensor_id': 1, 'temp': 2}  (row positions)
temp = doc["Values"][0][fm["temp"]]                # 23.5

note_uuid = bejson_core_define_field(doc, "note", "string")      # appends a column, pads every row with null, returns its field_uuid
rec_uuid  = bejson_core_add_record_105(doc, ["S3", 1.5, "hi"])   # values WITHOUT record_uuid, in Fields order; returns the new record_uuid
bejson_core_write_cell(doc, rec_uuid, note_uuid, "updated")       # address a cell by (record_uuid, field_uuid)
bejson_core_delete_record(doc, rec_uuid)                          # delete by record_uuid
bejson_core_remove_field(doc, "note")                              # remove by name or field_uuid; never by index

with bejson_core_transaction(doc):                 # one cache rebuild for the whole batch
    for row in csv_rows:
        bejson_core_add_record_105(doc, row)

report = bejson_core_verify_105_integrity(doc)     # read-only; {'ok': True, 'field_count': 3, 'record_count': 2, 'errors': []}
bejson_core_atomic_write("sensors.bejson", doc)    # temp file + fsync + os.replace; runtime '_' keys are stripped
```

What each call really guarantees:

| Function | Guarantees | Does **not** guarantee |
| :--- | :--- | :--- |
| `define_field(doc, name, type, *, fk_target_entity, fk_on_delete)` | Type is one of the six; name is new; FK args valid; new `field_uuid`; rows padded | n/a (checks eagerly, writes nothing on failure) |
| `add_field(doc, name, type)` | Type must be one of the six; duplicate name rejected (`E_DUPLICATE_FIELD_NAME`, 84); new `field_uuid`; rows padded | n/a |
| `add_record_105(doc, values)` | `len(values) == len(Fields)` (code 9) and every value matches its type (code 8), checked **before** anything is written; for `105db` the discriminator must be in `Records_Type`; new `record_uuid` in the right column | n/a |
| `write_cell(doc, record_uuid, field_uuid, value)` | Finds the cell by UUIDs; value type checked (code 8); heals stale `expected_row/expected_col` hints | n/a |
| `remove_field` / `delete_record` | By UUID or name, never by index | Assumes the document is valid; run `validate_bejson` first on files from outside |
| `verify_105_integrity(doc)` | UUID checks **plus** row length and value types (same function the validator uses) | n/a |

Do not mix in the 104 mutators on 105 data:

* `bejson_core_add_record(doc, row)` is 104-only and now **raises** `E_FORMAT_UNSUPPORTED` (81) on a 105-series document (it used to append a row with no `record_uuid`). Use `add_record_105`.
* `bejson_core_update_field`, `filter_rows` and `sort_by_field` do work on 105 because they go through `get_field_index`, which returns row positions.

Serialization: `bejson_core_serialize(doc)` and `atomic_write` drop every key beginning with `_` or `*`, including `_bejson_field_map`.

### 1.8 Upgrading 104 → 105

```python
from lib_bejson_Core_bejson_upgrade import bejson_core_upgrade_to_105, bejson_core_upgrade_dry_run

report = bejson_core_upgrade_dry_run(doc, "sensors.bejson")   # no disk writes
# {'field_count', 'record_count', 'validation_pass', 'errors', 'source_path', 'target_version'}

new_doc = bejson_core_upgrade_to_105(doc, "sensors.bejson")   # backs up, validates, swaps atomically
```

* Mapping: `104 → 105`, `104a → 105a`, `104db → 105db`. Custom 104a headers are preserved.
* Every field gets a new `field_uuid`; every row gets a new `record_uuid` in the right column (column 0, or column 1 for `105db` after the discriminator).
* The original file is first copied byte-for-byte to `Backups/<filename>.104.bak` (a `Backups/` folder next to the source). Rollback is a plain file copy.
* The upgraded document is validated with the 105 strict-integrity check **before** anything is written; on failure the original is untouched (`E_UPGRADE_VALIDATION_FAILED`, 83).
* Upgrading a 105-series document raises `E_FORMAT_UNSUPPORTED` (81). You cannot upgrade twice.
* ✅ The upgrade **validates the 104 source first** (full `validate_bejson`): a source with a short row, a mistyped cell, a wrong `Records_Type` count or a complex type in 104a raises `E_UPGRADE_VALIDATION_FAILED` (83) before any backup or write. `upgrade_dry_run` reports the same problems in `errors` with `validation_pass: False`.
* CLI: `Lib_PY/Core/cli/bejson_upgrade_cli.py` (with `--dry-run`).
* Do not hand-edit `Format_Version` to `105`. The Fail-on-Switch check in the validator rejects a re-headered file that has no `field_uuid` values.

### 1.9 Nested 104 (documents inside cells)

Nested BEJSON is a **104-only** feature (`Lib_PY/Core/lib_bejson_Core_bejson_core_nesting.py`, error codes 130–139). A cell of a 104 document holds a complete embedded 104 document **stored as a JSON string** in a `string` field:

```json
{
  "Format": "BEJSON",
  "Format_Version": "104",
  "Format_Creator": "Elton Boehnen",
  "Records_Type": ["Order"],
  "Fields": [{"name": "id", "type": "string"}, {"name": "items", "type": "string"}],
  "Values": [["o1", "{\"Format\":\"BEJSON\",\"Format_Version\":\"104\",\"Format_Creator\":\"Elton Boehnen\",\"Records_Type\":[\"Items\"],\"Fields\":[{\"name\":\"sku\",\"type\":\"string\"},{\"name\":\"qty\",\"type\":\"integer\"}],\"Values\":[[\"a\",1],[\"b\",2]]}"]]
}
```

* `bejson_nesting_scan(doc)` finds nested documents and validates each with the Core validator; `bejson_nesting_query(doc, "items")` queries a column across all nested documents; `bejson_nesting_mutate` allows append-only schema changes and null-pads existing rows; hard depth ceiling `NESTING_MAX_DEPTH = 16`.
* All nested documents in one parent column must share the same fields (`E134`, schema mismatch).
* An embedded object stored directly in an `object` cell is **not** detected by the scanner.

### 1.10 Best practices (105)

* `snake_case` field names; `PascalCase` custom headers on `105a`; `PascalCase` entity names.
* Always generate UUIDs with `uuid.uuid4()`. Never hand-write, sequence or reuse them.
* Address columns and cells by `field_uuid` / `record_uuid` in code that must survive renames and concurrent edits. Never hard-code a row position.
* Use `null` for genuinely missing data, not `""`.
* Manage schema versions with a custom header on `105a`; on `105`/`105db` custom headers are forbidden, so use the MFDB manifest `schema_version` or the `Records_Type` name.
* Schema change rules: appending a field is minor. Removing, retyping or reordering a field is breaking.
* Writers and the validator now check row length and types, but files edited outside the library are only as good as your last `validate_bejson` call: run it after any manual or third-party change.
* Write files only through `bejson_core_atomic_write` (or Core MFDB writers). Never edit `Values` in place in a text editor and expect the validator to catch a slip.
* Store timestamps as ISO-8601 UTC strings, e.g. `2026-10-24T12:00:00Z`. There is no timestamp type.

---

## PART 2: MFDB 1.40 CRASH COURSE
**(Multi-File Database over 104 and 105 entity files)**

MFDB is an architecture, not a `Format_Version`. One `104a` manifest registers any number of entity files; each entity file holds one entity type. In MFDB 1.40 an entity file may be **`104` or `105`** (mixed is allowed in one database). 105 entities unlock uuid-addressed CRUD and **referential integrity**.

```text
mydb/
  104a.mfdb.bejson        <- manifest (always at the root, always 104a)
  data/
    customer.bejson       <- entity file (105)
    order.bejson          <- entity file (105)
    legacy.bejson         <- entity file (104)
```

### 2.1 The manifest

* `Format_Version` must be `"104a"` and `Records_Type` exactly `["mfdb"]`. ✅ (A `105a` manifest is rejected.)
* Headers: `MFDB_Version`, `DB_Name` (required by convention), `DB_Description`, `Schema_Version`, `Author`, `Created_At`, `Network_Role` (`"Master"`/`"Slave"`), `Ref_Integrity` (`"true"`/`"false"` as **strings**), and debug headers (`Debug_Mode`, `Debug_Row_Cap`, `Debug_Reads`).
* Fields: `entity_name`, `file_path` (required, non-null, unique) ✅; then `description`, `record_count`, `schema_version`, `primary_key`.
* `file_path` is relative to the manifest and must not escape the database root (`..` traversal is rejected). ✅
* ⚠️ **`mfdb_core_create_database(...)` defaults `mfdb_version="1.31"`.** Nothing stamps `1.40` for you. Pass `mfdb_version="1.40"` for a 105/Ref_Integrity database. The version string is a label; no code reads it to switch behaviour.

```json
{
  "Format": "BEJSON",
  "Format_Version": "104a",
  "Format_Creator": "Elton Boehnen",
  "MFDB_Version": "1.40",
  "Network_Role": "Master",
  "DB_Name": "Shop",
  "DB_Description": "Customers and orders",
  "Schema_Version": "1.0.0",
  "Author": "Elton Boehnen",
  "Created_At": "2026-10-24T00:00:00Z",
  "Ref_Integrity": "true",
  "Records_Type": ["mfdb"],
  "Fields": [
    {"name": "entity_name",    "type": "string"},
    {"name": "file_path",      "type": "string"},
    {"name": "description",    "type": "string"},
    {"name": "record_count",   "type": "integer"},
    {"name": "schema_version", "type": "string"},
    {"name": "primary_key",    "type": "string"}
  ],
  "Values": [
    ["Customer", "data/customer.bejson", "Registered customers", 1, "1.0", null],
    ["Order",    "data/order.bejson",    "Customer orders",      2, "1.0", null]
  ]
}
```

### 2.2 Entity files

* Format `104` or `105` (`105a` and `105db` are rejected as entity formats since `mfdb_validator` 2.4.0: an entity has exactly one `Records_Type`). ✅
* `Parent_Hierarchy` is a **relative path from the entity file's own directory** to the manifest, e.g. `"../104a.mfdb.bejson"` for `data/order.bejson`. ✅ It must be present and must resolve to an existing file.
* `Records_Type` is one string, the entity name.
* Create with `mfdb_core_create_database(root, name, entities, mfdb_version="1.40")` or `mfdb_core_create_entity_file(manifest, name, fields, format_version="105")`. Pass `format_version`/`"105"` per entity; omit it and you get a 104 entity.

```python
from lib_bejson_Core_mfdb_core import mfdb_core_create_database, mfdb_core_enable_ref_integrity
S = lambda n: {"name": n, "type": "string"}
manifest = mfdb_core_create_database("shop", "Shop", [
    {"name": "Customer", "fields": [S("cust_name")], "format_version": "105"},
    {"name": "Order", "format_version": "105", "fields": [
        S("order_code"),
        {"name": "customer_uuid_fk", "type": "string", "fk_target_entity": "Customer", "fk_on_delete": "cascade"},
        {"name": "total", "type": "number"}]},
], mfdb_version="1.40")
mfdb_core_enable_ref_integrity(manifest)
```

Entity file produced (`data/order.bejson`, one `field_uuid` per field generated for you):

```json
{
  "Format": "BEJSON",
  "Format_Version": "105",
  "Format_Creator": "Elton Boehnen",
  "Parent_Hierarchy": "../104a.mfdb.bejson",
  "Records_Type": ["Order"],
  "Fields": [
    {"name": "order_code", "type": "string", "field_uuid": "b0000000-0001-4000-8000-000000000001"},
    {"name": "customer_uuid_fk", "type": "string", "fk_target_entity": "Customer", "fk_on_delete": "cascade", "field_uuid": "b0000000-0002-4000-8000-000000000002"},
    {"name": "total", "type": "number", "field_uuid": "b0000000-0003-4000-8000-000000000003"}
  ],
  "Values": [
    ["c1111111-0001-4000-8000-000000000001", "O1", "c2222222-0001-4000-8000-000000000001", 9.5]
  ]
}
```

### 2.3 Discovery

`mfdb_core_discover(path)` returns `'manifest'`, `'entity'`, `'archive'` or `'standalone'`:

* `104a` + filename ending `.mfdb.bejson` → `manifest`.
* `104`/`105`/`105a`/`105db` with `Parent_Hierarchy` → `entity` (105-series recognised since `mfdb_core` 3.1.0).
* Anything else → `standalone`.

### 2.4 Referential integrity (the 1.40 feature)

**Declare** a foreign key on a field of a 105-series entity (`fk_target_entity`, `fk_on_delete`). **Turn it on** per database with `mfdb_core_enable_ref_integrity(manifest)` (sets the `Ref_Integrity` header to the string `"true"`; `mfdb_core_disable_ref_integrity` sets `"false"`). It is **off by default**.

An FK value is the target row's **`record_uuid`**. `null` always means "no relationship" and always passes. The suffix of the field name (`_fk`, `_uuid_fk`) is only a convention; the code looks at `fk_target_entity`.

Write-time behaviour (only through the `*_105` CRUD functions, only when `Ref_Integrity` is `"true"`):

| Action | Result (verified) |
| :--- | :--- |
| `mfdb_core_add_entity_record_105(m, "Order", ["O2", "ghost-uuid", 5.0])` | `MFDBCoreError` code **39** `E_MFDB_FK_UNRESOLVED`; nothing written |
| Same with a real customer `record_uuid` | Written; manifest `record_count` synced |
| Same with `None` for the FK | Written |
| `mfdb_core_update_entity_record_105(m, "Order", rec_uuid, "customer_uuid_fk", "nope")` | Code 39 |
| FK target entity unknown in manifest | Code 43 `E_MFDB_FK_TARGET_ENTITY_UNKNOWN` |
| FK target is a 104 entity | Code 43 ("not a 105-series entity") |
| Bad `fk_on_delete` value | Code 47 `E_MFDB_FK_INVALID_ON_DELETE` |
| Delete a parent whose child says `restrict` | Code **44** `E_MFDB_FK_RESTRICT_VIOLATION`; nothing deleted |
| Delete a parent whose child says `cascade` | Children deleted too (cycle-guarded; code 45 if a cycle is hit) |
| Delete a parent whose child says `null` | Parent deleted; child FK set to `null` |

Cascade/restrict/null deletes use **plan-then-commit**: the whole plan is built in memory first, then every touched file is snapshotted and restored if anything fails.

`mfdb_core_delete_entity_record_105(...)` and friends are the **only** guarded paths. These bypass integrity completely: the 104 CRUD functions, direct file edits, and any write made while `Ref_Integrity` is `"false"`.

Audit an existing database (read-only, works whether or not the switch is on):

```python
validate_mfdb_database(manifest, strict_fk=True)       # adds FK errors (code 39) to the result
mfdb_validator_check_referential_integrity(manifest)   # list of {'code','entity','detail'}
```

`mfdb_core_check_entity_droppable(manifest, entity)` is the read-only check for "is anyone still pointing at this entity" (code 46). There is no entity-drop function yet.

❌ `fk_target_field_uuid` appears in older documentation. **No code reads it.** FKs always point at the target's `record_uuid`.

### 2.5 105 CRUD in an MFDB

| Function | Notes |
| :--- | :--- |
| `mfdb_core_add_entity_record_105(m, entity, values)` | `values` in `Fields` order, **without** `record_uuid`; returns the updated entity doc; syncs `record_count`. Raises code 54 on a 104 entity. Wrong `len(values)` (code 9) or a mistyped value (code 8) raises before anything is written. |
| `mfdb_core_update_entity_record_105(m, entity, record_uuid, field_name, value)` | FK-checked when the field is a declared FK; value type checked. |
| `mfdb_core_delete_entity_record_105(m, entity, record_uuid)` | Honors `fk_on_delete`. |
| `mfdb_core_load_entity(m, entity)` | List of dicts; **105 rows include a `record_uuid` key**. |
| `mfdb_core_get_entity_doc(m, entity)` | The raw entity document. |
| `mfdb_core_sync_all_counts(m)` | Re-counts every entity and updates `record_count`. |
| `mfdb_core_get_stats(m)`, `mfdb_core_query_entity`, `mfdb_core_join` | Read helpers; `get_stats` reports per-entity `field_count`/`record_count`. |

The 104 writer `mfdb_core_add_entity_record(...)` now fails on a 105 entity (it relies on `bejson_core_add_record`, which raises `E_FORMAT_UNSUPPORTED` for 105-series) and writes nothing. It used to silently write a row with no `record_uuid`.

### 2.6 Validation

`validate_mfdb_database(manifest, strict_fk=False)` enforces the MFDB spec levels for **104 and 105** entities alike (`mfdb_validator` 2.4.0). Error codes are embedded in each message as `[NN]`.

| Check | Level | Hard/Warn | Code | Status |
| :--- | :---: | :---: | :---: | :---: |
| Manifest is valid `104a`, `Records_Type == ["mfdb"]` | 1 | Hard | 32 | ✅ |
| `entity_name` and `file_path` fields exist | 1 | Hard | 40 | ✅ |
| No null `entity_name` / `file_path` | 1 | Hard | 41 | ✅ |
| `entity_name` and `file_path` unique | 1 | Hard | 35 | ✅ |
| Every `file_path` exists and stays inside the DB root | 1 | Hard | 33 | ✅ |
| Entity is valid BEJSON (`104` or `105`) | 2 | Hard | n/a | ✅ |
| `Parent_Hierarchy` present | 2 | Hard | 36 | ✅ |
| `Parent_Hierarchy` resolves to an existing file (else orphan) | 2 | Hard | 37 | ✅ |
| `Records_Type` is exactly one string | 2 | Hard | 34 | ✅ |
| `Records_Type[0]` equals the manifest `entity_name` (case-sensitive) | 2 | Hard | 34 | ✅ |
| Bidirectional: `Parent_Hierarchy` names the manifest that lists this file, and that manifest has a row resolving to this file | 2 | Hard | 38 | ✅ |
| `record_count` equals the real row count | 3 | **Warning** | n/a | ✅ (in `result.warnings`; never invalidates) |
| FK values resolve (`strict_fk=True`, 105 entities only) | 3 | Hard (as error) | 39 | ✅ |

`validate_mfdb_entity_file(path)` run on a single file applies the Level 2 checks including the bidirectional check against whatever manifest its `Parent_Hierarchy` names. A stray copy of an entity file that no manifest row points at therefore fails with code 38.

`mfdb_core_deep_verify(manifest)` is column-offset aware since `mfdb_core` 3.1.0: a healthy 105 entity (row length `len(Fields)+1`) produces no findings, a genuinely short or long row gives `POSITIONAL_VIOLATION` with the correct expected length, and type warnings read the right column.

`mfdb_core_self_heal(manifest)` still re-syncs `record_count`, resurrects missing files and pads or truncates **104-series** rows. For a 105-series entity with a positional violation it **does not touch the file** (it cannot know which cell is missing or extra) and lists the entity under `remaining_errors` for manual repair. Healthy 105 entities are never modified.

### 2.7 Master/Slave federation

* `Network_Role` is `"Master"` or `"Slave"`. The slave is "structurally blind": it holds no path to the master.
* `mfdb_federation_push_config(config_doc, slave_target_path)` writes a BEJSON `104a` config into the slave's directory using a temp file in the same directory plus `os.rename` (atomic; no partial reads). Returns `True`/`False`.
* `mfdb_federation_poll_dropzone(dropzone_dir, callback, poll_interval=2.0, timeout=60.0)` (slave side): for each `*.bejson` file found, parse it, call `callback(path, doc)`, delete the file. Returns the number processed.
* `mfdb_federation_distill_logs(...)` (slave side): truncates overflow log rows and pushes distilled metrics to the master's poll directory.
* A `ConnectedSlave` registry entity can be created with `mfdb_core_create_connected_slave_entity(manifest)`.

### 2.8 MFDB-132 (single-file package)

`bejson_core_chunking_create_mfdb132_package(mfdb_root_dir, db_name, ...)` collapses a whole MFDB directory into one Chunked-104a document.

* Per-file fields (fixed): `File_Name`, `File_Extension`, `File_Content`, `File_Version`, `File_Hash`, `Relative_Path`, `Is_Binary`, `Is_Mounted`.
* Identity headers: `Schema_Name: "MFDB-132"`, `Records_Type: ["MFDB-132"]`, `MFDB_Version: "1.32"` (the constant `MFDB_CHUNK_SCHEMA_VERSION`, which never changes), `DB_Name`, `Package_Format: "MFDB-Chunked-104a"`, `Package_Version`, `Session_Is_Mounted`, `Mount_Path`.
* Mounting (`MFDB132Archive`) writes a lock file **`.mfdb132_lock`** (JSON: `pid`, `chunk_doc_path`, `original_hash`, `workspace_dir`, `mounted_at`). If the package SHA-256 still matches `original_hash`, the workspace is reused without re-extracting.
* Commits are gated by full validation: a corrupt entity rejects the commit before anything is written.
* The older zip-based `MFDBArchive` class uses a different lock file name, `.mfdb_lock`.
* The packager chunks a directory that holds a `104a.mfdb.bejson`; it is format-agnostic about whether entities are 104 or 105.

### 2.9 Error codes (those the 105 Core actually defines)

| Range | Meaning |
| :--- | :--- |
| 1–16 | BEJSON validation: 2 missing key · 3 invalid format/creator · 4 invalid version · 5 `Records_Type` · 6 `Fields` · 7 `Values` · 8 type mismatch · 9 row length · 10 reserved key · 11 `Record_Type_Parent` · 13 file not found · 15 atomic write failed |
| 17–29 | Core operations |
| 30–42 | MFDB validation: 30 not a manifest · 31 not an entity · 32 manifest `Records_Type` · 33 entity not found · 34 name mismatch · 35 duplicate · 36 no `Parent_Hierarchy` · 37 manifest not found · 38 bidirectional fail · 39 FK unresolved · 40 missing required field · 41 null required · 42 invalid archive |
| 43–47 | MFDB referential integrity: 43 FK target unknown · 44 restrict violation · 45 cascade cycle · 46 entity still referenced · 47 invalid `fk_on_delete` |
| 50–60, 70–72 | MFDB core operations (54 = invalid operation, e.g. a 105 call on a 104 entity) |
| 80–85 | 105-series: 80 field integrity mismatch · 81 format unsupported · 82 record not found · 83 upgrade validation failed · 84 duplicate field name · 85 duplicate field_uuid |
| 130–139 | Nested 104 |

The codes **86–114 do not exist**: the 105 "schema constraint" codes (required/unique/enum/min/max/length) were removed in `bejson_errors` 2.9.0. Older text that mentions `E90`–`E95` is out of date. Codes 30–42 and 86+ are partly unused by the validators in 105 (for example the validator never raises 34 or 38; Part 4).

### 2.10 Standardization conventions

| Item | Convention | Status |
| :--- | :--- | :---: |
| Manifest filename | `104a.mfdb.bejson`, one per database, at the root | ⚠️ |
| Entity filenames | `<entity_name_lower>.bejson` (multi-word `snake_case`), default folder `data/` | ⚠️ |
| Entity names | `PascalCase` | ⚠️ |
| Field names | `snake_case` | ⚠️ |
| Primary key | 105: the reserved `record_uuid`. A `<entity>_id` style key is optional business data. | ⚠️ |
| Foreign key | 105: a field with `fk_target_entity` holding the target `record_uuid`. Name it `<target>_uuid_fk` (or `<target>_id_fk`) for readability. | ⚠️ |
| Write safety | Temp file + rename for every write; `ResilientPIDLock` around read-modify-write | ✅ (Core does it) |
| `record_count` | Advisory; synced by the `*_105` CRUD functions and `mfdb_core_sync_all_counts` | ⚠️ |
| Paths | Relative, never leaving the DB root | ✅ |
| Secrets | Never in plaintext in a data file | ⚠️ |

---

## PART 3: CHEAT SHEETS

### 3.1 Format comparison

| Feature | 104 | 104a | 104db | 105 | 105a | 105db |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Record types | 1 | 1 | 2+ | 1 | 1 | 2+ |
| Custom headers | ❌ | ✅ | ❌ | ❌ | ✅ | ❌ |
| `Parent_Hierarchy` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `array`/`object` fields | ✅ | ❌ | ✅ | ✅ | ❌ | ✅ |
| `field_uuid` per field | no | no | no | ✅ | ✅ | ✅ |
| `record_uuid` per row | no | no | no | col 0 | col 0 | col 1 |
| Row length | `len(Fields)` | same | same | `len(Fields)+1` | same | same |
| Row length checked by validator | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Value types checked by validator | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| MFDB manifest | no | **yes** | no | no | no | no |
| MFDB entity file | yes | no | no | yes | no | no |
| Declarative FK + cascade | no | no | no | yes | yes | yes |

### 3.2 Most-used functions

| Task | Function |
| :--- | :--- |
| Validate a file/doc | `validate_bejson(path_or_doc, is_file=True)` → `.valid`, `.errors` |
| Validate an MFDB | `validate_mfdb_database(manifest, strict_fk=True)` |
| Load / save | `bejson_core_load_file(path)` / `bejson_core_atomic_write(path, doc)` |
| Column positions | `bejson_core_get_field_map(doc)` |
| Resolve by UUID or name | `bejson_core_resolve_field_index(doc, target)` |
| Add column / row (105) | `bejson_core_define_field`, `bejson_core_add_record_105` |
| Edit / delete (105) | `bejson_core_write_cell`, `bejson_core_delete_record`, `bejson_core_remove_field` |
| Health check (UUIDs only) | `bejson_core_verify_105_integrity(doc)` |
| Upgrade | `bejson_core_upgrade_dry_run`, `bejson_core_upgrade_to_105` |
| New MFDB | `mfdb_core_create_database(..., mfdb_version="1.40")` |
| Turn on FKs | `mfdb_core_enable_ref_integrity(manifest)` |
| Guarded CRUD | `mfdb_core_add/update/delete_entity_record_105` |
| FK audit | `mfdb_validator_check_referential_integrity(manifest)` |

---

## PART 4: REALITY AUDIT (what was missing, what the parity patch fixed, what is still open)

First pass: everything below was reproduced by running the original `libraries_105.zip` Core. Second pass: the **105↔104 parity patch** (validator 3.4.0 · core 3.6.0 · upgrade 1.1.0 · mfdb_core 3.1.0) was applied and each item re-run. The 30 tests in `tests/test_105_104_parity_suite.py` pin the fixes. The same rules were then ported to JS, TS and Shell (see 4.7), so the "after patch" column holds in every language for validation, and for the writers listed in 4.7.

### 4.1 Checks that 104 performs and 105 did not

| # | Check (104 behaviour) | Before patch | After patch |
| :-: | :--- | :--- | :--- |
| 1 | Row length equals field count (105: `len(Fields)+1`), code 9 | Short, long and uuid-less rows passed | ✅ Rejected (all 105 formats, offset-aware) |
| 2 | Value type matches field type, bool excluded from integer/number, code 8 | A string in an integer column passed (validator, `add_record_105`, `write_cell`) | ✅ Rejected by the validator, `add_record_105`, `write_cell`, `mfdb_core_add_entity_record_105` |
| 3 | 104a primitives only | `105a` accepted `array`/`object` | ✅ Rejected |
| 4 | `Records_Type` count 1 / 1 / 2+, code 5 | Any count passed on 105-series | ✅ Enforced (`105`, `105a`: exactly 1; `105db`: 2+) |
| 5 | 104db: first field `Record_Type_Parent`, per-field owner, discriminator in `Records_Type`, code 11 | None enforced on `105db` | ✅ All three enforced; `record_uuid` in column 0 is caught by the discriminator check |
| 6 | (105-specific) `field_uuid`/`record_uuid` are UUIDv4 | Any non-empty string passed silently | ⚠️ Still passes, but now reports a **warning** per non-v4 id. Kept non-fatal on purpose so existing files with hand-made or v5 ids keep validating. Making it an error is a one-line change in `validate_bejson` |
| 7 | Upgrade validates its input | A 104 source with a short row upgraded "successfully" | ✅ Source is fully validated first (`E_UPGRADE_VALIDATION_FAILED`, 83); nothing written, no backup made. Dry run reports it |
| 8 | Verification helper agrees with validator | `verify_105_integrity` said `ok: True` on bad rows | ✅ Uses the same checks |
| 8b | `add_field` validates the type string (105 path) | Accepted `"timestamp"` and then produced an invalid document | ✅ Rejected (code 80) |

### 4.2 MFDB spec checks the older course documents (104 **and** 105)

All three were documented in the 104 crash course but performed by no validator. Now enforced for both 104 and 105 databases (`mfdb_validator` 2.4.0, pinned by `tests/test_mfdb_spec_levels_suite.py`; 18 of its 24 tests fail on the original Core).

| # | Documented check | Before | After |
| :-: | :--- | :--- | :--- |
| 9 | Entity `Records_Type` equals manifest `entity_name`, exactly one string (34) | An entity renamed to `["WrongName"]` still validated | ✅ Hard error, case-sensitive |
| 10 | Bidirectional manifest↔entity (38); orphan (37) | Only "`Parent_Hierarchy` resolves to some file" | ✅ Manifest must list the entity file; entity must point back at the listing manifest. A stray unlisted copy fails |
| 11 | `record_count` mismatch is a warning | Not in the validator | ✅ Warning only |

Not part of the spec and **not** added: scanning the directory for unlisted entity files during `validate_mfdb_database` (the spec's discovery is file-local; run `validate_mfdb_entity_file` on a suspect file instead).

### 4.3 Functions that were unsafe or wrong on 105 data

| # | Function | Before patch | After patch |
| :-: | :--- | :--- | :--- |
| 12 | `mfdb_core_add_entity_record` (104 writer) on a 105 entity | Wrote a row with no `record_uuid`; database still validated | ✅ Raises (`E_FORMAT_UNSUPPORTED`), file untouched |
| 13 | `mfdb_core_deep_verify` | False `POSITIONAL_VIOLATION` / `CORRUPT_JSON` on every healthy 105 row | ✅ Clean on healthy 105; still flags a genuinely broken 105 row |
| 14 | `mfdb_core_self_heal` | **Deleted the last cell of every healthy 105 row** | ✅ Never modifies 105 entities; reports a broken 105 row under `remaining_errors`. 104 repair behaviour unchanged |
| 15 | `bejson_core_add_record` (104 adder) on a 105 doc | Appended a uuid-less row | ✅ Raises `E_FORMAT_UNSUPPORTED` (81) |
| 16 | `mfdb_core_discover` | `standalone` for every 105 entity | ✅ `entity` |
| 17 | `bejson_core_remove_field` on a doc with a short row | `IndexError` | ✅ Short rows can no longer be created through the library; validate files that come from elsewhere |
| 18 | Ref_Integrity is off by default and bypassed by direct edits | Easy to assume protection that is not there | ⚠️ Unchanged (by design). Turn it on and audit with `strict_fk=True` |

### 4.4 Documentation that still disagrees with the code

| Where | Says | Reality |
| :--- | :--- | :--- |
| `libraries_105` README §3.7 (historical) | FK metadata included `fk_target_field_uuid` | Reconciled at PKG111: FKs always target `record_uuid` |
| README §3.7 and §10.6 (historical) | Error codes `E90`–`E95` for 105 | Reconciled at PKG118: removed in `bejson_errors` 2.9.0; codes 86–114 do not exist |
| README / v23 course | MFDB 1.40 databases | `mfdb_core_create_database` defaults `MFDB_Version` to `"1.31"`; pass `"1.40"` |
| Older 104 course nesting section | A nested document can be a string **or** object | The scanner only finds nested documents stored as JSON **strings** |
| README §1.2 | 105 runtime enforces "strict positional length, data-type conformance" | True after this patch; it was not true before it |

### 4.5 Behaviour changes to know about

* **Stricter files.** A 105-series file that used to validate with a wrong-length row, a mistyped cell, or a wrong `Records_Type` count now fails. That is the point, but run `validate_bejson` over existing 105 data before deploying the patch.
* **Stricter MFDB.** A database whose entity `Records_Type` does not match the manifest, or whose `Parent_Hierarchy` does not point back at the manifest listing it, now fails `validate_mfdb_database`. Entity files must be `104` or `105`.
* **Stricter upgrades.** A 104 file that was never valid can no longer be upgraded. One shipped test fixture (a 104db with a single `Records_Type`, and one with a bad `Format_Creator`) was itself invalid and was corrected.
* **API change.** `bejson_core_add_record` raises on 105-series documents instead of returning a bool.
* **Not changed.** Error code numbers, the on-disk 105 layout, FK semantics, and all 104-series behaviour and messages.

### 4.6 Practical guidance

1. Use only the `*_105` functions on 105 data; never the 104 `add_record` / `mfdb_core_add_entity_record`.
2. Run `validate_bejson` (and `validate_mfdb_database`) after any edit made outside the library.
3. Turn on `Ref_Integrity` and audit with `strict_fk=True` for any database whose FKs matter.
4. Pass `mfdb_version="1.40"` when creating a 105 database.
5. Parity is verified for validation and the writers in 4.7; `deep_verify` / `self_heal` exist only in Python (4.7).

### 4.7 Multi-language status (verified by a shared conformance corpus)

A corpus is generated from the Python reference and replayed through each language: 82 single-document validation cases, 98 MFDB database cases (33 on the 104 tree) and 11 foreign-key audit cases. Contract: the same valid/invalid verdict everywhere, and the same MFDB spec codes `[30]`-`[41]` whenever the reference emits one. An entity that fails base-BEJSON validation is compared by verdict only (each language reports it in its own registry: PY no code, JS `[31]`, TS BEJSON numeric codes). FK audit: same findings (code and entity) and the same strict-FK verdict. Result: **0 differences** in PY, TS and SH; JS differs only in the number of advisory UUID-format warnings on documents that are already invalid. Harness: `dev/conformance/`.

**Path rule (all languages):** a manifest `file_path` or an entity `Parent_Hierarchy` must be relative and stay inside the database root. Absolute paths (`/x`, `C:\x`) and `..` climbs above the root are rejected; the manifest error carries `[33]`. Before this edition an absolute path to an existing file outside the root validated as valid.

**`fk_on_delete`:** only an absent key defaults to `restrict`; an explicit `null` is invalid (code 47) in every language.

**`Network_Role`:** optional manifest header; `Master`, `Slave` or `Standalone`, anything else is `[30]`.

| Rule set | PY | JS | TS | SH |
| :--- | :-: | :-: | :-: | :-: |
| 104 version rules: row length, value types, Records_Type count, 104a primitives, 104db Record_Type_Parent, custom headers | ✅ | ✅ | ✅ | ✅ (new) |
| 105 equivalents, offset-aware (`record_uuid` slot) | ✅ | ✅ | ✅ (new) | ✅ (new) |
| MFDB: Records_Type == `entity_name` (34), bidirectional (38), orphan (37), no Parent_Hierarchy (36), duplicates (35), missing/null field (40/41), missing file (33), `record_count` drift = warning | ✅ | ✅ | ✅ | ✅ (new; 104 SH had no entity/database validation at all) |
| Entity format: 104 in the 104 tree; 104 or 105 in the 105 tree | ✅ | ✅ | ✅ | ✅ |
| 105 writers check length/types (`add_record_105`, `write_cell`) | ✅ | ✅ | ✅ (new) | n/a (SH `add_record` refuses 105 docs) |
| 104 writers refuse 105 docs | ✅ | ✅ | ✅ (new) | ✅ |
| `deep_verify`, `self_heal`, upgrade validation | ✅ | n/a | n/a | n/a |
| UUIDv4-format advisory warnings | ✅ | ✅ | ✅ | ❌ (SH has no warning channel for it) |

TS notes: the validators are pure in-memory functions. Pass `manifestRelativePath` (the manifest's path relative to the database root) to `validateDatabase` so the bidirectional check is exact; without it the entity's `Parent_Hierarchy` must land on a root-level `*.mfdb.bejson`. SH notes: errors carry `[NN]` codes in `mfdb_validator_get_errors`; drift warnings are in `mfdb_validator_get_warnings`; the 104 tree's `strict_fk` is accepted and ignored (104 entities have no foreign keys).

*End of document.*
