"""
Library:         lib_bejson_AI_profile_parser_runtime.py
Family:          AI
Module Purpose:  Validates, fingerprints, runs and sandbox-hosts the Parser and
                 Renderer code that an AI_Profile carries inside its own
                 columns (Parser_Language / Parser / Renderer). Replaces the old
                 "one mode library + one parser library per profile" pattern.
Architecture:    Pure functions, stdlib only, no BEJSON I/O (the profile
                 schema lives in lib_bejson_AI_gemini_standard_profiles).
                 Contract names are fixed so every client agrees on them:
                   parse(raw_text)            -> JSON-serialisable value
                   render(parsed, container)  -> draws into a DOM element
                 Parser languages: "python" | "javascript" (chosen per profile).
                 Layers (weakest to strongest isolation):
                   1. static validation  -- structure + deny rules; catches
                      mistakes and obvious abuse, NOT a security boundary.
                   2. approval gate      -- callers pass the SHA-256 fingerprints
                      they trust; unapproved code is never executed.
                   3. execution          -- python: isolated subprocess with
                      timeout + rlimits; javascript: node vm in a subprocess,
                      or (preferred) the browser sandbox below.
                   4. browser sandbox    -- sandbox_build_srcdoc() returns a
                      srcdoc for <iframe sandbox="allow-scripts"> (opaque
                      origin, CSP default-src 'none', no network, no parent
                      DOM). This is the only real boundary; prefer JavaScript
                      for profiles you did not write yourself.
Version:         1.0.0
Release_Version: 300
Date:            2026-10-18
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   12c218a0-5488-443b-87f7-6a9d5de6baa2

Changelog:
  1.0.0 (2026-10-18) -- Initial creation.
"""

import ast
import hashlib
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, Iterable, List, Optional

VERSION = "1.0.0"

logger = logging.getLogger(__name__)

# ── Contract ──────────────────────────────────────────────────────────────────
PARSER_LANGUAGES = ("python", "javascript")
PARSER_ENTRY = "parse"
RENDERER_ENTRY = "render"

MAX_CODE_CHARS = 32768
MAX_INPUT_CHARS = 2_000_000
MAX_RESULT_BYTES = 1_048_576
DEFAULT_TIMEOUT_SECONDS = 5.0
_MAX_ERRORS = 20

_LANGUAGE_ALIASES = {"py": "python", "python3": "python", "js": "javascript", "node": "javascript"}

# ── Python deny / allow rules ─────────────────────────────────────────────────
PY_ALLOWED_IMPORTS = frozenset({
    "json", "re", "math", "string", "textwrap", "collections", "itertools",
    "functools", "datetime", "html", "decimal", "fractions", "statistics",
})
_PY_DENIED_NAMES = frozenset({
    "exec", "eval", "compile", "open", "__import__", "input", "breakpoint",
    "globals", "locals", "vars", "getattr", "setattr", "delattr", "type",
    "exit", "quit", "help", "memoryview", "super", "classmethod",
    "staticmethod", "property",
})
_PY_DENIED_ATTRS = frozenset({
    "codecs", "os", "sys", "subprocess", "importlib", "builtins", "modules",
    "popen", "system", "f_globals", "f_locals", "gi_frame", "tb_frame",
    "cr_frame", "gi_code", "mro",
})
_PY_SAFE_BUILTINS = (
    "abs", "all", "any", "bool", "bytes", "chr", "dict", "divmod", "enumerate",
    "filter", "float", "format", "frozenset", "hash", "int", "isinstance",
    "issubclass", "iter", "len", "list", "map", "max", "min", "next", "object",
    "ord", "pow", "range", "repr", "reversed", "round", "set", "slice",
    "sorted", "str", "sum", "tuple", "zip", "hasattr", "callable",
    "Exception", "ValueError", "TypeError", "KeyError", "IndexError",
    "StopIteration", "ArithmeticError", "ZeroDivisionError", "AttributeError",
    "RuntimeError", "NotImplementedError", "UnicodeError",
    "__build_class__",
)

