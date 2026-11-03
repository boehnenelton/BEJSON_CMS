"""
Library:         lib_bejson_AI_chat_interactions_engine.py
Family:          AI
Module Purpose:  Chat adapter over the existing Gemini Interactions provider (lib_bejson_AI_bejson_interactions.GeminiInteractionsAPI): key rotation with cool-off, server-side conversation chaining via previous_interaction_id, text/image/document inputs, optional google_search / code_execution tools, typed errors.
Architecture:    Wraps the provider (>= 1.2.0). Keys come from a ChatKeyRotator and are passed per call (api_key=). generation_config is opt-in (constructor flag) and UNVERIFIED against the live API, so a 400 retries without it. Failures raise the typed errors of lib_bejson_AI_bejson_errors; no new error codes.
Version:         1.1.0
Release_Version: 300
Date:            2026-10-29
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   0409189e-34b2-40bb-bb8c-ed7e2588b15f

Changelog:
  1.1.0 (2026-10-29) -- Uses interactions provider 1.2.0: opt-in generation_config (temperature / max_output_tokens / thinking), .http_status on errors, endpoint passed per call (no module-constant override), shared text/thought extractors. Falls back to a request without generation_config, then without tools, on HTTP 400.
  1.0.0 (2026-10-29) -- Initial creation (extension of the AI family; no existing AI library modified).
"""

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from lib_bejson_AI_bejson_errors import (
    AuthError, GenerationError, NetworkError, NoAPIKeysError, ProviderServerError, RateLimitedError,
)
from lib_bejson_AI_chat_gemini_engine import chat_engine_validate_model_id
from lib_bejson_AI_chat_key_rotator import ChatKeyRotator, chat_key_rotator_tag

try:                                    # the provider imports `requests`; without it the route is simply unavailable
    import lib_bejson_AI_bejson_interactions as _provider
    INTERACTIONS_IMPORT_ERROR: Optional[str] = None
except BaseException as _e:             # the provider calls sys.exit() on a missing dependency
    _provider = None
    INTERACTIONS_IMPORT_ERROR = f"{type(_e).__name__}: {_e}"

logger = logging.getLogger("lib_bejson_AI_chat_interactions_engine")

VERSION = "1.1.0"
RETRYABLE_STATUS = {429, 500, 503}
TOOL_GOOGLE_SEARCH = {"type": "google_search"}
TOOL_CODE_EXECUTION = {"type": "code_execution"}


@dataclass
class InteractionReply:
    text: str
    thinking: str
    interaction_id: Optional[str]
    notice: str = ""
    api_key: str = ""


class _KeyView:
    """Stand-in for GeminiKeyRegistry: the provider only reads .keys (and we always pass api_key explicitly)."""
    def __init__(self, rotator: ChatKeyRotator) -> None:
        self._r = rotator

    @property
    def keys(self) -> List[str]:
        return list(self._r._keys)


class _ModelView:
    active_model_id = ""


def interactions_available() -> bool:
    return _provider is not None


def interactions_extract_text(interaction: Dict[str, Any]) -> str:
    return _provider.interactions_extract_text(interaction)


def interactions_extract_thought(interaction: Dict[str, Any]) -> str:
    return _provider.interactions_extract_thought(interaction)


def interactions_generation_config(temperature: Optional[float], max_output_tokens: Optional[int],
                                   thinking_level: Optional[str]) -> Dict[str, Any]:
    """Interactions generation_config from chat options. Field names follow the public Interactions API reference
    (temperature, max_output_tokens, thinking_level, thinking_summaries) and are UNVERIFIED against a live call."""
    cfg: Dict[str, Any] = {}
    if temperature is not None:
        cfg["temperature"] = float(temperature)
    if max_output_tokens:
        cfg["max_output_tokens"] = int(max_output_tokens)
    if thinking_level:
        cfg["thinking_level"] = thinking_level
        cfg["thinking_summaries"] = "auto"
    return cfg


# The provider raises RuntimeError("[E_AI_INTERACTIONS_HTTP_ERROR=201] Interactions API error: <body>"); recover the HTTP status from the body.
def _status_of(message: str) -> Optional[int]:
    i = message.find("{")
    if i != -1:
        try:
            code = json.loads(message[i:]).get("error", {}).get("code")
            if isinstance(code, int):
                return code
        except ValueError:
            pass
    low = message.lower()
    for word, status in (("resource_exhausted", 429), ("unavailable", 503), ("internal", 500), ("permission_denied", 403),
                         ("unauthenticated", 401), ("invalid_argument", 400)):
        if word in low:
            return status
    m = re.search(r"\b(4\d\d|5\d\d)\b", message)
    return int(m.group(1)) if m else None


def _api_text(message: str) -> str:
    i = message.find("{")
    if i != -1:
        try:
            return json.loads(message[i:]).get("error", {}).get("message") or message
        except ValueError:
            pass
    return message


def _typed(status: Optional[int], message: str) -> Exception:
    text = _api_text(message)
    if status == 429:
        exc: Exception = RateLimitedError(text)
    elif status in (401, 403):
        exc = AuthError(text)
    elif status and status >= 500:
        exc = ProviderServerError(text)
    else:
        exc = GenerationError(text)
    exc.http_status = status
    return exc


