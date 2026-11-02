"""
Library:        lib_bejson_AI_ai_context_bubble.py
Path:           lib/AI/lib_bejson_AI_ai_context_bubble.py
Family:         AI
Description:    Context Bubble engine v2 -- ranked allotments with percentage
                budgets and spill-up.  Rebuilt from the ground up (v1 was a
                fixed seven-section percentage splitter).

                MODEL
                  * An ALLOTMENT is one named source of context (persistent
                    policy, profile, attachments, context, chat history, or
                    anything a plugin registers).  Each has a rank (1 =
                    highest), a baseline budget (percent of the outgoing
                    token budget), and a builder function.
                  * Allotments are listed in config/context_bubble.bejson
                    (BEJSON 104a).  Edits apply on the next turn.  A freshly
                    created file splits 100% evenly across the registered
                    allotments.
                  * SPILL-UP: budget an allotment does not use is released.
                    Over-budget allotments claim it in rank order (rank 1
                    first).  Each claimant draws EVENLY from all donors.  The
                    moment a donor needs its own share again it stops
                    donating and the claimant shrinks back toward baseline.
                    Percent left unassigned is part of the pool.
                  * Anything still over its grant is truncated, with a
                    visible marker.  An allotment with keep="end" (chat
                    history) keeps its newest content.
                  * CHUNKING: every allotment is chunked (Chunked-104a, via
                    the frozen Core chunking lib) into <context_dir>/bubble/
                    allotments/; the whole bubble directory is then chunked
                    again into <context_dir>/Context_Bubble.104a.bejson.  The
                    prompt payload is rendered FROM that bubble chunk after
                    every SHA-256 File_Hash is verified at both levels.
                  * LIFECYCLE: the bubble persists between turns.  It is
                    destroyed and rebuilt every Rebuild_Interval_Turns turns
                    (default 5) OR immediately when a stable allotment's
                    content changes (attachment set, context save, policy,
                    profile, config edit); a rebuild resets the counter.
                    Allotments with refresh="turn" (chat history) change by
                    nature, so they are re-chunked in place every turn and
                    never trigger or reset the counter.
                  * GROWTH: raise BUBBLE_MAX_ALLOTMENTS and call
                    ai_bubble_register_allotment() from any plugin/module.

                Builder contract:  fn(ctx: BubbleContext) -> str
                Return "" to contribute nothing this turn (its budget spills).

                Removed from v1 (nothing replaces them yet): cwd context.bejson,
                active-task checklists, env drip, keyword triggers, knowledge
                pool, ai_bubble_register_section/assemble.  The amnesia /
                compression helpers are carried over unchanged at the bottom.

Version:        2.2.0
Date:           2026-11-01
Author:         Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
RELATIONAL_ID:  2de45989-c5ac-499d-ada9-7378ff3f2508
Release_Version: 300

Changelog:
  2.2.0 (2026-11-01) -- Feature switching + visibility:
        * Enabled allotments' baselines are NORMALISED to 100% of the window
          (header Normalize_Baselines, default true): switching a feature off hands
          its share back to the others in proportion to their weights, switching it
          on takes it again.  false = v2.1 behaviour (even cut only when over 100).
        * ai_bubble_config_update(): validated, atomic enable/weight edits.
        * Registration takes an optional group=; names sharing a first token
          (brain_pinned, brain_recall) are grouped automatically.
        * ai_bubble_preview() now also returns the full catalog (disabled and
          unavailable rows too), per-allotment text and the effective share.
  2.1.0 (2026-10-20) -- Audit / hardening / optimisation pass:
        * Non-finite or out-of-range pct/rank/interval in context_bubble.bejson no
          longer crash (clamped / defaulted); a corrupt config runs on the registered
          defaults in memory instead of silently producing an empty bubble.
        * State file values are type-checked (a hand-edited "turn": "x" crashed).
        * An allotment missing or stale in the bubble chunk is now an integrity failure
          (destroy + rebuild once) instead of being silently dropped on reuse turns.
        * ai_bubble_prepare() never loses policy/attachments to a disk/state problem:
          any build failure falls back to an unchunked in-memory bubble, then to
          policy-only.  The next turn recovers on its own.
        * Wrapper markers inside content are defanged ([END CONTEXT BUBBLE] spoofing).
        * Sources are capped at budget + 1 KB before chunking/hashing: a 26 MB
          attachment used to write a 24.6 MB bubble and cost ~300 ms per rebuild /
          ~100 ms per turn; now ~216 KB and ~39 ms / ~18 ms.
        * An allotment too small to hold its header + a useful slice is dropped and
          its grant re-spilled to the others.
        * Registry mutations are locked; warn-once for the allotment-cap warning.
  2.0.0 (2026-10-20) -- Ground-up rebuild: ranked allotments, spill-up with
        even donor draw, per-allotment + whole-bubble Chunked-104a chunking
        with hash verification, 5-turn / change-triggered rebuild,
        context_bubble.bejson config, BUBBLE_MAX_ALLOTMENTS + register hook.
  1.0.1 (2026-08-13) -- (v1) chars_per_token guard; knowledge-pool schema dedupe.
  1.0.0 (2026-08-12) -- (v1) initial provider-agnostic bubble.
"""

import hashlib
import json
import logging
import math
import os
import re
import shutil
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

VERSION = "2.2.0"

logger = logging.getLogger(__name__)

