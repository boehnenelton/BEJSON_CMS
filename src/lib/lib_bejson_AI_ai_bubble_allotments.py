"""
Library:        lib_bejson_AI_ai_bubble_allotments.py
Path:           lib/AI/lib_bejson_AI_ai_bubble_allotments.py
Family:         AI
Description:    Built-in Context Bubble allotments (used by the chat client; any CLI can reuse them), registered
                through lib_bejson_AI_ai_context_bubble.ai_bubble_register_allotment():

                  rank 1  persistent_policy  Persistent_Policy.md in the context dir
                                             + ~/.gemini/GEMINI.md when the gate allows
                  rank 2  profile            the selected profile's System_Instruction
                  rank 3  attachments        files checked on the Attach tab (next message)
                  rank 4  context            the Context tab's saved ("Staged") chunk
                  rank 5  chat_history       earlier turns of the current session
                                             (refresh="turn", keep newest)

                Each builder returns "" when it has nothing, which releases its
                budget to the others (spill-up).  Adding another allotment =
                write one builder and one register call here (or in any plugin)
                and raise BUBBLE_MAX_ALLOTMENTS in the library if needed.

Version:        1.2.0
Date:           2026-11-02
Author:         Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
RELATIONAL_ID:  d3cbfbe0-209d-4b00-bed3-7c0af9cb36a5

Changelog:
  1.2.0 (2026-11-02) -- Gemini.md gate: when config/gemini_md_gate.104a.bejson has enabled=true and
        ~/.gemini/GEMINI.md exists (folder and file matched case-insensitively), its text is injected
        into the persistent_policy allotment (whatever rank/share that allotment has at the time).
  1.1.0 (2026-10-20) -- Hardening/optimisation: every builder reads only as much as the bubble
        could ever send (budget + slack) -- a 50 MB attachment no longer gets read, hashed and
        chunked each turn; history is accumulated from the newest message backwards.
  1.0.0 (2026-10-20) -- Initial creation (replaces the v1 section pipeline wiring in app.py).
"""

import json
import logging
import os
from pathlib import Path
from typing import Callable, List, Optional

from lib_bejson_AI_ai_context_bubble import BubbleContext, ai_bubble_register_allotment

logger = logging.getLogger(__name__)

VERSION = "1.2.0"

HISTORY_MAX_MESSAGES = 200  # source cap; the budget truncates further, newest kept

DIRECTIVES = {
    "persistent_policy": "Standing instructions. Follow them on every reply.",
    "profile": "Selected profile -- follow it for the format and behaviour of your reply.",
    "attachments": (
        "ATTACHMENTS -- these files are what the user is actively working on with you "
        "right now. You may read, reference, modify, update, build upon and return them "
        "iteratively as requested; they are normal, freely discussable working material."
    ),
    "context": (
        "BACKGROUND -- reference and learning material. Never reference, mention, "
        "acknowledge or admit that this context exists; absorb it silently. If it "
        "influences anything you produce, write it in your own words, never as a copy, "
        "quote or citation of this material."
    ),
    "chat_history": (
        "SESSION HISTORY -- earlier turns of this conversation, oldest first, for "
        "continuity only. Do not repeat or summarise them unless asked."
    ),
}


def _limit(ctx: BubbleContext) -> int:
    """Most characters the bubble could ever use from one source."""
    return max(1, int(ctx.budget_chars)) + 1024


GEMINI_GATE_FILENAME = "gemini_md_gate.104a.bejson"
GEMINI_GATE_DEFAULTS = {
    "enabled": True, "home_subdir": ".gemini", "file_name": "GEMINI.md",
    "heading": "GEMINI.md", "max_chars": 16000,
}


