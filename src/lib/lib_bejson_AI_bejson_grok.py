"""
Library:        lib_bejson_AI_bejson_grok.py
Family:         AI
Description:    Integration wrapper for xAI's Grok API.

                 ENDPOINT CHOICE: xAI now promotes /v1/responses as the
                 "preferred" endpoint (needed for their newer agentic
                 features -- server-side web/X search, code execution,
                 automatic conversation caching), but its response body is
                 a nested "output" array of typed content parts (the
                 client-library-only "response.output_text" convenience
                 field is computed by the official SDKs, not literally
                 present in the raw JSON every implementation returns).
                 /v1/chat/completions is documented as fully supported,
                 OpenAI-compatible, and returns the exact same simple
                 choices[0].message.content shape every other provider in
                 this family already uses. This file uses
                 /v1/chat/completions to match the established, already-
                 tested family pattern rather than introduce a new
                 response-parsing shape for no functional benefit.

                 Auth: xAI's own documented env var is XAI_API_KEY (a
                 single key, not numbered slots) -- this file's
                 GrokKeyRegistry checks that FIRST (env_var="XAI_API_KEY"),
                 then falls back to this family's numbered-slot convention
                 (GROK_KEY_1..10), then the BEJSON key file. Never hardcode
                 a key in this file or any config it writes -- keys only
                 ever come from secureenv_file.json / the environment.
Version:        2.1.0
Date:           2026-08-22
Author:         Elton Boehnen
Contact:        eltonboehnen@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  2fcd3e68-e3fd-4859-b002-6fee1078c8ee
Release_Version: 300

Changelog:
  2.1.0 (2026-09-28) -- Root-caused a round-robin-key-rotation bug found in this project's audit: get_standard_prompter() built a brand-new GrokStandardPrompter (and therefore a brand-new KeyRegistry, its rotation _idx reset to 0) on every single dispatch, since ai_dispatch.py calls it fresh per call. Round-robin existed in the class but never actually advanced past key #1 in practice. Cached after first call instead, matching the singleton pattern lib_bejson_AI_bejson_gemini.py's get_standard_api() already used correctly.
  2.0.0 - REGISTRY OVERHAUL (same pass as groq.py 3.0.0 / openrouter.py
          3.0.0, per Elton's direct instruction). STD_KEY_PATH/
          STD_MODEL_PATH/STD_PROFILE_PATH moved from {HOME}/.env/... and
          {ADMIN_ROOT}/data/schemas/... to this library's own self-
          contained config/ subfolder. GrokProfile removed (was hand-
          rolled, near-identical to Groq/OpenRouter's now-shared version);
          uses BejsonProfileBase. GrokKeyRegistry/GrokModelRegistry pass
          config_version=2, so any pre-existing on-disk file (no
          Config_Version) self-heals on next run instead of silently
          staying stale.
  1.0.0 - Initial creation.
"""

import os
import sys
import time
import logging
from pathlib import Path
from typing import Any, Dict, Optional

LIB_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_DIR = os.path.join(os.path.dirname(LIB_DIR), "Core")
if CORE_DIR not in sys.path:
    sys.path.append(CORE_DIR)

from lib_bejson_AI_ai_registry_base import (
    RoundRobinKeyRegistry,
    ModelRegistryBase,
    BejsonProfileBase,
    get_self_contained_dir,
)

logger = logging.getLogger("lib_bejson_AI_bejson_grok")

VERSION = "2.1.0"

# Config_Version for this provider's stores -- bump whenever a default
# schema below changes. See ai_registry_base.py's ensure_current().
GROK_CONFIG_VERSION = 2

# Self-contained storage: this library's own config/ subfolder.
CONFIG_DIR = get_self_contained_dir(__file__)

# --- SCHEMAS -----------------------------------------------------------

SCHEMA_MODEL_REGISTRY_GROK = {
    "Format": "BEJSON", "Format_Version": "104a", "Format_Creator": "Elton Boehnen",
    "Records_Type": ["GrokModel"],
    "Fields": [
        {"name": "model_name", "type": "string"},
        {"name": "model_id", "type": "string"},
        {"name": "currently_active", "type": "boolean"},
    ],
    # Current at time of writing per docs.x.ai. grok-4.6 is the flagship
    # general-purpose model; grok-4-fast trades some depth for latency/
    # cost; grok-3 kept as a stable legacy fallback.
    "Values": [
        ["Grok 4.6", "grok-4.6", True],
        ["Grok 4 Fast", "grok-4-fast", False],
        ["Grok 3", "grok-3", False],
    ],
}

