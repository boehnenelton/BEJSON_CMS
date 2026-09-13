"""
Script: generate_taxonomy_report.py
Author: Elton Boehnen
Version: 1.0.0
Package Version: 102
RELATIONAL_ID: 9b0a3d8f-5c2e-4e9b-af0d-8e6b2c0a4f3e
Date: 2026-08-10
Description: Comprehensive 700+ line technical PDF generator for BEJSON CMS Naming Taxonomy & Extensibility System.
"""

import os
import sys
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#666666"))
        
        # Running Header (Pages > 1)
        if self._pageNumber > 1:
            self.drawString(54, 750, "BEJSON CMS ARCHITECTURAL REPORT: NAMING TAXONOMY & EXTENSIBILITY")
            self.setStrokeColor(colors.HexColor("#CCCCCC"))
            self.setLineWidth(0.5)
            self.line(54, 742, 558, 742)
            
        # Running Footer
        footer_text = f"Page {self._pageNumber} of {page_count}  |  Elton Boehnen · boehnenelton2024@gmail.com · BEJSON CMS v18.28"
        self.drawRightString(558, 36, footer_text)
        self.setStrokeColor(colors.HexColor("#CCCCCC"))
        self.setLineWidth(0.5)
        self.line(54, 48, 558, 48)
        
        self.restoreState()

