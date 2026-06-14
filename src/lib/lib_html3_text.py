"""
Library:      lib_html3_text.py
Family:       HTML3
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      3.0.0 OFFICIAL
Format_Creator: Elton Boehnen
Date:         2026-06-10
Description:  Standardized rich text and markdown rendering for HTML3 components.
"""

import html as html_mod
import logging

VERSION = "3.0.0"
SCRIPT_NAME = "lib_html3_text.py"
RELATIONAL_ID = "e5f6g7h8-1i2j-3k4l-5m6n-7o8p9q0r1s2t"

# Try to import markdown
try:
    import markdown
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False
    logging.warning("[HTML3] python-markdown not found. Falling back to basic text rendering.")

def html_render_text(text: str) -> str:
    """
    Renders text as HTML. 
    If markdown is available, it processes markdown.
    Otherwise, it performs basic paragraph and line break conversion.
    """
    if not text:
        return ""
    
    if HAS_MARKDOWN:
        try:
            # Render markdown with common extensions
            return markdown.markdown(text, extensions=['fenced_code', 'tables', 'nl2br'])
        except Exception as e:
            logging.error(f"[HTML3] Markdown rendering failed: {e}")
            # Fallback to basic if markdown fails
    
    # Basic Fallback: HTML Escape + Paragraphs + Line Breaks
    # 1. Escape HTML to prevent XSS if we are in fallback mode
    # (Note: Markdown library handles this via its own logic/extensions if configured, 
    # but here we are in the 'no markdown' branch).
    safe_text = html_mod.escape(text)
    
    # 2. Convert double newlines to paragraphs
    paragraphs = safe_text.split("\n\n")
    html_paragraphs = [f"<p>{p.replace('\n', '<br>')}</p>" for p in paragraphs if p.strip()]
    
    return "\n".join(html_paragraphs)

def is_html(text: str) -> bool:
    """Simple heuristic to check if text contains HTML tags."""
    return "<" in text and ">" in text
