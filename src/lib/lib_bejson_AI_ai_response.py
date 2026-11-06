"""
Library:        lib_bejson_AI_ai_response.py
Family:         AI
Description:    Atomic unit: the single common response shape returned by
                 every provider adapter in lib_bejson_AI_ai_dispatch.py
                 (Groq, OpenRouter, Gemini, GenAI). Exists so calling code
                 never has to know that Groq returns a bare string, OpenRouter
                 returns a {content, thought} dict, GeminiAPI raises on
                 failure, and GenAI's prompter returns None on failure --
                 those four different conventions are exactly why nothing
                 could call the providers interchangeably before this file.
Version:        1.0.2
Date:           2026-10-21
Author:         Elton Boehnen
Contact:        boehnenelton2024@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  1402866f-e0d3-46bf-972e-fdb05957b075

Changelog:
  1.0.2 (2026-10-21) -- Guard auto_parse_bejson_104db against non-JSON text
        (require '{' alongside '104db' and 'BEJSON'), downgrade parser errors
        to debug without exc_info, and allow auto_parse=False in ai_response_ok.
  1.0.1 (2026-09-09) -- BUGFIX: Added missing imports (Tuple from typing,
        Path from pathlib, logging) that caused auto_parse_bejson_104db()
        to silently crash on every invocation via bare except swallowing
        NameError. Structured output detection now functional.
  1.0.0 (2026-08-13) -- Initial creation, part of the AI-family common call
        interface design (dispatch.py depends on this file).
"""

import logging
from pathlib import Path
from typing import Any, Optional, Tuple, TypedDict

logger = logging.getLogger(__name__)

VERSION = "1.0.2"


class AIResponse(TypedDict):
    """
    The one response shape every provider adapter returns.

    success            -- True if a usable reply was produced, False on any
                           failure (auth, network, no keys, SDK missing, etc).
    content             -- The reply text. "" on failure.
    thought             -- Reasoning/thinking text if the provider exposed it
                           (OpenRouter reasoning models, Gemini thinking).
                           "" if the provider doesn't support it.
    error               -- Human-readable error string. None on success.
    provider            -- "groq" | "openrouter" | "gemini" | "genai".
    model_id            -- The model actually used to fulfill the call.
    unsupported_params  -- Names of any common-interface kwargs this provider
                           could not honor (e.g. Groq can't take a per-call
                           system_instruction -- it's baked into its profile
                           file). Empty list if everything was honored.
                           ai_dispatch_call() always fills this in rather than
                           silently dropping a parameter the caller asked for.
    raw                 -- The provider's original, unnormalized return value,
                           for callers that need provider-specific detail.
    """
    success: bool
    content: str
    thought: str
    error: Optional[str]
    provider: str
    model_id: Optional[str]
    unsupported_params: list
    raw: Any
    unpacked_meta: Optional[dict]
    unpacked_files_written: int
    unpacked_output_dir: Optional[str]


def auto_parse_bejson_104db(content: str, base_output_dir: Optional[str] = None) -> Tuple[Optional[dict], int, Optional[str]]:
    """
    Detects if content is a valid BEJSON 104db document (e.g. from bejson_104db_generator profile),
    parses it, and automatically restores/unchunks files to a target directory.
    Output directory precedence:
      1. base_output_dir / project_name (if base_output_dir supplied)
      2. ./extracted_projects/<project_name> (default)
    Returns (project_meta, files_written_count, final_output_dir) or (None, 0, None) if not 104db.
    """
    if "{" not in content or "104db" not in content or "BEJSON" not in content:
        return None, 0, None

    try:
        from lib_bejson_Core_bejson_104db_parser import parse_bejson_104db_doc, unpack_bejson_104db_to_dir
        doc = parse_bejson_104db_doc(content)
        
        # Determine target directory from ProjectMeta or fallback
        proj_name = "unnamed_project"
        for row in doc.get("Values", []):
            if row and row[0] == "ProjectMeta" and len(row) > 1 and row[1]:
                proj_name = str(row[1])
                break

        if base_output_dir:
            target_dir = str(Path(base_output_dir) / proj_name)
        else:
            target_dir = str(Path.cwd() / "extracted_projects" / proj_name)

        meta, count = unpack_bejson_104db_to_dir(doc, target_dir)
        return meta, count, target_dir
    except Exception as e:
        logger.debug("auto_parse_bejson_104db failed/skipped: %s", e)
        return None, 0, None


def ai_response_ok(
    content: str,
    *,
    provider: str,
    model_id: Optional[str] = None,
    thought: str = "",
    unsupported_params: Optional[list] = None,
    raw: Any = None,
    base_output_dir: Optional[str] = None,
    auto_parse: bool = True,
) -> AIResponse:
    """Build a successful AIResponse and automatically unchunk/parse 104db content if detected."""
    meta, count, out_dir = auto_parse_bejson_104db(content, base_output_dir) if auto_parse else (None, 0, None)
    return AIResponse(
        success=True,
        content=content,
        thought=thought,
        error=None,
        provider=provider,
        model_id=model_id,
        unsupported_params=unsupported_params or [],
        raw=raw,
        unpacked_meta=meta,
        unpacked_files_written=count,
        unpacked_output_dir=out_dir,
    )


def ai_response_error(
    error: str,
    *,
    provider: str,
    model_id: Optional[str] = None,
    unsupported_params: Optional[list] = None,
    raw: Any = None,
) -> AIResponse:
    """Build a failed AIResponse. content is always "" on failure."""
    return AIResponse(
        success=False,
        content="",
        thought="",
        error=error,
        provider=provider,
        model_id=model_id,
        unsupported_params=unsupported_params or [],
        raw=raw,
        unpacked_meta=None,
        unpacked_files_written=0,
        unpacked_output_dir=None,
    )
