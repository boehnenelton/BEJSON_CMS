"""
Library:         lib_bejson_AI_bejson_gemini_rest_transcribe.py
Family:          AI
Module Purpose:  Gemini transcription over the plain REST endpoint (no google-genai SDK needed).
Architecture:    Subclasses GeminiTranscribeAPI (same key rotation, model registry, prompts,
                 mime detection and domain-term cleanup); only the network call differs:
                 POST {base}/v1beta/models/<model>:generateContent with inlineData, stdlib urllib.
Version:         1.1.0
Release_Version: 300
Date:            2026-10-16
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   6c0f7a52-3d1e-4b9a-8e47-5a2d91c3b7f0
"""

import base64
import json
import logging
import random
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional, Union

from lib_bejson_AI_bejson_gemini_transcribe import (
    GeminiTranscribeAPI,
    MAX_INLINE_BYTES,
    _build_system_prompt,
    clean_domain_terminology,
    detect_media_mime_type,
)
from lib_bejson_AI_bejson_gemini import (
    GeminiKeyRegistry, GeminiModelRegistry, STD_KEY_PATH, STD_MODEL_PATH, _classify_generation_error,
)
from lib_bejson_AI_bejson_errors import (
    NoAPIKeysError,
    TranscribeMediaNotFoundError,
    TranscribeMediaTooLargeError,
    GenerationError,
)

logger = logging.getLogger("lib_bejson_AI_bejson_gemini_rest_transcribe")

VERSION = "1.1.0"
REST_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
REST_TIMEOUT_SECONDS = 300
RETRYABLE_HTTP = (429, 500, 502, 503, 504)
RETRY_BACKOFF_SECONDS = (5, 15, 30)      # waits before attempts 2, 3, 4 (each retry also rotates to the next key)


class GeminiRestTranscribeAPI(GeminiTranscribeAPI):
    """GeminiTranscribeAPI whose transcribe() calls the REST endpoint directly."""

    def __init__(self, key_registry, model_registry):
        # Skip the parent's SDK-missing error log: the SDK is not used here.
        self.keys = key_registry
        self.models = model_registry

    def transcribe(
        self,
        file_path: Union[str, Path],
        *,
        model_id: Optional[str] = None,
        mode: str = "verbatim",
        segment: bool = False,
        domain_context: bool = True,
        clean_domain_terms: bool = True,
        mime_type: Optional[str] = None,
        extra_instructions: Optional[str] = None,
    ) -> str:
        path = Path(file_path)
        if not path.is_file():
            raise TranscribeMediaNotFoundError(f"Media file not found: {path}")
        resolved_mime = mime_type or detect_media_mime_type(path)
        size = path.stat().st_size
        if size > MAX_INLINE_BYTES:
            raise TranscribeMediaTooLargeError(
                f"{path.name} is {size / 1024 / 1024:.1f}MB, over the "
                f"{MAX_INLINE_BYTES / 1024 / 1024:.0f}MB single-request inline limit.")
        if not self.keys.keys:
            raise NoAPIKeysError("No Gemini API keys found.")

        mid = model_id or self.models.active_model_id
        prompt = _build_system_prompt(mode, segment, domain_context, extra_instructions)
        body = json.dumps({"contents": [{"parts": [
            {"inline_data": {"mime_type": resolved_mime,
                             "data": base64.b64encode(path.read_bytes()).decode("ascii")}},
            {"text": prompt},
        ]}]}).encode("utf-8")

        attempts = len(RETRY_BACKOFF_SECONDS) + 1
        payload = None
        for attempt in range(1, attempts + 1):
            key = self.keys.get_next_key() if hasattr(self.keys, "get_next_key") else None
            if key is None:
                key = random.choice(self.keys.keys)
            slot = (self.keys.keys.index(key) + 1) if key in self.keys.keys else 0
            logger.info("[GeminiRestTranscribe] %s: model=%s key slot %d/%d attempt %d/%d",
                        path.name, mid, slot, len(self.keys.keys), attempt, attempts)
            req = urllib.request.Request(
                f"{REST_BASE_URL}/{mid}:generateContent", data=body, method="POST",
                headers={"Content-Type": "application/json", "x-goog-api-key": key})
            try:
                with urllib.request.urlopen(req, timeout=REST_TIMEOUT_SECONDS) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:500]
                retryable = e.code in RETRYABLE_HTTP
                err = _classify_generation_error(Exception(f"HTTP {e.code} {e.reason}: {detail}"))
            except Exception as e:      # network / timeout: retryable
                retryable = True
                err = _classify_generation_error(e)
            logger.warning("[GeminiRestTranscribe] %s attempt %d/%d failed: %s", path.name, attempt, attempts,
                           str(err)[:200])
            if not retryable or attempt == attempts:
                raise err
            time.sleep(RETRY_BACKOFF_SECONDS[attempt - 1])

        try:
            parts = payload["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError):
            reason = (payload.get("promptFeedback") or {}).get("blockReason") or "no candidates returned"
            raise GenerationError(f"Gemini REST returned no transcript: {reason}")
        return clean_domain_terminology(text) if clean_domain_terms else text


_rest_singleton: Optional[GeminiRestTranscribeAPI] = None


def get_rest_transcribe_api() -> GeminiRestTranscribeAPI:
    """Zero-config REST transcriber sharing the standard key/model registries."""
    global _rest_singleton
    if _rest_singleton is None:
        _rest_singleton = GeminiRestTranscribeAPI(GeminiKeyRegistry(STD_KEY_PATH), GeminiModelRegistry(STD_MODEL_PATH))
    return _rest_singleton
