"""
Library:        lib_bejson_AI_bejson_groq.py
Family:         AI
Description:    Integration wrapper for Groq API services.
Version:        3.1.0
Date:           2026-08-22
Author:         Elton Boehnen
Contact:        eltonboehnen@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  7d3e9f42-1b6c-4a58-8e0d-9f2c5a7b3e14
Release_Version: 300

Changelog:
  3.1.0 (2026-09-28) -- Root-caused a round-robin-key-rotation bug found in this project's audit: get_standard_prompter() built a brand-new GroqStandardPrompter (and therefore a brand-new KeyRegistry, its rotation _idx reset to 0) on every single dispatch, since ai_dispatch.py calls it fresh per call. Round-robin existed in the class but never actually advanced past key #1 in practice. Cached after first call instead, matching the singleton pattern lib_bejson_AI_bejson_gemini.py's get_standard_api() already used correctly.
  3.0.0 - REGISTRY OVERHAUL, per Elton's direct instruction to fix the
          whole registry system, make every AI-family library self-
          contained, and stop hesitating. Replaces the 2.1.10 one-off fix
          (bundled defaults/ subfolder + self-heal-on-invalid-file) with
          the new shared, versioned system in ai_registry_base.py:
            - STD_KEY_PATH/STD_MODEL_PATH/STD_PROFILE_PATH moved from
              {HOME}/.env/... and {ADMIN_ROOT}/data/schemas/... to
              get_self_contained_dir(__file__) -- this library's own
              config/ subfolder, no external path dependency.
            - GroqProfile removed entirely; now uses the shared
              BejsonProfileBase directly (was 100% duplicated logic).
            - GroqModelRegistry/GroqKeyRegistry now pass config_version=2
              (bumped from the implicit version-less "1" every prior file
              on disk carries) -- this is what actually fixes "a model
              registry with the dead llama-3.3-70b-versatile still marked
              currently_active loads successfully and silently keeps
              sending it forever": any on-disk file from before this
              delivery has no Config_Version at all, so it's below 2 and
              gets regenerated automatically on next run, no manual file
              deletion required.
          Net effect: the empty-profile bug (2.1.8) and the stale-dead-
          model bug (root cause of the 404s seen after 2.1.9's model
          migration) are now the same bug, fixed the same way, and can't
          recur silently -- bumping config_version is the whole fix next
          time Groq deprecates a model.
  2.1.10 - SELF-HEALING PROFILE FIX (superseded by 3.0.0 above): profile
          self-healed from a bundled defaults/ subfolder copy on any load
          failure, but only covered structural invalidity (empty Values),
          not a structurally-valid-but-stale file (e.g. a dead model still
          marked active) -- see 3.0.0.
  2.1.9 - ROOT CAUSE FIX for "Groq is broken": researched GroqCloud's own
          deprecations page (console.groq.com/docs/deprecations) -- Groq
          announced on 2026-06-17 and SHUT DOWN on 2026-08-16 both
          llama-3.3-70b-versatile and llama-3.1-8b-instant for free/
          developer-tier usage. Migrated the default model registry to
          Groq's own recommended replacements: openai/gpt-oss-120b (new
          default) and openai/gpt-oss-20b, plus qwen/qwen3.6-27b.
  2.1.8 - BUG FIX: GROQ_PROFILE_SCHEMA's default had an empty "Values": []
          list, so GroqProfile.load() ALWAYS raised "has no Values rows"
          on a fresh install and silently fell back to a blank system
          instruction / empty config. Populated a proper default row.
  2.1.7 - Cap default max_tokens in GroqStandardPrompter payload to 8192
          (down from 32768) to avoid Groq 413 Payload Too Large errors.
  2.1.6 - Modularization: GroqKeyRegistry/GroqModelRegistry subclass
          lib_bejson_AI_ai_registry_base.py's shared atomic base instead
          of reimplementing BEJSON key-loading/round-robin/model-lookup
          logic. Gains GROQ_KEY_1.._10 numbered env-slot fallback.
  2.1.5 - AI-family audit fix: module-level VERSION var re-synced to a
          single source of truth.
"""

import os
import sys
import json
import time
import requests
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# --- Path Resolution Utility ---
LIB_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_DIR = os.path.join(os.path.dirname(LIB_DIR), "Core")
if CORE_DIR not in sys.path:
    sys.path.append(CORE_DIR)

from lib_bejson_Core_bejson_core import bejson_core_get_field_map
from lib_bejson_AI_ai_registry_base import (
    RoundRobinKeyRegistry,
    ModelRegistryBase,
    BejsonProfileBase,
    get_self_contained_dir,
)

VERSION = "3.1.0"

# Config_Version for this provider's model registry -- bump this whenever
# the default model list below changes (e.g. Groq deprecates a model
# again). Any on-disk file with no Config_Version, or one older than this,
# is regenerated automatically on next run -- see ai_registry_base.py's
# ensure_current(). Profile shares the same version for simplicity.
GROQ_CONFIG_VERSION = 2

# --- Self-contained storage: this library's own config/ subfolder, no
# external ADMIN_ROOT/HOME dependency. ---
CONFIG_DIR = get_self_contained_dir(__file__)

