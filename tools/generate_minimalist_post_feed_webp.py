#!/usr/bin/env python3
# ==============================================================================
# Script Name: generate_minimalist_post_feed_webp.py
# Description: Batch generate minimalist, lightweight 840x420 WebP post feed graphics
# using Graphics 105 and update BEJSON_CMS pages.
# Version: 100
# Author: Elton Boehnen · boehnenelton2024@gmail.com
# Relational ID: 4d28e719-8b3a-49c2-9e12-3a5f9b1c7065
# License: PolyForm-Noncommercial-1.0.0
# ==============================================================================

import asyncio
import hashlib
import html
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("feed_webp_generator")

CMS_ROOT = Path("/storage/emulated/0/Admin/Dev/Repos/BEJSON_CMS")
ASSETS_DIR = CMS_ROOT / "storage" / "mfdb" / "assets"
MEDIA_FILE = CMS_ROOT / "storage" / "mfdb" / "site_master" / "data" / "mediaasset.bejson"
PAGE_FILE = CMS_ROOT / "storage" / "mfdb" / "site_master" / "data" / "pagerecord.bejson"

GRAPHICS_105 = Path("/storage/emulated/0/Admin/Libraries/libraries_105/Lib_PY/Graphics")
if GRAPHICS_105.exists() and str(GRAPHICS_105) not in sys.path:
    sys.path.insert(0, str(GRAPHICS_105))

import lib_bejson_Graphics_graphics_core as gc


POSTS_TO_PROCESS = [
    {
        "uuid": "a8a81b42-753a-493c-a539-47e8a659e04a",
        "slug": "json_attention_tax_feed",
        "title": "THE JSON ATTENTION TAX ON LLMS",
        "subtitle": "Eliminating Structural Bloat with Zero-SQL Positional Matrices",
        "tag": "BEJSON 105 • AI ATTENTION",
        "components": [
            ("ATTENTION BUDGET", "Token Density · Zero Structural Noise"),
            ("POSITIONAL MATRIX", "Dense 105 Arrays · O(1) Key Cache"),
            ("PARSER SUBSYSTEM", "Zero-SQL Fast Path · Low Memory"),
        ]
    },
    {
        "uuid": "5cbdda76-937c-48ed-a697-6b38eec5efbd",
        "slug": "database_passwords_memory_security_feed",
        "title": "DATABASE PASSWORDS & RAM SECURITY",
        "subtitle": "Ephemeral In-Memory Keys and Zero-Persistence Security",
        "tag": "BEJSON 105 • SECURITY VAULT",
        "components": [
            ("VOLATILE RAM KEYS", "Zero Disk Entropy · Ephemeral Tokens"),
            ("AES-256-GCM CRYPTO", "Authenticated Envelope · Web Crypto"),
            ("SANDBOX ISOLATION", "Deterministic Scrubbing on Shutdown"),
        ]
    },
    {
        "uuid": "1d2ddf2f-c5a5-44fb-b76d-b8b769a3e6c1",
        "slug": "bejson_104_foundations_zero_bloat_feed",
        "title": "BEJSON 104 FOUNDATIONS",
        "subtitle": "Annihilating Key Bloat with Strict Positional Schemas",
        "tag": "BEJSON 104 • CORE FOUNDATION",
        "components": [
            ("POSITIONAL MATRICES", "O(1) Field Map · Zero Repeated Keys"),
            ("DENSE 104 STORAGE", "Compact Data Serialization on Disk"),
            ("SPEC ENFORCEMENT", "Strict Primitive Types · Zero Drift"),
        ]
    },
    {
        "uuid": "2ec89c17-9b49-40ec-a29f-ae89ecf9fd6f",
        "slug": "legacy_bejson_104_libraries_polyglot_feed",
        "title": "LEGACY BEJSON 104 POLYGLOT GUIDE",
        "subtitle": "Cross-Runtime Interoperability in Python, JS, and Bash",
        "tag": "BEJSON 104 • POLYGLOT RUNTIME",
        "components": [
            ("PYTHON RUNTIME", "Zero-Dependency Lib · High Velocity"),
            ("JAVASCRIPT RUNTIME", "Node & Browser · Web Crypto Engine"),
            ("BASH UTILITIES", "Minimal POSIX Shell Tooling · Low Footprint"),
        ]
    },
    {
        "uuid": "497ad03d-789e-46e1-8fc0-6c41c4f786bb",
        "slug": "bejson_105_relational_flat_files_feed",
        "title": "BEJSON 105: RELATIONAL FLAT FILES",
        "subtitle": "UUIDv4 Integrity Era, Row Hashing, and Zero-SQL MFDB",
        "tag": "BEJSON 105 • RELATIONAL INTEGRITY",
        "components": [
            ("UUIDV4 INTEGRITY", "Column-0 Primary Keys · Global Uniqueness"),
            ("ROW HASH SIGNING", "SHA-256 Row-Level Fingerprinting"),
            ("BIDIRECTIONAL MFDB", "Cross-Entity Cascades · Manifest Links"),
        ]
    },
    {
        "uuid": "a51f9b71-6de2-4e57-930c-bf2e344c9c2d",
        "slug": "designing_2d_action_rpgs_bejson_105_feed",
        "title": "DESIGNING 2D ACTION RPGS IN 105",
        "subtitle": "Decoupling Simulation State, Tilemaps, and Sprite Sheets",
        "tag": "BEJSON 105 • GAMING ENGINE",
        "components": [
            ("SPRITE ANIMATION", "Coordinate Sheets · State Machines"),
            ("TILEMAP COLLISION", "Grid Collisions · Layered Rendering"),
            ("SIMULATION ENGINE", "Fixed Tick Rate · Zero-SQL Flat Files"),
        ]
    }
]


