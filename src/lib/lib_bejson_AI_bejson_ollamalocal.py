"""
Library:        lib_bejson_AI_bejson_ollamalocal.py
Family:         AI
Description:    Local Ollama integration (provider key "ollamalocal", client
                 service "OllamaLocal"). Distinct from lib_bejson_AI_bejson_ollama.py,
                 which targets Ollama *Cloud* with API keys; this one talks to an
                 Ollama server running on the device itself (default
                 http://127.0.0.1:11434) and needs no key.

                 Provides:
                   - OllamaLocalServer: find/install the `ollama` binary
                     (Termux: `pkg install ollama`), run `ollama serve` as a
                     subprocess, pull models through Ollama's own /api/pull
                     (with progress), list installed models, background
                     setup with pollable state.
                   - OllamaLocalStandardPrompter: prompt() (single shot, the
                     shape ai_dispatch expects) and stream() (token generator
                     over /api/chat NDJSON) for chat clients.
                   - Zero-config singletons: get_standard_prompter(),
                     get_standard_server().

                 Default model: qwen2.5-coder:1.5b (phone-friendly). Others in
                 the registry: 0.5b, 3b, 7b.
Version:        1.0.0
Date:           2026-10-12
Author:         Elton Boehnen
Contact:        boehnenelton2024@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  ff8c0da8-06ac-4088-ab14-a307df3d33dc
Release_Version: 300

Changelog:
  1.0.0 (2026-10-12) -- Initial creation.
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
from typing import Any, Callable, Dict, Iterator, List, Optional
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

logger = logging.getLogger("lib_bejson_AI_bejson_ollamalocal")

VERSION = "1.0.0"
OLLAMALOCAL_CONFIG_VERSION = 1
CONFIG_DIR = get_self_contained_dir(__file__)

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
BASE_URL_ENV_VAR = "OLLAMA_LOCAL_URL"
DEFAULT_MODEL_TAG = "qwen2.5-coder:1.5b"
DEFAULT_NUM_CTX = 4096


class OllamaLocalError(AIRecoverableError):
    """Local Ollama server missing, not running, or rejected the request."""


# --- SCHEMAS -----------------------------------------------------------

SCHEMA_MODEL_REGISTRY_OLLAMALOCAL = {
    "Format": "BEJSON", "Format_Version": "104a", "Format_Creator": "Elton Boehnen",
    "Records_Type": ["OllamaLocalModel"],
    "Fields": [
        {"name": "model_name", "type": "string"},
        {"name": "model_id", "type": "string"},
        {"name": "currently_active", "type": "boolean"},
    ],
    "Values": [
        ["Qwen2.5-Coder 1.5B", "qwen2.5-coder:1.5b", True],
        ["Qwen2.5-Coder 0.5B", "qwen2.5-coder:0.5b", False],
        ["Qwen2.5-Coder 3B", "qwen2.5-coder:3b", False],
        ["Qwen2.5-Coder 7B", "qwen2.5-coder:7b", False],
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
            "AI_Profile", "OllamaLocal_Standard", "Assistant",
            "A concise, accurate local coding assistant.",
            "You are a concise and accurate coding assistant. Use fenced code blocks for code.",
            1024, 0.2,
        ]
    ],
}


class OllamaLocalModelRegistry(ModelRegistryBase):
    def __init__(self, file_path: str):
        super().__init__(
            file_path,
            default_model_id=DEFAULT_MODEL_TAG,
            default_rows_factory=lambda: SCHEMA_MODEL_REGISTRY_OLLAMALOCAL,
            config_version=OLLAMALOCAL_CONFIG_VERSION,
        )


class OllamaLocalProfile(BejsonProfileBase):
    def __init__(self, file_path: str):
        super().__init__(
            file_path,
            schema_factory=lambda: SCHEMA_AI_PROFILE,
            config_version=OLLAMALOCAL_CONFIG_VERSION,
        )


# --- SERVER MANAGER -----------------------------------------------------

def _http_error_text(resp) -> str:
    """Best-effort extraction of Ollama's {"error": "..."} body."""
    try:
        return str(resp.json().get("error") or resp.text)[:300]
    except Exception:
        return f"HTTP {resp.status_code}"


