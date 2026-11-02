"""
Library:         lib_bejson_AI_ai_transcribe_fallback_dispatch.py
Family:          AI
Module Purpose:  The common call interface for the FALLBACK transcription providers (groq, openrouter).
                 Companion to lib_bejson_AI_ai_transcribe_dispatch.py (which owns gemini / gemini_rest and is
                 left untouched): same pattern -- one function, one signature, one AIResponse shape.
Architecture:    _adapt_<provider>_transcribe() adapters registered in PROVIDERS/_ADAPTERS. Never raises for
                 provider-side or input failures (bad path, no keys, rate limit, network, auth): those come
                 back as AIResponse(success=False, error=...). Raises ValueError only for an unknown provider.
                 Params a provider cannot honor are reported in unsupported_params. An optional `throttle`
                 (object with wait()/mark()) paces every outgoing HTTP attempt.
Version:         1.0.1
Release_Version: 300
Date:            2026-10-21
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   a5a48cf7-5fde-4734-9807-b5b625289d82
"""

import logging
from pathlib import Path
from typing import Any, Optional, Union

from lib_bejson_AI_ai_response import AIResponse, ai_response_ok, ai_response_error

logger = logging.getLogger("lib_bejson_AI_ai_transcribe_fallback_dispatch")

VERSION = "1.0.1"

PROVIDERS = ("groq", "openrouter")

# Short notes for callers that mark fallback transcripts (empty = no caveat).
PROVIDER_CAVEATS = {
    "groq": "plain text, no speaker labels or timestamps",
    "openrouter": "",
}


def _get_api(provider: str):
    if provider == "groq":
        from lib_bejson_AI_bejson_groq_transcribe import get_groq_transcribe_api
        return get_groq_transcribe_api()
    from lib_bejson_AI_bejson_openrouter_transcribe import get_openrouter_transcribe_api
    return get_openrouter_transcribe_api()


def _adapt_groq_transcribe(file_path, model_id, *, mode, extra_instructions, audio_b64, throttle, **config) -> AIResponse:
    api = _get_api("groq")
    used_model = model_id or api.models.active_model_id
    unsupported = []
    if mode == "diarization":
        unsupported.append("mode:diarization")
    if extra_instructions:
        unsupported.append("extra_instructions")
    if config:
        unsupported.append("config:" + ",".join(sorted(config.keys())))
    try:
        content = api.transcribe(file_path, model_id=model_id, mode=mode,
                                 extra_instructions=extra_instructions, throttle=throttle)
        return ai_response_ok(content, provider="groq", model_id=used_model,
                              unsupported_params=unsupported, raw=content, auto_parse=False)
    except Exception as e:
        return ai_response_error(str(e), provider="groq", model_id=used_model,
                                 unsupported_params=unsupported, raw=e)


def _adapt_openrouter_transcribe(file_path, model_id, *, mode, extra_instructions, audio_b64, throttle, **config) -> AIResponse:
    api = _get_api("openrouter")
    used_model = model_id or api.models.active_model_id
    unsupported = ["config:" + ",".join(sorted(config.keys()))] if config else []
    try:
        content = api.transcribe(file_path, model_id=model_id, mode=mode,
                                 extra_instructions=extra_instructions, audio_b64=audio_b64, throttle=throttle)
        return ai_response_ok(content, provider="openrouter", model_id=used_model,
                              unsupported_params=unsupported, raw=content, auto_parse=False)
    except Exception as e:
        return ai_response_error(str(e), provider="openrouter", model_id=used_model,
                                 unsupported_params=unsupported, raw=e)


_ADAPTERS = {
    "groq": _adapt_groq_transcribe,
    "openrouter": _adapt_openrouter_transcribe,
}


def ai_transcribe_fallback_key_count(provider: str) -> int:
    """Number of usable API keys for a fallback provider (0 = not usable)."""
    if provider not in _ADAPTERS:
        raise ValueError(f"Unknown fallback transcription provider {provider!r}; expected one of {PROVIDERS}")
    return len(_get_api(provider).keys.keys)


def ai_transcribe_fallback_dispatch(
    provider: str,
    file_path: Union[str, Path],
    *,
    model_id: Optional[str] = None,
    mode: str = "verbatim",
    extra_instructions: Optional[str] = None,
    audio_b64: Optional[str] = None,
    throttle: Optional[Any] = None,
    **config,
) -> AIResponse:
    """
    The one call interface for fallback transcription providers.

    provider            -- "groq" (Whisper, plain text) or "openrouter" (audio-capable chat model).
    file_path           -- 16-bit mono WAV to transcribe.
    model_id            -- Optional model override; falls back to the provider's active model.
    mode                -- "verbatim" or "diarization" (OpenRouter honors it; Groq reports it unsupported).
    extra_instructions  -- Extra prompt text (OpenRouter only).
    audio_b64           -- Pre-encoded Base64 of file_path, sent as-is to providers that take Base64 (OpenRouter).
    throttle            -- Optional wait()/mark() object pacing each HTTP attempt.

    Returns an AIResponse; check response["success"] and response["error"].
    """
    if provider not in _ADAPTERS:
        raise ValueError(f"Unknown fallback transcription provider {provider!r}; expected one of {PROVIDERS}")
    try:
        return _ADAPTERS[provider](file_path, model_id, mode=mode, extra_instructions=extra_instructions,
                                   audio_b64=audio_b64, throttle=throttle, **config)
    except Exception as e:
        logger.error(f"[ai_transcribe_fallback_dispatch] Adapter for {provider!r} raised unexpectedly: {e}")
        return ai_response_error(f"dispatch adapter error: {e}", provider=provider, model_id=model_id)
