"""
Library:         lib_bejson_Core_bejson_state_management.py
Family:          Core
Module Purpose:  Application state with undo history kept in one BEJSON 104db document (StateNode + History).
Architecture:    BEJSON 104db: ONE file holding 2+ entity types, with a Record_Type_Parent discriminator in column 0, per-field Record_Type_Parent ownership, and null-padding for non-applicable fields. A single-file format; it is not MFDB.
Format_Scope:    104db only (single file; NOT MFDB)
Glossary:        BEJSON 104, 104a and 104db are the three file formats (Format_Version). 104db = ONE file holding 2+ entity types
                 (Record_Type_Parent discriminator, null-padding). MFDB is NOT a format and NOT 104db: it is a layer made of one 104a manifest
                 (104a.mfdb.bejson) plus dense 104 entity files linked by Parent_Hierarchy. MFDB-132 = an MFDB packed into one Chunked-104a document.
Version:         2.0.3
Release_Version: 300
Date:            2026-10-02
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   65b914d4-39c5-4896-936d-ba17329a7635
"""

import json
from datetime import datetime

class BEJSONState:
    """
    Mirror of lib_bejson_Core_bejson_state.js
    Python/Flask-compatible state management using ONE BEJSON 104db document
    (records StateNode + History). Single-file format; this is not an MFDB.
    """
    # Creates the state manager: an in-memory dict plus ONE BEJSON 104db document (records StateNode and History) that mirrors it.
    def __init__(self, schema_name="AppState", initial_state=None):
        self.bejson = {
            "Format": "BEJSON",
            "Format_Version": "104db",
            "Format_Creator": "Elton Boehnen",
            "Records_Type": ["StateNode", "History"],
            "Fields": [
                { "name": "Record_Type_Parent", "type": "string" },
                { "name": "key", "type": "string", "Record_Type_Parent": "StateNode" },
                { "name": "value", "type": "string", "Record_Type_Parent": "StateNode" },
                { "name": "timestamp", "type": "string", "Record_Type_Parent": "History" },
                { "name": "snapshot", "type": "string", "Record_Type_Parent": "History" }
            ],
            "Values": []
        }
        self._state = initial_state or {}
        self._history_index = -1
        self._sync_to_bejson()
        self._save_history()

    # Property: current state dict.
    @property
    def state(self):
        return self._state

    # Sets one key and re-syncs the StateNode rows of the 104db document.
    def set(self, key, value):
        self._state[key] = value
        self._sync_to_bejson()
        self._save_history()

    # Returns one key's value (default when missing).
    def get(self, key, default=None):
        return self._state.get(key, default)

    # Rebuilds the StateNode rows in the 104db document from the state dict, leaving History rows untouched.
    def _sync_to_bejson(self):
        # Clear current StateNodes
        self.bejson["Values"] = [r for r in self.bejson["Values"] if r[0] != "StateNode"]
        # Inject from current state
        for key, value in self._state.items():
            self.bejson["Values"].append(["StateNode", key, json.dumps(value), None, None])

    # Appends a History row (JSON snapshot + timestamp) and moves the undo index.
    def _save_history(self):
        snapshot = json.dumps(self._state)
        timestamp = datetime.now().isoformat()
        self.bejson["Values"].append(["History", None, None, timestamp, snapshot])
        history_rows = [r for r in self.bejson["Values"] if r[0] == "History"]
        self._history_index = len(history_rows) - 1

    # Restores the previous snapshot from History; no-op at the oldest snapshot.
    def undo(self):
        history_rows = [r for r in self.bejson["Values"] if r[0] == "History"]
        if self._history_index <= 0:
            return False
        self._history_index -= 1
        self._state = json.loads(history_rows[self._history_index][4])
        self._sync_to_bejson()
        return True

    # Serializes the 104db state document to a JSON string (indent 2).
    def export_bejson(self):
        return json.dumps(self.bejson, indent=2)