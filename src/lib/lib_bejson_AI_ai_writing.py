#!/usr/bin/env python3
"""
Library:         lib_bejson_AI_ai_writing.py
Family:          AI
Module Purpose:  BKS-1 AI Writing & Generation Bridge powered by the CLI_AI 48
                 AI library family (/storage/emulated/0/cli ai 48/lib/AI/).
                 Routes all plan and chapter generation calls through
                 lib_bejson_AI_ai_dispatch.ai_dispatch_call(), captures SHA-256
                 prompt provenance, enforces BKS-1 Contextualize_Plan and
                 Contextualize_Last, and records gated attempts into BKS-1
                 Book Documents via lib_bejson_Writing_bks_store.
Format_Scope:    104db (Book Document) | 104a (JobMaker plan & AI model registries)
Release_Version: 300
Version:         1.1.0
Date:            2026-11-03
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   e19f7a42-3c81-4b50-9d24-6f8b2a1e4c90
"""

import hashlib
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

VERSION = "1.1.0"

logger = logging.getLogger("lib_bejson_AI_ai_writing")

# Ensure local src/lib has strict priority over external fallback paths
_SCRIPT_DIR = Path(__file__).resolve().parent
_CLI_AI_48_ROOT = Path("/storage/emulated/0/cli ai 48")

if str(_SCRIPT_DIR) in sys.path:
    sys.path.remove(str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR))

for _candidate_path in (
    str(_CLI_AI_48_ROOT / "lib" / "AI"),
    str(_CLI_AI_48_ROOT / "lib" / "Core"),
    str(_CLI_AI_48_ROOT / "lib"),
):
    if os.path.isdir(_candidate_path) and _candidate_path not in sys.path:
        sys.path.append(_candidate_path)

import lib_bejson_Core_bejson_core as Core
from lib_bejson_AI_ai_dispatch import PROVIDERS, ai_dispatch_call
from lib_bejson_AI_ai_response import AIResponse
import lib_bejson_Writing_bks_booktypes as BookTypes
import lib_bejson_Writing_bks_derive as Derive
import lib_bejson_Writing_bks_gates as Gates
import lib_bejson_Writing_bks_plan as Plan
import lib_bejson_Writing_bks_registry as Registry
import lib_bejson_Writing_bks_store as Store

EXCLUDED_LOCAL_PROVIDERS = {"ollamalocal", "litertlm"}
ACTIVE_PROVIDERS = [p for p in PROVIDERS if p.lower() not in EXCLUDED_LOCAL_PROVIDERS]

MAX_COMBINED_PROMPT_TOKENS = 48000
MAX_COMBINED_PROMPT_CHARS = 192000  # 48,000 tokens * 4 chars/token

AUTHOR_PRECEDENCE_DIRECTIVE = (
    "[AUTHOR PRECEDENCE RULE]:\n"
    "The Author Persona and Author Writing Instructions defined for this task establish "
    "the primary voice, domain authority, and stylistic direction. The author's directives and role "
    "STRICTLY OVERRIDE any contradictory profile instructions, baseline guidelines, or generic rules. "
    "When directives conflict, ALWAYS prioritize and obey the author's voice, instructions, and constraints."
)

_PROVIDER_REGISTRY_FILES = {
    "geminirest": "gemini_model_registry.104a.bejson",
    "gemini": "gemini_model_registry.104a.bejson",
    "genai": "gemini_model_registry.104a.bejson",
    "groq": "groq_model_registry.104a.bejson",
    "openrouter": "openrouter_model_registry.104a.bejson",
    "tokenrouter": "tokenrouter_model_registry.104a.bejson",
    "grok": "grok_model_registry.104a.bejson",
    "huggingface": "huggingface_model_registry.104a.bejson",
    "openai": "openai_model_registry.104a.bejson",
    "ollama": "ollama_model_registry.104a.bejson",
}


