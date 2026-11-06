"""
Library:        lib_cms_persona_writer.py
Family:         CMS
Description:    PersonaWriter - used by Page_Editor_v2.py and BKS Blog Job
                 system for AI-assisted content generation backed by the
                 CLI_AI 48 AI library family (lib_bejson_AI_ai_dispatch.py /
                 lib_bejson_AI_ai_writing.py).
Version:        2.0
Date:           2026-11-02
Author:         Elton Boehnen
RELATIONAL_ID:  e76634db-20d3-4dc9-b8e3-984f0fa084bg
"""
import os
import sys
import json
import logging

VERSION = 20

# Ensure Core & AI libraries are accessible
LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

try:
    import lib_bejson_CMS_cms_core as CMSCore
    from lib_bejson_Core_bejson_core import bejson_core_get_field_map
except ImportError:
    CMSCore = None
    bejson_core_get_field_map = None

from lib_bejson_AI_ai_writing import ai_writing_call


class PersonaWriter:
    def __init__(self, manifest_path):
        self.manifest_path = manifest_path
        self.db = CMSCore.CMSCore(manifest_path) if CMSCore else None

    def get_persona(self, name):
        if not self.db or not name:
            return None
        try:
            records = self.db.get_records("AI_Profile")
            for r in records:
                if r.get("Name") == name:
                    return r
        except Exception:
            pass
        return None

    def assemble_system_instruction(self, persona):
        if not persona:
            return ""
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

    def dispatch_ai(self, user_input, provider="geminirest", model="gemini-2.5-flash", persona_name=None, system_instruction=None, **config):
        persona = self.get_persona(persona_name) if persona_name else None
        persona_inst = self.assemble_system_instruction(persona) if persona else ""
        combined_sys = "\n\n".join(p for p in [persona_inst, system_instruction] if p) or None
        if persona and "temperature" not in config:
            try:
                config["temperature"] = float(persona.get("Creativity", 0.7))
            except Exception:
                pass
        return ai_writing_call(
            user_input,
            provider=provider or "geminirest",
            model_id=model,
            system_instruction=combined_sys,
            **config,
        )

    def draft_content(self, persona_name, topic, model="gemini-2.5-flash", provider="geminirest"):
        persona = self.get_persona(persona_name)
        sys_inst = self.assemble_system_instruction(persona) if persona else ""
        prompt = f"Write a CMS page about: {topic}. Output ONLY clean HTML body content without Markdown blocks or ``` tags."
        resp = self.dispatch_ai(prompt, provider=provider, model=model, system_instruction=sys_inst)
        if resp.get("success"):
            return resp.get("content", "")
        return f"ERROR ({resp.get('provider', provider)}): {resp.get('error', 'Generation failed')}"
