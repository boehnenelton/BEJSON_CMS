"""
Library:       lib_bejson_CMS_taxonomy.py
Family:        lib_bejson_CMS
Description:   Canonical Prefix Registry and Field Alias Map for BEJSON_CMS.
               Single source of truth for all entity prefix tags, new canonical
               field names, and old->new field translation. All migration tools
               and Phase 5 blueprint updates import from this module.
               See docs/taxonomy_migration_tasks.md for step context.
Version:       1.0.0
Author:        Elton Boehnen
Date:          2026-08-10
RELATIONAL_ID: 7c3a5e9f-2b4d-4f6a-8e0c-1a9b7d5c3e2f
"""

from pathlib import Path
from typing import Dict, List, Optional

VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# CANONICAL PREFIX REGISTRY
# Each entry: entity_name -> {prefix, uuid_field, description}
# Prefix is the short tag prepended to all field names for that entity.
# uuid_field is the canonical synthetic UUID primary key for the entity.
# ---------------------------------------------------------------------------
TAXONOMY_PREFIX_REGISTRY: Dict[str, Dict] = {
    "PageRecord": {
        "prefix": "page_",
        "uuid_field": "page_uuid",          # already exists in live schema
        "description": "Page content records — articles, links, app-embeds"
    },
    "AuthorProfile": {
        "prefix": "author_",
        "uuid_field": "author_uuid",         # NEW — to be injected by migration
        "description": "Author persona/profile records"
    },
    "MediaAsset": {
        "prefix": "asset_",
        "uuid_field": "asset_uuid",          # NEW — to be injected by migration
        "description": "Locally uploaded binary media files"
    },
    "ExternalMedia": {
        "prefix": "extmedia_",
        "uuid_field": "extmedia_uuid",       # rename from media_uuid
        "description": "Externally hosted media embeds (YouTube, PDFs, etc.)"
    },
    "AdUnit": {
        "prefix": "ad_",
        "uuid_field": "ad_uuid",             # already exists in live schema
        "description": "Advertisement placements and banners"
    },
    "Category": {
        "prefix": "cat_",
        "uuid_field": "cat_uuid",            # NEW — to be injected by migration
        "description": "Taxonomy category records"
    },
    "NavLink": {
        "prefix": "nav_",
        "uuid_field": "nav_uuid",            # NEW — to be injected by migration
        "description": "Navigation link records"
    },
    "SiteConfig": {
        "prefix": "sys_",
        "uuid_field": "sys_uuid",            # NEW — to be injected by migration
        "description": "Site-wide configuration key-value records"
    },
    "SocialLink": {
        "prefix": "social_",
        "uuid_field": "social_uuid",         # NEW — to be injected by migration
        "description": "Social media profile link records"
    },
    "StandaloneApp": {
        "prefix": "app_",
        "uuid_field": "app_uuid",            # already exists in live schema
        "description": "Standalone HTML/JS mini-app records"
    },
    # AI_Profile intentionally excluded — out of scope for this taxonomy pass
}

# ---------------------------------------------------------------------------
# FIELD ALIAS MAP
# Each entry: entity_name -> {old_field_name: new_canonical_field_name}
# Only fields that CHANGE are listed. Fields already canonical are omitted.
# All new names follow <prefix>_<description> snake_case convention.
# ---------------------------------------------------------------------------
TAXONOMY_FIELD_ALIAS_MAP: Dict[str, Dict[str, str]] = {

    "AuthorProfile": {
        "auth_name":    "author_display_name",
        "auth_bio":     "author_bio",           # prefix normalise (was auth_)
        "auth_img":     "author_avatar_url",    # explicit: URL/path to avatar image
    },

    "Category": {
        "category_name":  "cat_name",
        "category_slug":  "cat_slug",
    },

    "PageRecord": {
        # page_ prefix already present on page_uuid, page_title, page_slug
        "category_ref":   "page_cat_name",      # transition: still stores name string
        "item_type":      "page_type",
        "created_at":     "page_created_at",
        "external_url":   "page_external_url",
        "author_ref":     "page_author_name",   # transition: still stores name string
        "featured_img":   "page_featured_img",  # keeps asset filename for now
        "template_key":   "page_template_key",  # prefix normalise
    },

    "MediaAsset": {
        # No prefix change (asset_ chosen but files currently unprefix'd)
        "filename":       "asset_filename",
        "original_name":  "asset_original_name",
        "file_hash":      "asset_file_hash",
        "file_size":      "asset_file_size",
        "mime_type":      "asset_mime_type",
        "uploaded_at":    "asset_uploaded_at",
    },

    "ExternalMedia": {
        "media_uuid":   "extmedia_uuid",
        "media_name":   "extmedia_name",
        "media_type":   "extmedia_type",
        "media_url":    "extmedia_url",
        "created_at":   "extmedia_created_at",
    },

    "AdUnit": {
        # ad_uuid, ad_name already canonical
        "ad_image":   "ad_banner_url",
        "ad_link":    "ad_target_url",
        # ad_zone, ad_active already canonical
    },

    "NavLink": {
        "nav_label":  "nav_display_label",
        "nav_url":    "nav_target_url",
    },

    "SiteConfig": {
        "config_key":    "sys_key",
        "config_value":  "sys_value",
    },

    "SocialLink": {
        "social_platform":  "social_platform_name",
        "social_url":       "social_target_url",
    },

    "StandaloneApp": {
        # app_uuid, app_name, app_slug already canonical
        "app_desc":   "app_description",
        "entry_file": "app_entry_file",
        "app_image":  "app_featured_img",
    },
}

# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

def taxonomy_get_prefix(entity_name: str) -> Optional[str]:
    """Return the canonical prefix tag for an entity, or None if not registered."""
    entry = TAXONOMY_PREFIX_REGISTRY.get(entity_name)
    return entry["prefix"] if entry else None


def taxonomy_get_uuid_field(entity_name: str) -> Optional[str]:
    """Return the canonical UUID primary key field name for an entity."""
    entry = TAXONOMY_PREFIX_REGISTRY.get(entity_name)
    return entry["uuid_field"] if entry else None


def taxonomy_resolve_field(entity_name: str, old_key: str) -> str:
    """Translate old_key to its canonical name for entity_name.
    Returns the old_key unchanged if no alias is registered (already canonical
    or out-of-scope field).
    """
    alias_map = TAXONOMY_FIELD_ALIAS_MAP.get(entity_name, {})
    return alias_map.get(old_key, old_key)


def taxonomy_translate_record(entity_name: str, record: Dict) -> Dict:
    """Return a new dict with all keys translated to canonical field names.
    Does NOT modify the input dict.
    """
    alias_map = TAXONOMY_FIELD_ALIAS_MAP.get(entity_name, {})
    return {alias_map.get(k, k): v for k, v in record.items()}


def taxonomy_validate_entity_fields(entity_name: str, field_names: List[str]) -> Dict:
    """Check a list of field names against the alias map for entity_name.
    Returns a dict: {
        'known_old': [...],    # fields that have a registered alias
        'already_canonical': [...],  # fields not in alias map (assumed canonical)
        'unknown': [],         # always empty in current design (all pass through)
    }
    """
    alias_map = TAXONOMY_FIELD_ALIAS_MAP.get(entity_name, {})
    result = {"known_old": [], "already_canonical": []}
    for f in field_names:
        if f in alias_map:
            result["known_old"].append(f)
        else:
            result["already_canonical"].append(f)
    return result


def taxonomy_list_entities() -> List[str]:
    """Return all entity names in the prefix registry."""
    return list(TAXONOMY_PREFIX_REGISTRY.keys())


def taxonomy_full_report() -> str:
    """Return a human-readable table of all prefix registry entries
    and their field alias maps, for verification."""
    lines = []
    lines.append("=" * 70)
    lines.append("BEJSON CMS TAXONOMY REGISTRY REPORT")
    lines.append(f"lib_bejson_CMS_taxonomy.py v{VERSION}")
    lines.append("=" * 70)
    for entity, meta in TAXONOMY_PREFIX_REGISTRY.items():
        lines.append(f"\n  Entity:  {entity}")
        lines.append(f"  Prefix:  {meta['prefix']}")
        lines.append(f"  UUID:    {meta['uuid_field']}")
        lines.append(f"  Desc:    {meta['description']}")
        aliases = TAXONOMY_FIELD_ALIAS_MAP.get(entity, {})
        if aliases:
            lines.append("  Field aliases (old -> new):")
            for old, new in aliases.items():
                lines.append(f"    {old:<28} -> {new}")
        else:
            lines.append("  Field aliases: (none — all fields already canonical)")
        lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)