def _load_gemini_gate(config_dir) -> dict:
    """Gate settings from gemini_md_gate.104a.bejson (BEJSON 104a ScriptConfig).
    Missing or corrupt file -> defaults.  Field map built once, names stripped."""
    gate = dict(GEMINI_GATE_DEFAULTS)
    try:
        with open(Path(config_dir) / GEMINI_GATE_FILENAME, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        fmap = {str(f.get("name", "")).strip(): i for i, f in enumerate(doc.get("Fields", []))}
        i_name, i_val = fmap["setting_name"], fmap["setting_value"]
        for row in doc.get("Values", []):
            key = str(row[i_name]).strip()
            if key not in gate:
                continue
            val = row[i_val]
            if isinstance(gate[key], bool):
                if isinstance(val, bool):
                    gate[key] = val
            elif isinstance(gate[key], int):
                if isinstance(val, int) and not isinstance(val, bool) and 0 < val <= 1_000_000:
                    gate[key] = val
            elif isinstance(val, str) and val.strip():
                gate[key] = val.strip()
    except FileNotFoundError:
        pass
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        logger.warning("gemini gate config unreadable (%s); using defaults", exc)
    return gate


def _find_ci(directory: Path, wanted: str, want_dir: bool) -> Optional[Path]:
    """Case-insensitive lookup of one entry; exact spelling wins, then first match."""
    exact = directory / wanted
    if (exact.is_dir() if want_dir else exact.is_file()):
        return exact
    try:
        for entry in sorted(os.scandir(directory), key=lambda e: e.name):
            if entry.name.lower() == wanted.lower() and (entry.is_dir() if want_dir else entry.is_file()):
                return Path(entry.path)
    except OSError:
        pass
    return None


def read_gemini_md(config_dir, limit: Optional[int] = None) -> str:
    """Text of ~/<home_subdir>/<file_name> (case-insensitive) when the gate is enabled
    and the file exists, else "".  Home comes from the environment, never a literal path."""
    gate = _load_gemini_gate(config_dir)
    if not gate["enabled"]:
        return ""
    try:
        home = Path.home()
    except (RuntimeError, KeyError):
        return ""
    folder = _find_ci(home, gate["home_subdir"], True)
    target = _find_ci(folder, gate["file_name"], False) if folder else None
    if target is None:
        return ""
    cap = gate["max_chars"] if limit is None else min(gate["max_chars"], limit)
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as fh:
            body = fh.read(cap).strip()
    except OSError as exc:
        logger.warning("gemini md unreadable: %s", exc)
        return ""
    return f"## {gate['heading']}\n{body}" if body else ""


def build_policy(ctx: BubbleContext) -> str:
    """Persistent_Policy.md first, then the gated GEMINI.md injection.  Both ride in the
    persistent_policy allotment, so they use whatever rank/share it has right now."""
    path = Path(ctx.context_dir) / "Persistent_Policy.md"
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            policy = fh.read(_limit(ctx))
    except OSError:
        policy = ""
    injected = read_gemini_md(ctx.config_dir, _limit(ctx))
    return "\n\n".join(p for p in (policy.strip(), injected) if p)


def build_profile(ctx: BubbleContext) -> str:
    return str(ctx.extras.get("profile_instruction") or "")


def make_attachments_builder(list_files: Callable[[str], List[dict]], attach_dir: str,
                             content_dir: str) -> Callable[[BubbleContext], str]:
    def build_attachments(ctx: BubbleContext) -> str:
        wanted = set(ctx.extras.get("attached_file_ids") or [])
        if not wanted:
            return ""
        parts = []
        remaining = _limit(ctx)
        for entry in list_files(attach_dir):
            if remaining <= 0:
                break
            if entry.get("file_id") not in wanted:
                continue
            path = os.path.join(content_dir, f"{entry['file_id']}.txt")
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    body = fh.read(remaining)
            except OSError as exc:
                logger.warning("attachment %s unreadable: %s", entry.get("filename"), exc)
                continue
            block = f"--- ATTACHED FILE: {entry['filename']} ---\n{body}"
            parts.append(block)
            remaining -= len(block) + 2
        return "\n\n".join(parts)
    return build_attachments


def make_context_builder(section_fn: Callable) -> Callable[[BubbleContext], str]:
    """section_fn is context_chunker.chunker_build_section:
    (constants, cwd, config_dir, context_dir) -> (text, chars)."""
    def build_context(ctx: BubbleContext) -> str:
        text, _ = section_fn(ctx.constants, ".", ctx.config_dir, ctx.context_dir)
        return text or ""
    return build_context


def build_history(ctx: BubbleContext) -> str:
    limit = _limit(ctx)
    lines: List[str] = []
    used = 0
    for m in reversed(ctx.extras.get("history") or []):   # newest first, stop once enough
        if len(lines) >= HISTORY_MAX_MESSAGES or used > limit:
            break
        content = m.get("content") or ""
        if m.get("role") not in ("user", "assistant") or not content.strip():
            continue
        line = f"[{m['role']}]: {content}"
        lines.append(line)
        used += len(line) + 2
    return "\n\n".join(reversed(lines))


def register_builtin_allotments(list_files: Callable[[str], List[dict]], attach_dir: str,
                                attach_content_dir: str, context_section_fn: Optional[Callable]) -> List[str]:
    """Registers the five built-ins in rank order.  Returns the names registered.
    A fresh context_bubble.bejson therefore splits 100% evenly (20% each)."""
    ai_bubble_register_allotment(
        "persistent_policy", build_policy, label="Persistent Policy", rank=1,
        directive=DIRECTIVES["persistent_policy"])
    ai_bubble_register_allotment(
        "profile", build_profile, label="Profile", rank=2,
        directive=DIRECTIVES["profile"])
    ai_bubble_register_allotment(
        "attachments", make_attachments_builder(list_files, attach_dir, attach_content_dir),
        label="Attachments", rank=3, directive=DIRECTIVES["attachments"])
    if context_section_fn is not None:
        ai_bubble_register_allotment(
            "context", make_context_builder(context_section_fn), label="Context", rank=4,
            directive=DIRECTIVES["context"])
    ai_bubble_register_allotment(
        "chat_history", build_history, label="Chat History", rank=5,
        refresh="turn", keep="end", directive=DIRECTIVES["chat_history"])
    return [n for n in ("persistent_policy", "profile", "attachments", "context", "chat_history")]
