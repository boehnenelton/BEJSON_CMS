"""
Library:      lib_bejson_gemini.py
Family:       AI
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.1.2 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-06-04
Description:  Integration wrapper for Google Gemini API using the official google-genai SDK.
REMEDIATED:   Implemented Field Map Indexing with Safe Get fallbacks (Phase 4.1).
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

try:
    from lib_bejson_core import (
        bejson_core_load_file, 
        bejson_core_get_field_index, 
        bejson_core_get_field_map,
        bejson_core_atomic_write
    )
    from lib_bejson_schema import SCHEMA_MODEL_REGISTRY
except ImportError as e:
    print(f"Gemini Lib Error: Missing core dependencies. {e}")
    sys.exit(1)

# --- Legacy Fallback Constants ---
_GEMINI_MODEL_LEGACY = {
    "model_name": 0, 
    "model_id": 1, 
    "currently_active": 2,
    "thinking_enabled": 3, 
    "google_search_enabled": 4
}

# --- Registry Managers ---

class GeminiKeyRegistry:
    def __init__(self, file_path: Union[str, Path]):
        self.file_path = Path(file_path)
        self.keys = []
        if not self.file_path.exists(): self._create_default()
        self.load()

    def _create_default(self):
        try:
            os.makedirs(self.file_path.parent, exist_ok=True)
            default_keys = {
                "Format": "BEJSON", "Format_Version": "104", "Records_Type": ["ApiKey"],
                "Fields": [{"name": "key", "type": "string"}],
                "Values": [[os.getenv("GEMINI_API_KEY", "YOUR_KEY_HERE")]]
            }
            bejson_core_atomic_write(str(self.file_path), default_keys)
        except Exception as e: logging.warning(f"[GeminiLib] Key default fail: {e}")

    def load(self):
        try:
            # REMEDIATED: Support centralized registry + Environment Variables (Phase 2)
            env_keys = os.environ.get("GEMINI_API_KEYS", "").split(",")
            self.keys = [k.strip() for k in env_keys if k.strip()]

            data = bejson_core_load_file(str(self.file_path))
            idx = bejson_core_get_field_index(data, "key")
            if idx != -1:
                registry_keys = [row[idx] for row in data["Values"] if "YOUR_KEY" not in str(row[idx])]
                self.keys.extend(registry_keys)
        except Exception:
            # Fallback to env keys if file load fails
            env_keys = os.environ.get("GEMINI_API_KEYS", "").split(",")
            self.keys = [k.strip() for k in env_keys if k.strip()]

class GeminiModelRegistry:
    def __init__(self, file_path: Union[str, Path]):
        self.file_path = Path(file_path)
        self.models = []
        # Remediation: Default to 2.5 Flash as per audit
        self.active_model_id = "gemini-2.5-flash"
        if not self.file_path.exists(): self._create_default()
        self.load()

    def _create_default(self):
        try:
            os.makedirs(self.file_path.parent, exist_ok=True)
            bejson_core_atomic_write(str(self.file_path), SCHEMA_MODEL_REGISTRY)
        except Exception: pass

    def load(self):
        try:
            data = bejson_core_load_file(str(self.file_path))
            fi = bejson_core_get_field_map(data)
            
            id_idx     = fi.get("model_id",              _GEMINI_MODEL_LEGACY["model_id"])
            act_idx    = fi.get("currently_active",      _GEMINI_MODEL_LEGACY["currently_active"])
            think_idx  = fi.get("thinking_enabled",      _GEMINI_MODEL_LEGACY["thinking_enabled"])
            search_idx = fi.get("google_search_enabled", _GEMINI_MODEL_LEGACY["google_search_enabled"])
            
            self.models = []
            for row in data["Values"]:
                m_info = {
                    "id": row[id_idx],
                    "thinking": row[think_idx] if think_idx != -1 and think_idx < len(row) else False,
                    "search": row[search_idx] if search_idx != -1 and search_idx < len(row) else False
                }
                self.models.append(m_info)
                if row[act_idx] is True: self.active_model_id = row[id_idx]
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
            raise RuntimeError("google-genai SDK not installed.")
        if not self.keys.keys:
            raise Exception("No Gemini API keys found.")
        
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
            raise Exception(f"Gemini API Error: {e}")

