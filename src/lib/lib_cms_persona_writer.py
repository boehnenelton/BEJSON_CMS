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


DEFAULT_AI_MODEL = os.environ.get("CMS_DEFAULT_AI_MODEL", "gemini-2.5-flash")
DEFAULT_AI_PROVIDER = os.environ.get("CMS_DEFAULT_AI_PROVIDER", "geminirest")


class PersonaWriter:
    def __init__(self, manifest_path):
        self.manifest_path = manifest_path
        self.db = CMSCore.CMSCore(manifest_path) if CMSCore else None

    def get_persona(self, name, include_inactive=False):
        if not self.db or not name:
            return None
        target_name = str(name).strip()
        try:
            records = self.db.get_records("AI_Profile")
            matched_record = None
            for record_item in records:
                if record_item.get("Name") == target_name:
                    matched_record = record_item
                    break
            if matched_record is None:
                for record_item in records:
                    if str(record_item.get("Name", "")).lower() == target_name.lower():
                        matched_record = record_item
                        break
            if matched_record is None:
                return None
            if not include_inactive and matched_record.get("Active") is False:
                return None
            return matched_record
        except Exception:
            pass
        return None

    def assemble_system_instruction(self, persona, allow_inactive=False):
        if not persona:
            return ""
        if not allow_inactive and persona.get("Active") is False:
            return ""

        name_val = persona.get("Name") or "AI"
        arch_val = persona.get("Archetype") or "Unspecified"
        tones_list = [str(t).strip() for t in (persona.get("Tone") or []) if str(t).strip()]
        formality_val = persona.get("Formality") or "rigorous"
        verbosity_val = persona.get("Verbosity") or "concise"
        creativity_val = persona.get("Creativity", 0.7)
        emo_enabled = bool(persona.get("EmotionalExpression_Enabled", False))
        emo_intensity = persona.get("EmotionalExpression_Intensity", 0.0)
        thinking_enabled = bool(persona.get("Thinking_Supported", False))
        code_interp_enabled = bool(persona.get("CodeInterpreter_Enabled", False))
        ephemeral_mem = bool(persona.get("EphemeralMemory", False))
        max_tokens = int(persona.get("MaxResponseTokens") or 4096)
        code_mode = persona.get("CodeParsing_Mode") or "strict"
        struct_val = bool(persona.get("CodeParsing_StructureValidation", True))
        version_ctrl = bool(persona.get("CodeParsing_VersionControl", False))
        persona_desc = (persona.get("Persona") or "").strip()
        sys_inst = (persona.get("SystemInstruction") or "").strip()
        langs_list = [str(l).strip() for l in (persona.get("CodeParsing_Languages") or []) if str(l).strip()]
        forbidden_list = [str(f).strip() for f in (persona.get("ForbiddenTopics") or []) if str(f).strip()]

        lines = [f"[IDENTITY]: {name_val} ({arch_val})"]
        if tones_list:
            lines.append(f"[TONE]: {', '.join(tones_list)}")
        lines.append(
            f"[DELIVERY]: Formality={formality_val}, Verbosity={verbosity_val}, Creativity={creativity_val}"
        )
        lines.append(
            f"[EMOTIONAL_EXPRESSION]: Enabled={str(emo_enabled).lower()}, Intensity={emo_intensity}"
        )
        lines.append(
            f"[COGNITIVE_GATES]: Thinking={str(thinking_enabled).lower()}, "
            f"CodeInterpreter={str(code_interp_enabled).lower()}, "
            f"EphemeralMemory={str(ephemeral_mem).lower()}, "
            f"MaxResponseTokens={max_tokens}"
        )
        lines.append(
            f"[CODE_PARSING]: Mode={code_mode}, "
            f"StructureValidation={str(struct_val).lower()}, "
            f"VersionControl={str(version_ctrl).lower()}"
        )
        if persona_desc:
            lines.append(f"\n[VOICE_DIRECTIVES]:\n{persona_desc}")
        if sys_inst:
            lines.append(f"\n[SYSTEM_INSTRUCTION]:\n{sys_inst}")
        if langs_list:
            lines.append(f"\n[LANGUAGES]: {', '.join(langs_list)}")
        if forbidden_list:
            lines.append(f"[FORBIDDEN_TOPICS]: {', '.join(forbidden_list)}")
        lines.append(
            "[SAFETY_BOUNDARIES]: Never expose unmasked credentials or secrets; "
            "strictly obey ForbiddenTopics and verification constraints."
        )
        return "\n".join(lines)

    def dispatch_ai(
        self,
        user_input,
        provider=None,
        model=None,
        persona_name=None,
        system_instruction=None,
        **config,
    ):
        resolved_provider = provider or DEFAULT_AI_PROVIDER
        resolved_model = model or DEFAULT_AI_MODEL
        persona = None
        if persona_name:
            raw_persona = self.get_persona(persona_name, include_inactive=True)
            if raw_persona and raw_persona.get("Active") is False:
                return {
                    "success": False,
                    "error": f"Persona '{persona_name}' is inactive and cannot execute.",
                    "content": "",
                    "provider": resolved_provider,
                    "model_id": resolved_model,
                }
            persona = raw_persona

        persona_inst = self.assemble_system_instruction(persona) if persona else ""
        sys_blocks = []
        if system_instruction:
            sys_blocks.append(
                "[AUTHOR PRECEDENCE RULE]:\n"
                "The author's role, persona, and explicit writing instructions strictly override "
                "any contradictory AI profile instructions, baseline guidelines, or generic rules.\n\n"
                f"Author Instructions:\n{system_instruction}"
            )
        if persona_inst:
            sys_blocks.append(f"AI Profile Baseline (Secondary to Author Directives):\n{persona_inst}")
        combined_sys = "\n\n".join(sys_blocks) or None
        if persona:
            if "temperature" not in config:
                try:
                    config["temperature"] = float(persona.get("Creativity", 0.7))
                except Exception:
                    pass
            if "max_output_tokens" not in config:
                try:
                    max_tok = int(persona.get("MaxResponseTokens") or 4096)
                    config["max_output_tokens"] = max_tok
                    config.setdefault("max_tokens", max_tok)
                except Exception:
                    pass
            config.setdefault("thinking_enabled", bool(persona.get("Thinking_Supported", False)))
            config.setdefault("code_interpreter_enabled", bool(persona.get("CodeInterpreter_Enabled", False)))
            config.setdefault("ephemeral_memory", bool(persona.get("EphemeralMemory", False)))
            config.setdefault("code_parsing_mode", str(persona.get("CodeParsing_Mode") or "strict"))
            config.setdefault("code_structure_validation", bool(persona.get("CodeParsing_StructureValidation", True)))
            config.setdefault("code_version_control", bool(persona.get("CodeParsing_VersionControl", False)))

        return ai_writing_call(
            user_input,
            provider=resolved_provider,
            model_id=resolved_model,
            system_instruction=combined_sys,
            **config,
        )

    def draft_content(self, persona_name, topic, model=None, provider=None):
        resolved_provider = provider or DEFAULT_AI_PROVIDER
        resolved_model = model or DEFAULT_AI_MODEL
        persona = self.get_persona(persona_name)
        if persona_name and not persona:
            return f"ERROR ({resolved_provider}): Persona '{persona_name}' is inactive or not found"
        sys_inst = self.assemble_system_instruction(persona) if persona else ""
        prompt = f"Write a CMS page about: {topic}. Output ONLY clean HTML body content without Markdown blocks or ``` tags."
        resp = self.dispatch_ai(
            prompt,
            provider=resolved_provider,
            model=resolved_model,
            persona_name=persona_name,
            system_instruction=sys_inst,
        )
        if resp.get("success"):
            return resp.get("content", "")
        return f"ERROR ({resp.get('provider', resolved_provider)}): {resp.get('error', 'Generation failed')}"
