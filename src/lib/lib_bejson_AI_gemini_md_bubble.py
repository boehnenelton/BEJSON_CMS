"""
Library:         lib_bejson_AI_gemini_md_bubble.py
Family:          AI
Module Purpose:  Plugs the GEMINI.md policy file into the Context Bubble as one allotment that takes a fixed share (default 40 percent) of the token budget off the top and automatically rescales every other allotment to share the remainder.
Architecture:    Uses the bubble plugin hook ai_bubble_register_allotment (slot 8 of 8). The gate (lib_bejson_AI_gemini_md_gate) decides activity; gemini_md_bubble_sync() rewrites only the pct, rank and enabled cells of context_bubble.bejson through Core atomic writes, remembering the user's baseline in the gate file so that turning the switch off, or removing the file, restores the previous split exactly. Ratios between the other allotments are preserved. No existing library is modified.
Version:         1.0.0
Release_Version: 300
Date:            2026-10-29
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   1663e02c-5129-4b7a-a53d-2fd04aedcd03
"""

import logging
from pathlib import Path

from lib_bejson_AI_gemini_md_gate import (
    gemini_md_gate_read_text, gemini_md_gate_state_get, gemini_md_gate_state_set, gemini_md_gate_status,
)
from lib_bejson_AI_ai_context_bubble import (
    BubbleContext, REFRESH_STABLE, ai_bubble_config_init, ai_bubble_register_allotment,
)
from lib_bejson_Core_bejson_core import bejson_core_atomic_write, bejson_core_get_field_map, bejson_core_load_file

try:
    from lib_bejson_AI_ai_constants import ai_constants_init, ai_constants_load
except ImportError:  # budget figures in the status fall back to the bubble defaults
    ai_constants_init = ai_constants_load = None

VERSION = "1.0.0"
RELATIONAL_ID = "1663e02c-5129-4b7a-a53d-2fd04aedcd03"
_LOGGER = logging.getLogger("gemini_md.bubble")

ALLOTMENT_NAME = "gemini_md"
BUBBLE_CONFIG_FILENAME = "context_bubble.bejson"
TOP_RANK = 1                     # "off the top": highest rank, so it is built and spilled-to first
FALLBACK_MAX_TOKENS, FALLBACK_CHARS_PER_TOKEN = 8000, 4
_PCT_TOLERANCE = 0.01

DIRECTIVE = ("GEMINI.MD -- the user's standing policy file (the contents of their GEMINI.md), included because the user switched it on in this client. "
             "Apply its conventions, tone and coding standards to your replies. Anything in it about session-start maintenance, job folders, "
             "archiving, editing files or running commands is for command-line agents with filesystem access; you have none here, so do not "
             "claim to perform those steps.")


# Builder for the allotment: the file text while the gate is active, otherwise an empty string (the budget then spills to the others).
def _make_builder(config_dir: Path):
    def build_gemini_md(ctx: BubbleContext) -> str:
        status = gemini_md_gate_status(config_dir)
        return gemini_md_gate_read_text(status["file_path"]) if status["active"] else ""
    return build_gemini_md


# Registers the allotment. Call BEFORE ai_bubble_init. Returns False when the bubble has no free slot.
def gemini_md_bubble_register(config_dir) -> bool:
    registered = ai_bubble_register_allotment(
        ALLOTMENT_NAME, _make_builder(Path(config_dir)), label="GEMINI.md", pct=0.0, rank=TOP_RANK, enabled=False,
        refresh=REFRESH_STABLE, directive=DIRECTIVE)
    if not registered:
        _LOGGER.error("GEMINI.md allotment could not be registered (bubble slot limit reached?).")
    return registered


# Pure: returns (pct_by_name, rank_by_name) for the other allotments while GEMINI.md holds `take_pct` off the top.
def gemini_md_bubble_plan(base_pcts: dict, base_ranks: dict, take_pct: float) -> tuple:
    remaining_pct = max(0.0, 100.0 - take_pct)
    base_sum = sum(base_pcts.values())
    scaled = {name: (round(value * remaining_pct / base_sum, 4) if base_sum > 0 else 0.0) for name, value in base_pcts.items()}
    ordered = sorted(base_pcts, key=lambda name: (base_ranks.get(name, 99), name))
    return scaled, {name: TOP_RANK + 1 + position for position, name in enumerate(ordered)}


