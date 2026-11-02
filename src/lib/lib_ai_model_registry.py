"""
# ============================================================
# File:         lib_ai_model_registry.py
# Description:  Centralized AI model registry library.
#               Populates default models for every non-auto-generating
#               service (Gemini, Groq, Grok, HuggingFace, Ollama), pulls
#               live OpenRouter and TokenRoute model catalogs, and writes
#               everything back to ai_model_registry.bejson. Clients
#               (the chat client and, as of 1.1.0, the CLI tools when
#               model_registry_source=unified) source service/model lists
#               from this registry as the single source of truth.
#               When portable_mode is False, live API updates are
#               enabled. When True, only the local registry file is
#               consulted.
# Version:      1.5.0
# Date Created: 2026-09-16
# Author:       Elton Boehnen · boehnenelton2024@gmail.com
#               boehnenelton2024.pages.dev · github.com/boehnenelton
# RELATIONAL_ID: a3f7c821-5d4e-4b91-bc2e-1e8f0d3c9a47
#
# Changelog:
#   1.5.0 (2026-10-20) -- Added static service "LiteRTLM" (on-device LiteRT-LM
#         server, provider key "litertlm"; default model gemma-4-e2b). Seeded into
#         existing registry files via ADDED_STATIC_SERVICES (additive only).
#   1.4.0 (2026-10-12) -- Added static service "OllamaLocal" (local Ollama
#         server, provider key "ollamalocal"). load() back-fills the defaults of
#         services listed in ADDED_STATIC_SERVICES into an existing
#         registry file (additive only; existing entries and user edits
#         are never touched), so adding a service no longer requires
#         deleting ai_model_registry.bejson.
#   1.2.1 (2026-09-18) -- Drift consolidation: this file forked from
#         1.1.0 into two branches -- this one (free-tier filtering,
#         get_model_source_type) and a parallel branch that fixed a
#         strict-104-format violation (a "Schema_Name" custom key,
#         disallowed for Format_Version "104", which was already invalid
#         before either branch and got caught when the file was wired
#         into menu_cli's validator). Re-removed "Schema_Name" from the
#         schema-generation dict here (the parallel branch's only actual
#         code change to this file) to merge both branches' work. No
#         other changes in this pass.
#   1.3.0 (2026-09-22) -- Merged in FALLBACK_DEFAULTS from a second
#         parallel branch (update.md-driven session, PKG22 drift): a
#         single free-tier fallback model per AUTO_GENERATING_SERVICE
#         (OpenRouter, TokenRoute), seeded alongside the static defaults
#         so the UI is never actually empty for these two before a live
#         refresh succeeds -- this is the exact "No models found" gap
#         observed and left unresolved earlier this session. On-disk
#         ai_model_registry.bejson migrated in place (seeding only fires
#         on an empty record set, and the file already had rows).
#   1.2.0 (2026-09-18) -- Added get_model_source_type(service) returning
#         "hardcoded" or "remote" (wraps is_auto_generating with the
#         naming Elton asked for) so client/app.py can decide whether a
#         refresh control makes sense for a service without hardcoding
#         service names itself. Filtered _fetch_openrouter/_fetch_tokenroute
#         to free-tier models only (was: every model, paid included) -
#         OpenRouter via its documented pricing object (prompt/completion
#         both "0") or its real ":free" ID-suffix convention; TokenRoute
#         via the same pricing check plus its own "-free" (hyphen, not
#         OpenRouter's colon) ID-suffix convention, confirmed directly
#         from lib/AI/config/tokenrouter_model_registry.104a.bejson rather
#         than assumed - an initial guess that TokenRoute also used a
#         colon was wrong and caught by testing before delivery. Records
#         from either now carry flag="free" instead of None.
#   1.1.0 (2026-09-16) -- Added the service classification GEMINI.MD's
#         "MODEL CLASSIFICATIONS" section asked for: STATIC_SERVICES
#         (Gemini, Groq, Grok, HuggingFace, Ollama -- can't auto-populate,
#         seeded from static defaults) vs AUTO_GENERATING_SERVICES
#         (OpenRouter, TokenRoute -- pull their own live catalog).
#         Generalized _seed_gemini_defaults() -> _seed_static_defaults()
#         to seed every STATIC_SERVICES entry, not just Gemini, so CLI
#         tools switching to this registry (model_registry_source=unified)
#         have real data for Groq/Grok/HuggingFace/Ollama instead of an
#         empty list. GEMINI_DEFAULTS kept as an alias of
#         STATIC_DEFAULTS["Gemini"] for backward compatibility -- nothing
#         outside this file is known to import it directly, but no reason
#         to break it if something does. update_registry()'s live-fetch
#         behavior is unchanged: still OpenRouter + TokenRoute only.
# ============================================================
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

import requests

_logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────
REGISTRY_FILENAME = "ai_model_registry.bejson"

# Services that cannot auto-populate their own model list (no free-tier
# list endpoint, or intentionally curated) -- seeded from STATIC_DEFAULTS
# below and left alone otherwise (same "only regenerate when the record
# set is empty" rule GEMINI.MD specifies for Gemini, now applied to all).
STATIC_SERVICES = ("Gemini", "Groq", "Grok", "HuggingFace", "Ollama", "OllamaLocal", "LiteRTLM")

# Services with a live models-list endpoint this registry can pull from.
AUTO_GENERATING_SERVICES = ("OpenRouter", "TokenRoute")

SUPPORTED_SERVICES = STATIC_SERVICES + AUTO_GENERATING_SERVICES

# Static services introduced after the first release. Only these are
# back-filled into an existing registry file (see load()); a service a user
# deliberately removed from an older file is not resurrected.
ADDED_STATIC_SERVICES = ("OllamaLocal", "LiteRTLM")

# Static defaults per non-auto-generating service. Each seeded from that
# service's current CLI default_model_id (see CLI/<service>_cli/
# *_cli_config.104a.bejson) -- one confirmed-working entry per service
# rather than a fabricated fuller catalog. Elton can expand these directly
# in ai_model_registry.bejson at any time; this registry will not
# overwrite or remove entries once the file exists (see load()).
STATIC_DEFAULTS = {
    "Gemini": [
        {"service": "Gemini", "model_id": "gemini-3.8-flash",      "model_name": "Gemini 3.8 Flash",      "flag": None},
        {"service": "Gemini", "model_id": "gemini-3.7-flash",      "model_name": "Gemini 3.7 Flash",      "flag": None},
        {"service": "Gemini", "model_id": "gemini-3.6-flash",      "model_name": "Gemini 3.6 Flash",      "flag": None},
        {"service": "Gemini", "model_id": "gemini-3.5-flash",      "model_name": "Gemini 3.5 Flash",      "flag": None},
        {"service": "Gemini", "model_id": "gemini-3.5-flash-lite", "model_name": "Gemini 3.5 Flash Lite", "flag": None},
    ],
    "Groq": [
        {"service": "Groq", "model_id": "openai/gpt-oss-120b", "model_name": "GPT-OSS 120B", "flag": None},
    ],
    "Grok": [
        {"service": "Grok", "model_id": "grok-4.6", "model_name": "Grok 4.6", "flag": None},
    ],
    "HuggingFace": [
        {"service": "HuggingFace", "model_id": "openai/gpt-oss-120b", "model_name": "GPT-OSS 120B", "flag": None},
    ],
    "Ollama": [
        {"service": "Ollama", "model_id": "gpt-oss:120b-cloud", "model_name": "GPT-OSS 120B Cloud", "flag": None},
    ],
    "LiteRTLM": [
        {"service": "LiteRTLM", "model_id": "gemma-4-e2b", "model_name": "Gemma 4 E2B", "flag": None},
    ],
    "OllamaLocal": [
        {"service": "OllamaLocal", "model_id": "qwen2.5-coder:1.5b", "model_name": "Qwen2.5-Coder 1.5B", "flag": None},
        {"service": "OllamaLocal", "model_id": "qwen2.5-coder:0.5b", "model_name": "Qwen2.5-Coder 0.5B", "flag": None},
        {"service": "OllamaLocal", "model_id": "qwen2.5-coder:3b",   "model_name": "Qwen2.5-Coder 3B",   "flag": None},
        {"service": "OllamaLocal", "model_id": "qwen2.5-coder:7b",   "model_name": "Qwen2.5-Coder 7B",   "flag": None},
    ],
}

# Backward-compat alias -- see changelog note above.
GEMINI_DEFAULTS = STATIC_DEFAULTS["Gemini"]

# Fallback defaults for AUTO_GENERATING_SERVICES -- seeded into the
# registry when it's first created so the UI always has at least one
# working model per service, even when the live API fetch fails (no
# API key configured, no network, endpoint down). These get replaced
# by the real live catalog the first time update_registry() succeeds.
# (This is why OpenRouter/TokenRoute showed "No models found" in earlier
# testing this session -- there was no fallback until now.)
FALLBACK_DEFAULTS = {
    "OpenRouter": [
        {"service": "OpenRouter", "model_id": "google/gemma-4-31b-it:free", "model_name": "Google: Gemma 4 31B (free)", "flag": "free"},
    ],
    "TokenRoute": [
        {"service": "TokenRoute", "model_id": "z-ai/glm-5.3-free", "model_name": "Z.AI GLM 5.3 (free)", "flag": "free"},
    ],
}


# ── BEJSON Helpers ───────────────────────────────────────────

def _build_field_map(fields: list) -> dict:
    """Build O(1) Field Map Cache from BEJSON Fields array."""
    return {f["name"].strip(): i for i, f in enumerate(fields)}


def _registry_to_bejson(records: list) -> dict:
    """Serialize a list of record dicts back to BEJSON 104 structure."""
    fields = [
        {"name": "service",    "type": "string", "description": "Service provider"},
        {"name": "model_id",   "type": "string", "description": "Canonical API model ID"},
        {"name": "model_name", "type": "string", "description": "Human-readable display name"},
        {"name": "flag",       "type": "string", "description": "Optional tag — null means unclassified, ignored by tooling"},
    ]
    values = [
        [r["service"], r["model_id"], r["model_name"], r.get("flag")]
        for r in records
    ]
    return {
        "Format":         "BEJSON",
        "Format_Version": "104",
        "Format_Creator": "Elton Boehnen",
        "Records_Type":   ["AIModel"],
        "Fields":         fields,
        "Values":         values,
    }


def _bejson_to_records(data: dict) -> list:
    """Parse a BEJSON 104 document into a list of record dicts using Field Map Cache."""
    fmap = _build_field_map(data.get("Fields", []))
    records = []
    for row in data.get("Values", []):
        record = {}
        for field_name, idx in fmap.items():
            record[field_name] = row[idx] if idx < len(row) else None
        records.append(record)
    return records


# ── Registry Core ────────────────────────────────────────────

class AIModelRegistry:
    """
    Centralized AI model registry.

    Usage:
        reg = AIModelRegistry(registry_path, api_keys)
        reg.load()
        reg.update_registry()          # pull live from OpenRouter + TokenRoute
        models = reg.get_models("OpenRouter")
    """

    def __init__(self, registry_path: str, api_keys: dict):
        self.registry_path = Path(registry_path)
        self.api_keys = api_keys
        self._records: list = []

    # ── I/O ─────────────────────────────────────────────────

    def load(self) -> "AIModelRegistry":
        """Load registry from disk. Seeds Gemini defaults if file is missing or empty."""
        if self.registry_path.exists():
            try:
                with open(self.registry_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._records = _bejson_to_records(data)
                _logger.info("Registry loaded: %d records from %s", len(self._records), self.registry_path)
            except Exception as e:
                _logger.warning("Failed to load registry (%s). Seeding defaults.", e)
                self._records = []
        else:
            _logger.info("Registry file not found. Creating and seeding defaults.")
            self._records = []

        if not self._records:
            self._seed_static_defaults()
            self._save()
        else:
            # Additive migration: a static service added in a later release
            # (e.g. OllamaLocal) is seeded into an existing file without
            # touching any existing record.
            present = {r.get("service") for r in self._records}
            missing = [svc for svc in ADDED_STATIC_SERVICES if svc not in present]
            if missing:
                for svc in missing:
                    self._records.extend(dict(e) for e in STATIC_DEFAULTS[svc])
                _logger.info("Seeded newly added static service(s): %s", ", ".join(missing))
                self._save()

        return self

    def _save(self):
        """Write current records back to the BEJSON registry file."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        doc = _registry_to_bejson(self._records)
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)
        _logger.info("Registry saved: %d records to %s", len(self._records), self.registry_path)

    # ── Seeding ──────────────────────────────────────────────

    def _seed_static_defaults(self):
        """Populate every STATIC_SERVICES entry's static defaults into the
        record list. Also seeds FALLBACK_DEFAULTS for AUTO_GENERATING_SERVICES
        so the UI always has at least one model per service even without a
        live fetch."""
        for service, defaults in STATIC_DEFAULTS.items():
            existing_ids = {r["model_id"] for r in self._records if r.get("service") == service}
            for entry in defaults:
                if entry["model_id"] not in existing_ids:
                    self._records.append(dict(entry))
        _logger.info("Static defaults seeded for: %s", ", ".join(STATIC_DEFAULTS.keys()))

        for service, defaults in FALLBACK_DEFAULTS.items():
            existing_ids = {r["model_id"] for r in self._records if r.get("service") == service}
            if not existing_ids:
                for entry in defaults:
                    self._records.append(dict(entry))
                _logger.info("Seeded fallback defaults for: %s", service)

    # ── Live Fetches ─────────────────────────────────────────

    def _fetch_openrouter(self) -> list:
        """Pull live model catalog from OpenRouter GET /v1/models, filtered
        to free-tier models only. OpenRouter's pricing object gives
        per-token cost as a string ("0" for free); a model is treated as
        free only when BOTH prompt and completion cost 0 - that's the
        authoritative signal. The well-known ":free" ID suffix convention
        is checked too (OR'd in), since some free listings have been seen
        with pricing fields that don't cleanly parse - belt and
        suspenders, not a replacement for the pricing check."""
        api_key = self.api_keys.get("OPENROUTER_KEY_1")
        if not api_key:
            _logger.warning("OPENROUTER_KEY_1 not found in API keys.")
            return []
        try:
            resp = requests.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            total = len(data)
            free = [m for m in data if m.get("id") and self._is_free_model(m)]
            records = [
                {
                    "service":    "OpenRouter",
                    "model_id":   m["id"],
                    "model_name": m.get("name", m["id"]),
                    "flag":       "free",
                }
                for m in free
            ]
            _logger.info("OpenRouter: fetched %d free models (of %d total).", len(records), total)
            return records
        except Exception as e:
            _logger.error("OpenRouter fetch failed: %s", e)
            return []

    @staticmethod
    def _is_free_model(model: dict) -> bool:
        pricing = model.get("pricing") or {}
        try:
            prompt_cost = float(pricing.get("prompt", "1") or "1")
            completion_cost = float(pricing.get("completion", "1") or "1")
            if prompt_cost == 0.0 and completion_cost == 0.0:
                return True
        except (TypeError, ValueError):
            pass
        model_id = str(model.get("id", ""))
        # OpenRouter's real, documented convention uses a colon
        # ("meta-llama/llama-3.1-8b-instruct:free"). TokenRoute's own
        # config (lib/AI/config/tokenrouter_model_registry.104a.bejson)
        # shows it uses a hyphen instead ("z-ai/glm-5.3-free",
        # "glm-5.3-free") - confirmed directly from this project's data,
        # not assumed. Both are checked since either service could hit
        # this shared method.
        return model_id.endswith(":free") or model_id.endswith("-free")

    def _fetch_tokenroute(self) -> list:
        """Pull live model catalog from TokenRoute GET /v1/models, filtered
        to free-tier models only. TokenRoute's exact pricing field shape
        isn't documented anywhere in this project (unlike OpenRouter's,
        which is public/stable). Its own model registry config
        (lib/AI/config/tokenrouter_model_registry.104a.bejson) confirms it
        uses a hyphenated "-free" ID suffix (z-ai/glm-5.3-free,
        glm-5.3-free) - not OpenRouter's colon convention - so that's the
        primary filter here (see _is_free_model, which checks both). A
        pricing object shaped like OpenRouter's is also checked in case
        TokenRoute's API returns one, but the suffix is the only signal
        confirmed by evidence already in this project."""
        api_key = self.api_keys.get("TOKENROUTER_KEY_1")
        if not api_key:
            _logger.warning("TOKENROUTER_KEY_1 not found in API keys.")
            return []
        try:
            resp = requests.get(
                "https://api.tokenrouter.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=15,
            )
            resp.raise_for_status()
            raw = resp.json()
            items = raw if isinstance(raw, list) else raw.get("data", [])
            total = len(items)
            free = [m for m in items if m.get("id") and self._is_free_model(m)]
            records = [
                {
                    "service":    "TokenRoute",
                    "model_id":   m.get("id"),
                    "model_name": m.get("name", m.get("id", "")),
                    "flag":       "free",
                }
                for m in free
            ]
            _logger.info("TokenRoute: fetched %d free models (of %d total).", len(records), total)
            return records
        except Exception as e:
            _logger.error("TokenRoute fetch failed: %s", e)
            return []

    # ── Public API ───────────────────────────────────────────

    def update_registry(self, services: Optional[list] = None):
        """
        Pull live model lists for the specified services (default: OpenRouter + TokenRoute).
        Replaces existing records for each fetched service, keeps others intact.
        Persists result to disk.
        """
        if services is None:
            services = ["OpenRouter", "TokenRoute"]

        fetchers = {
            "OpenRouter": self._fetch_openrouter,
            "TokenRoute": self._fetch_tokenroute,
        }

        for service in services:
            if service not in fetchers:
                _logger.warning("No live fetcher for service '%s'. Skipping.", service)
                continue

            live = fetchers[service]()
            if live:
                # Drop all existing records for this service, replace with fresh live data
                self._records = [r for r in self._records if r.get("service") != service]
                self._records.extend(live)
                _logger.info("Registry updated for %s: %d records.", service, len(live))
            else:
                _logger.warning("No models fetched for %s — existing records retained.", service)

        self._save()

    def get_models(self, service: str) -> list:
        """
        Return all model records for a given service as a list of
        {"id": model_id, "name": model_name} dicts, sorted by name.
        Suitable for direct use in API responses and UI dropdowns.
        """
        results = [
            {"id": r["model_id"], "name": r["model_name"]}
            for r in self._records
            if r.get("service") == service and r.get("model_id")
        ]
        return sorted(results, key=lambda x: x["name"])

    def get_all_records(self) -> list:
        """Return raw record list for debugging or export."""
        return list(self._records)

    def get_services(self) -> list:
        """Return sorted list of unique service names present in the registry."""
        return sorted({r["service"] for r in self._records if r.get("service")})

    @staticmethod
    def is_auto_generating(service: str) -> bool:
        """True if `service` can pull its own live model catalog (see AUTO_GENERATING_SERVICES)."""
        return service in AUTO_GENERATING_SERVICES

    @staticmethod
    def get_model_source_type(service: str) -> str:
        """Returns "hardcoded" for a STATIC_SERVICES entry (Gemini, Groq,
        Grok, HuggingFace, Ollama - no live list endpoint, seeded once and
        never auto-overwritten) or "remote" for an AUTO_GENERATING_SERVICES
        entry (OpenRouter, TokenRoute - synced live via update_registry()).
        A UI can use this to decide, e.g., whether a refresh control makes
        sense for a given service at all, without hardcoding service names
        itself - see client/app.py's /api/models."""
        if service in AUTO_GENERATING_SERVICES:
            return "remote"
        return "hardcoded"