def _resolve_ai_config_dir() -> Path:
    """Locate the AI config directory containing *_model_registry.104a.bejson."""
    local_cfg = _SCRIPT_DIR / "config"
    if local_cfg.is_dir():
        return local_cfg
    cli_ai_cfg = _CLI_AI_48_ROOT / "lib" / "AI" / "config"
    if cli_ai_cfg.is_dir():
        return cli_ai_cfg
    local_cfg.mkdir(parents=True, exist_ok=True)
    return local_cfg


def ai_writing_get_providers_and_models() -> Dict[str, Any]:
    """
    Read all registered AI providers and their models from the CLI_AI 48
    BEJSON 104a model registries using O(1) Field Map Cache lookups.
    """
    config_dir = _resolve_ai_config_dir()
    providers_map: Dict[str, List[Dict[str, Any]]] = {}
    all_models_flat: List[Dict[str, Any]] = []

    for provider_name in ACTIVE_PROVIDERS:
        reg_filename = _PROVIDER_REGISTRY_FILES.get(provider_name)
        models_for_provider: List[Dict[str, Any]] = []
        if reg_filename:
            reg_path = config_dir / reg_filename
            if not reg_path.exists():
                reg_path = _SCRIPT_DIR / "config" / reg_filename
            if reg_path.exists():
                doc = Core.bejson_core_load_file(str(reg_path))
                if doc and doc.get("Fields") and doc.get("Values"):
                    field_map = Core.bejson_core_get_field_map(doc)
                    id_idx = field_map.get("model_id", -1)
                    name_idx = field_map.get(
                        "display_name",
                        field_map.get("model_name", field_map.get("friendly_name", id_idx)),
                    )
                    active_idx = field_map.get("currently_active", -1)
                    for row in doc.get("Values", []):
                        if id_idx != -1 and id_idx < len(row) and row[id_idx]:
                            model_id_val = str(row[id_idx])
                            display_val = (
                                str(row[name_idx])
                                if (name_idx != -1 and name_idx < len(row) and row[name_idx])
                                else model_id_val
                            )
                            is_active = (
                                bool(row[active_idx])
                                if (active_idx != -1 and active_idx < len(row))
                                else False
                            )
                            entry = {
                                "provider": provider_name,
                                "model_id": model_id_val,
                                "friendly_name": f"[{provider_name}] {display_val}",
                                "display_name": display_val,
                                "currently_active": is_active,
                            }
                            models_for_provider.append(entry)
                            all_models_flat.append(entry)
        providers_map[provider_name] = models_for_provider

    return {
        "providers": list(ACTIVE_PROVIDERS),
        "default_provider": "geminirest",
        "models_by_provider": providers_map,
        "models": all_models_flat,
    }


def ai_writing_call(
    user_input: str,
    *,
    provider: str = "geminirest",
    model_id: Optional[str] = None,
    system_instruction: Optional[str] = None,
    **config,
) -> AIResponse:
    """
    Execute an AI generation call via CLI_AI 48's ai_dispatch_call().
    If 'gemini' or 'genai' fails due to missing google-genai SDK, automatically
    falls back to 'geminirest' (zero-SDK stdlib REST).
    """
    normalized_provider = (provider or "geminirest").strip().lower()
    if normalized_provider not in PROVIDERS:
        normalized_provider = "geminirest"

    response = ai_dispatch_call(
        normalized_provider,
        user_input,
        model_id=model_id,
        system_instruction=system_instruction,
        **config,
    )
    if not response.get("success") and normalized_provider in ("gemini", "genai"):
        err_text = str(response.get("error") or "").lower()
        if "sdk" in err_text or "genai" in err_text or "import" in err_text:
            logger.info("[ai_writing] Falling back from %s to geminirest", normalized_provider)
            response = ai_dispatch_call(
                "geminirest",
                user_input,
                model_id=model_id,
                system_instruction=system_instruction,
            )
    return response


def _strip_outer_code_fence(text: str) -> str:
    """Remove outer ```json / ```markdown / ```html fences if present."""
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    return cleaned.strip()


