# BEJSON_CMS - Decomposition Recipe
**Type:** Python / Flask / MFDB
**Purpose:** Unified content management system based on the MFDB architecture.
**Date Analyzed:** 2026-06-14

## Identity
- **Name:** BEJSON_CMS
- **Type:** Full-Stack CMS
- **Purpose:** Manages BEJSON 104/104a/104db records across an MFDB-federated system.
- **Status:** Active
- **Dependencies:** Flask, Werkzeug, BeautifulSoup4, PIL (Pillow), lib_bejson_core, lib_mfdb_core.

## Architecture Overview
BEJSON_CMS is an authoritative administrative layer for managing MFDB-federated data. It uses a Flask-based web interface and a unified CLI toolkit (`cms-manage.py`) for backend operations. The system is designed with atomic write mandates and standard library bootstrapping.

## File Structure
```
BEJSON_CMS/
├── src/
│   ├── cli/ (Record management tools)
│   ├── lib/ (Extensive BEJSON/MFDB library stack)
│   ├── web/ (Flask CMS, Page Editor, Profile Manager)
│   └── cms-manage.py (Unified CLI Toolkit)
├── storage/ (MFDB archives and data)
├── resources/ (CSS styles and HTML skeletons)
├── AGENTS.MD (Machine execution layer)
├── README.md (Human vibe layer)
└── SYSTEM_MANUAL.md (Technical documentation)
```

## Styling
### Color Palette
- **Primary:** #DE2626 (Accent Red)
- **Secondary:** #111111 (Dark Base)

### Typography
- **Headings:** Inter / System Sans
- **Body:** Inter / System Sans

### CSS Patterns
- BECSS (Namespaced BEM)
- HTML3 Layout Patterns

## Classes & Interfaces
### MFDB_CMS_Manager (lib_cms_mfdb)
- **Purpose:** Core state manager for MFDB repositories.
- **Methods:**
  - `mount_system()` -> Initialized repository.
  - `repack_system()` -> Archives dirty changes.
  - `create_page(title, category, type, content)` -> Creates new page UUID.
  - `import_html_as_page(html, title, category, author)` -> Ingests HTML content.

## Functions
### _check_auth(username, password)
- **Purpose:** Basic authentication gatekeeper.
- **Returns:** Boolean.

### bejson_core_atomic_write(path, data)
- **Purpose:** Ensures data integrity via temp-then-rename pattern.
- **Returns:** Boolean success signal.

## Features (Categorized)
### Core Management
- ✓ MFDB Federation — Multi-file database orchestration.
- ✓ Atomic Persistence — Corruption-proof data writes.
- ✓ Unified CLI — Single entry point for system maintenance.

### Web Interface
- ✓ Page Editor v2 — Real-time content manipulation.
- ✓ HTML Import — Automated ingestion of external HTML documents.
- ✓ Ad & Author Manager — Integrated taxonomy and entity controls.

## Reconstruction Checklist
- [ ] Initialize `storage/mfdb` hierarchy.
- [ ] Bootstrap `src/lib` dependencies.
- [ ] Configure `CMS_USER` and `CMS_PASSWORD` environment variables.
- [ ] Mount the system using `python3 src/cms-manage.py mount`.
