"""
Library:        lib_bejson_AI_bejson_gemini.py
Family:         AI
Description:    Integration wrapper for Google Gemini API using the official
                 google-genai SDK. This wraps generate_content
                 (single-shot / non-agentic generation). For function
                 calling, multi-turn tool loops, attachments, or
                 previous_interaction_id-based chat, use the new sibling
                 module lib_bejson_AI_bejson_interactions.py instead — the
                 Interactions API is the recommended endpoint going forward
                 per the gemini-interactions-api skill.
Version:        2.5.0
Date:           2026-08-22
Author:         Elton Boehnen
Contact:        eltonboehnen@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  4c8e1f26-7b3d-49a5-8e0f-1d6c3a9b7e42
Release_Version: 300

Changelog:
  2.5.0 (2026-08-22) -- Registry overhaul: GeminiKeyRegistry/
          GeminiModelRegistry moved to self-contained lib/AI/config/
          storage (no more {ADMIN_ROOT}/{HOME} paths) with
          config_version=2, matching the same pass applied to groq.py/
          openrouter.py/grok.py (3.0.0/2.0.0). Root cause: a stale on-disk
          model registry with a decommissioned model still marked
          currently_active used to load successfully and stay wrong
          forever -- see ai_registry_base.py's 2.0.0 changelog. (2026-09-04
          note: this Version header previously still said "2.4.1" while
          the VERSION constant below already said "2.5.0" -- same class of
          drift as prompt_menu.py's 1.0.0/1.4.0 mismatch fixed earlier;
          synced here during a full-project staleness sweep, header text
          only, no logic touched.)
  2.4.1 - Modularization: GeminiKeyRegistry/GeminiModelRegistry now subclass
          lib_bejson_AI_ai_registry_base.py's shared atomic base (same
          migration done for Groq 2.1.6 and OpenRouter 2.1.7). Behavior
          preserved exactly, including the total-load-failure fallback
          rebuilding thinking/search positionally from SCHEMA_MODEL_REGISTRY
          (kept via a load() override, not just the base's generic
          fallback). Original single-var GEMINI_API_KEYS env convention is
          kept working; ALSO now reads the numbered-slot convention
          (GEMINI_KEY_1.._21) actually used in the live secure env store,
          which the original code never read at all. Verified: both env
          conventions load together correctly with gaps skipped, model list
          + thinking/search fields + active_model_id all match
          pre-migration output.
  2.4.0 - Applied NewAgent's fatal/recoverable error-handling principles
          (lib_bejson_newagent_errors.py) to GeminiAPI.generate(): SDK-
          missing and no-keys conditions now raise typed AIFatalError
          subclasses (SDKNotInstalledError, NoAPIKeysError) instead of bare
          RuntimeError/Exception; generation-call failures are classified
          via _classify_generation_error() into typed AIRecoverableError
          subclasses (RateLimitedError, NetworkError, AuthError,
          ProviderServerError, GenerationError) using the same plain-
          language substring matching NewAgent's agent.py loop uses on raw
          exception text. New codes 211-216 in
          lib_bejson_AI_bejson_errors.py 1.2.0. Verified: all 5
          classification categories tested against representative error
          strings; fatal path (no SDK) confirmed to raise AIFatalError and
          still come back clean through ai_dispatch.py as
          AIResponse(success=False).
  2.3.3 - AI-family common-interface design pass: added STD_KEY_PATH,
          STD_MODEL_PATH, and get_standard_api() -- Gemini was the only
          provider in the family with no zero-config factory, which is part
          of why lib_bejson_AI_ai_dispatch.py's provider adapters couldn't
          treat it the same as Groq/OpenRouter. Purely additive: GeminiAPI,
          GeminiKeyRegistry, and GeminiModelRegistry are unchanged.
  2.3.2 - AI-family audit fix: Core dependency import failure was calling
          sys.exit(1), killing the entire host process instead of raising a
          catchable ImportError -- the only module in the family doing this
          (every sibling uses try/except ImportError to degrade gracefully).
          Now raises normally after logging.
  2.3.0 - Default active model updated to "gemini-3.6-flash" (released
          2026-07-21, supersedes 3.5 Flash as the Flash-tier default).
  2.2.0 - Default active model updated from the legacy "gemini-2.5-flash"
          fallback to "gemini-3.5-flash" (current GA default workhorse per
          gemini-api-dev skill). No behavioral/API changes otherwise —
          generate_content call shape is untouched.
"""

