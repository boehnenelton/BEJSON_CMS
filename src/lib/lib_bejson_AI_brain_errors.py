"""
Library:         lib_bejson_AI_brain_errors.py
Family:          AI
Module Purpose:  Error registry for the AI-family brain memory extension: named codes 240-269, one exception class, recoverability flags.
Architecture:    Pure constants and one exception type. No I/O. The AI family registry (lib_bejson_AI_bejson_errors) uses 200-235 and is not modified; this extension owns 240-269 so nothing collides.
Version:         1.0.0
Release_Version: 300
Date:            2026-10-24
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   2876b895-7e82-4147-8dad-1032e8084ff3
"""

import lib_bejson_AI_brain_core_bridge  # noqa: F401  (keeps sibling imports resolvable)
from lib_bejson_AI_bejson_errors import AIException, AIFatalError, AIRecoverableError

VERSION = "1.1.0"
RELATIONAL_ID = "2876b895-7e82-4147-8dad-1032e8084ff3"

E_BRAIN_NOT_INITIALIZED = 240
E_BRAIN_CORRUPT = 241
E_BRAIN_LOCK_TIMEOUT = 242
E_BRAIN_PATH_GUARD = 243
E_BRAIN_CATEGORY_EXISTS = 244
E_BRAIN_CATEGORY_NOT_FOUND = 245
E_BRAIN_CATEGORY_PROTECTED = 246
E_BRAIN_MEMORY_NOT_FOUND = 247
E_BRAIN_MEMORY_INVALID = 248
E_BRAIN_LIMIT_EXCEEDED = 249
E_BRAIN_XML_MALFORMED = 250
E_BRAIN_XML_UNKNOWN_COMMAND = 251
E_BRAIN_XML_MISSING_ATTRIBUTE = 252
E_BRAIN_XML_NONCE_MISMATCH = 253
E_BRAIN_WRITE_FORBIDDEN = 254
E_BRAIN_PROPOSAL_NOT_FOUND = 255
E_BRAIN_SNAPSHOT_PACKAGE_FAILED = 256
E_BRAIN_SNAPSHOT_INVALID = 257
E_BRAIN_SNAPSHOT_NOT_FOUND = 258
E_BRAIN_ROLLBACK_VERIFY_FAILED = 259
E_BRAIN_RECOVERY_REQUIRED = 260
# 261-269 reserved for the Brain family.

BRAIN_ERROR_NAMES = {
    240: "E_BRAIN_NOT_INITIALIZED", 241: "E_BRAIN_CORRUPT", 242: "E_BRAIN_LOCK_TIMEOUT",
    243: "E_BRAIN_PATH_GUARD", 244: "E_BRAIN_CATEGORY_EXISTS", 245: "E_BRAIN_CATEGORY_NOT_FOUND",
    246: "E_BRAIN_CATEGORY_PROTECTED", 247: "E_BRAIN_MEMORY_NOT_FOUND", 248: "E_BRAIN_MEMORY_INVALID",
    249: "E_BRAIN_LIMIT_EXCEEDED", 250: "E_BRAIN_XML_MALFORMED", 251: "E_BRAIN_XML_UNKNOWN_COMMAND",
    252: "E_BRAIN_XML_MISSING_ATTRIBUTE", 253: "E_BRAIN_XML_NONCE_MISMATCH", 254: "E_BRAIN_WRITE_FORBIDDEN",
    255: "E_BRAIN_PROPOSAL_NOT_FOUND", 256: "E_BRAIN_SNAPSHOT_PACKAGE_FAILED", 257: "E_BRAIN_SNAPSHOT_INVALID",
    258: "E_BRAIN_SNAPSHOT_NOT_FOUND", 259: "E_BRAIN_ROLLBACK_VERIFY_FAILED", 260: "E_BRAIN_RECOVERY_REQUIRED",
}

# Fatal codes mean the store should not keep writing until a person looks at it; the rest are ordinary refusals.
BRAIN_FATAL_CODES = frozenset({
    E_BRAIN_NOT_INITIALIZED, E_BRAIN_CORRUPT, E_BRAIN_PATH_GUARD,
    E_BRAIN_SNAPSHOT_INVALID, E_BRAIN_ROLLBACK_VERIFY_FAILED, E_BRAIN_RECOVERY_REQUIRED,
})

# Codes the CLI reports as an environment problem (exit 20); every other Brain code is a data/validation problem (exit 30).
BRAIN_ENVIRONMENT_CODES = frozenset({E_BRAIN_NOT_INITIALIZED, E_BRAIN_PATH_GUARD, E_BRAIN_LOCK_TIMEOUT})


class BrainError(AIException):
    # Raised by every Brain library function. `code` is one of the E_BRAIN_* constants. Subclasses AIException, so existing
    # `except AIException` handlers catch it; BrainError(code, ...) returns a BrainFatalError or BrainRecoverableError
    # (AIFatalError / AIRecoverableError) according to BRAIN_FATAL_CODES, so callers can use the AI family's stop-or-retry split.
    def __new__(cls, code: int = 0, *args, **kwargs):
        if cls is BrainError:
            cls = BrainFatalError if code in BRAIN_FATAL_CODES else BrainRecoverableError
        return super().__new__(cls)

    def __init__(self, code: int, message: str, detail: dict | None = None):
        super().__init__(message, error_code=code)
        self.code = code
        self.name = BRAIN_ERROR_NAMES.get(code, "E_BRAIN_UNKNOWN")
        self.message = message
        self.detail = detail or {}
        self.fatal = isinstance(self, AIFatalError)

    def to_dict(self) -> dict:
        return {"code": self.code, "name": self.name, "message": self.message, "fatal": self.fatal, "detail": self.detail}


class BrainFatalError(BrainError, AIFatalError):
    # Nothing can succeed until a person looks at the store.
    pass


class BrainRecoverableError(BrainError, AIRecoverableError):
    # The single request was refused; the store is fine and the next request may succeed.
    pass


# Returns the registry name for a code, or E_BRAIN_UNKNOWN.
def brain_errors_name_of(code: int) -> str:
    return BRAIN_ERROR_NAMES.get(code, "E_BRAIN_UNKNOWN")