def _extract_json_payload(raw_text: str) -> Any:
    """Parse JSON object or array from model output, tolerating prose around fences."""
    cleaned = _strip_outer_code_fence(raw_text)
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    # Try finding first { ... } or [ ... ]
    obj_match = re.search(r"(\{[\s\S]*\})", cleaned)
    if obj_match:
        try:
            return json.loads(obj_match.group(1))
        except Exception:
            pass
    arr_match = re.search(r"(\[[\s\S]*\])", cleaned)
    if arr_match:
        try:
            return json.loads(arr_match.group(1))
        except Exception:
            pass
    return None


def _build_default_4part_nodes(topic: str, booktype_row: Optional[dict] = None, chapter_count: int = 4) -> List[Dict[str, Any]]:
    """Build deterministic 4-part blog post outline nodes when offline or as fallback."""
    T = Registry.F.BookType
    if booktype_row and booktype_row.get(T.booktype_outline_template_list):
        template_nodes = BookTypes.bks_booktypes_outline_nodes(booktype_row, chapter_count)
        if len(template_nodes) == chapter_count:
            out = []
            for idx, node in enumerate(template_nodes, start=1):
                out.append({
                    "title": node.get("title", f"Part {idx}"),
                    "brief": f"{node.get('brief', '')} Focus specifically on: {topic}.".strip(),
                    "kind": node.get("kind", "chapter"),
                    "part": node.get("part"),
                })
            return out

    return [
        {
            "title": "Part 1: Foundations, Context & Problem Statement",
            "brief": f"Establish the core technical problem, architectural motivation, and foundational concepts for {topic}. Define key terms inline on first use and ground the scope.",
            "kind": "chapter",
        },
        {
            "title": "Part 2: Core Architecture, Schema & Structural Invariants",
            "brief": f"Dissect the underlying data structures, schema contracts, state machines, and architectural invariants powering {topic}. Connect directly to the foundations in Part 1.",
            "kind": "chapter",
        },
        {
            "title": "Part 3: Implementation Mechanics & Code Walkthrough",
            "brief": f"Provide a concrete, production-grade implementation walkthrough for {topic} with runnable code examples, data flow traces, and boundary handling.",
            "kind": "chapter",
        },
        {
            "title": "Part 4: Verification, Edge Cases & Operational Takeaways",
            "brief": f"Detail verification gates, edge-case failure modes, performance characteristics, and actionable engineering takeaways for {topic}, concluding with a Summary section.",
            "kind": "chapter",
        },
    ][:chapter_count]


