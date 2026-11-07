"""
Library:         lib_bejson_HTML_bejson_diagram_core.py
Family:          HTML
Module Purpose:  Implements runtime functionality and logic for lib_bejson_HTML_bejson_diagram_core.py.
Architecture:    MFDB provides multi-file database federation coordinating a 104a central manifest (104a.mfdb.bejson) with dense 104 entity tables, supporting atomic transaction locks and cross-disk relational foreign keys.
Version:         1.2.0
Release_Version: 300
Date:            2026-07-09
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   c4a8e2f1-9d3b-4a7e-8c05-1f6b3e9a7d24
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Schema constants — MUST stay in lockstep with the live app's
# static/js/diagrammer.js SIZE_CLASSES table. If that table changes, update
# here too; there is no runtime link between the two.
# ---------------------------------------------------------------------------

SIZE_CLASSES = {
    "small":  {"w": 100, "h": 100},
    "medium": {"w": 200, "h": 100},
    "large":  {"w": 300, "h": 150},
    "huge":   {"w": 600, "h": 300},
}

GEN_COLORS = ["transparent", "#2a6496", "#2e7d32", "#e65100", "#6a1a8a"]


# ---------------------------------------------------------------------------
# Loading — mode 1: assembled diagram JSON
# ---------------------------------------------------------------------------

class NotADiagramError(ValueError):
    """Raised when a file lacks any of shapes/connectors/territories entirely
    — i.e. it isn't diagram-shaped data at all, as opposed to a genuinely
    empty diagram (which still has those keys present as empty lists)."""


def load_assembled_diagram(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not any(k in data for k in ("shapes", "connectors", "territories")):
        raise NotADiagramError(
            f"'{path}' has none of the keys 'shapes', 'connectors', or 'territories' — "
            f"this isn't diagram-shaped data. (Found top-level keys: "
            f"{list(data.keys()) if isinstance(data, dict) else type(data).__name__}.) "
            f"A genuinely empty diagram still has these keys present as empty lists; "
            f"a file missing them entirely is a different kind of document."
        )
    return _normalize(data)


def _normalize(data: Dict[str, Any]) -> Dict[str, Any]:
    """Fills in defaults so downstream code never has to guard for missing keys."""
    return {
        "name": data.get("name", "Untitled Diagram"),
        "shapes": [
            {
                "id": s["id"],
                "cx": s["cx"], "cy": s["cy"],
                "sizeClass": s.get("sizeClass", "medium"),
                "kind": s.get("kind", "rect"),
                "label": s.get("label", ""),
                "color": s.get("color", "#334"),
                "fontColor": s.get("fontColor", "auto"),
                "text": s.get("text", ""),
                "parentId": s.get("parentId"),
                "collapsed": bool(s.get("collapsed", False)),
                "custom": s.get("custom", {}),
            }
            for s in data.get("shapes", [])
        ],
        "connectors": [
            {"id": c["id"], "from": c["from"], "to": c["to"], "flow": c.get("flow", "none")}
            for c in data.get("connectors", [])
        ],
        "territories": [
            {
                "id": t["id"], "kind": t.get("kind", "rect"),
                "cx": t["cx"], "cy": t["cy"], "size": t.get("size", 240),
                "label": t.get("label", "Territory"), "color": t.get("color", "#2a6496"),
            }
            for t in data.get("territories", [])
        ],
    }


# ---------------------------------------------------------------------------
# Loading — mode 2: live MFDB diagram folder (manifest + entity files)
# ---------------------------------------------------------------------------

def load_mfdb_diagram(mfdb_root: str) -> Dict[str, Any]:
    """
    Reads a live MFDB diagram folder directly as plain JSON — no dependency
    on the mfdb_core library, so this stays portable. Expects the manifest
    at <mfdb_root>/104a.mfdb.bejson and entity files at the paths it lists.
    Board rows carry shape_entity_name pointing at each shape's own file;
    each shape's own file carries board_membership_fk back to Board.shape_id
    (the required foreign-key linkage — see references/SCHEMA.md).
    """
    manifest_path = os.path.join(mfdb_root, "104a.mfdb.bejson")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    def _entity_doc(entity_name: str) -> Optional[Dict[str, Any]]:
        fi = {f["name"]: i for i, f in enumerate(manifest["Fields"])}
        for row in manifest["Values"]:
            if row[fi["entity_name"]] == entity_name:
                rel_path = row[fi["file_path"]]
                full_path = os.path.join(mfdb_root, rel_path)
                if not os.path.exists(full_path):
                    return None
                with open(full_path, "r", encoding="utf-8") as ef:
                    return json.load(ef)
        return None

    def _rows_as_dicts(doc: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not doc:
            return []
        names = [f["name"] for f in doc["Fields"]]
        return [dict(zip(names, row)) for row in doc["Values"]]

    board_rows = _rows_as_dicts(_entity_doc("Board"))
    conn_rows = _rows_as_dicts(_entity_doc("Connector"))
    terr_rows = _rows_as_dicts(_entity_doc("Territory"))

    shapes = []
    for b in board_rows:
        own_doc = _entity_doc(b["shape_entity_name"])
        own_rows = _rows_as_dicts(own_doc)
        own = own_rows[0] if own_rows else {}
        known = {"board_membership_fk", "shape_label", "shape_color", "shape_font_color", "shape_text"}
        custom = {k: v for k, v in own.items() if k not in known}
        shapes.append({
            "id": b["shape_id"], "cx": b["shape_cx"], "cy": b["shape_cy"],
            "sizeClass": b["shape_size_class"], "kind": b["shape_kind"],
            "label": own.get("shape_label", ""), "color": own.get("shape_color", "#334"),
            "fontColor": own.get("shape_font_color", "auto"), "text": own.get("shape_text", ""),
            "parentId": b.get("shape_parent_fk"), "collapsed": bool(b.get("shape_collapsed", False)),
            "custom": custom,
        })

    connectors = [
        {"id": c["conn_id"], "from": c["conn_from_fk"], "to": c["conn_to_fk"], "flow": c.get("conn_flow", "none")}
        for c in conn_rows
    ]
    territories = [
        {"id": t["terr_id"], "kind": t["terr_kind"], "cx": t["terr_cx"], "cy": t["terr_cy"],
         "size": t["terr_size"], "label": t["terr_label"], "color": t["terr_color"]}
        for t in terr_rows
    ]

    return _normalize({
        "name": manifest.get("DB_Name", "Untitled Diagram"),
        "shapes": shapes, "connectors": connectors, "territories": territories,
    })


# ---------------------------------------------------------------------------
# Geometry — direct port of the live app's edgePoint()/boxOf() logic. Placed
# ahead of validate_diagram() because the overlap check below needs boxOf().
# ---------------------------------------------------------------------------

def _dims(shape: Dict[str, Any]) -> Dict[str, int]:
    return SIZE_CLASSES.get(shape["sizeClass"], SIZE_CLASSES["medium"])


def _box_of(shape: Dict[str, Any]) -> Dict[str, float]:
    d = _dims(shape)
    return {"x": shape["cx"] - d["w"] / 2, "y": shape["cy"] - d["h"] / 2, "w": d["w"], "h": d["h"]}


def _boxes_overlap(a: Dict[str, float], b: Dict[str, float]) -> bool:
    return a["x"] < b["x"] + b["w"] and a["x"] + a["w"] > b["x"] and a["y"] < b["y"] + b["h"] and a["y"] + a["h"] > b["y"]


# ---------------------------------------------------------------------------
# Validation — "Relational Truth": the diagram must reflect exactly what the
# source data says. Never hallucinate a node or link that isn't there.
#
# IMPORTANT — what "no issues" actually means: this function only reports
# what it explicitly checks for below. It is NOT a general correctness or
# quality judgment on the diagram; it's a fixed list of structural rules.
# If you add a new structural rule the live app enforces (or a new class of
# error you've hit in practice), add a check for it here — don't assume
# "validate_diagram() returned []" implies more than it does.
#
# FIX (N6): bump this whenever a structural rule is added/changed above.
# Bump it in the same change that adds the rule, not after the fact.
VALIDATOR_RULES_VERSION = 1
#
# There was previously no mechanism to detect drift between this fixed rule
# set and the live app: if the app grows a new structural rule this
# function doesn't know about, [] silently reads as "clean" with no signal
# that the check is now incomplete - exactly the failure mode the comment
# above warns about, but with nothing to catch it happening. Callers that
# know their own app's rule-set version can now pass it as app_version;
# if it's ahead of VALIDATOR_RULES_VERSION, a drift warning is prepended to
# the issues list. Passing nothing preserves the exact old behavior and
# the empty-list-means-clean contract for existing callers.
# ---------------------------------------------------------------------------

def validate_diagram(diagram: Dict[str, Any], app_version: Optional[int] = None) -> List[str]:
    """Returns a list of human-readable issues. Empty list = clean."""
    issues: List[str] = []

    if app_version is not None and app_version > VALIDATOR_RULES_VERSION:
        issues.append(
            f"[VALIDATOR-DRIFT] app_version ({app_version}) is newer than this "
            f"validator's known rules (VALIDATOR_RULES_VERSION={VALIDATOR_RULES_VERSION}) "
            f"- results may be incomplete. Check for new structural rules the app "
            f"enforces that this function doesn't check for yet."
        )

    shape_ids = {s["id"] for s in diagram["shapes"]}
    shapes_by_id = {s["id"]: s for s in diagram["shapes"]}

    seen_ids = set()
    for s in diagram["shapes"]:
        if s["id"] in seen_ids:
            issues.append(f"Duplicate shape id '{s['id']}'")
        seen_ids.add(s["id"])
        if s["sizeClass"] not in SIZE_CLASSES:
            issues.append(f"Shape '{s['id']}' has unknown sizeClass '{s['sizeClass']}'")
        if s["kind"] not in ("rect", "circle"):
            issues.append(f"Shape '{s['id']}' has unknown kind '{s['kind']}'")
        if s["parentId"] is not None and s["parentId"] not in shape_ids:
            issues.append(f"Shape '{s['id']}' has parentId '{s['parentId']}' which does not exist "
                           f"(hallucinated hierarchy link)")

    # Cycle detection: a chain of parentId references that never reaches a
    # root (None) is invalid — walk the chain from every shape with a
    # visited-set; if we ever revisit a node in the SAME walk, it's a cycle.
    # This was missing before: the earlier check only confirmed each
    # parentId points at *a* real shape, not that the chain terminates.
    for s in diagram["shapes"]:
        visited = set()
        cur = s
        while cur and cur.get("parentId"):
            if cur["id"] in visited:
                issues.append(f"Shape '{s['id']}' is part of a parentId cycle "
                               f"(hierarchy chain never reaches a root — infinite loop)")
                break
            visited.add(cur["id"])
            cur = shapes_by_id.get(cur["parentId"])

    seen_conn_pairs = set()
    for c in diagram["connectors"]:
        if c["from"] not in shape_ids:
            issues.append(f"Connector '{c['id']}' references missing source shape '{c['from']}' "
                           f"(hallucinated link)")
        if c["to"] not in shape_ids:
            issues.append(f"Connector '{c['id']}' references missing target shape '{c['to']}' "
                           f"(hallucinated link)")
        if c["flow"] not in ("none", "forward", "backward", "bidirectional"):
            issues.append(f"Connector '{c['id']}' has unknown flow '{c['flow']}'")
        if c["from"] == c["to"]:
            issues.append(f"Connector '{c['id']}' connects shape '{c['from']}' to itself")
        # Undirected pair dedup — (A,B) and (B,A) are the same visual edge.
        # The live app blocks creating a second one; a diagram that already
        # has both is a real inconsistency, not just a style nit.
        pair = tuple(sorted((c["from"], c["to"])))
        if pair in seen_conn_pairs:
            issues.append(f"Connector '{c['id']}' duplicates an existing connection between "
                           f"'{c['from']}' and '{c['to']}'")
        seen_conn_pairs.add(pair)

    for t in diagram["territories"]:
        if t["kind"] not in ("rect", "circle"):
            issues.append(f"Territory '{t['id']}' has unknown kind '{t['kind']}'")
        if t["size"] <= 0:
            issues.append(f"Territory '{t['id']}' has non-positive size {t['size']}")

    def _terr_box(t):
        return {"x": t["cx"] - t["size"] / 2, "y": t["cy"] - t["size"] / 2, "w": t["size"], "h": t["size"]}

    for i, t1 in enumerate(diagram["territories"]):
        for t2 in diagram["territories"][i + 1:]:
            if _boxes_overlap(_terr_box(t1), _terr_box(t2)):
                issues.append(f"Territories '{t1['id']}' and '{t2['id']}' overlap "
                               f"(territories must not overlap)")

    # Shape-vs-shape overlap — SKILL.md's own "Visual Clutter" red flag says
    # nodes overlapping is a defect, but nothing here actually checked for
    # it until now. Uses the real rendered footprint (sizeClass-derived box),
    # same math the live app uses to block an overlapping drag.
    for i, s1 in enumerate(diagram["shapes"]):
        for s2 in diagram["shapes"][i + 1:]:
            if _boxes_overlap(_box_of(s1), _box_of(s2)):
                issues.append(f"Shapes '{s1['id']}' and '{s2['id']}' overlap "
                               f"(visual clutter — their rendered boxes intersect)")

    return issues


def _children_of(pid: Optional[str], shapes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [s for s in shapes if s.get("parentId") == pid]


def _descendants(pid: str, shapes: List[Dict[str, Any]], out: Optional[set] = None) -> set:
    if out is None:
        out = set()
    for c in _children_of(pid, shapes):
        out.add(c["id"])
        _descendants(c["id"], shapes, out)
    return out


def _hidden_set(shapes: List[Dict[str, Any]]) -> set:
    """
    Direct port of the live app's hiddenSet(): every descendant of a
    collapsed shape is hidden. A static export that ignored this would show
    MORE than the live editor currently shows for the same diagram — a real
    rendering discrepancy, not just a missing nice-to-have.
    """
    hidden: set = set()
    for s in shapes:
        if s.get("collapsed"):
            hidden |= _descendants(s["id"], shapes)
    return hidden


def _edge_point(cx1: float, cy1: float, shape: Dict[str, Any]) -> Dict[str, float]:
    box = _box_of(shape)
    cx2, cy2 = shape["cx"], shape["cy"]
    dx, dy = cx1 - cx2, cy1 - cy2
    if abs(dx) < 0.001 and abs(dy) < 0.001:
        return {"x": cx2, "y": cy2}

    t_min = float("inf")

    def try_t(t):
        nonlocal t_min
        if t <= 1e-6:
            return
        xi, yi = cx2 + t * dx, cy2 + t * dy
        if box["x"] - 0.5 <= xi <= box["x"] + box["w"] + 0.5 and box["y"] - 0.5 <= yi <= box["y"] + box["h"] + 0.5:
            t_min = min(t_min, t)

    if abs(dx) > 0.001:
        try_t((box["x"] - cx2) / dx)
        try_t((box["x"] + box["w"] - cx2) / dx)
    if abs(dy) > 0.001:
        try_t((box["y"] - cy2) / dy)
        try_t((box["y"] + box["h"] - cy2) / dy)

    if t_min == float("inf"):
        return {"x": cx2, "y": cy2}
    return {"x": cx2 + t_min * dx, "y": cy2 + t_min * dy}


def _gen_of(shape_id: str, shapes_by_id: Dict[str, Any]) -> int:
    g, cur = 0, shapes_by_id.get(shape_id)
    while cur and cur.get("parentId"):
        cur = shapes_by_id.get(cur["parentId"])
        g += 1
        if g > 200:
            break
    return g


def _containing_territory(shape: Dict[str, Any], territories: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for t in territories:
        if t["kind"] == "circle":
            dx, dy = shape["cx"] - t["cx"], shape["cy"] - t["cy"]
            if (dx * dx + dy * dy) ** 0.5 <= t["size"] / 2:
                return t
        else:
            b = {"x": t["cx"] - t["size"] / 2, "y": t["cy"] - t["size"] / 2, "w": t["size"], "h": t["size"]}
            if b["x"] <= shape["cx"] <= b["x"] + b["w"] and b["y"] <= shape["cy"] <= b["y"] + b["h"]:
                return t
    return None


def _esc(s: Any) -> str:
    return (str(s or "")
            .replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _text_color_for(hex_color: str, font_color_setting: str) -> str:
    if font_color_setting != "auto":
        return font_color_setting
    hx = str(hex_color).lstrip("#")
    if len(hx) < 6:
        return "#000"
    r, g, b = int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16)
    return "#000" if (r * 299 + g * 587 + b * 114) / 1000 >= 128 else "#fff"


# ---------------------------------------------------------------------------
# HTML export — Universal Style Policy compliant (white background, black
# text/borders, #DE2626 used only sparingly for active/root emphasis, flat
# design, Inter + Source Code Pro). No dark-cyberpunk theme, no glow
# filters, no animation — this is a viewer-only audit artifact.
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} · BEJSON Diagram</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=Source+Code+Pro:wght@400;600&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{ --bg: #ffffff; --fg: #000000; --accent: #DE2626; --muted: #666666; --line: #cccccc; }}
  html, body {{ width: 100%; height: 100%; background: var(--bg); }}
  body {{ font-family: 'Inter', sans-serif; color: var(--fg); }}
  .page {{ display: flex; flex-direction: column; height: 100vh; }}
  .title-bar {{ padding: 14px 24px; background: #ffffff; border-bottom: 2px solid #000000; }}
  .schema-tag {{ font-family: 'Source Code Pro', monospace; font-size: 10px; letter-spacing: 2px; color: var(--muted); text-transform: uppercase; }}
  h1 {{ font-size: 20px; font-weight: 800; letter-spacing: 0.5px; margin-top: 2px; }}
  .diagram-wrapper {{ flex: 1; overflow: auto; background: var(--bg); }}
  #diagram-svg {{ width: 100%; height: 100%; display: block; }}
  .meta-bar {{ padding: 8px 24px; background: #ffffff; border-top: 1px solid var(--line); font-family: 'Source Code Pro', monospace; font-size: 10px; color: var(--muted); display: flex; gap: 20px; }}
  .shape-label {{ font-weight: 800; font-size: 13px; }}
  .shape-body {{ font-weight: 400; font-size: 11px; opacity: 0.85; white-space: pre; }}
</style>
</head>
<body>
<div class="page">
  <header class="title-bar">
    <div class="schema-tag">BEJSON &middot; MFDB DIAGRAM &middot; AUDIT VIEW</div>
    <h1>{title}</h1>
  </header>
  <div class="diagram-wrapper">
    <svg id="diagram-svg" viewBox="{viewbox}" preserveAspectRatio="xMidYMid meet">
      <defs>
        <marker id="me" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#000"/></marker>
        <marker id="ms" markerWidth="10" markerHeight="10" refX="1" refY="3" orient="auto"><path d="M9,0 L9,6 L0,3 z" fill="#000"/></marker>
      </defs>
      {territories_svg}
      {connectors_svg}
      {shapes_svg}
    </svg>
  </div>
  <footer class="meta-bar">
    <span>Format: BEJSON</span><span>Schema: MFDB (center-point + sizeClass)</span>
    <span>Shapes: {shape_count}</span><span>Connectors: {conn_count}</span><span>Territories: {terr_count}</span>
    <span>Exported: {timestamp}</span>
  </footer>
</div>
</body>
</html>
"""


