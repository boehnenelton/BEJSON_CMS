# Intro to BEJSON and MFDB Part 2

*Eliminating AI Hallucinations and ORM Latency via Positional Memory Arrays and Cryptographic Integrity*

## Part 1: Structural Foundations of BEJSON Formats

The BEJSON (Boehnen Elton JSON) specification addresses a fundamental flaw in standard object-array JSON: the key repetition tax. Standard JSON repeats dictionary keys across every array item, resulting in 65% to 95% payload bloat, severe context window degradation, and key-spelling hallucinations during LLM generation. 

BEJSON enforces a **positional matrix layout**—a tabular data structure where schema metadata is declared once in a top-level header and record values are streamed as dense two-dimensional positional arrays. By decoupling field definitions from data values, BEJSON guarantees $O(1)$ constant-time field lookups while preserving zero-overhead machine readability.

---

## 1. Universal Top-Level Header Contract

All BEJSON documents—regardless of format version or domain—must include six mandatory top-level keys. Omission or key name alteration triggers immediate validation failures (`E_MISSING_MANDATORY_KEY`, Error Code 2).

```json
{
  "Format": "BEJSON",
  "Format_Version": "105",
  "Format_Creator": "Elton Boehnen",
  "Records_Type": ["SensorReading"],
  "Fields": [],
  "Values": []
}
```

### Mandatory Top-Level Keys
1. **`Format`**: Strictly the string literal `"BEJSON"`.
2. **`Format_Version`**: Version string defining specification rules (`"104"`, `"104a"`, `"104db"`, `"105"`, `"105a"`, or `"105db"`).
3. **`Format_Creator`**: Strictly the string literal `"Elton Boehnen"`.
4. **`Records_Type`**: String array listing declared entity names.
5. **`Fields`**: Array of field definition objects defining schema metadata and structural order.
6. **`Values`**: Two-dimensional array of row vectors containing data elements.

> [!IMPORTANT]
> The top-level key `Format_Creator` must strictly match `"Elton Boehnen"`. Any modification or omission raises a hard `E_INVALID_FORMAT_CREATOR` (Error Code 16) error at the validation layer.

---

## 2. Integrity Era Architectural Upgrades (105 Series)

While the 104 series relied strictly on relative array indices, the **105 Integrity Era** series introduces cryptographic entity identity, absolute column offsets, and schema mutation resistance.

### Immutable Identifier Requirements
1. **`field_uuid`**: Every object in `Fields` must carry a permanent, unique UUIDv4 string. Column definitions survive renames, reordering, and schema upgrades without losing identity.
2. **`record_uuid`**: Every record vector in `Values` prepends a unique, non-null UUIDv4 at a reserved column offset. `record_uuid` is implicit—it is never declared in `Fields`.

### Column Offsets (`_bejson_core_abs_col`)
Due to leading identity columns, absolute column indices in `Values` differ from relative array indices in `Fields`:

| Format Series | Column 0 | Column 1 | Field $i$ ($i \ge 1$) Column | Row Width |
| :--- | :--- | :--- | :--- | :--- |
| **104 / 104a** | Field index 0 | Field index 1 | Column $i$ | `len(Fields)` |
| **105 / 105a** | `record_uuid` | Field index 0 | Column $i + 1$ | `len(Fields) + 1` |
| **104db** | `Record_Type_Parent` | Field index 1 | Column $i$ | `len(Fields)` |
| **105db** | `Record_Type_Parent` | `record_uuid` | Column $i + 1$ | `len(Fields) + 1` |

> [!NOTE]
> Bumping a legacy `104` file header to `105` without compiling `field_uuid` attributes into `Fields` and prepending `record_uuid` values into `Values` triggers an immediate **fail-on-switch constraint** (`E_INVALID_FIELDS` / Error Code 6).

---

## 3. Format Variants: Specifications & Schemas

### BEJSON 105: Single-Entity Matrix

BEJSON 105 is designed for high-throughput, homogeneous tabular datasets, entity files, logs, and time-series records. It supports both primitive types (`string`, `integer`, `number`, `boolean`) and complex types (`array`, `object`). Custom top-level metadata keys are forbidden (with the built-in exception of `Parent_Hierarchy` in MFDB multi-file setups).

