"""
Library:      lib_bejson_groq.py
Family:       AI
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.1.3 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-06-05
Description:  Integration wrapper for Groq API services.
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

# --- SCHEMAS INFERRED VIA LIB_BEJSON_SCHEMA ---
GROQ_PROFILE_SCHEMA = {
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
    ],
    "Values": []
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
_GROQ_MODEL_LEGACY   = {"model_name": 0, "model_id": 1, "currently_active": 2}
_GROQ_PROFILE_LEGACY = {"SystemInstruction": 4} # Note: Groq profile schema varies, using safe fallback

# --- Registry Managers ---
class GroqKeyRegistry:
    def __init__(self, file_path: str):
        self.file_path = Path(resolve_system_path(file_path))
        self.keys = []
        if not self.file_path.exists():
            self.create_default()
        self.load()

    def create_default(self):
        os.makedirs(self.file_path.parent, exist_ok=True)
        bejson_core_atomic_write(str(self.file_path), {"Format": "BEJSON", "Format_Version": "104a", "Format_Creator": "Elton Boehnen", "Records_Type": ["ApiKey"], "Fields": [{"name": "key_slot", "type": "integer"}, {"name": "key", "type": "string"}], "Values": []})

    def load(self):
        try:
            data = bejson_core_load_file(str(self.file_path))
            idx = bejson_core_get_field_index(data, "key")
            if idx != -1:
                self.keys = [row[idx] for row in data["Values"] if "YOUR_GROQ_KEY" not in str(row[idx]) and "KEY_HERE" not in str(row[idx])]
        except Exception as e:
            logging.error(f"[GroqLib] Failed to load keys from {self.file_path}: {e}")
            self.keys = []

class GroqModelRegistry:
    def __init__(self, file_path: str):
        self.file_path = Path(resolve_system_path(file_path))
        self.models = []
        self.active_model_id = "llama-3.3-70b-versatile"
        if not self.file_path.exists():
            self.create_default()
        self.load()

    def create_default(self):
        os.makedirs(self.file_path.parent, exist_ok=True)
        bejson_core_atomic_write(str(self.file_path), {"Format": "BEJSON", "Format_Version": "104a", "Format_Creator": "Elton Boehnen", "Records_Type": ["GroqModel"], "Fields": [{"name": "model_name", "type": "string"}, {"name": "model_id", "type": "string"}, {"name": "currently_active", "type": "boolean"}], "Values": [["Llama 3.3 70B Versatile", "llama-3.3-70b-versatile", True], ["Llama 3.1 8B Instant", "llama-3.1-8b-instant", False]]})

    def load(self):
        try:
            data = bejson_core_load_file(str(self.file_path))
            fi = bejson_core_get_field_map(data)
            
            id_idx = fi.get("model_id", _GROQ_MODEL_LEGACY["model_id"])
            active_idx = fi.get("currently_active", _GROQ_MODEL_LEGACY["currently_active"])
            
            self.models = []
            for row in data["Values"]:
                m_info = {"id": row[id_idx]}
                self.models.append(m_info)
                if row[active_idx] is True:
                    self.active_model_id = row[id_idx]
        except Exception as e:
            logging.warning(f"[GroqLib] Failed to load model registry {self.file_path}, using defaults: {e}")
            # Fallback to llama3
            self.models = [{"id": "llama-3.3-70b-versatile"}]

    def get_model_info(self, model_id: Optional[str] = None) -> Dict[str, Any]:
        target_id = model_id or self.active_model_id
        for m in self.models:
            if m["id"] == target_id: return m
        return {"id": target_id}

class GroqProfile:
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
            
            instr_idx = fi.get("SystemInstruction", _GROQ_PROFILE_LEGACY["SystemInstruction"])
            self.instruction = data["Values"][0][instr_idx]
            self.config = {f["name"]: data["Values"][0][i] for i, f in enumerate(data["Fields"])}
        except Exception as e:
            logging.warning(f"[GroqLib] Failed to load profile {self.file_path}, using defaults: {e}")
            self.instruction = ""
            self.config = {}

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
            "max_tokens": self.profile.config.get("MaxResponseTokens", 32768),
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

# --- Global Standard Paths ---
STD_KEY_PATH = resolve_system_path("{HOME}/.env/groq_keys.bejson")
STD_MODEL_PATH = resolve_system_path("{ADMIN_ROOT}/data/schemas/groq_model_registry.104a.bejson")
STD_PROFILE_PATH = resolve_system_path("{ADMIN_ROOT}/data/schemas/groq_standard_profile.bejson")

VERSION = "2.1.2"

def get_standard_prompter():
    return GroqStandardPrompter(STD_KEY_PATH, STD_MODEL_PATH, STD_PROFILE_PATH)