import os
import sys
import json
import time
import random
import copy
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    from google import genai
    from google.genai import types
except ImportError:
    # We don't crash here to allow registry management without the SDK, 
    # but the API class will fail if used.
    genai = None

# --- Sibling Resolution ---
LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if LIB_DIR not in sys.path: sys.path.insert(0, LIB_DIR)

CORE_DIR = os.path.join(os.path.dirname(LIB_DIR), "Core")
if CORE_DIR not in sys.path: sys.path.insert(0, CORE_DIR)

VERSION = "2.5.0"  # 2026-08-22: registry overhaul -- self-contained config/
                    # subfolder (no more {ADMIN_ROOT}/{HOME} paths) +
                    # config_version=2 on both registries, matching the
                    # groq.py/openrouter.py/grok.py 3.0.0/2.0.0 pass. See
                    # ai_registry_base.py 2.0.0 changelog for the root
                    # cause (a stale on-disk model file with a dead model
                    # still marked currently_active used to load
                    # successfully and stay wrong forever).

try:
    from lib_bejson_Core_bejson_core import (
        bejson_core_load_file, 
        bejson_core_get_field_index, 
        bejson_core_get_field_map,
        bejson_core_atomic_write
    )
    from lib_bejson_Core_bejson_schema import SCHEMA_MODEL_REGISTRY_GEMINI as SCHEMA_MODEL_REGISTRY
    from lib_bejson_AI_bejson_errors import (
        NoAPIKeysError, SDKNotInstalledError,
        RateLimitedError, NetworkError, AuthError, ProviderServerError, GenerationError,
    )
    from lib_bejson_AI_ai_registry_base import (
        RoundRobinKeyRegistry, ModelRegistryBase, get_self_contained_dir,
    )

    # Config_Version for this provider's stores -- bump whenever
    # SCHEMA_MODEL_REGISTRY's default lineup changes. Self-contained
    # storage: this library's own config/ subfolder, no {ADMIN_ROOT}/...
    # or {HOME}/... dependency. See ai_registry_base.py's ensure_current().
    GEMINI_CONFIG_VERSION = 2
    CONFIG_DIR = get_self_contained_dir(__file__)
    _CORE_IMPORT_ERROR = None
except ImportError as e:
    # 2.3.2: was sys.exit(1) here -- killed the entire host process on import
    # (Flask server, CLI agent, orchestrator, whatever imported this module),
    # inconsistent with every other AI-family module's try/except ImportError
    # graceful-degradation convention (see lib_bejson_AI_ai_context_bubble.py).
    # Now stores the error and raises a normal ImportError so a caller doing
    # `try: import lib_bejson_AI_bejson_gemini / except ImportError:` -- the
    # same pattern used elsewhere in this family -- can actually catch it.
    _CORE_IMPORT_ERROR = e
    logging.error(f"[GeminiLib] Missing core dependencies: {e}")
    raise

# --- Legacy Fallback Constants ---
_GEMINI_MODEL_LEGACY = {
    "model_name": 0, 
    "model_id": 1, 
    "currently_active": 2,
    "thinking_enabled": 3, 
    "google_search_enabled": 4
}