```json
{
  "Format": "BEJSON",
  "Format_Version": "105",
  "Format_Creator": "Elton Boehnen",
  "Records_Type": ["SensorReading"],
  "Fields": [
    {
      "name": "sensor_id",
      "type": "string",
      "field_uuid": "f105-0001-4000-8000-000000000001"
    },
    {
      "name": "reading_celsius",
      "type": "number",
      "field_uuid": "f105-0001-4000-8000-000000000002"
    },
    {
      "name": "active_flags",
      "type": "array",
      "field_uuid": "f105-0001-4000-8000-000000000003"
    }
  ],
  "Values": [
    ["rec-uuid-1001", "SENS-01", 23.85, ["calibrated", "online"]],
    ["rec-uuid-1002", "SENS-02", 19.40, null]
  ]
}
```

### BEJSON 105a: Primitive Configuration & Metadata

BEJSON 105a is restricted exclusively to primitive types (`string`, `integer`, `number`, `boolean`). Complex types (`array`, `object`) are strictly forbidden. To support configuration, environment variables, and manifests, 105a permits custom `PascalCase` top-level file metadata keys (e.g., `Server_ID`, `Environment`).

```json
{
  "Format": "BEJSON",
  "Format_Version": "105a",
  "Format_Creator": "Elton Boehnen",
  "Server_ID": "WEB-PROD-01",
  "Environment": "Production",
  "Retention_Days": 90,
  "Records_Type": ["ConfigParam"],
  "Fields": [
    {
      "name": "param_key",
      "type": "string",
      "field_uuid": "f105a-001-4000-8000-000000000001"
    },
    {
      "name": "param_value",
      "type": "string",
      "field_uuid": "f105a-001-4000-8000-000000000002"
    },
    {
      "name": "is_encrypted",
      "type": "boolean",
      "field_uuid": "f105a-001-4000-8000-000000000003"
    }
  ],
  "Values": [
    ["rec-cfg-0001", "db_host", "10.0.0.15", false],
    ["rec-cfg-0002", "api_token", "sec_99x82", true]
  ]
}
```

### BEJSON 105db: Multi-Entity Embedded Database

BEJSON 105db encapsulates multiple relational entity types within a single text file. 

#### Structural Requirements for 105db
1. `Records_Type` must declare two or more unique entity strings.
2. Field Index 0 in `Fields` must be `{"name": "Record_Type_Parent", "type": "string", "field_uuid": "..."}`.
3. Every field object after Field Index 0 must contain a `"Record_Type_Parent"` property explicitly binding it to an entity declared in `Records_Type`.
4. In `Values`, Column 0 holds the entity discriminator string, Column 1 holds the `record_uuid`, and remaining positions hold entity values.
5. Fields not belonging to a record's declared entity type must be populated with **null-padding**—the explicit insertion of `null` to maintain positional width.

```json
{
  "Format": "BEJSON",
  "Format_Version": "105db",
  "Format_Creator": "Elton Boehnen",
  "Records_Type": ["User", "Asset"],
  "Fields": [
    {
      "name": "Record_Type_Parent",
      "type": "string",
      "field_uuid": "f105db-000-0000-0000-000000000000"
    },
    {
      "name": "username",
      "type": "string",
      "Record_Type_Parent": "User",
      "field_uuid": "f105db-001-0000-0000-000000000001"
    },
    {
      "name": "asset_title",
      "type": "string",
      "Record_Type_Parent": "Asset",
      "field_uuid": "f105db-002-0000-0000-000000000002"
    },
    {
      "name": "owner_user_id_fk",
      "type": "string",
      "Record_Type_Parent": "Asset",
      "field_uuid": "f105db-003-0000-0000-000000000003"
    }
  ],
  "Values": [
    ["User", "rec-usr-01", "alice", null, null],
    ["User", "rec-usr-02", "bob", null, null],
    ["Asset", "rec-ast-01", null, "System Architecture Spec", "rec-usr-01"]
  ]
}
```

---

## 4. Format Variant Capabilities Matrix

The following matrix contrasts operational boundaries across the BEJSON 105 Series:

