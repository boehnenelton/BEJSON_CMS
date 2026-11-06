"""
Library:         lib_bejson_AI_ai_transcribe_http.py
Family:          AI
Module Purpose:  Shared stdlib (urllib) POST with round-robin key rotation for REST transcription providers,
                 raising the AI family's typed errors; honors an optional call throttle between every attempt.
Architecture:    Mirrors the retry loop in lib_bejson_AI_bejson_gemini_rest_transcribe.py (key rotation per
                 attempt, _classify_generation_error() typing) without its fixed backoff sleeps: pacing is
                 delegated to the caller's throttle object (any object with wait() and mark()).
Version:         1.0.0
Release_Version: 300
Date:            2026-10-18
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   9576ae18-db4c-4ab3-a81e-dd40b78f7f4c
"""

import logging
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Optional, Tuple

from lib_bejson_AI_bejson_errors import NoAPIKeysError
from lib_bejson_AI_bejson_gemini import _classify_generation_error

logger = logging.getLogger("lib_bejson_AI_ai_transcribe_http")

VERSION = "1.0.0"
USER_AGENT = "Autobase64-AI/1.0"
RETRYABLE_HTTP = (401, 403, 429, 500, 502, 503, 504)   # 401/403: the next key may be valid
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_TIMEOUT_SECONDS = 300


def rotating_post(
    keys: Any,
    build_request: Callable[[str], Tuple[str, Dict[str, str], bytes]],
    *,
    label: str,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    throttle: Optional[Any] = None,
) -> str:
    """
    POSTs build_request(key) -> (url, headers, body), rotating keys on retryable failures (HTTP 401/403/429/5xx
    or network error). Returns the response body text. Raises NoAPIKeysError (fatal) or the typed
    AIRecoverableError from _classify_generation_error() once attempts are exhausted or the error is not retryable.
    """
    if not getattr(keys, "keys", None):
        raise NoAPIKeysError(f"No {label} API keys found.")
    attempts = max(1, min(len(keys.keys), max_attempts))
    last: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        key = keys.get_next_key()
        url, headers, body = build_request(key)
        headers.setdefault("User-Agent", USER_AGENT)
        if throttle is not None:
            throttle.wait()
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            detail = " ".join(e.read().decode("utf-8", "replace").split())[:300]
            retryable = e.code in RETRYABLE_HTTP
            last = _classify_generation_error(Exception(f"HTTP {e.code} {e.reason}: {detail}"))
        except Exception as e:      # network / timeout
            retryable = True
            last = _classify_generation_error(e)
        finally:
            if throttle is not None:
                throttle.mark()
        last = type(last)(str(last).replace("Gemini", label, 1))     # classifier text is Gemini-worded; name the real provider
        logger.warning("[%s] attempt %d/%d failed: %s", label, attempt, attempts, str(last)[:200])
        if not retryable:
            break
    raise last
