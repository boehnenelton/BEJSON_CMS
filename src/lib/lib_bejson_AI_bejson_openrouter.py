"""
Library:        lib_bejson_AI_bejson_openrouter.py
Family:         AI
Description:    Multi-model routing gateway for AI interactions.
Version:        3.2.0
Date:           2026-09-07
Author:         Elton Boehnen
Contact:        eltonboehnen@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  1f4c8b73-6d2a-4e91-9c5f-3a7d0e8b4c26
Release_Version: 300

Changelog:
  3.2.0 (2026-09-28) -- Root-caused a round-robin-key-rotation bug found in this project's audit: get_standard_prompter() built a brand-new OpenRouterStandardPrompter (and therefore a brand-new KeyRegistry, its rotation _idx reset to 0) on every single dispatch, since ai_dispatch.py calls it fresh per call. Round-robin existed in the class but never actually advanced past key #1 in practice. Cached after first call instead, matching the singleton pattern lib_bejson_AI_bejson_gemini.py's get_standard_api() already used correctly.
  3.1.0 (2026-09-07) -- Ported the flag/service schema migration from
          libraries_104's copy of this file (that repo's 3.1.0/3.1.1,
          2026-09-06) into this project, per Elton's confirmation. Appended
          "flag" and "service" fields (string, default "") to the END of
          both SCHEMA_KEY_REGISTRY and SCHEMA_MODEL_REGISTRY_OPENROUTER's
          Fields arrays. Both unused for now: undeclared/empty means
          "usable for anything, no restriction" -- flag for a future
          paid-tier marker, service for future capability filtering (e.g.
          "image"). Existing 5 model rows each gained two trailing ""
          columns; refresh_from_live_api() updated to append the same two
          trailing columns to the rows it builds from the live API, so a
          live refresh doesn't drop back to 4-column rows.
          OPENROUTER_CONFIG_VERSION bumped 2 -> 3. This project's own
          on-disk openrouter_keys.104a.bejson (0 rows, no migration needed)
          and openrouter_model_registry.104a.bejson were migrated in place
          to match -- columns appended, Config_Version set to 3 directly.
          Numbering note: this project's own history never had a 3.1.0
          (it went 3.0.0 -> 3.0.1 -- see that entry), so 3.1.0 is used here
          cleanly. libraries_104's copy of this same migration is at 3.1.1,
          not 3.1.0, because that repo's 3.1.0 shipped with a regression
          (env_var_max_slots/has_thinking silently dropped) that 3.1.1
          fixed; this project's 3.0.1 never had that regression, so this
          3.1.0 is equivalent in content to libraries_104's 3.1.1, not its
          3.1.0. The two repos' version numbers for this file are not
          expected to line up exactly given the diverged history -- what
          matters is that each repo's own numbers are internally
          consistent from here forward.
  3.0.1 (2026-09-07) -- Process-only fix: these two behavioral changes were
          already present in the file's code (found undocumented during a
          library sync to libraries_104) but VERSION/Version/changelog
          were never bumped for them, so 3.0.0 silently covered two
          different behaviors. Documenting them here at the correct patch
          level: (1) env_var_max_slots raised 2 -> 10 for the OpenRouter
          key registry's env-var fallback scan. (2) refresh_from_live_api()
          now derives thinking_enabled from the live API response
          ("include_reasoning"/"reasoning" in supported_parameters, or a
          truthy "reasoning" field) instead of hardcoding False for every
          refreshed row. NOTE: libraries_104's own copy of this file has
          since moved on to 3.1.0/3.1.1 (flag/service schema columns,
          Config_Version 3) independently of this project's copy -- that
          migration has NOT been ported here. 3.0.1 is used rather than
          3.1.0 specifically to avoid colliding with that unrelated
          content under the same version number across the two repos.
  3.0.0 - REGISTRY OVERHAUL (same pass as groq.py 3.0.0, per Elton's
          direct instruction). STD_KEY_PATH/STD_MODEL_PATH/STD_PROFILE_PATH
          moved from {HOME}/.env/... and {ADMIN_ROOT}/data/schemas/... to
          this library's own self-contained config/ subfolder
          (get_self_contained_dir(__file__)). OpenRouterProfile removed;
          now uses the shared BejsonProfileBase. Both registries pass
          config_version=2 -- any on-disk file from before this delivery
          has no Config_Version and is regenerated automatically. Note:
          OpenRouterModelRegistry's stale-model exposure was already far
          lower than Groq's, since refresh_from_live_api() (preserved
          verbatim below) actively re-pulls the free model list rather
          than trusting a static default forever -- this pass brings it
          onto the same self-contained/versioned storage for consistency,
          not because it had the identical silent-404 bug.
  2.1.7 - Modularization: OpenRouterKeyRegistry/OpenRouterModelRegistry now
          subclass lib_bejson_AI_ai_registry_base.py's shared atomic base
          (same migration done for Groq 2.1.6). refresh_from_live_api()
          preserved verbatim. Behavior verified: default file creation,
          full model lineup with thinking fields, active_model_id,
          get_model_info() all match pre-migration output; gains
          OPENROUTER_KEY_1/_2 numbered env-slot fallback it never had.
  2.1.6 - AI-family audit fix: no module-level VERSION var existed despite
          this header claiming 2.1.5. Added, bumped for the fix itself.
  2.1.5 - Added OpenRouterModelRegistry.refresh_from_live_api(): pulls the
          CURRENT free-tier model list from OpenRouter's public catalog
          (GET /models, filtered to pricing.prompt == "0" and
          pricing.completion == "0", no API key required) and rewrites the
          registry file via bejson_core_atomic_write. This is the actual
          fix for stale model_id strings -- researched OpenRouter's free
          lineup directly (2026-08-10) and confirmed it rotates constantly
          (providers add/pull free access with no notice; multiple
          contemporary sources disagree on whether DeepSeek currently has
          any free variant), so hand-correcting SCHEMA_MODEL_REGISTRY_OPENROUTER's
          hardcoded "deepseek/deepseek-r1:free" to a different guessed
          string would just go stale again. Call refresh_from_live_api()
          whenever online instead of trusting any hardcoded snapshot,
          including the one still baked into this file. Network failure
          leaves the existing registry untouched (never wipes a working
          local list).
  2.1.4 - SCHEMA_MODEL_REGISTRY renamed to SCHEMA_MODEL_REGISTRY_OPENROUTER
          to eliminate the name collision with SCHEMA_MODEL_REGISTRY_GEMINI in
          lib_bejson_Core_bejson_schema.py (Step 1 — 1.32 finalization).
"""