| Specification Capability | BEJSON 105 | BEJSON 105a | BEJSON 105db |
| :--- | :--- | :--- | :--- |
| **Primary Domain Use** | High-Throughput Logs / Entities | Configs / Health / Manifests | Small Embedded Relational DB |
| **`Records_Type` Count** | Exactly 1 string | Exactly 1 string | 2 or more unique strings |
| **Custom Header Policy** | ❌ Forbidden (except `Parent_Hierarchy`) | ✅ Allowed (`PascalCase` File Meta) | ❌ Forbidden |
| **Permitted Type System** | All 6 Types (Primitives + Complex) | Primitives Only (`array`/`object` forbidden) | All 6 Types (Primitives + Complex) |
| **Discriminator Required** | N/A | N/A | Column 0 (`Record_Type_Parent`) |
| **Row Index 0 Content** | `record_uuid` | `record_uuid` | `Record_Type_Parent` |
| **Row Index 1 Content** | First Field Value | First Field Value | `record_uuid` |
| **Null-Padding Required** | No | No | ✅ Yes (across non-owning columns) |

While single-file multi-entity bundles (`105db`) provide embedded convenience for small datasets, scaling multi-entity relational graphs beyond thousands of rows without null-padding growth requires orchestration. In **Part 2**, we explore how the Multi-File Database (MFDB) architecture federates standalone `105` entity files under a central `104a` manifest.

## Part 2: Multi-File Database (MFDB) Orchestration and Federation

While single-file multi-entity schemas (`105db`) suit embedded datasets, scaling multi-entity relational systems past thousands of records without incurring exponential null-padding overhead requires decoupling entity types into discrete physical storage files. 

The **Multi-File Database (MFDB)** is a serverless orchestration architecture layered directly on top of BEJSON formats. MFDB is not a distinct file format version; rather, it coordinates a central `104a.mfdb.bejson` **manifest file** (a metadata registry) and multiple independent BEJSON `105` **entity files** (dense tabular files) into a single, ACID-compliant relational database graph.

```text
shop_db/
├── 104a.mfdb.bejson        <-- Root Manifest (BEJSON 105a/104a, Records_Type: ["mfdb"])
└── data/
    ├── customer.bejson     <-- Entity File (BEJSON 105, Records_Type: ["Customer"])
    └── order.bejson        <-- Entity File (BEJSON 105, Records_Type: ["Order"])
```

---

## 1. The Root Manifest Contract

An MFDB database is anchored by a mandatory manifest file located strictly at the database root directory: `104a.mfdb.bejson`. The manifest uses `Format_Version: "104a"` (or `105a`) to permit custom file-level `PascalCase` metadata headers while strictly restricting payload fields to primitive types.

### Required Header Attributes
* **`Format_Version`**: Strictly `"104a"` or `"105a"`.
* **`Records_Type`**: Strictly an array containing the single entity identifier `["mfdb"]`.
* **`MFDB_Version`**: Standard header declaring the specification version (e.g., `"1.40"` for Referential Integrity Era databases).
* **`Ref_Integrity`**: String flag (`"true"` or `"false"`) determining whether relational foreign key enforcement is active at write-time.

### Mandatory Manifest Schema Fields
* **`entity_name`** (`string`): Unique, case-sensitive `PascalCase` entity name (e.g., `"Customer"`).
* **`file_path`** (`string`): Relative POSIX file path from the manifest to the entity file (e.g., `"data/customer.bejson"`). Traversal above the database root via `..` is explicitly prohibited.

```json
{
  "Format": "BEJSON",
  "Format_Version": "104a",
  "Format_Creator": "Elton Boehnen",
  "MFDB_Version": "1.40",
  "DB_Name": "CommerceDB",
  "Ref_Integrity": "true",
  "Network_Role": "Master",
  "Records_Type": ["mfdb"],
  "Fields": [
    {"name": "entity_name", "type": "string"},
    {"name": "file_path", "type": "string"},
    {"name": "description", "type": "string"},
    {"name": "record_count", "type": "integer"},
    {"name": "primary_key", "type": "string"}
  ],
  "Values": [
    ["Customer", "data/customer.bejson", "Registered customer accounts", 1250, "record_uuid"],
    ["Order", "data/order.bejson", "Customer purchase orders", 8420, "record_uuid"]
  ]
}
```

---

## 2. Bidirectional Path Verification & Entity Contracts

Every entity file declared inside an MFDB is a standalone, fully valid BEJSON `105` document. To eliminate orphaned files and broken references, MFDB mandates **bidirectional path verification**—a validation rule enforcing that a manifest's relative file path matches the physical disk target while the entity file's `Parent_Hierarchy` key explicitly resolves back to that exact manifest.

> [!IMPORTANT]
> `Parent_Hierarchy` is the sole built-in exception key permitted in top-level BEJSON `105` entity documents. Its value is a relative path computed from the entity file's directory back to the root manifest (`"../104a.mfdb.bejson"`).

