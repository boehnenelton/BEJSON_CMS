"""
Library:        lib_bejson_AI_bejson_litertlm.py
Family:         AI
Description:    On-device LiteRT-LM integration (provider key "litertlm", client
                 service "LiteRTLM"). Talks to the OpenAI-compatible server that
                 `litert-lm serve` exposes (default http://127.0.0.1:9379:
                 /v1/models, /v1/chat/completions); needs no API key.

                 Provides:
                   - LiteRTLMServer: locate the `litert-lm` binary, run
                     `litert-lm serve --port N` as a subprocess (or reuse a server
                     that already answers), list served models via /v1/models,
                     background setup with pollable state. Models are imported with
                     the litert-lm CLI itself (`litert-lm import ...`); this class
                     does not download them.
                   - LiteRTLMStandardPrompter: prompt() (single shot, the shape
                     ai_dispatch expects) and stream() (token generator over the SSE
                     chat-completions stream) for chat clients.
                   - Zero-config singletons: get_standard_prompter(),
                     get_standard_server().

                 Default model: gemma-4-e2b (Gemma 4 E2B, ~32k context, text +
                 vision + audio input on the engine; this client sends text).
Version:        1.0.0
Date:           2026-10-20
Author:         Elton Boehnen
Contact:        boehnenelton2024@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  3d8a5c1e-92b4-4f6a-a7d3-0e5b61c9f284
Release_Version: 300

Changelog:
  1.0.0 (2026-10-20) -- Initial creation (structure mirrors lib_bejson_AI_bejson_ollamalocal.py).
"""

import atexit
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import urlparse

LIB_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_DIR = os.path.join(os.path.dirname(LIB_DIR), "Core")
if CORE_DIR not in sys.path:
    sys.path.append(CORE_DIR)

from lib_bejson_AI_ai_registry_base import (
    ModelRegistryBase,
    BejsonProfileBase,
    get_self_contained_dir,
)
from lib_bejson_AI_bejson_errors import AIRecoverableError

logger = logging.getLogger("lib_bejson_AI_bejson_litertlm")

VERSION = "1.0.0"
LITERTLM_CONFIG_VERSION = 1
CONFIG_DIR = get_self_contained_dir(__file__)

DEFAULT_BASE_URL = "http://127.0.0.1:9379"
BASE_URL_ENV_VAR = "LITERTLM_URL"
BINARY_NAME = "litert-lm"
DEFAULT_MODEL_ID = "gemma-4-e2b"


class LiteRTLMError(AIRecoverableError):
    """LiteRT-LM server missing, not running, or rejected the request."""


# --- SCHEMAS -----------------------------------------------------------

SCHEMA_MODEL_REGISTRY_LITERTLM = {
    "Format": "BEJSON", "Format_Version": "104a", "Format_Creator": "Elton Boehnen",
    "Records_Type": ["LiteRTLMModel"],
    "Fields": [
        {"name": "model_name", "type": "string"},
        {"name": "model_id", "type": "string"},
        {"name": "currently_active", "type": "boolean"},
    ],
    "Values": [
        ["Gemma 4 E2B", "gemma-4-e2b", True],
    ],
}

SCHEMA_AI_PROFILE = {
    "Format": "BEJSON", "Format_Version": "104", "Format_Creator": "Elton Boehnen",
    "Records_Type": ["AI_Profile"],
    "Fields": [
        {"name": "Record_Type_Parent", "type": "string"},
        {"name": "Name", "type": "string"},
        {"name": "Archetype", "type": "string"},
        {"name": "Persona", "type": "string"},
        {"name": "SystemInstruction", "type": "string"},
        {"name": "MaxResponseTokens", "type": "integer"},
        {"name": "Creativity", "type": "number"},
    ],
    "Values": [
        [
            "AI_Profile", "LiteRTLM_Standard", "Assistant",
            "A concise, accurate on-device assistant.",
            "You are a concise and accurate assistant. Use fenced code blocks for code.",
            1024, 0.4,
        ]
    ],
}


class LiteRTLMModelRegistry(ModelRegistryBase):
    def __init__(self, file_path: str):
        super().__init__(
            file_path,
            default_model_id=DEFAULT_MODEL_ID,
            default_rows_factory=lambda: SCHEMA_MODEL_REGISTRY_LITERTLM,
            config_version=LITERTLM_CONFIG_VERSION,
        )


class LiteRTLMProfile(BejsonProfileBase):
    def __init__(self, file_path: str):
        super().__init__(
            file_path,
            schema_factory=lambda: SCHEMA_AI_PROFILE,
            config_version=LITERTLM_CONFIG_VERSION,
        )


def _http_error_text(resp) -> str:
    """Best-effort extraction of an OpenAI-style {"error": {"message": ...}} body."""
    try:
        err = resp.json().get("error")
        if isinstance(err, dict):
            err = err.get("message")
        return str(err or resp.text)[:300]
    except Exception:
        return f"HTTP {resp.status_code}"