# --- SCHEMAS ---
GROQ_PROFILE_SCHEMA = {
    "Format": "BEJSON",
    "Format_Version": "104",
    "Format_Creator": "Elton Boehnen",
    "Records_Type": ["AI_Profile"],
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
    ],
    "Values": [
        [
            "AI_Profile", "Groq_Standard", "Assistant",
            "A helpful and professional AI assistant.",
            "You are a helpful assistant. Provide clear, accurate, and concise information.",
            [], "Emoji", "", "\U0001F916", 8192, 0.7,
            ["Professional", "Helpful"], "Formal", "Balanced",
            False, 0.0, False, True,
        ]
    ]
}


def _default_model_rows() -> dict:
    return {
        "Format": "BEJSON", "Format_Version": "104a", "Format_Creator": "Elton Boehnen",
        "Records_Type": ["GroqModel"],
        "Fields": [
            {"name": "model_name", "type": "string"},
            {"name": "model_id", "type": "string"},
            {"name": "currently_active", "type": "boolean"},
        ],
        "Values": [
            ["GPT-OSS 120B", "openai/gpt-oss-120b", True],
            ["GPT-OSS 20B", "openai/gpt-oss-20b", False],
            ["Qwen3.6 27B", "qwen/qwen3.6-27b", False],
        ],
    }


# --- Registry Managers ---

class GroqKeyRegistry(RoundRobinKeyRegistry):
    def __init__(self, file_path: str):
        super().__init__(
            file_path,
            placeholder_markers=["YOUR_GROQ_KEY", "KEY_HERE"],
            env_var_prefix="GROQ_KEY",
            env_var_max_slots=10,
            config_version=GROQ_CONFIG_VERSION,
        )


class GroqModelRegistry(ModelRegistryBase):
    def __init__(self, file_path: str):
        super().__init__(
            file_path,
            default_model_id="openai/gpt-oss-120b",
            default_rows_factory=_default_model_rows,
            config_version=GROQ_CONFIG_VERSION,
        )


class GroqProfile(BejsonProfileBase):
    def __init__(self, file_path: str):
        super().__init__(
            file_path,
            schema_factory=lambda: GROQ_PROFILE_SCHEMA,
            config_version=GROQ_CONFIG_VERSION,
        )


# --- Unified Prompter Engine ---
class GroqStandardPrompter:
    def __init__(self, key_registry_path: str, model_registry_path: str, profile_path: str):
        self.key_reg = GroqKeyRegistry(key_registry_path)
        self.model_reg = GroqModelRegistry(model_registry_path)
        self.profile = GroqProfile(profile_path)
        self.current_key_idx = 0
        self.last_request_time = 0
        self.request_delay = 1.0

    def _get_next_key(self) -> Optional[str]:
        keys = self.key_reg.keys
        if not keys: return None
        key = keys[self.current_key_idx]
        self.current_key_idx = (self.current_key_idx + 1) % len(keys)
        return key

    def prompt(self, user_input: str, model_id: Optional[str] = None) -> str:
        now = time.time()
        diff = now - self.last_request_time
        if diff < self.request_delay: time.sleep(self.request_delay - diff)

        key = self._get_next_key()
        if not key: return "ERROR: No valid API keys."

        m_info = self.model_reg.get_model_info(model_id)
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        payload = {
            "model": m_info["id"],
            "messages": [
                {"role": "system", "content": self.profile.instruction},
                {"role": "user", "content": user_input}
            ],
            "max_tokens": self.profile.config.get("MaxResponseTokens", 8192),
            "temperature": self.profile.config.get("Creativity", 0.7)
        }
        self.last_request_time = time.time()
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=90)
            res.raise_for_status()
            data = res.json()
            if "choices" in data and data["choices"]:
                return data["choices"][0]["message"]["content"].strip()
            return f"ERROR: No choices. {json.dumps(data)}"
        except Exception as e:
            return f"ERROR: {str(e)}"

# --- Global Standard Paths: self-contained, inside this library's own
# config/ folder (see get_self_contained_dir() above) -- no more
# {HOME}/.env/... or {ADMIN_ROOT}/data/schemas/... external dependency. ---
STD_KEY_PATH = CONFIG_DIR / "groq_keys.104a.bejson"
STD_MODEL_PATH = CONFIG_DIR / "groq_model_registry.104a.bejson"
STD_PROFILE_PATH = CONFIG_DIR / "groq_standard_profile.bejson"

_std_prompter_singleton = None


def get_standard_prompter():
    """
    Zero-config GroqStandardPrompter, cached after first call. This
    caching is the actual fix for the round-robin key bug found in this
    project's audit: GroqStandardPrompter's KeyRegistry rotates via an
    internal _idx counter, but that counter only persists if the SAME
    registry instance is reused across calls. Before this fix,
    get_standard_prompter() built a brand-new prompter (and therefore a
    brand-new KeyRegistry, _idx reset to 0) on every single dispatch --
    round-robin existed in the class but never executed in practice, since
    ai_dispatch.py calls get_standard_prompter() fresh on every call. Now
    matches the singleton pattern lib_bejson_AI_bejson_gemini.py's
    get_standard_api() already used correctly.
    """
    global _std_prompter_singleton
    if _std_prompter_singleton is None:
        _std_prompter_singleton = GroqStandardPrompter(STD_KEY_PATH, STD_MODEL_PATH, STD_PROFILE_PATH)
    return _std_prompter_singleton
