"""
Library:      lib_bejson_gemprofiles.py
Family:       AI
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      2.1.0 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-06-04
Description:  AI Profile generator for the BEJSON ecosystem.
REMEDIATED:   Delegated field mapping to Core; implemented Safe Get fallbacks (Phase 4.2).
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import sys
import os

# Add parent directory to sys.path to import existing validator
LIB_PATH = os.path.dirname(os.path.abspath(__file__))
CORE_PATH = os.path.join(os.path.dirname(LIB_PATH), "Core")
if CORE_PATH not in sys.path:
    sys.path.append(CORE_PATH)

from lib_bejson_core import bejson_core_get_field_index, bejson_core_get_field_map
import lib_bejson_validator

# --- Legacy Fallback Constants ---
_PROFILES_LEGACY = {
    "Name": 0, "Archetype": 1, "Persona": 2, "SystemInstruction": 3,
    "ForbiddenTopics": 4, "Avatar_Type": 5, "Avatar_sourceUrl": 6,
    "Avatar_Data": 7, "MaxResponseTokens": 8, "Creativity": 9,
    "Tone": 10, "Formality": 11, "Verbosity": 12,
    "EmotionalExpression_Enabled": 13, "EmotionalExpression_Intensity": 14,
    "GoogleSearch_Enabled": 15, "CodeInterpreter_Enabled": 16,
    "EphemeralMemory": 17, "CodeParsing_Mode": 18, "CodeParsing_Languages": 19,
    "CodeParsing_StructureValidation": 20, "CodeParsing_VersionControl": 21,
    "Thinking_Supported": 22
}

# REMEDIATED: Removed "Record_Type_Parent" which is reserved for 104db multi-entity files.
PROFILE_FIELDS = [
    {"name": "Name", "type": "string"},
    {"name": "Archetype", "type": "string"},
    {"name": "Persona", "type": "string"},
    {"name": "SystemInstruction", "type": "string"},
    {"name": "ForbiddenTopics", "type": "array"},
    {"name": "Avatar_Type", "type": "string"},
    {"name": "Avatar_sourceUrl", "type": "string"},
    {"name": "Avatar_Data", "type": "string"},
    {"name": "MaxResponseTokens", "type": "integer"},
    {"name": "Creativity", "type": "number"},
    {"name": "Tone", "type": "array"},
    {"name": "Formality", "type": "string"},
    {"name": "Verbosity", "type": "string"},
    {"name": "EmotionalExpression_Enabled", "type": "boolean"},
    {"name": "EmotionalExpression_Intensity", "type": "number"},
    {"name": "GoogleSearch_Enabled", "type": "boolean"},
    {"name": "CodeInterpreter_Enabled", "type": "boolean"},
    {"name": "EphemeralMemory", "type": "boolean"},
    {"name": "CodeParsing_Mode", "type": "string"},
    {"name": "CodeParsing_Languages", "type": "array"},
    {"name": "CodeParsing_StructureValidation", "type": "boolean"},
    {"name": "CodeParsing_VersionControl", "type": "boolean"},
    {"name": "Thinking_Supported", "type": "boolean"}
]

def bejson_profiles_validate(doc: Dict[str, Any]) -> bool:
    """Validates if a BEJSON document follows the AI Profile schema."""
    try:
        # 1. Standard BEJSON Validation
        lib_bejson_validator.bejson_validator_validate_string(json.dumps(doc))
        
        # 2. Profile-Specific Schema Check
        fields = doc.get("Fields", [])
        field_names = [f["name"] for f in fields]
        required_names = [f["name"] for f in PROFILE_FIELDS]
        
        for req in required_names:
            if req not in field_names:
                return False
        
        # 3. Check Records_Type
        if "AI_Profile" not in doc.get("Records_Type", []):
            return False
            
        return True
    except Exception:
        return False

def bejson_profiles_create(
    name: str,
    archetype: str,
    persona: str,
    instruction: str,
    **kwargs
) -> Dict[str, Any]:
    """Creates a new AI Profile BEJSON document."""
    
    # Default values for profile fields
    values = [
        name,
        archetype,
        persona,
        instruction,
        kwargs.get("ForbiddenTopics", []),
        kwargs.get("Avatar_Type", "Emoji"),
        kwargs.get("Avatar_sourceUrl", ""),
        kwargs.get("Avatar_Data", "🤖"),
        kwargs.get("MaxResponseTokens", 16384),
        kwargs.get("Creativity", 0.7),
        kwargs.get("Tone", ["Professional", "Helpful"]),
        kwargs.get("Formality", "Formal"),
        kwargs.get("Verbosity", "Balanced"),
        kwargs.get("EmotionalExpression_Enabled", False),
        kwargs.get("EmotionalExpression_Intensity", 0.0),
        kwargs.get("GoogleSearch_Enabled", True),
        kwargs.get("CodeInterpreter_Enabled", True),
        kwargs.get("EphemeralMemory", True),
        kwargs.get("CodeParsing_Mode", "complete"),
        kwargs.get("CodeParsing_Languages", []),
        kwargs.get("CodeParsing_StructureValidation", True),
        kwargs.get("CodeParsing_VersionControl", False),
        kwargs.get("Thinking_Supported", True)
    ]

    profile = {
        "Format": "BEJSON",
        "Format_Version": "104",
        "Format_Creator": "Elton Boehnen",
        "Records_Type": ["AI_Profile"],
        "Parent_Hierarchy": "/LLM_Configuration",
        "Fields": PROFILE_FIELDS,
        "Values": [values]
    }
    
    return profile

def bejson_profiles_save(profile: Dict[str, Any], path: str):
    """Saves a profile to a file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)

def bejson_profiles_get_field_index(profile: Dict[str, Any], field_name: str) -> int:
    """
    Returns the index of a field by name, or -1 if not found.
    DEPRECATED: Delegates to bejson_core_get_field_index.
    """
    idx = bejson_core_get_field_index(profile, field_name)
    if idx == -1:
        # Safe Get Fallback
        idx = _PROFILES_LEGACY.get(field_name, -1)
    return idx

def bejson_profiles_get_value(profile: Dict[str, Any], field_name: str, record_index: int = 0) -> Any:
    """Queries a specific field value from a profile record."""
    idx = bejson_profiles_get_field_index(profile, field_name)
    values = profile.get("Values", [])
    if idx != -1 and record_index < len(values) and idx < len(values[record_index]):
        return values[record_index][idx]
    return None

def bejson_profiles_update_value(profile: Dict[str, Any], field_name: str, new_value: Any, record_index: int = 0) -> bool:
    """Updates a specific field value in a profile record. Returns True if successful."""
    idx = bejson_profiles_get_field_index(profile, field_name)
    values = profile.get("Values", [])
    if idx != -1 and record_index < len(values) and idx < len(values[record_index]):
        values[record_index][idx] = new_value
        return True
    return False

def bejson_profiles_query_by_name(profiles_dir: str, profile_name: str) -> Optional[Dict[str, Any]]:
    """Searches a directory for a profile with a specific Name field."""
    path = Path(profiles_dir)
    for file in path.glob("*.bejson"):
        try:
            with open(file, "r") as f:
                doc = json.load(f)
                if bejson_profiles_get_value(doc, "Name") == profile_name:
                    return doc
        except:
            continue
    return None
