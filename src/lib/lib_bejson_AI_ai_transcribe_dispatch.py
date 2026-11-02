"""
Library:        lib_bejson_AI_ai_transcribe_dispatch.py
Family:         AI
Description:    The common call interface for transcription capability
                 across the AI family's providers -- mirrors
                 lib_bejson_AI_ai_dispatch.py's ai_dispatch_call() pattern
                 (one function, one call signature, one AIResponse return
                 shape) but for file-based transcription instead of a text
                 prompt, since a media file path doesn't fit
                 ai_dispatch_call()'s user_input:str signature.

                 Today PROVIDERS only has "gemini"
                 (lib_bejson_AI_bejson_gemini_transcribe.py), the only
                 AI-family provider with a transcription wrapper. Structured
                 so a future provider (e.g. Groq's Whisper-based audio
                 endpoint) can be added the same way _adapt_groq/etc. were
                 added to ai_dispatch.py -- a new _adapt_<provider>_transcribe
                 function plus a PROVIDERS/_ADAPTERS entry, nothing else
                 changes.

                 Like ai_dispatch_call(), this never raises for provider-side
                 or input failures (bad path, unsupported extension, no
                 keys, SDK missing, network/auth/rate-limit errors) -- those
                 come back as AIResponse(success=False, error=...). It only
                 raises for programmer error (unknown provider name).
Version:        1.1.0
Date:           2026-10-16
Author:         Elton Boehnen
Contact:        boehnenelton2024@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  3b7e9f14-6c2a-4d81-9e5f-7a1c4b8d2e63
Release_Version: 300

Changelog:
  1.1.0 (2026-10-16) -- Added the "gemini_rest" provider (additive): same Gemini
        keys/models/prompts as "gemini" but over the REST endpoint via urllib,
        no google-genai SDK required (lib_bejson_AI_bejson_gemini_rest_transcribe.py).
        "gemini" behavior is unchanged.
  1.0.0 (2026-09-03) -- Initial creation. New file; ai_dispatch.py,
        ai_response.py, and lib_bejson_AI_bejson_gemini_transcribe.py were
        not modified to add this.
"""

import logging
from pathlib import Path
from typing import Optional, Union

from lib_bejson_AI_ai_response import AIResponse, ai_response_ok, ai_response_error

logger = logging.getLogger("lib_bejson_AI_ai_transcribe_dispatch")

VERSION = "1.1.0"

PROVIDERS = ("gemini", "gemini_rest")


# ── Gemini (bejson_gemini_transcribe.py / GeminiTranscribeAPI) ─────────────

def _adapt_gemini_transcribe(
    file_path: Union[str, Path],
    model_id: Optional[str],
    *,
    mode: str = "verbatim",
    segment: bool = False,
    long_media: bool = False,
    chunk_seconds: int = 600,
    **config,
) -> AIResponse:
    from lib_bejson_AI_bejson_gemini_transcribe import get_standard_transcribe_api

    api = get_standard_transcribe_api()
    used_model = model_id or api.models.active_model_id

    unsupported = []
    if config:
        unsupported.append("config:" + ",".join(sorted(config.keys())))

    try:
        if long_media:
            content = api.transcribe_long_media(
                file_path, model_id=model_id, mode=mode, segment=segment,
                chunk_seconds=chunk_seconds,
            )
        else:
            content = api.transcribe(file_path, model_id=model_id, mode=mode, segment=segment)
        return ai_response_ok(content, provider="gemini", model_id=used_model,
                               unsupported_params=unsupported, raw=content)
    except Exception as e:
        # Fatal (bad path, unsupported extension, no SDK, no keys) and
        # recoverable (rate limit, network, auth, provider, chunking)
        # errors are both normalized to AIResponse(success=False, ...) here
        # -- same contract as ai_dispatch_call(), so a caller never has to
        # know which of GeminiTranscribeAPI's typed exceptions was raised.
        return ai_response_error(str(e), provider="gemini", model_id=used_model,
                                  unsupported_params=unsupported, raw=e)


def _adapt_gemini_rest_transcribe(
    file_path: Union[str, Path],
    model_id: Optional[str],
    *,
    mode: str = "verbatim",
    segment: bool = False,
    long_media: bool = False,
    chunk_seconds: int = 600,
    **config,
) -> AIResponse:
    from lib_bejson_AI_bejson_gemini_rest_transcribe import get_rest_transcribe_api

    api = get_rest_transcribe_api()
    used_model = model_id or api.models.active_model_id
    unsupported = ["config:" + ",".join(sorted(config.keys()))] if config else []
    try:
        if long_media:
            content = api.transcribe_long_media(
                file_path, model_id=model_id, mode=mode, segment=segment,
                chunk_seconds=chunk_seconds,
            )
        else:
            content = api.transcribe(file_path, model_id=model_id, mode=mode, segment=segment)
        return ai_response_ok(content, provider="gemini_rest", model_id=used_model,
                               unsupported_params=unsupported, raw=content)
    except Exception as e:
        return ai_response_error(str(e), provider="gemini_rest", model_id=used_model,
                                  unsupported_params=unsupported, raw=e)


_ADAPTERS = {
    "gemini": _adapt_gemini_transcribe,
    "gemini_rest": _adapt_gemini_rest_transcribe,
}


def ai_transcribe_dispatch(
    provider: str,
    file_path: Union[str, Path],
    *,
    model_id: Optional[str] = None,
    mode: str = "verbatim",
    segment: bool = False,
    long_media: bool = False,
    chunk_seconds: int = 600,
    **config,
) -> AIResponse:
    """
    The one call interface for transcription across AI-family providers.

    provider       -- "gemini" (SDK) or "gemini_rest" (urllib REST, no SDK needed).
    file_path      -- Path to the audio/video file to transcribe.
    model_id       -- Optional model override; falls back to the provider's
                       own active/default model if omitted.
    mode           -- "verbatim" (default) or "diarization".
    segment        -- If True, asks for logical segment/chapter markers.
    long_media     -- If True, chunks the file via ffmpeg first
                       (GeminiTranscribeAPI.transcribe_long_media()) instead
                       of a single inline request -- use for files over the
                       ~15MB single-request limit.
    chunk_seconds  -- Chunk duration when long_media=True (default 600s).
    **config       -- Provider-specific knobs. None are currently honored;
                       passed values land in unsupported_params.

    Returns an AIResponse. Never raises for provider-side or input
    failures -- check response["success"] and response["error"]. Raises
    ValueError only for an unknown provider name.
    """
    if provider not in _ADAPTERS:
        raise ValueError(f"Unknown transcription provider {provider!r}; expected one of {PROVIDERS}")

    try:
        return _ADAPTERS[provider](
            file_path, model_id, mode=mode, segment=segment,
            long_media=long_media, chunk_seconds=chunk_seconds, **config,
        )
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"[ai_transcribe_dispatch] Adapter for {provider!r} raised unexpectedly: {e}")
        return ai_response_error(f"dispatch adapter error: {e}", provider=provider, model_id=model_id)
