"""
Library:         lib_bejson_AI_chat_gemini_engine.py
Family:          AI
Module Purpose:  Multi-turn Gemini REST chat engine: history, inline attachments, thinking, Google Search and code-execution tools, key rotation. The existing GeminiREST prompter is single-shot text-only; this adds what a chat client needs.
Architecture:    urllib only (no SDK). Keys come from a ChatKeyRotator and are sent in the x-goog-api-key header, never in the URL. Failures raise the typed errors from lib_bejson_AI_bejson_errors (E_AI_* codes); no new error codes are defined here.
Version:         1.0.0
Release_Version: 300
Date:            2026-10-28
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   68cda8fc-1dfc-4594-8f45-2ea601b187dc

Changelog:
  1.0.0 (2026-10-28) -- Initial creation (extension of the AI family; no existing AI library modified).
"""

import json
import logging
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set

from lib_bejson_AI_bejson_errors import (
    AuthError, GenerationError, NetworkError, NoAPIKeysError, ProviderServerError, RateLimitedError,
)
from lib_bejson_AI_chat_key_rotator import ChatKeyRotator, chat_key_rotator_tag

logger = logging.getLogger("lib_bejson_AI_chat_gemini_engine")

VERSION = "1.0.0"
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_RETRYABLE_CODES = frozenset({429, 500, 503})
_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]{0,100}$")
GENERIC_SYSTEM_INSTRUCTION = "You are a helpful AI assistant."


@dataclass
class ChatReply:
    text: str
    thinking: str
    parts: List[Dict[str, Any]]      # non-thought parts, stored back into the history
    role: str = "model"
    api_key: str = ""


# Raises GenerationError for ids that could alter the request URL.
def chat_engine_validate_model_id(model: str) -> str:
    if not isinstance(model, str) or not _MODEL_ID_RE.match(model):
        raise GenerationError("Invalid model id.")
    return model


def _api_message(err_body: str, code: int) -> str:
    try:
        return json.loads(err_body).get("error", {}).get("message") or f"HTTP error {code}"
    except Exception:
        return f"HTTP error {code}"


def _classify_http(code: int, message: str) -> Exception:
    if code == 429:
        return RateLimitedError(message)
    if code in (401, 403):
        return AuthError(message)
    if code >= 500:
        return ProviderServerError(message)
    return GenerationError(message)


