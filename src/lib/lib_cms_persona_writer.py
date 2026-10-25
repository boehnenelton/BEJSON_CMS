"""
Library:        lib_cms_persona_writer.py
Family:         CMS
Description:    PersonaWriter - used by Page_Editor_v2.py for AI-assisted
                 content generation (Gemini-backed persona/task workflow).
Version:        1.2
Date:           2026-10-25
Author:         Elton Boehnen
RELATIONAL_ID:  e76634db-20d3-4dc9-b8e3-984f0fa084bg
"""
import os
import sys
import json
import logging
import requests
import time

VERSION = 12

# Ensure Core libraries are accessible
LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if LIB_DIR not in sys.path:
    sys.path.append(LIB_DIR)

try:
    from google import genai
except ImportError:
    genai = None

try:
    import lib_bejson_CMS_cms_core as CMSCore
    from lib_bejson_Core_bejson_core import bejson_core_get_field_map
except ImportError:
    CMSCore = None
    bejson_core_get_field_map = None

class PersonaWriter:
    def __init__(self, manifest_path):
        self.manifest_path = manifest_path
        self.db = CMSCore.CMSCore(manifest_path) if CMSCore else None
        self.api_keys = self._load_keys() # REC-8: Load and shuffle once
        self.current_key_idx = 0

    def _load_keys(self):
        # Authoritative path from global context via bejson_env
        from lib_bejson_Core_bejson_env import resolve_path
        key_path = resolve_path("{ADMIN_ROOT}/data/.env/gemini_keys.bejson")
        if not os.path.exists(key_path):
            return []
        try:
            with open(key_path, "r") as f:
                data = json.load(f)
            field_map = bejson_core_get_field_map(data) if bejson_core_get_field_map else {}
            key_col_idx = next((field_map[col_name] for col_name in ("key", "api_key", "setting_value", "value") if col_name in field_map), None)
            if key_col_idx is None:
                return []
            valid_keys = [
                row[key_col_idx]
                for row in data.get("Values", [])
                if len(row) > key_col_idx and row[key_col_idx] and row[key_col_idx] != "[REDACTED]"
            ]
            import random
            random.shuffle(valid_keys)
            return valid_keys
        except (json.JSONDecodeError, KeyError, IOError) as e:
            logging.error("[PersonaWriter] Error loading keys: %s", e)
            return []

    def _get_key(self):
        if not self.api_keys: return None
        if self.current_key_idx >= len(self.api_keys): self.current_key_idx = 0
        key = self.api_keys[self.current_key_idx]
        self.current_key_idx += 1
        return key

    def get_persona(self, name):
        if not self.db: return None
        records = self.db.get_records("AI_Profile")
        for r in records:
            if r.get("Name") == name:
                return r
        return None

    def assemble_system_instruction(self, persona):
        name = persona.get("Name", "AI")
        arch = persona.get("Archetype", "Persona")
        identity = f"[IDENTITY]: {name} ({arch})"

        tones = persona.get("Tone") or []
        voice = f"[VOICE]: {', '.join(tones)}" if isinstance(tones, list) and tones else ""

        quirks_text = persona.get("Persona") or ""
        quirks = f"[QUIRKS]: {quirks_text}" if quirks_text else ""

        langs = persona.get("CodeParsing_Languages") or []
        domain = f"[DOMAIN]: {', '.join(langs)}" if isinstance(langs, list) and langs else ""

        base_inst = persona.get("SystemInstruction", "")
        extra_lines = "\n".join(line for line in [identity, voice, quirks, domain] if line)
        return f"{base_inst}\n\n{extra_lines}" if extra_lines else base_inst

    def draft_content(self, persona_name, topic, model="gemini-2.5-flash"):
        persona = self.get_persona(persona_name)
        if not persona: return "ERROR: Persona not found."
        key = self._get_key()
        if not key: return "ERROR: No API keys found."
        
        sys_inst = self.assemble_system_instruction(persona)
        prompt = f"Write a CMS page about: {topic}. Output ONLY clean HTML body content without Markdown blocks or ``` tags."
        
        if genai:
            try:
                client = genai.Client(api_key=key)
                config = {
                    "system_instruction": sys_inst,
                    "temperature": float(persona.get("Creativity", 0.7)),
                    "max_output_tokens": int(persona.get("MaxResponseTokens", 8192))
                }
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config
                )
                return response.text
            except Exception as e:
                return f"ERROR (SDK): {str(e)}"
        else:
            # Fallback to REST if SDK missing (with security warning)
            print("[WARNING] google-genai SDK missing. Falling back to REST (unsecure).")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "system_instruction": {"parts": [{"text": sys_inst}]},
                "generationConfig": {
                    "maxOutputTokens": int(persona.get("MaxResponseTokens", 8192)),
                    "temperature": float(persona.get("Creativity", 0.7))
                }
            }
            
            try:
                res = requests.post(url, json=payload, timeout=90)
                res.raise_for_status()
                data = res.json()
                if "candidates" in data:
                    cands = data["candidates"]
                    if cands and "content" in cands[0] and "parts" in cands[0]["content"]:
                        content = cands[0]["content"]["parts"][0]["text"].strip()
                        return content
                return "ERROR: No content generated."
            except Exception as e:
                return f"ERROR (REST): {str(e)}"
