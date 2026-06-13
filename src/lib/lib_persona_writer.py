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
    import lib_cms_core as CMSCore
except ImportError:
    CMSCore = None

class PersonaWriter:
    def __init__(self, manifest_path):
        self.manifest_path = manifest_path
        self.db = CMSCore.CMSCore(manifest_path) if CMSCore else None
        self.api_keys = []
        self.current_key_idx = 0
        self.current_key_idx = 0

    def _load_keys(self):
        # Authoritative path from global context
        key_path = os.path.expanduser("~/.env/gemini_keys.bejson")
        if not os.path.exists(key_path):
            return []
        try:
            with open(key_path, "r") as f:
                data = json.load(f)
            # BEJSON 104a format: row[1] is typically the key
            valid_keys = [row[1] for row in data.get("Values", []) if row[1] and row[1] != "[REDACTED]"]
            import random
            random.shuffle(valid_keys)
            return valid_keys
        except:
            return []

    def _get_key(self):
        self.api_keys = self._load_keys()
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
        tones = persona.get("Tone", [])
        voice = f"[VOICE]: {(', '.join(tones) if isinstance(tones, list) else str(tones))}"
        quirks = f"[QUIRKS]: {str(persona.get('Persona', ''))}"
        langs = persona.get("CodeParsing_Languages", [])
        domain = f"[DOMAIN]: {(', '.join(langs) if isinstance(langs, list) else str(langs))}"
        base_inst = persona.get("SystemInstruction", "")
        return f"{base_inst}\n\n{identity}\n{voice}\n{quirks}\n{domain}"

    def draft_content(self, persona_name, topic, model="gemini-3-flash-preview"):
        persona = self.get_persona(persona_name)
        if not persona: return "ERROR: Persona not found."
        key = self._get_key()
        if not key: return "ERROR: No API keys found."
        
        sys_inst = self.assemble_system_instruction(persona)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        
        payload = {
            "contents": [{"parts": [{"text": f"Write a CMS page about: {topic}. Output ONLY clean HTML body content without Markdown blocks or ``` tags."}]}],
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
                    # Clean up markdown if any
                    if content.startswith("```html"):
                        content = content[7:].strip()
                    elif content.startswith("```"):
                        # Find the first newline
                        nl = content.find("\n")
                        if nl != -1:
                            content = content[nl+1:].strip()
                        else:
                            content = content[3:].strip()
                    if content.endswith("```"):
                        content = content[:-3].strip()
                    return content
            return "ERROR: No content generated."
        except Exception as e:
            return f"ERROR: {str(e)}"
