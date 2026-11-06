"""
Library:         lib_bejson_AI_bejson_groq_transcribe.py
Family:          AI
Module Purpose:  Groq Whisper transcription (OpenAI-compatible /audio/transcriptions) for the AI family's
                 transcription dispatch. Plain-text result: Whisper has no diarization or custom instructions.
Architecture:    Same shape as GeminiRestTranscribeAPI: __init__(key_registry, model_registry) exposing .keys
                 and .models, transcribe(file_path, *, model_id, mode, ...) -> str, typed errors from
                 lib_bejson_AI_bejson_errors, and a cached zero-config get_groq_transcribe_api() factory.
                 Config (key fallback file, model registry) lives in this library's own config/ folder.
                 Groq accepts only a raw multipart file upload (no Base64 field), so audio_b64 is ignored.
Version:         1.0.0
Release_Version: 300
Date:            2026-10-18
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   9c69ef23-9910-4110-9e46-efdfa01a207b
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Optional, Union

from lib_bejson_AI_ai_registry_base import ModelRegistryBase, get_self_contained_dir
from lib_bejson_AI_ai_transcribe_registry import TranscribeKeyRegistry
from lib_bejson_AI_ai_transcribe_http import rotating_post
from lib_bejson_AI_bejson_gemini_transcribe import clean_domain_terminology
from lib_bejson_AI_bejson_errors import GenerationError, TranscribeMediaNotFoundError, TranscribeMediaTooLargeError

logger = logging.getLogger("lib_bejson_AI_bejson_groq_transcribe")

VERSION = "1.0.0"
CONFIG_VERSION = 1
GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MAX_FILE_BYTES = 25 * 1024 * 1024
DEFAULT_TRANSCRIBE_MODEL = "whisper-large-v3-turbo"

CONFIG_DIR = get_self_contained_dir(__file__)
STD_KEY_PATH = CONFIG_DIR / "groq_transcribe_keys.104a.bejson"
STD_MODEL_PATH = CONFIG_DIR / "groq_transcribe_model_registry.104a.bejson"


def _default_model_rows() -> dict:
    return {
        "Format": "BEJSON", "Format_Version": "104a", "Format_Creator": "Elton Boehnen",
        "Records_Type": ["GroqTranscribeModel"],
        "Fields": [
            {"name": "model_name", "type": "string"},
            {"name": "model_id", "type": "string"},
            {"name": "currently_active", "type": "boolean"},
        ],
        "Values": [
            ["Whisper Large v3 Turbo", "whisper-large-v3-turbo", True],
            ["Whisper Large v3", "whisper-large-v3", False],
        ],
    }


class GroqTranscribeKeyRegistry(TranscribeKeyRegistry):
    def __init__(self, file_path: Union[str, Path]):
        super().__init__(file_path, env_prefixes=("GROQ_MM_KEY", "GROQ_KEY"),
                         placeholder_markers=["YOUR_GROQ_KEY", "KEY_HERE"], config_version=CONFIG_VERSION)


class GroqTranscribeModelRegistry(ModelRegistryBase):
    def __init__(self, file_path: Union[str, Path]):
        super().__init__(file_path, default_model_id=DEFAULT_TRANSCRIBE_MODEL,
                         default_rows_factory=_default_model_rows, config_version=CONFIG_VERSION)


class GroqTranscribeAPI:
    """Groq Whisper over plain REST (stdlib urllib, no SDK)."""

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
        audio_b64: Optional[str] = None,       # accepted for interface parity; Groq needs the raw file
        throttle: Optional[Any] = None,
    ) -> str:
        path = Path(file_path)
        if not path.is_file():
            raise TranscribeMediaNotFoundError(f"Media file not found: {path}")
        size = path.stat().st_size
        if size > GROQ_MAX_FILE_BYTES:
            raise TranscribeMediaTooLargeError(
                f"{path.name} is {size / 1024 / 1024:.1f}MB, over Groq's {GROQ_MAX_FILE_BYTES // (1024 * 1024)}MB upload limit.")
        mid = model_id or self.models.active_model_id
        file_bytes = path.read_bytes()
        mime = mime_type or "audio/wav"

        def build(key: str):
            boundary = "----AutoGroq" + uuid.uuid4().hex
            chunks = []
            for k, v in (("model", mid), ("response_format", "json"), ("temperature", "0")):
                chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
            chunks.append((f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
                           f'Content-Type: {mime}\r\n\r\n').encode())
            chunks.append(file_bytes)
            chunks.append(f"\r\n--{boundary}--\r\n".encode())
            return (GROQ_TRANSCRIBE_URL,
                    {"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}"},
                    b"".join(chunks))

        logger.info("[GroqTranscribe] %s: model=%s keys=%d", path.name, mid, len(self.keys.keys))
        body = rotating_post(self.keys, build, label="Groq", throttle=throttle)
        try:
            text = str(json.loads(body)["text"]).strip()
        except (ValueError, KeyError, TypeError) as e:
            raise GenerationError(f"Groq returned an unexpected transcription response: {e}")
        if not text:
            raise GenerationError("Groq returned an empty transcript.")
        return clean_domain_terminology(text) if clean_domain_terms else text


_groq_singleton: Optional[GroqTranscribeAPI] = None


def get_groq_transcribe_api() -> GroqTranscribeAPI:
    """Zero-config Groq transcriber, cached so key rotation persists across calls."""
    global _groq_singleton
    if _groq_singleton is None:
        _groq_singleton = GroqTranscribeAPI(GroqTranscribeKeyRegistry(STD_KEY_PATH),
                                            GroqTranscribeModelRegistry(STD_MODEL_PATH))
    return _groq_singleton