# --- Registry Managers ---
# 2.4.1: GeminiKeyRegistry/GeminiModelRegistry now subclass the shared
# AI-family atomic base, same migration already done for Groq (2.1.6) and
# OpenRouter (2.1.7). load() is overridden on both rather than relying
# solely on _extra_fields(), to preserve two Gemini-specific behaviors the
# base doesn't have: (1) the original comma-joined GEMINI_API_KEYS env var
# is kept working alongside the new GEMINI_KEY_1.._21 numbered-slot
# convention (confirmed against the live secure env store), and (2) the
# total-load-failure fallback rebuilds thinking/search positionally from
# SCHEMA_MODEL_REGISTRY rather than the base's generic single-entry
# fallback.

class GeminiKeyRegistry(RoundRobinKeyRegistry):
    def __init__(self, file_path: Union[str, Path]):
        default_schema = {
            "Format": "BEJSON", "Format_Version": "104", "Records_Type": ["ApiKey"],
            "Fields": [{"name": "key", "type": "string"}],
            "Values": [[os.getenv("GEMINI_API_KEY", "YOUR_KEY_HERE")]],
        }
        super().__init__(
            file_path,
            placeholder_markers=["YOUR_KEY"],
            env_var="GEMINI_API_KEYS",       # original single-var convention, kept
            env_var_prefix="GEMINI_KEY",     # actual numbered-slot convention in use
            env_var_max_slots=21,
            default_schema=default_schema,
            config_version=GEMINI_CONFIG_VERSION,
        )


class GeminiModelRegistry(ModelRegistryBase):
    def __init__(self, file_path: Union[str, Path]):
        super().__init__(
            file_path,
            # 2.3.0: default updated to "gemini-3.6-flash" (released
            # 2026-07-21, supersedes 3.5 Flash as Google's Flash-tier default)
            default_model_id="gemini-3.6-flash",
            default_rows_factory=lambda: SCHEMA_MODEL_REGISTRY,
            config_version=GEMINI_CONFIG_VERSION,
        )

    def _extra_fields(self, row, fmap):
        think_idx = fmap.get("thinking_enabled", _GEMINI_MODEL_LEGACY["thinking_enabled"])
        search_idx = fmap.get("google_search_enabled", _GEMINI_MODEL_LEGACY["google_search_enabled"])
        return {
            "thinking": row[think_idx] if think_idx != -1 and think_idx < len(row) else False,
            "search": row[search_idx] if search_idx != -1 and search_idx < len(row) else False,
        }

    def load(self) -> None:
        try:
            data = bejson_core_load_file(str(self.file_path))
            fi = bejson_core_get_field_map(data)
            id_idx = fi.get("model_id", _GEMINI_MODEL_LEGACY["model_id"])
            act_idx = fi.get("currently_active", _GEMINI_MODEL_LEGACY["currently_active"])
            self.models = []
            for row in data["Values"]:
                m_info = {"id": row[id_idx], **self._extra_fields(row, fi)}
                self.models.append(m_info)
                if row[act_idx] is True:
                    self.active_model_id = row[id_idx]
        except Exception:
            for row in SCHEMA_MODEL_REGISTRY["Values"]:
                self.models.append({"id": row[1], "thinking": row[3], "search": row[4]})

    def get_model_info(self, model_id: Optional[str] = None) -> Dict[str, Any]:
        tid = model_id or self.active_model_id
        return next((m for m in self.models if m["id"] == tid), {"id": tid, "thinking": False, "search": False})

# --- Main API Interface ---

