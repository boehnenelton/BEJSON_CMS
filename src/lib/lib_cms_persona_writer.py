"""
Library:        lib_cms_persona_writer.py
Family:         CMS
Description:    PersonaWriter - used by Page_Editor_v2.py for AI-assisted
                 content generation (Gemini-backed persona/task workflow).
Version:        1.2
Date:           2026-09-25
Author:         Elton Boehnen
RELATIONAL_ID:  7c4e9a21-8f3d-4b6c-a052-1e9d7f3c6a48
CHANGE (2026-09-25): PKG142 -- ported the generation architecture from the
React CMS's server-side proxy (src/services/geminiService.ts v1.4.0 +
server.ts's /api/gemini/generate route), per Elton: "take a look at the AI
system in place in the react system, use it to architect the python CMS
version AI system." The React proxy already solves what this file's
previous single-shot generate call didn't: a 429 (quota)/503 (overloaded)
model fallback cascade, token-budget pre-flight trimming to stay under
Gemini's free-tier per-minute ceiling, and structured retry-delay
extraction from error messages. Added as bejson_cms_estimate_tokens()/
bejson_cms_safe_trim_prompt()/bejson_cms_parse_retry_delay() (direct ports
of lib_bejson_CMS_token_budget.ts's same-named functions -- same 3.3
chars/token estimate, same head/tail trim ratios) and a new
generate_with_fallback() method carrying the actual cascade logic. One
adaptation, not a blind port: the React version splits key rotation
(client, before the call) from model cascade (server, in the proxy)
because it's a browser+Node split; this is a single Flask process, so
each cascade attempt here also round-robins to the next key via the
existing (already-correct) _get_key(), rather than fixing one key for the
whole cascade. draft_content() now delegates to generate_with_fallback()
internally instead of its own separate single-shot REST path, so every
caller of this class gets the same robust behavior -- draft_content()
itself has no live caller in this CMS today (grepped
BEJSON_CMS_PageEditorV2.py: it calls _get_key()/get_persona()/
assemble_system_instruction() directly and does its own raw
requests.post(), which is what actually needed this architecture and is
being wired to generate_with_fallback() separately in that file's own
pkg142 change), but keeping it correct and consistent matches this
library family's "modular puzzle pieces" design note (see the
INSTRUCTIONS.txt shipped alongside the standalone Lib_PY/AI family this
CMS's own AI code intentionally does NOT depend on -- this file stays
self-contained, no new dependency on that separate library).
"""
import os
import sys
import re
import math
import json
import time

# Ensure Core libraries are accessible
LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if LIB_DIR not in sys.path:
    sys.path.append(LIB_DIR)

try:
    from google import genai
except ImportError:
    genai = None

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    requests = None
    _REQUESTS_AVAILABLE = False
    # BUG FIX (pkg142, caught before shipping): the pkg142 port added REST-
    # based generate_with_fallback(), which needs `requests` -- but this
    # file previously had NO requests dependency at all (draft_content()
    # was genai-SDK-only, erroring cleanly if genai was missing). Making
    # `import requests` unconditional here would have broken EVERY import
    # of this module -- and therefore all of BEJSON_CMS_PageEditorV2.py,
    # which imports this module at its own top level -- in any environment
    # without requests installed, even though that file already has its
    # own careful _REQUESTS_AVAILABLE guard for exactly this scenario.
    # Confirmed by simulating a missing `requests` module and reproducing
    # the crash before adding this guard.

try:
    import lib_bejson_CMS_cms_core as CMSCore
except ImportError:
    CMSCore = None

VERSION = "1.2"
RELATIONAL_ID = "7c4e9a21-8f3d-4b6c-a052-1e9d7f3c6a48"

# ---------------------------------------------------------------------------
# Token budgeting -- direct port of lib_bejson_CMS_token_budget.ts (React
# CMS, v1.2.0). Same constants, same estimate/trim math, so a prompt judged
# "safe" or "needs trimming" is consistent whether the person is using the
# React CMS or this Flask one.
# ---------------------------------------------------------------------------

