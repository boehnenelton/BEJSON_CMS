"""
Library:         lib_bejson_AI_ai_transcribe_registry.py
Family:          AI
Module Purpose:  Key registry for transcription providers that read multimodal-capable key slots
                 (e.g. GROQ_MM_KEY_*, OPENROUTER_MM_KEY_*) ahead of the provider's standard slots.
Architecture:    Subclasses lib_bejson_AI_ai_registry_base.RoundRobinKeyRegistry (same BEJSON 104a ApiKey
                 fallback file, same round-robin get_next_key()). Env keys are gathered first from every
                 variable equal to a prefix or starting with '<prefix>_' (so OPENROUTER_KEY_11_BE24 counts),
                 in prefix order, then the base class's numbered slots and file keys follow.
Version:         1.0.0
Release_Version: 300
Date:            2026-10-18
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   65f5ec3c-d7bb-4617-9504-da4826c2b93c
"""

import logging
import os
import re
from pathlib import Path
from typing import List, Tuple, Union

from lib_bejson_AI_ai_registry_base import RoundRobinKeyRegistry

logger = logging.getLogger("lib_bejson_AI_ai_transcribe_registry")

VERSION = "1.0.0"


def _natural_key(name: str) -> list:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", name)]


class TranscribeKeyRegistry(RoundRobinKeyRegistry):
    """RoundRobinKeyRegistry that also scans several env-var prefixes (highest priority first)."""

    def __init__(self, file_path: Union[str, Path], *, env_prefixes: Tuple[str, ...],
                 placeholder_markers: List[str], config_version: int = 1):
        self.env_prefixes = tuple(env_prefixes)       # must exist before super().__init__ (which calls load())
        super().__init__(
            file_path,
            placeholder_markers=placeholder_markers,
            env_var_prefix=self.env_prefixes[-1],
            env_var_max_slots=40,
            config_version=config_version,
        )

    def load(self) -> None:
        super().load()
        prioritized: List[str] = []
        for prefix in self.env_prefixes:
            names = sorted((n for n in os.environ if n == prefix or n.startswith(prefix + "_")), key=_natural_key)
            for name in names:
                val = os.environ.get(name, "").strip()
                if val and not any(m in val for m in self.placeholder_markers) and val not in prioritized:
                    prioritized.append(val)
        rest = [k for k in self.keys if k not in prioritized
                and not any(m in str(k) for m in self.placeholder_markers)]   # base class leaves env placeholders unfiltered
        self.keys = prioritized + rest