```json
{
  "Format": "BEJSON",
  "Format_Version": "105",
  "Format_Creator": "Elton Boehnen",
  "Parent_Hierarchy": "../104a.mfdb.bejson",
  "Records_Type": ["Order"],
  "Fields": [
    {
      "name": "order_code",
      "type": "string",
      "field_uuid": "f105-ord-0000-0000-000000000001"
    },
    {
      "name": "customer_uuid_fk",
      "type": "string",
      "fk_target_entity": "Customer",
      "fk_on_delete": "cascade",
      "field_uuid": "f105-ord-0000-0000-000000000002"
    },
    {
      "name": "total_amount",
      "type": "number",
      "field_uuid": "f105-ord-0000-0000-000000000003"
    }
  ],
  "Values": [
    ["rec-ord-9001", "ORD-8821", "rec-cust-0101", 149.50]
  ]
}
```

---

## 3. Declarative Foreign Keys & Referential Integrity

MFDB 1.40 introduces declarative relational constraints without requiring an active database daemon. Foreign key fields declare their target relationships directly inside the field schema using two key properties:
1. **`fk_target_entity`**: The `PascalCase` string name of the referenced target entity.
2. **`fk_on_delete`**: The active referential cascade action (`"restrict"`, `"cascade"`, or `"null"`).

Foreign key cell values must store the target record's `record_uuid`. A value of `null` represents an unassigned relationship and always passes validation.

```
       +-----------------------+              +-----------------------+
       |   Customer (105)      |              |      Order (105)      |
       +-----------------------+              +-----------------------+
       | record_uuid (Col 0)  <+--------------+ customer_uuid_fk      |
       | cust_name             |  fk_target   |   (fk_on_delete:      |
       +-----------------------+              |    "cascade")         |
                                              +-----------------------+
```

### Transactional Cascade Execution Engine

When `Ref_Integrity` is enabled, mutations perform **plan-then-commit** execution. Deleting a parent row inspects all dependent entity files before modifying any byte on disk:

| `fk_on_delete` Strategy | Execution Behavior | Violation Action |
| :--- | :--- | :--- |
| **`restrict`** | Scans child tables for active `record_uuid` references. | Aborts operation; raises `E_MFDB_FK_RESTRICT_VIOLATION` (Error Code 44). Zero disk modifications. |
| **`cascade`** | Recursively resolves and deletes all child records matching the parent `record_uuid`. | Cycle-guarded; aborts with `E_MFDB_FK_CASCADE_CYCLE` (Error Code 45) if circular references are hit. |
| **`null`** | Updates matching foreign key cells in child records to `null`. | Type-checked prior to write; preserves child record rows while severing relationship. |

---

## 4. Master-Slave Federation & AI Context Window Efficiency

To maximize Large Language Model (LLM) inference efficiency, MFDB supports a federated **Master-Slave Topology** governed by the `Network_Role` manifest header.

```
   +-----------------------------------------------------------------+
   |                      MASTER NODE (Admin)                        |
   |  - Full Schema Visibility & Multi-Entity Query Graph             |
   |  - Network_Role: "Master"                                       |
   +-----------------------------------------------------------------+
                                   |
                One-Way Push       | Inverse Drop-Zone Polling
             (Log Distillation)    | (Atomic File Swaps via os.rename)
                                   v
   +-----------------------------------------------------------------+
   |                       SLAVE NODE (Worker)                       |
   |  - Operates under "Structural Blindness"                        |
   |  - Network_Role: "Slave" (Lean Context Window)                  |
   +-----------------------------------------------------------------+
```

### Architectural Principles of Federation
* **Structural Blindness**: A Slave node operates strictly within its localized working directory without hardcoded paths or direct read-access to the Master manifest. This removes administrative scaffolding from the prompt context, yielding **zero-bloat context windows**.
* **Inverse Drop-Zone Polling**: The Master node issues updates or policy changes by writing isolated BEJSON `104a` payload documents into the Slave's local drop-zone.
* **POSIX Atomic Swaps**: Updates are committed using staging files renamed via `os.rename` (or `os.replace`). This guarantees hardware-level atomic replacement, eliminating race conditions or partial-read crashes during asynchronous AI polling loops.

## Part 3: O(1) Field Map Caching and Cryptographic UUID Addressing