# ── JavaScript deny rules (defence in depth; the iframe sandbox is the boundary)
_JS_DENIED = [
    (re.compile(r"\beval\s*\("), "eval()"),
    (re.compile(r"\bnew\s+Function\b|\bFunction\s*\("), "Function constructor"),
    (re.compile(r"\bfetch\s*\("), "fetch()"),
    (re.compile(r"\bXMLHttpRequest\b"), "XMLHttpRequest"),
    (re.compile(r"\b(WebSocket|EventSource|SharedWorker|ServiceWorker|Worker)\b"), "network/worker API"),
    (re.compile(r"\bimportScripts\b"), "importScripts"),
    (re.compile(r"\bimport\s*\(|^\s*import\s", re.M), "import"),
    (re.compile(r"\b(localStorage|sessionStorage|indexedDB)\b"), "browser storage"),
    (re.compile(r"\bdocument\s*\.\s*(cookie|domain|location)\b|\bwindow\s*\.\s*location\b|\blocation\s*\.\s*(href|assign|replace)\b"), "navigation/cookie access"),
    (re.compile(r"(?<![.\w])(parent|top|opener|frames)\s*[.\[]"), "frame escape (parent/top/opener)"),
    (re.compile(r"\bsendBeacon\b"), "sendBeacon"),
    (re.compile(r"\bpostMessage\b"), "postMessage (the host owns messaging)"),
    (re.compile(r"</script", re.I), "'</script' sequence"),
    (re.compile(r"<!--"), "'<!--' sequence"),
]


def runtime_normalize_language(language: Any) -> Optional[str]:
    """Returns "python"/"javascript" for a supported language (aliases py/js
    accepted, case-insensitive), else None."""
    if not isinstance(language, str):
        return None
    key = language.strip().lower()
    key = _LANGUAGE_ALIASES.get(key, key)
    return key if key in PARSER_LANGUAGES else None


