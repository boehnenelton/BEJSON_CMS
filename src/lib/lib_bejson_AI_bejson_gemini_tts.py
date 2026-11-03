"""
Library:         lib_bejson_AI_bejson_gemini_tts.py
Family:          New
Module Purpose:  Integration wrapper for Google Gemini text-to-speech (TTS) generation via the Interactions API (https://generativelanguage.googleapis.com/v1beta/interactions), per the "Text-to-speech" doc supplied directly for this build (not the older incident-report chat/function-calling flow). Supports single-speaker and multi-speaker (max 2) synthesis, streaming (model-permitting), and saving decoded PCM output to a .wav file. Reuses GeminiKeyRegistry from lib_bejson_AI_bejson_gemini.py (same API keys serve both text and TTS generation) and INTERACTIONS_ENDPOINT from lib_bejson_AI_bejson_interactions.py rather than duplicating either (Surgical Changes / Simplicity First). Ships its own self-contained TTS model registry -- deliberately NOT added to Core's lib_bejson_Core_bejson_schema.py, since Core is a frozen core-family library and this schema is AI-family- specific, additive, and only needed here. KNOWN ASSUMPTIONS -- flagged rather than silently guessed, same spirit as bejson_interactions.py's own "unverified territory" notes: 1. bejson_interactions.py's module docstring warns that sending "generation_config" on the general Interactions API silently breaks the call (Incident 7, chat/ function-calling flow). The TTS doc supplied for this build explicitly requires generation_config.speech_config for TTS requests. Treated here as a genuine per- capability exception (TTS is a different request shape than chat), not a contradiction to silently paper over -- confirm against a live call before relying on this in production. 2. The doc's Python examples use the google-genai SDK's `client.interactions.create(...)` convenience wrapper and read `interaction.output_audio.data`. This module is REST-first (matches bejson_interactions.py's standing policy), so audio extraction defensively checks a top-level "output_audio" key first, then falls back to scanning "outputs" for a {"type": "audio", ...} entry (the shape used for other typed outputs like function_call elsewhere in this API). The exact REST field name was not independently confirmed against a live response -- verify before shipping to production and correct this comment + _extract_audio_b64() together if it differs. 3. Streaming (synthesize_stream()) parses standard "data: {...}" SSE lines and looks for event_type == "step.delta" with delta.type == "audio", matching the doc's SDK-level event shape. The raw REST SSE framing was not independently confirmed -- same caveat as #2.
Architecture:    BEJSON 104a provides fast primitive metadata and manifest configuration with O(1) field map caching.
Version:         1.0.0
Release_Version: 300
Date:            2026-09-05
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   9b68545c-598c-404a-9eb3-25b0da3c5da1
"""

import os
import sys
import json
import time
import wave
import base64
import logging
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict, Union

import requests

# --- Sibling Resolution ---
LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

CORE_DIR = os.path.join(os.path.dirname(LIB_DIR), "Core")
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

VERSION = "1.0.0"

try:
    from lib_bejson_AI_bejson_gemini import GeminiKeyRegistry, STD_KEY_PATH as GEMINI_STD_KEY_PATH
    from lib_bejson_AI_bejson_interactions import INTERACTIONS_ENDPOINT
    from lib_bejson_AI_ai_registry_base import ModelRegistryBase, get_self_contained_dir
    from lib_bejson_AI_bejson_errors import (
        NoAPIKeysError,
        TTSHTTPError,
        TTSTimeoutError,
        TTSNoAudioReturnedError,
        TTSInvalidVoiceError,
        TTSMultiSpeakerLimitExceededError,
        TTSUnsupportedCapabilityError,
    )
    _CORE_IMPORT_ERROR = None
except ImportError as e:
    # Graceful-degradation convention used across the AI family (see
    # bejson_gemini.py 2.3.2 changelog) -- store and re-raise a normal
    # ImportError instead of killing the host process.
    _CORE_IMPORT_ERROR = e
    logging.error(f"[GeminiTTSLib] Missing sibling/core dependencies: {e}")
    raise

TTS_CONFIG_VERSION = 1
CONFIG_DIR = get_self_contained_dir(__file__)

MAX_SPEAKERS = 2
DEFAULT_VOICE = "Kore"
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_SAMPLE_RATE = 24000
DEFAULT_CHANNELS = 1
DEFAULT_SAMPLE_WIDTH = 2  # bytes (16-bit PCM), per doc's wave_file() example