def render_feed_card_svg(
    title: str,
    subtitle: str,
    tag: str,
    components: list[tuple[str, str]],
    width: int = 840,
    height: int = 420
) -> str:
    """Renders sleek, compact 840x420 minimalist feed card SVG."""
    e_title = html.escape(title.upper())
    e_subtitle = html.escape(subtitle)
    e_tag = html.escape(tag.upper())

    spec_blocks = []
    for idx, (comp_title, comp_desc) in enumerate(components[:3]):
        y_pos = idx * 44
        ct = html.escape(comp_title.upper())
        cd = html.escape(comp_desc)
        spec_blocks.append(f"""        <g transform="translate(0, {y_pos})">
          <rect x="0" y="0" width="540" height="36" fill="#16161C" stroke="#26262E" stroke-width="1" />
          <rect x="0" y="0" width="28" height="36" fill="#1E1E26" />
          <text x="14" y="22" fill="#DE2626" font-size="11" font-family="monospace" font-weight="800" text-anchor="middle">[{idx+1:02d}]</text>
          <text x="38" y="15" fill="#FFFFFF" font-size="11" font-family="system-ui, -apple-system, sans-serif" font-weight="700" letter-spacing="0.5">{ct}</text>
          <text x="38" y="28" fill="#888894" font-size="9" font-family="monospace">{cd}</text>
        </g>""")

    joined_specs = "\n".join(spec_blocks)

    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
  <!-- Obsidian Substrate -->
  <rect width="{width}" height="{height}" fill="#111113" />

  <!-- Outer Precision Boundary -->
  <rect x="18" y="18" width="{width - 36}" height="{height - 36}" fill="#0E0E12" stroke="#26262E" stroke-width="1.5" />
  <rect x="18" y="18" width="4" height="{height - 36}" fill="#DE2626" />

  <!-- Coordinate Crosshairs -->
  <path d="M 38 32 L 38 42 M 33 37 L 43 37" stroke="#3A3A44" stroke-width="1.5" />
  <path d="M {width - 38} 32 L {width - 38} 42 M {width - 43} 37 L {width - 33} 37" stroke="#3A3A44" stroke-width="1.5" />

  <!-- Header Tag Pill -->
  <g transform="translate(42, 38)">
    <rect x="0" y="0" width="180" height="20" fill="#1C1C22" stroke="#DE2626" stroke-width="1" />
    <text x="90" y="14" fill="#DE2626" font-size="9" font-family="monospace" font-weight="800" text-anchor="middle" letter-spacing="1.5">{e_tag}</text>
  </g>

  <!-- Article Headline & Subtitle -->
  <text x="42" y="94" fill="#FFFFFF" font-size="20" font-family="system-ui, -apple-system, sans-serif" font-weight="800" letter-spacing="0.5">{e_title}</text>
  <text x="42" y="118" fill="#A1A1AA" font-size="12" font-family="system-ui, -apple-system, sans-serif" font-weight="500">{e_subtitle}</text>
  <line x1="42" y1="134" x2="{width - 42}" y2="134" stroke="#262630" stroke-width="1" />

  <!-- Left Sharp Isometric Cube Substrate -->
  <g transform="translate(130, 240)">
    <circle cx="0" cy="0" r="60" fill="none" stroke="#262630" stroke-width="1" stroke-dasharray="3,3" />
    <circle cx="0" cy="0" r="44" fill="none" stroke="#DE2626" stroke-width="1" opacity="0.3" />
    <polygon points="0,-36 32,-18 0,0 -32,-18" fill="#FFFFFF" stroke="#FFFFFF" stroke-width="1" stroke-linejoin="round" />
    <polygon points="0,-28 24,-14 0,-2 -24,-14" fill="#111113" opacity="0.9" />
    <polygon points="-32,-18 0,0 0,36 -32,18" fill="#1C1C22" stroke="#FFFFFF" stroke-width="1" stroke-linejoin="round" />
    <polygon points="0,0 32,-18 32,18 0,36" fill="#DE2626" stroke="#FFFFFF" stroke-width="1" stroke-linejoin="round" />
  </g>
  <text x="130" y="325" fill="#71717A" font-size="9" font-family="monospace" font-weight="600" text-anchor="middle" letter-spacing="1">BEJSON SUBSTRATE</text>

  <!-- Right 3-Pillar Component Specifications -->
  <g transform="translate(225, 155)">
{joined_specs}
  </g>

  <!-- Footer Line & Metadata -->
  <line x1="42" y1="365" x2="{width - 42}" y2="365" stroke="#262630" stroke-width="1" />
  <text x="42" y="385" fill="#71717A" font-size="10" font-family="monospace" font-weight="600" letter-spacing="1">ELTON BOEHNEN • ZERO-SQL FLAT FILE CMS</text>

  <!-- Brand Lock -->
  <g transform="translate({width - 150}, 372)">
    <text x="0" y="12" fill="#FFFFFF" font-size="13" font-family="system-ui, -apple-system, sans-serif" font-weight="900" letter-spacing="1">BEJSON</text>
    <polygon points="62,2 69,5 62,9 55,5" fill="#DE2626" />
  </g>