class GeminiChatEngine:
    def __init__(self, rotator: ChatKeyRotator, *, base_url: str = DEFAULT_BASE_URL, timeout: float = 120.0,
                 retryable_codes: Optional[Set[int]] = None, thinking_budget: int = 8192,
                 opener: Optional[Callable[..., Any]] = None, max_retries: Optional[int] = 3,
                 backoff_delay: float = 1.0, sleep_fn: Optional[Callable[[float], None]] = None) -> None:
        self.rotator = rotator
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retryable = set(retryable_codes) if retryable_codes else set(DEFAULT_RETRYABLE_CODES)
        self.thinking_budget = int(thinking_budget)
        self.max_retries = max(1, int(max_retries)) if max_retries is not None else 3
        self.backoff_delay = max(0.0, float(backoff_delay))
        self._sleep = sleep_fn or time.sleep
        self.last_used_key = ""
        self._open = opener or urllib.request.urlopen

    # ---- payload -----------------------------------------------------------
    def build_payload(self, history: List[Dict[str, Any]], *, system_instruction: str = "", temperature: float = 0.7,
                      max_output_tokens: int = 8192, thinking: bool = False, google_search: bool = False,
                      code_execution: bool = False) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "contents": history,
            "generationConfig": {"temperature": float(temperature), "maxOutputTokens": int(max_output_tokens)},
        }
        si = (system_instruction or "").strip()
        if si and si != GENERIC_SYSTEM_INSTRUCTION:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        if thinking:
            payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": self.thinking_budget, "includeThoughts": True}
        tools: List[Dict[str, Any]] = []
        if google_search:
            tools.append({"googleSearch": {}})
        if code_execution:
            tools.append({"codeExecution": {}})
        if tools:
            payload["tools"] = tools
        return payload

    # ---- transport ---------------------------------------------------------
    # One generateContent call, rotating keys on retryable failures. Raises typed AI errors.
    def generate(self, payload: Dict[str, Any], model: str) -> Dict[str, Any]:
        chat_engine_validate_model_id(model)
        if self.rotator.key_count() == 0:
            raise NoAPIKeysError("No Gemini API keys loaded. Add GEMINI_KEY_1.. to secureenv_file.json.")
        body = json.dumps(payload).encode("utf-8")
        url = f"{self.base_url}/models/{model}:generateContent"
        last_exc: Optional[Exception] = None
        limit = min(self.rotator.key_count(), self.max_retries)
        for attempt in range(limit):
            key = self.rotator.next_key()
            req = urllib.request.Request(url, data=body, method="POST",
                                         headers={"Content-Type": "application/json", "x-goog-api-key": key})
            tag = chat_key_rotator_tag(key)
            try:
                with self._open(req, timeout=self.timeout) as resp:
                    result = json.load(resp)
                self.rotator.mark_success(key)
                self.last_used_key = key
                return result
            except urllib.error.HTTPError as e:
                try:
                    err_body = e.read().decode("utf-8", errors="replace")
                except Exception:
                    err_body = ""
                finally:
                    try:
                        e.close()
                    except Exception:
                        pass
                message = _api_message(err_body, e.code)
                logger.error("%s HTTP %s (attempt %d): %s", tag, e.code, attempt + 1, err_body[:200])
                exc = _classify_http(e.code, message)
                exc.http_status = e.code
                if e.code in self.retryable:
                    self.rotator.mark_failure(key, immediate=(e.code == 429))
                    last_exc = exc
                    if attempt + 1 < limit and self.backoff_delay > 0:
                        self._sleep(min(4.0, self.backoff_delay * (attempt + 1)))
                    continue
                raise exc
            except (urllib.error.URLError, OSError, TimeoutError) as e:
                logger.error("%s network error (attempt %d): %s", tag, attempt + 1, e)
                self.rotator.mark_failure(key)
                last_exc = NetworkError(f"Network error: {e}")
                if attempt + 1 < limit and self.backoff_delay > 0:
                    self._sleep(min(4.0, self.backoff_delay * (attempt + 1)))
        raise last_exc or GenerationError("All API keys exhausted without a successful response.")

    # ---- response ----------------------------------------------------------
    @staticmethod
    def parse_response(result: Dict[str, Any]) -> ChatReply:
        cands = result.get("candidates") or []
        if not cands:
            block = (result.get("promptFeedback") or {}).get("blockReason")
            raise GenerationError(f"Prompt blocked by the model ({block})." if block else "No response from model (no candidates).")
        content = cands[0].get("content") or {}
        text, thought, clean = "", "", []
        for part in content.get("parts", []):
            if part.get("thought"):
                thought += part.get("text", "")
            else:
                text += part.get("text", "")
                clean.append(part)
        return ChatReply(text=text, thinking=thought, parts=clean or [{"text": text}], role=content.get("role", "model"))

    # ---- one chat turn -----------------------------------------------------
    # If a thinking request is rejected with HTTP 400 (model without thinkingConfig support), retries once without it.
    def chat_turn(self, history: List[Dict[str, Any]], model: str, **opts: Any) -> ChatReply:
        payload = self.build_payload(history, **opts)
        try:
            reply = self.parse_response(self.generate(payload, model))
            reply.api_key = self.last_used_key
            return reply
        except GenerationError as e:
            if opts.get("thinking") and getattr(e, "http_status", None) == 400:
                logger.warning("Model %s rejected thinkingConfig; retrying without thinking.", model)
                opts = dict(opts, thinking=False)
                reply = self.parse_response(self.generate(self.build_payload(history, **opts), model))
                reply.api_key = self.last_used_key
                return reply
            raise
