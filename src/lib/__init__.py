"""
Library:      __init__.py
Family:       HTML3
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      3.0.0 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-29
Description:  Central entry point for the HTML3 library family.
"""

from .lib_html3_version import VERSION, get_version, get_manifest
from .lib_bejson_html3_skeletons import (
    COLOR, BRUTAL_COLOR, CSS_CORE, CSS_BRUTAL, HTML_SKELETON, HTML_SKELETON_BRUTAL
)
from .lib_html3_page_templates import html_page, html_save, html_page_brutal
from .lib_html3_body import (
    html_stats_bar, html_card, html_brutal_card, html_brutal_table,
    html_subtabs, html_tab_content, html_description_list, html_badge,
    html_card_grid, html_code_box, html_toast_system, html_progress_bar,
    html_empty_state, html_accordion, html_breadcrumbs, html_key_value_table
)
from .lib_html3_tables import html_table
from .lib_html3_charts import html_chart
from .lib_html3_animations import html_intro_terminal, html_glitch_reveal
from .lib_html3_clipboard import get_clipboard_js
from .lib_html3_widgets import (
    html_widget, html_gallery, html_video_grid, html_info_box,
    html_standalone_widget, html_carousel, html_code_block
)
from .lib_html3_flask import FlaskDashboard, list_to_bejson
from .lib_html3_metrics import (
    html_metric_card, html_data_distribution, html_summary_statistics
)
from .lib_html3_feed_templates import html_feed, html_card_grid as html_feed_card_grid

__all__ = [
    "VERSION", "get_version", "get_manifest",
    "COLOR", "BRUTAL_COLOR", "CSS_CORE", "CSS_BRUTAL", "HTML_SKELETON", "HTML_SKELETON_BRUTAL",
    "html_page", "html_save", "html_page_brutal",
    "html_stats_bar", "html_card", "html_brutal_card", "html_brutal_table",
    "html_subtabs", "html_tab_content", "html_description_list", "html_badge",
    "html_card_grid", "html_code_box",
    "html_toast_system", "html_progress_bar", "html_empty_state",
    "html_accordion", "html_breadcrumbs", "html_key_value_table",
    "html_table",
    "html_chart",
    "html_intro_terminal", "html_glitch_reveal",
    "get_clipboard_js",
    "html_widget", "html_gallery", "html_video_grid", "html_info_box",
    "html_standalone_widget", "html_carousel", "html_code_block",
    "FlaskDashboard", "list_to_bejson",
    "html_metric_card", "html_data_distribution", "html_summary_statistics",
    "html_feed", "html_feed_card_grid"
]