def ai_writing_generate_outline_plan(
    topic: str,
    booktype_row: dict,
    *,
    chapter_count: int = 4,
    provider: str = "geminirest",
    model_id: Optional[str] = None,
    system_instruction: Optional[str] = None,
    context_text: str = "",
    context_bubble_text: str = "",
) -> Dict[str, Any]:
    """
    Generate a BKS-1 outline plan (title, subtitle, and ordered chapter nodes)
    using CLI_AI 48's ai_dispatch_call().
    """
    T = Registry.F.BookType
    plan_inst_template = booktype_row.get(T.booktype_plan_instruction_text) or (
        "Produce a title, a subtitle and an ordered outline of {chapter_count} parts/chapters."
    )
    plan_inst = plan_inst_template.replace("{chapter_count}", str(chapter_count))
    identity_inst = booktype_row.get(T.booktype_chapter_identity_text) or "You are a senior technical author."

    sys_prompt_parts = [
        AUTHOR_PRECEDENCE_DIRECTIVE,
        identity_inst,
        plan_inst,
        (
            "Return ONLY valid JSON with this exact structure:\n"
            '{\n'
            '  "title": "Compelling Technical Title",\n'
            '  "subtitle": "Concise Subtitle",\n'
            '  "chapters": [\n'
            '    {"title": "Part 1: ...", "brief": "2-4 sentence detailed writing brief...", "kind": "chapter"}\n'
            '  ]\n'
            '}'
        ),
    ]
    if system_instruction:
        sys_prompt_parts.insert(1, f"Author Directives:\n{system_instruction}")
    full_sys_prompt = "\n\n".join(p for p in sys_prompt_parts if p)

    user_prompt_sections = []
    if context_bubble_text and context_bubble_text.strip():
        user_prompt_sections.append(context_bubble_text.strip())
    user_prompt_sections.append(f"Topic / Goal: {topic}\nRequired Part/Chapter Count: {chapter_count}")
    if context_text and context_text.strip():
        user_prompt_sections.append(f"Reference Context:\n{context_text[:12000]}")
    user_prompt = "\n\n".join(user_prompt_sections) + "\n"

    # Enforce combined prompt and bubble allotment ceiling (48,000 tokens / 192,000 chars)
    if len(full_sys_prompt) + len(user_prompt) > MAX_COMBINED_PROMPT_CHARS:
        excess = (len(full_sys_prompt) + len(user_prompt)) - MAX_COMBINED_PROMPT_CHARS + 500
        if context_bubble_text and len(context_bubble_text) > excess:
            trimmed_bubble = context_bubble_text[:-excess] + "\n[...truncated: over 48,000 combined token ceiling]"
            user_prompt_sections[0] = trimmed_bubble
            user_prompt = "\n\n".join(user_prompt_sections) + "\n"

    resp = ai_writing_call(
        user_prompt,
        provider=provider,
        model_id=model_id,
        system_instruction=full_sys_prompt,
    )

    if resp.get("success") and resp.get("content"):
        parsed = _extract_json_payload(resp["content"])
        raw_chapters = None
        gen_title = None
        gen_subtitle = None
        if isinstance(parsed, dict):
            gen_title = parsed.get("title")
            gen_subtitle = parsed.get("subtitle")
            raw_chapters = parsed.get("chapters") or parsed.get("tasks") or parsed.get("parts")
        elif isinstance(parsed, list):
            raw_chapters = parsed

        if isinstance(raw_chapters, list) and len(raw_chapters) > 0:
            nodes: List[Dict[str, Any]] = []
            for idx, item in enumerate(raw_chapters[:chapter_count], start=1):
                if isinstance(item, dict):
                    c_title = str(item.get("title") or item.get("task_name") or f"Part {idx}").strip()
                    c_brief = str(item.get("brief") or item.get("prompt") or item.get("task_description") or c_title).strip()
                    c_kind = str(item.get("kind") or "chapter").strip()
                    if c_kind not in ("front", "chapter", "section", "back"):
                        c_kind = "chapter"
                    node_entry: Dict[str, Any] = {"title": c_title, "brief": c_brief, "kind": c_kind}
                    if item.get("part"):
                        node_entry["part"] = str(item["part"]).strip()
                    nodes.append(node_entry)
            if nodes:
                # Pad if fewer than chapter_count returned
                default_nodes = _build_default_4part_nodes(topic, booktype_row, chapter_count)
                while len(nodes) < chapter_count:
                    nodes.append(default_nodes[len(nodes)])
                return {
                    "ok": True,
                    "ai_generated": True,
                    "provider": resp.get("provider", provider),
                    "model_id": resp.get("model_id", model_id),
                    "title": (gen_title or topic).strip(),
                    "subtitle": (gen_subtitle or "").strip() or None,
                    "nodes": nodes,
                    "error": None,
                }

    # Deterministic fallback outline using the BookType template + topic
    fallback_nodes = _build_default_4part_nodes(topic, booktype_row, chapter_count)
    return {
        "ok": True,
        "ai_generated": False,
        "provider": resp.get("provider", provider),
        "model_id": resp.get("model_id", model_id),
        "title": topic.strip()[:120] or "Untitled Technical Post",
        "subtitle": None,
        "nodes": fallback_nodes,
        "error": resp.get("error"),
    }


