"""
Library:         lib_bejson_AI_ai_tool_system.py
Family:          AI
Module Purpose:  Implements runtime functionality and logic for lib_bejson_AI_ai_tool_system.py.
Architecture:    BEJSON 104 Ecosystem Component maintaining strict schema integrity, field map caching, and standardized runtime contracts.
Version:         1.0.0
Release_Version: 300
Date:            2026-08-14
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   c9edacd7-dac7-44ca-ac7a-ea1ac67e23f0
"""

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from lib_bejson_Core_bejson_path_guard import bejson_safe_join

logger = logging.getLogger("lib_bejson_AI_ai_tool_system")

VERSION = "1.0.0"


class ToolRegistry:
    """
    register(name, func, description, parameters) then hand
    get_tool_declarations() and make_executor() straight to
    GeminiInteractionsAPI.chat(tools=..., tool_executor=...).

    func signature: func(**kwargs) -> Any (kwargs come from the model's
    "arguments" object; return value is str()-ified into the
    function_result content per interactions.py's own convention -- this
    registry doesn't second-guess that, it just calls through).
    """

    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        name: str,
        func: Callable[..., Any],
        *,
        description: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> None:
        if name in self._tools:
            logger.warning(f"[ai_tool_system] Overwriting existing tool registration for {name!r}.")
        self._tools[name] = {
            "func": func,
            "description": description,
            "parameters": parameters or {"type": "object", "properties": {}},
        }

    def register_from_tool_def(self, tool_def_path: str, func: Callable[..., Any]) -> None:
        """
        Load name/description/parameters straight from a tool_def.json in
        the Flask_Gemini_Interactions convention (name, description,
        parameters keys, parameters already a JSON-schema object) and
        register func against it. func still has to be supplied here --
        this project's tool_def.json files describe tools that are
        themselves implemented as a second Gemini call server-side
        (Flask_Gemini_Service.py's /api/tool_exec); real local execution
        needs a real Python callable, which only the caller can provide.
        """
        with open(tool_def_path, "r", encoding="utf-8") as f:
            spec = json.load(f)
        self.register(spec["name"], func, description=spec.get("description", ""), parameters=spec.get("parameters"))

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get_tool_declarations(self) -> List[Dict[str, Any]]:
        """Flat {"type":"function","name",...} shape -- see module docstring."""
        return [
            {"type": "function", "name": name, "description": t["description"], "parameters": t["parameters"]}
            for name, t in self._tools.items()
        ]

    def make_executor(self) -> Callable[[str, Dict[str, Any]], Any]:
        """
        Returns a callable matching GeminiInteractionsAPI.chat()'s
        tool_executor signature exactly: (name: str, arguments: dict) -> Any.
        """
        def executor(name: str, arguments: Dict[str, Any]) -> Any:
            tool = self._tools.get(name)
            if tool is None:
                return f"ERROR: unknown tool '{name}'"
            try:
                return tool["func"](**arguments)
            except Exception as e:
                logger.error(f"[ai_tool_system] Tool {name!r} raised: {e}")
                return f"ERROR executing tool '{name}': {e}"
        return executor

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())


class SandboxedFileTools:
    """
    Local file read/write/list confined to root_dir via
    bejson_safe_join() -- every method raises ValueError (surfaced to the
    model as a tool error, not a crash) if the requested path would land
    outside root_dir. No method here can touch anything outside the
    directory the caller hands to __init__.

    Usage:
        fs = SandboxedFileTools("/path/to/project")
        registry.register("read_file", fs.read_file,
            description="Read a text file's contents.",
            parameters={"type":"object","properties":{
                "path":{"type":"string","description":"Path relative to the project root."}
            }, "required":["path"]})
        registry.register("write_file", fs.write_file, description=..., parameters=...)
        registry.register("list_directory", fs.list_directory, description=..., parameters=...)
    """

    def __init__(self, root_dir: str, *, max_read_bytes: int = 200_000):
        self.root_dir = str(Path(root_dir).resolve())
        self.max_read_bytes = max_read_bytes

    def read_file(self, path: str) -> str:
        full = bejson_safe_join(self.root_dir, path)
        p = Path(full)
        if not p.exists():
            return f"ERROR: {path} does not exist."
        if not p.is_file():
            return f"ERROR: {path} is not a file."
        data = p.read_bytes()
        if len(data) > self.max_read_bytes:
            return f"ERROR: {path} is {len(data)} bytes, over the {self.max_read_bytes}-byte read limit."
        return data.decode("utf-8", errors="replace")

    def write_file(self, path: str, content: str, *, overwrite: bool = True) -> str:
        full = bejson_safe_join(self.root_dir, path)
        p = Path(full)
        if p.exists() and not overwrite:
            return f"ERROR: {path} already exists and overwrite=False."
        p.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write (temp-then-rename), matching the System Development
        # Policy's atomic-writes-throughout standing rule.
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(p)
        return f"OK: wrote {len(content)} chars to {path}."

    def list_directory(self, path: str = ".") -> str:
        full = bejson_safe_join(self.root_dir, path)
        p = Path(full)
        if not p.exists():
            return f"ERROR: {path} does not exist."
        if not p.is_dir():
            return f"ERROR: {path} is not a directory."
        entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name))
        return "\n".join(f"{'[dir] ' if e.is_dir() else '      '}{e.name}" for e in entries) or "(empty)"

    def register_all(self, registry: ToolRegistry) -> None:
        """Convenience: registers read_file/write_file/list_directory in one call."""
        registry.register(
            "read_file", self.read_file,
            description=f"Read a text file's contents, relative to the sandboxed root ({self.root_dir}).",
            parameters={"type": "object", "properties": {
                "path": {"type": "string", "description": "File path relative to the sandbox root."}
            }, "required": ["path"]},
        )
        registry.register(
            "write_file", self.write_file,
            description=f"Write (create or overwrite) a text file, relative to the sandboxed root ({self.root_dir}).",
            parameters={"type": "object", "properties": {
                "path": {"type": "string", "description": "File path relative to the sandbox root."},
                "content": {"type": "string", "description": "Full file contents to write."},
                "overwrite": {"type": "boolean", "description": "If false, fails when the file already exists. Default true."},
            }, "required": ["path", "content"]},
        )
        registry.register(
            "list_directory", self.list_directory,
            description=f"List files and subdirectories, relative to the sandboxed root ({self.root_dir}).",
            parameters={"type": "object", "properties": {
                "path": {"type": "string", "description": "Directory path relative to the sandbox root. Default '.'."}
            }},
        )