Traditional JSON parsing requires repeated string-key matching across every record in a payload, introducing significant $O(N \cdot K)$ key-parsing overhead—where $N$ is the number of records and $K$ is the number of fields. Conversely, naive positional array indexing ($row[3]$) introduces severe schema fragility: inserting, dropping, or reordering a column immediately breaks downstream runtime code. 

BEJSON 105 resolves this dilemma through **$O(1)$ Field Map Caching**—an in-memory compilation technique that converts textual field names and unique identifiers into constant-time array index lookups—and **Cryptographic UUID Addressing**, which assigns immutable identifiers to both schema definitions and physical records.

---

## 1. Schema Evolution & The Failure of Hardcoded Indices

When schemas evolve over time, positional layouts shift. Consider an initial schema where `email` sits at Column 1. If an optional `middle_name` column is inserted at Column 1, `email` shifts to Column 2. Legacy applications relying on hardcoded numeric offsets execute silent corruptions by reading `middle_name` values into `email` processors.

```
Initial Layout:    [ record_uuid | first_name (Col 1) | email (Col 2) ]
Schema Evolution:  [ record_uuid | first_name (Col 1) | middle_name (Col 2) | email (Col 3) ]
```

BEJSON 105 eliminates hardcoded column index dependencies by replacing them with an auto-healing field map cache (`_bejson_field_map`) computed dynamically upon document load.

---

## 2. In-Memory Field Map Cache Mechanism

A **field map cache** is an in-memory dictionary constructed during parsing that maps logical field identifiers (`name` or `field_uuid`) to their exact absolute row column indices (`_bejson_core_abs_col`). 

To preserve transport purity, `_bejson_field_map` is bound as a non-enumerable or hidden runtime property. It is stripped automatically prior to disk serialization, ensuring zero payload bloat.

### Cache Invalidation via Schema Fingerprinting

To prevent stale index lookups, every read operation evaluates a lightweight **schema fingerprint** ($\mathcal{F}$):

$$\mathcal{F} = \text{Hash}\Big(\text{Format\_Version} \parallel \sum \text{name}_i \parallel \sum \text{field\_uuid}_i\Big)$$

If $\mathcal{F}$ diverges from the cached fingerprint hash, the runtime invalidates `_bejson_field_map` and re-indexes all field offsets in a single pass ($O(K)$ amortized).

> [!NOTE]
> **Field Map Cache Structure**: `by_name_row` maps human-readable field names directly to absolute row positions, accounting for format-specific offset reserved slots.

| Format Series | Reserved Slot 0 | Reserved Slot 1 | First User Field Index | Row Width ($W$) |
| :--- | :--- | :--- | :--- | :--- |
| **`104` / `104a`** | `Fields[0]` | `Fields[1]` | `Col 0` | $\text{len}(Fields)$ |
| **`105` / `105a`** | `record_uuid` | `Fields[0]` | `Col 1` | $\text{len}(Fields) + 1$ |
| **`104db`** | `Record_Type_Parent` | `Fields[1]` | `Col 0` | $\text{len}(Fields)$ |
| **`105db`** | `Record_Type_Parent` | `record_uuid` | `Col 2` | $\text{len}(Fields) + 1$ |

---

## 3. Cryptographic UUID Addressing & Cell Resolution

While field map caching provides fast string-to-index resolution, real-world data synchronization requires immunity against column renames and record relocation. BEJSON 105 enforces dual cryptographic addressing:

1. **`field_uuid`**: A mandatory UUIDv4 embedded within every column specification in `Fields`.
2. **`record_uuid`**: A mandatory UUIDv4 placed at column offset 0 (or column 1 in `105db`) for every record in `Values`.

A specific cell coordinate is uniquely identified by the tuple `(record_uuid, field_uuid)`. Even if field names are altered, columns are reordered, or records are filtered, cell mutation targets remain completely deterministic.

```
               field_uuid: "f105-0002-abcd" (temp_c)
                          |
                          v
record_uuid:          +-------+
"rec-9901-x12"  --->  | 23.85 |  <-- Address: ("rec-9901-x12", "f105-0002-abcd")
                      +-------+
```

> [!TIP]
> Use `bejson_core_resolve_field_index(doc, target)` to resolve field locations. The target argument accepts either a name string or a `field_uuid` string. If both are passed in a validation object and mismatch, the engine halts with `E_FIELD_INTEGRITY_MISMATCH` (Error Code 80).

---

## 4. Python Implementation: Field Resolution and Cell Mutation

