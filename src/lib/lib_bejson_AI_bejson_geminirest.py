"""
Library:        lib_bejson_AI_bejson_geminirest.py
Family:         AI
Description:    Gemini REST engine -- hits the generativelanguage Google API directly
                 via urllib.request instead of using the google-genai SDK.
                 Shares the exact same keys and model registries as the main
                 Gemini provider.
Version:        1.1.0
Date:           2026-09-22
Author:         Elton Boehnen
Contact:        boehnenelton2024@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  f112c37e-61e4-44b2-9a3d-6b1424b912ab
Release_Version: 300

Changelog:
  1.1.0 (2026-09-28) -- Root-caused a round-robin-key-rotation bug found
        in this project's audit: get_standard_prompter() built a brand-new
        GeminiRESTPrompter (and therefore a brand-new KeyRegistry, its
        rotation _idx reset to 0) on every single dispatch, since
        ai_dispatch.py calls it fresh per call. Round-robin existed in the
        class but never actually advanced past key #1 in practice. Cached
        after first call for the default (no-arg) case, matching the
        singleton pattern lib_bejson_AI_bejson_gemini.py's
        get_standard_api() already used correctly. A caller passing
        explicit keys_path/models_path still gets an uncached instance.
        Also added this file's previously-missing Release_Version:300
        header (audit finding: 12 AI-family files missing it).
"""

import json
import urllib.request
import urllib.error
import socket
from typing import Optional, Dict, Any
from pathlib import Path
import os
import uuid

# Re-use the existing Gemini registries
from lib_bejson_AI_bejson_gemini import GeminiKeyRegistry, GeminiModelRegistry

VERSION = "1.1.0"

_HOME = os.getenv("HOME", "/data/data/com.termux/files/home")
_ADMIN_ROOT = os.getenv("ADMIN", f"{_HOME}/storage/shared/Admin")

def _resolve_admin_path(relative_path: str) -> Path:
    """Helper to consistently build paths relative to ADMIN_ROOT or fallback to HOME."""
    admin_path = Path(_ADMIN_ROOT) / relative_path
    if admin_path.exists() or admin_path.parent.exists():
        return admin_path
    home_path = Path(_HOME) / relative_path
    home_path.parent.mkdir(parents=True, exist_ok=True)
    return home_path

# Standard paths (same as gemini)
STD_KEYS_PATH = _resolve_admin_path("data/bejson/ai_api_keys.bejson")
STD_MODELS_PATH = _resolve_admin_path("data/bejson/ai_model_registry.bejson")


class GeminiRESTPrompter:
    def __init__(self, key_reg: GeminiKeyRegistry, model_reg: GeminiModelRegistry):
        self.key_reg = key_reg
        self.model_reg = model_reg

    def prompt(self, user_input: str, model_id: Optional[str] = None, system_instruction: Optional[str] = None) -> str:
        api_key = self.key_reg.get_next_key()
        if not api_key:
            return "ERROR: No Gemini API keys configured or loaded."

        target_model = model_id or self.model_reg.active_model_id
        if not target_model:
            target_model = "gemini-3.5-flash"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={api_key}"

        payload: Dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_input}]
                }
            ]
        }

        if system_instruction:
            payload["system_instruction"] = {
                "parts": [{"text": system_instruction}]
            }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                resp_data = json.loads(response.read().decode('utf-8'))
                
                candidates = resp_data.get("candidates", [])
                if not candidates:
                    return "ERROR: Empty candidates array in response."
                    
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                if not parts:
                    return "ERROR: Empty parts array in response."
                    
                return parts[0].get("text", "")
                
        except urllib.error.HTTPError as e:
            try:
                err_data = json.loads(e.read().decode('utf-8'))
                err_msg = err_data.get('error', {}).get('message', str(e))
                return f"ERROR: API returned HTTP {e.code} - {err_msg}"
            except Exception:
                return f"ERROR: API returned HTTP {e.code}"
        except urllib.error.URLError as e:
            if isinstance(e.reason, socket.timeout):
                return "ERROR: Connection timed out."
            return f"ERROR: Network error: {e.reason}"
        except Exception as e:
            return f"ERROR: Unexpected exception: {e}"


_std_prompter_singleton = None


def get_standard_prompter(keys_path: Optional[str] = None, models_path: Optional[str] = None) -> GeminiRESTPrompter:
    """Zero-config GeminiRESTPrompter. Cached after first call for the
    default (no-arg) case -- see lib_bejson_AI_bejson_groq.py's
    get_standard_prompter() for why this caching is the actual
    round-robin-key-rotation fix, not just an optimization. A caller that
    passes explicit keys_path/models_path (tests, alternate configs) gets
    a fresh, uncached instance instead, since that's a deliberate
    departure from the standard shared registry."""
    global _std_prompter_singleton
    if keys_path is not None or models_path is not None:
        kr = GeminiKeyRegistry(keys_path or str(STD_KEYS_PATH))
        kr.load()
        mr = GeminiModelRegistry(models_path or str(STD_MODELS_PATH))
        mr.load()
        return GeminiRESTPrompter(kr, mr)

    if _std_prompter_singleton is None:
        kr = GeminiKeyRegistry(str(STD_KEYS_PATH))
        kr.load()
        mr = GeminiModelRegistry(str(STD_MODELS_PATH))
        mr.load()
        _std_prompter_singleton = GeminiRESTPrompter(kr, mr)
    return _std_prompter_singleton
