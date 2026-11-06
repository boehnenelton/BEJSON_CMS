"""
Library:         lib_bejson_AI_brain_core_bridge.py
Family:          AI
Module Purpose:  Locates the Core BEJSON/MFDB libraries without hardcoded paths and puts them on sys.path (read-only use).
Architecture:    Searches, relative to this file: a sibling Lib_PY/Core, a project-local lib/, then lib/ beside Lib_PY. Never writes to, copies or modifies Core; Core stays an immutable external dependency.
Version:         1.0.0
Release_Version: 300
Date:            2026-10-24
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   cfd38433-aa28-40d3-be5e-c7e6d2ff0aeb
"""

import logging
import sys
from pathlib import Path

VERSION = "1.0.0"
RELATIONAL_ID = "cfd38433-aa28-40d3-be5e-c7e6d2ff0aeb"

_LOGGER = logging.getLogger("brain.core_bridge")
_CORE_MARKER = "lib_bejson_Core_mfdb_core.py"


# Directories that may hold the Core family, in priority order, all relative to this file.
def _candidate_dirs() -> list[Path]:
    here = Path(__file__).resolve().parent            # .../Lib_PY/AI  or  .../Brain/Lib_PY/AI
    lib_py = here.parent                              # .../Lib_PY
    return [lib_py / "Core", lib_py.parent / "lib", here / "lib", lib_py / "lib"]


# Puts the Brain directory and the first Core directory found on sys.path. Returns the Core directory used. Raises ImportError when none exists.
def brain_core_bridge_install() -> Path:
    here = Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    for candidate in _candidate_dirs():
        if (candidate / _CORE_MARKER).is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            _LOGGER.debug("Core library directory: %s", candidate)
            return candidate
    raise ImportError("Brain could not find the Core library family (looked for Lib_PY/Core or lib/).")


CORE_DIR = brain_core_bridge_install()
