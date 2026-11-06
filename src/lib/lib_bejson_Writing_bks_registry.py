"""
Library:         lib_bejson_Writing_bks_registry.py
Family:          Writing
Module Purpose:  Single schema owner for BKS-1: every entity, field, type, requirement and enumeration, plus the 104db Fields generator and a generated entity reference.
Architecture:    BKS-1 (BEJSON Book Standard) Writing family. Non-AI book organisation layer built on the frozen Core family (field-map cache, atomic write, validator, list validator). Contains no AI calls and no Flask code. Book Documents are BEJSON 104db; plans are the JobMaker 104a job schema.
Format_Scope:    104db (Book Document) | 104a (JobMaker plan)
Release_Version: 300
Version:         see VERSION below
Date:            2026-10-29
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   0335954b-3c42-4ac1-b0d4-cb9ebce0079e
"""

import types
from typing import Dict, List, NamedTuple, Optional, Tuple

VERSION = "1.0.0"
BKS_SCHEMA_VERSION = "bks-1.0.0"
BKS_SCHEMA_PREFIX = "bks-1."
RECORD_TYPE_PARENT = "Record_Type_Parent"

# Entities stored inside one Book Document (104db), in canonical row order.
BOOK_DOCUMENT_ENTITIES = ("Book", "Chapter", "Generation", "Export")
# Entities that live in the shared library (one file each), never inside a Book Document.
LIBRARY_ENTITIES = ("Author", "Category", "BookType", "ContextAsset", "RegistryEntry")
ALL_ENTITIES = BOOK_DOCUMENT_ENTITIES + LIBRARY_ENTITIES

ENTITY_PREFIX = {
    "Book": "book", "Chapter": "chapter", "Generation": "generation", "Export": "export",
    "Author": "author", "Category": "category", "BookType": "booktype",
    "ContextAsset": "context", "RegistryEntry": "registry",
}

# Enumerations exactly as BKS-1 section 4.5. Extension export formats (epub, docx, pdf) are reserved ids and not valid values yet.
ENUMS = {
    "book_status_text": ("draft", "complete", "final", "archived"),
    "chapter_kind_text": ("front", "part", "chapter", "section", "back"),
    "chapter_status_text": ("planned", "drafted", "accepted", "rejected"),
    "generation_target_kind_text": ("plan", "chapter"),
    "generation_outcome_text": ("accepted", "rejected", "failed", "cancelled"),
    "export_format_text": ("md", "md_zip", "html", "txt", "json", "bejson"),
    "author_formality_text": ("casual", "neutral", "formal"),
    "author_verbosity_text": ("concise", "balanced", "expansive"),
    "context_file_format_text": ("txt", "code", "json", "bejson"),
    "context_study_instruction_text": ("learn_only", "direct_reference"),
    "registry_kind_text": ("book", "plan", "booktype", "author", "category", "template", "schema"),
    "booktype_family_text": ("nonfiction", "technical", "analysis", "creative"),
    "booktype_audit_profile_text": ("none", "standard", "strict"),
}

class FieldDef(NamedTuple):
    name: str
    type: str
    required: bool
    enum: Optional[Tuple[str, ...]]

def _f(name: str, typ: str, required: bool = False) -> FieldDef:
    return FieldDef(name, typ, required, ENUMS.get(name))

S, I, N, B, A = "string", "integer", "number", "boolean", "array"