def export_html(diagram: Dict[str, Any], output_path: str, title: Optional[str] = None) -> str:
    """
    Renders the diagram to a single self-contained, static HTML file using
    the flat Viewer-Only Standard template. Returns the output_path.
    """
    title = title or diagram.get("name", "BEJSON Diagram")
    shapes_by_id = {s["id"]: s for s in diagram["shapes"]}
    hidden = _hidden_set(diagram["shapes"])

    terr_svg = []
    for t in diagram["territories"]:
        if t["kind"] == "circle":
            r = t["size"] / 2
            terr_svg.append(
                f'<circle cx="{t["cx"]}" cy="{t["cy"]}" r="{r}" fill="{t["color"]}" opacity="0.38"/>'
                f'<circle cx="{t["cx"]}" cy="{t["cy"]}" r="{r}" fill="none" stroke="{t["color"]}" stroke-width="2.5"/>'
            )
        else:
            x, y = t["cx"] - t["size"] / 2, t["cy"] - t["size"] / 2
            terr_svg.append(
                f'<rect x="{x}" y="{y}" width="{t["size"]}" height="{t["size"]}" fill="{t["color"]}" opacity="0.38"/>'
                f'<rect x="{x}" y="{y}" width="{t["size"]}" height="{t["size"]}" fill="none" stroke="{t["color"]}" stroke-width="2.5"/>'
            )
        tag_w = max(40, len(t["label"]) * 7 + 16)
        lx, ly = (t["cx"] - t["size"] / 2 + 8, t["cy"] - t["size"] / 2 + 4)
        terr_svg.append(
            f'<rect x="{lx}" y="{ly}" width="{tag_w}" height="18" fill="{t["color"]}" opacity="0.9"/>'
            f'<text x="{lx+8}" y="{ly+13}" font-size="10" font-weight="700" fill="#fff">{_esc(t["label"])}</text>'
        )

    conn_svg = []
    for c in diagram["connectors"]:
        s1, s2 = shapes_by_id.get(c["from"]), shapes_by_id.get(c["to"])
        if not s1 or not s2:
            continue  # already flagged by validate_diagram(); never render a hallucinated link
        if s1["id"] in hidden or s2["id"] in hidden:
            continue  # matches live app: connectors touching a collapsed branch's descendants are hidden too
        edge_to = _edge_point(s1["cx"], s1["cy"], s2)
        edge_from = _edge_point(s2["cx"], s2["cy"], s1)
        x1, y1 = s1["cx"], s1["cy"]
        x2, y2 = edge_to["x"], edge_to["y"]
        if c["flow"] in ("backward", "bidirectional"):
            x1, y1 = edge_from["x"], edge_from["y"]
        markers = ""
        if c["flow"] in ("forward", "bidirectional"):
            markers += ' marker-end="url(#me)"'
        if c["flow"] in ("backward", "bidirectional"):
            markers += ' marker-start="url(#ms)"'
        conn_svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#000" stroke-width="2"{markers}/>')

    shape_svg = []
    for s in diagram["shapes"]:
        if s["id"] in hidden:
            continue  # descendant of a collapsed shape — not shown in the live editor either
        box = _box_of(s)
        member = _containing_territory(s, diagram["territories"])
        fill = member["color"] if member else s["color"]
        text_col = _text_color_for(fill, s["fontColor"])
        gen = _gen_of(s["id"], shapes_by_id)
        stripe = GEN_COLORS[min(gen, len(GEN_COLORS) - 1)]

        if s["kind"] == "circle":
            shape_svg.append(
                f'<g transform="translate({box["x"]},{box["y"]})">'
                f'<ellipse cx="{box["w"]/2}" cy="{box["h"]/2}" rx="{box["w"]/2}" ry="{box["h"]/2}" '
                f'fill="{fill}" stroke="#000" stroke-width="2"/>'
            )
        else:
            shape_svg.append(f'<g transform="translate({box["x"]},{box["y"]})">'
                              f'<rect width="{box["w"]}" height="{box["h"]}" fill="{fill}" stroke="#000" stroke-width="2"/>')
            if gen > 0:
                shape_svg.append(f'<rect width="{box["w"]}" height="5" fill="{stripe}"/>')

        body = f'<div class="shape-body">{_esc(s["text"])}</div>' if s["text"] else ""
        shape_svg.append(
            f'<foreignObject width="{box["w"]}" height="{box["h"]}">'
            f'<div xmlns="http://www.w3.org/1999/xhtml" style="width:100%;height:100%;display:flex;'
            f'flex-direction:column;justify-content:center;align-items:center;text-align:center;'
            f'padding:4px;color:{text_col};">'
            f'<div class="shape-label">{_esc(s["label"])}</div>{body}</div></foreignObject></g>'
        )

    visible_shapes = [s for s in diagram["shapes"] if s["id"] not in hidden]
    if visible_shapes:
        boxes = [_box_of(s) for s in visible_shapes]
        min_x = min(b["x"] for b in boxes)
        min_y = min(b["y"] for b in boxes)
        max_x = max(b["x"] + b["w"] for b in boxes)
        max_y = max(b["y"] + b["h"] for b in boxes)
        pad = 80
        viewbox = f"{min_x - pad} {min_y - pad} {max_x - min_x + pad*2} {max_y - min_y + pad*2}"
    else:
        viewbox = "0 0 1000 600"

    visible_conn_count = sum(
        1 for c in diagram["connectors"]
        if c["from"] in shapes_by_id and c["to"] in shapes_by_id
        and c["from"] not in hidden and c["to"] not in hidden
    )
    hidden_count = len(hidden)
    shape_count_label = f"{len(visible_shapes)}" + (f" ({hidden_count} hidden by collapse)" if hidden_count else "")
    conn_count_label = f"{visible_conn_count}" + (
        f" ({len(diagram['connectors']) - visible_conn_count} hidden/invalid)"
        if visible_conn_count != len(diagram["connectors"]) else ""
    )

    html = _HTML_TEMPLATE.format(
        title=_esc(title), viewbox=viewbox,
        territories_svg="".join(terr_svg),
        connectors_svg="".join(conn_svg),
        shapes_svg="".join(shape_svg),
        shape_count=shape_count_label, conn_count=conn_count_label,
        terr_count=len(diagram["territories"]),
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path