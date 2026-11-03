"""
Library:         lib_bejson_AI_bejson_provocative.py
Family:          AI
Module Purpose:  Implements runtime functionality and logic for lib_bejson_AI_bejson_provocative.py.
Architecture:    BEJSON 104 Ecosystem Component maintaining strict schema integrity, field map caching, and standardized runtime contracts.
Version:         1.0.0
Release_Version: 300
Date:            2026-08-13
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   f5a49cd0-afd7-4032-b49d-e1df708cd641
"""

import os
import sys
from pathlib import Path
from typing import Optional

LIB_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_DIR = os.path.join(os.path.dirname(LIB_DIR), "Core")
if CORE_DIR not in sys.path:
    sys.path.append(CORE_DIR)

from lib_bejson_Core_bejson_env import resolve_path as resolve_system_path
from lib_bejson_AI_ai_registry_base import RoundRobinKeyRegistry
from lib_bejson_AI_ai_openai_compatible_base import OpenAICompatibleClient

VERSION = "1.0.0"

BASE_URL = "https://inference.provocative.earth/v1"
DEFAULT_MODEL = "qwen3.6-35b"

STD_KEY_PATH = resolve_system_path("{ADMIN_ROOT}/data/schemas/provocative_keys.bejson")


class ProvocativeKeyRegistry(RoundRobinKeyRegistry):
    def __init__(self, file_path: str = STD_KEY_PATH):
        super().__init__(
            file_path,
            placeholder_markers=["YOUR_PROVOCATIVE_KEY", "KEY_HERE"],
            env_var="ProvocativeAI",  # confirmed exact var name in the secure env store
            env_var_max_slots=0,      # no numbered-slot convention for this provider yet
        )


_client = OpenAICompatibleClient("provocative", BASE_URL, DEFAULT_MODEL)
_std_key_registry: Optional[ProvocativeKeyRegistry] = None


def get_standard_key_registry() -> ProvocativeKeyRegistry:
    global _std_key_registry
    if _std_key_registry is None:
        _std_key_registry = ProvocativeKeyRegistry()
    return _std_key_registry


def prompt(
    user_input: str,
    model_id: Optional[str] = None,
    *,
    system_instruction: Optional[str] = None,
    enable_thinking: Optional[bool] = None,
    **config,
) -> str:
    reg = get_standard_key_registry()
    key = reg.get_next_key()
    if enable_thinking is not None:
        config["chat_template_kwargs"] = {"enable_thinking": enable_thinking}
    return _client.chat(user_input, key, model=model_id, system_instruction=system_instruction, **config)