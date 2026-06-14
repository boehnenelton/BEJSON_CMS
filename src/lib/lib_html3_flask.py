"""
Library:      lib_html3_flask.py
Family:       HTML3
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      3.1.0 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-06-03
Description:  BECSS-compliant middleware for Flask dashboard generation.
RELATIONAL_ID: de2626-flask-optimized-005
"""

import os
import json

try:
    from flask import request
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False
    request = None

VERSION = "3.1.0"
SCRIPT_NAME = "lib_html3_flask.py"
RELATIONAL_ID = "de2626-flask-optimized-005"

# Core UI imports
from lib_bejson_html3_skeletons import COLOR, CSS_CORE, HTML_SKELETON
from lib_html3_page_templates import html_page
from lib_html3_tables import html_table
from lib_html3_body import html_stats_bar, html_card, html_card_grid, html_badge

def list_to_bejson(data_list, entity_name="Entity"):
    """
    Utility: Converts list[dict] (from MFDB) to spec-compliant BEJSON 104a.
    REMEDIATED: Optimized key discovery to single-pass O(N) for better scalability.
    """
    if not data_list:
        return {
            "Format": "BEJSON",
            "Format_Version": "104a",
            "Format_Creator": "Elton Boehnen",
            "Records_Type": [entity_name],
            "Fields": [],
            "Values": []
        }
    
    # 1. Collect all unique keys from all dictionaries in a single pass
    # Using a list for stable order (first seen first kept) but a set for O(1) membership check
    all_keys = []
    keys_set = set()
    for d in data_list:
        for k in d.keys():
            if k not in keys_set:
                all_keys.append(k)
                keys_set.add(k)
    
    # 2. Construct Fields array (Standard 104a)
    fields = [{"name": k, "type": "string"} for k in all_keys]
    
    # 3. Construct Values array ensuring positional integrity
    values = [[d.get(k) for k in all_keys] for d in data_list]
        
    return {
        "Format": "BEJSON",
        "Format_Version": "104a",
        "Format_Creator": "Elton Boehnen",
        "Records_Type": [entity_name],
        "Fields": fields,
        "Values": values
    }

class FlaskDashboard:
    """
    Streamlines Core-Command dashboard creation in Flask.
    """
    def __init__(self, app=None, title="Control Center", nav_links=None, status_extra=""):
        self.app = app
        self.title = title
        self.nav_links = nav_links or []
        self.status_extra = status_extra
        
        if app:
            self.init_app(app)

    def init_app(self, app):
        """Register filters and context processors."""
        @app.context_processor
        def ui_context():
            return {"css_core": CSS_CORE.format(**COLOR), "nav_links": self.nav_links}
            
        app.jinja_env.globals.update(
            html_stats_bar=html_stats_bar,
            html_card=html_card,
            html_badge=html_badge,
            html_table=html_table
        )

    def register_blueprint(self, blueprint):
        """Allows using the dashboard logic within a Flask Blueprint."""
        @blueprint.context_processor
        def ui_context():
            return {"css_core": CSS_CORE.format(**COLOR), "nav_links": self.nav_links}
        
        # Note: app.jinja_env is global, so we don't need to re-register globals if init_app was called on app

    def render(self, page_title, content, active_url="", status_extra=None):
        """Renders a full dashboard page."""
        return html_page(
            title=f"{page_title} - {self.title}",
            content=content,
            nav_links=self.nav_links,
            status_extra=status_extra or self.status_extra,
            active_url=active_url
        )

    def render_table(self, data_list, entity_name="Entity"):
        """Convenience: Renders MFDB data list as a searchable table."""
        if not data_list: return '<div class="c-card">No records found.</div>'
        doc = list_to_bejson(data_list, entity_name)
        return html_table(doc)

def flask_toggle_button(action_url, sid, current_value, label=None):
    """Generates a standard activation/deactivation form/button."""
    is_on = str(current_value).lower() == 'true'
    btn_text = 'DEACTIVATE' if is_on else 'ACTIVATE'
    return f"""
    <form action="{action_url}" method="POST" style="display:inline;">
        <input type="hidden" name="sid" value="{sid}">
        <input type="hidden" name="current" value="{current_value}">
        <button type="submit" class="c-button">{label or btn_text}</button>
    </form>"""

def flask_quick_form(action_url, fields, submit_label="SUBMIT"):
    """
    Generate a simple BECSS form.
    """
    fields_html = ""
    for f in fields:
        fields_html += f'<input type="text" name="{f["name"]}" placeholder="{f["placeholder"]}" required class="c-input u-mb-8">\n'
    
    return f"""
    <div class="c-card">
        <form action="{action_url}" method="POST">
            {fields_html}
            <button type="submit" class="c-button">{submit_label}</button>
        </form>
    </div>"""
