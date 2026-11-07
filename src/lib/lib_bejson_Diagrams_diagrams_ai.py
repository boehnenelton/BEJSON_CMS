"""
Library:        lib_bejson_Diagrams_diagrams_ai.py
Family:         Diagrams
Description:    Prompt-to-diagram builder. Turns a plain-English user prompt
                 into a structured "build plan" (shapes/connectors/
                 territories) via Gemini (lib_bejson_AI_bejson_gemini.py),
                 then the caller (diagram_mfdb.py) executes that plan
                 through its own normal create_shape()/create_connector()/
                 create_territory() calls -- this library never touches an
                 MFDB root directly, it only talks to the model and
                 validates what comes back.
Version:        1.3.0
Date:           2026-10-29
Author:         Elton Boehnen
Contact:        boehnenelton2024@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  8a9f2e1d-4b7c-43e6-90d5-3c1e8b2a7f50
Release_Version: 300
Changelog:
  1.3.0 (2026-10-29) - Merged v3 Diagrammer updates into diagrams_ai_validate_plan_semantics():
          added optional existing_shape_ids and auto_remediate support (fuzzy label-to-tempId
          resolution for parentTempId and connector endpoints, "200px" string-to-float coercion,
          duplicate tempId disambiguation, and unresolved connector filtering).
  1.1.0 (2026-09-25) - Added diagrams_ai_validate_plan_semantics() and fixed AUTHOR_CONTACT_BLOCK.
"""

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from lib_bejson_AI_bejson_gemini import get_standard_api
from lib_bejson_AI_bejson_errors import AIException

from lib_bejson_Diagrams_bejson_errors import (
    AIBuildError,
    E_DIAGRAMS_AI_EMPTY_PROMPT,
    E_DIAGRAMS_AI_BAD_RESPONSE,
    E_DIAGRAMS_AI_INVALID_PLAN,
    E_DIAGRAMS_AI_PROVIDER_ERROR,
    E_DIAGRAMS_AI_SEMANTIC_INVALID,
)

AUTHOR_CONTACT_BLOCK = (
    "Elton Boehnen | boehnenelton2024@gmail.com | boehnenelton2024.pages.dev | "
    "github.com/boehnenelton"
)


def _field_table(fields: List[Dict[str, str]], example_row: Dict[str, Any], title: str) -> str:
    """
    Renders a field list as a spreadsheet-style reference table: one row per
    column, its declared type, and a real example value -- the same
    Fields[]/Values[] pairing BEJSON documents themselves use, just written
    out as prose the model can read without parsing JSON schema.
    """
    lines = [f"{title} (Field | Type | Example value)"]
    for f in fields:
        name = f["name"]
        example = example_row.get(name, "")
        lines.append(f"  - {name} | {f['type']} | {example!r}")
    return "\n".join(lines)


