"""
Library:        lib_bejson_AI_ai_openai_compatible_base.py
Family:         AI
Description:    Atomic REST client for any provider that speaks the
                 OpenAI /chat/completions wire format (bearer auth, POST
                 {model, messages, ...} -> choices[0].message.content).
                 HuggingFace's inference router and Provocative both fit
                 this shape exactly ("same OpenAI SDK, zero other changes"
                 per Provocative's own docs), so rather than write two
                 near-identical requests.post() wrappers, both providers'
                 library files are thin config on top of this one client --
                 same reasoning as lib_bejson_AI_ai_registry_base.py
                 factoring out the key/model registry duplication across
                 Groq/OpenRouter/Gemini.
Version:        1.0.0
Date:           2026-08-13
Author:         Elton Boehnen
Contact:        boehnenelton2024@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  2d6281dd-9931-4267-8998-ea0584e02c23
Release_Version: 300

Changelog:
  1.0.0 (2026-08-13) -- Initial creation.
"""

import logging
from typing import Any, Dict, Optional

import requests

from lib_bejson_AI_bejson_errors import (
    NoAPIKeysError, RateLimitedError, NetworkError, AuthError,
    ProviderServerError, GenerationError,
)

logger = logging.getLogger("lib_bejson_AI_ai_openai_compatible_base")

VERSION = "1.0.0"


def classify_http_error(e: Exception, status_code: Optional[int] = None) -> Exception:
    """
    Same fatal/recoverable classification lib_bejson_AI_bejson_gemini.py
    2.4.0 applies to its SDK exceptions, adapted for a raw HTTP client:
    status code first (authoritative when present), falling back to the
    plain-language substring matching used elsewhere in the family.
    """
    if status_code == 429:
        return RateLimitedError(f"Rate limited (HTTP 429): {e}")
    if status_code in (401, 403):
        return AuthError(f"Auth error (HTTP {status_code}): {e}")
    if status_code is not None and status_code >= 500:
        return ProviderServerError(f"Provider server error (HTTP {status_code}): {e}")

    text = str(e)
    low = text.lower()
    if "429" in text or "rate limit" in low:
        return RateLimitedError(f"Rate limited: {text}")
    if ("timed out" in low or "connection" in low or "network" in low
            or "name or service not known" in low or "urlopen error" in low):
        return NetworkError(f"Network error: {text}")
    if "401" in text or "403" in text or "unauthorized" in low or "invalid api key" in low:
        return AuthError(f"Auth error: {text}")
    if "500" in text or "502" in text or "503" in text or "unavailable" in low:
        return ProviderServerError(f"Provider server error: {text}")
    return GenerationError(f"Generation failed: {text}")


class OpenAICompatibleClient:
    """
    provider_label  -- used only in error messages/logging (e.g. "huggingface").
    base_url        -- e.g. "https://inference.provocative.earth/v1" (no
                       trailing /chat/completions -- this class appends it).
    """

    def __init__(self, provider_label: str, base_url: str, default_model: str):
        self.provider_label = provider_label
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model

    def chat(
        self,
        prompt: str,
        api_key: Optional[str],
        *,
        model: Optional[str] = None,
        system_instruction: Optional[str] = None,
        timeout: int = 30,
        **extra_body,
    ) -> str:
        if not api_key:
            raise NoAPIKeysError(f"No {self.provider_label} API key available.")

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        body: Dict[str, Any] = {"model": model or self.default_model, "messages": messages}
        body.update(extra_body)

        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=timeout,
            )
            if resp.status_code >= 400:
                raise classify_http_error(
                    Exception(f"{resp.status_code} {resp.text[:300]}"), status_code=resp.status_code
                )
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except (RateLimitedError, NetworkError, AuthError, ProviderServerError, GenerationError, NoAPIKeysError):
            raise
        except Exception as e:
            logger.error(f"[{self.provider_label}] Request failed: {e}")
            raise classify_http_error(e)