# ── Sibling resolution ────────────────────────────────────────────────────────

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_CORE_DIR = os.path.join(os.path.dirname(_LIB_DIR), "Core")
for _p in (_LIB_DIR, _CORE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib_bejson_Core_bejson_core import (
    bejson_core_atomic_write,
    bejson_core_get_field_map,
    bejson_core_load_file,
)
from lib_bejson_Core_bejson_chunking import (
    bejson_core_chunking_bump_package_version,
    bejson_core_chunking_create_chunked_104,
    bejson_core_chunking_hash_file_bytes,
)

try:
    from lib_bejson_AI_ai_constants import ai_constants_init, ai_constants_load
    _CONSTANTS_AVAILABLE = True
except ImportError:  # degrade to hardcoded defaults
    _CONSTANTS_AVAILABLE = False
    logger.warning("[AIContextBubble] ai_constants not found; using built-in defaults.")

# ── Declared constants ────────────────────────────────────────────────────────

# Hard ceiling on active allotments.  Raise this one number to allow more.
BUBBLE_MAX_ALLOTMENTS = 8

DEFAULT_REBUILD_INTERVAL_TURNS = 5
DEFAULT_MAX_CONTEXT_TOKENS = 8000
DEFAULT_CHARS_PER_TOKEN = 4

CONFIG_FILENAME = "context_bubble.bejson"
BUBBLE_DIRNAME = "bubble"
ALLOTMENTS_SUBDIR = "allotments"
STAGE_SUBDIR = "_stage"
BUBBLE_CHUNK_FILENAME = "Context_Bubble.104a.bejson"
STATE_FILENAME = "bubble_state.json"
_POLICY_FILENAME = "Persistent_Policy.md"
_AMNESIA_FILENAME = "amnesia_recap.txt"

REFRESH_STABLE = "stable"   # change => rebuild + counter reset
REFRESH_TURN = "turn"       # re-chunked every turn, never triggers rebuild
KEEP_START = "start"
KEEP_END = "end"

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_UNASSIGNED = "(unassigned)"
_MIN_USEFUL_CHARS = 40
_SOURCE_SLACK_CHARS = 1024     # source cap = budget + slack, so over-budget sources always render as truncated
_MAX_RANK = 1_000_000
_MAX_INTERVAL = 1_000_000
_TRUNC_MARK_TAIL = "\n[...truncated: over allotment budget]"
_TRUNC_MARK_HEAD = "[...earlier content truncated: over allotment budget]\n"
_WRAP_OPEN = "[CONTEXT BUBBLE]\n"
_WRAP_CLOSE = "\n[END CONTEXT BUBBLE]"

_CONFIG_FIELDS = [
    {"name": "name",      "type": "string"},
    {"name": "rank",      "type": "integer"},
    {"name": "pct",       "type": "number"},
    {"name": "enabled",   "type": "boolean"},
    {"name": "refresh",   "type": "string"},
    {"name": "keep",      "type": "string"},
    {"name": "label",     "type": "string"},
    {"name": "directive", "type": "string"},
]

_LOCK = threading.RLock()


class BubbleIntegrityError(Exception):
    """A chunk row's SHA-256 File_Hash did not match its content."""


# ── Plugin hook / registry ────────────────────────────────────────────────────

@dataclass
class BubbleContext:
    """Everything a builder may need.  extras carries caller data
    (attached_file_ids, history, profile_instruction, ...)."""
    user_msg: str
    turn: int
    constants: Dict[str, Any]
    context_dir: Path
    config_dir: Path
    budget_chars: int = 0
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class _Registered:
    name: str
    label: str
    builder: Callable[[BubbleContext], str]
    pct: Optional[float]
    rank: Optional[int]
    enabled: bool
    refresh: str
    keep: str
    directive: str
    group: str = ""


_registry: Dict[str, _Registered] = {}
_warned: set = set()   # warn-once keys (avoids per-turn log spam)


def _warn_once(key: str, msg: str, *args) -> None:
    if key not in _warned:
        _warned.add(key)
        logger.warning(msg, *args)


def ai_bubble_register_allotment(
    name: str,
    builder_fn: Callable[[BubbleContext], str],
    *,
    label: Optional[str] = None,
    pct: Optional[float] = None,
    rank: Optional[int] = None,
    enabled: bool = True,
    refresh: str = REFRESH_STABLE,
    keep: str = KEEP_START,
    directive: str = "",
    group: str = "",
) -> bool:
    """
    Plugin hook.  Registers an allotment.  pct/rank/enabled/... are only
    DEFAULTS used to add a row to context_bubble.bejson the first time the
    name is seen; afterwards the file is authoritative.  A new row added to
    an existing file defaults to pct 0 (it can still claim spill) and the
    next free rank.  Re-registering a name replaces its builder.

    Returns False (and logs) if the name is invalid or the registry is full
    (BUBBLE_MAX_ALLOTMENTS).
    """
    name = (name or "").strip()
    if not _NAME_RE.match(name):
        logger.error("[AIContextBubble] Invalid allotment name %r (use a-z, 0-9, _).", name)
        return False
    if not callable(builder_fn):
        logger.error("[AIContextBubble] Allotment '%s': builder_fn is not callable.", name)
        return False
    with _LOCK:
        if name not in _registry and len(_registry) >= BUBBLE_MAX_ALLOTMENTS:
            logger.error("[AIContextBubble] Cannot register '%s': BUBBLE_MAX_ALLOTMENTS=%d reached.",
                         name, BUBBLE_MAX_ALLOTMENTS)
            return False
        if refresh not in (REFRESH_STABLE, REFRESH_TURN):
            refresh = REFRESH_STABLE
        if keep not in (KEEP_START, KEEP_END):
            keep = KEEP_START
        _registry[name] = _Registered(
            name=name, label=(label or name).strip(), builder=builder_fn, pct=pct,
            rank=rank, enabled=enabled, refresh=refresh, keep=keep,
            directive=(directive or "").strip(), group=_clean_str(group).lower(),
        )
    return True


def ai_bubble_unregister_allotment(name: str) -> bool:
    with _LOCK:
        return _registry.pop(name, None) is not None


def ai_bubble_clear_allotments() -> None:
    """Removes every registered allotment (tests / re-init)."""
    with _LOCK:
        _registry.clear()
        _warned.clear()


def ai_bubble_registered_names() -> List[str]:
    with _LOCK:
        return list(_registry)


# ── Config (context_bubble.bejson) ────────────────────────────────────────────

def _clean_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ("" if value is None else str(value).strip())


def _to_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    if value is None:
        return default
    return bool(value)


def _to_float(value: Any, default: float = 0.0) -> float:
    """Finite float clamped to 0..100 (a percentage); anything else -> default."""
    try:
        v = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(v):
        return default
    return min(100.0, max(0.0, v))


def _to_int(value: Any, default: int, maximum: int = _MAX_RANK) -> int:
    """Integer in 1..maximum; non-numeric, non-finite or < 1 -> default."""
    try:
        f = float(value)
        if not math.isfinite(f):
            return default
        v = int(f)
    except (TypeError, ValueError, OverflowError):
        return default
    return min(maximum, v) if v >= 1 else default


def _row_from_registered(reg: _Registered, pct: float, rank: int) -> list:
    return [reg.name, rank, pct, reg.enabled, reg.refresh, reg.keep, reg.label, reg.directive]


def _config_path(config_dir: Path) -> Path:
    return Path(config_dir) / CONFIG_FILENAME


def _build_config_doc(rows: list, interval: int, normalize: bool = True) -> dict:
    return {
        "Format": "BEJSON",
        "Format_Version": "104a",
        "Format_Creator": "Elton Boehnen",
        "Schema_Name": "ContextBubbleConfig",
        "Schema_Version": "2.0.0",
        "Rebuild_Interval_Turns": interval,
        "Normalize_Baselines": normalize,
        "Records_Type": ["Allotment"],
        "Fields": _CONFIG_FIELDS,
        "Values": rows,
    }


def ai_bubble_config_init(config_dir: Path) -> Path:
    """Creates context_bubble.bejson if absent (even split across the
    currently registered allotments) and appends rows for registered
    allotments missing from an existing file.  Never edits existing rows."""
    config_dir = Path(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    path = _config_path(config_dir)
    regs = list(_registry.values())

    if not path.exists():
        n = len(regs)
        even = round(100.0 / n, 2) if n else 0.0
        used_ranks: set = set()
        rows = []
        for i, reg in enumerate(regs, start=1):
            rank = reg.rank if reg.rank and reg.rank not in used_ranks else i
            while rank in used_ranks:
                rank += 1
            used_ranks.add(rank)
            rows.append(_row_from_registered(reg, reg.pct if reg.pct is not None else even, rank))
        if not bejson_core_atomic_write(str(path), _build_config_doc(rows, DEFAULT_REBUILD_INTERVAL_TURNS)):
            logger.error("[AIContextBubble] Could not write %s", path)
        return path

    doc = bejson_core_load_file(str(path))
    if not isinstance(doc, dict):
        logger.error("[AIContextBubble] %s unreadable; leaving it untouched.", path)
        return path
    fmap = bejson_core_get_field_map(doc)
    name_idx = fmap.get("name", 0)
    rank_idx = fmap.get("rank", 1)
    present = {_clean_str(r[name_idx]) for r in doc.get("Values", []) if len(r) > name_idx}
    ranks = [_to_int(r[rank_idx], 0) for r in doc.get("Values", []) if len(r) > rank_idx]
    missing = [r for r in regs if r.name not in present]
    if missing:
        next_rank = max(ranks + [0]) + 1
        for reg in missing:
            doc["Values"].append(_row_from_registered(reg, reg.pct if reg.pct is not None else 0.0,
                                                      reg.rank or next_rank))
            next_rank = max(next_rank, (reg.rank or next_rank)) + 1
        bejson_core_atomic_write(str(path), doc)
    return path


def ai_bubble_config_load(config_dir: Path) -> dict:
    """Returns {"interval": int, "rows": [dict, ...]} sorted by rank.  Rows
    are sanitised (stripped strings, clamped numbers, valid enums)."""
    path = ai_bubble_config_init(Path(config_dir))
    doc = bejson_core_load_file(str(path))
    interval = DEFAULT_REBUILD_INTERVAL_TURNS
    normalize = _to_bool(doc.get("Normalize_Baselines"), True) if isinstance(doc, dict) else True
    rows: List[dict] = []
    if not isinstance(doc, dict) or not isinstance(doc.get("Values"), list):
        # Unreadable / mangled file: never go silent.  Run on the registered
        # defaults (even split) in memory and leave the user's file alone.
        _warn_once("cfg-corrupt", "[AIContextBubble] %s unreadable; using registered defaults in memory.", path)
        with _LOCK:
            regs = list(_registry.values())
        even = round(100.0 / len(regs), 2) if regs else 0.0
        for i, reg in enumerate(regs, start=1):
            rows.append({"name": reg.name, "rank": reg.rank or i,
                         "pct": reg.pct if reg.pct is not None else even, "enabled": reg.enabled,
                         "refresh": reg.refresh, "keep": reg.keep, "label": reg.label,
                         "directive": reg.directive})
        rows.sort(key=lambda r: (r["rank"], r["name"]))
        return {"interval": interval, "rows": rows, "normalize": normalize}
    if isinstance(doc, dict):
        interval = _to_int(doc.get("Rebuild_Interval_Turns"), DEFAULT_REBUILD_INTERVAL_TURNS, _MAX_INTERVAL)
        fmap = bejson_core_get_field_map(doc)
        idx = {k: fmap.get(k) for k in ("name", "rank", "pct", "enabled", "refresh", "keep", "label", "directive")}
        seen = set()
        for raw in doc.get("Values", []):
            def cell(key, default=None):
                i = idx.get(key)
                return raw[i] if i is not None and i < len(raw) else default
            name = _clean_str(cell("name"))
            if not _NAME_RE.match(name) or name in seen:
                logger.warning("[AIContextBubble] Skipping bad/duplicate config row %r.", name)
                continue
            seen.add(name)
            refresh = _clean_str(cell("refresh")).lower()
            keep = _clean_str(cell("keep")).lower()
            rows.append({
                "name": name,
                "rank": _to_int(cell("rank"), 99),
                "pct": _to_float(cell("pct"), 0.0),
                "enabled": _to_bool(cell("enabled"), True),
                "refresh": refresh if refresh in (REFRESH_STABLE, REFRESH_TURN) else REFRESH_STABLE,
                "keep": keep if keep in (KEEP_START, KEEP_END) else KEEP_START,
                "label": _clean_str(cell("label")) or name,
                "directive": _clean_str(cell("directive")),
            })
    rows.sort(key=lambda r: (r["rank"], r["name"]))
    return {"interval": interval, "rows": rows, "normalize": normalize}


# ── Allocator (pure) ──────────────────────────────────────────────────────────

def _split_evenly(capacity: Dict[str, int], amount: int) -> Dict[str, int]:
    """Takes `amount` from the keys, as equally as their capacities allow."""
    give = {k: 0 for k in capacity}
    remaining = min(max(0, amount), sum(capacity.values()))
    while remaining > 0:
        open_keys = sorted(k for k, c in capacity.items() if c - give[k] > 0)
        if not open_keys:
            break
        share = remaining // len(open_keys)
        if share == 0:
            for k in open_keys[:remaining]:
                give[k] += 1
            break
        for k in open_keys:
            g = min(share, capacity[k] - give[k])
            give[k] += g
            remaining -= g
    return give


def _normalise_pcts(pcts: Dict[str, float]) -> Dict[str, float]:
    """If the baselines add up to more than 100, cut EVENLY (equal points off
    each, never below 0) until they sum to 100.  Otherwise unchanged."""
    out = dict(pcts)
    excess = sum(out.values()) - 100.0
    while excess > 1e-9:
        open_keys = [k for k, v in out.items() if v > 1e-12]
        if not open_keys:
            break
        cut = excess / len(open_keys)
        for k in open_keys:
            c = min(cut, out[k])
            out[k] -= c
            excess -= c
    return out


def ai_bubble_allocate(total_chars: int, items: List[dict]) -> Dict[str, dict]:
    """
    items: [{"name", "rank", "pct", "demand"}] -- demand in chars (header
    included).  Returns name -> {budget, demand, grant, spill_in, spill_out,
    sources: {donor: chars}, truncated}.

    1. baseline budget = total * pct (pcts over 100 are cut evenly).
    2. an allotment keeps min(demand, budget); the rest of its budget is
       unused and donated, as is any unassigned remainder.
    3. over-budget allotments claim in rank order, each drawing evenly from
       every donor that still has something left.
    """
    total_chars = max(0, int(total_chars))
    pcts = _normalise_pcts({i["name"]: float(i["pct"]) for i in items})
    result: Dict[str, dict] = {}
    capacity: Dict[str, int] = {}
    for it in items:
        budget = int(total_chars * pcts[it["name"]] / 100.0)
        demand = max(0, int(it["demand"]))
        keep_own = min(demand, budget)
        result[it["name"]] = {
            "budget": budget, "demand": demand, "grant": keep_own,
            "spill_in": 0, "spill_out": 0, "sources": {}, "truncated": False,
        }
        if budget - keep_own > 0:
            capacity[it["name"]] = budget - keep_own
    unassigned = total_chars - sum(r["budget"] for r in result.values())
    if unassigned > 0:
        capacity[_UNASSIGNED] = unassigned

    for it in sorted(items, key=lambda i: (i["rank"], i["name"])):
        r = result[it["name"]]
        need = r["demand"] - r["budget"]
        if need <= 0:
            continue
        taken = _split_evenly(capacity, need)
        total_taken = 0
        for donor, amt in taken.items():
            if amt <= 0:
                continue
            capacity[donor] -= amt
            r["sources"][donor] = amt
            total_taken += amt
            if donor in result:
                result[donor]["spill_out"] += amt
        r["spill_in"] = total_taken
        r["grant"] = r["budget"] + total_taken
    for r in result.values():
        r["truncated"] = r["demand"] > r["grant"]
    return result


# ── Truncation / rendering ────────────────────────────────────────────────────

def _truncate(text: str, room: int, keep: str) -> str:
    if len(text) <= room:
        return text
    mark = _TRUNC_MARK_HEAD if keep == KEEP_END else _TRUNC_MARK_TAIL
    keep_chars = room - len(mark)
    if keep_chars < _MIN_USEFUL_CHARS:
        return ""
    if keep == KEEP_END:
        piece = text[-keep_chars:]
        nl = piece.find("\n", 0, 200)
        if nl != -1:
            piece = piece[nl + 1:]
        return mark + piece
    piece = text[:keep_chars]
    nl = piece.rfind("\n", max(0, keep_chars - 200))
    if nl > 0:
        piece = piece[:nl]
    return piece + mark


def _header(row: dict) -> str:
    h = f"## {row['label']}\n"
    if row["directive"]:
        h += f"{row['directive']}\n"
    return h


_SEP = "\n\n"


# ── Paths / state ─────────────────────────────────────────────────────────────

def _paths(root: Path) -> dict:
    root = Path(root)
    bdir = root / BUBBLE_DIRNAME
    return {
        "dir": bdir,
        "allotments": bdir / ALLOTMENTS_SUBDIR,
        "stage": bdir / STAGE_SUBDIR,
        "chunk": root / BUBBLE_CHUNK_FILENAME,
        "state": root / STATE_FILENAME,
        "policy": root / _POLICY_FILENAME,
    }


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def _clean_text(text: Any) -> str:
    """Valid UTF-8, stripped, and with the bubble's own wrapper markers
    defanged so content can never fake the start/end of the bubble."""
    if not isinstance(text, str):
        return ""
    text = text.encode("utf-8", "replace").decode("utf-8").strip()
    if "CONTEXT BUBBLE]" in text:
        text = text.replace("[END CONTEXT BUBBLE]", "[END CONTEXT-BUBBLE]").replace("[CONTEXT BUBBLE]", "[CONTEXT-BUBBLE]")
    return text


def _cap_source(text: str, limit: int, keep: str) -> str:
    """Bounds a source to `limit` chars (budget + slack), keeping the side
    that survives truncation anyway.  Nothing beyond the whole bubble budget
    can ever be sent, so storing/hashing it is pure waste."""
    if len(text) <= limit:
        return text
    return text[-limit:] if keep == KEEP_END else text[:limit]


def _load_state(root: Path) -> dict:
    p = _paths(root)["state"]
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    for key in ("turn", "turns_since_rebuild", "rebuild_count"):
        v = data.get(key, 0)
        data[key] = v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else 0
    for key in ("stable", "volatile"):
        v = data.get(key)
        data[key] = {k: x for k, x in v.items() if isinstance(k, str) and isinstance(x, str)} if isinstance(v, dict) else {}
    if not isinstance(data.get("config_sig"), str):
        data.pop("config_sig", None)
    data["package_version"] = str(data.get("package_version", "0"))
    return data


def _save_state(root: Path, state: dict) -> None:
    if not bejson_core_atomic_write(str(_paths(root)["state"]), state):
        logger.error("[AIContextBubble] Could not persist bubble state.")


def ai_bubble_destroy(root: Path) -> bool:
    """Deletes the bubble directory and the bubble chunk.  The next prepare
    rebuilds from scratch.  Returns True if anything was removed."""
    p = _paths(Path(root))
    removed = False
    if p["dir"].exists():
        shutil.rmtree(p["dir"], ignore_errors=True)
        removed = True
    if p["chunk"].exists():
        try:
            p["chunk"].unlink()
            removed = True
        except OSError as exc:
            logger.warning("[AIContextBubble] Could not remove bubble chunk: %s", exc)
    return removed


# ── Chunking ──────────────────────────────────────────────────────────────────

def _remove_allotment_chunk(root: Path, name: str) -> None:
    adir = _paths(root)["allotments"]
    if adir.is_dir():
        for f in adir.glob(f"*_{name}.104a.bejson"):
            try:
                f.unlink()
            except OSError:
                pass


def _chunk_allotment(root: Path, rank: int, name: str, text: str, file_version: str, pkg: str) -> None:
    """Writes the allotment text to a stage dir, chunks it with the Core
    lib, stores the chunk in bubble/allotments/, removes the stage."""
    p = _paths(root)
    stage = p["stage"] / name
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True, exist_ok=True)
    (stage / f"{name}.txt").write_bytes(text.encode("utf-8"))
    try:
        doc = bejson_core_chunking_create_chunked_104(
            str(stage), version=file_version, extensions=[".txt"],
            exclude_dirs=[], package_version=pkg)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    _remove_allotment_chunk(root, name)
    p["allotments"].mkdir(parents=True, exist_ok=True)
    target = p["allotments"] / f"{rank:02d}_{name}.104a.bejson"
    if not bejson_core_atomic_write(str(target), doc):
        raise OSError(f"could not write allotment chunk {target}")


def _chunk_bubble(root: Path, file_version: str, pkg: str) -> None:
    """Chunks the whole bubble directory into one Chunked-104a document."""
    p = _paths(root)
    p["dir"].mkdir(parents=True, exist_ok=True)
    shutil.rmtree(p["stage"], ignore_errors=True)
    doc = bejson_core_chunking_create_chunked_104(
        str(p["dir"]), version=file_version, extensions=[".bejson"],
        exclude_dirs=[STAGE_SUBDIR], package_version=pkg)
    if not bejson_core_atomic_write(str(p["chunk"]), doc):
        raise OSError(f"could not write bubble chunk {p['chunk']}")


def _read_bubble(root: Path) -> Dict[str, str]:
    """Reads the bubble chunk, verifies every File_Hash at both levels, and
    returns {allotment_name: text}.  Raises BubbleIntegrityError."""
    chunk_path = _paths(root)["chunk"]
    doc = bejson_core_load_file(str(chunk_path)) if chunk_path.exists() else None
    if not isinstance(doc, dict):
        raise BubbleIntegrityError("bubble chunk missing or unreadable")
    fm = bejson_core_get_field_map(doc)
    out: Dict[str, str] = {}
    for row in doc.get("Values", []):
        rel = str(row[fm["Relative_Path"]]).replace("\\", "/")
        content = row[fm["File_Content"]]
        if bejson_core_chunking_hash_file_bytes(content.encode("utf-8")) != row[fm["File_Hash"]]:
            raise BubbleIntegrityError(f"hash mismatch in bubble chunk row {rel}")
        m = re.match(rf"^{ALLOTMENTS_SUBDIR}/\d+_([a-z][a-z0-9_]*)\.104a\.bejson$", rel)
        if not m:
            continue
        name = m.group(1)
        try:
            inner = json.loads(content)
            ifm = {f["name"]: i for i, f in enumerate(inner["Fields"])}
            irow = next(r for r in inner["Values"] if r[ifm["File_Name"]] == f"{name}.txt")
        except (ValueError, KeyError, StopIteration) as exc:
            raise BubbleIntegrityError(f"allotment chunk '{name}' malformed: {exc}") from exc
        text = irow[ifm["File_Content"]]
        if bejson_core_chunking_hash_file_bytes(text.encode("utf-8")) != irow[ifm["File_Hash"]]:
            raise BubbleIntegrityError(f"hash mismatch in allotment chunk '{name}'")
        out[name] = text
    return out


# ── Prepare (the per-turn entry point) ────────────────────────────────────────

def _constants(config_dir: Path) -> dict:
    if _CONSTANTS_AVAILABLE:
        try:
            ai_constants_init(Path(config_dir))
            c = dict(ai_constants_load(Path(config_dir)))
        except Exception as exc:
            logger.warning("[AIContextBubble] ai_constants failed (%s); using defaults.", exc)
            c = {}
    else:
        c = {}
    try:
        c["max_context_tokens"] = max(1, int(c.get("max_context_tokens", DEFAULT_MAX_CONTEXT_TOKENS)))
    except (TypeError, ValueError):
        c["max_context_tokens"] = DEFAULT_MAX_CONTEXT_TOKENS
    try:
        cpt = int(c.get("chars_per_token", DEFAULT_CHARS_PER_TOKEN))
    except (TypeError, ValueError):
        cpt = 0
    if cpt <= 0:
        logger.warning("[AIContextBubble] chars_per_token <= 0; using %d.", DEFAULT_CHARS_PER_TOKEN)
        cpt = DEFAULT_CHARS_PER_TOKEN
    c["chars_per_token"] = cpt
    return c


def _run_builders(active: List[dict], ctx: BubbleContext) -> Dict[str, str]:
    texts: Dict[str, str] = {}
    limit = ctx.budget_chars + _SOURCE_SLACK_CHARS
    for row in active:
        reg = _registry.get(row["name"])
        if reg is None:
            texts[row["name"]] = ""
            continue
        try:
            texts[row["name"]] = _cap_source(_clean_text(reg.builder(ctx)), limit, row["keep"])
        except Exception as exc:
            logger.warning("[AIContextBubble] Allotment '%s' builder failed: %s", row["name"], exc)
            texts[row["name"]] = ""
    return texts


def _select_active(cfg: dict, skip) -> List[dict]:
    active = [r for r in cfg["rows"]
              if r["enabled"] and r["name"] in _registry and r["name"] not in skip]
    if len(active) > BUBBLE_MAX_ALLOTMENTS:
        _warn_once("max-allot", "[AIContextBubble] %d active allotments exceed BUBBLE_MAX_ALLOTMENTS=%d; "
                   "dropping the lowest ranks.", len(active), BUBBLE_MAX_ALLOTMENTS)
        active = active[:BUBBLE_MAX_ALLOTMENTS]
    return active


def _effective_pcts(active: List[dict], normalize: bool) -> Dict[str, float]:
    """Share of the window each ENABLED allotment may claim as its baseline.
    normalize=True: the configured weights are scaled so the enabled shares add
    up to exactly 100 (all-zero weights -> an even split).  Switching an
    allotment off therefore hands its share to the rest, in proportion to
    their weights.  normalize=False: the weights are used as written (cut
    evenly only if they exceed 100; any remainder is an unassigned pool)."""
    raw = {r["name"]: float(r["pct"]) for r in active}
    if not raw:
        return {}
    if not normalize:
        return _normalise_pcts(raw)
    total = sum(raw.values())
    if total <= 1e-9:
        return {k: 100.0 / len(raw) for k in raw}
    return {k: v * 100.0 / total for k, v in raw.items()}


def _render(active: List[dict], chunk_texts: Dict[str, str], constants: dict, turn: int,
            normalize: bool = True, include_text: bool = False) -> dict:
    """Allocates budgets and renders the payload from verified chunk text.
    An allotment whose grant is too small to hold even its header plus a
    useful slice is dropped and its grant re-spilled to the others."""
    cpt = constants["chars_per_token"]
    total_chars = constants["max_context_tokens"] * cpt
    room_total = max(0, total_chars - len(_WRAP_OPEN) - len(_WRAP_CLOSE))
    dropped: set = set()
    alloc: Dict[str, dict] = {}
    blocks: Dict[str, str] = {}
    shares = _effective_pcts(active, normalize)
    for _ in range(len(active) + 1):
        items = []
        for row in active:
            text = chunk_texts.get(row["name"], "")
            demand = (len(_header(row)) + len(text) + len(_SEP)) if text and row["name"] not in dropped else 0
            items.append({"name": row["name"], "rank": row["rank"], "pct": shares[row["name"]], "demand": demand})
        alloc = ai_bubble_allocate(room_total, items)
        blocks = {}
        newly: set = set()
        for row in active:
            name = row["name"]
            text = chunk_texts.get(name, "")
            if not text or name in dropped:
                continue
            head = _header(row)
            room = alloc[name]["grant"] - len(head) - len(_SEP)
            body = _truncate(text, room, row["keep"]) if room > 0 else ""
            if body:
                blocks[name] = head + body
            else:
                newly.add(name)
        if not newly:
            break
        dropped |= newly

    stats: List[dict] = []
    for row in active:
        a = alloc[row["name"]]
        text = chunk_texts.get(row["name"], "")
        block = blocks.get(row["name"], "")
        stats.append({
            "name": row["name"], "label": row["label"], "rank": row["rank"], "pct": row["pct"],
            "share_pct": round(shares[row["name"]], 2),
            "refresh": row["refresh"], "keep": row["keep"],
            "budget_tokens": a["budget"] // cpt, "demand_tokens": a["demand"] // cpt,
            "granted_tokens": a["grant"] // cpt, "used_tokens": len(block) // cpt,
            "spill_in_tokens": a["spill_in"] // cpt, "spill_out_tokens": a["spill_out"] // cpt,
            "sources": {k: v // cpt for k, v in a["sources"].items()},
            "truncated": bool(text) and (a["truncated"] or row["name"] in dropped),
            "empty": not text, "dropped": row["name"] in dropped,
        })
        if include_text:
            stats[-1]["text"] = block
    ordered = [blocks[r["name"]] for r in active if r["name"] in blocks]
    payload = (_WRAP_OPEN + _SEP.join(ordered) + _WRAP_CLOSE) if ordered else ""
    return {"text": payload, "allotments": stats, "normalize": normalize,
            "used_tokens": len(payload) // cpt,
            "max_context_tokens": constants["max_context_tokens"], "chars_per_token": cpt}


def _config_signature(cfg: dict) -> str:
    return _sha(json.dumps([cfg["interval"], cfg.get("normalize", True), cfg["rows"]], sort_keys=True))


def ai_bubble_prepare(
    context_dir: Path,
    config_dir: Path,
    user_msg: str,
    extras: Optional[Dict[str, Any]] = None,
    skip: tuple = (),
) -> dict:
    """
    Per-turn entry point.  Advances the turn counter, rebuilds the bubble if
    due (interval reached, content change, or missing), refreshes volatile
    allotments, and returns the payload plus stats:

      text, allotments[], used_tokens, max_context_tokens, rebuilt (bool),
      reason ("first" | "missing" | "interval" | "changed: a,b" | "reuse"),
      turn, turns_until_rebuild, rebuild_interval, chunk_path

    skip: allotment names to leave out this call (e.g. ("chat_history",)
    when the caller already sends history itself).  Raises
    BubbleIntegrityError only if a rebuild also fails verification.
    """
    context_dir, config_dir = Path(context_dir), Path(config_dir)
    extras, skip = extras or {}, tuple(skip)
    with _LOCK:
        try:
            try:
                return _prepare_locked(context_dir, config_dir, user_msg, extras, skip)
            except BubbleIntegrityError as exc:
                logger.error("[AIContextBubble] Integrity failure (%s); rebuilding once.", exc)
                ai_bubble_destroy(context_dir)
                return _prepare_locked(context_dir, config_dir, user_msg, extras, skip,
                                       forced_reason="integrity")
        except Exception as exc:
            # Never lose the policy/attachments because of a disk or state problem:
            # budget and render straight from the builders, skipping the chunks.
            logger.error("[AIContextBubble] Bubble build failed (%s: %s); sending an unchunked bubble.",
                         type(exc).__name__, exc)
            return _degraded(context_dir, config_dir, user_msg, extras, skip, exc)


def _degraded(context_dir, config_dir, user_msg, extras, skip, exc) -> dict:
    """In-memory bubble: same allocation, truncation and directives, no chunk
    files, no state writes.  Falls back to the policy-only bubble if even
    that fails."""
    try:
        constants = _constants(config_dir)
        cfg = ai_bubble_config_load(config_dir)
        active = _select_active(cfg, skip)
        ctx = BubbleContext(
            user_msg=user_msg, turn=int(_load_state(context_dir).get("turn", 0)) + 1,
            constants=constants, context_dir=context_dir, config_dir=config_dir,
            budget_chars=constants["max_context_tokens"] * constants["chars_per_token"], extras=extras)
        texts = _run_builders(active, ctx)
        out = _render(active, texts, constants, ctx.turn, cfg.get("normalize", True))
        out.update({"rebuilt": False, "reason": f"degraded: {type(exc).__name__}", "turn": ctx.turn,
                    "rebuild_interval": cfg["interval"], "turns_until_rebuild": 0, "chunk_path": ""})
        return out
    except Exception as exc2:
        logger.error("[AIContextBubble] Unchunked bubble failed too (%s); policy only.", exc2)
        out = ai_bubble_minimal(context_dir)
        out["reason"] = f"degraded: {type(exc2).__name__}"
        return out


def _prepare_locked(context_dir, config_dir, user_msg, extras, skip, forced_reason=None) -> dict:
    context_dir.mkdir(parents=True, exist_ok=True)
    constants = _constants(config_dir)
    cfg = ai_bubble_config_load(config_dir)
    active = _select_active(cfg, skip)
    state = _load_state(context_dir)
    turn = int(state.get("turn", 0)) + 1
    ctx = BubbleContext(
        user_msg=user_msg, turn=turn, constants=constants, context_dir=context_dir,
        config_dir=config_dir, budget_chars=constants["max_context_tokens"] * constants["chars_per_token"],
        extras=extras)
    texts = _run_builders(active, ctx)

    stable = {r["name"]: _sha(texts[r["name"]]) for r in active if r["refresh"] == REFRESH_STABLE}
    volatile = {r["name"]: _sha(texts[r["name"]]) for r in active if r["refresh"] == REFRESH_TURN}
    cfg_sig = _config_signature(cfg)
    paths = _paths(context_dir)
    interval = cfg["interval"]
    since = int(state.get("turns_since_rebuild", 0))

    changed = sorted(n for n in set(stable) | set(state.get("stable", {}))
                     if stable.get(n) != state.get("stable", {}).get(n))
    if forced_reason:
        reason = forced_reason
    elif not state or "stable" not in state:
        reason = "first"
    elif not paths["chunk"].exists() or not paths["allotments"].is_dir():
        reason = "missing"
    elif state.get("config_sig") != cfg_sig:
        reason = "changed: config"
    elif changed:
        reason = "changed: " + ",".join(changed)
    elif since + 1 >= interval:
        reason = "interval"
    else:
        reason = "reuse"
    rebuilt = reason != "reuse"

    rebuild_count = int(state.get("rebuild_count", 0))
    pkg = str(state.get("package_version", "0"))
    if rebuilt:
        ai_bubble_destroy(context_dir)
        rebuild_count += 1
        pkg = bejson_core_chunking_bump_package_version({"Package_Version": pkg})
        fv = str(rebuild_count)
        for row in active:
            if texts[row["name"]]:
                _chunk_allotment(context_dir, row["rank"], row["name"], texts[row["name"]], fv, pkg)
        _chunk_bubble(context_dir, fv, pkg)
        since = 0
    else:
        since += 1
        dirty = [r for r in active if r["refresh"] == REFRESH_TURN
                 and state.get("volatile", {}).get(r["name"]) != volatile[r["name"]]]
        if dirty:
            pkg = bejson_core_chunking_bump_package_version({"Package_Version": pkg})
            fv = str(rebuild_count)
            for row in dirty:
                if texts[row["name"]]:
                    _chunk_allotment(context_dir, row["rank"], row["name"], texts[row["name"]], fv, pkg)
                else:
                    _remove_allotment_chunk(context_dir, row["name"])
            _chunk_bubble(context_dir, fv, pkg)

    chunk_texts = _read_bubble(context_dir)
    # The bubble on disk must carry exactly what the builders produced this
    # turn.  A missing or stale allotment (deleted file, edited chunk, crash
    # remnant) is an integrity failure, never a silent drop.
    for row in active:
        want = texts[row["name"]]
        if want and chunk_texts.get(row["name"]) != want:
            raise BubbleIntegrityError(f"allotment '{row['name']}' missing or stale in bubble chunk")
    rendered = _render(active, chunk_texts, constants, turn, cfg.get("normalize", True))

    _save_state(context_dir, {
        "turn": turn, "turns_since_rebuild": since, "rebuild_count": rebuild_count,
        "package_version": pkg, "stable": stable, "volatile": volatile, "config_sig": cfg_sig,
    })
    rendered.update({
        "rebuilt": rebuilt, "reason": reason, "turn": turn,
        "rebuild_interval": interval, "turns_until_rebuild": max(0, interval - 1 - since),
        "chunk_path": str(paths["chunk"]),
    })
    return rendered


def _group_map() -> Dict[str, str]:
    """name -> group.  Explicit group= wins; otherwise names that share a first
    token with at least one other registered name (brain_pinned, brain_recall)
    form a group named after that token."""
    with _LOCK:
        regs = dict(_registry)
    tokens: Dict[str, int] = {}
    for name in regs:
        tok = name.split("_")[0]
        tokens[tok] = tokens.get(tok, 0) + 1
    out: Dict[str, str] = {}
    for name, reg in regs.items():
        tok = name.split("_")[0]
        out[name] = reg.group or (tok if tokens[tok] >= 2 else "")
    return out


def _catalog(cfg: dict, skip: tuple = ()) -> List[dict]:
    """Every config row -- enabled or not, available or not -- for the UI."""
    groups = _group_map()
    with _LOCK:
        available = set(_registry)
    return [{"name": r["name"], "label": r["label"], "rank": r["rank"], "pct": r["pct"],
             "enabled": r["enabled"], "available": r["name"] in available,
             "group": groups.get(r["name"], ""), "refresh": r["refresh"], "keep": r["keep"],
             "skipped": r["name"] in skip} for r in cfg["rows"]]


def ai_bubble_config_update(config_dir: Path, changes: Dict[str, Dict[str, Any]],
                            normalize: Optional[bool] = None) -> dict:
    """
    Validated, atomic edit of context_bubble.bejson.
      changes: {allotment_name: {"enabled": bool, "pct": number}}   (either key optional)
      normalize: optional new value for Normalize_Baselines
    Raises ValueError (nothing written) on an unknown name, a non-bool enabled
    or a pct that is not a finite number in 0..100.  Returns the reloaded
    config.  The next prepare sees the change and rebuilds the bubble.
    """
    config_dir = Path(config_dir)
    with _LOCK:
        path = ai_bubble_config_init(config_dir)
        doc = bejson_core_load_file(str(path))
        if not isinstance(doc, dict) or not isinstance(doc.get("Values"), list):
            raise ValueError("context_bubble.bejson is unreadable; fix or delete it first")
        fmap = bejson_core_get_field_map(doc)
        for col in ("name", "enabled", "pct"):
            if col not in fmap:
                raise ValueError(f"context_bubble.bejson has no '{col}' column")
        by_name = {_clean_str(r[fmap["name"]]): r for r in doc["Values"] if len(r) > fmap["name"]}
        staged = []
        for name, ch in (changes or {}).items():
            if name not in by_name:
                raise ValueError(f"unknown allotment: {name!r}")
            if not isinstance(ch, dict):
                raise ValueError(f"changes for {name!r} must be an object")
            if "enabled" in ch:
                if not isinstance(ch["enabled"], bool):
                    raise ValueError(f"'enabled' for {name!r} must be true or false")
                staged.append((by_name[name], fmap["enabled"], ch["enabled"]))
            if "pct" in ch:
                v = ch["pct"]
                if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 100:
                    raise ValueError(f"'pct' for {name!r} must be a number from 0 to 100")
                staged.append((by_name[name], fmap["pct"], float(v)))
        if normalize is not None and not isinstance(normalize, bool):
            raise ValueError("'normalize' must be true or false")
        for row, idx, value in staged:
            row[idx] = value
        if normalize is not None:
            doc["Normalize_Baselines"] = normalize
        if (staged or normalize is not None) and not bejson_core_atomic_write(str(path), doc):
            raise OSError("could not write context_bubble.bejson")
        return ai_bubble_config_load(config_dir)


def ai_bubble_preview(
    context_dir: Path,
    config_dir: Path,
    user_msg: str = "",
    extras: Optional[Dict[str, Any]] = None,
    skip: tuple = (),
) -> dict:
    """Builds the bubble the way the next prompt would see it, in a throw-away
    temp directory.  Touches no live bubble, no counter, no state."""
    context_dir, config_dir = Path(context_dir), Path(config_dir)
    with _LOCK:
        constants = _constants(config_dir)
        cfg = ai_bubble_config_load(config_dir)
        active = _select_active(cfg, tuple(skip))
        live = _load_state(context_dir)
        turn = int(live.get("turn", 0)) + 1
        ctx = BubbleContext(
            user_msg=user_msg, turn=turn, constants=constants, context_dir=context_dir,
            config_dir=config_dir, budget_chars=constants["max_context_tokens"] * constants["chars_per_token"],
            extras=extras or {})
        texts = _run_builders(active, ctx)
        with tempfile.TemporaryDirectory(prefix="bubble_preview_") as tmp:
            tmp_root = Path(tmp)
            for row in active:
                if texts[row["name"]]:
                    _chunk_allotment(tmp_root, row["rank"], row["name"], texts[row["name"]], "preview", "1")
            _chunk_bubble(tmp_root, "preview", "1")
            rendered = _render(active, _read_bubble(tmp_root), constants, turn,
                               cfg.get("normalize", True), include_text=True)
        since = int(live.get("turns_since_rebuild", 0))
        rendered.update({
            "rebuilt": False, "reason": "preview", "turn": turn,
            "catalog": _catalog(cfg, tuple(skip)), "rebuild_interval": cfg["interval"],
            "turns_until_rebuild": max(0, cfg["interval"] - 1 - since) if live else 0,
            "chunk_path": "",
        })
        return rendered


def ai_bubble_init(context_dir: Path, config_dir: Path, policy_text: Optional[str] = None) -> dict:
    """Creates the directories, ai_constants.bejson, context_bubble.bejson
    (for the allotments registered so far) and a default Persistent_Policy.md
    (only if absent).  Returns the path dict."""
    context_dir, config_dir = Path(context_dir), Path(config_dir)
    context_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    if _CONSTANTS_AVAILABLE:
        ai_constants_init(config_dir)
    ai_bubble_config_init(config_dir)
    p = _paths(context_dir)
    if policy_text and not p["policy"].exists():
        p["policy"].write_text(policy_text, encoding="utf-8")
    return {k: str(v) for k, v in p.items()} | {"config": str(_config_path(config_dir))}


def ai_bubble_minimal(context_dir: Path) -> dict:
    """Degraded-mode fallback: Persistent Policy only."""
    policy_path = _paths(Path(context_dir))["policy"]
    try:
        policy_text = policy_path.read_text("utf-8", errors="replace")[:4000]
    except OSError:
        policy_text = ""
    text = f"{_WRAP_OPEN}## Persistent Policy\n{policy_text}{_WRAP_CLOSE}" if policy_text else ""
    return {"text": text, "allotments": [], "rebuilt": False, "reason": "degraded"}


# ── Compression / amnesia helpers (carried over unchanged from v1) ───────────

_observer_compressor: Optional[Callable[[str], Optional[str]]] = None


def ai_bubble_set_compressor(fn: Callable[[str], Optional[str]]) -> None:
    """Registers an optional compressor callable (text -> compressed text | None)."""
    global _observer_compressor
    _observer_compressor = fn


def ai_bubble_compress_history(
    history: List[dict],
    compressor_fn: Callable[[str], Optional[str]],
) -> Optional[str]:
    """Compresses a conversation to a dense recap string; fails open (None)."""
    if not history:
        return None
    transcript = "\n\n".join(f"[{t.get('role', '?')}]: {t.get('content', '')}" for t in history)
    if not transcript.strip():
        return None
    try:
        result = compressor_fn(transcript)
        if result and result.strip():
            return result.strip()
    except Exception as exc:
        logger.warning("[AIContextBubble] History compression failed: %s", exc)
    return None


def ai_bubble_save_amnesia_recap(context_dir: Path, recap: str) -> None:
    context_dir = Path(context_dir)
    context_dir.mkdir(parents=True, exist_ok=True)
    target = context_dir / _AMNESIA_FILENAME
    tmp = target.with_suffix(".tmp")
    tmp.write_text(recap, encoding="utf-8")
    tmp.replace(target)


def ai_bubble_load_amnesia_recap(context_dir: Path) -> Optional[str]:
    target = Path(context_dir) / _AMNESIA_FILENAME
    if not target.is_file():
        return None
    text = target.read_text(encoding="utf-8").strip()
    return text or None


def ai_bubble_rebirth(history: List[dict], recap: str) -> None:
    """Wipes history in place and reseeds it with the recap as the sole turn."""
    history.clear()
    history.append({"role": "user", "content": f"[Rebirth -- compressed session recap]\n{recap}"})
