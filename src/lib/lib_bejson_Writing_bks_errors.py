"""
Library:         lib_bejson_Writing_bks_errors.py
Family:          Writing
Module Purpose:  Bookstd error family (codes 500-549): constants, names and the BKSError exception.
Architecture:    BKS-1 (BEJSON Book Standard) Writing family. Non-AI book organisation layer built on the frozen Core family (field-map cache, atomic write, validator, list validator). Contains no AI calls and no Flask code. Book Documents are BEJSON 104db; plans are the JobMaker 104a job schema.
Format_Scope:    104db (Book Document) | 104a (JobMaker plan)
Release_Version: 300
Version:         see VERSION below
Date:            2026-10-29
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   c590dfe4-24f4-4052-bf52-718c20a206e6
"""

VERSION = "1.0.0"

E_BKS_STRUCTURE = 500
E_BKS_SCHEMA_MISMATCH = 501
E_BKS_VERSION_UNSUPPORTED = 502
E_BKS_BOOK_COUNT = 503
E_BKS_REQUIRED_NULL = 510
E_BKS_ENUM_INVALID = 511
E_BKS_TIMESTAMP_INVALID = 512
E_BKS_EMPTY_STRING = 513
E_BKS_UUID_INVALID = 514
E_BKS_PATH_INVALID = 515
E_BKS_PK_DUPLICATE = 520
E_BKS_FK_DANGLING = 521
E_BKS_ORDER_INVALID = 522
E_BKS_OUTLINE_INVALID = 523
E_BKS_PARENT_KIND = 524
E_BKS_DERIVED_MISMATCH = 525
E_BKS_STATUS_INCONSISTENT = 526
E_BKS_GATE_NOT_PASSED = 527
E_BKS_PROVENANCE_MISSING = 528
E_BKS_HASH_MISMATCH = 529
E_BKS_EXPORT_NOT_ALLOWED = 530
E_BKS_EXPORT_STALE = 531
E_BKS_PLAN_NOT_JOBTASK = 532
E_BKS_PLAN_HEADER = 533
E_BKS_PLAN_CELL_SHAPE = 535
E_BKS_PLAN_LINK = 536
E_BKS_GATE_UNKNOWN = 537
E_BKS_IMPORT_UNSUPPORTED = 538
E_BKS_RENDER_FAILED = 539
E_BKS_MIGRATION_FAILED = 540
E_BKS_BOOKTYPE_LIMITS = 541  # addition to BKS-1: a BookType's chapter limits or outline template are inconsistent
# 534 is retired (formerly E_BKS_TEST_CMD_FORBIDDEN) and is never reused.
RETIRED_CODES = (534,)

BKS_ERROR_NAMES = {
    500: "E_BKS_STRUCTURE", 501: "E_BKS_SCHEMA_MISMATCH", 502: "E_BKS_VERSION_UNSUPPORTED", 503: "E_BKS_BOOK_COUNT",
    510: "E_BKS_REQUIRED_NULL", 511: "E_BKS_ENUM_INVALID", 512: "E_BKS_TIMESTAMP_INVALID", 513: "E_BKS_EMPTY_STRING",
    514: "E_BKS_UUID_INVALID", 515: "E_BKS_PATH_INVALID", 520: "E_BKS_PK_DUPLICATE", 521: "E_BKS_FK_DANGLING",
    522: "E_BKS_ORDER_INVALID", 523: "E_BKS_OUTLINE_INVALID", 524: "E_BKS_PARENT_KIND", 525: "E_BKS_DERIVED_MISMATCH",
    526: "E_BKS_STATUS_INCONSISTENT", 527: "E_BKS_GATE_NOT_PASSED", 528: "E_BKS_PROVENANCE_MISSING",
    529: "E_BKS_HASH_MISMATCH", 530: "E_BKS_EXPORT_NOT_ALLOWED", 531: "E_BKS_EXPORT_STALE",
    532: "E_BKS_PLAN_NOT_JOBTASK", 533: "E_BKS_PLAN_HEADER", 535: "E_BKS_PLAN_CELL_SHAPE",
    536: "E_BKS_PLAN_LINK", 537: "E_BKS_GATE_UNKNOWN", 538: "E_BKS_IMPORT_UNSUPPORTED", 539: "E_BKS_RENDER_FAILED",
    540: "E_BKS_MIGRATION_FAILED", 541: "E_BKS_BOOKTYPE_LIMITS",
}

# Why: one place maps a numeric code to its name, so messages and tests never repeat string literals.
# Input: numeric code. Output: the E_BKS_* name, or "E_BKS_UNKNOWN".
def bks_errors_name_for(code: int) -> str:
    return BKS_ERROR_NAMES.get(code, "E_BKS_UNKNOWN")


class BKSError(Exception):
    """Raised when a Book Document or plan operation is refused. Carries the numeric code and name."""

    def __init__(self, code: int, message: str):
        self.code = code
        self.name = bks_errors_name_for(code)
        self.message = message
        super().__init__(f"[{self.name} {code}] {message}")