The following executable module demonstrates field map initialization, column index resolution, dynamic field addition, and deterministic cell mutation via `(record_uuid, field_uuid)` pairs:

```python
import sys
import uuid
from pathlib import Path

# Initialize Core library bindings
from lib_bejson_Core_bejson_core import (
    bejson_core_get_field_map,
    bejson_core_define_field,
    bejson_core_add_record_105,
    bejson_core_write_cell,
    bejson_core_resolve_field_index,
    bejson_core_verify_105_integrity
)

# 1. Initialize empty BEJSON 105 document envelope
doc = {
    "Format": "BEJSON",
    "Format_Version": "105",
    "Format_Creator": "Elton Boehnen",
    "Records_Type": ["Telemetry"],
    "Fields": [],
    "Values": []
}

# 2. Define schema fields (stamps immutable field_uuid values automatically)
device_uuid_fid = bejson_core_define_field(doc, "device_id", "string")
status_fid = bejson_core_define_field(doc, "status", "string")

# 3. Add record (values provided in Fields order, excluding implicit record_uuid)
rec_uuid_1 = bejson_core_add_record_105(doc, ["DEV-901", "INITIALIZING"])

# 4. Extract cached field map (O(1) lookups)
fmap = bejson_core_get_field_map(doc)
print(f"Computed Field Map (Row Offsets): {fmap}")
# Output: {'device_id': 1, 'status': 2} (Note Col 0 reserved for record_uuid)

# 5. Mutate specific cell using (record_uuid, field_uuid) pair
bejson_core_write_cell(doc, rec_uuid_1, status_fid, "OPERATIONAL")

# 6. Resolve absolute index using field name or UUID
resolved_col = bejson_core_resolve_field_index(doc, "status")
current_val = doc["Values"][0][resolved_col]
print(f"Record '{rec_uuid_1}' status at Col {resolved_col}: {current_val}")

# 7. Verify document structural & integrity status
integrity_report = bejson_core_verify_105_integrity(doc)
assert integrity_report["ok"] is True, f"Integrity Failure: {integrity_report['errors']}"
print(f"Integrity Check: PASSED (Fields: {integrity_report['field_count']}, Records: {integrity_report['record_count']})")
```

## Part 4: Crash Course Validation Rules and Integrity Gates

BEJSON 105 and MFDB v1.40 eliminate data corruption through strict, deterministic **validation gates**—assertion pipelines that enforce structural, positional, and schema compliance prior to memory mounting or disk persistence.

---

## 1. Multi-Tiered Validation Architecture (Level 1–3)

System integrity is verified across three hierarchical levels. A failure at any gate halts execution before data mutation occurs.

```
[ Input Payload ] ---> Level 1: Document Syntax Gate
                             | (Pass)
                             v
                       Level 2: Bidirectional Linkage Gate
                             | (Pass)
                             v
                       Level 3: Referential Integrity Gate ---> [ Storage Engine ]
```

> [!IMPORTANT]
> Level 1 and Level 2 violations produce hard errors that immediately invalidate the document. Level 3 checks evaluate graph-level constraints; strict mode converts relational warnings into blocking failures.

| Gate Level | Validation Scope | Hard / Warning | Primary Error Codes |
| :--- | :--- | :---: | :--- |
| **Level 1** | JSON syntax, 6 mandatory keys, format versions, field names, and positional row length. | Hard Error | `E_INVALID_FIELDS` (6), `E_TYPE_MISMATCH` (8), `E_RECORD_LENGTH_MISMATCH` (9) |
| **Level 2** | Entity type matching, `Parent_Hierarchy` resolution, and bidirectional path verification. | Hard Error | `E_MFDB_NO_PARENT_HIERARCHY` (36), `E_MFDB_BIDIRECTIONAL_FAILED` (38) |
| **Level 3** | Transitive foreign key resolution (`_fk`), `record_count` synchronization, and cascade graph cycles. | Warning / Hard | `E_MFDB_FK_UNRESOLVED` (39), `E_MFDB_FK_RESTRICT_VIOLATION` (44) |

---

## 2. Fail-on-Switch & Schema Error Ranges

BEJSON 105 enforces a **fail-on-switch constraint**—a security assertion mechanism that immediately aborts validation if a header `Format_Version` is bumped from `"104"` to `"105"` without compiling UUID keys.