class OllamaLocalServer:
    """Finds/installs `ollama`, runs `ollama serve` in a subprocess, pulls
    models, and exposes pollable setup state for UIs."""

    BUSY_PHASES = ("installing", "starting", "pulling")

    def __init__(self, base_url: Optional[str] = None, log_dir: Optional[str] = None,
                 binary_name: str = "ollama", ready_timeout_s: int = 60):
        self.base_url = (base_url or os.environ.get(BASE_URL_ENV_VAR) or DEFAULT_BASE_URL).rstrip("/")
        self.log_dir = Path(log_dir) if log_dir else CONFIG_DIR / "logs"
        self.binary_name = binary_name
        self.ready_timeout_s = ready_timeout_s
        self._proc: Optional[subprocess.Popen] = None
        self._logfh = None
        self._lock = threading.RLock()
        self._atexit_registered = False
        self.state: Dict[str, Any] = {"phase": "idle", "message": "", "percent": None, "error": None}

    # -- state ------------------------------------------------------------
    def _set_state(self, **kw: Any) -> None:
        with self._lock:
            self.state.update(kw)

    # -- probes -----------------------------------------------------------
    def is_ready(self) -> bool:
        import requests
        try:
            return requests.get(f"{self.base_url}/api/version", timeout=2).status_code == 200
        except Exception:
            return False

    def installed_models(self) -> List[str]:
        import requests
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            r.raise_for_status()
            return [m.get("name", "") for m in r.json().get("models", []) if m.get("name")]
        except Exception:
            return []

    def has_model(self, tag: str) -> bool:
        have = set(self.installed_models())
        return tag in have or f"{tag}:latest" in have

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

    # -- install / run ----------------------------------------------------
    def ensure_binary(self) -> str:
        found = shutil.which(self.binary_name)
        if found:
            return found
        if "com.termux" in os.environ.get("PREFIX", ""):
            self._set_state(phase="installing", message="Installing ollama (pkg install ollama)...", percent=None)
            logger.info("ollama not found; running: pkg install -y ollama")
            rc = subprocess.run(["pkg", "install", "-y", "ollama"]).returncode
            if rc != 0:
                raise OllamaLocalError("'pkg install -y ollama' failed")
            found = shutil.which(self.binary_name)
        if not found:
            raise OllamaLocalError(
                f"'{self.binary_name}' not found on PATH. Install Ollama "
                f"(Termux: pkg install ollama; elsewhere: https://ollama.com/download).")
        return found

    def start(self) -> None:
        """Start `ollama serve` as a subprocess unless a server already answers."""
        with self._lock:
            if self.is_ready():
                logger.info("Ollama already running at %s; reusing.", self.base_url)
                return
            binary = self.ensure_binary()
            parsed = urlparse(self.base_url)
            env = dict(os.environ, OLLAMA_HOST=f"{parsed.hostname}:{parsed.port or 11434}")
            self.log_dir.mkdir(parents=True, exist_ok=True)
            log_path = self.log_dir / "ollama_server.log"
            self._logfh = open(log_path, "ab")
            self._set_state(phase="starting", message="Starting ollama serve ...", percent=None)
            logger.info("Starting ollama serve (log: %s)", log_path)
            self._proc = subprocess.Popen([binary, "serve"], stdout=self._logfh,
                                          stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env)
            if not self._atexit_registered:
                atexit.register(self.stop)
                self._atexit_registered = True
            deadline = time.time() + self.ready_timeout_s
            while time.time() < deadline:
                if self._proc.poll() is not None:
                    raise OllamaLocalError(
                        f"ollama serve exited (code {self._proc.returncode}). See {log_path}")
                if self.is_ready():
                    logger.info("Ollama ready.")
                    return
                time.sleep(0.5)
            raise OllamaLocalError(f"Timed out waiting for ollama serve ({self.ready_timeout_s}s). See {log_path}")

    def stop(self) -> None:
        """Stop only a server this object started."""
        with self._lock:
            if self._proc and self._proc.poll() is None:
                logger.info("Stopping managed ollama serve ...")
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

    def pull_model(self, tag: str, progress_cb: Optional[Callable[[str, Optional[int]], None]] = None) -> None:
        """Pull `tag` through Ollama's /api/pull, reporting (status, percent)."""
        import requests
        with requests.post(f"{self.base_url}/api/pull", json={"model": tag, "name": tag, "stream": True},
                           stream=True, timeout=(5, 3600)) as r:
            if r.status_code != 200:
                raise OllamaLocalError(f"Pull failed: {_http_error_text(r)}")
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("error"):
                    raise OllamaLocalError(f"Pull failed: {obj['error']}")
                total, done = obj.get("total"), obj.get("completed")
                pct = int(done * 100 / total) if total and done is not None else None
                if progress_cb:
                    progress_cb(str(obj.get("status", "")), pct)
                if obj.get("status") == "success":
                    break

    def setup(self, tag: Optional[str] = None) -> None:
        """Blocking: ensure binary + running server + model present."""
        tag = tag or DEFAULT_MODEL_TAG
        try:
            if not self.is_ready():
                self.start()
            if not self.has_model(tag):
                self._set_state(phase="pulling", message=f"Pulling {tag} ...", percent=0, error=None)
                self.pull_model(tag, lambda s, p: self._set_state(
                    phase="pulling", message=f"{tag}: {s}", percent=p))
            self._set_state(phase="ready", message=f"{tag} ready", percent=100, error=None)
        except Exception as exc:
            logger.error("Ollama setup failed: %s", exc)
            self._set_state(phase="error", message=str(exc), percent=None, error=str(exc))
            raise

    def setup_async(self, tag: Optional[str] = None) -> bool:
        """Run setup() in a daemon thread. False if a setup is already running."""
        with self._lock:
            if self.state.get("phase") in self.BUSY_PHASES:
                return False
            self._set_state(phase="starting", message="Working ...", percent=None, error=None)

        def _run() -> None:
            try:
                self.setup(tag)
            except Exception:
                pass  # state already carries the error

        threading.Thread(target=_run, daemon=True, name="ollamalocal-setup").start()
        return True