def ai_writing_assemble_chapter_prompt(
    book_doc: dict,
    chapter_uuid: str,
    booktype_row: dict,
    *,
    author_system_instruction: Optional[str] = None,
    extra_context: str = "",
    context_bubble_text: str = "",
) -> Tuple[str, str, str]:
    """
    Assemble (system_instruction, user_prompt, prompt_sha256) for a single BKS-1
    writable chapter, enforcing Contextualize_Plan, Contextualize_Last, and
    pre-prompt Context Bubble injection.
    """
    B = Registry.F.Book
    C = Registry.F.Chapter
    T = Registry.F.BookType

    book = Store.bks_store_book(book_doc)
    chapters = Store.bks_store_chapters(book_doc)
    writable = [c for c in chapters if Store.bks_store_is_writable(c)]
    by_id = {c[C.chapter_uuid]: c for c in chapters}

    target_ch = by_id.get(chapter_uuid)
    if target_ch is None:
        raise ValueError(f"Chapter {chapter_uuid} not found in Book Document")

    min_words = booktype_row.get(T.booktype_min_words_per_chapter_count) or 250
    required_sections = booktype_row.get(T.booktype_required_sections_list) or []
    identity_text = booktype_row.get(T.booktype_chapter_identity_text) or (
        "You are a senior technical collaborator writing a deep, rigorous technical publication."
    )

    sys_parts = [
        AUTHOR_PRECEDENCE_DIRECTIVE,
    ]
    if author_system_instruction and author_system_instruction.strip():
        sys_parts.append(f"Author Directives:\n{author_system_instruction.strip()}")
    sys_parts.append(identity_text)
    sys_parts.append(
        "Formatting Rules:\n"
        "- Output clean Markdown ONLY (do not wrap the entire response in outer ```markdown fences).\n"
        "- Use semantic headings (##, ###), GFM tables, fenced code blocks with language tags, and GitHub-style callouts (> [!NOTE], > [!TIP], > [!IMPORTANT]).\n"
        "- Zero filler, zero 'lorem ipsum', zero TODO/TBD placeholders.\n"
        f"- Minimum target length for this part: at least {min_words} words."
    )
    if required_sections:
        req_str = ", ".join(f"'## {s}'" for s in required_sections)
        sys_parts.append(f"- You MUST include the following section heading(s) in this part: {req_str}.")
    system_instruction = "\n\n".join(sys_parts)

    # 1. Job_Goal & Plan Contextualization (Contextualize_Plan = True)
    job_goal = Plan.bks_plan_job_goal(book)
    plan_lines = []
    prev_writable: Optional[dict] = None
    target_pos = 1
    for idx, wch in enumerate(writable, start=1):
        marker = "--> [ACTIVE PART]" if wch[C.chapter_uuid] == chapter_uuid else "   "
        plan_lines.append(f"{marker} Part {idx}: {wch[C.chapter_title_text]} — {wch[C.chapter_brief_text] or ''}")
        if wch[C.chapter_uuid] == chapter_uuid:
            target_pos = idx
            if idx > 1:
                prev_writable = writable[idx - 2]

    prompt_sections = []
    if context_bubble_text and context_bubble_text.strip():
        prompt_sections.append(context_bubble_text.strip())

    prompt_sections.extend([
        f"GLOBAL GOAL:\n{job_goal}",
        "FULL 4-PART PUBLICATION PLAN (Contextualize_Plan):\n" + "\n".join(plan_lines),
    ])

    # 2. Previous Part Output Pipelining (Contextualize_Last = True)
    if prev_writable and prev_writable.get(C.chapter_body_md):
        prev_body = prev_writable[C.chapter_body_md]
        prompt_sections.append(
            f"PREVIOUS PART OUTPUT (Part {target_pos - 1}: {prev_writable[C.chapter_title_text]}) "
            f"[Contextualize_Last — maintain seamless technical continuity without repeating]:\n"
            f"---\n{prev_body[-6000:]}\n---"
        )

    # 3. Extra Context / Embedded Chunks
    if extra_context and extra_context.strip():
        prompt_sections.append(f"REFERENCE CONTEXT:\n{extra_context[:10000]}")

    # 4. Active Task Instructions
    task_desc = Plan.bks_plan_task_description(target_ch, by_id, min_words)
    prompt_sections.append(
        f"ACTIVE TASK — Write Part {target_pos} of {len(writable)}: \"{target_ch[C.chapter_title_text]}\"\n"
        f"Brief & Instructions:\n{task_desc}\n\n"
        f"Write the complete Markdown content for \"{target_ch[C.chapter_title_text]}\" now:"
    )

    user_prompt = "\n\n".join(prompt_sections)

    # Enforce combined prompt and bubble allotment ceiling (48,000 tokens / 192,000 chars)
    if len(system_instruction) + len(user_prompt) > MAX_COMBINED_PROMPT_CHARS:
        excess = (len(system_instruction) + len(user_prompt)) - MAX_COMBINED_PROMPT_CHARS + 500
        if context_bubble_text and len(context_bubble_text) > excess:
            trimmed_bubble = context_bubble_text[:-excess] + "\n[...truncated: over 48,000 combined token ceiling]"
            prompt_sections[0] = trimmed_bubble
            user_prompt = "\n\n".join(prompt_sections)

    combined_for_hash = f"SYS:\n{system_instruction}\n\nUSER:\n{user_prompt}"
    prompt_sha256 = hashlib.sha256(combined_for_hash.encode("utf-8")).hexdigest()
    return system_instruction, user_prompt, prompt_sha256


