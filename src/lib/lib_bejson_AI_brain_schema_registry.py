"""
Library:         lib_bejson_AI_brain_schema_registry.py
Family:          AI
Module Purpose:  The single place where Brain entity and field names are written. Every other module reads names from here.
Architecture:    BEJSON MFDB (104a manifest + 104 entity files): entities BrainCategory (prefix brcat_) and BrainMemory (prefix brmem_). Field names are snake_case with one prefix per entity; timestamps are <entity>_created_at (UTC ISO-8601); foreign keys end in _fk.
Version:         1.0.0
Release_Version: 300
Date:            2026-10-24
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   4f567a83-1fab-4d1a-af1b-b37b93a62514
"""

VERSION = "1.0.0"
RELATIONAL_ID = "4f567a83-1fab-4d1a-af1b-b37b93a62514"
SCHEMA_VERSION = "1.0.0"

ENTITY_CATEGORY = "BrainCategory"
ENTITY_MEMORY = "BrainMemory"
ENTITY_ORDER = (ENTITY_CATEGORY, ENTITY_MEMORY)
DB_NAME = "BrainMemory"   # MFDB DB_Name header and snapshot package name

# Write owner of every entity: only these store functions may insert or change rows (policy 6.6).
WRITE_OWNER = {ENTITY_CATEGORY: "lib_bejson_AI_brain_store", ENTITY_MEMORY: "lib_bejson_AI_brain_store"}

STATUS_ACTIVE = "active"
STATUS_PROPOSED = "proposed"
STATUS_ARCHIVED = "archived"
STATUS_REJECTED = "rejected"
CATEGORY_STATUSES = (STATUS_ACTIVE, STATUS_PROPOSED, STATUS_ARCHIVED)
MEMORY_STATUSES = (STATUS_ACTIVE, STATUS_PROPOSED, STATUS_ARCHIVED, STATUS_REJECTED)

ORIGIN_USER = "user"
ORIGIN_AI = "ai"
ORIGIN_SYSTEM = "system"
ORIGINS = (ORIGIN_USER, ORIGIN_AI, ORIGIN_SYSTEM)

KEYWORD_SEPARATOR = "|"


class CatF:
    # Field names of BrainCategory.
    ID = "brcat_id"
    NAME = "brcat_name"
    DESCRIPTION = "brcat_description"
    KEYWORDS = "brcat_default_keywords"
    STATUS = "brcat_status"
    ORIGIN = "brcat_origin"
    PROTECTED = "brcat_protected_flag"
    CREATED_AT = "brcat_created_at"
    UPDATED_AT = "brcat_updated_at"


class MemF:
    # Field names of BrainMemory.
    ID = "brmem_id"
    CATEGORY_FK = "brmem_category_fk"
    TITLE = "brmem_title"
    CONTENT = "brmem_content"
    KEYWORDS = "brmem_keywords"
    PRIORITY = "brmem_priority"
    CONFIDENCE = "brmem_confidence"
    STATUS = "brmem_status"
    ORIGIN = "brmem_origin"
    PINNED = "brmem_pinned_flag"
    LOCKED = "brmem_locked_flag"
    SUPERSEDES_FK = "brmem_supersedes_id_fk"
    CREATED_AT = "brmem_created_at"
    UPDATED_AT = "brmem_updated_at"
    LAST_RECALLED_AT = "brmem_last_recalled_at"


_FIELD_SPECS = {
    ENTITY_CATEGORY: [
        (CatF.ID, "string"), (CatF.NAME, "string"), (CatF.DESCRIPTION, "string"), (CatF.KEYWORDS, "string"),
        (CatF.STATUS, "string"), (CatF.ORIGIN, "string"), (CatF.PROTECTED, "boolean"),
        (CatF.CREATED_AT, "string"), (CatF.UPDATED_AT, "string"),
    ],
    ENTITY_MEMORY: [
        (MemF.ID, "string"), (MemF.CATEGORY_FK, "string"), (MemF.TITLE, "string"), (MemF.CONTENT, "string"),
        (MemF.KEYWORDS, "string"), (MemF.PRIORITY, "integer"), (MemF.CONFIDENCE, "number"),
        (MemF.STATUS, "string"), (MemF.ORIGIN, "string"), (MemF.PINNED, "boolean"), (MemF.LOCKED, "boolean"),
        (MemF.SUPERSEDES_FK, "string"), (MemF.CREATED_AT, "string"), (MemF.UPDATED_AT, "string"),
        (MemF.LAST_RECALLED_AT, "string"),
    ],
}

_PRIMARY_KEYS = {ENTITY_CATEGORY: CatF.ID, ENTITY_MEMORY: MemF.ID}

# Foreign keys: entity -> {field: (parent entity, on-delete behaviour)}. Nothing is ever hard-deleted, so "restrict" documents the intent.
FOREIGN_KEYS = {
    ENTITY_MEMORY: {
        MemF.CATEGORY_FK: (ENTITY_CATEGORY, "restrict"),
        MemF.SUPERSEDES_FK: (ENTITY_MEMORY, "null"),
    },
}

# Categories created by init. Protected ones can never be archived.
SYSTEM_CATEGORIES = (
    {"name": "General", "description": "Anything that fits nowhere else.", "protected": True},
    {"name": "Preferences", "description": "How the user wants things done.", "protected": True},
    {"name": "Projects", "description": "Facts about the user's projects and tools.", "protected": False},
)


# Field definitions of one entity as BEJSON Fields[] entries.
def schema_registry_entity_fields(entity_name: str) -> list[dict]:
    return [{"name": name, "type": ftype} for name, ftype in _FIELD_SPECS[entity_name]]


# Plain field-name list of one entity, in storage order.
def schema_registry_field_names(entity_name: str) -> list[str]:
    return [name for name, _ in _FIELD_SPECS[entity_name]]


# Primary-key field of one entity.
def schema_registry_primary_key(entity_name: str) -> str:
    return _PRIMARY_KEYS[entity_name]


# Entity definitions in the shape mfdb_core_create_database expects.
def schema_registry_entities() -> list[dict]:
    descriptions = {
        ENTITY_CATEGORY: "Brain memory categories.",
        ENTITY_MEMORY: "Brain memories (one table; category is a foreign key).",
    }
    return [
        {
            "name": name,
            "file_path": f"data/{name.lower()}.bejson",
            "description": descriptions[name],
            "primary_key": _PRIMARY_KEYS[name],
            "schema_version": SCHEMA_VERSION,
            "fields": schema_registry_entity_fields(name),
        }
        for name in ENTITY_ORDER
    ]


# Splits the stored keyword string into a list.
def schema_registry_split_keywords(stored: str | None) -> list[str]:
    if not stored:
        return []
    return [item for item in stored.split(KEYWORD_SEPARATOR) if item]


# Joins a keyword list into the stored string.
def schema_registry_join_keywords(keywords: list[str]) -> str:
    return KEYWORD_SEPARATOR.join(keywords)
