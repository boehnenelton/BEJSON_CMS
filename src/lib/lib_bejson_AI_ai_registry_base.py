"""
Library:         lib_bejson_AI_ai_registry_base.py
Family:          AI
Module Purpose:  Implements runtime functionality and logic for lib_bejson_AI_ai_registry_base.py.
Architecture:    BEJSON 104a provides fast primitive metadata and manifest configuration with O(1) field map caching.
Version:         2.1.0
Release_Version: 300
Date:            2026-10-13
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   b4f17d93-2c68-4e0a-9a35-7d1e8c52f046

Changelog:
  2.1.0 (2026-10-13) - Bug fix + secure-store fill. (1) RoundRobinKeyRegistry.load() scanned the
        numbered slots (GEMINI_KEY_1.. / GROQ_KEY_1..) only INSIDE `if self.env_var:`, so a registry
        built with env_var_prefix alone never read any env key; the two checks are now independent.
        (2) load() first calls source_env_fill() (Core env 2.3.0, non-overwriting, cached) so keys held
        in secureenv_file.json are visible without the caller sourcing the env first. If the Core env
        lib is older or absent the call is skipped and behaviour is exactly as before. (3) env keys are
        de-duplicated. File fallback, placeholder filtering and every public name are unchanged.
"""

import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from lib_bejson_Core_bejson_core import (
    bejson_core_atomic_write,
    bejson_core_get_field_index,
    bejson_core_get_field_map,
    bejson_core_load_file,
)

try:  # Core env 2.3.0+; older/absent Core -> no-op and behaviour is unchanged
    from lib_bejson_Core_bejson_env import source_env_fill as _source_env_fill
except ImportError:
    _source_env_fill = None

logger = logging.getLogger("lib_bejson_AI_ai_registry_base")

VERSION = "2.1.0"


# --- Self-contained storage location ---------------------------------------

def get_self_contained_dir(caller_file: Union[str, Path]) -> Path:
    """
    Returns <AI_lib_folder>/config, auto-created. Every AI-family provider
    now stores its runtime config (keys fallback file, model registry,
    profile) here -- inside the library's own folder tree -- instead of an
    external ADMIN_ROOT/HOME path. Pass __file__ from the calling provider
    module so each provider's config sits next to that provider's own code.
    """
    d = Path(caller_file).resolve().parent / "config"
    d.mkdir(parents=True, exist_ok=True)
    return d


# --- Versioned self-healing store ------------------------------------------

def _read_config_version(path: Path) -> Optional[int]:
    try:
        data = bejson_core_load_file(str(path))
        return data.get("Config_Version") if data else None
    except Exception:
        return None


def ensure_current(path: Path, schema_factory: Callable[[], dict], config_version: int) -> None:
    """
    Shared self-heal entry point used by RoundRobinKeyRegistry,
    ModelRegistryBase, and BejsonProfileBase. Regenerates path from
    schema_factory() (with Config_Version stamped in) whenever the file is
    missing, unreadable, or carries an older Config_Version than the
    caller's current one -- this is what actually fixes "stale file stays
    broken/wrong forever", not just "file is missing".
    """
    needs_write = not path.exists()
    if not needs_write:
        on_disk_version = _read_config_version(path)
        needs_write = on_disk_version is None or on_disk_version < config_version
    if needs_write:
        try:
            os.makedirs(path.parent, exist_ok=True)
            schema = schema_factory()
            schema["Config_Version"] = config_version
            bejson_core_atomic_write(str(path), schema)
        except Exception as e:
            logger.warning(f"[ai_registry_base] Could not write {path}: {e}")