def diagrams_ai_build_system_instructions(
    board_fields: List[Dict[str, str]],
    connector_fields: List[Dict[str, str]],
    territory_fields: List[Dict[str, str]],
    shape_own_fields: List[Dict[str, str]],
    known_size_classes: Iterable[str],
    known_shape_kinds: Iterable[str],
    known_flow_values: Iterable[str],
) -> str:
    """
    Builds the full system instruction text for the diagram-building model.
    Pass in the CALLER's live field lists (diagram_mfdb.py's own
    BOARD_FIELDS/CONNECTOR_FIELDS/TERRITORY_FIELDS/SHAPE_BASE_FIELDS) so this
    stays in sync with whatever the app actually accepts on writes -- this
    library holds no schema copy of its own.
    """
    board_example = {
        "shape_id": "shape_1a2b3c4d5e", "shape_entity_name": "Shape_shape_1a2b3c4d5e",
        "shape_cx": 300, "shape_cy": 150, "shape_size_class": "medium",
        "shape_kind": "rect", "shape_parent_fk": None, "shape_collapsed": False,
    }
    conn_example = {
        "conn_id": "conn_9f8e7d6c5b", "conn_from_fk": "shape_1a2b3c4d5e",
        "conn_to_fk": "shape_2b3c4d5e6f", "conn_flow": "forward",
    }
    terr_example = {
        "terr_id": "terr_5e6f7a8b9c", "terr_kind": "rect", "terr_cx": 450,
        "terr_cy": 150, "terr_size": 300, "terr_label": "Zone A", "terr_color": "#2a6496",
    }
    shape_own_example = {
        "board_membership_fk": "shape_1a2b3c4d5e", "shape_label": "Auth Service",
        "shape_color": "#334455", "shape_font_color": "auto", "shape_text": "",
    }

    size_list = list(known_size_classes)
    kind_list = list(known_shape_kinds)
    flow_list = list(known_flow_values)

    return f"""You are the diagram-building assistant embedded in the BEJSON Diagrammer, a
tool by {AUTHOR_CONTACT_BLOCK}. You turn a user's plain-English request into a
structured diagram build plan for that app's MFDB-backed diagram store.

## How the data is actually shaped (MFDB / BEJSON)

The diagram lives in an MFDB database: one manifest (104a.mfdb.bejson) that
lists entities, each entity a separate table of Fields (columns) and Values
(rows) -- the same shape as a spreadsheet: one header row of column names,
one data row per record. The manifest itself is described the same way:

MFDB manifest (Field | Type | Example value)
  - entity_name | string | 'Board'
  - file_path | string | 'data/board.bejson'
  - description | string | 'One row per shape placed on the board'
  - primary_key | string | 'shape_id'

The diagram has three entities plus each shape's own private entity:

{_field_table(board_fields, board_example, "Board entity -- one row per shape placed on the board")}

{_field_table(shape_own_fields, shape_own_example, "Shape's own entity -- one row, this shape's content")}
  (board_membership_fk on this row equals that shape's shape_id on Board --
  that's the foreign key tying the two together.)

{_field_table(connector_fields, conn_example, "Connector entity -- one row per line between two shapes")}
  (conn_from_fk / conn_to_fk are foreign keys into Board.shape_id.)

{_field_table(territory_fields, terr_example, "Territory entity -- one row per background zone/grouping")}

Known enums -- use ONLY these values:
  - shape_size_class / sizeClass: {size_list}
  - shape_kind / kind: {kind_list}
  - conn_flow / flow: {flow_list}

## Your job

Given the user's prompt, decide what shapes, connectors, and territories
would represent it, and respond with ONLY a single JSON object (no markdown
fences, no prose before or after) matching this build-plan contract:

{{
  "shapes": [
    {{
      "tempId": "s1",
      "label": "Auth Service",
      "kind": "rect",
      "sizeClass": "medium",
      "cx": 300, "cy": 150,
      "color": "#334455",
      "fontColor": "auto",
      "text": "",
      "parentTempId": null
    }}
  ],
  "connectors": [
    {{ "fromTempId": "s1", "toTempId": "s2", "flow": "forward" }}
  ],
  "territories": [
    {{ "kind": "rect", "cx": 450, "cy": 150, "size": 300, "label": "Zone A", "color": "#2a6496" }}
  ]
}}

Rules:
  - "tempId" is YOUR OWN short local id (e.g. "s1", "s2") -- the real
    shape_id doesn't exist yet, it's assigned when the app actually creates
    the shape. Connectors and parentTempId reference these tempIds, never
    real ids.
  - Every connector's fromTempId/toTempId MUST match a tempId you defined
    in "shapes". Every shape's parentTempId MUST be null or another tempId
    you defined (never a shape's own tempId).
  - cx and cy MUST ALWAYS BE NUMERIC values (e.g. 200, 350). Do NOT output
    strings, "px" suffixes, or node IDs for cx/cy.
  - Lay shapes out on a 50px grid, spaced so boxes don't overlap -- medium
    shapes are roughly 200x100, so space centers at least 250-300px apart
    horizontally when connected left-to-right, more for "large"/"huge".
  - color is a hex string (e.g. "#334455"); fontColor is "auto" unless the
    user asks for a specific text color.
  - Omit "connectors" or "territories" entirely (or leave as an empty list)
    if the prompt doesn't call for any.
  - If the request is unclear or not diagram-shaped, return
    {{"shapes": [], "connectors": [], "territories": []}} rather than
    guessing wildly.
  - Respond with ONLY the JSON object. No commentary, no code fences.
"""


def _strip_code_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    return t.strip()