_ENTITY_FIELDS: Dict[str, List[FieldDef]] = {
    "Book": [
        _f("book_uuid", S, True), _f("book_title_text", S, True), _f("book_subtitle_text", S),
        _f("book_topic_text", S, True), _f("book_goal_text", S), _f("book_booktype_uuid_fk", S),
        _f("book_booktype_slug_text", S, True), _f("book_author_uuid_fk", S), _f("book_author_name_text", S, True),
        _f("book_category_uuid_fk", S), _f("book_category_name_text", S), _f("book_plan_uuid_fk", S),
        _f("book_language_text", S, True), _f("book_audience_text", S), _f("book_summary_text", S),
        _f("book_cover_path_text", S), _f("book_tags_list", A), _f("book_version_text", S, True),
        _f("book_status_text", S, True), _f("book_chapter_count", I, True), _f("book_word_count", I, True),
        _f("book_content_sha256_text", S), _f("book_schema_version_text", S, True),
        _f("book_created_at", S, True), _f("book_updated_at", S, True),
    ],
    "Chapter": [
        _f("chapter_uuid", S, True), _f("chapter_book_uuid_fk", S, True), _f("chapter_parent_uuid_fk", S),
        _f("chapter_kind_text", S, True), _f("chapter_order_index", I, True), _f("chapter_title_text", S, True),
        _f("chapter_brief_text", S), _f("chapter_body_md", S), _f("chapter_status_text", S, True),
        _f("chapter_word_count", I, True), _f("chapter_audit_enabled_flag", B, True),
        _f("chapter_audit_passed_flag", B), _f("chapter_audit_fail_reason_text", S),
        _f("chapter_generation_uuid_fk", S), _f("chapter_created_at", S, True), _f("chapter_updated_at", S, True),
    ],
    "Generation": [
        _f("generation_uuid", S, True), _f("generation_target_kind_text", S, True),
        _f("generation_target_uuid_fk", S, True), _f("generation_provider_text", S), _f("generation_model_text", S),
        _f("generation_author_uuid_fk", S), _f("generation_prompt_sha256_text", S), _f("generation_temperature_value", N),
        _f("generation_max_tokens_count", I), _f("generation_input_tokens_count", I),
        _f("generation_output_tokens_count", I), _f("generation_attempt_index", I, True),
        _f("generation_outcome_text", S, True), _f("generation_error_code", I),
        _f("generation_started_at", S, True), _f("generation_finished_at", S),
    ],
    "Export": [
        _f("export_uuid", S, True), _f("export_book_uuid_fk", S, True), _f("export_format_text", S, True),
        _f("export_renderer_text", S, True), _f("export_theme_text", S), _f("export_path_text", S, True),
        _f("export_size_bytes_count", I), _f("export_sha256_text", S, True),
        _f("export_source_content_sha256_text", S, True), _f("export_created_at", S, True),
    ],
    "Author": [
        _f("author_uuid", S, True), _f("author_name_text", S, True), _f("author_email_text", S),
        _f("author_website_text", S), _f("author_github_text", S), _f("author_bio_text", S),
        _f("author_avatar_path_text", S), _f("author_archetype_text", S), _f("author_persona_text", S),
        _f("author_system_instruction_text", S), _f("author_tone_list", A), _f("author_forbidden_topics_list", A),
        _f("author_formality_text", S, True), _f("author_verbosity_text", S, True), _f("author_creativity_value", N, True),
        _f("author_max_response_tokens_count", I, True), _f("author_thinking_enabled_flag", B, True),
        _f("author_tools_list", A), _f("author_is_deleted_flag", B, True),
        _f("author_created_at", S, True), _f("author_updated_at", S, True),
    ],
    "Category": [
        _f("category_uuid", S, True), _f("category_name_text", S, True), _f("category_slug_text", S, True),
        _f("category_badge_color_hex", S, True), _f("category_is_deleted_flag", B, True),
        _f("category_created_at", S, True), _f("category_updated_at", S, True),
    ],
    "BookType": [
        _f("booktype_uuid", S, True), _f("booktype_slug_text", S, True), _f("booktype_name_text", S, True),
        _f("booktype_description_text", S), _f("booktype_family_text", S, True),
        _f("booktype_plan_instruction_text", S, True), _f("booktype_chapter_identity_text", S, True),
        _f("booktype_outline_template_list", A), _f("booktype_required_sections_list", A),
        _f("booktype_min_chapters_count", I, True), _f("booktype_max_chapters_count", I, True),
        _f("booktype_default_chapters_count", I, True), _f("booktype_min_words_per_chapter_count", I, True),
        _f("booktype_audit_profile_text", S, True), _f("booktype_default_exports_list", A),
        _f("booktype_is_builtin_flag", B, True), _f("booktype_schema_version_text", S, True),
        _f("booktype_created_at", S, True), _f("booktype_updated_at", S, True),
    ],
    "ContextAsset": [
        _f("context_uuid", S, True), _f("context_original_file_name_text", S, True),
        _f("context_file_format_text", S, True), _f("context_source_path_text", S, True),
        _f("context_size_bytes_count", I, True), _f("context_sha256_text", S, True),
        _f("context_study_instruction_text", S, True), _f("context_is_active_flag", B, True),
        _f("context_uploaded_at", S, True),
    ],
    "RegistryEntry": [
        _f("registry_uuid", S, True), _f("registry_kind_text", S, True), _f("registry_name_text", S, True),
        _f("registry_slug_text", S, True), _f("registry_file_path_text", S, True), _f("registry_target_uuid_fk", S),
        _f("registry_schema_version_text", S, True), _f("registry_created_at", S, True),
        _f("registry_updated_at", S, True),
    ],
}