class GeminiAPI:
    def __init__(self, key_registry: GeminiKeyRegistry, model_registry: GeminiModelRegistry):
        self.keys = key_registry
        self.models = model_registry
        if genai is None:
            logging.error("[GeminiLib] google-genai SDK not installed. Please run 'pip install google-genai'.")

    def generate(self, prompt: str, model_id: str = None, **config) -> str:
        if genai is None:
            # Fatal: nothing can succeed without the SDK. Was `raise
            # RuntimeError(...)` -- now a typed AIFatalError subclass per
            # NewAgent's fatal/recoverable pattern (see
            # lib_bejson_AI_bejson_errors.py 1.2.0).
            raise SDKNotInstalledError(
                "google-genai SDK not installed. Run 'pip install google-genai'.")
        if not self.keys.keys:
            # Fatal: no key rotation can help if there are zero keys at all.
            raise NoAPIKeysError("No Gemini API keys found.")

        key = random.choice(self.keys.keys)
        mid = model_id or self.models.active_model_id
        
        client = genai.Client(api_key=key)
        
        # Prepare configuration
        gen_config = {}
        if "temperature" in config: gen_config["temperature"] = config["temperature"]
        if "top_p" in config: gen_config["top_p"] = config["top_p"]
        if "top_k" in config: gen_config["top_k"] = config["top_k"]
        if "max_output_tokens" in config: gen_config["max_output_tokens"] = config["max_output_tokens"]
        if "stop_sequences" in config: gen_config["stop_sequences"] = config["stop_sequences"]
        
        system_instruction = config.get("system_instruction")
        
        try:
            response = client.models.generate_content(
                model=mid,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    **gen_config
                )
            )
            return response.text
        except Exception as e:
            logging.error(f"[GeminiLib] Generation failed: {e}")
            raise _classify_generation_error(e)


def _classify_generation_error(e: Exception) -> Exception:
    """
    Turns a raw SDK exception into one of the typed AIRecoverableError
    subclasses, same plain-language substring classification NewAgent's
    agent.py main loop uses on its own exception strings (rate limit,
    network, auth, server error) -- moved here so gemini.py raises the
    right type itself instead of every caller re-deriving it from a string.
    All of these are recoverable, not fatal: one bad call (wrong key in a
    rotation, a transient network blip, a provider hiccup) doesn't mean the
    next call will also fail. A caller that wants NewAgent's circuit-
    breaker behavior (escalate to fatal after N consecutive recoverable
    failures) still owns that counting -- this function only classifies.
    """
    text = str(e)
    low = text.lower()

    if "429" in text or "rate limit" in low or "resource_exhausted" in low:
        return RateLimitedError(f"Gemini rate limited: {text}")
    if ("no address associated with hostname" in low or "urlopen error" in low
            or "connection" in low or "network" in low or "timed out" in low):
        return NetworkError(f"Gemini network error: {text}")
    if ("401" in text or "403" in text or "api key not valid" in low
            or "permission_denied" in low or "unauthenticated" in low):
        return AuthError(f"Gemini auth error: {text}")
    if "500" in text or "503" in text or "internal" in low or "unavailable" in low:
        return ProviderServerError(f"Gemini provider server error: {text}")
    return GenerationError(f"Gemini API Error: {text}")


# --- Global Standard Paths (2.3.2) ---
# Added so gemini.py matches the zero-config get_standard_prompter() pattern
# already established in groq.py and openrouter.py -- previously a caller had
# to know these paths and construct GeminiKeyRegistry/GeminiModelRegistry by
# hand, which is exactly why ai_dispatch.py's common interface needed this.
STD_KEY_PATH = CONFIG_DIR / "gemini_keys.104a.bejson"
STD_MODEL_PATH = CONFIG_DIR / "gemini_model_registry.104a.bejson"

_std_api_singleton: Optional["GeminiAPI"] = None


def get_standard_api() -> "GeminiAPI":
    """
    Zero-config GeminiAPI, built from the standard key/model registry paths.
    Cached after first call (matches the singleton pattern used by
    get_standard_prompter() in groq.py/openrouter.py).
    """
    global _std_api_singleton
    if _std_api_singleton is None:
        key_reg = GeminiKeyRegistry(STD_KEY_PATH)
        model_reg = GeminiModelRegistry(STD_MODEL_PATH)
        _std_api_singleton = GeminiAPI(key_reg, model_reg)
    return _std_api_singleton
