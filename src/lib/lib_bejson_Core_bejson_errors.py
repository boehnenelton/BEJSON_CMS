"""
Library:         lib_bejson_Core_bejson_errors.py
Family:          Core
Module Purpose:  Unified numeric error-code registry shared by the BEJSON, MFDB and Nesting modules.
Architecture:    Shared numeric error-code registry. Codes are grouped by layer (BEJSON validation/core, MFDB, Nesting); a code name containing MFDB does not make the module that raises it MFDB-specific.
Format_Scope:    All layers (registry only)
Glossary:        BEJSON 104, 104a and 104db are the three file formats (Format_Version). 104db = ONE file holding 2+ entity types
                 (Record_Type_Parent discriminator, null-padding). MFDB is NOT a format and NOT 104db: it is a layer made of one 104a manifest
                 (104a.mfdb.bejson) plus dense 104 entity files linked by Parent_Hierarchy. MFDB-132 = an MFDB packed into one Chunked-104a document.
Version:         2.5.0
Release_Version: 300
Date:            2026-10-16
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   61fc188e-ccb2-448b-85a0-b3bdb0e224ab
Changelog:
  2.5.0 (2026-10-16) - Added the Core nesting codes E_NESTING_* (130-139), moved here from the removed lib_bejson_Core_bejson_nesting_errors.py.
          Core now resolves every error code through this single file. Codes, names and values unchanged.
"""

# ---------------------------------------------------------------------------
# BEJSON Validation (1-16)
# ---------------------------------------------------------------------------
E_INVALID_JSON                       = 1
E_MISSING_MANDATORY_KEY              = 2
E_INVALID_FORMAT                     = 3
E_INVALID_VERSION                    = 4
E_INVALID_RECORDS_TYPE               = 5
E_INVALID_FIELDS                     = 6
E_INVALID_VALUES                     = 7
E_TYPE_MISMATCH                      = 8
E_RECORD_LENGTH_MISMATCH             = 9
E_RESERVED_KEY_COLLISION             = 10
E_INVALID_RECORD_TYPE_PARENT         = 11
E_NULL_VIOLATION                     = 12
E_FILE_NOT_FOUND                     = 13
E_PERMISSION_DENIED                  = 14
E_ATOMIC_WRITE_FAILED                = 15
E_INVALID_FORMAT_CREATOR             = 16

# BEJSON Core ops (17-29)
# Codes 17-19: parse/serialization layer (same codes as TS)
E_CORE_PARSE_ERROR                   = 17
E_CORE_SERIALIZATION_ERROR           = 18
E_CORE_NULL_DOCUMENT                 = 19
E_CORE_INVALID_VERSION               = 20
E_CORE_INVALID_OPERATION             = 21
E_CORE_INDEX_OUT_OF_BOUNDS           = 22
E_CORE_FIELD_NOT_FOUND               = 23
E_CORE_TYPE_CONVERSION_FAILED        = 24
E_CORE_BACKUP_FAILED                 = 25
E_CORE_WRITE_FAILED                  = 26
E_CORE_QUERY_FAILED                  = 27
E_CORE_ENCRYPTION_FAILED             = 28
E_CORE_DECRYPTION_FAILED             = 29

# Aliases — map TS BEJSON_CORE_CODES aliases to canonical codes above
E_CORE_UNSUPPORTED_OPERATION         = E_CORE_INVALID_OPERATION    # 21
E_CORE_WRITE_TYPE_MISMATCH           = E_TYPE_MISMATCH             # 8
E_CORE_WRITE_LENGTH_MISMATCH         = E_RECORD_LENGTH_MISMATCH    # 9

# ---------------------------------------------------------------------------
# MFDB Validation (30-42)
# ---------------------------------------------------------------------------
E_MFDB_NOT_MANIFEST                  = 30
E_MFDB_NOT_ENTITY_FILE               = 31
E_MFDB_MANIFEST_RECORDS_TYPE         = 32
E_MFDB_ENTITY_NOT_FOUND              = 33
E_MFDB_ENTITY_NAME_MISMATCH          = 34
E_MFDB_DUPLICATE_ENTRY               = 35
E_MFDB_NO_PARENT_HIERARCHY           = 36
E_MFDB_MANIFEST_NOT_FOUND            = 37
E_MFDB_BIDIRECTIONAL_FAIL            = 38
E_MFDB_FK_UNRESOLVED                 = 39
E_MFDB_MISSING_REQUIRED_FIELD        = 40
E_MFDB_NULL_REQUIRED                 = 41
E_MFDB_INVALID_ARCHIVE               = 42

# ---------------------------------------------------------------------------
# MFDB Core ops (50-72)
# Codes 57-60 match TS MFDB_CORE_CODES
# ---------------------------------------------------------------------------
E_MFDB_CORE_MANIFEST_NOT_FOUND       = 50
E_MFDB_CORE_ENTITY_NOT_FOUND         = 51
E_MFDB_CORE_WRITE_FAILED             = 52
E_MFDB_CORE_LOCK_FAILED              = 53
E_MFDB_CORE_INVALID_OPERATION        = 54
E_MFDB_CORE_INDEX_OUT_OF_BOUNDS      = 55
E_MFDB_CORE_JOIN_FAILED              = 56
E_MFDB_CORE_DUPLICATE_ENTITY_NAME    = 57
E_MFDB_CORE_RECORD_COUNT_SYNC_FAILED = 58
E_MFDB_CORE_NULL_MANIFEST            = 59
E_MFDB_CORE_ENTITY_NOT_IN_MANIFEST   = 60
E_MFDB_CORE_ARCHIVE_ERROR            = 70
E_MFDB_CORE_MOUNT_CONFLICT           = 71
E_MFDB_CORE_CREATE_FAILED            = 72

# ---------------------------------------------------------------------------
# Core nesting (130-159)
# Nested BEJSON 104 (embedded 104 cells). Part of the Core family; resolved here,
# there is no separate nesting errors file.
# ---------------------------------------------------------------------------
E_NESTING_INVALID_CELL               = 130  # Cell address out of bounds for mutation
E_NESTING_NOT_BEJSON                 = 131  # Doc argument is not a dict
E_NESTING_DEPTH_EXCEEDED             = 132  # Recursion hit NESTING_MAX_DEPTH
E_NESTING_CACHE_MISS                 = 133  # Address not found in NestMap (informational)
E_NESTING_SCHEMA_MISMATCH            = 134  # Column schema uniformity violation
E_NESTING_CIRCULAR_REF               = 135  # Same fingerprint seen twice in walk path
E_NESTING_VALIDATION_FAILED          = 136  # Nested doc fails 104 validation rules
E_NESTING_FIELD_MAP_FAILED           = 137  # Could not build field map for nested doc
E_NESTING_QUERY_INVALID_PATH         = 138  # Path string failed grammar parse
E_NESTING_QUERY_EMPTY_PATH           = 139  # Path was empty / whitespace only

# 140-159 reserved for future Core nesting codes.

# Cognition codes moved to lib_bejson_Cognition_bejson_errors.py (v2.4.0)