import os
import sys
import json
import time
import requests
import random
import copy
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
# --- Path Resolution Utility ---
# Add Lib directory to path for relative imports
LIB_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_DIR = os.path.join(os.path.dirname(LIB_DIR), "Core")
if CORE_DIR not in sys.path:
    sys.path.append(CORE_DIR)

VERSION = "3.2.0"

# Config_Version for this provider's stores -- bump whenever a default
# schema below changes; any on-disk file with no Config_Version, or one
# older than this, is regenerated automatically. See ai_registry_base.py.
OPENROUTER_CONFIG_VERSION = 3

# --- EMBEDDED SCHEMAS ---
SCHEMA_KEY_REGISTRY = {
    "Format": "BEJSON",
    "Format_Version": "104a",
    "Format_Creator": "Elton Boehnen",
    "Schema_Name": "OpenRouterKeyRegistry",
    "Records_Type": ["ApiKey"],
    "Fields": [
        {"name": "key_slot", "type": "integer"},
        {"name": "key", "type": "string"},
        {"name": "flag", "type": "string"},     # unused; e.g. "paid"
        {"name": "service", "type": "string"},  # unused; e.g. "image"
    ],
    "Values": []
}

SCHEMA_MODEL_REGISTRY_OPENROUTER = {
    "Format": "BEJSON",
    "Format_Version": "104a",
    "Format_Creator": "Elton Boehnen",
    "Schema_Name": "OpenRouterModelRegistry",
    "Records_Type": ["OpenRouterModel"],
    "Fields": [
        {"name": "model_name", "type": "string"},
        {"name": "model_id", "type": "string"},
        {"name": "currently_active", "type": "boolean"},
        {"name": "thinking_enabled", "type": "boolean"},
        {"name": "flag", "type": "string"},     # unused; e.g. "paid"
        {"name": "service", "type": "string"},  # unused; e.g. "image"
    ],
    "Values": [
        ["DeepSeek R1 (Free)", "deepseek/deepseek-r1:free", True, True, "", ""],
        ["Gemma 4 27B (Preview)", "google/gemma-4-27b-it", False, False, "", ""],
        ["Gemma 3 27B (Preview)", "google/gemma-3-27b-it", False, False, "", ""],
        ["Liquid LFM 2.5 Thinking", "liquid/lfm-2.5-1.2b-thinking:free", False, True, "", ""],
        ["Llama 3.3 70B", "meta-llama/llama-3.3-70b-instruct", False, False, "", ""]
    ]
}