MAX_GEMINI_INPUT_TOKENS = 1048576
GEMINI_FREE_TIER_TOKEN_LIMIT = 250000
SAFE_MAX_PROMPT_TOKENS = 160000
SAFE_PLAN_CONTEXT_BUDGET = 140000
SAFE_CHAPTER_CONTEXT_BUDGET = 150000
SAFE_MAX_PROMPT_TOKENS_PAID = 950000


def bejson_cms_estimate_tokens(text):
    """Fast estimator: ~3.3 chars/token for English prose/code/JSON, +4
    token baseline. Deliberately conservative (slight overcount) to
    guarantee safety rather than precision -- same tradeoff the React
    version makes."""
    if not text:
        return 0
    return math.ceil(len(text) / 3.3) + 4


def bejson_cms_format_token_count(tokens):
    if tokens < 1000:
        return f"{tokens} tokens"
    elif tokens < 1000000:
        return f"{tokens / 1000:.1f}k tokens"
    else:
        return f"{tokens / 1000000:.2f}M tokens"


def bejson_cms_safe_trim_prompt(prompt, max_tokens=SAFE_MAX_PROMPT_TOKENS):
    """Pre-flight safeguard: trims a prompt to guarantee it never exceeds
    max_tokens, keeping 70% from the head (instructions/context usually
    lead) and 30% from the tail (often has the actual request). Returns a
    dict, not a tuple, to match the React version's named-field return
    shape rather than positional."""
    initial_tokens = bejson_cms_estimate_tokens(prompt)
    if initial_tokens <= max_tokens:
        return {"trimmed_prompt": prompt, "was_trimmed": False, "estimated_tokens": initial_tokens}

    target_chars = int(max_tokens * 3.3)
    head_chars = int(target_chars * 0.7)
    tail_chars = int(target_chars * 0.3)
    head = prompt[:head_chars]
    tail = prompt[-tail_chars:] if tail_chars else ""
    trimmed = (f"{head}\n\n[WARNING: Prompt content safely budgeted to stay "
               f"under the 1,048,576 Gemini input token limit]\n\n{tail}")
    return {"trimmed_prompt": trimmed, "was_trimmed": True, "estimated_tokens": bejson_cms_estimate_tokens(trimmed)}


def bejson_cms_parse_retry_delay(error_message):
    """Extracts the requested cooldown delay (seconds) from a Gemini 429
    error message. Handles both the human-readable "Please retry in
    25.3s." form and the structured "retryDelay: "25s"" form. Defaults to
    25s if neither pattern matches -- same default the React version uses."""
    if not error_message:
        return 25
    m = re.search(r'retry in\s+([\d.]+)\s*s', error_message, re.IGNORECASE)
    if not m:
        m = re.search(r'retryDelay["\']?\s*:\s*["\']?(\d+)', error_message, re.IGNORECASE)
    if m:
        try:
            parsed = math.ceil(float(m.group(1)))
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return 25


# ---------------------------------------------------------------------------
# Model fallback cascade -- ported from server.ts's /api/gemini/generate
# proxy. The requested model always goes first; the rest of this list
# fills in behind it (deduplicated) so a 429/503 on the requested model
# cascades through alternative Flash models with separate quotas before
# giving up.
# ---------------------------------------------------------------------------

GEMINI_MODEL_FALLBACK_CASCADE_BASE = [
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
]

_CASCADE_STEP_DELAY_SECONDS = 0.6  # matches server.ts's 600ms between cascade attempts


