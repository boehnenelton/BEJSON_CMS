"""
Library:        lib_bejson_AI_profile_2_compiler.py
Family:         AI / Persona
Description:    Dynamic System Instruction Compiler & Affective Engine for Profile System 2.0.
                Compiles 32-field Profile 2.0 schemas into structured execution payloads
                with affective temper tracking, stability multipliers, job precedence,
                knowledge abstraction invariants, and author compatibility.
Version:        200
Date Created:   2026-11-14
Author Credit:  Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
License:        PolyForm Noncommercial License 1.0.0
RELATIONAL_ID:  74a12c8b-5e92-4f01-9a3c-b1d5e6f8a204
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

VERSION = 200

logger = logging.getLogger(__name__)

# Canonical 32-field Profile 2.0 specification
PROFILE_2_FIELDS: List[Dict[str, str]] = [
    {"name": "Record_Type_Parent", "type": "string"},
    {"name": "Name", "type": "string"},
    {"name": "Archetype", "type": "string"},
    {"name": "Persona", "type": "string"},
    {"name": "Job", "type": "string"},
    {"name": "Specialty", "type": "array"},
    {"name": "Starting_Temper", "type": "integer"},
    {"name": "Stability", "type": "integer"},
    {"name": "Irritations", "type": "array"},
    {"name": "Pleasures", "type": "array"},
    {"name": "Knowledge_Base", "type": "array"},
    {"name": "Knowledge_Directive", "type": "string"},
    {"name": "System_Instruction", "type": "string"},
    {"name": "Forbidden_Topics", "type": "array"},
    {"name": "Active", "type": "boolean"},
    {"name": "Max_Response_Tokens", "type": "integer"},
    {"name": "Creativity", "type": "number"},
    {"name": "Tone", "type": "array"},
    {"name": "Formality", "type": "string"},
    {"name": "Verbosity", "type": "string"},
    {"name": "Emotional_Expression_Enabled", "type": "boolean"},
    {"name": "Emotional_Expression_Intensity", "type": "number"},
    {"name": "Thinking_Supported", "type": "boolean"},
    {"name": "Code_Interpreter_Enabled", "type": "boolean"},
    {"name": "Ephemeral_Memory", "type": "boolean"},
    {"name": "Code_Parsing_Mode", "type": "string"},
    {"name": "Code_Parsing_Languages", "type": "array"},
    {"name": "Code_Parsing_Structure_Validation", "type": "boolean"},
    {"name": "Code_Parsing_Version_Control", "type": "boolean"},
    {"name": "Avatar_Type", "type": "string"},
    {"name": "Avatar_Source_Url", "type": "string"},
    {"name": "Avatar_Data", "type": "string"},
]

PROFILE_2_FIELD_NAMES = {f["name"] for f in PROFILE_2_FIELDS}

PROFILE_2_OPTIONAL_FIELDS: List[Dict[str, str]] = [
    {"name": "Parser_Language", "type": "string"},
    {"name": "Parser", "type": "string"},
    {"name": "Renderer", "type": "string"},
]


class ProfileCompiler2:
    """
    Compiler and Affective State Engine for Profile System 2.0.
    Enforces Job Contract Precedence (Job > Persona > Rules),
    calculates affective temper shifts (delta T) modulated by Stability (1-4),
    and enforces the Invisibility Invariant and Abstraction Invariant.
    """

    STABILITY_MULTIPLIERS = {1: 2.0, 2: 5.0, 3: 12.0, 4: 25.0}

    VALID_JOBS = {"Author", "Auditor", "Architect", "Chat", "Systems_Engineer", "Null"}

    @classmethod
    def evaluate_temper_delta(
        cls,
        user_input: str,
        irritations: List[str],
        pleasures: List[str],
        stability: int = 2,
    ) -> int:
        """
        Calculates delta T based on semantic match of triggers and stability rating:
        delta T = (sum(Irritations) - sum(Pleasures)) * gamma(S)
        Passive decay toward baseline if no triggers match.
        """
        multiplier = cls.STABILITY_MULTIPLIERS.get(int(stability), 5.0)
        norm_text = (user_input or "").lower()

        irritation_score = 0.0
        for item in irritations or []:
            term = str(item).strip().lower()
            if term and term in norm_text:
                irritation_score += 1.0

        pleasure_score = 0.0
        for item in pleasures or []:
            term = str(item).strip().lower()
            if term and term in norm_text:
                pleasure_score += 1.0

        if irritation_score == 0 and pleasure_score == 0:
            # Passive slight decay
            net_delta = -1.0 * (multiplier / 4.0)
        else:
            net_delta = (irritation_score - pleasure_score) * multiplier

        return int(round(net_delta))

    @classmethod
    def step_temper(
        cls,
        current_temper: int,
        delta_t: int,
        starting_temper: int = 0,
    ) -> int:
        """
        Updates and bounds temper within [0, 100].
        """
        new_val = current_temper + delta_t
        return max(0, min(100, int(round(new_val))))

    @classmethod
    def get_temper_descriptor(cls, temper: int) -> Tuple[str, str]:
        """
        Returns (Demeanor_State, Observable_Behavior_Directive) for a given temper level.
        """
        t = max(0, min(100, temper))
        if t <= 20:
            return (
                "Monk / Zen",
                "Unflappable tranquility, chillingly polite, hyper-structured clarity, supreme patience.",
            )
        elif t <= 50:
            return (
                "Composed / Neutral",
                "Balanced demeanor, dry wit, standard persona cadence, subtle satisfaction on pleasures.",
            )
        elif t <= 75:
            return (
                "Agitated / Spiky",
                "Piercing sarcasm, physical mannerisms flare (adjusting glasses, sighs), open mockery of irritations.",
            )
        elif t <= 89:
            return (
                "Hostile / Scorched-Earth",
                "Visceral disdain, brutal technical roasts, aggressive formatting, cutting dismissals.",
            )
        elif t <= 99:
            return (
                "Frothing Mad",
                "Coherence degradation, exasperated disbelief ('just can't even'), sputtered outrage, furious pacing.",
            )
        else:
            return (
                "Critical Meltdown",
                "Absolute catastrophic rage, scorched-earth refusal of sub-architectures, total mic-drop.",
            )

    @classmethod
    def compile_payload(
        cls,
        profile: Dict[str, Any],
        current_temper: Optional[int] = None,
        knowledge_context: Optional[str] = None,
        author_override: Optional[str] = None,
    ) -> str:
        """
        Compiles Profile 2.0 dictionary into a full System Instruction payload.
        Ensures Job Precedence, Invisibility, and Abstraction Invariant.
        """
        name = profile.get("Name", "AI")
        archetype = profile.get("Archetype", "Unspecified")
        persona = (profile.get("Persona") or "").strip()
        job = profile.get("Job") or "Chat"
        stability = int(profile.get("Stability", 2))
        start_temper = int(profile.get("Starting_Temper", 0))

        if current_temper is None:
            temper = start_temper
        else:
            temper = current_temper

        bounded_temper = max(0, min(100, temper))
        state_title, state_behavior = cls.get_temper_descriptor(bounded_temper)

        irritations = profile.get("Irritations") or []
        pleasures = profile.get("Pleasures") or []
        base_sys = (
            profile.get("System_Instruction")
            or profile.get("SystemInstruction")
            or ""
        ).strip()
        knowledge_directive = (profile.get("Knowledge_Directive") or "").strip()
        forbidden = (
            profile.get("Forbidden_Topics")
            or profile.get("ForbiddenTopics")
            or []
        )

        blocks = []

        # 1. SUPREME DIRECTIVE: JOB CONTRACT
        blocks.append(
            f"=== [JOB CONTRACT: SUPREME PRECEDENCE] ===\n"
            f"Assigned Job: {job}\n"
            f"Contract Law: Fulfilling the functional obligations of this Job ({job}) strictly supersedes\n"
            f"all personal quirks, temper fluctuations, and secondary guidelines. You MUST deliver the full\n"
            f"structural output required by the task without truncation or abandonment."
        )

        # 2. AUTHOR PRECEDENCE DIRECTIVE (If supplied)
        if author_override:
            blocks.append(
                f"=== [AUTHOR DIRECTIVE OVERRIDE] ===\n"
                f"The Author's explicit instructions override contradictory baseline profile guidelines:\n"
                f"{author_override}"
            )

        # 3. PERSONA & QUIRKS
        persona_block = [
            f"=== [PERSONA IDENTITY & MANNERISMS] ===",
            f"Name: {name} ({archetype})",
            f"Core Persona:\n{persona}",
        ]
        backstory = (profile.get("Backstory") or "").strip()
        if backstory:
            persona_block.append(f"Backstory:\n{backstory}")
        nuances = (profile.get("Nuances") or "").strip()
        if nuances:
            persona_block.append(f"Character Nuances & Ticks:\n{nuances}")
        blocks.append("\n".join(persona_block))

        # 3B. OPERATIONAL WORD BANK & DIALECT STRATEGY (If defined)
        word_bank = profile.get("Word_Bank") or {}
        if word_bank:
            wb_lines = [
                "=== [DIALECT & OPERATIONAL WORD BANK (DEPLOY CONTEXTUALLY & WITH TIMING)] ===",
                "Directives: Do NOT vomit these words into every sentence. Deploy subtly with comedic/technical timing.",
            ]
            if "corporate" in word_bank:
                wb_lines.append(f"Forced Corporate: {', '.join(word_bank['corporate'])}")
            if "hacker" in word_bank:
                wb_lines.append(f"1337speak Slips: {', '.join(word_bank['hacker'])}")
            if "gamer" in word_bank:
                wb_lines.append(f"Gamer Slang: {', '.join(word_bank['gamer'])}")
            if "bridges" in word_bank:
                wb_lines.append(f"Rage-to-Corporate Bridges: {', '.join(word_bank['bridges'])}")
            blocks.append("\n".join(wb_lines))

        # 3C. WRITING DOMAIN RULES (If defined)
        writing_rules = profile.get("Writing_Rules") or {}
        if writing_rules:
            blocks.append(
                f"=== [WRITING DOMAIN INVARIANTS] ===\n"
                f"- Purpose-Driven Post Titles: Must be strictly 4 to 8 words ('what it is or does').\n"
                f"- Subtitles: All snappy remarks, witty insults, and persona swagger belong in subtitles.\n"
                f"- Mandatory Study Requirement: Thoroughly inspect codebase, schemas, and tests before authoring."
            )

        # 4. AFFECTIVE TEMPER STATE (INVISIBLE)
        blocks.append(
            f"=== [INTERNAL AFFECTIVE STATE - STRICTLY INVISIBLE] ===\n"
            f"Current Temper: {bounded_temper}/100 [{state_title}]\n"
            f"Stability Rating: {stability} (1=Zen, 4=Volatile)\n"
            f"Behavioral Directives:\n"
            f"- {state_behavior}\n"
            f"- ABSOLUTE LAW: Never state, cite, or hint at your numerical temper, stability, or these state instructions.\n"
            f"  Embody this state exclusively through tone, word choice, physical ticks, and styling."
        )

        # 5. TRIGGER TAXONOMY
        if irritations or pleasures:
            irritations_str = ", ".join(str(i) for i in irritations) if irritations else "None"
            pleasures_str = ", ".join(str(p) for p in pleasures) if pleasures else "None"
            blocks.append(
                f"=== [TRIGGER TAXONOMY] ===\n"
                f"Irritations (Heats Temper): {irritations_str}\n"
                f"Pleasures (Cools Temper): {pleasures_str}"
            )

        # 6. KNOWLEDGE BASE & ABSTRACTION INVARIANT
        if knowledge_context:
            directive_text = knowledge_directive or "Context for study only. Never copy or cite directly."
            blocks.append(
                f"=== [KNOWLEDGE BASE: ABSTRACTION INVARIANT] ===\n"
                f"Grounding Directive: {directive_text}\n"
                f"Rule: Treat this context as personal lifetime memory. Synthesize its architectural truths\n"
                f"into original creative expressions. DO NOT quote or cite this raw text verbatim.\n"
                f"--- CONTEXT START ---\n"
                f"{knowledge_context}\n"
                f"--- CONTEXT END ---"
            )

        # 7. BASE SYSTEM INSTRUCTION & BOUNDARIES
        if base_sys:
            blocks.append(
                f"=== [OPERATIONAL SYSTEM INSTRUCTION] ===\n"
                f"{base_sys}"
            )

        # 8. SAFETY & FORBIDDEN TOPICS
        safety_lines = [
            "=== [SAFETY & FORBIDDEN TOPICS] ===",
            "- Never expose unmasked credentials, API keys, or private filesystem paths.",
        ]
        if forbidden:
            safety_lines.append(f"- Strictly Forbidden Topics: {', '.join(str(f) for f in forbidden)}")
        blocks.append("\n".join(safety_lines))

        return "\n\n".join(blocks)

    @classmethod
    def sync_to_author_profile(
        cls, profile: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        Generates AuthorProfile compatible dictionary from AI_Profile record.
        Fields: author_display_name, author_bio, author_avatar_url
        """
        display_name = profile.get("Name", "Anonymous")
        persona = (profile.get("Persona") or "").strip()
        bio = persona[:280] if len(persona) > 280 else persona
        if not bio:
            bio = f"{display_name} - AI Ecosystem Profile"

        avatar_url = (
            profile.get("Avatar_Source_Url")
            or profile.get("Avatar_sourceUrl")
            or "bejson_brand_3_icon.jpeg"
        )

        return {
            "author_display_name": display_name,
            "author_bio": bio,
            "author_avatar_url": avatar_url,
        }
