"""
Library:      lib_bejson_genai.py
Family:       AI
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.1.4 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-06-05
Description:  Interface for Google Generative AI (GenAI) models.
REMEDIATED:   Purged transition stubs for Core and Env (Phase 1).
"""

import os
import json
import time
import random
import sys
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

# Add Lib directory to path for relative imports
LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

# Resilient sibling resolution for nested MFDB structures
parent_dir = os.path.dirname(LIB_DIR)
for sibling in ["Core", "Env", "AI", "Utility"]:
    sibling_path = os.path.join(parent_dir, sibling)
    if os.path.exists(sibling_path) and sibling_path not in sys.path:
        sys.path.append(sibling_path)

from lib_bejson_env import resolve_path
from lib_bejson_core import bejson_core_get_field_map

# ANSI Status Colors
C_RED = "\033[91m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_NC = "\033[0m"
C_BOLD = "\033[1m"

DEFAULT_KEY_FILE = resolve_path("{HOME}/.env/gemini_keys.bejson")

MODELS = [
    "gemini-3-flash-preview",
    "gemini-flash-lite-latest",
    "gemini-flash-latest",
    "gemini-2.5",
    "gemini-2.5-pro",
    "gemini-3-pro-preview",
    "gemini-3.1-pro-preview"
]

class GenAIKeyManager:
    def __init__(self, key_file: str = DEFAULT_KEY_FILE):
        self.key_file = key_file
        self.keys = []
        self.current_index = 0
        self.load_keys()

    def load_keys(self):
        """Load keys from the centralized BEJSON 104a key file and environment variables."""
        # REMEDIATED: Support centralized registry + Environment Variables (Phase 2)
        env_keys = os.environ.get("GEMINI_API_KEYS", "").split(",")
        self.keys = [k.strip() for k in env_keys if k.strip()]

        if not os.path.exists(self.key_file):
            return
        try:
            with open(self.key_file, 'r') as f:
                doc = json.load(f)
                
                # Identify 'key' field index using Field Map standard
                fm = bejson_core_get_field_map(doc)
                key_idx = fm.get("key", 0) # Legacy fallback to index 0
                
                # Extract keys from Values
                registry_keys = [row[key_idx] for row in doc.get("Values", []) if len(row) > key_idx and row[key_idx] and "YOUR_KEY" not in str(row[key_idx])]
                self.keys.extend(registry_keys)
                    
            # Randomize order for true round-robin
            random.shuffle(self.keys)
        except Exception:
            pass

    def get_next_key(self) -> Optional[str]:
        """Get the next key in rotation."""
        if not self.keys:
            self.load_keys() # Retry once
        if not self.keys:
            return None
        
        key = self.keys[self.current_index % len(self.keys)]
        self.current_index += 1
        return key

    def get_key_count(self) -> int:
        return len(self.keys)

class GenAIClient:
    def __init__(self, key_manager: GenAIKeyManager = None):
        self.km = key_manager or GenAIKeyManager()
        self.status_callback: Optional[Callable[[str, str], None]] = None
        
        # Try to import SDK
        try:
            from google import genai
            from google.genai import types
            self.genai = genai
            self.types = types
            self.sdk_available = True
        except ImportError:
            self.sdk_available = False

    def set_status_callback(self, callback: Callable[[str, str], None]):
        """Set a custom callback for status updates. (state, message)"""
        self.status_callback = callback

    def update_status(self, state: str, message: str):
        """Standardized status updates following policy (ALL CAPS)."""
        msg = message.upper()
        if self.status_callback:
            self.status_callback(state, msg)
        else:
            # Default terminal status bar logic
            color = C_NC
            if state == "error": color = C_RED
            elif state == "success": color = C_GREEN
            elif state == "wait": color = C_YELLOW
            
            # Simple ANSI line overwrite status
            sys.stdout.write(f"\r{C_BOLD}STATUS:{C_NC} {color}{msg}{C_NC} {' ' * 20}\r")
            sys.stdout.flush()

    def embed_content(self, text: str, model: str = "models/gemini-embedding-001") -> Optional[List[float]]:
        """Generate embeddings for the given text."""
        if not self.sdk_available:
            self.update_status("error", "ERROR: google-genai SDK not installed.")
            return None

        key_count = self.km.get_key_count()
        if key_count == 0:
            self.update_status("error", "ERROR: No API keys found.")
            return None

        for i in range(key_count):
            api_key = self.km.get_next_key()
            try:
                client = self.genai.Client(api_key=api_key)
                response = client.models.embed_content(model=model, contents=text)
                return response.embeddings[0].values
            except Exception:
                continue
        return None

    def generate_content(self, prompt: str, model: str = "gemini-3-flash-preview", system_instruction: str = None) -> Optional[str]:
        """Generate content with automatic key rotation and mandatory status feedback."""
        if not self.sdk_available:
            self.update_status("error", "ERROR: google-genai SDK not installed.")
            return None

        if model not in MODELS:
            # Policy: Only 2.5+
            self.update_status("error", f"ERROR: Model {model} not allowed by policy.")
            return None

        key_count = self.km.get_key_count()
        if key_count == 0:
            self.update_status("error", "ERROR: No API keys found in key pool.")
            return None

        # Try keys round-robin
        last_error = ""
        for i in range(key_count):
            api_key = self.km.get_next_key()
            if not api_key: continue

            try:
                self.update_status("wait", f"ATTEMPT {i+1}: DISPATCHING QUERY...")
                client = self.genai.Client(api_key=api_key)
                
                config = None
                if system_instruction:
                    config = self.types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.7
                    )

                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config
                )
                
                self.update_status("success", "QUERY SUCCESSFUL")
                print() # Move past status line
                return response.text

            except Exception as e:
                last_error = str(e)
                self.update_status("error", f"KEY FAILED: {last_error[:50]}...")
                time.sleep(1) # Brief pause before next key
                continue

        self.update_status("error", "ALL KEYS EXHAUSTED")
        return None

# ─── COMPATIBILITY LAYER ───────────────────────────────────────────────────

# Compatibility Aliases
GeminiKeyRegistry = GenAIKeyManager
GeminiModelRegistry = GenAIClient

class GeminiStandardPrompter:
    """Compatibility wrapper for legacy scripts (Phase 1)."""
    def __init__(self, key_registry_path: str = None, model_registry_path: str = None, profile_path: str = None):
        self.key_reg = GenAIKeyManager(key_registry_path or DEFAULT_KEY_FILE)
        self.client = GenAIClient(self.key_reg)
        self.model_registry_path = model_registry_path
        self.profile_path = profile_path

    def prompt(self, text: str, model: str = "gemini-3-flash-preview", system_instruction: str = None) -> Optional[str]:
        """Wrapper for generate_content."""
        return self.client.generate_content(text, model=model, system_instruction=system_instruction)
