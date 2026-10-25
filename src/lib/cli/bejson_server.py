"""
Library:        bejson_server.py
Family:         Core
Description:    CLI entry point wrapper delegating to canonical src/lib/bejson_server.py
                to eliminate duplicate function bodies across src/lib/ and src/lib/cli/.
Version:        2.2.0
Date:           2026-10-25
Author:         Elton Boehnen
Contact:        boehnenelton2024@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  5c9b3faf-e25d-4418-a75f-b82418a39999
"""

import os
import sys

VERSION = "2.2.0"

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.dirname(_CLI_DIR)
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from bejson_server import (  # noqa: E402,F401
    resolve_path,
    bejson_core_atomic_write,
    ResilientPIDLock,
    copy_to_clipboard,
    open_url,
    is_port_in_use,
    get_random_available_port,
    register_server,
    unregister_server,
    start_flask_server_random,
)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        start_flask_server_random(sys.argv[1])
    else:
        sys.stdout.write("Usage: python3 lib_bejson_server.py <app_path>\n")
