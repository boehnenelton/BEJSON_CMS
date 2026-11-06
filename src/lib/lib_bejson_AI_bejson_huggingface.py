"""
Library:        lib_bejson_AI_bejson_huggingface.py
Family:         AI
Description:    Hugging Face Inference Providers adapter (OpenAI-compatible
                 chat completions router at router.huggingface.co, NOT the
                 legacy api-inference.huggingface.co endpoint). Uses the
                 shared lib_bejson_AI_ai_openai_compatible_base.py REST
                 client (also used by Provocative) for the actual HTTP
                 call, and the shared ai_registry_base.py classes for key/
                 model/profile storage -- same pattern as Groq/OpenRouter/
                 Grok/Gemini, not a standalone design.

                 Model IDs on this router are addressed as
                 "<hf_repo>:<provider>" (e.g.
                 "deepseek-ai/DeepSeek-V3.1:novita") or bare "<hf_repo>" to
                 let HF auto-select a provider. Provider names currently
                 routed: baseten, cerebras, cohere, deepinfra, fal-ai,
                 featherless-ai, fireworks-ai, groq, hf-inference, novita,
                 nscale, openai, ovhcloud, publicai, replicate, scaleway,
                 together, wavespeed, zai-org (source: huggingface_hub
                 InferenceClient docs).
Version:        2.1.0
Date:           2026-08-22
Author:         Elton Boehnen
Contact:        eltonboehnen@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  aee9149e-5e05-4d8d-82f2-fb9ddaf0ae72
Release_Version: 300

Changelog:
  2.1.0 (2026-09-28) -- Root-caused a round-robin-key-rotation bug found in this project's audit: get_standard_prompter() built a brand-new HuggingFaceStandardPrompter (and therefore a brand-new KeyRegistry, its rotation _idx reset to 0) on every single dispatch, since ai_dispatch.py calls it fresh per call. Round-robin existed in the class but never actually advanced past key #1 in practice. Cached after first call instead, matching the singleton pattern lib_bejson_AI_bejson_gemini.py's get_standard_api() already used correctly.
  2.0.0 - REPLACES the 1.0.0 stub entirely. That version had no model
          registry at all (one hardcoded, explicitly UNVERIFIED default
          model, "meta-llama/Llama-3.1-8B-Instruct:novita") and no
          profile. Brought up to full parity with the rest of the AI
          family, on the new self-contained/versioned system (same pass
          as groq.py/openrouter.py/grok.py):
            - HuggingFaceModelRegistry (field-map-cached, versioned,
              self-healing) with a real, previously-verified model
              lineup, replacing the single unverified constant.
            - HuggingFaceProfile via the shared BejsonProfileBase.
            - STD_KEY_PATH/STD_MODEL_PATH/STD_PROFILE_PATH all under this
              library's own self-contained config/ subfolder -- no
              {ADMIN_ROOT}/... dependency.
            - get_standard_prompter() added, matching every other
              provider's entry point (was previously just a bare
              module-level prompt() function backed by a lazily-built
              singleton key registry).
          HTTP call still goes through the shared OpenAICompatibleClient
          (lib_bejson_AI_ai_openai_compatible_base.py) -- unchanged,
          still shared with Provocative.
  1.0.0 (2026-08-13) -- Initial creation (superseded above).
"""

import os
import sys
import time
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

VERSION = "2.1.0"

HF_BASE_URL = "https://router.huggingface.co/v1"
HF_DEFAULT_MODEL = "openai/gpt-oss-120b"

# Config_Version for this provider's stores -- bump whenever a default
# schema below changes. See ai_registry_base.py's ensure_current().
HF_CONFIG_VERSION = 1

CONFIG_DIR = get_self_contained_dir(__file__)

SCHEMA_MODEL_REGISTRY_HF = {
    "Format": "BEJSON", "Format_Version": "104a", "Format_Creator": "Elton Boehnen",
    "Records_Type": ["HuggingFaceModel"],
    "Fields": [
        {"name": "model_name", "type": "string"},
        {"name": "model_id", "type": "string"},
        {"name": "currently_active", "type": "boolean"},
        {"name": "thinking_enabled", "type": "boolean"},
        {"name": "context_window", "type": "integer"},
    ],
    "Values": [
        ["GPT-OSS 120B (auto-routed provider)", HF_DEFAULT_MODEL, True, False, 131072],
        ["DeepSeek V3.1 (novita)", "deepseek-ai/DeepSeek-V3.1:novita", False, True, 131072],
        ["Llama 3.3 70B (auto-routed provider)", "meta-llama/Llama-3.3-70B-Instruct", False, False, 131072],
        ["Kimi K2 Instruct (groq)", "moonshotai/Kimi-K2-Instruct-0905:groq", False, False, 131072],
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
        {"name": "Thinking_Supported", "type": "boolean"},
    ],
    "Values": [
        [
            "AI_Profile", "HuggingFace_Standard", "Assistant",
            "A helpful and professional AI assistant.",
            "You are a helpful assistant. Provide clear, accurate, and concise information.",
            16384, 0.7, False,
        ]
    ],
}


