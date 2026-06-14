"""
Library:      lib_bejson_openrouter.py
Family:       AI
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.1.3 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-06-05
Description:  Multi-model routing gateway for AI interactions.
REMEDIATED:   Purged transition stubs for Core and Env (Phase 1).
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

from lib_bejson_env import resolve_path as resolve_system_path

# --- EMBEDDED SCHEMAS ---
SCHEMA_KEY_REGISTRY = {
    "Format": "BEJSON",
    "Format_Version": "104a",
    "Format_Creator": "Elton Boehnen",
    "Schema_Name": "OpenRouterKeyRegistry",
    "Records_Type": ["ApiKey"],
    "Fields": [
        {"name": "key_slot", "type": "integer"},
        {"name": "key", "type": "string"}
    ],
    "Values": []
}

SCHEMA_MODEL_REGISTRY = {
    "Format": "BEJSON",
    "Format_Version": "104a",
    "Format_Creator": "Elton Boehnen",
    "Schema_Name": "OpenRouterModelRegistry",
    "Records_Type": ["OpenRouterModel"],
    "Fields": [
        {"name": "model_name", "type": "string"},
        {"name": "model_id", "type": "string"},
        {"name": "currently_active", "type": "boolean"},
        {"name": "thinking_enabled", "type": "boolean"}
    ],
    "Values": [
        ["DeepSeek R1 (Free)", "deepseek/deepseek-r1:free", True, True],
        ["Gemma 4 27B (Preview)", "google/gemma-4-27b-it", False, False],
        ["Gemma 3 27B (Preview)", "google/gemma-3-27b-it", False, False],
        ["Liquid LFM 2.5 Thinking", "liquid/lfm-2.5-1.2b-thinking:free", False, True],
        ["Llama 3.3 70B", "meta-llama/llama-3.3-70b-instruct", False, False]
    ]
}

SCHEMA_AI_PROFILE = {
    "Format": "BEJSON",
    "Format_Version": "104",
    "Format_Creator": "Elton Boehnen",
    "Records_Type": ["AI_Profile"],
    "Parent_Hierarchy": "/LLM_Configuration",
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

from lib_bejson_core import (
    bejson_core_load_file, 
    bejson_core_get_field_index, 
    bejson_core_get_field_map, 
    bejson_core_atomic_write
)

# --- Legacy Fallback Constants ---
_OR_MODEL_LEGACY   = {"model_name": 0, "model_id": 1, "currently_active": 2, "thinking_enabled": 3}
_OR_PROFILE_LEGACY = {"SystemInstruction": 4} 

# --- Registry Managers ---
class OpenRouterKeyRegistry:
    def __init__(self, file_path: str):
        self.file_path = Path(resolve_system_path(file_path))
        self.keys = []
        if not self.file_path.exists():
            self.create_default()
        self.load()

    def create_default(self):
        os.makedirs(self.file_path.parent, exist_ok=True)
        bejson_core_atomic_write(str(self.file_path), SCHEMA_KEY_REGISTRY)

    def load(self):
        try:
            data = bejson_core_load_file(str(self.file_path))
            idx = bejson_core_get_field_index(data, "key")
            if idx != -1:
                self.keys = [row[idx] for row in data["Values"] if "YOUR_OPENROUTER_KEY" not in str(row[idx]) and "KEY_HERE" not in str(row[idx])]
        except Exception as e:
            logging.error(f"[OR_Lib] Failed to load keys from {self.file_path}: {e}")
            self.keys = []

class OpenRouterModelRegistry:
    def __init__(self, file_path: str):
        self.file_path = Path(resolve_system_path(file_path))
        self.models = []
        self.active_model_id = "deepseek/deepseek-r1:free"
        if not self.file_path.exists():
            self.create_default()
        self.load()

    def create_default(self):
        os.makedirs(self.file_path.parent, exist_ok=True)
        bejson_core_atomic_write(str(self.file_path), SCHEMA_MODEL_REGISTRY)

    def load(self):
        try:
            data = bejson_core_load_file(str(self.file_path))
            fi = bejson_core_get_field_map(data)
            
            id_idx     = fi.get("model_id",         _OR_MODEL_LEGACY["model_id"])
            active_idx = fi.get("currently_active", _OR_MODEL_LEGACY["currently_active"])
            think_idx  = fi.get("thinking_enabled", _OR_MODEL_LEGACY["thinking_enabled"])
            
            self.models = []
            for row in data["Values"]:
                m_info = {"id": row[id_idx], "thinking": row[think_idx] if think_idx != -1 and think_idx < len(row) else False}
                self.models.append(m_info)
                if row[active_idx] is True:
                    self.active_model_id = row[id_idx]
        except Exception as e:
            logging.warning(f"[OR_Lib] Failed to load model registry {self.file_path}, using defaults: {e}")
            for row in SCHEMA_MODEL_REGISTRY["Values"]:
                self.models.append({"id": row[1], "thinking": row[3]})

    def get_model_info(self, model_id: Optional[str] = None) -> Dict[str, Any]:
        target_id = model_id or self.active_model_id
        for m in self.models:
            if m["id"] == target_id: return m
        return {"id": target_id, "thinking": False}

class OpenRouterProfile:
    def __init__(self, file_path: str):
        self.file_path = Path(resolve_system_path(file_path))
        self.instruction = ""
        self.config = {}
        if not self.file_path.exists():
            self.create_default()
        self.load()

    def create_default(self):
        os.makedirs(self.file_path.parent, exist_ok=True)
        bejson_core_atomic_write(str(self.file_path), SCHEMA_AI_PROFILE)

    def load(self):
        try:
            data = bejson_core_load_file(str(self.file_path))
            fi = bejson_core_get_field_map(data)
            
            instr_idx = fi.get("SystemInstruction", _OR_PROFILE_LEGACY["SystemInstruction"])
            self.instruction = data["Values"][0][instr_idx]
            self.config = {f["name"]: data["Values"][0][i] for i, f in enumerate(data["Fields"])}
        except Exception as e:
            logging.warning(f"[OR_Lib] Failed to load profile {self.file_path}, using defaults: {e}")
            self.instruction = SCHEMA_AI_PROFILE["Values"][0][4]
            self.config = {f["name"]: SCHEMA_AI_PROFILE["Values"][0][i] for i, f in enumerate(SCHEMA_AI_PROFILE["Fields"])}

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

# --- Global Standard Paths ---
STD_KEY_PATH = resolve_system_path("{HOME}/.env/openrouter_keys.bejson")
STD_MODEL_PATH = resolve_system_path("{ADMIN_ROOT}/data/schemas/openrouter_model_registry.104a.bejson")
STD_PROFILE_PATH = resolve_system_path("{ADMIN_ROOT}/data/schemas/openrouter_standard_profile.bejson")

def get_standard_prompter():
    return OpenRouterStandardPrompter(STD_KEY_PATH, STD_MODEL_PATH, STD_PROFILE_PATH)