def ai_writing_generate_chapter(
    book_doc: dict,
    chapter_uuid: str,
    booktype_row: dict,
    *,
    provider: str = "geminirest",
    model_id: Optional[str] = None,
    author_uuid: Optional[str] = None,
    author_system_instruction: Optional[str] = None,
    extra_context: str = "",
    context_bubble_text: str = "",
    min_words_override: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Execute a single BKS-1 chapter generation call via CLI_AI 48's ai_dispatch_call(),
    evaluate the BKS-1 gate in-process, and record the Generation row + chapter state
    into book_doc via bks_store_apply_attempt / bks_store_apply_failure.
    """
    C = Registry.F.Chapter
    T = Registry.F.BookType

    started_at = Derive.bks_derive_now_utc()
    sys_inst, user_prompt, prompt_sha256 = ai_writing_assemble_chapter_prompt(
        book_doc,
        chapter_uuid,
        booktype_row,
        author_system_instruction=author_system_instruction,
        extra_context=extra_context,
        context_bubble_text=context_bubble_text,
    )

    resp = ai_writing_call(
        user_prompt,
        provider=provider,
        model_id=model_id,
        system_instruction=sys_inst,
    )
    finished_at = Derive.bks_derive_now_utc()
    used_provider = resp.get("provider") or provider
    used_model = resp.get("model_id") or model_id

    if not resp.get("success") or not (resp.get("content") or "").strip():
        Store.bks_store_apply_failure(
            book_doc,
            chapter_uuid,
            error_code=539,
            provider=used_provider,
            model=used_model,
            author_uuid=author_uuid,
            now=finished_at,
            outcome="failed",
        )
        return {
            "ok": False,
            "passed": False,
            "reason": resp.get("error") or "Empty response from AI provider",
            "body_md": None,
            "word_count": 0,
            "provider": used_provider,
            "model_id": used_model,
            "chapter_uuid": chapter_uuid,
        }

    cleaned_md = _strip_outer_code_fence(resp["content"])

    # Determine gate rules from BookType (allowing optional min_words_override)
    gate_rules = BookTypes.bks_booktypes_gate_rules(booktype_row)
    if gate_rules and min_words_override is not None:
        gate_rules = dict(gate_rules)
        gate_rules["min_words"] = int(min_words_override)

    passed, reason = Store.bks_store_apply_attempt(
        book_doc,
        chapter_uuid,
        cleaned_md,
        rules=gate_rules,
        provider=used_provider,
        model=used_model,
        author_uuid=author_uuid,
        prompt_sha256=prompt_sha256,
        started_at=started_at,
        now=finished_at,
    )

    # Read updated chapter state
    chapters = {c[C.chapter_uuid]: c for c in Store.bks_store_chapters(book_doc)}
    updated_ch = chapters.get(chapter_uuid, {})

    return {
        "ok": True,
        "passed": passed,
        "reason": reason,
        "body_md": updated_ch.get(C.chapter_body_md) or cleaned_md,
        "word_count": updated_ch.get(C.chapter_word_count, Derive.bks_derive_count_words(cleaned_md)),
        "status": updated_ch.get(C.chapter_status_text),
        "provider": used_provider,
        "model_id": used_model,
        "chapter_uuid": chapter_uuid,
        "chapter_title": updated_ch.get(C.chapter_title_text),
    }