SCHEMA_AI_PROFILE = {
    "Format": "BEJSON", "Format_Version": "104", "Format_Creator": "Elton Boehnen",
    "Records_Type": ["AI_Profile"],
    "Fields": [
        {"name": "Record_Type_Parent", "type": "string"},
        {"name": "Name", "type": "string"},
        {"name": "Archetype", "type": "string"},
        {"name": "Persona", "type": "string"},
        {"name": "SystemInstruction", "type": "string"},
        {"name": "MaxResponseTokens", "type": "integer"},
        {"name": "Creativity", "type": "number"},
    ],
    "Values": [
        [
            "AI_Profile", "Grok_Standard", "Assistant",
            "A helpful, direct AI assistant.",
            "You are a helpful assistant. Provide clear, accurate, and concise information.",
            8192, 0.7,
        ]
    ],
}


class GrokKeyRegistry(RoundRobinKeyRegistry):
    def __init__(self, file_path: str):
        super().__init__(
            file_path,
            placeholder_markers=["YOUR_GROK_KEY", "YOUR_XAI_KEY", "KEY_HERE"],
            env_var="XAI_API_KEY",       # xAI's own documented single-var name, checked first
            env_var_prefix="GROK_KEY",   # this family's numbered-slot convention, checked second
            env_var_max_slots=10,
            config_version=GROK_CONFIG_VERSION,
        )


class GrokModelRegistry(ModelRegistryBase):
    def __init__(self, file_path: str):
        super().__init__(
            file_path,
            default_model_id="grok-4.6",
            default_rows_factory=lambda: SCHEMA_MODEL_REGISTRY_GROK,
            config_version=GROK_CONFIG_VERSION,
        )


class GrokProfile(BejsonProfileBase):
    def __init__(self, file_path: str):
        super().__init__(
            file_path,
            schema_factory=lambda: SCHEMA_AI_PROFILE,
            config_version=GROK_CONFIG_VERSION,
        )


class GrokStandardPrompter:
    def __init__(self, key_registry_path: str, model_registry_path: str, profile_path: str):
        self.key_reg = GrokKeyRegistry(key_registry_path)
        self.model_reg = GrokModelRegistry(model_registry_path)
        self.profile = GrokProfile(profile_path)
        self.current_key_idx = 0
        self.last_request_time = 0
        self.request_delay = 1.0

    def _get_next_key(self) -> Optional[str]:
        keys = self.key_reg.keys
        if not keys:
            return None
        key = keys[self.current_key_idx]
        self.current_key_idx = (self.current_key_idx + 1) % len(keys)
        return key

    def prompt(self, user_input: str, model_id: Optional[str] = None,
               system_instruction: Optional[str] = None) -> str:
        import requests
        now = time.time()
        diff = now - self.last_request_time
        if diff < self.request_delay:
            time.sleep(self.request_delay - diff)

        key = self._get_next_key()
        if not key:
            return "ERROR: No valid API keys."

        m_info = self.model_reg.get_model_info(model_id)
        url = "https://api.x.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        payload = {
            "model": m_info["id"],
            "messages": [
                {"role": "system", "content": system_instruction or self.profile.instruction},
                {"role": "user", "content": user_input},
            ],
            "max_tokens": self.profile.config.get("MaxResponseTokens", 8192),
            "temperature": self.profile.config.get("Creativity", 0.7),
        }
        self.last_request_time = time.time()
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=90)
            res.raise_for_status()
            data = res.json()
            if "choices" in data and data["choices"]:
                return data["choices"][0]["message"]["content"].strip()
            return f"ERROR: No choices. {data}"
        except Exception as e:
            return f"ERROR: {str(e)}"


# --- Global Standard Paths: self-contained, inside this library's own
# config/ folder -- no more {HOME}/.env/... or {ADMIN_ROOT}/... dependency.
STD_KEY_PATH = CONFIG_DIR / "grok_keys.104a.bejson"
STD_MODEL_PATH = CONFIG_DIR / "grok_model_registry.104a.bejson"
STD_PROFILE_PATH = CONFIG_DIR / "grok_standard_profile.bejson"


_std_prompter_singleton = None


def get_standard_prompter():
    """Zero-config GrokStandardPrompter, cached after first call -- see
    lib_bejson_AI_bejson_groq.py's get_standard_prompter() for why this
    caching is the actual round-robin-key-rotation fix, not just an
    optimization."""
    global _std_prompter_singleton
    if _std_prompter_singleton is None:
        _std_prompter_singleton = GrokStandardPrompter(STD_KEY_PATH, STD_MODEL_PATH, STD_PROFILE_PATH)
    return _std_prompter_singleton
