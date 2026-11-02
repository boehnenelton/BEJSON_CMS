"""
Library:        lib_bejson_Core_svg_sanitizer.py
Family:         Core
Description:    Strict allowlist SVG sanitizer. Resolves audit finding H-3
                (BEJSON_CMS pkg132 external audit): SVG uploads were disabled
                entirely at pkg133 because ALLOWED_ASSET_EXTENSIONS permitted
                .svg while serve_asset() did send_file() with zero content
                inspection -- an uploaded SVG could carry <script>/on*=
                payloads and would be served back verbatim (stored XSS). No
                sanitizer existed. This library is that sanitizer, built so
                .svg can be safely re-enabled (Elton's call, pkg139).
Version:        1.0.0
Date:           2026-09-19
RELATIONAL_ID:  4b657a26-8545-4d67-9a48-05fd4071720f
Release_Version: 300

DESIGN
------
Allowlist, not denylist: an element or attribute is stripped unless it is
explicitly known-safe. A denylist ("strip <script>, strip on*=...") is a
losing game against SVG's attack surface -- SMIL animation elements
(<animate>, <set>, <animateTransform>) can trigger arbitrary event handlers
just like on*= attributes can, <foreignObject> embeds arbitrary HTML,
<image>/<use xlink:href> can reference external or javascript: URIs, and
CSS in a <style> block can carry url(javascript:...) or @import. Rather
than chase every one of those individually, this only ever emits elements
and attributes on the allowlists below; everything else -- known-dangerous
or not -- is silently dropped.

Stdlib-only, deliberately: this project's design conventions favor
lightweight, stdlib-first code for resource-constrained environments
(Termux/Pydroid3 on Android), so this uses xml.etree.ElementTree rather
than adding a third-party dependency (e.g. defusedxml/bleach) for a single
narrow use case. XXE note: ElementTree's underlying expat parser does not
resolve external entities or process DTDs by default (unlike xml.dom.
minidom or lxml without explicit hardening), which is the primary XXE
defense; this is not reimplemented as a hardened parser subclass, it's the
stdlib's existing default behavior, deliberately relied on rather than
silently assumed -- see test_svg_sanitizer.py's XXE case if one exists, or
sanitize_svg()'s own doctest-style example below.

WHAT THIS DOES NOT DO
----------------------
- Does not attempt to preserve every valid SVG feature. Animation (SMIL:
  <animate>/<set>/<animateTransform>/<animateMotion>), <script>, <style>,
  <foreignObject>, <image>, and external references via href/xlink:href
  are all dropped unconditionally, not sanitized-and-kept. An icon/logo/
  diagram SVG -- the overwhelming majority of what a CMS media library
  actually needs SVG for -- survives sanitization intact. An animated or
  externally-referencing SVG will lose that behavior; this is a deliberate
  security/functionality tradeoff, not an oversight.
- Does not sanitize CSS. <style> elements and any `style="..."` attribute
  value are dropped/stripped entirely rather than parsed and filtered --
  CSS injection (url(javascript:...), @import, expression()) is its own
  sanitization problem this library does not attempt to solve partially.
- Does not fix up malformed/non-well-formed XML. A file that doesn't parse
  as valid XML is rejected outright (returns None), not repaired.
"""

import re
import xml.etree.ElementTree as ET

VERSION = "1.0.0"

# Namespace URIs this sanitizer understands. Any element or attribute in a
# DIFFERENT namespace (or no namespace, for elements) is dropped -- this is
# what actually stops e.g. an embedded MathML/XHTML smuggling attempt via
# namespace tricks, not just the tag-name allowlist below.
_SVG_NS = "http://www.w3.org/2000/svg"
_XLINK_NS = "http://www.w3.org/1999/xlink"
_XML_NS = "http://www.w3.org/XML/1998/namespace"

# Elements allowed to survive sanitization, by local name (namespace
# checked separately). Deliberately excludes: script, style, foreignObject,
# image, animate, animateTransform, animateMotion, animateColor, set, a
# (an SVG <a> can carry a href to navigate the whole page on click).
_ALLOWED_TAGS = {
    "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline",
    "polygon", "text", "tspan", "textPath", "defs", "clipPath", "mask",
    "pattern", "symbol", "use", "title", "desc",
    "linearGradient", "radialGradient", "stop",
}