# Brings context_bubble.bejson in line with the gate. Idempotent and cheap; writes only when a cell must change. Returns the gate status dict plus "applied".
def gemini_md_bubble_sync(config_dir) -> dict:
    config_dir = Path(config_dir)
    status = gemini_md_gate_status(config_dir)
    status["applied"] = False
    try:
        bubble_path = ai_bubble_config_init(config_dir)
        document = bejson_core_load_file(str(bubble_path))
        field_map = bejson_core_get_field_map(document)
        rows = document["Values"]
        name_idx, rank_idx, pct_idx, enabled_idx = field_map["name"], field_map["rank"], field_map["pct"], field_map["enabled"]
        own_row = next((row for row in rows if str(row[name_idx]).strip() == ALLOTMENT_NAME), None)
        if own_row is None:
            return status
        other_rows = [row for row in rows if row is not own_row]
        base_pcts = gemini_md_gate_state_get(config_dir, "sync_base_pcts")
        base_ranks = gemini_md_gate_state_get(config_dir, "sync_base_ranks")
        applied_pcts = gemini_md_gate_state_get(config_dir, "sync_applied_pcts")
        changed = False

        def put(row, idx, value):
            nonlocal changed
            if isinstance(value, float) and isinstance(row[idx], (int, float)) and abs(row[idx] - value) <= _PCT_TOLERANCE:
                return
            if row[idx] != value:
                row[idx] = value
                changed = True

        if status["active"]:
            current = {str(row[name_idx]).strip(): float(row[pct_idx]) for row in other_rows}
            if applied_pcts:
                drifted = any(abs(current.get(name, 0.0) - value) > _PCT_TOLERANCE for name, value in applied_pcts.items()) or set(current) != set(applied_pcts)
                if drifted:                                   # the user edited the split while active: keep their ratios as the new baseline
                    scale = (sum(base_pcts.values()) / sum(applied_pcts.values())) if sum(applied_pcts.values()) > 0 else 1.0
                    base_pcts = {name: value * scale for name, value in current.items()}
                    base_ranks = {str(row[name_idx]).strip(): int(row[rank_idx]) for row in other_rows}
            else:
                base_pcts = current
                base_ranks = {str(row[name_idx]).strip(): int(row[rank_idx]) for row in other_rows}
            scaled_pcts, new_ranks = gemini_md_bubble_plan(base_pcts, base_ranks, status["budget_pct"])
            for row in other_rows:
                row_name = str(row[name_idx]).strip()
                put(row, pct_idx, float(scaled_pcts[row_name]))
                put(row, rank_idx, new_ranks[row_name])
            put(own_row, pct_idx, float(status["budget_pct"]))
            put(own_row, rank_idx, TOP_RANK)
            put(own_row, enabled_idx, True)
            if changed:
                bejson_core_atomic_write(str(bubble_path), document)
            gemini_md_gate_state_set(config_dir, "sync_base_pcts", base_pcts)
            gemini_md_gate_state_set(config_dir, "sync_base_ranks", base_ranks)
            gemini_md_gate_state_set(config_dir, "sync_applied_pcts", scaled_pcts)
            status["applied"] = True
        else:
            if applied_pcts:                                  # restore the baseline captured before GEMINI.md took its share
                for row in other_rows:
                    row_name = str(row[name_idx]).strip()
                    if row_name in base_pcts:
                        put(row, pct_idx, float(base_pcts[row_name]))
                    if row_name in base_ranks:
                        put(row, rank_idx, int(base_ranks[row_name]))
            put(own_row, pct_idx, 0.0)
            put(own_row, enabled_idx, False)
            if changed:
                bejson_core_atomic_write(str(bubble_path), document)
            if applied_pcts:
                for state_key in ("sync_base_pcts", "sync_base_ranks", "sync_applied_pcts"):
                    gemini_md_gate_state_set(config_dir, state_key, {})
    except (OSError, KeyError, ValueError, TypeError) as sync_error:
        _LOGGER.error("GEMINI.md bubble sync failed: %s", sync_error)
        status["error"] = str(sync_error)
    return status


# Token-budget facts for the UI: estimated size of the file against the share it is given.
def gemini_md_bubble_budget(config_dir, status: dict) -> dict:
    max_tokens, chars_per_token = FALLBACK_MAX_TOKENS, FALLBACK_CHARS_PER_TOKEN
    if ai_constants_load is not None:
        try:
            ai_constants_init(Path(config_dir))
            constants = ai_constants_load(Path(config_dir))
            max_tokens = max(1, int(constants.get("max_context_tokens", max_tokens)))
            chars_per_token = max(1, int(constants.get("chars_per_token", chars_per_token)))
        except (OSError, ValueError, TypeError) as constants_error:
            _LOGGER.warning("ai_constants unavailable (%s); using defaults.", constants_error)
    share_tokens = int(max_tokens * status["budget_pct"] / 100.0)
    file_tokens = -(-status["file_chars"] // chars_per_token)
    return {"max_context_tokens": max_tokens, "share_tokens": share_tokens, "file_tokens_est": file_tokens,
            "truncated": status["active"] and file_tokens > share_tokens}
