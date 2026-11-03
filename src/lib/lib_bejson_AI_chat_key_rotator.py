"""
Library:         lib_bejson_AI_chat_key_rotator.py
Family:          AI
Module Purpose:  Thread-safe round-robin API-key rotator with per-key failure counting and cooldown. Complements the AI key registries (which only hand out keys round-robin) for long-running chat servers.
Architecture:    Stdlib only. Takes a plain list of keys (from GeminiKeyRegistry.keys or any registry); never reads files and never logs a key value, only a short hash tag.
Version:         1.0.0
Release_Version: 300
Date:            2026-10-28
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   b285909f-d884-402a-9196-c39c9a0bfd0b

Changelog:
  1.0.0 (2026-10-28) -- Initial creation (extension of the AI family; no existing AI library modified).
"""

import hashlib
import logging
import threading
import time
from typing import Callable, Dict, List, Optional

logger = logging.getLogger("lib_bejson_AI_chat_key_rotator")

VERSION = "1.0.0"
DEFAULT_FAIL_THRESHOLD = 3
DEFAULT_COOLDOWN_SECONDS = 60.0


# Short, non-reversible tag for log lines (never the key itself).
def chat_key_rotator_tag(key: str) -> str:
    return "key#" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:6]


class ChatKeyRotator:
    """Round-robin over `keys`, skipping keys that are cooling off after repeated failures."""

    def __init__(self, keys: List[str], fail_threshold: int = DEFAULT_FAIL_THRESHOLD,
                 cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
                 clock: Optional[Callable[[], float]] = None) -> None:
        seen: List[str] = []
        for k in keys or []:
            k = str(k).strip()
            if k and k not in seen:
                seen.append(k)
        self._keys = seen
        self._fail_threshold = max(1, int(fail_threshold))
        self._cooldown = float(cooldown_seconds)
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._index = 0
        self._fail_count: Dict[str, int] = {}
        self._cooldown_until: Dict[str, float] = {}

    def key_count(self) -> int:
        return len(self._keys)

    # Next usable key, or None when there are no keys at all. If every key is cooling off, returns the one that recovers soonest.
    def next_key(self) -> Optional[str]:
        with self._lock:
            n = len(self._keys)
            if n == 0:
                return None
            now = self._clock()
            for _ in range(n):
                key = self._keys[self._index % n]
                self._index = (self._index + 1) % n
                if now >= self._cooldown_until.get(key, 0.0):
                    return key
            best_idx = min(range(n), key=lambda i: (self._cooldown_until.get(self._keys[i], 0.0), (i - self._index) % n))
            best = self._keys[best_idx]
            self._index = (best_idx + 1) % n
            logger.warning("All %d API keys are cooling off; using the one that recovers first (%s).", n, chat_key_rotator_tag(best))
            return best

    def mark_failure(self, key: str, *, immediate: bool = False) -> None:
        with self._lock:
            count = self._fail_count.get(key, 0) + 1
            self._fail_count[key] = count
            if immediate or count >= self._fail_threshold:
                self._cooldown_until[key] = self._clock() + self._cooldown
                reason = "immediate cooldown" if immediate else f"{count} failures"
                logger.warning("%s hit %s; cooling off for %ss.", chat_key_rotator_tag(key), reason, int(self._cooldown))

    def mark_success(self, key: str) -> None:
        with self._lock:
            self._fail_count.pop(key, None)
            self._cooldown_until.pop(key, None)

    # Counts only, no key material.
    def status(self) -> Dict[str, int]:
        with self._lock:
            now = self._clock()
            cooling = sum(1 for k in self._keys if now < self._cooldown_until.get(k, 0.0))
            return {"keys": len(self._keys), "cooling_off": cooling}