class InteractionsChatEngine:
    def __init__(self, rotator: ChatKeyRotator, *, timeout: int = 60, endpoint: Optional[str] = None,
                 retryable: Optional[set] = None, send_generation_config: bool = False,
                 thinking_level: str = "high", max_retries: Optional[int] = 3,
                 backoff_delay: float = 1.0, sleep_fn: Optional[Callable[[float], None]] = None) -> None:
        if _provider is None:
            raise GenerationError(f"Interactions provider unavailable ({INTERACTIONS_IMPORT_ERROR}).")
        self.endpoint = endpoint or None
        self.send_generation_config = bool(send_generation_config)
        self.thinking_level = thinking_level
        self.rotator = rotator
        self.timeout = int(timeout)
        self.retryable = set(retryable) if retryable else set(RETRYABLE_STATUS)
        self.max_retries = max(1, int(max_retries)) if max_retries is not None else 3
        self.backoff_delay = max(0.0, float(backoff_delay))
        self._sleep = sleep_fn or time.sleep
        self.last_used_key = ""
        self._api = _provider.GeminiInteractionsAPI(_KeyView(rotator), _ModelView())

    # `input_parts`: Interactions content blocks ({"type":"text"|"image"|"document", ...}).
    def chat_turn(self, input_parts: List[Dict[str, Any]], model: str, *, system_instruction: str = "",
                  previous_interaction_id: Optional[str] = None, google_search: bool = False,
                  code_execution: bool = False, temperature: Optional[float] = None,
                  max_output_tokens: Optional[int] = None, thinking: bool = False) -> InteractionReply:
        chat_engine_validate_model_id(model)
        if self.rotator.key_count() == 0:
            raise NoAPIKeysError("No Gemini API keys loaded. Add GEMINI_KEY_1.. to secureenv_file.json.")
        tools: List[Dict[str, Any]] = []
        if google_search:
            tools.append(dict(TOOL_GOOGLE_SEARCH))
        if code_execution:
            tools.append(dict(TOOL_CODE_EXECUTION))
        gen_cfg: Dict[str, Any] = {}
        if self.send_generation_config:
            gen_cfg = interactions_generation_config(temperature, max_output_tokens, self.thinking_level if thinking else None)
        notices: List[str] = []
        last_exc: Optional[Exception] = None
        attempt = 0
        limit = min(self.rotator.key_count(), self.max_retries)
        while attempt < limit:
            key = self.rotator.next_key()
            self.last_used_key = key
            tag = chat_key_rotator_tag(key)
            try:
                interaction = self._api.chat(list(input_parts), tools=tools or None, model_id=model,
                                             system_instruction=system_instruction or None,
                                             previous_interaction_id=previous_interaction_id, api_key=key, store=True,
                                             generation_config=gen_cfg or None, endpoint=self.endpoint)
            except TimeoutError as e:
                logger.error("%s timeout (attempt %d): %s", tag, attempt + 1, e)
                self.rotator.mark_failure(key); last_exc = NetworkError(str(e)); attempt += 1
                if attempt < limit and self.backoff_delay > 0:
                    self._sleep(min(4.0, self.backoff_delay * attempt))
                continue
            except RuntimeError as e:
                status = getattr(e, "http_status", None) or _status_of(str(e))
                logger.error("%s HTTP %s (attempt %d): %s", tag, status, attempt + 1, str(e)[:200])
                if status == 400 and gen_cfg:
                    logger.warning("Interactions API rejected generation_config %s; retrying without it.", sorted(gen_cfg))
                    gen_cfg = {}
                    notices.append("The Interactions API rejected temperature/max-token/thinking settings; answered with defaults.")
                    if self.backoff_delay > 0:
                        self._sleep(0.5)
                    continue                                   # retried on the next key in rotation; not counted as an attempt
                if (status == 400 or (status == 429 and "quota" in str(e).lower())) and tools:
                    logger.warning("Interactions API rejected tools %s (status %s); retrying without them.", [t["type"] for t in tools], status)
                    tools = []
                    notices.append("The Interactions API rejected the search/code tool for this request; answered without it.")
                    if self.backoff_delay > 0:
                        self._sleep(0.5)
                    continue
                exc = _typed(status, str(e))
                if status in self.retryable:
                    self.rotator.mark_failure(key, immediate=(status == 429))
                    last_exc = exc
                    attempt += 1
                    if attempt < limit and self.backoff_delay > 0:
                        self._sleep(min(4.0, self.backoff_delay * attempt))
                    continue
                raise exc
            except Exception as e:                             # requests.ConnectionError etc.
                logger.error("%s network error (attempt %d): %s", tag, attempt + 1, e)
                self.rotator.mark_failure(key); last_exc = NetworkError(f"Network error: {e}"); attempt += 1
                if attempt < limit and self.backoff_delay > 0:
                    self._sleep(min(4.0, self.backoff_delay * attempt))
                continue
            self.rotator.mark_success(key)
            self.last_used_key = key
            text = interactions_extract_text(interaction)
            if not text:
                raise GenerationError("No text output from the Interactions API (status: %s)." % interaction.get("status", "unknown"))
            return InteractionReply(text=text, thinking=interactions_extract_thought(interaction),
                                    interaction_id=interaction.get("id"), notice=" ".join(notices),
                                    api_key=key)
        raise last_exc or GenerationError("All API keys exhausted without a successful response.")
