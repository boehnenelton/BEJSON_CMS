"""
Library:        lib_cms_persona_writer.py
Family:         CMS
Description:    PersonaWriter - used by Page_Editor_v2.py for AI-assisted
                 content generation (Gemini-backed persona/task workflow).
Version:        1.1
Date:           2026-07-27
Author:         Elton Boehnen
RELATIONAL_ID:  d65523ca-19c2-4cb8-afd2-873e9ef973af
"""
import os
import sys
import json
import requests
import time

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
except ImportError:
    CMSCore = None

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
            # BEJSON 104a format: row[1] is typically the key
            valid_keys = [row[1] for row in data.get("Values", []) if len(row) > 1 and row[1] and row[1] != "[REDACTED]"]
            import random
            random.shuffle(valid_keys)
            return valid_keys
        except (json.JSONDecodeError, KeyError, IOError) as e:
            print(f"[PersonaWriter] Error loading keys: {e}")
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
            if r.get("persona_name") == name:
                return r
        return None

    def assemble_system_instruction(self, persona):
        name = persona.get("persona_name", "AI")
        arch = persona.get("persona_archetype", "Persona")
        identity = f"[IDENTITY]: {name} ({arch})"

        tones = persona.get("persona_tone") or []
        voice = f"[VOICE]: {', '.join(tones)}" if isinstance(tones, list) and tones else ""

        quirks_text = persona.get("persona_bio") or ""
        quirks = f"[QUIRKS]: {quirks_text}" if quirks_text else ""

        langs = persona.get("persona_code_parsing_languages") or []
        domain = f"[DOMAIN]: {', '.join(langs)}" if isinstance(langs, list) and langs else ""

        base_inst = persona.get("persona_system_instruction", "")
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
                    "temperature": float(persona.get("persona_creativity", 0.7)),
                    "max_output_tokens": int(persona.get("persona_max_tokens", 8192))
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
                    "maxOutputTokens": int(persona.get("persona_max_tokens", 8192)),
                    "temperature": float(persona.get("persona_creativity", 0.7))
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