# --- PROMPTER -------------------------------------------------------------

class OllamaLocalStandardPrompter:
    def __init__(self, model_registry_path: str, profile_path: str, server: OllamaLocalServer):
        self.model_reg = OllamaLocalModelRegistry(model_registry_path)
        self.profile = OllamaLocalProfile(profile_path)
        self.server = server

    def _options(self, config: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "num_predict": int(config.get("max_tokens") or self.profile.config.get("MaxResponseTokens", 1024)),
            "temperature": float(config.get("temperature", self.profile.config.get("Creativity", 0.2))),
            "num_ctx": int(config.get("num_ctx", DEFAULT_NUM_CTX)),
        }

    def build_messages(self, user_input: str, system_instruction: Optional[str] = None,
                       history: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, str]]:
        msgs = [{"role": "system", "content": system_instruction or self.profile.instruction}]
        msgs += list(history or [])
        msgs.append({"role": "user", "content": user_input})
        return msgs

    def _not_running(self) -> str:
        return (f"ERROR: Local Ollama server is not running at {self.server.base_url}. "
                f"Start it from Settings > Local Model, or run: ollama serve")

    def prompt(self, user_input: str, model_id: Optional[str] = None,
               system_instruction: Optional[str] = None, **config: Any) -> str:
        import requests
        if not self.server.is_ready():
            return self._not_running()
        model = self.model_reg.get_model_info(model_id)["id"]
        payload = {"model": model, "messages": self.build_messages(user_input, system_instruction),
                   "stream": False, "options": self._options(config)}
        try:
            r = requests.post(f"{self.server.base_url}/api/chat", json=payload, timeout=600)
            if r.status_code != 200:
                return f"ERROR: {_http_error_text(r)}"
            content = (r.json().get("message") or {}).get("content")
            return content.strip() if content else "ERROR: Empty response from Ollama."
        except Exception as e:
            return f"ERROR: {e}"

    def stream(self, messages: List[Dict[str, str]], model_id: Optional[str] = None,
               **config: Any) -> Iterator[str]:
        """Yield content deltas. Closing the generator closes the HTTP
        connection, which makes Ollama stop generating."""
        import requests
        if not self.server.is_ready():
            raise OllamaLocalError(self._not_running()[7:])
        model = self.model_reg.get_model_info(model_id)["id"]
        payload = {"model": model, "messages": messages, "stream": True, "options": self._options(config)}
        with requests.post(f"{self.server.base_url}/api/chat", json=payload,
                           stream=True, timeout=(5, 600)) as r:
            if r.status_code != 200:
                raise OllamaLocalError(_http_error_text(r))
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("error"):
                    raise OllamaLocalError(str(obj["error"]))
                delta = (obj.get("message") or {}).get("content")
                if delta:
                    yield delta
                if obj.get("done"):
                    break


STD_MODEL_PATH = CONFIG_DIR / "ollamalocal_model_registry.104a.bejson"
STD_PROFILE_PATH = CONFIG_DIR / "ollamalocal_standard_profile.bejson"

_std_server_singleton: Optional[OllamaLocalServer] = None
_std_prompter_singleton: Optional[OllamaLocalStandardPrompter] = None


def get_standard_server(log_dir: Optional[str] = None) -> OllamaLocalServer:
    """Shared server manager. `log_dir` only takes effect on the first call."""
    global _std_server_singleton
    if _std_server_singleton is None:
        _std_server_singleton = OllamaLocalServer(log_dir=log_dir)
    return _std_server_singleton


def get_standard_prompter() -> OllamaLocalStandardPrompter:
    """Zero-config prompter, cached after first call (same pattern as the
    other AI-family providers)."""
    global _std_prompter_singleton
    if _std_prompter_singleton is None:
        _std_prompter_singleton = OllamaLocalStandardPrompter(
            STD_MODEL_PATH, STD_PROFILE_PATH, get_standard_server())
    return _std_prompter_singleton
