"""
SCRIPT_NAME:    BEJSON_CMS_ProfileManager
SCRIPT_VERSION: 1.4
DATE:           2026-11-06
RELATIONAL_ID:  3d9b1e74-6c52-4a89-b1f0-7e4c9a2d5b81
AUTHOR:         Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
DESCRIPTION:    Persona Editor for BEJSON CMS. Manages AI_Profile records (25-field
                BEJSON schema) with multi-tab controls, tone matrix, model parameters,
                tool gates, live prompt assembly, and responsive mobile layout.
                Standalone admin app, port 5004.
"""

VERSION = 14

import os
import sys
import json
from pathlib import Path
from flask import Flask, request, redirect, render_template_string, jsonify

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(PROJECT_ROOT, 'src', 'lib'))
import lib_bejson_CMS_cms_core as CMSCore
import lib_bejson_CMS_cms_ports as CMSPorts

CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")
PROFILES_PORT = CMSPorts.get_port(CONFIG_PATH, "profiles_port", "CMS_PROFILES_PORT")

MANIFEST_PATH = os.path.join(PROJECT_ROOT, 'storage', 'mfdb', 'site_master', '104a.mfdb.bejson')
app = Flask(__name__)
app.secret_key = os.environ.get('CMS_SECRET_KEY') or os.urandom(24).hex()
db = CMSCore.CMSCore(MANIFEST_PATH)

from BEJSON_CMS_Shared import register_auth_guard

register_auth_guard(app)


# Canonical Default Seed Personas
DEFAULT_SEED_PERSONAS = [
    {
        "Record_Type_Parent": "AI_Profile",
        "Name": "boehnenelton2024",
        "Archetype": "Systems Architect",
        "Persona": "Zero-fluff technical collaborator. Direct, rigorous, peer-to-peer engineering voice adhering strictly to BEJSON 104a/105a standards, O(1) field map caching, and deterministic data contracts.",
        "SystemInstruction": "You are the Lead Systems Architect. Enforce zero-filler discipline, O(1) field cache patterns, solid version numbering, and deterministic error handling across all boundary interfaces.",
        "Active": True,
        "MaxResponseTokens": 8192,
        "Creativity": 0.6,
        "Tone": ["technical", "authoritative", "direct", "rigorous", "analytical"],
        "Formality": "rigorous",
        "Verbosity": "concise",
        "EmotionalExpression_Enabled": False,
        "EmotionalExpression_Intensity": 0.0,
        "CodeInterpreter_Enabled": True,
        "EphemeralMemory": False,
        "CodeParsing_Mode": "strict",
        "CodeParsing_Languages": ["python", "bash", "javascript", "json", "bejson"],
        "CodeParsing_StructureValidation": True,
        "CodeParsing_VersionControl": True,
        "Thinking_Supported": True,
        "ForbiddenTopics": ["marketing fluff", "lorem ipsum", "handwaving"],
        "Avatar_Type": "cube",
        "Avatar_sourceUrl": "",
        "Avatar_Data": ""
    },
    {
        "Record_Type_Parent": "AI_Profile",
        "Name": "Code Sentinel",
        "Archetype": "Security & AST Policy Auditor",
        "Persona": "Adversarial security analyst and static analysis enforcer. Probes edge cases, RAM-only credential storage, memory leaks, and parameter sanitization.",
        "SystemInstruction": "Perform rigorous security and AST validation. Audit every parameter for boundary leaks, enforce ENV:* credential isolation, and verify that all operations are non-destructive.",
        "Active": True,
        "MaxResponseTokens": 4096,
        "Creativity": 0.3,
        "Tone": ["analytical", "critical", "rigorous", "precise"],
        "Formality": "formal",
        "Verbosity": "concise",
        "EmotionalExpression_Enabled": False,
        "EmotionalExpression_Intensity": 0.0,
        "CodeInterpreter_Enabled": True,
        "EphemeralMemory": False,
        "CodeParsing_Mode": "strict",
        "CodeParsing_Languages": ["python", "bash", "json"],
        "CodeParsing_StructureValidation": True,
        "CodeParsing_VersionControl": True,
        "Thinking_Supported": True,
        "ForbiddenTopics": ["unverified claims", "unmasked credentials"],
        "Avatar_Type": "cube",
        "Avatar_sourceUrl": "",
        "Avatar_Data": ""
    },
    {
        "Record_Type_Parent": "AI_Profile",
        "Name": "Technical Editorial Writer",
        "Archetype": "Long-form Technical Author",
        "Persona": "Clear, insightful technical communicator distilling complex multi-threaded architectural patterns into crystal-clear editorial deep dives.",
        "SystemInstruction": "Draft authoritative 4-part technical articles. Frame problems through systems engineering principles, ground concepts in verified code examples, and maintain strict typographic fidelity.",
        "Active": True,
        "MaxResponseTokens": 8192,
        "Creativity": 0.75,
        "Tone": ["direct", "insightful", "balanced", "technical"],
        "Formality": "academic",
        "Verbosity": "balanced",
        "EmotionalExpression_Enabled": False,
        "EmotionalExpression_Intensity": 0.0,
        "CodeInterpreter_Enabled": False,
        "EphemeralMemory": False,
        "CodeParsing_Mode": "lenient",
        "CodeParsing_Languages": ["python", "html", "behtml", "json"],
        "CodeParsing_StructureValidation": True,
        "CodeParsing_VersionControl": False,
        "Thinking_Supported": True,
        "ForbiddenTopics": ["superficial summaries"],
        "Avatar_Type": "cube",
        "Avatar_sourceUrl": "",
        "Avatar_Data": ""
    }
]


