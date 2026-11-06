"""
Library:        lib_bejson_AI_bejson_interactions.py
Family:         AI
Description:    Integration wrapper for the Google Gemini Interactions API
                 (https://generativelanguage.googleapis.com/v1beta/interactions).
                 REST-first per standing policy (Section 6: REST is primary,
                 google-genai SDK is fallback). Field names and payload shape
                 below are copied verbatim from the confirmed-working call
                 chain documented in GEMINI_INTERACTIONS_INCIDENT_REPORT.md
                 (Flask_Gemini_Interactions project, 11 incidents, v1.8.0-1.11.1)
                 — do not "correct" any of these names against training-data
                 assumptions about the API; they were each wrong once and
                 fixed against the API's own error messages.
Version:        1.1.0
Date:           2026-07-22
Author:         Elton Boehnen
Contact:        eltonboehnen@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  1826a27b-8d4e-4653-a788-a2001e428fee
Release_Version: 300

Changelog:
  1.1.0 - BUGFIX (2026-09-04): chat() function-call loop was reading
          interaction.get("outputs", []) — "outputs" is not a field in the
          Interactions API response. The correct field name per the API
          reference (§3 Step Types) and the confirmed-working Flask_Gemini_
          Interactions implementation is "steps". Fixed to
          interaction.get("steps", []). Also fixed the docstring reference
          on the Return line (said ["outputs"]) and the warning log message.
          This bug meant the function-call loop never detected any tool calls
          from real API responses, returning immediately after the first turn.
  1.0.0 - Initial release. New file, not a rewrite of
          lib_bejson_AI_bejson_gemini.py (that module wraps
          client.models.generate_content / REST generateContent and is
          left untouched in behavior). This module is for agentic /
          multi-turn / function-calling / attachment use cases, where
          the Interactions API is the recommended endpoint going
          forward per the gemini-interactions-api skill. Reuses
          GeminiKeyRegistry and GeminiModelRegistry from
          lib_bejson_AI_bejson_gemini.py rather than duplicating
          registry logic (Surgical Changes / Simplicity First).

Confirmed-correct payload shapes (source: incident report Part 1 & 2):
  - Auth:            header "x-goog-api-key", NOT a "?key=" query param
  - Tool declare:     flat {"type":"function","name":...,"description":...,"parameters":...}
  - function_call:    model returns "arguments" (NOT "args")
  - function_result:  {"type":"function_result","name":...,"call_id":fc["id"],
                        "result":[{"type":"text","text":"..."}]}
                       "result" MUST be an array of content objects, never a
                       bare dict like {"response":{"result":...}}
  - NEVER send a "generation_config" field in the payload — the API
    silently drops/breaks the call if present (Incident 7). There is
    currently no known-working equivalent; if per-call temperature /
    max-output-tokens control is required, that is unverified territory —
    stop and confirm against a live call before shipping, don't guess.
  - Attachments:
      text/code files  -> {"type":"text","text": "<file contents>"}   (no base64)
      images           -> {"type":"image","data": "<base64>","mime_type":"..."}
      pdf/binary       -> {"type":"document","data": "<base64>","mime_type":"..."}
    "inline_data" is NOT a valid input type on this API (Incident 5) —
    that shape belongs to a different Google API and silently drops the file.
"""

import os
import sys
import json
import time
import base64
import logging
import mimetypes
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import requests

# --- Sibling Resolution ---
LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

CORE_DIR = os.path.join(os.path.dirname(LIB_DIR), "Core")
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

try:
    from lib_bejson_Core_bejson_env import resolve_path as resolve_system_path
except ImportError as e:
    print(f"Interactions Lib Error: Missing core dependency (bejson_env). {e}")
    sys.exit(1)

# Reuse the existing key/model registries instead of duplicating them here.
try:
    from lib_bejson_AI_bejson_gemini import GeminiKeyRegistry, GeminiModelRegistry
    from lib_bejson_AI_ai_registry_base import get_self_contained_dir
except ImportError as e:
    print(f"Interactions Lib Error: Missing sibling dependency (bejson_gemini). {e}")
    sys.exit(1)

from lib_bejson_AI_bejson_errors import (
    E_AI_NO_API_KEYS,
    E_AI_INTERACTIONS_HTTP_ERROR,
    E_AI_INTERACTIONS_TIMEOUT,
)

