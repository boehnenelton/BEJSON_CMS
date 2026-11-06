"""
Library:         lib_bejson_Writing_bks_gates.py
Family:          Writing
Module Purpose:  Declarative in-process chapter gates (min_words, max_words, must_include, no_placeholders, md_wellformed). Never runs shell commands.
Architecture:    BKS-1 (BEJSON Book Standard) Writing family. Non-AI book organisation layer built on the frozen Core family (field-map cache, atomic write, validator, list validator). Contains no AI calls and no Flask code. Book Documents are BEJSON 104db; plans are the JobMaker 104a job schema.
Format_Scope:    104db (Book Document) | 104a (JobMaker plan)
Release_Version: 300
Version:         see VERSION below
Date:            2026-10-29
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   9f9d0e40-80a3-4020-90f1-f46ebf05eb85
"""

import re
from typing import List, Optional, Tuple

import lib_bejson_Writing_bks_derive as Derive
import lib_bejson_Writing_bks_errors as Errors

VERSION = "1.0.0"
GATE_KEYS = ("min_words", "max_words", "must_include", "no_placeholders", "md_wellformed")
_PLACEHOLDER_RE = re.compile(r"\b(TODO|TBD|FIXME|lorem ipsum)\b|\[\s*insert[^\]]*\]|\[\.\.\.\]", re.I)
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$", re.M)

# Why: BookType audit profiles expand to a fixed rule set so a gate never depends on a shell (BKS-1 9.4).
# Input: profile name (none|standard|strict), minimum words, required section headings.
# Output: rules dict, or None when the profile is "none".
def bks_gates_rules_for_profile(profile: str, min_words: int = 0, required_sections: Optional[List[str]] = None) -> Optional[dict]:
    if profile == "none":
        return None
    if profile == "standard":
        return {"min_words": min_words, "no_placeholders": True}
    if profile == "strict":
        rules = {"min_words": min_words, "no_placeholders": True, "md_wellformed": True}
        if required_sections:
            rules["must_include"] = list(required_sections)
        return rules
    raise Errors.BKSError(Errors.E_BKS_GATE_UNKNOWN, f"unknown audit profile '{profile}'")

# Why: reject gate vocab typos loudly instead of silently passing text (BKS-1 E_BKS_GATE_UNKNOWN).
def bks_gates_check_rules(rules: Optional[dict]) -> None:
    for key in (rules or {}):
        if key not in GATE_KEYS:
            raise Errors.BKSError(Errors.E_BKS_GATE_UNKNOWN, f"unknown gate rule '{key}'")

# Why: the one in-process audit applied to staged text before a chapter may be committed.
# Input: body text and a rules dict (or None for no gate). Output: (passed, reason); reason is None on pass.
def bks_gates_evaluate(body: Optional[str], rules: Optional[dict]) -> Tuple[bool, Optional[str]]:
    bks_gates_check_rules(rules)
    if not rules:
        return True, None
    text = Derive.bks_derive_normalize_body(body) or ""
    failures: List[str] = []
    words = Derive.bks_derive_count_words(text)
    if rules.get("min_words") and words < rules["min_words"]:
        failures.append(f"min_words={rules['min_words']} not met ({words} words)")
    if rules.get("max_words") and words > rules["max_words"]:
        failures.append(f"max_words={rules['max_words']} exceeded ({words} words)")
    if rules.get("must_include"):
        headings = {h.strip().lower() for h in _HEADING_RE.findall(text)}
        for section in rules["must_include"]:
            if section.strip().lower() not in headings:
                failures.append(f"missing heading '{section}'")
    if rules.get("no_placeholders") and _PLACEHOLDER_RE.search(text):
        failures.append("placeholder text found")
    if rules.get("md_wellformed") and sum(1 for ln in text.split("\n") if ln.lstrip().startswith("```")) % 2:
        failures.append("unclosed code fence")
    if failures:
        return False, "; ".join(failures)
    return True, None