def diagrams_ai_build_plan(user_prompt: str, system_instructions: str,
                            model_id: Optional[str] = None,
                            temperature: float = 0.4,
                            existing_shape_ids: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """
    Calls Gemini with the given system instructions + the user's prompt,
    parses the JSON build plan back out, and structurally validates it
    (every connector/parent reference resolves to a declared tempId) before
    handing it back to the caller to actually execute. Raises AIBuildError
    on any failure -- empty prompt, provider error, unparseable response, or
    an internally-inconsistent plan.
    """
    prompt = (user_prompt or "").strip()
    if not prompt:
        raise AIBuildError("Prompt is empty.", E_DIAGRAMS_AI_EMPTY_PROMPT)

    api = get_standard_api()
    try:
        raw = api.generate(prompt, model_id=model_id,
                            system_instruction=system_instructions,
                            temperature=temperature)
    except AIException as e:
        raise AIBuildError(f"AI provider error: {e}", E_DIAGRAMS_AI_PROVIDER_ERROR)

    cleaned = _strip_code_fences(raw or "")
    try:
        plan = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise AIBuildError(
            f"Model response wasn't valid JSON: {e}", E_DIAGRAMS_AI_BAD_RESPONSE,
            {"raw_response": raw},
        )

    if not isinstance(plan, dict):
        raise AIBuildError("Model response JSON wasn't an object.", E_DIAGRAMS_AI_BAD_RESPONSE,
                            {"raw_response": raw})

    shapes = plan.setdefault("shapes", []) or []
    connectors = plan.setdefault("connectors", []) or []
    plan.setdefault("territories", [])

    temp_ids = set(existing_shape_ids) if existing_shape_ids else set()
    for s in shapes:
        tid = s.get("tempId")
        if not tid:
            raise AIBuildError("A shape in the plan is missing tempId.", E_DIAGRAMS_AI_INVALID_PLAN,
                                {"shape": s})
        if tid in temp_ids:
            raise AIBuildError(f"Duplicate tempId '{tid}' in plan.", E_DIAGRAMS_AI_INVALID_PLAN)
        temp_ids.add(tid)

    for s in shapes:
        pid = s.get("parentTempId")
        if pid is not None and pid not in temp_ids:
            raise AIBuildError(f"Shape '{s.get('tempId')}' parentTempId '{pid}' "
                                f"doesn't match any declared shape tempId.",
                                E_DIAGRAMS_AI_INVALID_PLAN, {"plan": plan})
        if pid == s.get("tempId"):
            raise AIBuildError(f"Shape '{pid}' lists itself as its own parentTempId.",
                                E_DIAGRAMS_AI_INVALID_PLAN)

    for c in connectors:
        for key in ("fromTempId", "toTempId"):
            if c.get(key) not in temp_ids:
                raise AIBuildError(
                    f"Connector {key} '{c.get(key)}' doesn't match any declared shape tempId.",
                    E_DIAGRAMS_AI_INVALID_PLAN, {"plan": plan},
                )

    return plan


_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{3}$|^#[0-9a-fA-F]{6}$|^#[0-9a-fA-F]{8}$")


def _try_parse_coord(val: Any) -> Optional[float]:
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = re.sub(r"px", "", val, flags=re.IGNORECASE).strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def diagrams_ai_validate_plan_semantics(
    plan: Dict[str, Any],
    known_size_classes: Iterable[str],
    known_shape_kinds: Iterable[str],
    known_flow_values: Iterable[str],
    existing_shape_ids: Optional[Iterable[str]] = None,
    auto_remediate: bool = False,
) -> Tuple[List[str], List[str]]:
    """
    Post-reception validation, run AFTER diagrams_ai_build_plan()'s
    structural pass and BEFORE the plan is ever shown to the user for
    approval or executed against the diagram.
    Supports both strict checking (default) and v3 auto-remediation
    (auto_remediate=True or when existing_shape_ids is supplied).
    Never raises: returns (errors, warnings).
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(plan, dict):
        errors.append("Plan root must be an object.")
        return errors, warnings

    size_set = list(known_size_classes)
    kind_set = list(known_shape_kinds)
    flow_set = list(known_flow_values)

    shapes = plan.get("shapes") or []
    connectors = plan.get("connectors") or []
    territories = plan.get("territories") or []

    temp_ids = set(existing_shape_ids) if existing_shape_ids else set()
    label_to_temp_id: Dict[str, str] = {}

    for i, s in enumerate(shapes):
        tid = s.get("tempId")
        if auto_remediate:
            if not tid or not isinstance(tid, str) or not tid.strip():
                tid = f"node_{i + 1}"
                s["tempId"] = tid
                warnings.append(f"Shape at index {i} was missing tempId, auto-assigned '{tid}'.")
            elif tid in temp_ids:
                original = tid
                tid = f"{original}_{i + 1}"
                s["tempId"] = tid
                warnings.append(f"Shape '{original}' had a duplicate tempId, auto-assigned '{tid}'.")
        tid = tid or "?"
        temp_ids.add(tid)

        label = s.get("label")
        if label and str(label).strip():
            label_to_temp_id[str(label).strip().lower()] = tid
        else:
            warnings.append(f"Shape '{tid}': no label -- will show up blank on the board.")

        sc = s.get("sizeClass")
        if sc not in size_set:
            if auto_remediate and sc:
                warnings.append(f"Shape '{tid}' unknown sizeClass '{sc}', defaulting to 'medium'.")
                s["sizeClass"] = "medium"
            else:
                errors.append(f"Shape '{tid}': sizeClass {sc!r} is not one of {size_set}.")

        kind = s.get("kind")
        if kind not in kind_set:
            if auto_remediate and kind:
                warnings.append(f"Shape '{tid}' unknown kind '{kind}', defaulting to 'rect'.")
                s["kind"] = "rect"
            else:
                errors.append(f"Shape '{tid}': kind {kind!r} is not one of {kind_set}.")

        for coord_idx, coord in enumerate(("cx", "cy")):
            raw_val = s.get(coord)
            if isinstance(raw_val, str) and auto_remediate:
                parsed = _try_parse_coord(raw_val)
                if parsed is not None:
                    s[coord] = parsed
                    raw_val = parsed
            if isinstance(raw_val, bool) or not isinstance(raw_val, (int, float)):
                if auto_remediate:
                    fallback = (200 + (i % 4) * 260) if coord_idx == 0 else (200 + (i // 4) * 180)
                    s[coord] = fallback
                    warnings.append(f"Shape '{tid}' {coord} was non-numeric, auto-assigned to {fallback}.")
                else:
                    errors.append(f"Shape '{tid}': {coord} is not numeric ({raw_val!r}).")

        color = s.get("color")
        if color is not None and not _HEX_COLOR_RE.match(str(color)):
            warnings.append(f"Shape '{tid}': color {color!r} doesn't look like a hex color -- "
                             "will likely render oddly.")
        font_color = s.get("fontColor")
        if font_color not in (None, "auto") and not _HEX_COLOR_RE.match(str(font_color)):
            warnings.append(f"Shape '{tid}': fontColor {font_color!r} is neither 'auto' nor a hex color.")

    if auto_remediate:
        for s in shapes:
            pid = s.get("parentTempId")
            if pid and pid not in temp_ids:
                fuzzy = label_to_temp_id.get(str(pid).lower())
                if fuzzy:
                    s["parentTempId"] = fuzzy
                    warnings.append(f"Shape '{s.get('tempId')}' parentTempId resolved to '{fuzzy}' via label matching.")
                else:
                    warnings.append(f"Shape '{s.get('tempId')}' unresolved parentTempId '{pid}', promoted to root.")
                    s["parentTempId"] = None

    valid_connectors = []
    for i, c in enumerate(connectors):
        if auto_remediate:
            from_id = c.get("fromTempId")
            to_id = c.get("toTempId")
            if not from_id or from_id not in temp_ids:
                fuzzy_from = label_to_temp_id.get(str(from_id).lower()) if from_id else None
                if fuzzy_from:
                    c["fromTempId"] = fuzzy_from
            if not to_id or to_id not in temp_ids:
                fuzzy_to = label_to_temp_id.get(str(to_id).lower()) if to_id else None
                if fuzzy_to:
                    c["toTempId"] = fuzzy_to
            if c.get("fromTempId") not in temp_ids or c.get("toTempId") not in temp_ids:
                warnings.append(
                    f"Connector at index {i} ('{c.get('fromTempId')}' -> '{c.get('toTempId')}') "
                    "had unresolved endpoints and was auto-filtered."
                )
                continue

        flow = c.get("flow")
        if flow not in flow_set:
            if auto_remediate and flow:
                warnings.append(f"Connector at index {i} unknown flow '{flow}', defaulting to 'none'.")
                c["flow"] = "none"
            else:
                errors.append(f"Connector #{i} ({c.get('fromTempId')}->{c.get('toTempId')}): "
                               f"flow {flow!r} is not one of {flow_set}.")
        valid_connectors.append(c)

    if auto_remediate:
        plan["connectors"] = valid_connectors

    for i, t in enumerate(territories):
        for coord, default_val in (("cx", 300), ("cy", 300), ("size", 350)):
            raw_val = t.get(coord)
            if isinstance(raw_val, str) and auto_remediate:
                parsed = _try_parse_coord(raw_val)
                if parsed is not None:
                    t[coord] = parsed
                    raw_val = parsed
            if isinstance(raw_val, bool) or not isinstance(raw_val, (int, float)):
                if auto_remediate:
                    t[coord] = default_val
                else:
                    errors.append(f"Territory #{i}: {coord} is not numeric ({raw_val!r}).")
        color = t.get("color")
        if color is not None and not _HEX_COLOR_RE.match(str(color)):
            warnings.append(f"Territory #{i}: color {color!r} doesn't look like a hex color.")

    return errors, warnings