def _is_quota_or_overloaded(status_code, error_text):
    """Classifies a failed attempt as cascade-worthy (429 quota / 503
    overloaded) vs. terminal (bad request, auth failure, etc.) -- same
    string/status matching server.ts's isRateLimited/isServiceUnavailable
    checks use."""
    text_lower = (error_text or "").lower()
    is_503 = (status_code == 503
              or "503" in (error_text or "")
              or "high demand" in text_lower
              or "unavailable" in text_lower)
    is_429 = (status_code == 429
              or "429" in (error_text or "")
              or "resource_exhausted" in text_lower
              or "quota" in text_lower)
    return is_503 or is_429


class PersonaWriter:
    def __init__(self, manifest_path):
        self.manifest_path = manifest_path
        self.db = CMSCore.CMSCore(manifest_path) if CMSCore else None
        self.api_keys = self._load_keys() # REC-8: Load and shuffle once
        self.current_key_idx = 0

    def _load_keys(self):
        # Authoritative path from global context via bejson_env
        from lib_bejson_Core_bejson_env import resolve_path
        key_path = resolve_path("{ADMIN_ROOT}/data/.env/gemini_keys.bejson")
        if not os.path.exists(key_path):
            return []
        try:
            with open(key_path, "r") as f:
                data = json.load(f)
            # BEJSON 104a format: row[1] is typically the key
            valid_keys = [row[1] for row in data.get("Values", []) if len(row) > 1 and row[1] and row[1] != "[REDACTED]"]
            import random
            random.shuffle(valid_keys)
            return valid_keys
        except (json.JSONDecodeError, KeyError, IOError) as e:
            print(f"[PersonaWriter] Error loading keys: {e}")
            return []

    def _get_key(self):
        if not self.api_keys: return None
        if self.current_key_idx >= len(self.api_keys): self.current_key_idx = 0
        key = self.api_keys[self.current_key_idx]
        self.current_key_idx += 1
        return key

    def get_persona(self, name):
        if not self.db: return None
        records = self.db.get_records("AI_Profile")
        for r in records:
            if r.get("persona_name") == name:
                return r
        return None

    def assemble_system_instruction(self, persona):
        name = persona.get("persona_name", "AI")
        arch = persona.get("persona_archetype", "Persona")
        identity = f"[IDENTITY]: {name} ({arch})"

        tones = persona.get("persona_tone") or []
        voice = f"[VOICE]: {', '.join(tones)}" if isinstance(tones, list) and tones else ""

        quirks_text = persona.get("persona_bio") or ""
        quirks = f"[QUIRKS]: {quirks_text}" if quirks_text else ""

        langs = persona.get("persona_code_parsing_languages") or []
        domain = f"[DOMAIN]: {', '.join(langs)}" if isinstance(langs, list) and langs else ""

        base_inst = persona.get("persona_system_instruction", "")
        extra_lines = "\n".join(line for line in [identity, voice, quirks, domain] if line)
        return f"{base_inst}\n\n{extra_lines}" if extra_lines else base_inst

    def generate_with_fallback(self, prompt, system_instruction=None, model="gemini-3.6-flash",
                                generation_config=None, timeout=90):
        """Ported from server.ts's /api/gemini/generate proxy (React CMS
        v1.4.0). REST-only (this file's google-genai SDK path stays in
        draft_content()'s legacy branch below for when the SDK is
        installed) -- REST keeps this cascade's retry logic simple and
        uniform across every attempt, and every route in this CMS that
        actually calls Gemini today (BEJSON_CMS_PageEditorV2.py's
        /api/tasking/* routes) already used REST directly, so this doesn't
        add a new dependency anywhere.

        Pre-flight trims the prompt to SAFE_MAX_PROMPT_TOKENS, then walks
        the model cascade (requested model first, then
        GEMINI_MODEL_FALLBACK_CASCADE_BASE, deduplicated). Each attempt
        pulls the next key from _get_key() (round-robin, unchanged) --
        unlike the React version, which only cascades models because the
        client already picked one key before calling the server, this
        cascades BOTH keys and models per attempt, since everything is
        server-side here and there's no reason not to.

        Returns {"ok": True, "text": str, "model_used": str,
        "was_trimmed": bool} on success, or {"ok": False, "error": str,
        "status": int, "retry_delay": int} on failure -- the retry_delay
        is always populated (bejson_cms_parse_retry_delay defaults to 25
        even when nothing in the error message says so), so a caller can
        always show a "try again in Ns" message rather than a bare error.
        """
        if not _REQUESTS_AVAILABLE:
            return {"ok": False, "error": "The 'requests' package is not installed.", "status": 500, "retry_delay": 0}

        trim = bejson_cms_safe_trim_prompt(prompt)
        prompt_to_send = trim["trimmed_prompt"]

        cascade = [model] + [m for m in GEMINI_MODEL_FALLBACK_CASCADE_BASE if m != model]

        last_error = None
        last_status = 500

        for i, candidate_model in enumerate(cascade):
            key = self._get_key()
            if not key:
                return {"ok": False, "error": "No API keys found.", "status": 400, "retry_delay": 0}

            payload = {"contents": [{"parts": [{"text": prompt_to_send}]}]}
            if system_instruction:
                payload["system_instruction"] = {"parts": [{"text": system_instruction}]}
            if generation_config:
                payload["generationConfig"] = generation_config

            try:
                res = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{candidate_model}:generateContent?key={key}",
                    json=payload, timeout=timeout,
                )
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                last_status = 599
                if i < len(cascade) - 1:
                    time.sleep(_CASCADE_STEP_DELAY_SECONDS)
                    continue
                break

            if res.status_code == 200:
                try:
                    data = res.json()
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError, ValueError):
                    last_error = "Malformed response: no candidates/content in a 200 OK."
                    last_status = 502
                    break
                return {"ok": True, "text": text, "model_used": candidate_model, "was_trimmed": trim["was_trimmed"]}

            last_error = res.text
            last_status = res.status_code

            if _is_quota_or_overloaded(res.status_code, res.text) and i < len(cascade) - 1:
                time.sleep(_CASCADE_STEP_DELAY_SECONDS)
                continue
            break

        return {
            "ok": False,
            "error": last_error or "Unknown error",
            "status": last_status,
            "retry_delay": bejson_cms_parse_retry_delay(last_error or ""),
        }

    def draft_content(self, persona_name, topic, model="gemini-3.6-flash"):
        persona = self.get_persona(persona_name)
        if not persona: return "ERROR: Persona not found."

        sys_inst = self.assemble_system_instruction(persona)
        prompt = f"Write a CMS page about: {topic}. Output ONLY clean HTML body content without Markdown blocks or ``` tags."

        if genai:
            # SDK path kept as-is (single-shot, no cascade) when the
            # google-genai SDK is installed -- the cascade above is REST-
            # only by design (see generate_with_fallback()'s docstring).
            key = self._get_key()
            if not key: return "ERROR: No API keys found."
            try:
                client = genai.Client(api_key=key)
                config = {
                    "system_instruction": sys_inst,
                    "temperature": float(persona.get("persona_creativity", 0.7)),
                    "max_output_tokens": int(persona.get("persona_max_tokens", 8192))
                }
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config
                )
                return response.text
            except Exception as e:
                return f"ERROR (SDK): {str(e)}"
        else:
            # No SDK: use the cascade -- this is the path that benefits
            # from generate_with_fallback() (fixed pkg142; previously this
            # branch was its own separate single-shot requests.post() call
            # with no retry/fallback at all).
            gen_config = {
                "maxOutputTokens": int(persona.get("persona_max_tokens", 8192)),
                "temperature": float(persona.get("persona_creativity", 0.7)),
            }
            result = self.generate_with_fallback(prompt, system_instruction=sys_inst, model=model, generation_config=gen_config)
            if result["ok"]:
                return result["text"].strip()
            return f"ERROR (REST): {result['error']}"