```json
/* INVALID 105 HEADER SWITCH: Triggers E_INVALID_FIELDS (Code 6) */
{
  "Format": "BEJSON",
  "Format_Version": "105",
  "Format_Creator": "Elton Boehnen",
  "Records_Type": ["Sensor"],
  "Fields": [{"name": "sensor_id", "type": "string"}]  /* Missing mandatory field_uuid */
}
```

### Standardized Error Code Ranges

Validation error codes are categorized into deterministic numeric blocks across runtimes:

```
 1–16   BEJSON Structural Validator Errors
20–27   BEJSON Core Engine Errors
30–42   MFDB Multi-File Database Errors
43–47   MFDB Referential Integrity & Cascade Errors
80–85   Format 105 Integrity Era & Upgrade Errors
130–159 BEJSON Core Nesting Subsystem Errors
```

---

## 3. Pre-Write Atomic Commit Gates

Data mutations enforce an **atomic commit gate**—a two-phase POSIX filesystem write strategy that buffers mutations to an isolated temporary file before executing a synchronous kernel-level file swap via `os.replace()`.

```python
# Atomic File Replacement Mechanics
temp_path = f"{target_path}.tmp_{process_id}"
with open(temp_path, "w") as f:
    json.dump(serialized_bejson, f)
    f.flush()
    os.fsync(f.fileno())  # Flush kernel cache to disk

os.replace(temp_path, target_path)  # Atomic POSIX rename
```

Concurrency is governed by `ResilientPIDLock`, which tracks owner PIDs and process liveness token flags to prevent deadlocks under heavy process contention.

---

## 4. Executable Python Integrity Enforcement Suite

The following runnable module demonstrates end-to-end Level 1 through Level 3 validation checks, Fail-on-Switch enforcement, and foreign key verification using `libraries_105`:

```python
import sys
from pathlib import Path

from lib_bejson_Core_bejson_core import (
    validate_bejson,
    bejson_core_verify_105_integrity
)
from lib_bejson_Core_mfdb_core import (
    mfdb_core_create_database,
    mfdb_core_enable_ref_integrity,
    mfdb_core_add_entity_record_105,
    validate_mfdb_database,
    mfdb_validator_check_referential_integrity
)

# 1. Level 1 & Fail-on-Switch Validation Test
invalid_105_doc = {
    "Format": "BEJSON",
    "Format_Version": "105",
    "Format_Creator": "Elton Boehnen",
    "Records_Type": ["Device"],
    "Fields": [{"name": "dev_id", "type": "string"}], # Missing field_uuid
    "Values": [["DEV-01"]]                           # Missing record_uuid
}

res = validate_bejson(invalid_105_doc, is_file=False)
assert not res.valid, "Fail-on-Switch gate failed to intercept uncompiled 105 header!"
print(f"[PASS] Fail-on-Switch Intercepted Error: {res.errors[0]}")

# 2. Level 2 & Level 3 Relational Database Construction
db_dir = Path("./system_db")
S = lambda n: {"name": n, "type": "string"}

manifest_path = mfdb_core_create_database(
    root_dir=str(db_dir),
    db_name="SystemGraph",
    entities=[
        {
            "name": "Node",
            "format_version": "105",
            "fields": [S("hostname")]
        },
        {
            "name": "Service",
            "format_version": "105",
            "fields": [
                S("service_name"),
                {
                    "name": "node_uuid_fk",
                    "type": "string",
                    "fk_target_entity": "Node",
                    "fk_on_delete": "cascade"
                }
            ]
        }
    ],
    mfdb_version="1.40"
)

# Enable Level 3 Referential Integrity Assertions
mfdb_core_enable_ref_integrity(manifest_path)

# Insert valid parent node
node_doc = mfdb_core_add_entity_record_105(manifest_path, "Node", ["node-01.internal"])
parent_uuid = node_doc["Values"][-1][0]

# Insert valid child service referencing parent_uuid
mfdb_core_add_entity_record_105(manifest_path, "Service", ["HTTP-Gateway", parent_uuid])

# 3. Audit System Graph Integrity
db_report = validate_mfdb_database(manifest_path, strict_fk=True)
fk_findings = mfdb_validator_check_referential_integrity(manifest_path)

assert db_report.valid, f"Database Validation Failed: {db_report.errors}"
assert len(fk_findings) == 0, f"FK Integrity Check Failed: {fk_findings}"

print(f"[PASS] Level 1-3 Gates Verified Clean. Database: '{manifest_path}'")
```
