"""
Library:        lib_bejson_AI_bejson_tokenrouter.py
Family:         AI
Description:    Integration wrapper for TokenRouter API endpoints (https://api.tokenrouter.com/v1).

                 Auth: Sourced securely via environment variables:
                 - TOKENROUTER_API_KEY (single key)
                 - TOKENROUTER_KEY_1..N (numbered slots)
                 - BEJSON fallback key file under config/

Version:        1.1.0
Date:           2026-09-11
Author:         Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  8d2e6f4a-1b3c-4d5e-9f7a-8b0c2d3e4f5a
Release_Version: 300

Changelog:
  1.1.0 (2026-09-28) -- Root-caused a round-robin-key-rotation bug found in this project's audit: get_standard_prompter() built a brand-new TokenRouterStandardPrompter (and therefore a brand-new KeyRegistry, its rotation _idx reset to 0) on every single dispatch, since ai_dispatch.py calls it fresh per call. Round-robin existed in the class but never actually advanced past key #1 in practice. Cached after first call instead, matching the singleton pattern lib_bejson_AI_bejson_gemini.py's get_standard_api() already used correctly.
  1.0.0 - Initial creation. TokenRouter provider integration with self-healing
          versioned config, RoundRobinKeyRegistry, ModelRegistryBase,
          BejsonProfileBase, and OpenAICompatibleClient REST wrapper.
"""

import os
import sys
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
from lib_bejson_AI_ai_openai_compatible_base import OpenAICompatibleClient

logger = logging.getLogger("lib_bejson_AI_bejson_tokenrouter")

VERSION = "1.1.0"

TOKENROUTER_CONFIG_VERSION = 1

CONFIG_DIR = get_self_contained_dir(__file__)

# --- SCHEMAS -----------------------------------------------------------

SCHEMA_MODEL_REGISTRY_TOKENROUTER = {
    "Format": "BEJSON", "Format_Version": "104a", "Format_Creator": "Elton Boehnen",
    "Records_Type": ["TokenRouterModel"],
    "Fields": [
        {"name": "model_name", "type": "string"},
        {"name": "model_id", "type": "string"},
        {"name": "currently_active", "type": "boolean"},
    ],
    "Values": [
        ["GLM-5.3 Free (z-ai)", "z-ai/glm-5.3-free", True],
        ["GLM-5.3 Free (Short Alias)", "glm-5.3-free", False],
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
            "AI_Profile", "TokenRouter_Standard", "Assistant",
            "An intelligent assistant, please reply concisely.",
            "You are an intelligent assistant, please reply concisely.",
            8192, 0.7,
        ]
    ],
}


class TokenRouterKeyRegistry(RoundRobinKeyRegistry):
    def __init__(self, file_path: str):
        super().__init__(
            file_path,
            placeholder_markers=["YOUR_TOKENROUTER_KEY", "YOUR_API_KEY", "KEY_HERE"],
            env_var="TOKENROUTER_API_KEY",
            env_var_prefix="TOKENROUTER_KEY",
            env_var_max_slots=20,
            config_version=TOKENROUTER_CONFIG_VERSION,
        )

    def load(self) -> None:
        super().load()
        # Scan os.environ for custom named slots
        for var_name, var_val in os.environ.items():
            if var_name.startswith("TOKENROUTER_KEY_") and var_val and var_val not in self.keys:
                if not any(marker in var_val for marker in self.placeholder_markers):
                    self.keys.append(var_val)


class TokenRouterModelRegistry(ModelRegistryBase):
    def __init__(self, file_path: str):
        super().__init__(
            file_path,
            default_model_id="z-ai/glm-5.3-free",
            default_rows_factory=lambda: SCHEMA_MODEL_REGISTRY_TOKENROUTER,
            config_version=TOKENROUTER_CONFIG_VERSION,
        )


class TokenRouterProfile(BejsonProfileBase):
    def __init__(self, file_path: str):
        super().__init__(
            file_path,
            schema_factory=lambda: SCHEMA_AI_PROFILE,
            config_version=TOKENROUTER_CONFIG_VERSION,
        )


class TokenRouterStandardPrompter:
    def __init__(self, key_registry_path: str, model_registry_path: str, profile_path: str):
        self.key_reg = TokenRouterKeyRegistry(key_registry_path)
        self.model_reg = TokenRouterModelRegistry(model_registry_path)
        self.profile = TokenRouterProfile(profile_path)
        self.client = OpenAICompatibleClient(
            provider_label="tokenrouter",
            base_url="https://api.tokenrouter.com/v1",
            default_model="z-ai/glm-5.3-free"
        )

    def prompt(self, user_input: str, model_id: Optional[str] = None, system_instruction: Optional[str] = None) -> str:
        key = self.key_reg.get_next_key()
        if not key:
            return "ERROR: No TokenRouter API keys loaded."
        
        target_model = model_id or self.model_reg.active_model_id
        sys_inst = system_instruction or self.profile.instruction

        try:
            return self.client.chat(
                prompt=user_input,
                api_key=key,
                model=target_model,
                system_instruction=sys_inst
            )
        except Exception as e:
            return f"ERROR: {e}"


_std_prompter_singleton = None


def get_standard_prompter() -> TokenRouterStandardPrompter:
    """Zero-config TokenRouterStandardPrompter, cached after first call --
    see lib_bejson_AI_bejson_groq.py's get_standard_prompter() for why
    this caching is the actual round-robin-key-rotation fix, not just an
    optimization."""
    global _std_prompter_singleton
    if _std_prompter_singleton is None:
        _std_prompter_singleton = TokenRouterStandardPrompter(
            key_registry_path=str(CONFIG_DIR / "tokenrouter_keys.104a.bejson"),
            model_registry_path=str(CONFIG_DIR / "tokenrouter_model_registry.104a.bejson"),
            profile_path=str(CONFIG_DIR / "tokenrouter_standard_profile.bejson")
        )
    return _std_prompter_singleton