SCHEMA_AI_PROFILE = {
    "Format": "BEJSON",
    "Format_Version": "104",
    "Format_Creator": "Elton Boehnen",
    "Records_Type": ["AI_Profile"],
    # FIX (LIB-AI-M2): previously "Parent_Hierarchy": "/LLM_Configuration".
    # Parent_Hierarchy is a relative back-reference from an entity file to
    # its MFDB manifest (see mfdb_validator.py, which resolves it via
    # os.path.join(entity_dir, ph) - a leading "/" makes os.path.join
    # discard entity_dir entirely and resolve to the literal OS path
    # "/LLM_Configuration"). This profile isn't tracked by any MFDB
    # manifest, and Parent_Hierarchy is optional for standalone 104 docs
    # (see bejson_validator.py's custom-key check), so it's removed rather
    # than replaced with a guessed relative path that could be wrong.
    "Fields": [
        {"name": "Record_Type_Parent", "type": "string"},
        {"name": "Name", "type": "string"},
        {"name": "Archetype", "type": "string"},
        {"name": "Persona", "type": "string"},
        {"name": "SystemInstruction", "type": "string"},
        {"name": "ForbiddenTopics", "type": "array"},
        {"name": "Avatar_Type", "type": "string"},
        {"name": "Avatar_sourceUrl", "type": "string"},
        {"name": "Avatar_Data", "type": "string"},
        {"name": "MaxResponseTokens", "type": "integer"},
        {"name": "Creativity", "type": "number"},
        {"name": "Tone", "type": "array"},
        {"name": "Formality", "type": "string"},
        {"name": "Verbosity", "type": "string"},
        {"name": "EmotionalExpression_Enabled", "type": "boolean"},
        {"name": "EmotionalExpression_Intensity", "type": "number"},
        {"name": "GoogleSearch_Enabled", "type": "boolean"},
        {"name": "CodeInterpreter_Enabled", "type": "boolean"},
        {"name": "EphemeralMemory", "type": "boolean"},
        {"name": "CodeParsing_Mode", "type": "string"},
        {"name": "CodeParsing_Languages", "type": "array"},
        {"name": "CodeParsing_StructureValidation", "type": "boolean"},
        {"name": "CodeParsing_VersionControl", "type": "boolean"},
        {"name": "Thinking_Supported", "type": "boolean"}
    ],
    "Values": [
        [
            "AI_Profile",
            "OpenRouter_Standard",
            "Assistant",
            "A helpful and professional AI assistant.",
            "You are a helpful assistant. Provide clear, accurate, and concise information.",
            [], "Emoji", "", "🚀", 16384, 0.7, ["Professional", "Helpful"], "Formal", "Balanced", 
            False, 0.0, False, True, True, "complete", ["python", "javascript"], True, True, True
        ]
    ]
}

# --- Environment & Setup ---
LIB_DIR = os.environ.get("BEJSON_LIB_DIR", str(Path(__file__).resolve().parent))
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

from lib_bejson_Core_bejson_core import (
    bejson_core_load_file, 
    bejson_core_get_field_index, 
    bejson_core_get_field_map, 
    bejson_core_atomic_write
)
from lib_bejson_AI_ai_registry_base import (
    RoundRobinKeyRegistry,
    ModelRegistryBase,
    BejsonProfileBase,
    get_self_contained_dir,
)

# Self-contained storage: this library's own config/ subfolder, no
# external ADMIN_ROOT/HOME dependency.
CONFIG_DIR = get_self_contained_dir(__file__)

# --- Legacy Fallback Constants ---
_OR_MODEL_LEGACY   = {"model_name": 0, "model_id": 1, "currently_active": 2, "thinking_enabled": 3}
_OR_PROFILE_LEGACY = {"SystemInstruction": 4} 

# --- Registry Managers ---
# 2.1.7: OpenRouterKeyRegistry/OpenRouterModelRegistry now subclass the
# shared AI-family atomic base (lib_bejson_AI_ai_registry_base.py), same
# migration already done for Groq in groq.py 2.1.6. refresh_from_live_api()
# is preserved verbatim as an added method on the subclass -- the base has
# no equivalent (it's OpenRouter-specific), so it isn't a base-class thing.

class OpenRouterKeyRegistry(RoundRobinKeyRegistry):
    def __init__(self, file_path: str):
        super().__init__(
            file_path,
            placeholder_markers=["YOUR_OPENROUTER_KEY", "KEY_HERE"],
            env_var_prefix="OPENROUTER_KEY",
            env_var_max_slots=10,
            default_schema=SCHEMA_KEY_REGISTRY,
            config_version=OPENROUTER_CONFIG_VERSION,
        )