# Why: callers read the schema through this accessor so no field name is ever typed as a literal in app code.
# Input: entity name. Output: ordered list of FieldDef.
def bks_registry_fields(entity: str) -> List[FieldDef]:
    return list(_ENTITY_FIELDS[entity])

# Why: lookups by field name are needed by the validator on every row; build once per entity.
# Input: entity name. Output: {field name: FieldDef}.
def bks_registry_field_defs(entity: str) -> Dict[str, FieldDef]:
    return {fd.name: fd for fd in _ENTITY_FIELDS[entity]}

# Why: attribute access (F.Book.book_title_text) gives the exact column name without a string literal.
# Output: namespace per entity whose attributes equal their own field names.
def _build_field_namespaces() -> types.SimpleNamespace:
    ns = types.SimpleNamespace()
    for entity, fields in _ENTITY_FIELDS.items():
        setattr(ns, entity, types.SimpleNamespace(**{fd.name: fd.name for fd in fields}))
    return ns

F = _build_field_namespaces()

# Why: the 104db Fields array (Record_Type_Parent first, then every Book Document field, each carrying its owning entity) must come from the registry only.
# Output: list of field dicts exactly as stored in a Book Document.
def bks_registry_book_document_fields() -> List[dict]:
    out = [{"name": RECORD_TYPE_PARENT, "type": "string"}]
    for entity in BOOK_DOCUMENT_ENTITIES:
        for fd in _ENTITY_FIELDS[entity]:
            out.append({"name": fd.name, "type": fd.type, "Record_Type_Parent": entity})
    return out

# Why: manifest primary keys and FK checks derive from naming rules, not a second table.
# Output: the primary-key field name of an entity (its first field).
def bks_registry_primary_key(entity: str) -> str:
    return _ENTITY_FIELDS[entity][0].name

# Why: foreign keys are declared by the _fk suffix (BKS-1 10.3).
# Output: list of foreign-key field names of an entity.
def bks_registry_foreign_keys(entity: str) -> List[str]:
    return [fd.name for fd in _ENTITY_FIELDS[entity] if fd.name.endswith("_fk")]

# Why: self-test used by the conformance suite: names are snake_case, prefixed per entity, and unique across all entities (104db needs unique names).
# Output: list of problem strings (empty when the registry is sound).
def bks_registry_self_check() -> List[str]:
    problems, seen = [], set()
    for entity, fields in _ENTITY_FIELDS.items():
        prefix = ENTITY_PREFIX[entity] + "_"
        for fd in fields:
            if not fd.name.startswith(prefix):
                problems.append(f"{entity}.{fd.name}: missing prefix {prefix}")
            if fd.name != fd.name.lower() or " " in fd.name:
                problems.append(f"{entity}.{fd.name}: not snake_case")
            if fd.name in seen:
                problems.append(f"{entity}.{fd.name}: duplicate field name")
            seen.add(fd.name)
            if fd.enum is None and fd.name in ENUMS:
                problems.append(f"{entity}.{fd.name}: enum not attached")
    return problems

# Why: handwritten schema docs are prohibited (10.8); the entity reference is generated from the registry.
# Output: Markdown text.
def bks_registry_markdown() -> str:
    lines = [f"# BKS-1 Entity Reference (generated, schema {BKS_SCHEMA_VERSION})", "",
             "Generated from `lib_bejson_Writing_bks_registry.py`. Do not edit by hand.", ""]
    for entity in ALL_ENTITIES:
        where = "Book Document" if entity in BOOK_DOCUMENT_ENTITIES else "library file"
        lines += [f"## {entity} ({where}, {len(_ENTITY_FIELDS[entity])} fields)", "",
                  f"Primary key: `{bks_registry_primary_key(entity)}`", "",
                  "| Field | Type | Required | Values |", "|---|---|---|---|"]
        for fd in _ENTITY_FIELDS[entity]:
            vals = ", ".join(fd.enum) if fd.enum else ""
            lines.append(f"| `{fd.name}` | {fd.type} | {'yes' if fd.required else 'no'} | {vals} |")
        lines.append("")
    return "\n".join(lines)
