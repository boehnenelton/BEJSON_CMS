"""
Name:            lib_bejson_CMS_diagrams.py
Description:     CMS diagram format detection, arrival validation, remediation, and inline 3-tab component rendering bridge for BEJSON_CMS.
Version:         10000
Date Created:    2026-11-07
Author Credit:   Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
RELATIONAL_ID:   64b9314e-f6bf-4807-84c7-a2852eae1771
"""

import json
import logging
import re
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lib_bejson_Core_bejson_core import (
    bejson_core_atomic_write,
    bejson_core_get_field_map,
)
from lib_bejson_Diagrams_diagrams_core import (
    DIAGRAM_SCHEMA_TAG,
    diagrams_core_extract_diagram_model_from_mfdb132,
)
from lib_bejson_Diagrams_diagrams_validator import (
    diagrams_validator_validate_package,
    validate_diagram_model,
)
from lib_bejson_HTML_bejson_diagram_validator import (
    bejson_validator_diagram_get_issues,
)

module_diagram_logger_instance = logging.getLogger("BEJSON_CMS.Diagrams")

SCRIPT_DIRECTORY_PATH = Path(__file__).resolve().parent
CMS_ROOT_DIRECTORY_PATH = SCRIPT_DIRECTORY_PATH.parent.parent
DEFAULT_COMPONENT_TEMPLATE_FILE_PATH = (
    CMS_ROOT_DIRECTORY_PATH / "resources" / "templates" / "diagram_component_template.html"
)

DIAGRAM_SIZE_CLASSES_MAP: Dict[str, Dict[str, int]] = {
    "small": {"w": 100, "h": 100},
    "medium": {"w": 200, "h": 100},
    "large": {"w": 300, "h": 150},
    "huge": {"w": 600, "h": 300},
}
DIAGRAM_KNOWN_SIZE_CLASSES_LIST: List[str] = ["small", "medium", "large", "huge"]
DIAGRAM_KNOWN_SHAPE_KINDS_LIST: List[str] = ["rect", "circle"]
DIAGRAM_KNOWN_FLOW_VALUES_LIST: List[str] = ["forward", "backward", "bidirectional", "none"]
DIAGRAM_HEX_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{3,8}$")

HTML_COMPONENT_DATA_SCRIPT_PATTERN = re.compile(
    r'<script\s+(?:class="w-diag-data"|id="injected-diagram-data")\s+type="application/json"\s*>([\s\S]*?)</script>',
    re.IGNORECASE,
)