# --- Optional SDK fallback (google-genai's interactions surface) ---
try:
    from google import genai as _genai_sdk
except ImportError:
    _genai_sdk = None

VERSION = "1.1.0"
INTERACTIONS_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
DEFAULT_MAX_ROUNDS = 5        # matches the confirmed-working client's function-call loop cap
DEFAULT_TIMEOUT_SECONDS = 60  # matches Incident 11's hard network timeout fix


# ---------------------------------------------------------------------------
# Attachment builders — see module docstring for why these three shapes only
# ---------------------------------------------------------------------------

_TEXT_LIKE_EXTENSIONS = {
    ".html", ".htm", ".js", ".ts", ".py", ".css", ".json", ".md", ".txt",
    ".bejson", ".sh", ".yml", ".yaml", ".csv", ".xml", ".c", ".cpp", ".java",
}


def build_text_attachment(file_path: Union[str, Path]) -> Dict[str, Any]:
    """Text/code file -> {"type":"text","text":...}. No base64 encoding."""
    p = Path(file_path)
    return {"type": "text", "text": p.read_text(encoding="utf-8", errors="replace")}


def build_image_attachment(file_path: Union[str, Path], mime_type: Optional[str] = None) -> Dict[str, Any]:
    """Image file -> {"type":"image","data":base64,"mime_type":...}."""
    p = Path(file_path)
    mt = mime_type or mimetypes.guess_type(str(p))[0] or "image/jpeg"
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return {"type": "image", "data": data, "mime_type": mt}


def build_document_attachment(file_path: Union[str, Path], mime_type: Optional[str] = None) -> Dict[str, Any]:
    """PDF/binary file -> {"type":"document","data":base64,"mime_type":...}."""
    p = Path(file_path)
    mt = mime_type or mimetypes.guess_type(str(p))[0] or "application/pdf"
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return {"type": "document", "data": data, "mime_type": mt}


def build_attachment(file_path: Union[str, Path]) -> Dict[str, Any]:
    """Dispatch to the correct builder by extension. Unknown extensions fall
    back to document (binary) rather than guessing text, since a wrongly
    decoded binary is a worse failure than an over-cautious base64 attach."""
    p = Path(file_path)
    ext = p.suffix.lower()
    if ext in _TEXT_LIKE_EXTENSIONS:
        return build_text_attachment(p)
    mt = mimetypes.guess_type(str(p))[0] or ""
    if mt.startswith("image/"):
        return build_image_attachment(p, mt)
    return build_document_attachment(p, mt)


# ---------------------------------------------------------------------------
# Main API interface
# ---------------------------------------------------------------------------