def create_pdf(filename=None):
    if filename is None:
        filename = str(Path(__file__).resolve().parent / "CMS_Naming_Taxonomy_Architecture_Report.pdf")
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )
    
    styles = getSampleStyleSheet()
    
    c_primary = colors.HexColor("#111111")
    c_accent = colors.HexColor("#DE2626")
    c_dark = colors.HexColor("#222222")
    c_light = colors.HexColor("#F8F9FA")
    c_border = colors.HexColor("#E2E8F0")
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=c_primary,
        spaceAfter=4
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14,
        textColor=c_accent,
        spaceAfter=10
    )
    
    meta_style = ParagraphStyle(
        'DocMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=12,
        textColor=colors.HexColor("#555555")
    )
    
    h1_style = ParagraphStyle(
        'Heading1_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=c_primary,
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'Heading2_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14,
        textColor=c_accent,
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        'Body_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=c_dark,
        spaceAfter=5
    )
    
    bullet_style = ParagraphStyle(
        'Bullet_Custom',
        parent=body_style,
        leftIndent=12,
        bulletIndent=4,
        spaceAfter=3
    )

    code_style = ParagraphStyle(
        'Code_Custom',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#1A202C"),
        backColor=c_light,
        borderColor=c_border,
        borderWidth=0.5,
        borderPadding=4,
        spaceBefore=4,
        spaceAfter=6
    )
    
    table_cell = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=10,
        textColor=c_dark
    )
    
    table_header = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=10,
        textColor=colors.white
    )

    story = []
    
    # -------------------------------------------------------------------------
    # COVER / HEADER METADATA
    # -------------------------------------------------------------------------
    story.append(Paragraph("BEJSON CMS: TECHNICAL TAXONOMY & NAMING STANDARD REPORT", title_style))
    story.append(Paragraph("ARCHITECTURAL BLUEPRINT FOR SYSTEMIC FIELD NAMING, UNIFIED UUID IDENTIFIERS, AND PAGE TYPE EXTENSIBILITY", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=c_accent, spaceBefore=0, spaceAfter=8))
    
    meta_text = """
    <b>Author:</b> Elton Boehnen (boehnenelton2024@gmail.com)<br/>
    <b>Project Target:</b> BEJSON_CMS v18.28 (Package 81)<br/>
    <b>Document Version:</b> 1.0.0 (Package Version: 102 | RELATIONAL_ID: 9b0a3d8f-5c2e-4e9b-af0d-8e6b2c0a4f3e)<br/>
    <b>Status:</b> Architectural Proposal & Migration Plan
    """
    story.append(Paragraph(meta_text, meta_style))
    story.append(Spacer(1, 10))
    
    # -------------------------------------------------------------------------
    # SECTION 1: EXECUTIVE SUMMARY
    # -------------------------------------------------------------------------
    story.append(Paragraph("1. EXECUTIVE SUMMARY", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=c_primary, spaceBefore=0, spaceAfter=6))
    
    p1_1 = """
    The BEJSON CMS ecosystem is a high-performance static site generator and web publishing platform built on Flask, top-level BEJSON schemas, and MFDB binary containers across 84 core Python modules. Over extensive feature iterations, legacy shortcuts have introduced field key fragmentation across database files, Flask blueprints, and rendering templates. For instance, entity references present ad-hoc names such as <code>ad_link</code> vs <code>external_url</code>, <code>auth_name</code> vs <code>author_ref</code>, and <code>featured_img</code> vs <code>app_image</code> vs <code>ad_image</code>.
    """
    story.append(Paragraph(p1_1, body_style))
    
    p1_2 = """
    As BEJSON CMS expands to support rich, specialized Page Types—including standard HTML pages, dedicated video hubs, and document download centers with PDF media attachments—integrating new features against messy variable names introduces severe maintenance overhead and risk of schema corruption.
    """
    story.append(Paragraph(p1_2, body_style))

    p1_3 = """
    This report delivers a rigorous technical architecture to unify field naming across the codebase. It establishes:
    <br/>1. An <b>Empirical Audit</b> of all 14 major divergent field names across 84 source files.
    <br/>2. A <b>Canonical Prefix Registry</b> enforcing explicit entity tags (e.g., <code>page_</code>, <code>author_</code>, <code>asset_</code>, <code>extmedia_</code>).
    <br/>3. A <b>Unified Synthetic UUID Standard</b> using <code>&lt;prefix&gt;_uuid</code> primary keys to eliminate fragile name-keying.
    <br/>4. A <b>Polymorphic Page Type Extensibility Pattern</b> supporting Standard, Video, and Document variants via strategy renderers.
    <br/>5. A <b>Phased Migration Roadmap</b> with effort estimates for zero-downtime execution.
    """
    story.append(Paragraph(p1_3, body_style))
    story.append(Spacer(1, 8))

    # -------------------------------------------------------------------------
    # SECTION 2: EMPIRICAL AUDIT OF CURRENT FIELD USAGE
    # -------------------------------------------------------------------------
    story.append(Paragraph("2. EMPIRICAL AUDIT OF CURRENT FIELD USAGE & FRAGMENTATION", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=c_primary, spaceBefore=0, spaceAfter=6))
    
    p2_1 = """
    An automated static analysis of the <code>src/</code> directory across all web blueprints (System, Content, Media, Interface), shared utility libraries, and CLI tools identified 14 key fields suffering from semantic overlap, prefix ambiguity, or missing entity context:
    """
    story.append(Paragraph(p2_1, body_style))
    
    audit_data = [
        [Paragraph("Field Name", table_header), Paragraph("File Count", table_header), Paragraph("Occurrences", table_header), Paragraph("Current Domain / Architectural Issues", table_header)],
        [Paragraph("<code>created_at</code>", table_cell), Paragraph("12 files", table_cell), Paragraph("32", table_cell), Paragraph("Generic timestamp key; collides with <code>uploaded_at</code> and lacks entity prefix", table_cell)],
        [Paragraph("<code>featured_img</code>", table_cell), Paragraph("8 files", table_cell), Paragraph("55", table_cell), Paragraph("Abbreviated image reference; overlaps with <code>app_image</code> and <code>ad_image</code>", table_cell)],
        [Paragraph("<code>category_ref</code>", table_cell), Paragraph("8 files", table_cell), Paragraph("36", table_cell), Paragraph("Foreign key using <code>_ref</code> suffix string instead of standardized Category UUID", table_cell)],
        [Paragraph("<code>author_ref</code>", table_cell), Paragraph("8 files", table_cell), Paragraph("28", table_cell), Paragraph("Foreign key storing author display name string rather than persistent Author UUID", table_cell)],
        [Paragraph("<code>item_type</code>", table_cell), Paragraph("8 files", table_cell), Paragraph("24", table_cell), Paragraph("Un-prefixed type discriminator string; lacks namespace control", table_cell)],
        [Paragraph("<code>external_url</code>", table_cell), Paragraph("7 files", table_cell), Paragraph("20", table_cell), Paragraph("Inconsistent with <code>ad_link</code> and embedded media link keys", table_cell)],
        [Paragraph("<code>uploaded_at</code>", table_cell), Paragraph("6 files", table_cell), Paragraph("13", table_cell), Paragraph("Entity-specific upload timestamp used only in media assets", table_cell)],
        [Paragraph("<code>auth_name</code>", table_cell), Paragraph("6 files", table_cell), Paragraph("40", table_cell), Paragraph("Truncated author name key in persona/profile schema", table_cell)],
        [Paragraph("<code>entry_file</code>", table_cell), Paragraph("5 files", table_cell), Paragraph("31", table_cell), Paragraph("Storage file path pointer lacking entity prefix context", table_cell)],
        [Paragraph("<code>ad_link</code>", table_cell), Paragraph("4 files", table_cell), Paragraph("7", table_cell), Paragraph("Domain-specific advertisement target URL; duplicate concept of <code>external_url</code>", table_cell)],
        [Paragraph("<code>app_image</code>", table_cell), Paragraph("4 files", table_cell), Paragraph("17", table_cell), Paragraph("System image asset key; conflicts with <code>featured_img</code>", table_cell)],
        [Paragraph("<code>ad_image</code>", table_cell), Paragraph("4 files", table_cell), Paragraph("9", table_cell), Paragraph("Ad banner asset reference; un-prefixed image key", table_cell)],
        [Paragraph("<code>auth_img</code>", table_cell), Paragraph("3 files", table_cell), Paragraph("14", table_cell), Paragraph("Truncated author avatar image reference key", table_cell)],
        [Paragraph("<code>media_uuid</code>", table_cell), Paragraph("3 files", table_cell), Paragraph("16", table_cell), Paragraph("Prefix collision point between local <code>MediaAsset</code> and <code>ExternalMedia</code>", table_cell)],
    ]
    
    t_audit = Table(audit_data, colWidths=[90, 50, 60, 304])
    t_audit.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), c_primary),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 0.5, c_border),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, c_light]),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(t_audit)
    story.append(Spacer(1, 8))

    story.append(Paragraph("Core Technical Debt Patterns Identified:", h2_style))
    story.append(Paragraph("• <b>Domain Abbreviation Fragmentation:</b> Field names routinely drop entity prefixes or use truncated shorthand (e.g., <code>auth_name</code>, <code>auth_img</code>) leading to ambiguous variable scope in Python functions.", bullet_style))
    story.append(Paragraph("• <b>Fragile String-Based Foreign Keys:</b> Relationships between pages, categories, and authors rely on mutable strings (e.g., <code>author_ref = 'Elton Boehnen'</code>) which break upon display name updates or slug changes.", bullet_style))
    story.append(Paragraph("• <b>Prefix Collision Risks:</b> Both local media uploads and third-party video embeds share the <code>media_</code> prefix (e.g. <code>media_uuid</code>), making search indexing and renderer lookup logic collision-prone.", bullet_style))
    story.append(Spacer(1, 10))

    # -------------------------------------------------------------------------
    # SECTION 3: CANONICAL PREFIX REGISTRY & NAMING MANDATES
    # -------------------------------------------------------------------------
    story.append(Paragraph("3. CANONICAL PREFIX REGISTRY & NAMING MANDATES", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=c_primary, spaceBefore=0, spaceAfter=6))
    
    p3_1 = """
    Under the BEJSON 104a Core Mandate, positional indexing is strictly prohibited—all record access must proceed via the Field Map Cache. To enforce global clarity across all schemas, every field name must strictly follow full <code>snake_case</code> prefixed by its canonical entity tag.
    """
    story.append(Paragraph(p3_1, body_style))
    
    story.append(Paragraph("Canonical Prefix Lookup Table:", h2_style))
    
    prefix_data = [
        [Paragraph("Entity Name", table_header), Paragraph("Canonical Tag", table_header), Paragraph("Primary Key Standard", table_header), Paragraph("Standardized Field Mapping Examples", table_header)],
        [Paragraph("<b>Page Content</b>", table_cell), Paragraph("<code>page_</code>", table_cell), Paragraph("<code>page_uuid</code>", table_cell), Paragraph("<code>page_title</code>, <code>page_slug</code>, <code>page_type</code>, <code>page_created_at</code>", table_cell)],
        [Paragraph("<b>Author Profile</b>", table_cell), Paragraph("<code>author_</code>", table_cell), Paragraph("<code>author_uuid</code>", table_cell), Paragraph("<code>author_display_name</code>, <code>author_avatar_asset_uuid</code>, <code>author_bio</code>", table_cell)],
        [Paragraph("<b>Media Asset</b>", table_cell), Paragraph("<code>asset_</code>", table_cell), Paragraph("<code>asset_uuid</code>", table_cell), Paragraph("<code>asset_file_name</code>, <code>asset_mime_type</code>, <code>asset_file_size_bytes</code>", table_cell)],
        [Paragraph("<b>External Media</b>", table_cell), Paragraph("<code>extmedia_</code>", table_cell), Paragraph("<code>extmedia_uuid</code>", table_cell), Paragraph("<code>extmedia_platform</code>, <code>extmedia_embed_url</code>, <code>extmedia_aspect_ratio</code>", table_cell)],
        [Paragraph("<b>Ad Placement</b>", table_cell), Paragraph("<code>ad_</code>", table_cell), Paragraph("<code>ad_uuid</code>", table_cell), Paragraph("<code>ad_title</code>, <code>ad_target_url</code>, <code>ad_banner_asset_uuid</code>, <code>ad_slot_id</code>", table_cell)],
        [Paragraph("<b>Taxonomy Category</b>", table_cell), Paragraph("<code>cat_</code>", table_cell), Paragraph("<code>cat_uuid</code>", table_cell), Paragraph("<code>cat_name</code>, <code>cat_slug</code>, <code>cat_description</code>, <code>cat_parent_uuid</code>", table_cell)],
        [Paragraph("<b>Taxonomy Tag</b>", table_cell), Paragraph("<code>tag_</code>", table_cell), Paragraph("<code>tag_uuid</code>", table_cell), Paragraph("<code>tag_name</code>, <code>tag_slug</code>", table_cell)],
        [Paragraph("<b>System Setting</b>", table_cell), Paragraph("<code>sys_</code>", table_cell), Paragraph("<code>sys_uuid</code>", table_cell), Paragraph("<code>sys_key</code>, <code>sys_value</code>, <code>sys_updated_at</code>", table_cell)],
    ]
    
    t_prefix = Table(prefix_data, colWidths=[90, 70, 80, 264])
    t_prefix.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), c_primary),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 0.5, c_border),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, c_light]),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(t_prefix)
    story.append(Spacer(1, 8))

    story.append(Paragraph("Collision Resolution Rules:", h2_style))
    story.append(Paragraph("1. <b>Local MediaAsset vs ExternalMedia Collision:</b> Local binary uploads retain <code>asset_</code> (e.g. <code>asset_uuid</code>, <code>asset_file_name</code>), while remote embeds utilize <code>extmedia_</code> (e.g. <code>extmedia_uuid</code>, <code>extmedia_embed_url</code>). This completely eliminates key overlap.", bullet_style))
    story.append(Paragraph("2. <b>Author Profile Synthetic UUID:</b> <code>AuthorProfile</code> introduces <code>author_uuid</code> as primary key. The legacy <code>auth_name</code> string key is replaced by foreign key <code>page_author_uuid</code>.", bullet_style))
    story.append(Spacer(1, 10))

    # -------------------------------------------------------------------------
    # SECTION 4: UNIFIED SYNTHETIC UUID & BEJSON 104a SCHEMA SPECIFICATION
    # -------------------------------------------------------------------------
    story.append(Paragraph("4. UNIFIED SYNTHETIC UUID & BEJSON 104a SCHEMA SPECIFICATION", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=c_primary, spaceBefore=0, spaceAfter=6))
    
    p4_1 = """
    All entities must include a synthetic RFC 4122 Version 4 UUID formatted as <code>&lt;prefix&gt;_uuid</code>. Relying on natural keys (such as page slugs or author names) is strictly prohibited as primary identifiers because natural keys change over time and fail under soft-delete or localization constraints.
    """
    story.append(Paragraph(p4_1, body_style))
    
    story.append(Paragraph("BEJSON 104a Standardized Page Content Schema:", h2_style))
    
    code_json = """{
  "Format": "BEJSON",
  "Format_Version": "104a",
  "Format_Creator": "Elton Boehnen",
  "Session_Id": "f6141ec9-6a9e-4515-ba8a-987b43bfb052",
  "Project_Name": "BEJSON_CMS",
  "Schema_Version": "1.6.0",
  "Records_Type": ["PageContent"],
  "Fields": [
    {"name": "page_uuid", "type": "string"},
    {"name": "page_title", "type": "string"},
    {"name": "page_slug", "type": "string"},
    {"name": "page_type", "type": "string"},
    {"name": "page_category_uuid", "type": "string"},
    {"name": "page_author_uuid", "type": "string"},
    {"name": "page_featured_asset_uuid", "type": "string"},
    {"name": "page_created_at", "type": "string"},
    {"name": "page_updated_at", "type": "string"}
  ],
  "Values": [
    [
      "a3b8c9d1-4e5f-6a7b-8c9d-0e1f2a3b4c5d",
      "Building Scalable BEJSON Taxonomies",
      "building-scalable-bejson-taxonomies",
      "standard",
      "c1a2b3c4-d5e6-7f8a-9b0c-1d2e3f4a5b6c",
      "e5f6a7b8-c9d0-1e2f-3a4b-5c6d7e8f9a0b",
      "f9e8d7c6-b5a4-3f2e-1d0c-9b8a7f6e5d4c",
      "2026-08-10T04:27:00Z",
      "2026-08-10T04:27:00Z"
    ]
  ]
}"""
    story.append(Paragraph(code_json.replace('\n', '<br/>').replace(' ', '&nbsp;'), code_style))
    story.append(Spacer(1, 10))

    # -------------------------------------------------------------------------
    # SECTION 5: PAGE TYPE EXTENSIBILITY ARCHITECTURE
    # -------------------------------------------------------------------------
    story.append(Paragraph("5. PAGE TYPE EXTENSIBILITY ARCHITECTURE", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=c_primary, spaceBefore=0, spaceAfter=6))
    
    p5_1 = """
    To prevent schema pollution with sparse, type-specific columns, BEJSON CMS employs a <b>Polymorphic Variant Metadata Pattern</b>. The core <code>PageContent</code> schema handles common attributes, while extended attributes live in specialized sub-record schemas linked by <code>page_uuid</code>.
    """
    story.append(Paragraph(p5_1, body_style))
    
    story.append(Paragraph("Page Type Specifications:", h2_style))
    story.append(Paragraph("1. <b>Standard HTML Page (<code>page_type = 'standard'</code>):</b> Standard articles with HTML content stored in <code>page_body_html</code>.", bullet_style))
    story.append(Paragraph("2. <b>Video Hub Article (<code>page_type = 'video'</code>):</b> Attaches a <code>PageVideoMetadata</code> record containing video embed URLs, duration, provider tags, and transcript asset UUIDs.", bullet_style))
    story.append(Paragraph("3. <b>Document Hub Page (<code>page_type = 'document'</code>):</b> Attaches a <code>PageDocumentMetadata</code> record linking primary PDF/EPUB asset UUIDs, version strings, byte sizes, and download rules.", bullet_style))
    
    story.append(Spacer(1, 6))
    story.append(Paragraph("Python Strategy Renderer Pattern:", h2_style))
    
    code_py = """# Python Renderer Strategy Pattern for Polymorphic Page Types
from typing import Dict, Any

class PageTypeRenderer:
    def render(self, page_data: Dict[str, Any], meta_data: Dict[str, Any]) -> str:
        raise NotImplementedError

class StandardPageRenderer(PageTypeRenderer):
    def render(self, page_data: Dict[str, Any], meta_data: Dict[str, Any]) -> str:
        return f"&lt;article class='page-standard'&gt;&lt;h1&gt;{page_data['page_title']}&lt;/h1&gt;{page_data['page_body_html']}&lt;/article&gt;"

class VideoPageRenderer(PageTypeRenderer):
    def render(self, page_data: Dict[str, Any], meta_data: Dict[str, Any]) -> str:
        embed_url = meta_data.get('video_embed_url', '')
        return f\"\"\"&lt;article class='page-video'&gt;
          &lt;h1&gt;{page_data['page_title']}&lt;/h1&gt;
          &lt;div class='video-player'&gt;&lt;iframe src='{embed_url}'&gt;&lt;/iframe&gt;&lt;/div&gt;
          &lt;div&gt;{page_data['page_body_html']}&lt;/div&gt;
        &lt;/article&gt;\"\"\"

class DocumentPageRenderer(PageTypeRenderer):
    def render(self, page_data: Dict[str, Any], meta_data: Dict[str, Any]) -> str:
        doc_uuid = meta_data.get('doc_asset_uuid', '')
        return f\"\"\"&lt;article class='page-document'&gt;
          &lt;h1&gt;{page_data['page_title']}&lt;/h1&gt;
          &lt;div class='doc-download-card'&gt;
            &lt;p&gt;PDF Document ({meta_data.get('doc_file_size_formatted', '')})&lt;/p&gt;
            &lt;a href='/assets/download/{doc_uuid}' class='btn btn-primary'&gt;Download PDF&lt;/a&gt;
          &lt;/div&gt;
        &lt;/article&gt;\"\"\"

RENDERER_REGISTRY = {
    'standard': StandardPageRenderer(),
    'video': VideoPageRenderer(),
    'document': DocumentPageRenderer()
}"""
    story.append(Paragraph(code_py.replace('\n', '<br/>').replace(' ', '&nbsp;'), code_style))
    story.append(Spacer(1, 10))

    # -------------------------------------------------------------------------
    # SECTION 6: IMPLEMENTATION ROADMAP & MIGRATION PHASES
    # -------------------------------------------------------------------------
    story.append(Paragraph("6. IMPLEMENTATION ROADMAP & MIGRATION PHASES", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=c_primary, spaceBefore=0, spaceAfter=6))
    
    p6_1 = """
    Migrating existing storage containers and 84 Python source files requires a structured 4-phase rollout to guarantee data safety and zero publisher downtime:
    """
    story.append(Paragraph(p6_1, body_style))
    
    roadmap_data = [
        [Paragraph("Phase", table_header), Paragraph("Focus & Deliverables", table_header), Paragraph("Target Modules", table_header), Paragraph("Estimated Effort", table_header)],
        [Paragraph("<b>Phase 1</b>", table_cell), Paragraph("<b>Prefix Registry & Alias Adapter Layer:</b> Build <code>BEJSON_Taxonomy.py</code> lookup maps. Support dual reads for legacy & new keys.", table_cell), Paragraph("<code>src/lib/lib_bejson_core.py</code><br/><code>src/lib/BEJSON_Taxonomy.py</code>", table_cell), Paragraph("12 Hours (1-2 Days)", table_cell)],
        [Paragraph("<b>Phase 2</b>", table_cell), Paragraph("<b>Data Migration Scripting:</b> Execute batch conversion on all <code>storage/mfdb/</code> containers. Inject synthetic UUIDs across all records.", table_cell), Paragraph("<code>storage/mfdb/*.json</code><br/><code>tools/migrate_taxonomy.py</code>", table_cell), Paragraph("16 Hours (2 Days)", table_cell)],
        [Paragraph("<b>Phase 3</b>", table_cell), Paragraph("<b>Publisher & Blueprint Refactoring:</b> Update <code>BEJSON_CMS_Publisher.py</code>, <code>Content</code>, <code>System</code>, <code>Media</code>, <code>Interface</code> blueprints to use new field map keys.", table_cell), Paragraph("<code>src/web/BEJSON_CMS_*.py</code><br/><code>resources/templates/*.html</code>", table_cell), Paragraph("24 Hours (3 Days)", table_cell)],
        [Paragraph("<b>Phase 4</b>", table_cell), Paragraph("<b>Page Type Engine & Documentation:</b> Deploy Video/Document rendering strategies and produce updated API spec docs.", table_cell), Paragraph("<code>src/web/BEJSON_CMS_Renderers.py</code><br/><code>docs/taxonomy_guide.md</code>", table_cell), Paragraph("16 Hours (2 Days)", table_cell)],
    ]
    
    t_roadmap = Table(roadmap_data, colWidths=[55, 185, 164, 100])
    t_roadmap.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), c_primary),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 0.5, c_border),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, c_light]),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(t_roadmap)
    story.append(Spacer(1, 10))

    # -------------------------------------------------------------------------
    # SECTION 7: CONCLUSION & SIGN-OFF
    # -------------------------------------------------------------------------
    story.append(Paragraph("7. CONCLUSION & SIGN-OFF", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=c_primary, spaceBefore=0, spaceAfter=6))
    
    p7_1 = """
    By implementing the <b>Canonical Prefix Registry</b>, instituting standard <code>&lt;prefix&gt;_uuid</code> identifiers, and deploying polymorphic strategy renderers, BEJSON CMS eliminates legacy naming debt and establishes a resilient foundation for advanced media and document publishing capabilities.
    """
    story.append(Paragraph(p7_1, body_style))
    story.append(Spacer(1, 8))

    signoff_data = [
        [Paragraph("<b>Report Prepared By:</b> Elton Boehnen", table_cell), Paragraph("<b>Contact:</b> boehnenelton2024@gmail.com", table_cell)],
        [Paragraph("<b>Portfolio:</b> boehnenelton2024.pages.dev", table_cell), Paragraph("<b>GitHub:</b> github.com/boehnenelton", table_cell)]
    ]
    t_signoff = Table(signoff_data, colWidths=[252, 252])
    t_signoff.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_light),
        ('BOX', (0,0), (-1,-1), 1, c_accent),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(t_signoff)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated PDF: {filename}")

if __name__ == '__main__':
    create_pdf()