def runtime_fingerprint(language: Optional[str], parser: Optional[str], renderer: Optional[str]) -> str:
    """SHA-256 over (language, parser, renderer). This is what callers pin in
    their approved set; any edit to any of the three changes it."""
    blob = json.dumps([language or "", parser or "", renderer or ""], ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ── Static validation ─────────────────────────────────────────────────────────

def _common_errors(code: Any, what: str) -> List[str]:
    if not isinstance(code, str):
        return [f"{what} must be a string"]
    if not code.strip():
        return [f"{what} is empty"]
    errs: List[str] = []
    if len(code) > MAX_CODE_CHARS:
        errs.append(f"{what} is {len(code)} chars (max {MAX_CODE_CHARS})")
    if "\x00" in code:
        errs.append(f"{what} contains a NUL byte")
    return errs


def _dedupe(errs: List[str]) -> List[str]:
    seen, out = set(), []
    for e in errs:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out[:_MAX_ERRORS]


def runtime_validate_python_parser(code: Any) -> List[str]:
    """Static checks for a Python parser. Returns a list of problems (empty = ok)."""
    errs = _common_errors(code, "Python parser")
    if errs:
        return errs
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        return [f"Python parser syntax error (line {exc.lineno}): {exc.msg}"]
    entry_ok = False
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == PARSER_ENTRY:
            a = node.args
            if a.posonlyargs or a.args or a.vararg:
                entry_ok = True
            else:
                errs.append(f"{PARSER_ENTRY}() must accept one argument (raw_text)")
                entry_ok = True
    if not entry_ok:
        errs.append(f"Python parser must define top-level def {PARSER_ENTRY}(raw_text)")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in PY_ALLOWED_IMPORTS:
                    errs.append(f"import not allowed: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if node.level or root not in PY_ALLOWED_IMPORTS:
                errs.append(f"import not allowed: {'.' * node.level}{node.module or ''}")
        elif isinstance(node, ast.Name):
            if node.id in _PY_DENIED_NAMES or (node.id.startswith("__") and node.id.endswith("__")):
                errs.append(f"name not allowed: {node.id}")
        elif isinstance(node, ast.Attribute):
            if node.attr in _PY_DENIED_ATTRS or (node.attr.startswith("__") and node.attr.endswith("__")):
                errs.append(f"attribute not allowed: .{node.attr}")
    return _dedupe(errs)


def _js_has_entry(code: str, name: str) -> bool:
    pattern = (
        rf"\bfunction\s+{name}\s*\(|\b(?:const|let|var)\s+{name}\s*=|"
        rf"\b(?:window|globalThis)\s*\.\s*{name}\s*=|(?:^|[;\n])\s*{name}\s*=\s*(?:async\s*)?(?:function|\()"
    )
    return re.search(pattern, code) is not None


def _js_denied(code: str, what: str) -> List[str]:
    return [f"{what}: {label} is not allowed" for rx, label in _JS_DENIED if rx.search(code)]


def runtime_validate_javascript_parser(code: Any) -> List[str]:
    """Static checks for a JavaScript parser. Returns a list of problems."""
    errs = _common_errors(code, "JavaScript parser")
    if errs:
        return errs
    if not _js_has_entry(code, PARSER_ENTRY):
        errs.append(f"JavaScript parser must define {PARSER_ENTRY}(raw_text)")
    errs.extend(_js_denied(code, "JavaScript parser"))
    return _dedupe(errs)


def runtime_validate_renderer(code: Any) -> List[str]:
    """Static checks for a Renderer (always vanilla JavaScript)."""
    errs = _common_errors(code, "Renderer")
    if errs:
        return errs
    if not _js_has_entry(code, RENDERER_ENTRY):
        errs.append(f"Renderer must define {RENDERER_ENTRY}(parsed, container)")
    errs.extend(_js_denied(code, "Renderer"))
    return _dedupe(errs)


def runtime_validate_parser(language: Any, code: Any) -> List[str]:
    """Dispatches on *language*. An unknown language is itself a problem."""
    lang = runtime_normalize_language(language)
    if lang == "python":
        return runtime_validate_python_parser(code)
    if lang == "javascript":
        return runtime_validate_javascript_parser(code)
    return [f"Parser_Language must be one of {', '.join(PARSER_LANGUAGES)} (got {language!r})"]


def runtime_javascript_syntax_error(code: str, timeout: float = 10.0) -> Optional[str]:
    """Best-effort syntax check via `node --check`. Returns the error text, or
    None when the code is fine OR node is not installed (the browser sandbox
    reports syntax errors itself at load time)."""
    node = shutil.which("node")
    if not node:
        logger.debug("runtime_javascript_syntax_error: node not available, skipped")
        return None
    tmpdir = tempfile.mkdtemp(prefix="profile_js_")
    try:
        path = f"{tmpdir}/check.js"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(code)
        proc = subprocess.run([node, "--check", path], capture_output=True, text=True,
                              timeout=timeout, cwd=tmpdir, env={})
        if proc.returncode == 0:
            return None
        lines = [ln for ln in proc.stderr.splitlines() if "SyntaxError" in ln]
        return (lines[0] if lines else proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "syntax error")
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("runtime_javascript_syntax_error: check skipped (%s)", exc)
        return None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Execution: python parser (isolated subprocess) ────────────────────────────
_PY_RUNNER = r'''
import sys, json, builtins
cfg = json.loads(sys.argv[1])
try:
    import resource
    for _n, _v in (("RLIMIT_CPU", cfg["cpu"]), ("RLIMIT_AS", cfg["mem"]),
                   ("RLIMIT_FSIZE", 0), ("RLIMIT_NOFILE", 16)):
        try:
            resource.setrlimit(getattr(resource, _n), (_v, _v))
        except Exception:
            pass
except ImportError:
    pass
_real_import = builtins.__import__
_allowed = set(cfg["allowed"])
def _imp(name, globals=None, locals=None, fromlist=(), level=0):
    if level or name.split(".")[0] not in _allowed:
        raise ImportError("import not allowed: " + name)
    return _real_import(name, globals, locals, fromlist, level)
_safe = {n: getattr(builtins, n) for n in cfg["safe"] if hasattr(builtins, n)}
_safe["__import__"] = _imp
def _emit(obj):
    sys.stdout.write(json.dumps(obj))
try:
    payload = json.loads(sys.stdin.read())
    ns = {"__builtins__": _safe, "__name__": "profile_parser"}
    exec(compile(payload["code"], "<profile_parser>", "exec"), ns)
    fn = ns.get(cfg["entry"])
    if not callable(fn):
        raise RuntimeError(cfg["entry"] + "() is not defined")
    result = fn(payload["raw"])
    json.dumps(result)
    _emit({"ok": True, "result": result})
except BaseException as exc:
    _emit({"ok": False, "error": type(exc).__name__ + ": " + str(exc)})
'''


def _finish(proc_stdout: str, proc_returncode: int, proc_stderr: str, lang: str) -> Dict[str, Any]:
    if len(proc_stdout.encode("utf-8")) > MAX_RESULT_BYTES:
        return {"success": False, "reason": f"{lang} parser output exceeds {MAX_RESULT_BYTES} bytes"}
    try:
        payload = json.loads(proc_stdout)
    except ValueError:
        tail = (proc_stderr or "").strip().splitlines()[-1:] or [f"exit code {proc_returncode}"]
        return {"success": False, "reason": f"{lang} parser produced no result ({tail[0]})"}
    if payload.get("ok") and "result" in payload:
        return {"success": True, "result": payload["result"], "reason": ""}
    return {"success": False, "reason": payload.get("error") or f"{lang} parser returned no result"}


def runtime_run_python_parser(
    code: str, raw_text: str, timeout: float = DEFAULT_TIMEOUT_SECONDS, memory_mb: int = 512
) -> Dict[str, Any]:
    """
    Runs a Python parser's parse(raw_text) in an isolated child interpreter
    (-I -S, empty environment, scratch cwd, CPU/memory/file-size rlimits,
    wall-clock timeout, restricted builtins and import allow-list).
    Returns {"success": bool, "result": <json value>, "reason": str}.

    NOTE: this contains mistakes and casual abuse; it is not a hard security
    boundary (CPython cannot offer one in-process). Callers must gate on an
    approved fingerprint first -- gemini_profiles_run_parser() does.
    """
    errs = runtime_validate_python_parser(code)
    if errs:
        return {"success": False, "reason": "; ".join(errs)}
    if not isinstance(raw_text, str) or len(raw_text) > MAX_INPUT_CHARS:
        return {"success": False, "reason": "raw_text must be a string under the input cap"}
    cfg = {
        "allowed": sorted(PY_ALLOWED_IMPORTS), "safe": list(_PY_SAFE_BUILTINS),
        "entry": PARSER_ENTRY, "mem": int(memory_mb) * 1024 * 1024,
        "cpu": max(1, int(timeout) + 1),
    }
    tmpdir = tempfile.mkdtemp(prefix="profile_py_")
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-S", "-c", _PY_RUNNER, json.dumps(cfg)],
            input=json.dumps({"code": code, "raw": raw_text}),
            capture_output=True, text=True, timeout=timeout, cwd=tmpdir,
            env={"PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "reason": f"python parser timed out after {timeout}s"}
    except OSError as exc:
        return {"success": False, "reason": f"python parser could not start: {exc}"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return _finish(proc.stdout, proc.returncode, proc.stderr, "python")


# ── Execution: javascript parser (node vm in a child process) ─────────────────
_NODE_RUNNER = r'''
const vm = require('vm');
const T = parseInt(process.env.PARSER_TIMEOUT_MS || '5000', 10);
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', c => { input += c; });
process.stdin.on('end', () => {
  const out = o => process.stdout.write(JSON.stringify(o));
  try {
    const p = JSON.parse(input);
    const ctx = vm.createContext(Object.create(null));
    vm.runInContext(p.code, ctx, { timeout: T, filename: 'profile_parser.js' });
    if (vm.runInContext('typeof parse', ctx) !== 'function') throw new Error('parse() is not defined');
    ctx.__raw = p.raw;
    const json = vm.runInContext('JSON.stringify(parse(__raw))', ctx, { timeout: T });
    if (json === undefined) throw new Error('parse() returned undefined');
    out({ ok: true, result: JSON.parse(json) });
  } catch (e) {
    out({ ok: false, error: String((e && e.message) || e) });
  }
});
'''


def runtime_run_javascript_parser(
    code: str, raw_text: str, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> Dict[str, Any]:
    """
    Runs a JavaScript parser's parse(raw_text) under node's `vm` module in a
    child process (empty environment, scratch cwd, heap cap, wall-clock
    timeout). For CLI use only; in a browser client use the sandboxed iframe
    from sandbox_build_srcdoc() instead. `vm` is not a security boundary.
    Returns {"success": bool, "result": <json value>, "reason": str}.
    """
    errs = runtime_validate_javascript_parser(code)
    if errs:
        return {"success": False, "reason": "; ".join(errs)}
    if not isinstance(raw_text, str) or len(raw_text) > MAX_INPUT_CHARS:
        return {"success": False, "reason": "raw_text must be a string under the input cap"}
    node = shutil.which("node")
    if not node:
        return {"success": False, "reason": "node is not installed; run JavaScript parsers in the browser sandbox"}
    tmpdir = tempfile.mkdtemp(prefix="profile_js_")
    try:
        proc = subprocess.run(
            [node, "--max-old-space-size=128", "-e", _NODE_RUNNER],
            input=json.dumps({"code": code, "raw": raw_text}),
            capture_output=True, text=True, timeout=timeout + 1.0, cwd=tmpdir,
            env={"PARSER_TIMEOUT_MS": str(int(timeout * 1000))},
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "reason": f"javascript parser timed out after {timeout}s"}
    except OSError as exc:
        return {"success": False, "reason": f"node could not start: {exc}"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return _finish(proc.stdout, proc.returncode, proc.stderr, "javascript")


def runtime_run_parser(
    language: str, code: str, raw_text: str, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> Dict[str, Any]:
    """Runs a parser by language. Does NOT check approval; see
    gemini_profiles_run_parser() for the gated entry point."""
    lang = runtime_normalize_language(language)
    if lang == "python":
        return runtime_run_python_parser(code, raw_text, timeout)
    if lang == "javascript":
        return runtime_run_javascript_parser(code, raw_text, timeout)
    return {"success": False, "reason": f"unsupported parser language: {language!r}"}


# ── Browser sandbox host ──────────────────────────────────────────────────────
_HOST_SCRIPT = r"""(function () {
  var root = document.getElementById('root');
  function send(m) { window.parent.postMessage(m, '*'); }
  function fail(stage, e) { send({ type: 'error', stage: stage, message: String((e && e.message) || e) }); }
  function show(parsed) {
    try {
      if (typeof render === 'function') { render(parsed, root); }
      else { root.style.whiteSpace = 'pre-wrap'; root.textContent = (typeof parsed === 'string') ? parsed : JSON.stringify(parsed, null, 2); }
      send({ type: 'rendered', height: document.documentElement.scrollHeight });
    } catch (e) { fail('render', e); }
  }
  window.addEventListener('message', function (ev) {
    if (ev.source !== window.parent) { return; }
    var d = ev.data || {};
    if (d.type === 'run') {
      if (typeof parse !== 'function') { fail('parse', 'parse() is not defined in the sandbox'); return; }
      var parsed;
      try { parsed = parse(String(d.raw)); } catch (e) { fail('parse', e); return; }
      show(parsed);
    } else if (d.type === 'render') { show(d.parsed); }
  });
  send({ type: 'ready' });
})();"""

SANDBOX_IFRAME_ATTRIBUTES = 'sandbox="allow-scripts"'


def sandbox_build_srcdoc(
    parser_language: Optional[str], parser_code: Optional[str], renderer_code: Optional[str]
) -> str:
    """
    Builds the srcdoc for a sandboxed <iframe>. Raises ValueError if the code
    fails static validation.

    The client MUST create the iframe as
        <iframe sandbox="allow-scripts" srcdoc="...">
    (no allow-same-origin) -- the CSP embedded here blocks all network access
    but cannot impose the sandbox flag itself.

    Message protocol (parent <-> iframe, always check ev.source ===
    iframe.contentWindow on the parent side):
      parent -> iframe  {type:"run", raw:<text>}          JS parser: parse + render
      parent -> iframe  {type:"render", parsed:<value>}   Python parser: render a value
      iframe -> parent  {type:"ready"}                    scripts loaded
      iframe -> parent  {type:"rendered", height:<px>}
      iframe -> parent  {type:"error", stage:"parse"|"render", message:<text>}
    With no Renderer, the parsed value is shown as plain text (JSON when not a string).
    """
    lang = runtime_normalize_language(parser_language)
    problems: List[str] = []
    parser_part = ""
    if parser_code not in (None, ""):
        if lang != "javascript":
            if lang is None:
                problems.append(f"Parser_Language must be one of {', '.join(PARSER_LANGUAGES)}")
        else:
            problems.extend(runtime_validate_javascript_parser(parser_code))
            parser_part = parser_code
    renderer_part = ""
    if renderer_code not in (None, ""):
        problems.extend(runtime_validate_renderer(renderer_code))
        renderer_part = renderer_code
    if problems:
        raise ValueError("; ".join(_dedupe(problems)))
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; "
        "script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<style>html,body{margin:0;padding:0}body{font:14px/1.4 system-ui,sans-serif;"
        "color:#000;background:#fff}@media(prefers-color-scheme:dark){body{color:#fff;"
        "background:#000}}#root{padding:8px;word-break:break-word}</style>"
        "</head><body><div id=\"root\"></div>"
        f"<script>{parser_part}\n</script>"
        f"<script>{renderer_part}\n</script>"
        f"<script>{_HOST_SCRIPT}</script>"
        "</body></html>"
    )