class GeminiInteractionsAPI:
    """
    Wraps the Interactions API's confirmed-working call chain:
      - create_interaction()  raw POST wrapper (mirrors client interactionsPost())
      - chat()                 function-call loop (mirrors client callGemini())
      - tool_direct()          direct system-instruction injection, no loop
                                (mirrors client callToolDirect())

    Deliberately has NO generation_config passthrough. See module docstring.
    """

    def __init__(self, key_registry: GeminiKeyRegistry, model_registry: GeminiModelRegistry):
        self.keys = key_registry
        self.models = model_registry

    def _next_key(self) -> str:
        if not self.keys.keys:
            raise RuntimeError(f"[E_AI_NO_API_KEYS={E_AI_NO_API_KEYS}] No Gemini API keys found.")
        return self.keys.keys[int(time.time() * 1000) % len(self.keys.keys)]

    # -- raw POST wrapper --------------------------------------------------

    def create_interaction(
        self,
        payload: Dict[str, Any],
        api_key: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> Dict[str, Any]:
        """
        POST payload as-is to /v1beta/interactions. Caller is responsible
        for the payload shape; this function does not inject or strip
        fields. Never adds generation_config.
        """
        key = api_key or self._next_key()
        headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
        try:
            res = requests.post(INTERACTIONS_ENDPOINT, headers=headers, json=payload, timeout=timeout)
            res.raise_for_status()
            return res.json()
        except requests.exceptions.Timeout:
            raise TimeoutError(f"[E_AI_INTERACTIONS_TIMEOUT={E_AI_INTERACTIONS_TIMEOUT}] "
                                f"Interactions API call exceeded {timeout}s timeout.")
        except requests.exceptions.HTTPError as e:
            # The API's own error text names the exact wrong field/type — surface it verbatim.
            body = e.response.text if e.response is not None else str(e)
            raise RuntimeError(f"[E_AI_INTERACTIONS_HTTP_ERROR={E_AI_INTERACTIONS_HTTP_ERROR}] "
                                f"Interactions API error: {body}")

    # -- function-call loop --------------------------------------------------

    def chat(
        self,
        input_text: Union[str, List[Dict[str, Any]]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_executor: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
        model_id: Optional[str] = None,
        system_instruction: Optional[str] = None,
        previous_interaction_id: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
        store: bool = True,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Runs the confirmed function-call loop:
          1. POST input (+ tools, + previous_interaction_id if chaining)
          2. If any output step is type "function_call": execute it via
             tool_executor(name, arguments), send back a "function_result"
             step with call_id = the function_call's "id" and result as an
             array of content objects, then repeat.
          3. Stop when no function_call steps remain, or max_rounds is hit.

        Returns the final interaction dict (has .get("id"), ["steps"], etc).
        """
        mid = model_id or self.models.active_model_id
        key = api_key or self._next_key()

        content_input: List[Dict[str, Any]] = []
        if isinstance(input_text, str):
            content_input.append({"type": "text", "text": input_text})
        else:
            content_input.extend(input_text)
        if attachments:
            content_input.extend(attachments)

        payload: Dict[str, Any] = {"model": mid, "input": content_input, "store": store}
        if system_instruction:
            payload["system_instruction"] = system_instruction
        if tools:
            payload["tools"] = tools
        if previous_interaction_id:
            payload["previous_interaction_id"] = previous_interaction_id

        interaction = self.create_interaction(payload, api_key=key)
        rounds = 0

        while rounds < max_rounds:
            steps = interaction.get("steps", [])        # "steps" per API ref §3
            function_calls = [s for s in steps if s.get("type") == "function_call"]
            if not function_calls:
                return interaction
            if tool_executor is None:
                logging.warning("[InteractionsLib] function_call steps returned but no tool_executor provided.")
                return interaction

            results_input: List[Dict[str, Any]] = []
            for fc in function_calls:
                fc_name = fc.get("name")
                fc_args = fc.get("arguments", {})  # NOT "args" — see module docstring
                fc_id = fc.get("id")
                try:
                    tool_output = tool_executor(fc_name, fc_args)
                except Exception as e:
                    tool_output = f"ERROR executing tool '{fc_name}': {e}"
                results_input.append({
                    "type": "function_result",
                    "name": fc_name,
                    "call_id": fc_id,
                    "result": [{"type": "text", "text": str(tool_output)}],
                })

            payload = {
                "model": mid,
                "input": results_input,
                "previous_interaction_id": interaction.get("id"),
                "store": store,
            }
            if tools:
                payload["tools"] = tools
            interaction = self.create_interaction(payload, api_key=key)
            rounds += 1

        return interaction

    # -- direct tool injection, no loop --------------------------------------

    def tool_direct(
        self,
        tool_system_instruction: str,
        prompt: str,
        model_id: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        store: bool = True,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Direct single-shot call with a tool's system instruction injected,
        no function-call loop. Appropriate for generation-style tools
        (mirrors client callToolDirect()).
        """
        mid = model_id or self.models.active_model_id
        content_input: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
        if attachments:
            content_input.extend(attachments)
        payload = {
            "model": mid,
            "input": content_input,
            "system_instruction": tool_system_instruction,
            "store": store,
        }
        return self.create_interaction(payload, api_key=api_key or self._next_key())


# --- Global Standard Paths (mirrors lib_bejson_AI_bejson_gemini.py) ---
# Self-contained (see ai_registry_base.py get_self_contained_dir()) -- this
# resolves to the same lib/AI/config/ folder as gemini.py's own STD_*_PATH
# constants (both files live in lib/AI/), so both entry points share one
# on-disk key/model registry instead of two independent copies.
_CONFIG_DIR = get_self_contained_dir(__file__)
STD_KEY_PATH = _CONFIG_DIR / "gemini_keys.104a.bejson"
STD_MODEL_PATH = _CONFIG_DIR / "gemini_model_registry.104a.bejson"


def get_standard_interactions_api() -> GeminiInteractionsAPI:
    return GeminiInteractionsAPI(
        GeminiKeyRegistry(STD_KEY_PATH),
        GeminiModelRegistry(STD_MODEL_PATH),
    )