class OpenRouterModelRegistry(ModelRegistryBase):
    def __init__(self, file_path: str):
        super().__init__(
            file_path,
            # NOTE (2026-08-10, carried forward): OpenRouter's free (":free"
            # suffix) lineup rotates constantly. This hardcoded default WILL
            # go stale; call refresh_from_live_api() when online.
            default_model_id="deepseek/deepseek-r1:free",
            default_rows_factory=lambda: SCHEMA_MODEL_REGISTRY_OPENROUTER,
            config_version=OPENROUTER_CONFIG_VERSION,
        )

    def _extra_fields(self, row, fmap):
        think_idx = fmap.get("thinking_enabled", _OR_MODEL_LEGACY["thinking_enabled"])
        return {"thinking": row[think_idx] if think_idx != -1 and think_idx < len(row) else False}

    def load(self) -> None:
        # Overridden (not just _extra_fields()) to preserve the original's
        # exact total-failure fallback: rebuild {"id","thinking"} pairs
        # positionally straight from SCHEMA_MODEL_REGISTRY_OPENROUTER rather
        # than the base's generic single-entry fallback, since callers may
        # depend on the full default lineup being present even when the
        # on-disk registry is corrupt/unreadable.
        try:
            from lib_bejson_Core_bejson_core import bejson_core_load_file
            data = bejson_core_load_file(str(self.file_path))
            fi = bejson_core_get_field_map(data)
            id_idx = fi.get("model_id", _OR_MODEL_LEGACY["model_id"])
            active_idx = fi.get("currently_active", _OR_MODEL_LEGACY["currently_active"])
            self.models = []
            for row in data["Values"]:
                m_info = {"id": row[id_idx], **self._extra_fields(row, fi)}
                self.models.append(m_info)
                if row[active_idx] is True:
                    self.active_model_id = row[id_idx]
        except Exception as e:
            logging.warning(f"[OR_Lib] Failed to load model registry {self.file_path}, using defaults: {e}")
            self.models = [{"id": row[1], "thinking": row[3]} for row in SCHEMA_MODEL_REGISTRY_OPENROUTER["Values"]]

    def refresh_from_live_api(self, timeout: int = 15) -> int:
        """Replaces the registry's model list with whatever OpenRouter is
        CURRENTLY offering at zero cost, pulled from their public model
        catalog (GET /models, pricing.prompt == "0" and pricing.completion
        == "0" -- no API key required for this endpoint). This is the
        durable fix for the registry going stale: call this (network
        permitting) instead of hand-editing model_id strings, since the
        free lineup can change without notice. currently_active is kept on
        whichever model was already active if it's still free; otherwise
        the first free model found becomes active. Returns the number of
        free models found (0 on any failure -- registry is left untouched
        so a network hiccup never wipes out a working local list)."""
        try:
            resp = requests.get("https://openrouter.ai/api/v1/models", timeout=timeout)
            resp.raise_for_status()
            data = resp.json().get("data", [])
        except Exception as e:
            logging.warning(f"[OR_Lib] refresh_from_live_api failed, keeping existing registry: {e}")
            return 0

        free = [
            m for m in data
            if str(m.get("pricing", {}).get("prompt")) == "0"
            and str(m.get("pricing", {}).get("completion")) == "0"
        ]
        if not free:
            logging.warning("[OR_Lib] refresh_from_live_api: OpenRouter returned zero free models, keeping existing registry.")
            return 0

        still_active = self.active_model_id in {m.get("id") for m in free}
        new_active = self.active_model_id if still_active else free[0].get("id")

        new_values = []
        for m in free:
            model_id = m.get("id", "")
            name = m.get("name", model_id)
            supp = m.get("supported_parameters") or []
            reasoning = m.get("reasoning")
            has_thinking = ("include_reasoning" in supp or "reasoning" in supp or bool(reasoning))
            # Trailing "", "" are the flag/service columns added to
            # SCHEMA_MODEL_REGISTRY_OPENROUTER's Fields (2026-09-07) --
            # appended here too so row length keeps matching Fields length
            # (BEJSON positional integrity, §10.5).
            new_values.append([name, model_id, model_id == new_active, has_thinking, "", ""])

        new_doc = copy.deepcopy(SCHEMA_MODEL_REGISTRY_OPENROUTER)
        new_doc["Values"] = new_values
        new_doc["Config_Version"] = OPENROUTER_CONFIG_VERSION
        os.makedirs(self.file_path.parent, exist_ok=True)
        bejson_core_atomic_write(str(self.file_path), new_doc)

        self.active_model_id = new_active
        self.models = [{"id": v[1], "thinking": v[3]} for v in new_values]
        logging.info(f"[OR_Lib] refresh_from_live_api: registry updated with {len(free)} free model(s), active={new_active}")
        return len(free)

    def get_model_info(self, model_id: Optional[str] = None) -> Dict[str, Any]:
        target_id = model_id or self.active_model_id
        for m in self.models:
            if m["id"] == target_id: return m
        return {"id": target_id, "thinking": False}