class RoundRobinKeyRegistry:
    """
    Atomic unit: loads an ApiKey-schema BEJSON file (Fields: key_slot?, key)
    and hands out keys round-robin. Filters out placeholder values so an
    unconfigured key file (still holding "YOUR_..._KEY_HERE") never gets
    handed to a live API call. Env vars are always checked first regardless
    of file state (Section 4.2 secure-credentials-first ordering) -- the
    BEJSON file is only ever a fallback.

    Subclass or instantiate directly:
        reg = RoundRobinKeyRegistry(path, placeholder_markers=["YOUR_GROQ_KEY", "KEY_HERE"])
        key = reg.get_next_key()
    """

    def __init__(
        self,
        file_path: Union[str, Path],
        *,
        placeholder_markers: Optional[List[str]] = None,
        key_field: str = "key",
        env_var: Optional[str] = None,
        env_var_prefix: Optional[str] = None,
        env_var_max_slots: int = 30,
        default_schema: Optional[dict] = None,
        config_version: int = 1,
    ):
        """
        env_var          -- a single comma-separated env var (e.g. an all-in-
                             one "GROQ_API_KEYS" list), checked if set.
        env_var_prefix    -- numbered-slot convention actually used in
                             Elton's secure env store (GEMINI_KEY_1..N,
                             GROQ_KEY_1..N, OPENROUTER_KEY_1..N). Scans
                             f"{prefix}_1".."{prefix}_{max_slots}", skipping
                             any slot that's missing or blank -- gaps (an
                             empty numbered slot) are fine, not a stop
                             condition. Checked before the BEJSON file per
                             Section 4.2's secure-credentials-first ordering.
        default_schema    -- override the BEJSON doc written when the file
                             needs (re)generating, for providers whose
                             default differs from this class's generic one
                             (e.g. Gemini's single-"key"-field, Format 104
                             default). None uses the generic key_slot+key
                             104a default.
        config_version    -- bump this in the calling provider whenever its
                             default_schema changes; a stale on-disk file
                             (older Config_Version, or none at all) is
                             regenerated automatically on next init.
        """
        self.file_path = Path(file_path)
        self.key_field = key_field
        self.placeholder_markers = placeholder_markers or ["YOUR_", "KEY_HERE", "_KEY_HERE"]
        self.env_var = env_var
        self.env_var_prefix = env_var_prefix
        self.env_var_max_slots = env_var_max_slots
        self.default_schema = default_schema
        self.config_version = config_version
        self.keys: List[str] = []
        self._idx = 0
        self._ensure_current()
        self.load()

    def _default_factory(self) -> dict:
        return self.default_schema or {
            "Format": "BEJSON", "Format_Version": "104a", "Format_Creator": "Elton Boehnen",
            "Records_Type": ["ApiKey"],
            "Fields": [{"name": "key_slot", "type": "integer"}, {"name": self.key_field, "type": "string"}],
            "Values": [],
        }

    def _ensure_current(self) -> None:
        ensure_current(self.file_path, self._default_factory, self.config_version)

    # Back-compat aliases -- older provider code called these public names.
    def create_default(self) -> None:
        self._ensure_current()

    def _create_default(self) -> None:
        self._ensure_current()

    def load(self) -> None:
        self.keys = []

        if _source_env_fill is not None:
            try:
                _source_env_fill()
            except Exception as e:
                logger.warning(f"[RoundRobinKeyRegistry] secure env fill skipped: {type(e).__name__}")

        if self.env_var:
            env_val = os.environ.get(self.env_var, "")
            for k in (k.strip() for k in env_val.split(",")):
                if k and k not in self.keys:
                    self.keys.append(k)

        if self.env_var_prefix:
            for i in range(1, self.env_var_max_slots + 1):
                v = os.environ.get(f"{self.env_var_prefix}_{i}", "").strip()
                if v and v not in self.keys:
                    self.keys.append(v)

        try:
            data = bejson_core_load_file(str(self.file_path))
            idx = bejson_core_get_field_index(data, self.key_field)
            if idx != -1:
                for row in data.get("Values", []):
                    val = str(row[idx])
                    if not any(marker in val for marker in self.placeholder_markers):
                        self.keys.append(row[idx])
        except Exception as e:
            logger.warning(f"[RoundRobinKeyRegistry] Failed to load {self.file_path}: {e}")

    def get_next_key(self) -> Optional[str]:
        if not self.keys:
            return None
        key = self.keys[self._idx % len(self.keys)]
        self._idx += 1
        return key

    def get_key_count(self) -> int:
        return len(self.keys)