def cms_diagrams_convert_mfdb_model_to_assembled_dict(
    mfdb_diagram_model_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Converts an in-memory MFDB DiagramModel ({manifest, boardDoc, connectorDoc, territoryDoc, shapeDocs})
    into an assembled diagram dictionary ({diagramId, name, description, shapes, connectors, territories})
    strictly using the O(1) Field Map Cache.
    """
    manifest_document_dict = mfdb_diagram_model_dict.get("manifest") or {}
    board_document_dict = mfdb_diagram_model_dict.get("boardDoc") or {}
    connector_document_dict = mfdb_diagram_model_dict.get("connectorDoc") or {}
    territory_document_dict = mfdb_diagram_model_dict.get("territoryDoc") or {}
    shape_documents_map = mfdb_diagram_model_dict.get("shapeDocs") or {}

    board_field_map = bejson_core_get_field_map(board_document_dict)
    assembled_shapes_list: List[Dict[str, Any]] = []

    for board_row_values in board_document_dict.get("Values", []):
        shape_identifier_str = str(board_row_values[board_field_map["shape_id"]])
        shape_entity_name_str = str(board_row_values[board_field_map["shape_entity_name"]])
        shape_center_x_num = board_row_values[board_field_map["shape_cx"]]
        shape_center_y_num = board_row_values[board_field_map["shape_cy"]]
        shape_size_class_str = str(board_row_values[board_field_map["shape_size_class"]] or "medium")
        shape_kind_str = str(board_row_values[board_field_map["shape_kind"]] or "rect")
        shape_parent_id_val = (
            board_row_values[board_field_map["shape_parent_fk"]]
            if "shape_parent_fk" in board_field_map
            else None
        )
        shape_collapsed_bool = (
            bool(board_row_values[board_field_map["shape_collapsed"]])
            if "shape_collapsed" in board_field_map
            else False
        )

        shape_entity_document_dict = shape_documents_map.get(shape_entity_name_str) or {}
        shape_entity_field_map = (
            bejson_core_get_field_map(shape_entity_document_dict)
            if shape_entity_document_dict.get("Fields")
            else {}
        )
        shape_entity_rows_list = shape_entity_document_dict.get("Values") or []
        first_shape_entity_row = shape_entity_rows_list[0] if shape_entity_rows_list else []

        def _read_shape_field(field_key_name: str, default_field_value: Any) -> Any:
            if field_key_name in shape_entity_field_map and first_shape_entity_row:
                field_column_index = shape_entity_field_map[field_key_name]
                if field_column_index < len(first_shape_entity_row):
                    return first_shape_entity_row[field_column_index]
            return default_field_value

        assembled_shapes_list.append(
            {
                "id": shape_identifier_str,
                "cx": shape_center_x_num,
                "cy": shape_center_y_num,
                "sizeClass": shape_size_class_str,
                "kind": shape_kind_str,
                "label": str(_read_shape_field("shape_label", shape_identifier_str) or ""),
                "color": str(_read_shape_field("shape_color", "#d9d9d9") or "#d9d9d9"),
                "fontColor": str(_read_shape_field("shape_font_color", "auto") or "auto"),
                "text": str(_read_shape_field("shape_text", "") or ""),
                "parentId": shape_parent_id_val if shape_parent_id_val else None,
                "collapsed": shape_collapsed_bool,
            }
        )

    connector_field_map = (
        bejson_core_get_field_map(connector_document_dict)
        if connector_document_dict.get("Fields")
        else {}
    )
    assembled_connectors_list: List[Dict[str, Any]] = []
    for connector_row_values in connector_document_dict.get("Values", []):
        assembled_connectors_list.append(
            {
                "id": str(connector_row_values[connector_field_map["conn_id"]]),
                "from": str(connector_row_values[connector_field_map["conn_from_fk"]]),
                "to": str(connector_row_values[connector_field_map["conn_to_fk"]]),
                "flow": str(
                    connector_row_values[connector_field_map["conn_flow"]]
                    if "conn_flow" in connector_field_map
                    else "forward"
                ),
            }
        )

    territory_field_map = (
        bejson_core_get_field_map(territory_document_dict)
        if territory_document_dict.get("Fields")
        else {}
    )
    assembled_territories_list: List[Dict[str, Any]] = []
    for territory_row_values in territory_document_dict.get("Values", []):
        assembled_territories_list.append(
            {
                "id": str(territory_row_values[territory_field_map["terr_id"]]),
                "kind": str(territory_row_values[territory_field_map["terr_kind"]] or "rect"),
                "cx": territory_row_values[territory_field_map["terr_cx"]],
                "cy": territory_row_values[territory_field_map["terr_cy"]],
                "size": territory_row_values[territory_field_map["terr_size"]],
                "label": str(territory_row_values[territory_field_map["terr_label"]] or ""),
                "color": str(territory_row_values[territory_field_map["terr_color"]] or "#000000"),
            }
        )

    database_name_str = str(manifest_document_dict.get("DB_Name") or "Architecture Diagram")
    return {
        "diagramId": f"diag_{database_name_str.lower().replace(' ', '_')}",
        "name": database_name_str,
        "description": str(manifest_document_dict.get("Schema_Description") or ""),
        "shapes": assembled_shapes_list,
        "connectors": assembled_connectors_list,
        "territories": assembled_territories_list,
    }


def cms_diagrams_parse_raw_content(
    raw_content_text: str, source_filename_str: str = "diagram.json"
) -> Tuple[Optional[Dict[str, Any]], str, List[str], List[str]]:
    """
    Detects and parses any of the 3 supported diagram formats:
      1. Assembled Plan/Diagram JSON (.json with shapes/connectors/territories)
      2. Single-File MFDB-132 Package (.mfdb132.bejson / .bejson with Diagram_Schema == BEJSON-Diagram-1)
      3. Pre-Built Component or Canvas HTML (.html containing <script class="w-diag-data"> or <script id="injected-diagram-data">)
    Returns: (assembled_diagram_dict_or_none, detected_format_label, format_errors_list, format_warnings_list)
    """
    format_errors_list: List[str] = []
    format_warnings_list: List[str] = []
    stripped_content_text = (raw_content_text or "").strip()

    if not stripped_content_text:
        return None, "empty", ["Uploaded diagram file is empty."], []

    lower_filename_str = (source_filename_str or "").lower()

    # Case 1: HTML Component or Canvas file
    if lower_filename_str.endswith(".html") or stripped_content_text.startswith("<!DOCTYPE") or "<html" in stripped_content_text[:256].lower():
        script_match_obj = HTML_COMPONENT_DATA_SCRIPT_PATTERN.search(stripped_content_text)
        if not script_match_obj:
            return (
                None,
                "html_invalid",
                [
                    "HTML file does not contain a valid BEJSON Diagram data script block "
                    "(<script class=\"w-diag-data\" type=\"application/json\"> or "
                    "<script id=\"injected-diagram-data\" type=\"application/json\">)."
                ],
                [],
            )
        extracted_json_payload_str = script_match_obj.group(1).strip()
        try:
            parsed_html_json_dict = json.loads(extracted_json_payload_str)
        except Exception as json_parse_error:
            return (
                None,
                "html_invalid_json",
                [f"Embedded diagram JSON inside HTML is malformed: {json_parse_error}"],
                [],
            )
        if not isinstance(parsed_html_json_dict, dict) or not any(
            required_key in parsed_html_json_dict
            for required_key in ("shapes", "connectors", "territories")
        ):
            return (
                None,
                "html_not_diagram",
                ["Embedded JSON in HTML lacks 'shapes', 'connectors', or 'territories' keys."],
                [],
            )
        return parsed_html_json_dict, "html_component", format_errors_list, format_warnings_list

    # Case 2 & 3: JSON or BEJSON document
    try:
        parsed_json_document = json.loads(stripped_content_text)
    except Exception as json_decode_error:
        return (
            None,
            "invalid_json",
            [f"File is not valid JSON/BEJSON: {json_decode_error}"],
            [],
        )

    if not isinstance(parsed_json_document, dict):
        return (
            None,
            "invalid_root",
            ["Diagram root payload must be a JSON object."],
            [],
        )

    # Check if it is an MFDB-132 package (.mfdb132.bejson / .bejson)
    if (
        parsed_json_document.get("Diagram_Schema") == DIAGRAM_SCHEMA_TAG
        or parsed_json_document.get("Schema_Name") == "MFDB-132"
        or parsed_json_document.get("Package_Format") == "MFDB-Chunked-104a"
    ):
        package_validation_result = diagrams_validator_validate_package(parsed_json_document)
        if not package_validation_result.valid:
            return (
                None,
                "mfdb132_package",
                list(package_validation_result.errors),
                list(package_validation_result.warnings),
            )
        format_warnings_list.extend(package_validation_result.warnings)
        try:
            extracted_mfdb_model_dict = diagrams_core_extract_diagram_model_from_mfdb132(
                parsed_json_document
            )
            mfdb_model_validation = validate_diagram_model(extracted_mfdb_model_dict)
            if not mfdb_model_validation.valid:
                return (
                    None,
                    "mfdb132_package",
                    list(mfdb_model_validation.errors),
                    format_warnings_list + list(mfdb_model_validation.warnings),
                )
            assembled_from_mfdb_dict = cms_diagrams_convert_mfdb_model_to_assembled_dict(
                extracted_mfdb_model_dict
            )
            return (
                assembled_from_mfdb_dict,
                "mfdb132_package",
                format_errors_list,
                format_warnings_list,
            )
        except Exception as mfdb_extraction_error:
            return (
                None,
                "mfdb132_package",
                [f"Failed to extract MFDB-132 diagram model: {mfdb_extraction_error}"],
                format_warnings_list,
            )

    # Check if it is an assembled diagram / plan JSON
    if any(
        diagram_section_key in parsed_json_document
        for diagram_section_key in ("shapes", "connectors", "territories")
    ):
        return parsed_json_document, "assembled_json", format_errors_list, format_warnings_list

    return (
        None,
        "unrecognized_json",
        [
            "JSON document is neither an assembled BEJSON Diagram (missing 'shapes'/'connectors'/'territories') "
            "nor a valid MFDB-132 Diagram package (missing 'Diagram_Schema': 'BEJSON-Diagram-1')."
        ],
        [],
    )


def cms_diagrams_validate_plan_semantics(
    diagram_plan_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validates raw diagram plan semantics (enum membership, numeric coordinates, hex colors, non-empty labels).
    """
    semantic_errors_list: List[str] = []
    semantic_warnings_list: List[str] = []

    if not isinstance(diagram_plan_dict, dict):
        return {
            "valid": False,
            "errors": ["Diagram plan is not a JSON dictionary."],
            "warnings": [],
        }

    seen_shape_identifiers_set = set()
    for shape_index, shape_entry_dict in enumerate(diagram_plan_dict.get("shapes", [])):
        if not isinstance(shape_entry_dict, dict):
            semantic_errors_list.append(f"Shape at index {shape_index} is not an object.")
            continue
        shape_identifier_str = str(
            shape_entry_dict.get("id")
            or shape_entry_dict.get("tempId")
            or f"shape_{shape_index + 1}"
        )
        if shape_identifier_str in seen_shape_identifiers_set:
            semantic_errors_list.append(
                f"Duplicate shape identifier '{shape_identifier_str}'."
            )
        seen_shape_identifiers_set.add(shape_identifier_str)

        shape_size_class_str = str(shape_entry_dict.get("sizeClass", "medium"))
        if shape_size_class_str not in DIAGRAM_KNOWN_SIZE_CLASSES_LIST:
            semantic_errors_list.append(
                f"Shape '{shape_identifier_str}': invalid sizeClass '{shape_size_class_str}'."
            )
        shape_kind_str = str(shape_entry_dict.get("kind", "rect"))
        if shape_kind_str not in DIAGRAM_KNOWN_SHAPE_KINDS_LIST:
            semantic_errors_list.append(
                f"Shape '{shape_identifier_str}': invalid kind '{shape_kind_str}'."
            )
        for coordinate_axis_key in ("cx", "cy"):
            coordinate_value = shape_entry_dict.get(coordinate_axis_key)
            if not isinstance(coordinate_value, (int, float)):
                semantic_errors_list.append(
                    f"Shape '{shape_identifier_str}': {coordinate_axis_key} must be numeric."
                )
        shape_color_str = shape_entry_dict.get("color")
        if shape_color_str and not DIAGRAM_HEX_COLOR_PATTERN.match(str(shape_color_str)):
            semantic_warnings_list.append(
                f"Shape '{shape_identifier_str}': color '{shape_color_str}' is not standard hex."
            )
        shape_label_str = shape_entry_dict.get("label")
        if not shape_label_str or not str(shape_label_str).strip():
            semantic_warnings_list.append(
                f"Shape '{shape_identifier_str}': missing descriptive label."
            )

    for connector_index, connector_entry_dict in enumerate(
        diagram_plan_dict.get("connectors", [])
    ):
        if not isinstance(connector_entry_dict, dict):
            semantic_errors_list.append(
                f"Connector at index {connector_index} is not an object."
            )
            continue
        connector_flow_str = str(connector_entry_dict.get("flow", "forward"))
        if connector_flow_str not in DIAGRAM_KNOWN_FLOW_VALUES_LIST:
            semantic_errors_list.append(
                f"Connector #{connector_index}: invalid flow '{connector_flow_str}'."
            )

    for territory_index, territory_entry_dict in enumerate(
        diagram_plan_dict.get("territories", [])
    ):
        if not isinstance(territory_entry_dict, dict):
            semantic_errors_list.append(
                f"Territory at index {territory_index} is not an object."
            )
            continue
        for territory_numeric_key in ("cx", "cy", "size"):
            territory_numeric_val = territory_entry_dict.get(territory_numeric_key)
            if not isinstance(territory_numeric_val, (int, float)):
                semantic_errors_list.append(
                    f"Territory #{territory_index}: {territory_numeric_key} must be numeric."
                )
        if (territory_entry_dict.get("size") or 0) <= 0:
            semantic_errors_list.append(
                f"Territory #{territory_index}: size must be positive."
            )

    return {
        "valid": len(semantic_errors_list) == 0,
        "errors": semantic_errors_list,
        "warnings": semantic_warnings_list,
    }


def cms_diagrams_remediate_diagram(
    raw_diagram_dict: Dict[str, Any], default_title_str: str = "Architecture Diagram"
) -> Dict[str, Any]:
    """
    Applies the Arrival Validation & Remediation protocol:
      - Normalizes tempId -> id, parentTempId -> parentId, fromTempId -> from, toTempId -> to
      - Quantizes cx, cy to 50px grid increments
      - Strips dangling parentId links, hierarchy cycles, and self-loop/dangling connectors
    """
    remediated_shapes_list: List[Dict[str, Any]] = []
    seen_shape_ids_set = set()

    for shape_index, raw_shape_dict in enumerate(raw_diagram_dict.get("shapes", [])):
        if not isinstance(raw_shape_dict, dict):
            continue
        candidate_shape_id_str = str(
            raw_shape_dict.get("id")
            or raw_shape_dict.get("tempId")
            or f"shape_{shape_index + 1}"
        )
        if candidate_shape_id_str in seen_shape_ids_set:
            candidate_shape_id_str = f"{candidate_shape_id_str}_{shape_index + 1}"
        seen_shape_ids_set.add(candidate_shape_id_str)

        raw_cx_val = raw_shape_dict.get("cx")
        raw_cy_val = raw_shape_dict.get("cy")
        quantized_cx_int = int(
            round((float(raw_cx_val) if isinstance(raw_cx_val, (int, float)) else 300.0) / 50.0) * 50
        )
        quantized_cy_int = int(
            round((float(raw_cy_val) if isinstance(raw_cy_val, (int, float)) else 200.0) / 50.0) * 50
        )

        size_class_str = str(raw_shape_dict.get("sizeClass") or "medium")
        if size_class_str not in DIAGRAM_KNOWN_SIZE_CLASSES_LIST:
            size_class_str = "medium"

        shape_kind_str = str(raw_shape_dict.get("kind") or "rect")
        if shape_kind_str not in DIAGRAM_KNOWN_SHAPE_KINDS_LIST:
            shape_kind_str = "rect"

        parent_identifier_val = (
            raw_shape_dict.get("parentId")
            or raw_shape_dict.get("parentTempId")
            or None
        )

        remediated_shapes_list.append(
            {
                "id": candidate_shape_id_str,
                "label": str(raw_shape_dict.get("label") or f"Node {shape_index + 1}"),
                "text": str(raw_shape_dict.get("text") or ""),
                "kind": shape_kind_str,
                "sizeClass": size_class_str,
                "color": str(raw_shape_dict.get("color") or "#d9d9d9"),
                "fontColor": str(raw_shape_dict.get("fontColor") or "auto"),
                "cx": quantized_cx_int,
                "cy": quantized_cy_int,
                "parentId": str(parent_identifier_val) if parent_identifier_val else None,
            }
        )

    shape_lookup_map: Dict[str, Dict[str, Any]] = {
        shape_item["id"]: shape_item for shape_item in remediated_shapes_list
    }
    for shape_item in remediated_shapes_list:
        if shape_item["parentId"] and shape_item["parentId"] not in shape_lookup_map:
            shape_item["parentId"] = None
        visited_parent_ids_set = set()
        current_cursor_shape = shape_item
        while current_cursor_shape and current_cursor_shape.get("parentId"):
            if current_cursor_shape["id"] in visited_parent_ids_set:
                shape_item["parentId"] = None
                break
            visited_parent_ids_set.add(current_cursor_shape["id"])
            current_cursor_shape = shape_lookup_map.get(current_cursor_shape["parentId"])

    remediated_connectors_list: List[Dict[str, Any]] = []
    seen_connector_pairs_set = set()
    for connector_index, raw_connector_dict in enumerate(
        raw_diagram_dict.get("connectors", [])
    ):
        if not isinstance(raw_connector_dict, dict):
            continue
        source_shape_id_str = str(
            raw_connector_dict.get("from") or raw_connector_dict.get("fromTempId") or ""
        )
        target_shape_id_str = str(
            raw_connector_dict.get("to") or raw_connector_dict.get("toTempId") or ""
        )
        if (
            source_shape_id_str not in shape_lookup_map
            or target_shape_id_str not in shape_lookup_map
            or source_shape_id_str == target_shape_id_str
        ):
            continue
        undirected_pair_tuple = tuple(sorted((source_shape_id_str, target_shape_id_str)))
        if undirected_pair_tuple in seen_connector_pairs_set:
            continue
        seen_connector_pairs_set.add(undirected_pair_tuple)

        connector_flow_str = str(raw_connector_dict.get("flow") or "forward")
        if connector_flow_str not in DIAGRAM_KNOWN_FLOW_VALUES_LIST:
            connector_flow_str = "forward"

        remediated_connectors_list.append(
            {
                "id": str(raw_connector_dict.get("id") or f"conn_{connector_index + 1}"),
                "from": source_shape_id_str,
                "to": target_shape_id_str,
                "flow": connector_flow_str,
            }
        )

    remediated_territories_list: List[Dict[str, Any]] = []
    for territory_index, raw_territory_dict in enumerate(
        raw_diagram_dict.get("territories", [])
    ):
        if not isinstance(raw_territory_dict, dict):
            continue
        raw_terr_cx = raw_territory_dict.get("cx")
        raw_terr_cy = raw_territory_dict.get("cy")
        raw_terr_size = raw_territory_dict.get("size")
        terr_kind_str = str(raw_territory_dict.get("kind") or "rect")
        if terr_kind_str not in DIAGRAM_KNOWN_SHAPE_KINDS_LIST:
            terr_kind_str = "rect"

        remediated_territories_list.append(
            {
                "id": str(raw_territory_dict.get("id") or f"terr_{territory_index + 1}"),
                "kind": terr_kind_str,
                "cx": int(
                    round(
                        (float(raw_terr_cx) if isinstance(raw_terr_cx, (int, float)) else 300.0)
                        / 50.0
                    )
                    * 50
                ),
                "cy": int(
                    round(
                        (float(raw_terr_cy) if isinstance(raw_terr_cy, (int, float)) else 300.0)
                        / 50.0
                    )
                    * 50
                ),
                "size": max(
                    80,
                    int(
                        round(
                            (
                                float(raw_terr_size)
                                if isinstance(raw_terr_size, (int, float))
                                else 240.0
                            )
                            / 50.0
                        )
                        * 50
                    ),
                ),
                "label": str(raw_territory_dict.get("label") or f"Zone {territory_index + 1}"),
                "color": str(raw_territory_dict.get("color") or "#000000"),
            }
        )

    return {
        "diagramId": str(
            raw_diagram_dict.get("diagramId") or f"diag_{secrets.token_hex(4)}"
        ),
        "name": str(
            raw_diagram_dict.get("name")
            or raw_diagram_dict.get("DB_Name")
            or default_title_str
        ),
        "description": str(raw_diagram_dict.get("description") or ""),
        "shapes": remediated_shapes_list,
        "connectors": remediated_connectors_list,
        "territories": remediated_territories_list,
    }


def cms_diagrams_validate_and_remediate(
    raw_content_text: str,
    source_filename_str: str = "diagram.json",
    allow_overlap_as_warning: bool = True,
) -> Dict[str, Any]:
    """
    Full validation & arrival remediation pipeline for BEJSON_CMS:
      1. Detects format (.json assembled plan, .mfdb132.bejson / .bejson package, or .html component/canvas)
      2. Runs plan semantics validation
      3. Runs arrival remediation (50px grid snap, ID normalization, cycle/dangling link cleanup)
      4. Runs 104 HTML Diagram structural validator (bejson_validator_diagram_get_issues)
    Returns a dictionary report with:
      - valid (bool)
      - detected_format (str)
      - errors (List[str])
      - warnings (List[str])
      - diagram (Dict[str, Any] or None)
      - shape_count, connector_count, territory_count
    """
    parsed_diagram_dict, detected_format_str, parse_errors_list, parse_warnings_list = (
        cms_diagrams_parse_raw_content(raw_content_text, source_filename_str)
    )
    if parsed_diagram_dict is None or parse_errors_list:
        return {
            "valid": False,
            "detected_format": detected_format_str,
            "errors": parse_errors_list,
            "warnings": parse_warnings_list,
            "diagram": None,
            "shape_count": 0,
            "connector_count": 0,
            "territory_count": 0,
        }

    plan_semantics_report = cms_diagrams_validate_plan_semantics(parsed_diagram_dict)
    accumulated_errors_list: List[str] = list(plan_semantics_report["errors"])
    accumulated_warnings_list: List[str] = (
        list(parse_warnings_list) + list(plan_semantics_report["warnings"])
    )

    default_title_from_filename = (
        Path(source_filename_str).stem.replace("_", " ").replace("-", " ")
    )
    remediated_diagram_dict = cms_diagrams_remediate_diagram(
        parsed_diagram_dict, default_title_str=default_title_from_filename
    )

    try:
        remediated_json_string = json.dumps(remediated_diagram_dict)
        structural_issues_list = bejson_validator_diagram_get_issues(remediated_json_string)
        for structural_issue_str in structural_issues_list:
            if allow_overlap_as_warning and "overlap" in structural_issue_str.lower():
                accumulated_warnings_list.append(structural_issue_str)
            else:
                accumulated_errors_list.append(structural_issue_str)
    except Exception as validator_exception:
        accumulated_errors_list.append(f"104 Validator error: {validator_exception}")

    return {
        "valid": len(accumulated_errors_list) == 0,
        "detected_format": detected_format_str,
        "errors": accumulated_errors_list,
        "warnings": accumulated_warnings_list,
        "diagram": remediated_diagram_dict,
        "shape_count": len(remediated_diagram_dict.get("shapes", [])),
        "connector_count": len(remediated_diagram_dict.get("connectors", [])),
        "territory_count": len(remediated_diagram_dict.get("territories", [])),
    }


def cms_diagrams_validate_file(
    diagram_file_path_str: str, allow_overlap_as_warning: bool = True
) -> Dict[str, Any]:
    """
    Validates a diagram file on disk and returns the structured validation report.
    """
    target_path_obj = Path(diagram_file_path_str)
    if not target_path_obj.is_file():
        return {
            "valid": False,
            "detected_format": "missing_file",
            "errors": [f"Diagram file not found: {diagram_file_path_str}"],
            "warnings": [],
            "diagram": None,
            "shape_count": 0,
            "connector_count": 0,
            "territory_count": 0,
        }
    try:
        raw_file_text = target_path_obj.read_text(encoding="utf-8")
    except Exception as read_exception:
        return {
            "valid": False,
            "detected_format": "read_error",
            "errors": [f"Could not read file: {read_exception}"],
            "warnings": [],
            "diagram": None,
            "shape_count": 0,
            "connector_count": 0,
            "territory_count": 0,
        }
    return cms_diagrams_validate_and_remediate(
        raw_file_text,
        source_filename_str=target_path_obj.name,
        allow_overlap_as_warning=allow_overlap_as_warning,
    )


def cms_diagrams_render_inline_component(
    diagram_payload_dict: Dict[str, Any],
    custom_title_str: Optional[str] = None,
    template_file_path: Optional[Path] = None,
) -> str:
    """
    Compiles a validated BEJSON Diagram dictionary into an inline, self-contained
    3-tab HTML component widget (<style> + <div class="w-diag-comp" id="w-diag-inst-..."> + <script>)
    suitable for direct injection into a CMS page header or article body without iframe overhead
    and without locking the host page's body scroll or forcing 100vh height.
    """
    resolved_template_path = template_file_path or DEFAULT_COMPONENT_TEMPLATE_FILE_PATH
    if not resolved_template_path.is_file():
        module_diagram_logger_instance.error(
            "Diagram component template missing at %s", resolved_template_path
        )
        return ""

    raw_template_html_str = resolved_template_path.read_text(encoding="utf-8")
    remediated_diagram_dict = cms_diagrams_remediate_diagram(diagram_payload_dict)

    diagram_title_str = (
        custom_title_str
        or remediated_diagram_dict.get("name")
        or "Architecture Diagram"
    )
    diagram_description_str = (
        remediated_diagram_dict.get("description")
        or "Interactive BEJSON 104 Architecture Diagram."
    )
    serialized_diagram_json_str = json.dumps(remediated_diagram_dict, indent=2)
    unique_instance_id_str = "inst_" + secrets.token_hex(4)

    # Extract <style>...</style> block and remove global `html, body { ... }` rule
    style_match_obj = re.search(
        r"<style>([\s\S]*?)</style>", raw_template_html_str, re.IGNORECASE
    )
    extracted_style_css_str = style_match_obj.group(1) if style_match_obj else ""
    extracted_style_css_str = re.sub(
        r"html\s*,\s*body\s*\{[^}]*\}",
        "/* host page body scroll preserved for inline CMS injection */",
        extracted_style_css_str,
        count=1,
    )

    # Extract <div class="w-diag-comp" ...>...</div> body content
    body_match_obj = re.search(
        r"<body>([\s\S]*?)</body>", raw_template_html_str, re.IGNORECASE
    )
    extracted_body_inner_html_str = (
        body_match_obj.group(1).strip() if body_match_obj else raw_template_html_str
    )

    # Disable the standalone full-viewport 100vh override when embedded inline in a CMS page
    extracted_body_inner_html_str = re.sub(
        r"if\s*\(\s*window\.self\s*===\s*window\.top\s*\)\s*\{",
        "if (false && window.self === window.top) {",
        extracted_body_inner_html_str,
    )

    # Inject serialized diagram JSON into <script class="w-diag-data" type="application/json">
    placeholder_regex_pattern = r"/\*\s*__DIAGRAM_DATA__\s*\*/"
    if re.search(placeholder_regex_pattern, extracted_body_inner_html_str):
        extracted_body_inner_html_str = re.sub(
            placeholder_regex_pattern,
            lambda _match: serialized_diagram_json_str,
            extracted_body_inner_html_str,
        )
    else:
        extracted_body_inner_html_str = re.sub(
            r'<script class="w-diag-data" type="application/json">[\s\S]*?</script>',
            lambda _match: (
                f'<script class="w-diag-data" type="application/json">\n'
                f"{serialized_diagram_json_str}\n    </script>"
            ),
            extracted_body_inner_html_str,
        )

    assembled_inline_widget_str = (
        f'<div class="bej-cms-header-diagram" style="margin: 24px 0 32px 0; width: 100%;">\n'
        f"  <style>{extracted_style_css_str}</style>\n"
        f"  {extracted_body_inner_html_str}\n"
        f"</div>"
    )
    assembled_inline_widget_str = assembled_inline_widget_str.replace(
        "__INSTANCE_ID__", unique_instance_id_str
    )
    assembled_inline_widget_str = assembled_inline_widget_str.replace(
        "__DIAGRAM_TITLE__", diagram_title_str
    )
    assembled_inline_widget_str = assembled_inline_widget_str.replace(
        "__DIAGRAM_DESCRIPTION__", diagram_description_str
    )
    return assembled_inline_widget_str


def cms_diagrams_render_inline_from_file(
    diagram_file_path_str: str,
    custom_title_str: Optional[str] = None,
    template_file_path: Optional[Path] = None,
) -> str:
    """
    Loads, validates, remediates, and compiles a diagram file (.json, .bejson, or .html)
    into an inline 3-tab HTML component string. Returns empty string if file is missing or invalid.
    """
    validation_report_dict = cms_diagrams_validate_file(
        diagram_file_path_str, allow_overlap_as_warning=True
    )
    if not validation_report_dict.get("diagram"):
        module_diagram_logger_instance.warning(
            "Cannot render diagram from %s: %s",
            diagram_file_path_str,
            validation_report_dict.get("errors"),
        )
        return ""
    return cms_diagrams_render_inline_component(
        validation_report_dict["diagram"],
        custom_title_str=custom_title_str,
        template_file_path=template_file_path,
    )
