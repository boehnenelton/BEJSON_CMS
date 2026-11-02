"""
Library:        lib_bejson_AI_bejson_ollama.py
Family:         AI
Description:    Integration wrapper for Ollama Cloud API.
                 Uses the OpenAI-compatible /v1/chat/completions endpoint
                 (https://ollama.com/v1/chat/completions).

                 Auth: Uses OLLAMA_KEY_1..10 from secure environment.
Version:        1.1.0
Date:           2026-09-15
Author:         Elton Boehnen
Contact:        eltonboehnen@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  9a8b7c6d-5e4f-3a2b-1c0d-9e8f7a6b5c4d
Release_Version: 300

Changelog:
  1.1.0 (2026-09-28) -- Root-caused a round-robin-key-rotation bug found
        in this project's audit: get_standard_prompter() built a brand-new
        OllamaStandardPrompter (and therefore a brand-new KeyRegistry, its
        rotation _idx reset to 0) on every single dispatch, since
        ai_dispatch.py calls it fresh per call. Round-robin existed in the
        class but never actually advanced past key #1 in practice. Cached
        after first call instead, matching the singleton pattern
        lib_bejson_AI_bejson_gemini.py's get_standard_api() already used
        correctly.
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

logger = logging.getLogger("lib_bejson_AI_bejson_ollama")

VERSION = "1.1.0"
OLLAMA_CONFIG_VERSION = 1
CONFIG_DIR = get_self_contained_dir(__file__)

# --- SCHEMAS -----------------------------------------------------------

SCHEMA_MODEL_REGISTRY_OLLAMA = {
    "Format": "BEJSON", "Format_Version": "104a", "Format_Creator": "Elton Boehnen",
    "Records_Type": ["OllamaModel"],
    "Fields": [
        {"name": "model_name", "type": "string"},
        {"name": "model_id", "type": "string"},
        {"name": "currently_active", "type": "boolean"},
    ],
    "Values": [
        ["Llama 3.2 3B", "llama3.2:3b", True],
        ["Gemma 2 9B", "gemma2:9b", False],
        ["Phi 3 Mini", "phi3:mini", False],
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
            "AI_Profile", "Ollama_Standard", "Assistant",
            "A helpful, direct AI assistant.",
            "You are a helpful assistant. Provide clear, accurate, and concise information.",
            8192, 0.7,
        ]
    ],
}


class OllamaKeyRegistry(RoundRobinKeyRegistry):
    def __init__(self, file_path: str):
        super().__init__(
            file_path,
            placeholder_markers=["YOUR_OLLAMA_KEY", "KEY_HERE"],
            env_var="OLLAMA_API_KEY",
            env_var_prefix="OLLAMA_KEY",
            env_var_max_slots=10,
            config_version=OLLAMA_CONFIG_VERSION,
        )


class OllamaModelRegistry(ModelRegistryBase):
    def __init__(self, file_path: str):
        super().__init__(
            file_path,
            default_model_id="llama3.2:3b",
            default_rows_factory=lambda: SCHEMA_MODEL_REGISTRY_OLLAMA,
            config_version=OLLAMA_CONFIG_VERSION,
        )


class OllamaProfile(BejsonProfileBase):
    def __init__(self, file_path: str):
        super().__init__(
            file_path,
            schema_factory=lambda: SCHEMA_AI_PROFILE,
            config_version=OLLAMA_CONFIG_VERSION,
        )


class OllamaStandardPrompter:
    def __init__(self, key_registry_path: str, model_registry_path: str, profile_path: str):
        self.key_reg = OllamaKeyRegistry(key_registry_path)
        self.model_reg = OllamaModelRegistry(model_registry_path)
        self.profile = OllamaProfile(profile_path)
        self.current_key_idx = 0
        self.last_request_time = 0
        self.request_delay = 1.0

    def _get_next_key(self) -> Optional[str]:
        keys = self.key_reg.keys
        if not keys:
            return None
        import random
        return random.choice(keys)

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
        url = "https://ollama.com/api/chat"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        payload = {
            "model": m_info["id"],
            "messages": [
                {"role": "system", "content": system_instruction or self.profile.instruction},
                {"role": "user", "content": user_input},
            ],
            "stream": False,
            "options": {
                "num_predict": self.profile.config.get("MaxResponseTokens", 8192),
                "temperature": self.profile.config.get("Creativity", 0.7),
            }
        }
        self.last_request_time = time.time()
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=90)
            res.raise_for_status()
            data = res.json()
            if "message" in data and "content" in data["message"]:
                return data["message"]["content"].strip()
            return f"ERROR: No choices. {data}"
        except Exception as e:
            return f"ERROR: {str(e)}"


STD_KEY_PATH = CONFIG_DIR / "ollama_keys.104a.bejson"
STD_MODEL_PATH = CONFIG_DIR / "ollama_model_registry.104a.bejson"
STD_PROFILE_PATH = CONFIG_DIR / "ollama_standard_profile.bejson"


_std_prompter_singleton = None


def get_standard_prompter():
    """Zero-config OllamaStandardPrompter, cached after first call -- see
    lib_bejson_AI_bejson_groq.py's get_standard_prompter() for why this
    caching is the actual round-robin-key-rotation fix, not just an
    optimization."""
    global _std_prompter_singleton
    if _std_prompter_singleton is None:
        _std_prompter_singleton = OllamaStandardPrompter(STD_KEY_PATH, STD_MODEL_PATH, STD_PROFILE_PATH)
    return _std_prompter_singleton