class OpenRouterProfile(BejsonProfileBase):
    def __init__(self, file_path: str):
        super().__init__(
            file_path,
            schema_factory=lambda: SCHEMA_AI_PROFILE,
            config_version=OPENROUTER_CONFIG_VERSION,
        )

# --- Unified Prompter Engine ---
class OpenRouterStandardPrompter:
    def __init__(self, key_registry_path: str, model_registry_path: str, profile_path: str):
        self.key_reg = OpenRouterKeyRegistry(key_registry_path)
        self.model_reg = OpenRouterModelRegistry(model_registry_path)
        self.profile = OpenRouterProfile(profile_path)
        self.current_key_idx = 0
        self.last_request_time = 0
        self.request_delay = 1.0

    def _get_next_key(self) -> Optional[str]:
        keys = self.key_reg.keys
        if not keys: return None
        key = keys[self.current_key_idx]
        self.current_key_idx = (self.current_key_idx + 1) % len(keys)
        return key

    def prompt(self, user_input: str, model_id: Optional[str] = None) -> Dict[str, str]:
        now = time.time()
        diff = now - self.last_request_time
        if diff < self.request_delay: time.sleep(self.request_delay - diff)
        
        key = self._get_next_key()
        if not key: return {"content": "ERROR: No valid API keys.", "thought": ""}

        m_info = self.model_reg.get_model_info(model_id)
        mid = m_info["id"]
        
        is_gemma_modern = "google/gemma-4" in mid or "google/gemma-3" in mid
        if is_gemma_modern:
            messages = [{"role": "user", "content": f"{self.profile.instruction}\n\n{user_input}"}]
        else:
            messages = [{"role": "system", "content": self.profile.instruction}, {"role": "user", "content": user_input}]

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/boehnenelton/cli_openrouter",
            "X-Title": "Gemini CLI OpenRouter Standard Lib"
        }
        payload = {
            "model": mid,
            "messages": messages,
            "max_tokens": self.profile.config.get("MaxResponseTokens", 16384),
            "temperature": self.profile.config.get("Creativity", 0.7)
        }
        if m_info["thinking"] or self.profile.config.get("Thinking_Supported", False):
            payload["include_thoughts"] = True

        self.last_request_time = time.time()
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=90)
            res.raise_for_status()
            data = res.json()
            if "choices" in data and data["choices"]:
                choice = data["choices"][0]
                content = choice["message"].get("content", "").strip() if choice.get("message") else ""
                thought = choice["message"].get("reasoning", "") or choice["message"].get("thought", "") if choice.get("message") else ""
                if not thought: thought = choice.get("thought", "")
                return {"content": content, "thought": thought.strip()}
            return {"content": f"ERROR: No choices. {json.dumps(data)}", "thought": ""}
        except Exception as e:
            return {"content": f"ERROR: {str(e)}", "thought": ""}

# --- Global Standard Paths: self-contained, inside this library's own
# config/ folder -- no more {HOME}/.env/... or {ADMIN_ROOT}/... dependency.
STD_KEY_PATH = CONFIG_DIR / "openrouter_keys.104a.bejson"
STD_MODEL_PATH = CONFIG_DIR / "openrouter_model_registry.104a.bejson"
STD_PROFILE_PATH = CONFIG_DIR / "openrouter_standard_profile.bejson"

_std_prompter_singleton = None


def get_standard_prompter():
    """Zero-config OpenRouterStandardPrompter, cached after first call --
    see lib_bejson_AI_bejson_groq.py's get_standard_prompter() for why
    this caching is the actual round-robin-key-rotation fix, not just an
    optimization."""
    global _std_prompter_singleton
    if _std_prompter_singleton is None:
        _std_prompter_singleton = OpenRouterStandardPrompter(STD_KEY_PATH, STD_MODEL_PATH, STD_PROFILE_PATH)
    return _std_prompter_singleton