# --- SERVER MANAGER -----------------------------------------------------

class LiteRTLMServer:
    """Finds `litert-lm`, runs `litert-lm serve` in a subprocess, and exposes
    pollable setup state for UIs."""

    BUSY_PHASES = ("starting",)

    def __init__(self, base_url: Optional[str] = None, log_dir: Optional[str] = None,
                 binary_name: str = BINARY_NAME, ready_timeout_s: int = 90):
        self.base_url = (base_url or os.environ.get(BASE_URL_ENV_VAR) or DEFAULT_BASE_URL).rstrip("/")
        self.log_dir = Path(log_dir) if log_dir else CONFIG_DIR / "logs"
        self.binary_name = binary_name
        self.ready_timeout_s = ready_timeout_s
        self._proc: Optional[subprocess.Popen] = None
        self._logfh = None
        self._lock = threading.RLock()
        self._atexit_registered = False
        self.state: Dict[str, Any] = {"phase": "idle", "message": "", "percent": None, "error": None}

    def _set_state(self, **kw: Any) -> None:
        with self._lock:
            self.state.update(kw)

    # -- probes -----------------------------------------------------------
    def is_ready(self) -> bool:
        import requests
        try:
            return requests.get(f"{self.base_url}/v1/models", timeout=2).status_code == 200
        except Exception:
            return False

    def installed_models(self) -> List[str]:
        """Model ids the running server reports on /v1/models."""
        import requests
        try:
            r = requests.get(f"{self.base_url}/v1/models", timeout=5)
            r.raise_for_status()
            return [m.get("id", "") for m in r.json().get("data", []) if m.get("id")]
        except Exception:
            return []

    def has_model(self, model_id: str) -> bool:
        return model_id in set(self.installed_models())

    def status(self) -> Dict[str, Any]:
        ready = self.is_ready()
        with self._lock:
            state = dict(self.state)
        return {
            "ready": ready,
            "base_url": self.base_url,
            "binary": shutil.which(self.binary_name),
            "managed_pid": self._proc.pid if self._proc and self._proc.poll() is None else None,
            "installed_models": self.installed_models() if ready else [],
            "state": state,
        }

    # -- run --------------------------------------------------------------
    def ensure_binary(self) -> str:
        found = shutil.which(self.binary_name)
        if not found:
            raise LiteRTLMError(
                f"'{self.binary_name}' not found on PATH. Install LiteRT-LM (e.g. in Termux a venv with the "
                f"litert-lm package symlinked to $PREFIX/bin/{self.binary_name}) and import a model "
                f"(litert-lm import ...), then try again.")
        return found

    def start(self) -> None:
        """Start `litert-lm serve --port N` unless a server already answers."""
        with self._lock:
            if self.is_ready():
                logger.info("LiteRT-LM server already running at %s; reusing.", self.base_url)
                return
            binary = self.ensure_binary()
            port = urlparse(self.base_url).port or 9379
            self.log_dir.mkdir(parents=True, exist_ok=True)
            log_path = self.log_dir / "litertlm_server.log"
            self._logfh = open(log_path, "ab")
            self._set_state(phase="starting", message="Starting litert-lm serve ...", percent=None)
            logger.info("Starting litert-lm serve --port %s (log: %s)", port, log_path)
            self._proc = subprocess.Popen([binary, "serve", "--port", str(port)], stdout=self._logfh,
                                          stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            if not self._atexit_registered:
                atexit.register(self.stop)
                self._atexit_registered = True
            deadline = time.time() + self.ready_timeout_s
            while time.time() < deadline:
                if self._proc.poll() is not None:
                    raise LiteRTLMError(f"litert-lm serve exited (code {self._proc.returncode}). See {log_path}")
                if self.is_ready():
                    logger.info("LiteRT-LM ready.")
                    return
                time.sleep(0.5)
            raise LiteRTLMError(f"Timed out waiting for litert-lm serve ({self.ready_timeout_s}s). See {log_path}")

    def stop(self) -> None:
        """Stop only a server this object started."""
        with self._lock:
            if self._proc and self._proc.poll() is None:
                logger.info("Stopping managed litert-lm serve ...")
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
            self._proc = None
            if self._logfh:
                self._logfh.close()
                self._logfh = None
            if self.state.get("phase") in ("ready", "starting"):
                self._set_state(phase="idle", message="Stopped.", percent=None)

    def setup(self, model_id: Optional[str] = None) -> None:
        """Blocking: ensure binary + running server, then check the model is served."""
        model_id = model_id or DEFAULT_MODEL_ID
        try:
            if not self.is_ready():
                self.start()
            served = self.installed_models()
            if served and model_id not in served:
                raise LiteRTLMError(
                    f"Server is up but does not list '{model_id}' (served: {', '.join(served)}). "
                    f"Import it first: litert-lm import ...")
            self._set_state(phase="ready", message=f"{model_id} ready", percent=100, error=None)
        except Exception as exc:
            logger.error("LiteRT-LM setup failed: %s", exc)
            self._set_state(phase="error", message=str(exc), percent=None, error=str(exc))
            raise

    def setup_async(self, model_id: Optional[str] = None) -> bool:
        """Run setup() in a daemon thread. False if a setup is already running."""
        with self._lock:
            if self.state.get("phase") in self.BUSY_PHASES:
                return False
            self._set_state(phase="starting", message="Working ...", percent=None, error=None)

        def _run() -> None:
            try:
                self.setup(model_id)
            except Exception:
                pass  # state already carries the error

        threading.Thread(target=_run, daemon=True, name="litertlm-setup").start()
        return True


# --- PROMPTER -------------------------------------------------------------

class LiteRTLMStandardPrompter:
    def __init__(self, model_registry_path: str, profile_path: str, server: LiteRTLMServer):
        self.model_reg = LiteRTLMModelRegistry(model_registry_path)
        self.profile = LiteRTLMProfile(profile_path)
        self.server = server

    def _params(self, config: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "max_tokens": int(config.get("max_tokens") or self.profile.config.get("MaxResponseTokens", 1024)),
            "temperature": float(config.get("temperature", self.profile.config.get("Creativity", 0.4))),
        }

    def build_messages(self, user_input: str, system_instruction: Optional[str] = None,
                       history: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, str]]:
        msgs = [{"role": "system", "content": system_instruction or self.profile.instruction}]
        msgs += list(history or [])
        msgs.append({"role": "user", "content": user_input})
        return msgs

    def _not_running(self) -> str:
        return (f"ERROR: LiteRT-LM server is not running at {self.server.base_url}. "
                f"Start it from Settings > Local Model (LiteRT-LM), or run: litert-lm serve --port 9379")

    def prompt(self, user_input: str, model_id: Optional[str] = None,
               system_instruction: Optional[str] = None, **config: Any) -> str:
        import requests
        if not self.server.is_ready():
            return self._not_running()
        model = self.model_reg.get_model_info(model_id)["id"]
        payload = {"model": model, "messages": self.build_messages(user_input, system_instruction),
                   "stream": False, **self._params(config)}
        try:
            r = requests.post(f"{self.server.base_url}/v1/chat/completions", json=payload, timeout=600)
            if r.status_code != 200:
                return f"ERROR: {_http_error_text(r)}"
            choices = r.json().get("choices") or []
            content = ((choices[0].get("message") or {}).get("content")) if choices else None
            return content.strip() if content else "ERROR: Empty response from LiteRT-LM."
        except Exception as e:
            return f"ERROR: {e}"

    def stream(self, messages: List[Dict[str, str]], model_id: Optional[str] = None,
               **config: Any) -> Iterator[str]:
        """Yield content deltas from the SSE stream. Closing the generator
        closes the HTTP connection, which makes the server stop generating."""
        import requests
        if not self.server.is_ready():
            raise LiteRTLMError(self._not_running()[7:])
        model = self.model_reg.get_model_info(model_id)["id"]
        payload = {"model": model, "messages": messages, "stream": True, **self._params(config)}
        with requests.post(f"{self.server.base_url}/v1/chat/completions", json=payload,
                           stream=True, timeout=(5, 600)) as r:
            if r.status_code != 200:
                raise LiteRTLMError(_http_error_text(r))
            for raw in r.iter_lines():
                if not raw:
                    continue
                line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if obj.get("error"):
                    err = obj["error"]
                    raise LiteRTLMError(str(err.get("message") if isinstance(err, dict) else err))
                for ch in obj.get("choices") or []:
                    delta = (ch.get("delta") or {}).get("content")
                    if delta:
                        yield delta


STD_MODEL_PATH = CONFIG_DIR / "litertlm_model_registry.104a.bejson"
STD_PROFILE_PATH = CONFIG_DIR / "litertlm_standard_profile.bejson"

_std_server_singleton: Optional[LiteRTLMServer] = None
_std_prompter_singleton: Optional[LiteRTLMStandardPrompter] = None


def get_standard_server(log_dir: Optional[str] = None) -> LiteRTLMServer:
    """Shared server manager. `log_dir` only takes effect on the first call."""
    global _std_server_singleton
    if _std_server_singleton is None:
        _std_server_singleton = LiteRTLMServer(log_dir=log_dir)
    return _std_server_singleton


def get_standard_prompter() -> LiteRTLMStandardPrompter:
    """Zero-config prompter, cached after first call."""
    global _std_prompter_singleton
    if _std_prompter_singleton is None:
        _std_prompter_singleton = LiteRTLMStandardPrompter(
            STD_MODEL_PATH, STD_PROFILE_PATH, get_standard_server())
    return _std_prompter_singleton