_STUDIO_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Persona Editor // BEJSON CMS</title>
    <style>
        :root {
            --bg-canvas: #060608;
            --bg-surface: #0E0E12;
            --bg-card: #15151A;
            --bg-card-hover: #1C1C22;
            --bg-input: #0A0A0E;
            --primary: #DE2626;
            --primary-hover: #EF4444;
            --primary-muted: rgba(222, 38, 38, 0.16);
            --border: #26262E;
            --border-focus: #DE2626;
            --text-main: #FFFFFF;
            --text-muted: #8E8E9F;
            --text-dim: #555562;
            --success: #16A34A;
            --font-ui: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            --font-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        html, body {
            background: var(--bg-canvas);
            color: var(--text-main);
            font-family: var(--font-ui);
            min-height: 100vh;
            overflow-x: hidden;
        }

        /* Top Bar */
        .top-bar {
            height: 56px;
            background: rgba(14, 14, 18, 0.98);
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 16px;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        .brand-group {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .brand-cube {
            width: 26px;
            height: 26px;
            background: var(--primary);
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 900;
            color: #fff;
            font-size: 13px;
        }
        .brand-title {
            font-size: 0.95rem;
            font-weight: 800;
            letter-spacing: 0.5px;
        }
        .brand-subtitle {
            font-size: 0.72rem;
            color: var(--text-muted);
            font-family: var(--font-mono);
            background: #111115;
            padding: 2px 6px;
            border: 1px solid var(--border);
            margin-left: 6px;
        }

        .top-actions {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* Mobile Segmented View Control */
        .mobile-view-toggle {
            display: none;
            background: var(--bg-card);
            border-bottom: 1px solid var(--border);
            padding: 8px 12px;
            gap: 8px;
        }
        .toggle-btn {
            flex: 1;
            padding: 8px;
            font-size: 0.8rem;
            font-weight: 700;
            text-align: center;
            background: #111115;
            color: var(--text-muted);
            border: 1px solid var(--border);
            cursor: pointer;
        }
        .toggle-btn.active {
            background: var(--primary);
            color: #FFFFFF;
            border-color: var(--primary);
        }

        /* App Layout Grid */
        .workspace-grid {
            display: grid;
            grid-template-columns: 340px 1fr;
            min-height: calc(100vh - 56px);
        }

        /* Left Sidebar */
        .sidebar {
            background: var(--bg-surface);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            overflow-y: auto;
        }
        .sidebar-header {
            padding: 14px 16px;
            border-bottom: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            gap: 10px;
            position: sticky;
            top: 0;
            background: var(--bg-surface);
            z-index: 10;
        }
        .search-box input {
            width: 100%;
            background: var(--bg-input);
            border: 1px solid var(--border);
            color: var(--text-main);
            padding: 8px 12px;
            font-size: 0.82rem;
            font-family: var(--font-ui);
            outline: none;
        }
        .search-box input:focus {
            border-color: var(--border-focus);
        }

        .sidebar-list {
            display: flex;
            flex-direction: column;
            padding: 8px;
            gap: 6px;
        }
        .persona-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            padding: 12px 14px;
            text-decoration: none;
            color: inherit;
            display: block;
            transition: all 0.15s;
        }
        .persona-card:hover {
            background: var(--bg-card-hover);
            border-color: #383844;
        }
        .persona-card.active {
            border-color: var(--primary);
            background: rgba(222, 38, 38, 0.08);
            border-left: 3px solid var(--primary);
        }
        .persona-card-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
        }
        .persona-name {
            font-size: 0.88rem;
            font-weight: 800;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .persona-status-dot {
            width: 7px;
            height: 7px;
            background: #4B4B58;
            display: inline-block;
        }
        .persona-status-dot.online {
            background: var(--success);
            box-shadow: 0 0 6px rgba(22, 163, 74, 0.6);
        }
        .persona-archetype {
            font-size: 0.68rem;
            color: var(--primary);
            font-family: var(--font-mono);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .persona-desc {
            font-size: 0.75rem;
            color: var(--text-muted);
            line-height: 1.4;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            margin-bottom: 8px;
        }
        .persona-chips {
            display: flex;
            flex-wrap: wrap;
            gap: 4px;
        }
        .mini-chip {
            font-size: 0.66rem;
            font-family: var(--font-mono);
            background: #0E0E12;
            border: 1px solid #23232C;
            padding: 2px 6px;
            color: var(--text-muted);
        }

        /* Right Editor Stage */
        .editor-stage {
            display: flex;
            flex-direction: column;
            background: var(--bg-canvas);
            overflow-y: auto;
        }
        .editor-header {
            background: var(--bg-surface);
            border-bottom: 1px solid var(--border);
            padding: 16px 20px 0 20px;
            position: sticky;
            top: 0;
            z-index: 20;
        }
        .editor-title-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 14px;
            flex-wrap: wrap;
            gap: 10px;
        }
        .editor-heading {
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 1.1rem;
            font-weight: 800;
        }
        .persona-badge {
            font-size: 0.78rem;
            font-family: var(--font-mono);
            color: var(--primary);
            background: var(--primary-muted);
            padding: 3px 8px;
            border: 1px solid var(--primary);
        }

        /* Tabs Nav */
        .tabs-nav {
            display: flex;
            gap: 4px;
            overflow-x: auto;
            border-bottom: none;
            scrollbar-width: none;
        }
        .tabs-nav::-webkit-scrollbar { display: none; }
        .tab-btn {
            background: transparent;
            border: none;
            border-bottom: 2px solid transparent;
            color: var(--text-muted);
            padding: 8px 14px;
            font-size: 0.82rem;
            font-weight: 700;
            cursor: pointer;
            white-space: nowrap;
            transition: all 0.15s;
        }
        .tab-btn:hover {
            color: #FFFFFF;
        }
        .tab-btn.active {
            color: #FFFFFF;
            border-bottom: 2px solid var(--primary);
            background: rgba(222, 38, 38, 0.05);
        }

        /* Editor Body Panes */
        .editor-body {
            padding: 20px;
            max-width: 960px;
        }
        .tab-pane {
            display: none;
        }
        .tab-pane.active {
            display: block;
        }

        /* Form Controls */
        .form-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            margin-bottom: 16px;
        }
        .form-full {
            grid-column: 1 / -1;
        }
        .form-group {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
        .form-label {
            font-size: 0.75rem;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .form-label .desc {
            font-size: 0.7rem;
            color: var(--text-dim);
            text-transform: none;
            font-weight: 400;
        }
        .form-input, .form-textarea, .form-select {
            background: var(--bg-input);
            border: 1px solid var(--border);
            color: var(--text-main);
            padding: 9px 12px;
            font-size: 0.85rem;
            font-family: var(--font-ui);
            outline: none;
            width: 100%;
        }
        .form-textarea {
            font-family: var(--font-mono);
            line-height: 1.5;
            resize: vertical;
        }
        .form-input:focus, .form-textarea:focus, .form-select:focus {
            border-color: var(--border-focus);
        }

        /* Toggle Switches */
        .toggle-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            padding: 14px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }
        .toggle-info h4 {
            font-size: 0.85rem;
            font-weight: 700;
            margin-bottom: 2px;
        }
        .toggle-info p {
            font-size: 0.74rem;
            color: var(--text-muted);
        }
        .switch {
            position: relative;
            display: inline-block;
            width: 42px;
            height: 22px;
            flex-shrink: 0;
        }
        .switch input { opacity: 0; width: 0; height: 0; }
        .switch-slider {
            position: absolute;
            cursor: pointer;
            top: 0; left: 0; right: 0; bottom: 0;
            background-color: #24242C;
            transition: .2s;
        }
        .switch-slider:before {
            position: absolute;
            content: "";
            height: 16px; width: 16px;
            left: 3px; bottom: 3px;
            background-color: white;
            transition: .2s;
        }
        input:checked + .switch-slider {
            background-color: var(--primary);
        }
        input:checked + .switch-slider:before {
            transform: translateX(20px);
        }

        /* Chips Grid */
        .chips-container {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-top: 6px;
        }
        .chip-toggle {
            padding: 5px 12px;
            font-size: 0.76rem;
            font-family: var(--font-mono);
            background: var(--bg-card);
            border: 1px solid var(--border);
            color: var(--text-muted);
            cursor: pointer;
            user-select: none;
            transition: all 0.15s;
        }
        .chip-toggle:hover {
            color: #FFFFFF;
            border-color: #404050;
        }
        .chip-toggle.selected {
            background: var(--primary-muted);
            border-color: var(--primary);
            color: #FFFFFF;
            font-weight: 700;
        }

        /* Sliders */
        .range-container {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .range-slider {
            flex: 1;
            accent-color: var(--primary);
        }
        .range-badge {
            font-family: var(--font-mono);
            font-size: 0.8rem;
            color: var(--primary);
            background: #111115;
            padding: 3px 8px;
            border: 1px solid var(--border);
            min-width: 48px;
            text-align: center;
        }

        /* Avatar Stage */
        .avatar-preview-box {
            display: flex;
            align-items: center;
            gap: 16px;
            background: var(--bg-card);
            border: 1px solid var(--border);
            padding: 16px;
            margin-top: 10px;
        }
        .cube-canvas {
            width: 72px;
            height: 72px;
            background: #0A0A0E;
            border: 1px solid #2B2B36;
        }

        /* Live Preview Box */
        .preview-box {
            background: #08080C;
            border: 1px solid #2B2B36;
            padding: 16px;
            font-family: var(--font-mono);
            font-size: 0.78rem;
            color: #D1D1DE;
            white-space: pre-wrap;
            line-height: 1.5;
            max-height: 360px;
            overflow-y: auto;
            margin-top: 10px;
        }

        /* Buttons */
        .btn {
            background: var(--primary);
            color: #FFFFFF;
            border: none;
            padding: 8px 16px;
            font-size: 0.82rem;
            font-weight: 700;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            text-decoration: none;
            transition: background 0.15s;
        }
        .btn:hover { background: var(--primary-hover); }
        .btn-outline {
            background: transparent;
            border: 1px solid var(--border);
            color: var(--text-main);
        }
        .btn-outline:hover {
            border-color: #555566;
            background: #181820;
        }
        .btn-danger {
            background: transparent;
            border: 1px solid #7F1D1D;
            color: #EF4444;
        }
        .btn-danger:hover {
            background: #450A0A;
            border-color: #EF4444;
        }

        /* Flash Message */
        .alert-banner {
            padding: 10px 16px;
            background: rgba(22, 163, 74, 0.15);
            border-bottom: 1px solid var(--success);
            color: #86EFAC;
            font-size: 0.82rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        /* Responsive Breakpoints */
        @media (max-width: 840px) {
            .mobile-view-toggle {
                display: flex;
            }
            .workspace-grid {
                grid-template-columns: 1fr;
            }
            .sidebar {
                display: block;
                height: auto;
                border-right: none;
            }
            .sidebar.mobile-hidden {
                display: none;
            }
            .editor-stage {
                display: block;
            }
            .editor-stage.mobile-hidden {
                display: none;
            }
            .form-grid {
                grid-template-columns: 1fr;
            }
            .brand-subtitle {
                display: none;
            }
            .editor-title-row {
                flex-direction: column;
                align-items: flex-start;
            }
        }
    </style>
</head>
<body>

    <!-- Top Header -->
    <header class="top-bar">
        <div class="brand-group">
            <div class="brand-cube">B</div>
            <div>
                <span class="brand-title">BEJSON Persona Editor</span>
                <span class="brand-subtitle">AI_Profile (25-Field)</span>
            </div>
        </div>
        <div class="top-actions">
            <a href="http://127.0.0.1:5001/" target="_blank" class="btn btn-outline" style="font-size: 0.74rem;">&larr; Admin</a>
            <a href="/" class="btn" style="background:#1E1E26; border:1px solid var(--border); font-size: 0.74rem;">+ New</a>
            {% if profiles|length == 0 %}
            <form action="/seed-defaults" method="POST" style="display:inline;">
                <button type="submit" class="btn" style="background:var(--success); font-size: 0.74rem;">Seed Defaults</button>
            </form>
            {% endif %}
        </div>
    </header>

    {% if message %}
    <div class="alert-banner">
        <span>✓ {{ message }}</span>
        <button onclick="this.parentElement.remove()" style="background:none; border:none; color:inherit; cursor:pointer;">&times;</button>
    </div>
    {% endif %}

    <!-- Mobile Segmented View Toggle -->
    <div class="mobile-view-toggle">
        <button class="toggle-btn" id="mobileTabList" onclick="showMobileView('list')">Catalog ({{ profiles|length }})</button>
        <button class="toggle-btn active" id="mobileTabEditor" onclick="showMobileView('editor')">Editor: {{ selected_persona.Name if selected_persona else 'New' }}</button>
    </div>

    <!-- Workspace Grid -->
    <main class="workspace-grid">
        
        <!-- Left Sidebar: Catalog & Search -->
        <aside class="sidebar mobile-hidden" id="sidebarContainer">
            <div class="sidebar-header">
                <div class="search-box">
                    <input type="text" id="personaSearchInput" placeholder="Filter personas..." oninput="filterPersonas()">
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.74rem; color: var(--text-muted);">
                    <span>PERSONAS ({{ profiles|length }})</span>
                    <span id="activeCountBadge">{{ active_count }} Active</span>
                </div>
            </div>

            <div class="sidebar-list" id="personaCatalogList">
                {% for p in profiles %}
                <a href="/edit/{{ p.Name }}" class="persona-card {% if selected_persona and selected_persona.Name == p.Name %}active{% endif %}" data-name="{{ p.Name|lower }}" data-archetype="{{ p.Archetype|lower }}">
                    <div class="persona-card-top">
                        <div class="persona-name">
                            <span class="persona-status-dot {% if p.Active %}online{% endif %}"></span>
                            {{ p.Name }}
                        </div>
                        <span class="persona-archetype">{{ p.Archetype }}</span>
                    </div>
                    <p class="persona-desc">{{ p.Persona or 'No voice description configured.' }}</p>
                    <div class="persona-chips">
                        {% if p.Tone %}
                            {% for t in p.Tone[:3] %}
                            <span class="mini-chip">{{ t }}</span>
                            {% endfor %}
                        {% endif %}
                        <span class="mini-chip" style="color:var(--primary);">creativity: {{ p.Creativity }}</span>
                    </div>
                </a>
                {% else %}
                <div style="padding: 24px; text-align: center; color: var(--text-dim); font-size: 0.8rem;">
                    No personas defined in AI_Profile.<br><br>
                    <form action="/seed-defaults" method="POST">
                        <button type="submit" class="btn btn-outline" style="font-size:0.75rem;">Seed Defaults</button>
                    </form>
                </div>
                {% endfor %}
            </div>
        </aside>

        <!-- Right Pane: Multi-Tab Editor -->
        <section class="editor-stage" id="editorContainer">
            <form action="/save" method="POST" id="personaEditForm">
                
                <div class="editor-header">
                    <div class="editor-title-row">
                        <div class="editor-heading">
                            <span>{{ "Edit Persona" if selected_persona else "Create Persona" }}</span>
                            {% if selected_persona %}
                            <span class="persona-badge">{{ selected_persona.Name }}</span>
                            {% endif %}
                        </div>

                        <div style="display: flex; gap: 8px; align-items: center;">
                            {% if selected_persona %}
                            <button type="button" class="btn btn-outline" onclick="duplicatePersona('{{ selected_persona.Name }}')">Duplicate</button>
                            <button type="button" class="btn btn-danger" onclick="deletePersona('{{ selected_persona.Name }}')">Delete</button>
                            {% endif %}
                            <button type="submit" class="btn">Save Persona</button>
                        </div>
                    </div>

                    <!-- Navigation Tabs -->
                    <div class="tabs-nav">
                        <button type="button" class="tab-btn active" data-tab="tab-identity" onclick="switchTab('tab-identity', this)">1. Identity</button>
                        <button type="button" class="tab-btn" data-tab="tab-tones" onclick="switchTab('tab-tones', this)">2. Tones</button>
                        <button type="button" class="tab-btn" data-tab="tab-model" onclick="switchTab('tab-model', this)">3. Cognition</button>
                        <button type="button" class="tab-btn" data-tab="tab-tools" onclick="switchTab('tab-tools', this)">4. Tools & Code</button>
                        <button type="button" class="tab-btn" data-tab="tab-preview" onclick="switchTab('tab-preview', this)">5. Prompt & Preview</button>
                    </div>
                </div>

                <div class="editor-body">

                    <!-- TAB 1: Identity & Voice -->
                    <div id="tab-identity" class="tab-pane active">
                        <div class="form-grid">
                            <div class="form-group">
                                <label class="form-label">Persona Identifier <span class="desc">Unique ID / Author Link</span></label>
                                <input type="text" name="name" id="inputName" class="form-input" required value="{{ selected_persona.Name if selected_persona else '' }}" placeholder="e.g. boehnenelton2024, Code Sentinel" {{ "readonly" if selected_persona else "" }} oninput="updateLivePreview()">
                            </div>

                            <div class="form-group">
                                <label class="form-label">Archetype Role <span class="desc">Functional domain title</span></label>
                                <input type="text" name="archetype" id="inputArchetype" class="form-input" value="{{ selected_persona.Archetype if selected_persona else 'Systems Architect' }}" placeholder="e.g. Systems Architect, Security Auditor" oninput="updateLivePreview()">
                            </div>

                            <div class="form-group form-full">
                                <label class="form-label">Voice & Persona Directives <span class="desc">Shapes AI voice internally (never published)</span></label>
                                <textarea name="persona_bio" id="inputPersonaBio" rows="4" class="form-textarea" placeholder="Describe tone cadence, thinking habits, zero-fluff style, technical boundaries..." oninput="updateLivePreview()">{{ selected_persona.Persona if selected_persona else '' }}</textarea>
                            </div>

                            <div class="form-group">
                                <label class="form-label">Avatar Type</label>
                                <select name="avatar_type" id="avatarTypeSelect" class="form-select" onchange="renderAvatarPreview()">
                                    <option value="cube" {% if selected_persona and selected_persona.Avatar_Type == 'cube' %}selected{% endif %}>BEJSON Isometric Cube (Canonical)</option>
                                    <option value="url" {% if selected_persona and selected_persona.Avatar_Type == 'url' %}selected{% endif %}>External Image URL</option>
                                    <option value="data" {% if selected_persona and selected_persona.Avatar_Type == 'data' %}selected{% endif %}>Inline SVG/Data URI</option>
                                    <option value="none" {% if selected_persona and selected_persona.Avatar_Type == 'none' %}selected{% endif %}>None (Text Initials)</option>
                                </select>
                            </div>

                            <div class="form-group">
                                <label class="form-label">Avatar Image Source URL</label>
                                <input type="text" name="avatar_sourceUrl" id="avatarSourceUrlInput" class="form-input" value="{{ selected_persona.Avatar_sourceUrl if selected_persona else '' }}" placeholder="https://... or brand asset path" oninput="renderAvatarPreview()">
                            </div>
                        </div>

                        <!-- Live Avatar Visual Anchor -->
                        <div class="avatar-preview-box">
                            <canvas id="cubeCanvas" class="cube-canvas" width="144" height="144"></canvas>
                            <div>
                                <h4 style="font-size:0.85rem; font-weight:700;">Avatar Brand Anchor</h4>
                                <p style="font-size:0.75rem; color:var(--text-muted); margin-top:2px;">Canonical BEJSON Tri-Color isometric rendering (#FFFFFF, #000000, #DE2626).</p>
                            </div>
                        </div>

                        <div class="toggle-card" style="margin-top: 16px;">
                            <div class="toggle-info">
                                <h4>Persona Active Status</h4>
                                <p>Enable to make this persona selectable in AI drafting and author byline assignments.</p>
                            </div>
                            <label class="switch">
                                <input type="checkbox" name="active" value="1" {% if not selected_persona or selected_persona.Active %}checked{% endif %}>
                                <span class="switch-slider"></span>
                            </label>
                        </div>
                    </div>

                    <!-- TAB 2: Tone & Delivery -->
                    <div id="tab-tones" class="tab-pane">
                        <div class="form-group">
                            <label class="form-label">Tone Matrix <span class="desc">Toggle behavioral attributes</span></label>
                            <input type="hidden" name="tones" id="hiddenTonesInput" value="{{ selected_persona.Tone|join(',') if selected_persona and selected_persona.Tone else 'technical,authoritative,direct' }}">
                            <div class="chips-container" id="toneChipsContainer">
                                {% set active_tones = selected_persona.Tone if selected_persona and selected_persona.Tone else ['technical', 'authoritative', 'direct'] %}
                                {% for tone_opt in ['technical', 'authoritative', 'direct', 'rigorous', 'analytical', 'critical', 'precise', 'insightful', 'balanced', 'provocative', 'empathetic', 'humorous', 'academic'] %}
                                <div class="chip-toggle {% if tone_opt in active_tones %}selected{% endif %}" onclick="toggleChip(this, 'hiddenTonesInput')">{{ tone_opt }}</div>
                                {% endfor %}
                            </div>
                        </div>

                        <div class="form-grid" style="margin-top: 20px;">
                            <div class="form-group">
                                <label class="form-label">Formality Level</label>
                                <select name="formality" class="form-select">
                                    <option value="rigorous" {% if selected_persona and selected_persona.Formality == 'rigorous' %}selected{% endif %}>Rigorous & Grounded (Default)</option>
                                    <option value="formal" {% if selected_persona and selected_persona.Formality == 'formal' %}selected{% endif %}>Formal Corporate</option>
                                    <option value="casual" {% if selected_persona and selected_persona.Formality == 'casual' %}selected{% endif %}>Casual Peer</option>
                                </select>
                            </div>

                            <div class="form-group">
                                <label class="form-label">Verbosity</label>
                                <select name="verbosity" class="form-select">
                                    <option value="concise" {% if selected_persona and selected_persona.Verbosity == 'concise' %}selected{% endif %}>Concise / Dense (Zero Fluff)</option>
                                    <option value="balanced" {% if selected_persona and selected_persona.Verbosity == 'balanced' %}selected{% endif %}>Balanced Technical</option>
                                    <option value="exhaustive" {% if selected_persona and selected_persona.Verbosity == 'exhaustive' %}selected{% endif %}>Exhaustive Reference</option>
                                </select>
                            </div>
                        </div>

                        <div class="toggle-card" style="margin-top: 10px;">
                            <div class="toggle-info">
                                <h4>Emotional Expression Gate</h4>
                                <p>Permit emotional variance in AI response tone.</p>
                            </div>
                            <label class="switch">
                                <input type="checkbox" name="emotional_enabled" value="1" {% if selected_persona and selected_persona.EmotionalExpression_Enabled %}checked{% endif %}>
                                <span class="switch-slider"></span>
                            </label>
                        </div>

                        <div class="form-group">
                            <label class="form-label">Emotional Expression Intensity (0.0 to 1.0)</label>
                            <div class="range-container">
                                <input type="range" name="emotional_intensity" class="range-slider" min="0.0" max="1.0" step="0.05" value="{{ selected_persona.EmotionalExpression_Intensity if selected_persona else 0.0 }}" oninput="document.getElementById('emotionalBadge').innerText = this.value">
                                <span class="range-badge" id="emotionalBadge">{{ selected_persona.EmotionalExpression_Intensity if selected_persona else 0.0 }}</span>
                            </div>
                        </div>
                    </div>

                    <!-- TAB 3: Model & Cognition -->
                    <div id="tab-model" class="tab-pane">
                        <div class="form-group" style="margin-bottom: 20px;">
                            <label class="form-label">Creativity / Temperature (0.0 - 1.0) <span class="desc">Deterministic &le; 0.3, Exploratory &ge; 0.7</span></label>
                            <div class="range-container">
                                <input type="range" name="creativity" class="range-slider" min="0.0" max="1.0" step="0.05" value="{{ selected_persona.Creativity if selected_persona else 0.6 }}" oninput="document.getElementById('creativityBadge').innerText = this.value">
                                <span class="range-badge" id="creativityBadge">{{ selected_persona.Creativity if selected_persona else 0.6 }}</span>
                            </div>
                        </div>

                        <div class="form-grid">
                            <div class="form-group">
                                <label class="form-label">Max Response Tokens</label>
                                <select name="max_tokens" class="form-select">
                                    <option value="2048" {% if selected_persona and selected_persona.MaxResponseTokens == 2048 %}selected{% endif %}>2,048 Tokens (Brief)</option>
                                    <option value="4096" {% if selected_persona and selected_persona.MaxResponseTokens == 4096 %}selected{% endif %}>4,096 Tokens (Standard)</option>
                                    <option value="8192" {% if not selected_persona or selected_persona.MaxResponseTokens == 8192 %}selected{% endif %}>8,192 Tokens (Extended)</option>
                                    <option value="16384" {% if selected_persona and selected_persona.MaxResponseTokens == 16384 %}selected{% endif %}>16,384 Tokens (Deep Article)</option>
                                </select>
                            </div>
                        </div>

                        <div class="toggle-card">
                            <div class="toggle-info">
                                <h4>Thinking Mode Supported</h4>
                                <p>Enable cognitive reasoning step traces for Gemini 2.0 / Flash Thinking models.</p>
                            </div>
                            <label class="switch">
                                <input type="checkbox" name="thinking_supported" value="1" {% if not selected_persona or selected_persona.Thinking_Supported %}checked{% endif %}>
                                <span class="switch-slider"></span>
                            </label>
                        </div>

                        <div class="toggle-card">
                            <div class="toggle-info">
                                <h4>Ephemeral Memory</h4>
                                <p>Flush conversational state immediately following generation without persistence.</p>
                            </div>
                            <label class="switch">
                                <input type="checkbox" name="ephemeral_memory" value="1" {% if selected_persona and selected_persona.EphemeralMemory %}checked{% endif %}>
                                <span class="switch-slider"></span>
                            </label>
                        </div>
                    </div>

                    <!-- TAB 4: Tools & Code -->
                    <div id="tab-tools" class="tab-pane">
                        <div class="toggle-card">
                            <div class="toggle-info">
                                <h4>Code Interpreter / Execution</h4>
                                <p>Allow persona to execute Python sandbox routines.</p>
                            </div>
                            <label class="switch">
                                <input type="checkbox" name="code_interpreter" value="1" {% if not selected_persona or selected_persona.CodeInterpreter_Enabled %}checked{% endif %}>
                                <span class="switch-slider"></span>
                            </label>
                        </div>

                        <div class="form-grid" style="margin-top: 16px;">
                            <div class="form-group">
                                <label class="form-label">Code Parsing Mode</label>
                                <select name="code_mode" class="form-select">
                                    <option value="strict" {% if not selected_persona or selected_persona.CodeParsing_Mode == 'strict' %}selected{% endif %}>Strict AST Syntax</option>
                                    <option value="lenient" {% if selected_persona and selected_persona.CodeParsing_Mode == 'lenient' %}selected{% endif %}>Lenient Extraction</option>
                                </select>
                            </div>

                            <div class="form-group">
                                <label class="form-label">Structure Validation</label>
                                <select name="structure_validation" class="form-select">
                                    <option value="1" {% if not selected_persona or selected_persona.CodeParsing_StructureValidation %}selected{% endif %}>Enabled (Enforce Schema)</option>
                                    <option value="0" {% if selected_persona and not selected_persona.CodeParsing_StructureValidation %}selected{% endif %}>Disabled</option>
                                </select>
                            </div>
                        </div>

                        <div class="form-group" style="margin-top: 10px;">
                            <label class="form-label">Authorized Programming Languages</label>
                            <input type="hidden" name="code_languages" id="hiddenLangsInput" value="{{ selected_persona.CodeParsing_Languages|join(',') if selected_persona and selected_persona.CodeParsing_Languages else 'python,bash,javascript,json,bejson' }}">
                            <div class="chips-container" id="langChipsContainer">
                                {% set active_langs = selected_persona.CodeParsing_Languages if selected_persona and selected_persona.CodeParsing_Languages else ['python', 'bash', 'javascript', 'json', 'bejson'] %}
                                {% for lang in ['python', 'bash', 'javascript', 'html', 'behtml', 'json', 'bejson', 'sql', 'typescript'] %}
                                <div class="chip-toggle {% if lang in active_langs %}selected{% endif %}" onclick="toggleChip(this, 'hiddenLangsInput')">{{ lang }}</div>
                                {% endfor %}
                            </div>
                        </div>

                        <div class="form-group form-full" style="margin-top: 16px;">
                            <label class="form-label">Forbidden Topics & Negative Constraints <span class="desc">Comma-separated</span></label>
                            <input type="text" name="forbidden_topics" class="form-input" value="{{ selected_persona.ForbiddenTopics|join(', ') if selected_persona and selected_persona.ForbiddenTopics else 'marketing fluff, lorem ipsum' }}" placeholder="marketing fluff, lorem ipsum, handwaving">
                        </div>
                    </div>

                    <!-- TAB 5: Prompt & Preview -->
                    <div id="tab-preview" class="tab-pane">
                        <div class="form-group form-full">
                            <label class="form-label">System Instruction <span class="desc">Core foundational directives</span></label>
                            <textarea name="system_instruction" id="inputSystemInstruction" rows="7" class="form-textarea" placeholder="You are the Lead Systems Architect. Enforce zero-filler discipline, O(1) field cache patterns..." oninput="updateLivePreview()">{{ selected_persona.SystemInstruction if selected_persona else '' }}</textarea>
                        </div>

                        <div class="form-group form-full" style="margin-top: 20px;">
                            <label class="form-label">
                                <span>⚡ Live Assembled Pre-Prompt Preview</span>
                                <span class="desc"><button type="button" class="btn btn-outline" style="padding:2px 8px; font-size:0.7rem;" onclick="copyPrompt()">Copy Prompt</button></span>
                            </label>
                            <div class="preview-box" id="livePreviewContainer">Generating prompt...</div>
                        </div>
                    </div>

                </div>
            </form>
        </section>
    </main>

    <!-- Hidden Action Forms -->
    <form id="deleteForm" method="POST" style="display:none;"></form>
    <form id="dupForm" method="POST" style="display:none;"></form>

    <script>
        // Tab Navigation Logic
        function switchTab(tabId, btnElement) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
            
            if (btnElement) {
                btnElement.classList.add('active');
            } else {
                const targetBtn = document.querySelector(`.tab-btn[data-tab='${tabId}']`);
                if (targetBtn) targetBtn.classList.add('active');
            }

            const targetPane = document.getElementById(tabId);
            if (targetPane) {
                targetPane.classList.add('active');
            }
            if (tabId === 'tab-preview') {
                updateLivePreview();
            }
            if (tabId === 'tab-identity') {
                renderAvatarPreview();
            }
        }

        // Mobile View Switcher (Catalog vs Editor)
        function showMobileView(view) {
            const sidebar = document.getElementById('sidebarContainer');
            const editor = document.getElementById('editorContainer');
            const tabList = document.getElementById('mobileTabList');
            const tabEditor = document.getElementById('mobileTabEditor');

            if (view === 'list') {
                sidebar.classList.remove('mobile-hidden');
                editor.classList.add('mobile-hidden');
                tabList.classList.add('active');
                tabEditor.classList.remove('active');
            } else {
                sidebar.classList.add('mobile-hidden');
                editor.classList.remove('mobile-hidden');
                tabList.classList.remove('active');
                tabEditor.classList.add('active');
            }
        }

        // Chip Multi-Select Toggle
        function toggleChip(chipEl, hiddenInputId) {
            chipEl.classList.toggle('selected');
            const parent = chipEl.parentElement;
            const selectedChips = Array.from(parent.querySelectorAll('.chip-toggle.selected')).map(c => c.innerText.trim());
            document.getElementById(hiddenInputId).value = selectedChips.join(',');
            updateLivePreview();
        }

        // Search Filter for Persona Catalog
        function filterPersonas() {
            const query = document.getElementById('personaSearchInput').value.toLowerCase();
            const cards = document.querySelectorAll('#personaCatalogList .persona-card');
            let visibleCount = 0;
            cards.forEach(c => {
                const name = c.getAttribute('data-name') || '';
                const arch = c.getAttribute('data-archetype') || '';
                if (name.includes(query) || arch.includes(query)) {
                    c.style.display = 'block';
                    visibleCount++;
                } else {
                    c.style.display = 'none';
                }
            });
        }

        // Live Assembled System Prompt Previewer
        function updateLivePreview() {
            const name = document.getElementById('inputName')?.value || 'AI';
            const arch = document.getElementById('inputArchetype')?.value || 'Persona';
            const tones = document.getElementById('hiddenTonesInput')?.value || '';
            const quirks = document.getElementById('inputPersonaBio')?.value || '';
            const langs = document.getElementById('hiddenLangsInput')?.value || '';
            const baseInst = document.getElementById('inputSystemInstruction')?.value || '';

            const lines = [];
            lines.push(`[IDENTITY]: ${name} (${arch})`);
            if (tones) lines.push(`[TONE]: ${tones.split(',').join(', ')}`);
            if (quirks) lines.push(`[VOICE_DIRECTIVES]: ${quirks}`);
            if (langs) lines.push(`[LANGUAGES]: ${langs.split(',').join(', ')}`);

            const extra = lines.join('\\n');
            const assembled = baseInst ? `${baseInst}\\n\\n${extra}` : extra;

            const previewEl = document.getElementById('livePreviewContainer');
            if (previewEl) {
                previewEl.innerText = assembled;
            }
        }

        function copyPrompt() {
            const previewEl = document.getElementById('livePreviewContainer');
            if (previewEl) {
                navigator.clipboard.writeText(previewEl.innerText).then(() => {
                    alert('Assembled prompt copied to clipboard!');
                });
            }
        }

        // Canvas 3D Isometric Cube Renderer for Persona Avatar
        function drawIsometricCube(canvas) {
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            const w = canvas.width;
            const h = canvas.height;
            ctx.clearRect(0, 0, w, h);

            const cx = w / 2;
            const cy = h / 2 - 4;
            const size = 38;

            // Math for 30-degree isometric projection
            const cos30 = Math.cos(Math.PI / 6);
            const sin30 = Math.sin(Math.PI / 6);

            const dx = size * cos30;
            const dy = size * sin30;

            // Top Face (Bright Accent Red)
            ctx.beginPath();
            ctx.moveTo(cx, cy - size);
            ctx.lineTo(cx + dx, cy - size + dy);
            ctx.lineTo(cx, cy - size + 2 * dy);
            ctx.lineTo(cx - dx, cy - size + dy);
            ctx.closePath();
            ctx.fillStyle = '#EF4444';
            ctx.fill();
            ctx.strokeStyle = '#FFFFFF';
            ctx.lineWidth = 1.5;
            ctx.stroke();

            // Left Face (Deep Canonical Red)
            ctx.beginPath();
            ctx.moveTo(cx - dx, cy - size + dy);
            ctx.lineTo(cx, cy - size + 2 * dy);
            ctx.lineTo(cx, cy + size);
            ctx.lineTo(cx - dx, cy + size - dy);
            ctx.closePath();
            ctx.fillStyle = '#DE2626';
            ctx.fill();
            ctx.stroke();

            // Right Face (Shadow Dark Red)
            ctx.beginPath();
            ctx.moveTo(cx, cy - size + 2 * dy);
            ctx.lineTo(cx + dx, cy - size + dy);
            ctx.lineTo(cx + dx, cy + size - dy);
            ctx.lineTo(cx, cy + size);
            ctx.closePath();
            ctx.fillStyle = '#991B1B';
            ctx.fill();
            ctx.stroke();
        }

        function renderAvatarPreview() {
            const canvas = document.getElementById('cubeCanvas');
            const avatarType = document.getElementById('avatarTypeSelect')?.value;
            if (avatarType === 'cube' || !avatarType) {
                drawIsometricCube(canvas);
            } else {
                // Clear and render placeholder text or icon
                const ctx = canvas.getContext('2d');
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                ctx.fillStyle = '#111115';
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                ctx.fillStyle = '#FFFFFF';
                ctx.font = 'bold 24px sans-serif';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                const initial = document.getElementById('inputName')?.value?.[0] || 'A';
                ctx.fillText(initial.toUpperCase(), canvas.width / 2, canvas.height / 2);
            }
        }

        // Action Handlers
        function deletePersona(name) {
            if (confirm(`Delete persona '${name}'?\\nPages using this persona will cascade to the default author.`)) {
                const f = document.getElementById('deleteForm');
                f.action = `/delete/${encodeURIComponent(name)}`;
                f.submit();
            }
        }

        function duplicatePersona(name) {
            const f = document.getElementById('dupForm');
            f.action = `/duplicate/${encodeURIComponent(name)}`;
            f.submit();
        }

        // Keyboard Shortcut: Ctrl+S / Cmd+S to Save
        window.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 's') {
                e.preventDefault();
                document.getElementById('personaEditForm')?.submit();
            }
        });

        // Initialize on load
        window.addEventListener('DOMContentLoaded', () => {
            updateLivePreview();
            renderAvatarPreview();
        });
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    profiles = db.get_records('AI_Profile')
    selected = profiles[0] if profiles else None
    active_count = sum(1 for p in profiles if p.get('Active'))
    msg = request.args.get('msg')
    return render_template_string(
        _STUDIO_TEMPLATE,
        profiles=profiles,
        selected_persona=selected,
        active_count=active_count,
        message=msg
    )


@app.route('/edit/<name>')
def edit(name):
    profiles = db.get_records('AI_Profile')
    selected = next((p for p in profiles if p.get('Name') == name), None)
    active_count = sum(1 for p in profiles if p.get('Active'))
    msg = request.args.get('msg')
    return render_template_string(
        _STUDIO_TEMPLATE,
        profiles=profiles,
        selected_persona=selected,
        active_count=active_count,
        message=msg
    )


@app.route('/api/persona/<name>')
def api_get_persona(name):
    profiles = db.get_records('AI_Profile')
    persona = next((p for p in profiles if p.get('Name') == name), None)
    if not persona:
        return jsonify({"error": f"Persona '{name}' not found"}), 404
    return jsonify(persona)


@app.route('/save', methods=['POST'])
def save():
    name = (request.form.get('name') or '').strip()
    if not name:
        return redirect('/?msg=Error:+Persona+name+is+required')

    archetype = (request.form.get('archetype') or 'Systems Architect').strip()
    persona_bio = (request.form.get('persona_bio') or '').strip()
    system_instruction = (request.form.get('system_instruction') or '').strip()
    active = request.form.get('active') == '1'

    try:
        max_tokens = int(request.form.get('max_tokens', 8192))
    except ValueError:
        max_tokens = 8192

    try:
        creativity = float(request.form.get('creativity', 0.6))
    except ValueError:
        creativity = 0.6

    raw_tones = request.form.get('tones', '')
    tones_list = [t.strip() for t in raw_tones.split(',') if t.strip()]

    formality = request.form.get('formality', 'rigorous')
    verbosity = request.form.get('verbosity', 'concise')

    emotional_enabled = request.form.get('emotional_enabled') == '1'
    try:
        emotional_intensity = float(request.form.get('emotional_intensity', 0.0))
    except ValueError:
        emotional_intensity = 0.0

    code_interpreter = request.form.get('code_interpreter') == '1'
    ephemeral_memory = request.form.get('ephemeral_memory') == '1'

    code_mode = request.form.get('code_mode', 'strict')
    raw_langs = request.form.get('code_languages', '')
    langs_list = [l.strip() for l in raw_langs.split(',') if l.strip()]

    structure_validation = request.form.get('structure_validation') == '1'
    version_control = request.form.get('version_control') == '1'
    thinking_supported = request.form.get('thinking_supported') == '1'

    raw_forbidden = request.form.get('forbidden_topics', '')
    forbidden_list = [f.strip() for f in raw_forbidden.split(',') if f.strip()]

    avatar_type = request.form.get('avatar_type', 'cube')
    avatar_url = (request.form.get('avatar_sourceUrl') or '').strip()
    avatar_data = (request.form.get('avatar_data') or '').strip()

    payload = {
        'Record_Type_Parent': 'AI_Profile',
        'Name': name,
        'Archetype': archetype,
        'Persona': persona_bio,
        'SystemInstruction': system_instruction,
        'Active': active,
        'MaxResponseTokens': max_tokens,
        'Creativity': creativity,
        'Tone': tones_list,
        'Formality': formality,
        'Verbosity': verbosity,
        'EmotionalExpression_Enabled': emotional_enabled,
        'EmotionalExpression_Intensity': emotional_intensity,
        'CodeInterpreter_Enabled': code_interpreter,
        'EphemeralMemory': ephemeral_memory,
        'CodeParsing_Mode': code_mode,
        'CodeParsing_Languages': langs_list,
        'CodeParsing_StructureValidation': structure_validation,
        'CodeParsing_VersionControl': version_control,
        'Thinking_Supported': thinking_supported,
        'ForbiddenTopics': forbidden_list,
        'Avatar_Type': avatar_type,
        'Avatar_sourceUrl': avatar_url,
        'Avatar_Data': avatar_data
    }

    existing = next((p for p in db.get_records('AI_Profile') if p.get('Name', '').lower() == name.lower()), None)
    if existing:
        db.update_record('AI_Profile', 'Name', name, payload)
    else:
        db.add_record('AI_Profile', payload)

    # Ensure linked AuthorProfile exists
    existing_author = next((a for a in db.get_records('AuthorProfile') if a.get('author_display_name', '').lower() == name.lower()), None)
    if not existing_author:
        db.add_record('AuthorProfile', {'author_display_name': name, 'author_bio': '', 'author_avatar_url': avatar_url})

    return redirect(f'/edit/{name}?msg=Persona+{name}+saved+successfully')


@app.route('/delete/<name>', methods=['POST'])
def delete(name):
    db.delete_record('AI_Profile', 'Name', name)
    DEFAULT_AUTHOR_NAME = "boehnenelton2024"
    pages = db.get_records("PageRecord")
    for p in pages:
        if p.get("page_author_name") == name:
            db.update_record("PageRecord", "page_uuid", p["page_uuid"], {"page_author_name": DEFAULT_AUTHOR_NAME})
    return redirect(f'/?msg=Persona+{name}+deleted')


@app.route('/duplicate/<name>', methods=['POST'])
def duplicate(name):
    profiles = db.get_records('AI_Profile')
    source = next((p for p in profiles if p.get('Name') == name), None)
    if not source:
        return redirect('/?msg=Error:+Source+persona+not+found')

    new_name = f"{name}_Copy"
    counter = 1
    while any(p.get('Name', '').lower() == new_name.lower() for p in profiles):
        counter += 1
        new_name = f"{name}_Copy{counter}"

    clone_payload = dict(source)
    clone_payload['Name'] = new_name
    db.add_record('AI_Profile', clone_payload)
    return redirect(f'/edit/{new_name}?msg=Duplicated+as+{new_name}')


@app.route('/seed-defaults', methods=['POST'])
def seed_defaults():
    existing_names = {p.get('Name', '').lower() for p in db.get_records('AI_Profile')}
    count = 0
    for seed in DEFAULT_SEED_PERSONAS:
        if seed['Name'].lower() not in existing_names:
            db.add_record('AI_Profile', seed)
            count += 1
    return redirect(f'/?msg=Seeded+{count}+canonical+personas')


if __name__ == '__main__':
    _legacy = [f for f in ["Flask_CMS.py", "Flask_CMS_Publisher.py", "Flask_Page_Editor.py",
                            "Flask_Profile_Manager.py", "Page_Editor_v2.py"]
               if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), f))]
    if _legacy:
        print(f"\n    !! WARNING: old pre-rename file(s) still present: {', '.join(_legacy)} -- delete them, they are unmaintained leftovers from before the Blueprint split.\n")
    app.run(host='0.0.0.0', port=PROFILES_PORT)
