"""
Library:        lib_bejson_AI_ai_console_log.py
Family:         AI
Description:    Single source of truth for colored terminal status output
                 and file logging across every CLI_AI entry point (the
                 menu, and each of the five prompt_*.py tools). Two things
                 this file solves that were previously missing project-
                 wide: (1) every existing `logger = logging.getLogger(...)`
                 scattered through lib/AI/*.py (e.g.
                 lib_bejson_AI_ai_dispatch.py) had no handler attached
                 anywhere, so anything logged below WARNING vanished and
                 even WARNING+ only ever reached Python's unconfigured
                 "handler of last resort" on stderr, never a file; (2) the
                 four simple prompt_*.py CLIs (groq/openrouter/provocative/
                 huggingface) had zero ANSI color, unlike prompt_menu.py's
                 DE2626 theme and prompt_gemini.py.

                 setup_logging() attaches handlers to the ROOT logger, not
                 a new named one -- this is deliberate: every existing
                 logger in lib/AI and lib/Core (however it's named) has
                 propagate=True by default and no handlers of its own, so
                 once the root logger has handlers, every one of those
                 pre-existing logger.warning()/error() calls throughout the
                 codebase starts reaching the shared log file with zero
                 changes to those files. This respects Library Immutability
                 (Sec 3.5.2 style: Core/AI family libraries are not
                 rewritten to add logging plumbing) while still making
                 "harden everything" logging actually work project-wide.
Version:        1.0.0
Date:           2026-08-19
Author:         Elton Boehnen
Contact:        eltonboehnen@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  9f4a1c7e-3b6d-4a8f-9e2c-1d5b8a0f6c34
Release_Version: 300

Changelog:
  1.0.0 - Initial build.
"""

import logging
import logging.handlers
from pathlib import Path

# --- DE2626 terminal theme (matches prompt_menu.py's existing palette) ---
RED = "\033[38;2;222;38;38m"
DIM_RED = "\033[38;2;140;24;24m"
YELLOW = "\033[38;2;196;160;0m"
WHITE = "\033[97m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

_LOG_LEVEL_NAMES = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_configured = False


def setup_logging(project_root: Path, log_level: str = "INFO") -> logging.Logger:
    """Attaches a rotating file handler (project_root/dev/logs/cli_ai.log,
    5 files x 1MB) and a WARNING+ console handler to the ROOT logger. Safe
    to call from every entry point (menu + each prompt_*.py) -- only
    configures once per process."""
    global _configured
    root_logger = logging.getLogger()
    if _configured:
        return root_logger

    normalized_level = str(log_level).upper().strip()
    if normalized_level not in _LOG_LEVEL_NAMES:
        normalized_level = "INFO"

    log_dir = project_root / "dev" / "logs"
    file_handler_ready = False
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "cli_ai.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s: %(message)s"))
        file_handler_ready = True
    except OSError:
        pass  # degrade to console-only rather than crash the CLI over logging

    root_logger.setLevel(normalized_level)
    if file_handler_ready:
        root_logger.addHandler(file_handler)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(logging.Formatter(f"{DIM}[log] %(levelname)s %(name)s: %(message)s{RESET}"))
    root_logger.addHandler(console_handler)

    _configured = True
    return root_logger


def ok(message: str):
    print(f"{DIM}[*]{RESET} {message}")


def warn(message: str):
    print(f"{YELLOW}[!]{RESET} {message}")
    logging.getLogger("cli_ai.status").warning(message)


def error(message: str):
    print(f"{DIM_RED}[!] {message}{RESET}")
    logging.getLogger("cli_ai.status").error(message)


def heading(text: str):
    print(f"{RED}{BOLD}{text}{RESET}")
