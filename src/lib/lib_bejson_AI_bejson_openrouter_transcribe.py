"""
Library:         lib_bejson_AI_bejson_openrouter_transcribe.py
Family:          AI
Module Purpose:  OpenRouter transcription through an audio-capable chat model (input_audio content part),
                 using the same prompt builder as the Gemini transcribers so diarization/Markdown rules carry over.
Architecture:    Same shape as GeminiRestTranscribeAPI: __init__(key_registry, model_registry) exposing .keys
                 and .models, transcribe(...) -> str, typed errors from lib_bejson_AI_bejson_errors, cached
                 zero-config get_openrouter_transcribe_api(). A pre-encoded audio_b64 (e.g. the stored Base64
                 of a BEJSON 104a segment) is sent as-is, skipping a re-encode. Config lives in config/.
Version:         1.0.0
Release_Version: 300
Date:            2026-10-18
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   5446320f-3110-4f41-85ea-b32b34333156
"""

import base64
import json
import logging
from pathlib import Path
from typing import Any, Optional, Union

from lib_bejson_AI_ai_registry_base import ModelRegistryBase, get_self_contained_dir
from lib_bejson_AI_ai_transcribe_registry import TranscribeKeyRegistry
from lib_bejson_AI_ai_transcribe_http import rotating_post
from lib_bejson_AI_bejson_gemini_transcribe import MAX_INLINE_BYTES, _build_system_prompt, clean_domain_terminology
from lib_bejson_AI_bejson_errors import (
    GenerationError, TranscribeMediaNotFoundError, TranscribeMediaTooLargeError, TranscribeUnsupportedMediaError,
)

logger = logging.getLogger("lib_bejson_AI_bejson_openrouter_transcribe")

VERSION = "1.0.0"
CONFIG_VERSION = 1
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_TRANSCRIBE_MODEL = "google/gemini-2.5-flash"
SUPPORTED_AUDIO_FORMATS = ("wav", "mp3")

CONFIG_DIR = get_self_contained_dir(__file__)
STD_KEY_PATH = CONFIG_DIR / "openrouter_transcribe_keys.104a.bejson"
STD_MODEL_PATH = CONFIG_DIR / "openrouter_transcribe_model_registry.104a.bejson"


def _default_model_rows() -> dict:
    return {
        "Format": "BEJSON", "Format_Version": "104a", "Format_Creator": "Elton Boehnen",
        "Records_Type": ["OpenRouterTranscribeModel"],
        "Fields": [
            {"name": "model_name", "type": "string"},
            {"name": "model_id", "type": "string"},
            {"name": "currently_active", "type": "boolean"},
        ],
        "Values": [["Gemini 2.5 Flash (audio input)", "google/gemini-2.5-flash", True]],
    }


class OpenRouterTranscribeKeyRegistry(TranscribeKeyRegistry):
    def __init__(self, file_path: Union[str, Path]):
        super().__init__(file_path, env_prefixes=("OPENROUTER_MM_KEY", "OPENROUTER_KEY"),
                         placeholder_markers=["YOUR_OPENROUTER_KEY", "KEY_HERE"], config_version=CONFIG_VERSION)


class OpenRouterTranscribeModelRegistry(ModelRegistryBase):
    def __init__(self, file_path: Union[str, Path]):
        super().__init__(file_path, default_model_id=DEFAULT_TRANSCRIBE_MODEL,
                         default_rows_factory=_default_model_rows, config_version=CONFIG_VERSION)


class OpenRouterTranscribeAPI:
    """OpenRouter audio-input transcription over plain REST (stdlib urllib, no SDK)."""

    def __init__(self, key_registry: Any, model_registry: Any):
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
        audio_b64: Optional[str] = None,
        throttle: Optional[Any] = None,
    ) -> str:
        path = Path(file_path)
        if not path.is_file():
            raise TranscribeMediaNotFoundError(f"Media file not found: {path}")
        fmt = path.suffix.lower().lstrip(".")
        if fmt not in SUPPORTED_AUDIO_FORMATS:
            raise TranscribeUnsupportedMediaError(f"OpenRouter audio input supports {SUPPORTED_AUDIO_FORMATS}, got '.{fmt}'.")
        size = path.stat().st_size
        if size > MAX_INLINE_BYTES:
            raise TranscribeMediaTooLargeError(
                f"{path.name} is {size / 1024 / 1024:.1f}MB, over the {MAX_INLINE_BYTES // (1024 * 1024)}MB inline limit.")

        mid = model_id or self.models.active_model_id
        prompt = _build_system_prompt(mode, segment, domain_context, extra_instructions)
        payload_b64 = audio_b64 or base64.b64encode(path.read_bytes()).decode("ascii")
        body = json.dumps({"model": mid, "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "input_audio", "input_audio": {"data": payload_b64, "format": fmt}},
        ]}]}).encode("utf-8")

        def build(key: str):
            return (OPENROUTER_CHAT_URL,
                    {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "X-Title": "Autobase64"},
                    body)

        logger.info("[OpenRouterTranscribe] %s: model=%s keys=%d", path.name, mid, len(self.keys.keys))
        raw = rotating_post(self.keys, build, label="OpenRouter", throttle=throttle)
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and data.get("error"):
                raise GenerationError(f"OpenRouter error: {str(data['error'])[:200]}")
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise GenerationError(f"OpenRouter returned an unexpected response: {type(e).__name__}: {e}")
        text = str(content or "").strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[-1].strip() == "```":
                text = "\n".join(lines[1:-1]).strip()
        if not text:
            raise GenerationError("OpenRouter returned an empty transcript.")
        return clean_domain_terminology(text) if clean_domain_terms else text


_openrouter_singleton: Optional[OpenRouterTranscribeAPI] = None


def get_openrouter_transcribe_api() -> OpenRouterTranscribeAPI:
    """Zero-config OpenRouter transcriber, cached so key rotation persists across calls."""
    global _openrouter_singleton
    if _openrouter_singleton is None:
        _openrouter_singleton = OpenRouterTranscribeAPI(OpenRouterTranscribeKeyRegistry(STD_KEY_PATH),
                                                        OpenRouterTranscribeModelRegistry(STD_MODEL_PATH))
    return _openrouter_singleton