# ---------------------------------------------------------------------------
# Voice catalog -- the 30 prebuilt output voices documented for Gemini TTS.
# Kept as data (name -> short style descriptor) so callers/UIs can list or
# validate voices without a network call.
# ---------------------------------------------------------------------------
VOICE_CATALOG: Dict[str, str] = {
    "Zephyr": "Bright", "Puck": "Upbeat", "Charon": "Informative",
    "Kore": "Firm", "Fenrir": "Excitable", "Leda": "Youthful",
    "Orus": "Firm", "Aoede": "Breezy", "Callirrhoe": "Easy-going",
    "Autonoe": "Bright", "Enceladus": "Breathy", "Iapetus": "Clear",
    "Umbriel": "Easy-going", "Algieba": "Smooth", "Despina": "Smooth",
    "Erinome": "Clear", "Algenib": "Gravelly", "Rasalgethi": "Informative",
    "Laomedeia": "Upbeat", "Achernar": "Soft", "Alnilam": "Firm",
    "Schedar": "Even", "Gacrux": "Mature", "Pulcherrima": "Forward",
    "Achird": "Friendly", "Zubenelgenubi": "Casual", "Vindemiatrix": "Gentle",
    "Sadachbia": "Lively", "Sadaltager": "Knowledgeable", "Sulafat": "Warm",
}

# ---------------------------------------------------------------------------
# Self-contained TTS model registry -- own schema, own file, own family
# (not shared with lib_bejson_AI_bejson_gemini.py's text-generation model
# registry, since currently_active/capability flags mean different things
# for the two use cases). Uses the Field Map Cache via ModelRegistryBase /
# _extra_fields() -- no positional indexing, per standing BEJSON policy.
# ---------------------------------------------------------------------------
SCHEMA_MODEL_REGISTRY_GEMINI_TTS = {
    "Format": "BEJSON",
    "Format_Version": "104a",
    "Format_Creator": "Elton Boehnen",
    "Records_Type": ["AI_TTS_Model"],
    "Fields": [
        {"name": "display_name",              "type": "string"},   # 0
        {"name": "model_id",                  "type": "string"},   # 1
        {"name": "currently_active",          "type": "boolean"},  # 2
        {"name": "multi_speaker_supported",   "type": "boolean"},  # 3
        {"name": "streaming_supported",       "type": "boolean"},  # 4
    ],
    "Values": [
        ["Gemini 3.1 Flash TTS (Preview)", "gemini-3.1-flash-tts-preview", True, True, True],
        ["Gemini 2.5 Flash TTS (Preview)", "gemini-2.5-flash-preview-tts", False, True, False],
        ["Gemini 2.5 Pro TTS (Preview)",   "gemini-2.5-pro-preview-tts",   False, True, False],
    ],
}


class GeminiTTSModelRegistry(ModelRegistryBase):
    def __init__(self, file_path: Union[str, Path]):
        super().__init__(
            file_path,
            default_model_id="gemini-3.1-flash-tts-preview",
            default_rows_factory=lambda: SCHEMA_MODEL_REGISTRY_GEMINI_TTS,
            config_version=TTS_CONFIG_VERSION,
        )

    def _extra_fields(self, row: List[Any], fmap: Dict[str, int]) -> Dict[str, Any]:
        ms_idx = fmap.get("multi_speaker_supported")
        st_idx = fmap.get("streaming_supported")
        return {
            "multi_speaker_supported": bool(row[ms_idx]) if ms_idx is not None else True,
            "streaming_supported": bool(row[st_idx]) if st_idx is not None else False,
        }


# ---------------------------------------------------------------------------
# Response shape -- kept local rather than reusing lib_bejson_AI_ai_response's
# AIResponse, since TTS output is binary audio, not text/thought (Atomic
# Unit / Single Responsibility -- don't overload one TypedDict for two
# meaningfully different shapes).
# ---------------------------------------------------------------------------
class TTSResponse(TypedDict):
    success: bool
    audio_data: bytes           # raw PCM bytes, b"" on failure
    audio_path: Optional[str]   # set only if synthesize_to_file() was used
    sample_rate: int
    channels: int
    sample_width: int
    error: Optional[str]
    provider: str
    model_id: Optional[str]
    raw: Any


def tts_response_ok(
    audio_data: bytes,
    *,
    model_id: str,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = DEFAULT_CHANNELS,
    sample_width: int = DEFAULT_SAMPLE_WIDTH,
    audio_path: Optional[str] = None,
    raw: Any = None,
) -> TTSResponse:
    return TTSResponse(
        success=True, audio_data=audio_data, audio_path=audio_path,
        sample_rate=sample_rate, channels=channels, sample_width=sample_width,
        error=None, provider="gemini", model_id=model_id, raw=raw,
    )


def tts_response_error(error: str, *, model_id: Optional[str] = None, raw: Any = None) -> TTSResponse:
    return TTSResponse(
        success=False, audio_data=b"", audio_path=None,
        sample_rate=DEFAULT_SAMPLE_RATE, channels=DEFAULT_CHANNELS, sample_width=DEFAULT_SAMPLE_WIDTH,
        error=error, provider="gemini", model_id=model_id, raw=raw,
    )