</svg>"""


def register_media(asset_filename: str, file_path: Path):
    """Registers media asset in mediaasset.bejson."""
    if not MEDIA_FILE.exists():
        return
    with open(MEDIA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    fields = [f["name"] for f in data["Fields"]]
    name_idx = fields.index("asset_filename")
    existing = {r[name_idx] for r in data.get("Values", [])}

    if asset_filename not in existing:
        raw_bytes = file_path.read_bytes()
        sha = hashlib.sha256(raw_bytes).hexdigest()
        size = len(raw_bytes)
        ext = file_path.suffix.lower()
        mime = "image/webp" if ext == ".webp" else ("image/svg+xml" if ext == ".svg" else "image/png")
        now_iso = datetime.now(timezone.utc).isoformat()
        row = [asset_filename, asset_filename, sha, size, mime, now_iso]
        data["Values"].append(row)
        with open(MEDIA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Registered {asset_filename} ({size} bytes) in mediaasset.bejson")


def update_page_featured_img(page_uuid: str, featured_img_name: str):
    """Updates page_featured_img in pagerecord.bejson."""
    if not PAGE_FILE.exists():
        return
    with open(PAGE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    fields = [f["name"] for f in data["Fields"]]
    u_idx = fields.index("page_uuid")
    img_idx = fields.index("page_featured_img")

    updated = False
    for r in data.get("Values", []):
        if r[u_idx] == page_uuid:
            r[img_idx] = featured_img_name
            updated = True
            logger.info(f"Updated page {page_uuid} featured_img -> {featured_img_name}")
            break

    if updated:
        with open(PAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


async def build_graphics():
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    for item in POSTS_TO_PROCESS:
        slug = item["slug"]
        page_uuid = item["uuid"]
        title = item["title"]
        subtitle = item["subtitle"]
        tag = item["tag"]
        comps = item["components"]

        svg_filename = f"{slug}.svg"
        png_filename = f"{slug}.png"
        webp_filename = f"{slug}.webp"

        svg_path = ASSETS_DIR / svg_filename
        png_path = ASSETS_DIR / png_filename
        webp_path = ASSETS_DIR / webp_filename

        logger.info(f"Generating 840x420 graphic for: {title}")

        # 1. Render SVG
        svg_content = render_feed_card_svg(title, subtitle, tag, comps, width=840, height=420)
        svg_path.write_text(svg_content, encoding="utf-8")

        # 2. Render high-DPI raster PNG via Playwright still frame
        await gc.render_still_frame(
            width_px=840,
            height_px=420,
            output_path=str(png_path),
            svg_markup=svg_content,
            device_scale=2,
        )

        # 3. Convert to highly compressed WebP (quality 82, method 6 for max compression)
        im = Image.open(png_path)
        im.save(webp_path, "WEBP", quality=82, method=6)
        webp_size = webp_path.stat().st_size
        logger.info(f"[✓] Compiled {webp_filename}: {webp_size} bytes (ultra-compact)")

        # 4. Register in CMS and update page featured image to WebP
        register_media(svg_filename, svg_path)
        register_media(png_filename, png_path)
        register_media(webp_filename, webp_path)
        update_page_featured_img(page_uuid, webp_filename)

    logger.info("[✓] All 6 post feed graphics generated, WebP converted, and registered.")


if __name__ == "__main__":
    asyncio.run(build_graphics())