class HuggingFaceKeyRegistry(RoundRobinKeyRegistry):
    def __init__(self, file_path: str):
        super().__init__(
            file_path,
            placeholder_markers=["YOUR_HUGGINGFACE_KEY", "KEY_HERE"],
            env_var_prefix="HUGGINGFACE_MM_KEY",  # matches the roster naming exactly
            env_var_max_slots=20,
            config_version=HF_CONFIG_VERSION,
        )


class HuggingFaceModelRegistry(ModelRegistryBase):
    def __init__(self, file_path: str):
        super().__init__(
            file_path,
            default_model_id=HF_DEFAULT_MODEL,
            default_rows_factory=lambda: SCHEMA_MODEL_REGISTRY_HF,
            config_version=HF_CONFIG_VERSION,
        )

    def _extra_fields(self, row, fmap):
        think_idx = fmap.get("thinking_enabled")
        ctx_idx = fmap.get("context_window")
        return {
            "thinking": row[think_idx] if think_idx is not None and think_idx < len(row) else False,
            "context_window": row[ctx_idx] if ctx_idx is not None and ctx_idx < len(row) else 131072,
        }

    def get_model_info(self, model_id: Optional[str] = None) -> Dict[str, Any]:
        target_id = model_id or self.active_model_id
        for m in self.models:
            if m["id"] == target_id:
                return m
        return {"id": target_id, "thinking": False, "context_window": 131072}


class HuggingFaceProfile(BejsonProfileBase):
    def __init__(self, file_path: str):
        super().__init__(
            file_path,
            schema_factory=lambda: SCHEMA_AI_PROFILE,
            config_version=HF_CONFIG_VERSION,
        )


_client = OpenAICompatibleClient("huggingface", HF_BASE_URL, HF_DEFAULT_MODEL)


class HuggingFaceStandardPrompter:
    def __init__(self, key_registry_path: str, model_registry_path: str, profile_path: str):
        self.key_reg = HuggingFaceKeyRegistry(key_registry_path)
        self.model_reg = HuggingFaceModelRegistry(model_registry_path)
        self.profile = HuggingFaceProfile(profile_path)
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
               system_instruction: Optional[str] = None) -> Dict[str, str]:
        now = time.time()
        diff = now - self.last_request_time
        if diff < self.request_delay:
            time.sleep(self.request_delay - diff)

        key = self._get_next_key()
        if not key:
            return {"content": "ERROR: No valid API keys.", "thought": ""}

        m_info = self.model_reg.get_model_info(model_id)
        instruction = system_instruction or self.profile.instruction

        self.last_request_time = time.time()
        try:
            content = _client.chat(
                user_input, key,
                model=m_info["id"],
                system_instruction=instruction,
                max_tokens=self.profile.config.get("MaxResponseTokens", 16384),
                temperature=self.profile.config.get("Creativity", 0.7),
                timeout=90,
            )
            return {"content": (content or "").strip(), "thought": ""}
        except Exception as e:
            return {"content": f"ERROR: {str(e)}", "thought": ""}

    def get_model_info(self, model_id: Optional[str] = None) -> Dict[str, Any]:
        return self.model_reg.get_model_info(model_id)


# --- Global Standard Paths: self-contained, inside this library's own
# config/ folder -- no more {ADMIN_ROOT}/... dependency.
STD_KEY_PATH = CONFIG_DIR / "huggingface_keys.104a.bejson"
STD_MODEL_PATH = CONFIG_DIR / "huggingface_model_registry.104a.bejson"
STD_PROFILE_PATH = CONFIG_DIR / "huggingface_standard_profile.bejson"


_std_prompter_singleton = None


def get_standard_prompter():
    """Zero-config HuggingFaceStandardPrompter, cached after first call --
    see lib_bejson_AI_bejson_groq.py's get_standard_prompter() for why
    this caching is the actual round-robin-key-rotation fix, not just an
    optimization."""
    global _std_prompter_singleton
    if _std_prompter_singleton is None:
        _std_prompter_singleton = HuggingFaceStandardPrompter(STD_KEY_PATH, STD_MODEL_PATH, STD_PROFILE_PATH)
    return _std_prompter_singleton
