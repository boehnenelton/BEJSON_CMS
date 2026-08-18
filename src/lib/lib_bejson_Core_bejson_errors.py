"""
Library:        lib_bejson_Core_bejson_errors.py
Family:         Core
Description:    Unified error registry for BEJSON ecosystem.
Version:        2.4.0
Date:           2026-07-18
Author:         Elton Boehnen
Contact:        eltonboehnen@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  9f2e6a1c-4b8d-4e3f-a7c5-1d6b3e8f2a90

Changelog:
  2.4.0 - Removed Core_Nesting range (130-159) and Cognition range
          (270-289) — those families now own their codes in
          lib_bejson_CoreNesting_bejson_errors.py and
          lib_bejson_Cognition_bejson_errors.py respectively. MFDB codes
          (30-42, 50-72) remain here: MFDB is implemented as part of the
          Core family, not a separate family directory.
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
# Codes 17-19: parse/serialization layer — added v2.3.0 (parity with TS v2.3.0)
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
# Codes 57-60: added v2.3.0 (parity with TS MFDB_CORE_CODES v2.3.0)
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

# Core_Nesting codes moved to lib_bejson_CoreNesting_bejson_errors.py (v2.4.0)
# Cognition codes moved to lib_bejson_Cognition_bejson_errors.py (v2.4.0)