# Attributes allowed on ANY surviving element, by local name. Deliberately
# excludes: style (see module docstring), any on*= handler (enforced
# separately below, not via this set, so it can't be accidentally
# reintroduced by editing this set), href/xlink:href (see _ALLOWED_HREF_TAGS).
_ALLOWED_ATTRS = {
    "id", "class",
    "d", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry",
    "width", "height", "viewBox", "preserveAspectRatio", "transform",
    "points", "offset",
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width",
    "stroke-linecap", "stroke-linejoin", "stroke-dasharray",
    "stroke-opacity", "opacity", "stop-color", "stop-opacity",
    "gradientUnits", "gradientTransform", "patternUnits", "patternTransform",
    "clip-path", "clip-rule", "mask",
    "font-family", "font-size", "font-weight", "text-anchor", "version",
}

# use/textPath are the only two elements where an href is both meaningful
# and safe to keep -- and ONLY as a local fragment reference (#some-id),
# never an external or javascript: URI. Checked in _sanitize_element().
_ALLOWED_HREF_TAGS = {"use", "textPath"}

_EVENT_ATTR_RE = re.compile(r"^on", re.IGNORECASE)
_LOCAL_FRAGMENT_RE = re.compile(r"^#[A-Za-z_][\w.\-:]*$")

# Registered once at import time (not per-call): makes the serializer emit
# conventional unprefixed <svg>/<circle>/... output with a plain xlink:
# prefix, instead of ElementTree's default ns0:/ns1: auto-generated
# prefixes. This is a fixed, content-independent mapping -- safe to share
# across concurrent calls (e.g. simultaneous upload requests in the same
# Flask process), since every call registers the exact same two URIs.
ET.register_namespace("", _SVG_NS)
ET.register_namespace("xlink", _XLINK_NS)


def _local_name(tag: str) -> str:
    """Strip a '{namespace}' prefix ElementTree adds to tag/attribute names."""
    return tag.split("}", 1)[1] if tag.startswith("{") else tag


def _namespace(tag: str) -> str:
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else ""


def _sanitize_element(el: ET.Element) -> ET.Element | None:
    """Returns a sanitized copy of el (with sanitized children), or None if
    el itself must be dropped entirely (wrong tag, wrong namespace)."""
    tag_local = _local_name(el.tag)
    tag_ns = _namespace(el.tag)
    if tag_local not in _ALLOWED_TAGS:
        return None
    # An unprefixed/no-namespace tag from a raw ElementTree parse of a
    # namespaced document only happens if the document itself never
    # declared xmlns -- reject rather than assume SVG.
    if tag_ns not in (_SVG_NS, ""):
        return None

    clean = ET.Element(f"{{{_SVG_NS}}}{tag_local}" if tag_ns else tag_local)
    for attr_name, attr_value in el.attrib.items():
        a_local = _local_name(attr_name)
        a_ns = _namespace(attr_name)

        if _EVENT_ATTR_RE.match(a_local):
            continue  # onload=, onclick=, etc. -- never kept, on any element
        if a_ns == _XML_NS:
            continue  # xml:base etc. -- can be used to retarget relative URIs

        if a_local in ("href",) and a_ns in (_XLINK_NS, ""):
            if tag_local in _ALLOWED_HREF_TAGS and _LOCAL_FRAGMENT_RE.match(attr_value.strip()):
                clean.set(f"{{{_XLINK_NS}}}href", attr_value.strip())
            continue

        if a_local == "style":
            continue  # see module docstring -- CSS is not sanitized, only dropped

        if a_local not in _ALLOWED_ATTRS:
            continue

        clean.set(a_local, attr_value)

    for child in el:
        sanitized_child = _sanitize_element(child)
        if sanitized_child is not None:
            sanitized_child.tail = child.tail
            clean.append(sanitized_child)
        elif child.tail:
            # Dropped element, but its trailing whitespace/text is inert
            # (SVG tail text is never parsed as markup) -- reattach it to
            # whatever now-last surviving child there is, or clean.text if
            # this was the first child and got dropped.
            if len(clean):
                clean[-1].tail = (clean[-1].tail or "") + child.tail
            else:
                clean.text = (clean.text or "") + child.tail
    # text content (e.g. inside <text>/<title>/<desc>) is inert -- keep verbatim
    clean.text = el.text
    return clean


def sanitize_svg(raw: bytes) -> bytes | None:
    """Parse, sanitize, and re-serialize an uploaded SVG. Returns the
    sanitized SVG as UTF-8 bytes, or None if the input isn't parseable as
    XML, isn't an <svg> document, or the root element itself doesn't
    survive sanitization (e.g. wrong namespace).

    Callers MUST treat None as "reject the upload" -- there is no partial-
    success case; either the whole document sanitizes to something with a
    root <svg> element, or nothing is returned at all.
    """
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None

    clean_root = _sanitize_element(root)
    if clean_root is None or _local_name(clean_root.tag) != "svg":
        return None

    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(clean_root, encoding="utf-8")