# ---------------------------------------------------------------------------
# speech_config builder
# ---------------------------------------------------------------------------

def build_speech_config(
    voice: Optional[str] = None,
    speaker_voices: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    """
    Single-speaker: pass voice="Kore" -> [{"voice": "Kore"}]
    Multi-speaker:  pass speaker_voices=[{"speaker": "Joe", "voice": "Kore"},
                                          {"speaker": "Jane", "voice": "Puck"}]
    (max 2 speakers, per Gemini TTS limitation).
    """
    if speaker_voices:
        if len(speaker_voices) > MAX_SPEAKERS:
            raise TTSMultiSpeakerLimitExceededError(
                f"Gemini TTS supports at most {MAX_SPEAKERS} speakers, got {len(speaker_voices)}.")
        for sv in speaker_voices:
            if sv.get("voice") not in VOICE_CATALOG:
                raise TTSInvalidVoiceError(f"Unknown voice '{sv.get('voice')}'. See VOICE_CATALOG.")
            if not sv.get("speaker"):
                raise TTSInvalidVoiceError("Each multi-speaker entry needs a non-empty 'speaker' name.")
        return [{"speaker": sv["speaker"], "voice": sv["voice"]} for sv in speaker_voices]

    v = voice or DEFAULT_VOICE
    if v not in VOICE_CATALOG:
        raise TTSInvalidVoiceError(f"Unknown voice '{v}'. See VOICE_CATALOG.")
    return [{"voice": v}]


def _extract_audio_b64(interaction: Dict[str, Any]) -> Optional[str]:
    """See module docstring assumption #2. Checks the SDK-convenience-style
    top-level key first, then falls back to scanning typed outputs."""
    top = interaction.get("output_audio")
    if isinstance(top, dict) and top.get("data"):
        return top["data"]
    for out in interaction.get("outputs", []):
        if out.get("type") == "audio" and out.get("data"):
            return out["data"]
    return None


# ---------------------------------------------------------------------------
# Main API interface
# ---------------------------------------------------------------------------

class GeminiTTSAPI:
    """
    synthesize()         -- single call, returns decoded PCM bytes in memory.
    synthesize_to_file()  -- synthesize() + save_wave() convenience wrapper.
    synthesize_stream()   -- generator yielding PCM chunks as they arrive
                              (model must have streaming_supported=True).
    save_wave()           -- write raw PCM bytes to a .wav file (static).
    """

    def __init__(self, key_registry: GeminiKeyRegistry, model_registry: GeminiTTSModelRegistry):
        self.keys = key_registry
        self.models = model_registry

    def _next_key(self) -> str:
        if not self.keys.keys:
            raise NoAPIKeysError("No Gemini API keys found.")
        return self.keys.keys[int(time.time() * 1000) % len(self.keys.keys)]

    def _resolve_model(self, model_id: Optional[str]) -> Dict[str, Any]:
        mid = model_id or self.models.active_model_id
        return self.models.get_model_info(mid)

    def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        speaker_voices: Optional[List[Dict[str, str]]] = None,
        model_id: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        api_key: Optional[str] = None,
    ) -> TTSResponse:
        """
        text            -- the transcript to speak (may include audio tags
                            like "[whispers]" and, for multi-speaker, a
                            "Speaker: line" transcript format -- see the
                            Gemini TTS prompting guide).
        voice           -- single-speaker voice name (VOICE_CATALOG key).
                            Ignored if speaker_voices is given.
        speaker_voices  -- [{"speaker": "Joe", "voice": "Kore"}, ...] for
                            multi-speaker (max 2).
        """
        info = self._resolve_model(model_id)
        mid = info["id"]
        if speaker_voices and not info.get("multi_speaker_supported", True):
            raise TTSUnsupportedCapabilityError(f"Model '{mid}' does not support multi-speaker TTS.")

        speech_config = build_speech_config(voice=voice, speaker_voices=speaker_voices)
        payload = {
            "model": mid,
            "input": text,
            "response_format": {"type": "audio"},
            # See module docstring assumption #1 re: generation_config.
            "generation_config": {"speech_config": speech_config},
        }

        key = api_key or self._next_key()
        headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
        try:
            res = requests.post(INTERACTIONS_ENDPOINT, headers=headers, json=payload, timeout=timeout)
            res.raise_for_status()
            interaction = res.json()
        except requests.exceptions.Timeout:
            raise TTSTimeoutError(f"Gemini TTS call exceeded {timeout}s timeout.")
        except requests.exceptions.HTTPError as e:
            body = e.response.text if e.response is not None else str(e)
            raise TTSHTTPError(f"Gemini TTS HTTP error: {body}")

        b64_audio = _extract_audio_b64(interaction)
        if not b64_audio:
            # Matches the doc's documented "occasional text token returns"
            # limitation -- treated as recoverable (retry), not fatal.
            raise TTSNoAudioReturnedError(
                "Gemini TTS call succeeded but returned no audio output "
                "(model may have returned text tokens instead -- retry).")

        pcm = base64.b64decode(b64_audio)
        return tts_response_ok(pcm, model_id=mid, raw=interaction)

    def synthesize_to_file(
        self,
        text: str,
        filename: Union[str, Path],
        voice: Optional[str] = None,
        speaker_voices: Optional[List[Dict[str, str]]] = None,
        model_id: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        api_key: Optional[str] = None,
    ) -> TTSResponse:
        result = self.synthesize(
            text, voice=voice, speaker_voices=speaker_voices,
            model_id=model_id, timeout=timeout, api_key=api_key,
        )
        path = self.save_wave(
            result["audio_data"], filename,
            channels=result["channels"], rate=result["sample_rate"],
            sample_width=result["sample_width"],
        )
        result = dict(result)
        result["audio_path"] = str(path)
        return TTSResponse(**result)

    def synthesize_stream(
        self,
        text: str,
        voice: Optional[str] = None,
        speaker_voices: Optional[List[Dict[str, str]]] = None,
        model_id: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        api_key: Optional[str] = None,
    ):
        """
        Generator yielding raw PCM byte chunks as they stream in. Only
        valid for models with streaming_supported=True (currently
        "gemini-3.1-flash-tts-preview"). See module docstring assumption #3
        re: SSE framing not being independently verified.
        """
        info = self._resolve_model(model_id)
        mid = info["id"]
        if not info.get("streaming_supported", False):
            raise TTSUnsupportedCapabilityError(f"Model '{mid}' does not support streaming TTS.")

        speech_config = build_speech_config(voice=voice, speaker_voices=speaker_voices)
        payload = {
            "model": mid,
            "input": text,
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": speech_config},
            "stream": True,
        }
        key = api_key or self._next_key()
        headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
        try:
            with requests.post(INTERACTIONS_ENDPOINT, headers=headers, json=payload,
                                timeout=timeout, stream=True) as res:
                res.raise_for_status()
                for line in res.iter_lines(decode_unicode=True):
                    if not line or not line.startswith("data:"):
                        continue
                    raw_event = line[len("data:"):].strip()
                    if raw_event in ("", "[DONE]"):
                        continue
                    try:
                        event = json.loads(raw_event)
                    except json.JSONDecodeError:
                        continue
                    if event.get("event_type") != "step.delta":
                        continue
                    delta = event.get("delta", {})
                    if delta.get("type") == "audio" and delta.get("data"):
                        yield base64.b64decode(delta["data"])
        except requests.exceptions.Timeout:
            raise TTSTimeoutError(f"Gemini TTS stream exceeded {timeout}s timeout.")
        except requests.exceptions.HTTPError as e:
            body = e.response.text if e.response is not None else str(e)
            raise TTSHTTPError(f"Gemini TTS stream HTTP error: {body}")

    @staticmethod
    def save_wave(
        pcm: bytes,
        filename: Union[str, Path],
        channels: int = DEFAULT_CHANNELS,
        rate: int = DEFAULT_SAMPLE_RATE,
        sample_width: int = DEFAULT_SAMPLE_WIDTH,
    ) -> Path:
        """Writes raw PCM bytes to a standard .wav file (matches the doc's
        wave_file() helper)."""
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(rate)
            wf.writeframes(pcm)
        return path


# --- Global Standard Paths (mirrors bejson_gemini.py / bejson_interactions.py) ---
# Reuses the same Gemini API key file as text generation (STD_KEY_PATH from
# bejson_gemini.py) -- one Google API key serves both capabilities. Only the
# TTS model registry gets its own file, since it's a different model list
# with different capability flags.
STD_KEY_PATH = GEMINI_STD_KEY_PATH
STD_TTS_MODEL_PATH = CONFIG_DIR / "gemini_tts_model_registry.104a.bejson"

_std_tts_api_singleton: Optional["GeminiTTSAPI"] = None


def get_standard_tts_api() -> "GeminiTTSAPI":
    """Zero-config GeminiTTSAPI, built from the standard key/model registry
    paths. Cached after first call (matches get_standard_api() pattern in
    bejson_gemini.py)."""
    global _std_tts_api_singleton
    if _std_tts_api_singleton is None:
        key_reg = GeminiKeyRegistry(STD_KEY_PATH)
        model_reg = GeminiTTSModelRegistry(STD_TTS_MODEL_PATH)
        _std_tts_api_singleton = GeminiTTSAPI(key_reg, model_reg)
    return _std_tts_api_singleton