class ModelRegistryBase:
    """
    Atomic unit: loads a BEJSON model list (must have at least model_id and
    currently_active fields) and answers "what's the active model" /
    "give me info for model X" via the Field Map Cache (never positional).

    config_version self-heals the exact stale-model bug this class used to
    have: a decommissioned model left marked currently_active in an old
    on-disk file used to load "successfully" (structurally valid BEJSON)
    and silently become the active model forever, producing 404s from the
    provider's API with zero indication the local registry was the cause.
    Bumping config_version when a provider's default model list changes
    now regenerates that stale file instead of trusting it blindly.

    Subclass to add provider-specific fields to each model's info dict by
    overriding _extra_fields(); the base always includes "id".
    """

    def __init__(
        self,
        file_path: Union[str, Path],
        *,
        default_model_id: str,
        default_rows_factory: Optional[Callable[[], dict]] = None,
        config_version: int = 1,
    ):
        self.file_path = Path(file_path)
        self.active_model_id = default_model_id
        self._default_rows_factory = default_rows_factory
        self.config_version = config_version
        self.models: List[Dict[str, Any]] = []
        if self._default_rows_factory:
            ensure_current(self.file_path, self._default_rows_factory, self.config_version)
        self.load()

    # Back-compat alias
    def _create_default(self) -> None:
        if self._default_rows_factory:
            ensure_current(self.file_path, self._default_rows_factory, self.config_version)

    def load(self) -> None:
        try:
            data = bejson_core_load_file(str(self.file_path))
            fmap = bejson_core_get_field_map(data)
            id_idx = fmap.get("model_id")
            active_idx = fmap.get("currently_active")
            if id_idx is None:
                raise ValueError("model registry missing 'model_id' field")

            self.models = []
            for row in data.get("Values", []):
                info = {"id": row[id_idx]}
                info.update(self._extra_fields(row, fmap))
                self.models.append(info)
                if active_idx is not None and row[active_idx] is True:
                    self.active_model_id = row[id_idx]
        except Exception as e:
            logger.warning(f"[ModelRegistryBase] Failed to load {self.file_path}, using default only: {e}")
            self.models = [{"id": self.active_model_id}]

    def _extra_fields(self, row: List[Any], fmap: Dict[str, int]) -> Dict[str, Any]:
        """Override in a subclass to pull extra per-model fields (e.g. 'thinking')."""
        return {}

    def get_model_info(self, model_id: Optional[str] = None) -> Dict[str, Any]:
        target = model_id or self.active_model_id
        for m in self.models:
            if m["id"] == target:
                return m
        return {"id": target}


class BejsonProfileBase:
    """
    Atomic unit: loads a BEJSON AI_Profile record (system instruction +
    per-provider config dict) via the Field Map Cache, self-healing from a
    provider-supplied schema_factory whenever the on-disk file is missing,
    structurally invalid (e.g. an empty Values list), or carries an older
    Config_Version than the provider currently ships.

    Generalizes the create_default()/load() pattern that Groq, OpenRouter,
    Grok, and Hugging Face each independently duplicated -- providers now
    subclass this (or instantiate directly) instead of re-implementing it.

    Subclass or instantiate directly:
        profile = BejsonProfileBase(path, schema_factory=lambda: SCHEMA,
                                     config_version=1)
        profile.instruction   # -> str
        profile.config        # -> dict of every field in the profile row
    """

    def __init__(
        self,
        file_path: Union[str, Path],
        *,
        schema_factory: Callable[[], dict],
        config_version: int = 1,
        instruction_field: str = "SystemInstruction",
        legacy_instruction_index: int = 4,
    ):
        self.file_path = Path(file_path)
        self.schema_factory = schema_factory
        self.config_version = config_version
        self.instruction_field = instruction_field
        self.legacy_instruction_index = legacy_instruction_index
        self.instruction = ""
        self.config: Dict[str, Any] = {}
        ensure_current(self.file_path, self.schema_factory, self.config_version)
        self.load()

    # Back-compat alias
    def create_default(self) -> None:
        ensure_current(self.file_path, self.schema_factory, self.config_version)

    def load(self) -> None:
        try:
            data = bejson_core_load_file(str(self.file_path))
            fi = bejson_core_get_field_map(data)
            values = data.get("Values") or []
            if not values:
                raise ValueError(f"Profile at {self.file_path} has no Values rows")

            instr_idx = fi.get(self.instruction_field, self.legacy_instruction_index)
            self.instruction = values[0][instr_idx]
            self.config = {f["name"]: values[0][i] for i, f in enumerate(data["Fields"])}
        except Exception as e:
            # Self-heal: a structurally invalid file (e.g. empty Values,
            # the class of bug this method used to fall silent on) is
            # regenerated from schema_factory() and retried once before
            # giving up to a blank instruction/config.
            logger.warning(f"[BejsonProfileBase] Profile at {self.file_path} invalid ({e}), regenerating")
            try:
                schema = self.schema_factory()
                schema["Config_Version"] = self.config_version
                os.makedirs(self.file_path.parent, exist_ok=True)
                bejson_core_atomic_write(str(self.file_path), schema)

                data = bejson_core_load_file(str(self.file_path))
                fi = bejson_core_get_field_map(data)
                values = data["Values"]
                instr_idx = fi.get(self.instruction_field, self.legacy_instruction_index)
                self.instruction = values[0][instr_idx]
                self.config = {f["name"]: values[0][i] for i, f in enumerate(data["Fields"])}
            except Exception as repair_error:
                logger.warning(f"[BejsonProfileBase] Failed to repair profile {self.file_path}: {repair_error}")
                self.instruction = ""
                self.config = {}