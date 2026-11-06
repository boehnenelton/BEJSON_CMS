"""
Library:         lib_bejson_Writing_bks_derive.py
Family:          Writing
Module Purpose:  Derived values: body normalisation, word count, content hash, UTC timestamps, UUID helpers.
Architecture:    BKS-1 (BEJSON Book Standard) Writing family. Non-AI book organisation layer built on the frozen Core family (field-map cache, atomic write, validator, list validator). Contains no AI calls and no Flask code. Book Documents are BEJSON 104db; plans are the JobMaker 104a job schema.
Format_Scope:    104db (Book Document) | 104a (JobMaker plan)
Release_Version: 300
Version:         see VERSION below
Date:            2026-10-29
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   f9cf407a-634b-4ddd-b525-094994f3a138
"""

import hashlib
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Iterable, List, Optional

VERSION = "1.0.0"
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_FENCE_RE = re.compile(r"```.*?```", re.S)

# Why: every body is stored and hashed in one canonical form (BKS-1 R3 / 6.5).
# Input: raw model or user text. Output: text with \n line ends and no trailing whitespace.
def bks_derive_normalize_body(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    return text.replace("\r\n", "\n").replace("\r", "\n").rstrip()

# Why: word_count is a derived field; one rule everywhere (whitespace tokens, fenced code excluded).
# Input: body text or None. Output: integer count (0 for None).
def bks_derive_count_words(text: Optional[str]) -> int:
    if not text:
        return 0
    return len(_FENCE_RE.sub("", text).split())

# Why: the book content hash is the fingerprint exports are checked against (BKS-1 8.4). Only structure, titles and text are hashed.
# Input: book title and an iterable of (order_index, uuid, parent_uuid_or_None, kind, title, body_or_None) for EVERY chapter row, parts included.
# Output: lowercase sha256 hex of "BKS1\n" + NFC(title) + "\n" then one \x1e record per row in order.
def bks_derive_content_hash(book_title: str, chapter_rows: Iterable[tuple]) -> str:
    out = ["BKS1\n", unicodedata.normalize("NFC", book_title), "\n"]
    for _order, uid, parent, kind, title, body in sorted(chapter_rows, key=lambda r: r[0]):
        out.append("\x1e" + uid + "\x1f" + (parent or "") + "\x1f" + kind + "\x1f" + unicodedata.normalize("NFC", title)
                   + "\x1f" + unicodedata.normalize("NFC", bks_derive_normalize_body(body) or "") + "\n")
    return hashlib.sha256("".join(out).encode("utf-8")).hexdigest()

# Why: all timestamps are UTC ISO-8601 with a Z suffix (BKS-1 4.2).
def bks_derive_now_utc() -> str:
    return datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT)

# Why: the validator and the store share one strict timestamp test.
# Output: True when the string is a real UTC timestamp in TIMESTAMP_FORMAT.
def bks_derive_is_timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, TIMESTAMP_FORMAT)
        return True
    except ValueError:
        return False

# Why: primary keys are random UUIDs; importers mint deterministic ones from a book scope.
def bks_derive_new_uuid() -> str:
    return str(uuid.uuid4())

# Why: parts and importer rows need stable ids so re-imports do not create duplicates (BKS-1 5.2).
def bks_derive_scoped_uuid(book_uuid: str, label: str) -> str:
    return str(uuid.uuid5(uuid.UUID(book_uuid), label))

# Why: ids must be canonical lowercase hyphenated UUIDs.
def bks_derive_is_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False

# Why: stored paths are always relative and portable (BKS-1 4.2).
# Output: True for relative, forward-slash paths with no drive letter and no parent segments.
def bks_derive_is_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if value.startswith("/") or "\\" in value or re.match(r"^[A-Za-z]:", value):
        return False
    return ".." not in value.split("/")

# Why: JobRunner names its output files from the task id with this exact rule (JobRunner._slug).
# Output: lowercase slug with non-alphanumeric runs collapsed to underscores.
def bks_derive_runner_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()

# Why: file and folder names for exports come from the title, never from user-typed paths.
# Output: lowercase ascii-ish slug (letters, digits, hyphens); `fallback` when nothing is left.
def bks_derive_slugify(text: str, fallback: str = "book") -> str:
    base = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    return slug[:60].strip("-") or fallback
