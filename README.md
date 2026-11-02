# BEJSON CMS: Enterprise Zero-SQL Positional CMS & Static Site Publisher

**BEJSON CMS** is a high-density, zero-SQL Content Management System, Dynamic Headless REST Engine, and Static Site Generator engineered to operate entirely without external relational database engines (such as MySQL, PostgreSQL, or SQLite). Every structural entity—articles, hierarchical categories, author profiles, hash-deduplicated media assets, external media embeds, banner advertisements, responsive navigation links, site configuration key-value registries, social profiles, BKS-1 standardized 4-part job blueprints, and standalone containerized web applications—is stored in positional matrix files governed by a master Multi-File Database (MFDB) manifest (`storage/mfdb/site_master/104a.mfdb.bejson`).

- **Author**: Elton Boehnen
- **Contact**: boehnenelton2024@gmail.com · [boehnenelton2024.pages.dev](https://boehnenelton2024.pages.dev) · [github.com/boehnenelton](https://github.com/boehnenelton)
- **License**: PolyForm Noncommercial License 1.0.0
- **Version**: V18.31 (Package PKG135)

---

## Table of Contents
- [Executive Overview & Core Philosophy](#executive-overview--core-philosophy)
- [Prerequisites & Environment Setup](#prerequisites--environment-setup)
- [Service Launchers & Operational Modes](#service-launchers--operational-modes)
- [Visual Interface Tour & Audit Telemetry](#visual-interface-tour--audit-telemetry)
- [Complete Feature Catalog & Capabilities Matrix](#complete-feature-catalog--capabilities-matrix)
- [User Workflows & Operational Guides](#user-workflows--operational-guides)
  - [1. Article Authoring & Editing in PageEditor V2](#1-article-authoring--editing-in-pageeditor-v2)
  - [2. Standardized 4-Part Blog Job System (BKS-1)](#2-standardized-4-part-blog-job-system-bks-1)
  - [3. Markdown Import & Batch Conversion Pipeline](#3-markdown-import--batch-conversion-pipeline)
  - [4. Media Asset Pipeline & Thumbnails](#4-media-asset-pipeline--thumbnails)
  - [5. Standalone Web Application Hosting](#5-standalone-web-application-hosting)
  - [6. Static Site Compilation & Cloudflare Publishing](#6-static-site-compilation--cloudflare-publishing)
- [System Architecture & Microservice Topology](#system-architecture--microservice-topology)
  - [Admin Suite (:5001) & Architectural Blueprints](#admin-suite-5001--architectural-blueprints)
  - [Static Site Publisher (:5002)](#static-site-publisher-5002)
  - [Page Editor V1 (:5003)](#page-editor-v1-5003)
  - [Profile Manager (:5004)](#profile-manager-5004)
  - [Page Editor V2 Workspace (:5005 / :5010)](#page-editor-v2-workspace-5005--5010)
  - [Shared Web Infrastructure (BEJSON_CMS_Shared.py)](#shared-web-infrastructure-bejson_cms_sharedpy)
- [Data Storage Engine & BEJSON Schemas](#data-storage-engine--bejson-schemas)
  - [The Positional Matrix Paradigm](#the-positional-matrix-paradigm)
  - [BEJSON 104 vs 104a vs 104db Formats](#bejson-104-vs-104a-vs-104db-formats)
  - [MFDB Manifest Structure (104a.mfdb.bejson)](#mfdb-manifest-structure-104amfdbbejson)
  - [Full Relational Entity Schema Roster](#full-relational-entity-schema-roster)
  - [Page Storage Document Hierarchy (pages_db/)](#page-storage-document-hierarchy-pages_db)
- [BKS-1 Job Engine & Structured Writing Architecture](#bks-1-job-engine--structured-writing-architecture)
- [REST API & HTTP Route Reference](#rest-api--http-route-reference)
- [Command-Line Interface Reference (cms-manage.py)](#command-line-interface-reference-cms-managepy)
- [TUI Supervisor Reference (advanced_launcher.py)](#tui-supervisor-reference-advanced_launcherpy)
- [Directory Architecture & Repository Map](#directory-architecture--repository-map)
- [Security, Concurrency & Data Integrity Architecture](#security-concurrency--data-integrity-architecture)
- [Testing, Auditing & Verification Suite](#testing-auditing--verification-suite)
- [Troubleshooting & Diagnostic Handbook](#troubleshooting--diagnostic-handbook)
- [License & Project Metadata](#license--project-metadata)

---

## Executive Overview & Core Philosophy

Traditional content management architectures require heavy relational or document database daemons, database drivers, schema migration tooling, and complex connection pooling layers. BEJSON CMS eliminates these infrastructure bottlenecks by treating structured data as flat, dense JSON matrices with decoupled schema definitions.

Key architectural tenets include:
1. **Zero External Database Services**: Data is organized directly in deterministic, human-readable file stores. There are no background database processes to provision, tune, crash, or repair.
2. **Positional Matrix Efficiency**: Column field definitions are declared once in a file header (`Fields`), while all subsequent entity records are stored as lightweight arrays of scalar primitives (`Values`). This achieves a 40% to 65% reduction in raw JSON disk overhead compared to repeated key-value object collections.
3. **O(1) Field Map Caching**: Application code never parses raw positional indices blindly. Reading and writing modules compile an in-memory mapping (`{field_name: column_index}`) at initialization or boundary ingress, guaranteeing random-access lookups with instant algorithmic resolution.
4. **Decoupled Headless Microservices**: The management interface, static publisher, authoring workspace, and profile managers exist as decoupled Flask microservices. Each service can be run independently in resource-constrained environments or orchestrated under a unified terminal supervisor.
5. **Polymorphic Static Generation**: Unlike server-rendered monolithic systems where every page request incurs database lookup penalties, BEJSON CMS compiles relational content into zero-dependency, production-ready static HTML, CSS, and media bundles ready for edge delivery via Cloudflare Pages, GitHub Pages, or private NGINX servers.


![Figure: 01 Admin Dashboard](images/01_admin_dashboard.png)
*_Figure 1: Admin Dashboard Telemetry and System Overview_*


---

## Prerequisites & Environment Setup

BEJSON CMS is designed to run seamlessly across Android Termux (ARM64), Pydroid 3, standard Linux distributions (Debian, Ubuntu, Arch, Fedora, Alpine), and macOS with zero container virtualization overhead.

### System Requirements
- **Python**: Version 3.10, 3.11, or 3.12 (standard CPython).
- **Core Dependencies**: `flask`, `Pillow` (PIL fork).
- **Optional Extensions**:
  - `requests`: Required for remote network lookups and Cloudflare Pages webhook deployments.
  - `playwright`: Recommended for headless browser visual regression testing and responsive layout audits.
  - `pytest`: Required for executing the test and path integrity suite.

### Quick Dependency Installation
```bash
# Clone the repository
git clone https://github.com/boehnenelton/BEJSON_CMS.git
cd BEJSON_CMS

# Install standard dependencies
pip install flask Pillow requests pytest

# Optional: Install Playwright if running browser automated audits
pip install playwright
playwright install chromium
```

### Environment Variables & Runtime Configuration

BEJSON CMS reads runtime defaults from `config.json` (`104a` format) located in the repository root. Any setting in `config.json` can be overridden by exporting environment variables before process execution.

```bash
# Security & Access Control
export CMS_USER="admin"                                 # HTTP Basic Auth username
export CMS_PASSWORD="your-strong-production-password"   # HTTP Basic Auth password
export CMS_SECRET_KEY="generate-secure-random-token"    # Flask session signing secret

# Microservice Port Allocations
export CMS_ADMIN_PORT="5001"                            # Admin Suite & Blueprints
export CMS_PUBLISHER_PORT="5002"                        # Static Publisher & Preview Server
export CMS_PAGEEDITOR_PORT="5003"                       # Page Editor V1 (Classic Code)
export CMS_PROFILES_PORT="5004"                         # Author & Persona Profile Hub
export CMS_PAGEEDITORV2_PORT="5005"                     # Page Editor V2 (API Workspace)

# Filesystem & Data Store Overrides (For custom mount targets)
export CMS_DATA_ROOT="./storage/mfdb"                   # Master MFDB database root
export CMS_BUILDS_ROOT="./storage/builds"               # Static publishing output
export CMS_ASSETS_ROOT="./storage/mfdb/assets"          # Local media asset repository
```

| Variable | Default Value | Target Config Key | Architectural Role |
| :--- | :--- | :--- | :--- |
| `CMS_USER` | `admin` | `admin_user` | HTTP Basic Auth identity across all 5 web apps. |
| `CMS_PASSWORD` | `changeme` | `admin_password` | Master password protection on all service endpoints. |
| `CMS_SECRET_KEY` | Dynamic Hex | `secret_key` | Cryptographic secret for signing client session cookies. |
| `CMS_ADMIN_PORT` | `5001` | `admin_port` | Primary administrative hub (Content, Media, System, Interface). |
| `CMS_PUBLISHER_PORT` | `5002` | `publisher_port` | Static compiler, build log streamer, and preview host. |
| `CMS_PAGEEDITOR_PORT` | `5003` | `pageeditor_port` | Monolithic HTML editor with live iframe preview. |
| `CMS_PROFILES_PORT` | `5004` | `profiles_port` | Profile repository for author bios and system personas. |
| `CMS_PAGEEDITORV2_PORT`| `5005` | `pageeditorv2_port` | Modern reactive editing workspace with BKS-1 job studio. |
| `CMS_DATA_ROOT` | `storage/mfdb` | `mfdb_path` | Working database manifest directory. |


![Figure: 02 Pages Manager](images/02_pages_manager.png)
*_Figure 2: Pages Manager with Search Filters and Category Tabs_*


---

## Service Launchers & Operational Modes

BEJSON CMS provides three distinct process supervisors engineered for different operational profiles, ranging from dense multi-service developer environments to low-memory mobile hardware.

### 1. Advanced TUI Multi-Service Supervisor (`advanced_launcher.py`)

The primary operational launcher is `advanced_launcher.py`. Engineered with a strict 57-column viewport boundary, it functions reliably even on narrow mobile terminal sessions while monitoring all 5 services concurrently.

```bash
python3 advanced_launcher.py
```

#### Key Capabilities & Features of the TUI Launcher:
- **5-Row Positional Service Table**: Live display of service ID, runtime status (`RUN` / `OFF`), process ID (PID), port binding, active uptime timer, and friendly service identifier.
- **Persistent State Tracking**: Real-time process states, process IDs, and port assignments are recorded atomically into `storage/tmp/launcher_registry.104a.bejson` using field-map cached writes.
- **Direct Compound Control Grammar**:
  - `1`–`5`: Toggle service on or off (`1` Admin, `2` Publisher, `3` Editor V1, `4` Profiles, `5` Editor V2).
  - `r1`–`r5` (or `R`): Perform a clean service restart.
  - `k1`–`k5` (or `K`): Send an immediate `SIGKILL` to clear hung sockets.
  - `l1`–`l5` (or `L`): View the trailing 30 lines of service log streams (`storage/logs/launcher_<service>.log`).
  - `o1`–`o5` (or `O`): Trigger external browser dispatch directly to the service URL.
  - `S`: Start all configured services sequentially.
  - `Z`: Terminate all active CMS services cleanly.
  - `P`: Execute live TCP socket health probes across all 5 target ports.
  - `C`: Launch the interactive port configuration editor.
  - `E`: Inspect environment variable overrides.
  - `Q`: Detach from the TUI interface while allowing background background services to continue running.
  - `X`: Cleanly shut down all child services and exit.

### 2. Isolated Single-Service Shell Launcher (`cms_launcher.sh`)

For embedded environments, continuous integration runners, or minimal mobile hardware where only one service should consume RAM at any time, `cms_launcher.sh` terminates any existing instances before starting the chosen service:

```bash
# Launch Admin Suite (Port 5001)
./cms_launcher.sh admin

# Launch Static Site Publisher (Port 5002)
./cms_launcher.sh publisher

# Launch Page Editor V1 (Port 5003)
./cms_launcher.sh editor

# Launch Profile Manager (Port 5004)
./cms_launcher.sh profiles

# Launch Page Editor V2 Workspace (Port 5005)
./cms_launcher.sh editorv2
```

### 3. One-Tap Mobile Entry Point (`pydroid_start.py`)

For touch-screen development in Android Python environments like Pydroid 3:
```bash
python3 pydroid_start.py
```
This automatically verifies dependencies, initializes the local filesystem structure, mounts the default MFDB manifest, and boots the main Admin Suite on `http://127.0.0.1:5001`.


![Figure: 03 Media Library](images/03_media_library.png)
*_Figure 3: Hash-Deduplicated Media Library and External Asset Viewer_*


---

## Visual Interface Tour & Audit Telemetry

The BEJSON CMS interface enforces a unified tri-color palette (`#000000` deep canvas, `#FFFFFF` crisp typography, `#DE2626` high-contrast interactive accent) providing clear visual hierarchy across all viewports.

### 1. Admin Suite Dashboard (`http://127.0.0.1:5001/`)
The executive nerve center of the CMS. It displays real-time entity count telemetry across Pages, Standalone Applications, Categories, and Media Assets. Quick-action buttons provide instant access to the Page Creator, Media Upload modal, Static Site Publisher, and System Diagnostics.

### 2. Content & Pages Manager (`http://127.0.0.1:5001/pages`)
A unified interface for managing written content. Features include:
- Categorized tab filtering for quick browsing across topics.
- Live search filtering by title, slug, or author.
- One-click page duplication for rapid article templating.
- Direct links to both Page Editor V1 and PageEditor V2 workspaces.
- Inline status badges indicating publication state and featured media associations.

### 3. Media Library & Embed Engine (`http://127.0.0.1:5001/assets`)
A comprehensive digital asset management system:
- **Local Media Tab**: Displays uploaded graphics, audio, and documents with file size, SHA-256 integrity hash, dimensions, and MIME type.
- **YouTube Embed Tab**: Embeds external videos, parses YouTube video IDs, and displays video card previews.
- **External Documents Tab**: Registers externally hosted files (such as whitepapers and PDFs) with direct preview links.
- **Asset Replacement**: Allows in-place replacement of existing files without breaking relational references across published pages.

### 4. Page Editor V2 Workspace (`http://127.0.0.1:5005/`)
A responsive, dual-mode content engineering studio:
- **Metadata Pane**: Configure page title, URL slug, category, author attribution, template layout, featured image, and featured video link.
- **Content Tabs**:
  - *HTML Editor*: Monolithic raw HTML editing with responsive side-by-side or stacked preview.
  - *Markdown Source*: Full CommonMark editor with real-time conversion preview and format validation.
  - *AI Architect / BKS-1 Studio*: 4-part structured planning, part-by-part content generation, and one-click post merging.
- **Asset Integration Drawers**: Quick-insert modals for local image assets, YouTube video players, and inline PDF viewports.

### 5. Profile Manager (`http://127.0.0.1:5004/`)
Manages both public author profiles and internal system personas. Configure author display names, biographies, avatars, contact emails, and social media handles.

### 6. Static Site Publisher (`http://127.0.0.1:5002/`)
The build operations center. Monitors database mount status, tracks output file counts, streams build logs during static site compilation, provides a local test server controller, and deploys directly to edge networks.


![Figure: 04 Page Editor V2](images/04_page_editor_v2.png)
*_Figure 4: Page Editor V2 Workspace with Responsive Content Controls_*


---

## Complete Feature Catalog & Capabilities Matrix

BEJSON CMS provides a comprehensive suite of content management, static compilation, and automation features:

### 1. Data Persistence & Architecture
- **Zero-SQL Flat Matrix Engine**: All data resides in human-readable, version-controlled BEJSON files.
- **Multi-File Database Federation (MFDB)**: Central manifest (`104a.mfdb.bejson`) tracks 12 relational entity files with verified Parent-Hierarchy header links.
- **O(1) Field Map Caching**: Compiles in-memory index dictionaries to eliminate hardcoded column indices and prevent field-drift bugs.
- **Atomic File Operations**: Employs POSIX-compliant atomic temporary file creation, byte flushing, `fsync()`, and file replacement to guarantee zero data corruption during power interruptions or process termination.
- **Manifest Count Synchronization**: Automatically calculates and synchronizes record counts between physical entity files and the master manifest.

### 2. Content Creation & Authoring
- **Dual Cross-Compatible Editors**: Choose between classic server-rendered Page Editor V1 or the modern API-driven Page Editor V2.
- **Hybrid Markdown & HTML Storage**: Store raw Markdown source code alongside rendered HTML bodies in individual `pages_db/<uuid>.json` containers.
- **BKS-1 4-Part Job System**: Built-in 4-part structured blog post generator supporting automated planning, outline drafting, part-by-part expansion, and seamless target post replacement.
- **CommonMark Markdown Import**: CLI and web-based import pipeline converting external `.md` files or directory trees into formatted CMS articles with callout blocks, tables, code highlighting, and metadata extraction.
- **Polymorphic Page Types**: Supports standard articles, video landing pages with responsive 16:9 players, document downloads with PDF viewports, and custom web applications.

### 3. Media Asset Management
- **Streaming Uploads**: Direct-to-disk 64KB chunked stream processing capable of handling large media files with minimal RAM consumption.
- **SHA-256 Deduplication**: Generates cryptographic digests on ingest; duplicate uploads automatically reuse existing storage assets.
- **Asynchronous Thumbnail Worker**: Dedicated background serial queue creates downscaled image thumbnails using Pillow with automatic garbage collection between tasks.
- **WebP Optimization**: Built-in CLI command converts PNG assets to high-efficiency WebP format while updating database references in place.
- **External Media Registration**: Catalog external YouTube videos, Vimeo streams, and remote PDFs without consuming local disk space.

### 4. Standalone Application Hosting
- **Containerized Zip Extraction**: Upload standalone single-page applications, interactive calculators, or HTML5 tools as `.zip` packages.
- **Zip-Bomb & Traversal Guards**: Validates uncompressed file sizes (300MB maximum boundary) and blocks path traversal (`../`) during extraction.
- **Isolated URL Sandboxing**: Serves sandboxed applications at dedicated routes (`/apps/play/<app_uuid>/`) with automatic asset resolution.

### 5. Static Publishing & Edge Deployment
- **Zero-Dependency Static HTML**: Compiles all dynamic entities into pre-rendered static files in `storage/builds/`.
- **Tri-Color Design Themes**: Bundled dark (`dark.css`) and light (`light.css`) theme stylesheets adhering to strict typographic scales.
- **Automated Sitemaps & Feeds**: Generates `sitemap.xml`, `robots.txt`, and categorized archive feeds automatically on every build.
- **Built-in Local Preview Server**: Integrated HTTP server controller on port 8080 allows local verification of static builds before deployment.
- **Cloudflare Pages Hook**: One-click webhook trigger deploys compiled static files directly to global edge networks.

### 6. Security & Infrastructure
- **Comprehensive Path Traversal Protection**: Uses `bejson_safe_join()` to resolve absolute canonical paths and verify directory boundaries across all file-serving endpoints.
- **Centralized Basic Authentication**: Single shared `@app.before_request` hook secures all five microservices against unauthorized access.
- **57-Column TUI Supervisor**: Full-featured process monitor and terminal manager for resource-constrained development environments.


![Figure: 05 Profile Manager](images/05_profile_manager.png)
*_Figure 5: Profile Manager for Author Attribution and Personas_*


---

## User Workflows & Operational Guides

### 1. Article Authoring & Editing in PageEditor V2

Page Editor V2 provides an intuitive interface for drafting and publishing articles:

1. **Access Workspace**: Navigate to `http://127.0.0.1:5005/` in your browser.
2. **Select or Create**: Choose an existing article from the left drawer or click **+ New Page**.
3. **Configure Metadata**:
   - Set the **Page Title** and verify the automatically generated **URL Slug**.
   - Assign the appropriate **Category** from the dropdown menu.
   - Select the **Author Attribution** profile.
   - Choose a layout template (`default`, `full-width`, `minimal`).
4. **Author Content**:
   - Write directly in the **HTML Editor** or switch to the **Markdown Source** tab.
   - Click **Media Picker** to insert image references from the local asset library.
   - Click **Insert Video** or **Insert PDF** to embed media players or document viewports.
5. **Save & Preview**:
   - Click **Save Changes** (or press `Ctrl+S`). The editor validates JSON payloads and atomically updates `pages_db/<uuid>.json` and `pagerecord.bejson`.
   - Review changes in real time in the live preview pane.

---

### 2. Standardized 4-Part Blog Job System (BKS-1)

BEJSON CMS includes a standardized 4-part job framework for long-form technical articles, deep dives, and multi-part guides.

```
┌─────────────────────────────────────────────────────────────────┐
│                    BKS-1 Job Workflow                           │
├─────────────────┬─────────────────┬─────────────┬───────────────┤
│ 1. Plan & Job   │ 2. Execute Part │ 3. Merge    │ 4. Approve    │
│    Generation   │    by Part      │    4 Parts  │    & Overwrite│
│ (4 BookTypes)   │ (AI / Template) │ (MD + HTML) │ (Live Post)   │
└─────────────────┴─────────────────┴─────────────┴───────────────┘
```

#### Executing a Job via Web Studio (`:5001/jobs` or `:5005 #t-tasking`):
1. **Choose Template / BookType**:
   - `blog_post_4part`: Standard 4-part publication (Introduction, Core Architecture, Implementation, Future Horizons).
   - `technical_deep_dive_4part`: Rigorous engineering breakdown with code blocks and specifications.
   - `tutorial_guide_4part`: Step-by-step hands-on guide with prerequisites and verification steps.
2. **Define Topic & Target Post**:
   - Enter your article thesis or research subject.
   - Select an existing CMS article to overwrite on approval, or leave blank to stage a new draft.
3. **Generate Plan**:
   - Click **Generate 4-Part Plan**. The engine builds a 4-task execution template registered in `storage/mfdb/bks_jobs/templates/`.
4. **Execute Tasks**:
   - Click **Run Part** on individual cards to generate sections sequentially, or click **Execute All 4 Parts** to process the complete pipeline.
5. **Merge & Review**:
   - Click **Merge 4 Parts**. The system concatenates the Markdown source, converts it to structured BEJSON CMS HTML, and displays a responsive preview.
6. **Approve & Overwrite**:
   - Click **Approve & Overwrite Target Post**. The merged content is written directly to the target post in `pages_db/<uuid>.json` and the static site is automatically rebuilt.

#### Executing a Job via CLI:
```bash
# 1. List available templates
python3 src/cms-manage.py job templates

# 2. Create a 4-part job plan
python3 src/cms-manage.py job create   --topic "Zero-SQL Architecture in Distributed Environments"   --title "Zero-SQL Distributed Systems"   --template "technical_deep_dive_4part"   --target-uuid "e2dfa590-833d-410f-b3b8-70d85913ea29"

# 3. Execute all 4 parts
python3 src/cms-manage.py job run --all zero-sql-distributed-systems

# 4. Preview merged content
python3 src/cms-manage.py job merge zero-sql-distributed-systems

# 5. Approve and overwrite target post with immediate republish
python3 src/cms-manage.py job approve   --publish   zero-sql-distributed-systems
```

---

### 3. Markdown Import & Batch Conversion Pipeline

The `lib_bejson_CMS_md2html.py` pipeline converts standard CommonMark files into native CMS articles:

#### CLI Markdown Import:
```bash
# Import a single Markdown file
python3 src/cms-manage.py page md-import   --category "Architecture"   --author "Elton Boehnen"   --type "article"   --featured-img "architecture_hero.webp"   --publish   ./docs/distributed_systems.md

# Batch import a directory of Markdown files recursively
python3 src/cms-manage.py page md-import   --category "Guides"   --recursive   --publish   ./external_markdown_drops/
```

#### Markdown Formatting Enhancements Supported:
- **Callout Alert Blocks**:
  - `> [!NOTE]` -> Styled note box (`.callout-note`).
  - `> [!TIP]` -> Performance optimization notice (`.callout-tip`).
  - `> [!IMPORTANT]` -> Critical requirement warning (`.callout-important`).
  - `> [!WARNING]` -> Breaking change advisory (`.callout-warning`).
  - `> [!CAUTION]` -> High-risk data loss warning (`.callout-caution`).
- **Syntax-Highlighted Code Blocks**: Fenced blocks (` ```python `) are wrapped in styled container elements with language badges.
- **Task Lists**: Checkbox items (`- [x]`) are converted to styled interactive task lists.
- **Responsive Tables**: Rendered with alternate-row shading and horizontal overflow containment.

---

### 4. Media Asset Pipeline & Thumbnails

1. **Upload Asset**: Navigate to `:5001/assets` or use the CLI:
   ```bash
   python3 src/cms-manage.py asset add ./brand_graphics/hero_banner.png
   ```
2. **Processing Pipeline**:
   - The file is streamed to `storage/mfdb/assets/<filename>` in 64KB chunks.
   - The SHA-256 hash is computed. If an identical file exists, the existing record is reused.
   - A background worker creates a downscaled thumbnail in `storage/mfdb/assets/_thumbs/<filename>`.
   - The record is appended to `storage/mfdb/site_master/data/mediaasset.bejson`.
3. **WebP Optimization**:
   ```bash
   # Convert all PNG assets to WebP and update database references in place
   python3 src/cms-manage.py asset optimize
   ```

---

### 5. Standalone Web Application Hosting

Host interactive HTML/CSS/JavaScript web applications directly within BEJSON CMS:

1. **Package Application**: Compress your web application into a `.zip` archive containing `index.html` at its root.
2. **Upload Application**: Navigate to `:5001/apps` and click **+ New App**, or use the CLI:
   ```bash
   python3 src/cms-manage.py app add      --name "Telemetry Visualizer"      --slug "telemetry-viz"      --desc "Real-time positional matrix monitoring widget."      --zip ./widgets/telemetry_viz.zip
   ```
3. **Validation & Extraction**:
   - The server inspects the uncompressed payload size against the 300MB zip-bomb limit.
   - Files are extracted to `storage/mfdb/standalone_apps/<app_uuid>/`.
   - Path-traversal patterns (`../`) are detected and blocked.
4. **Access Live App**: The application is served at `http://127.0.0.1:5001/apps/view/<app_uuid>/index.html` and compiled into static builds at `/apps/<app_slug>/`.

---

### 6. Static Site Compilation & Cloudflare Publishing

1. **Trigger Static Build**:
   ```bash
   # Trigger build via HTTP POST from CLI
   curl -u admin:changeme -X POST http://127.0.0.1:5002/publish/build
   ```
2. **Verify Output**: The compiled static website is assembled in `storage/builds/`:
   ```
   storage/builds/
   ├── index.html                   # Home page with recent article feeds
   ├── style.css                    # Active theme stylesheet
   ├── sitemap.xml                  # Search engine XML sitemap
   ├── robots.txt                   # Web crawler configuration
   ├── assets/                      # Referenced media files and thumbnails
   ├── apps/                        # Standalone web applications
   ├── categories/                  # Category archive feeds
   └── <page_slug>.html             # Rendered static article pages
   ```
3. **Preview Locally**:
   - Click **Start Local Preview Server** in the Publisher interface (`:5002`).
   - Open `http://127.0.0.1:8080/` in your browser.
4. **Deploy to Cloudflare Pages**:
   ```bash
   npx wrangler pages deploy storage/builds --project-name my-bejson-site
   ```


![Figure: 06 Static Publisher](images/06_static_publisher.png)
*_Figure 6: Static Site Publisher with Build Telemetry and Preview Controls_*


---

## System Architecture & Microservice Topology

BEJSON CMS is architected as five decoupled Flask applications backed by shared authentication and middleware layers:

```
                            ┌─────────────────────────────────┐
                            │       Admin Suite (:5001)       │
                            │  System, Content, Media, Inter  │
                            └────────────────┬────────────────┘
                                             │
      ┌────────────────────────┬─────────────┴────────────┬────────────────────────┐
      │                        │                          │                        │
┌─────▼──────────────────┐ ┌───▼──────────────────┐ ┌─────▼──────────────────┐ ┌───▼──────────────────┐
│   Editor V1 (:5003)    │ │   Publisher (:5002)  │ │   Profiles (:5004)     │ │   Editor V2 (:5005)    │
│  Classic HTML Editor   │ │  Static Site Builder │ │  Author & Persona Hub  │ │  Modern API Studio     │
└─────┬──────────────────┘ └───┬──────────────────┘ └─────┬──────────────────┘ └─────┬──────────────────┘
      │                        │                          │                        │
      └────────────────────────┼──────────────────────────┴────────────────────────┘
                               │
                   ┌───────────▼──────────────────────────┐
                   │        BEJSON_CMS_Shared.py          │
                   │   Auth Guards, Asset I/O, Safe Join  │
                   └───────────┬──────────────────────────┘
                               │
                   ┌───────────▼──────────────────────────┐
                   │        CMSCore & MFDBCore            │
                   │  104a Manifest + 12 Positional Files │
                   └──────────────────────────────────────┘
```

### Admin Suite (:5001) & Architectural Blueprints
The administrative suite is structured using modular Flask Blueprints:
- **`BEJSON_CMS_System.py` (`system_cube`)**: Handles system telemetry, database export, asset bundle downloading, and factory reset routines.
- **`BEJSON_CMS_Content.py` (`content_cube`)**: Manages page CRUD, category definitions, author profiles, external links, standalone app hosting, and the BKS-1 Job Studio.
- **`BEJSON_CMS_Media.py` (`media_cube`)**: Controls media asset uploads, thumbnail generation queues, asset deletion, renaming, and external media cataloging.
- **`BEJSON_CMS_Interface.py` (`interface_cube`)**: Manages navigation links, social profile links, advertising banners, and theme selection.

### Static Site Publisher (:5002)
- Implemented in `BEJSON_CMS_Publisher.py`.
- Harvesters read all registered entities from `104a.mfdb.bejson`.
- Dispatches rendering tasks to polymorphic renderers (`StandardPageRenderer`, `VideoPageRenderer`, `DocumentPageRenderer`).
- Bundles static assets, compiles `sitemap.xml`, and manages the local port 8080 preview server.

### Page Editor V1 (:5003)
- Implemented in `BEJSON_CMS_PageEditor.py`.
- Traditional server-rendered interface featuring code-mirror style inputs, instant live iframe preview, and media insertion modals.

### Profile Manager (:5004)
- Implemented in `BEJSON_CMS_ProfileManager.py`.
- Dedicated interface for managing author identities and system personas used during content drafting.

### Page Editor V2 Workspace (:5005 / :5010)
- Implemented in `BEJSON_CMS_PageEditorV2.py`.
- Modern API-driven single-page architecture featuring category-filtered page loading, draft management, CommonMark Markdown editor, and integrated BKS-1 Job Studio.

### Shared Web Infrastructure (`BEJSON_CMS_Shared.py`)
- **`register_auth_guard(app)`**: Centralized `@app.before_request` hook enforcing HTTP Basic Authentication across all endpoints.
- **`serve_shared_asset(filename)` & `serve_shared_thumb(filename)`**: Unified asset streaming handlers protected by `bejson_safe_join()`.
- **`R(content, breadcrumbs, active_section)`**: Base HTML shell template renderer with responsive navigation, breadcrumb navigation, and alert dialogs.


![Figure: 07 Playwright Admin Dashboard Capture](images/audit_captures/01_playwright_admin_dashboard.png)
*_Figure 7: Automated Playwright Audit Capture of Admin Dashboard_*


---

## Data Storage Engine & BEJSON Schemas

### The Positional Matrix Paradigm

BEJSON replaces repetitive object keys with a clean tabular matrix format. A standard BEJSON file consists of:
1. **Header Metadata**: Format type, format version, creator attribution, and manifest hierarchy pointer.
2. **Field Definitions (`Fields`)**: An ordered list defining column names and data types.
3. **Values Matrix (`Values`)**: An array of rows, where each row is an array of scalar values corresponding positionally to the fields.

```json
{
  "Format": "BEJSON",
  "Format_Version": "104",
  "Format_Creator": "Elton Boehnen",
  "Parent_Hierarchy": "../104a.mfdb.bejson",
  "Records_Type": ["Category"],
  "Fields": [
    {"name": "cat_name", "type": "string"},
    {"name": "cat_slug", "type": "string"}
  ],
  "Values": [
    ["Architecture", "architecture"],
    ["Tutorials", "tutorials"],
    ["Specifications", "specifications"]
  ]
}
```

### BEJSON 104 vs 104a vs 104db Formats

| Format Variant | Purpose | Key Structural Characteristic | Usage in BEJSON CMS |
| :--- | :--- | :--- | :--- |
| **BEJSON 104** | Relational Entity Tables | Flat positional table linked to parent manifest. | All entity files in `storage/mfdb/site_master/data/*.bejson`. |
| **BEJSON 104a** | Configuration & Manifests | Strict scalar primitives only; zero nested structures. | `config.json`, `104a.mfdb.bejson`, `launcher_registry.104a.bejson`. |
| **BEJSON 104db** | Multi-Record Documents | First column defines row record type (`Record_Type_Parent`). | Individual page content files (`storage/mfdb/pages_db/<uuid>.json`). |

### MFDB Manifest Structure (`104a.mfdb.bejson`)

The central manifest at `storage/mfdb/site_master/104a.mfdb.bejson` registers all database tables, tracking their relative paths, record counts, and schema types:

```json
{
  "Format": "BEJSON",
  "Format_Version": "104a",
  "Format_Creator": "Elton Boehnen",
  "Database_Name": "BEJSON_CMS_SiteMaster",
  "MFDB_Version": "1.31",
  "Network_Role": "Master",
  "Records_Type": ["MFDBManifestRecord"],
  "Fields": [
    {"name": "table_identifier", "type": "string"},
    {"name": "entity_type", "type": "string"},
    {"name": "relative_path", "type": "string"},
    {"name": "records_count", "type": "integer"},
    {"name": "format_variant", "type": "string"}
  ],
  "Values": [
    ["tbl_pages", "PageRecord", "data/pagerecord.bejson", 6, "104"],
    ["tbl_categories", "Category", "data/category.bejson", 3, "104"],
    ["tbl_authors", "AuthorProfile", "data/authorprofile.bejson", 2, "104"],
    ["tbl_assets", "MediaAsset", "data/mediaasset.bejson", 24, "104"],
    ["tbl_extmedia", "ExternalMedia", "data/externalmedia.bejson", 2, "104"],
    ["tbl_ads", "AdUnit", "data/adunit.bejson", 1, "104"],
    ["tbl_apps", "StandaloneApp", "data/standaloneapp.bejson", 1, "104"],
    ["tbl_nav", "NavLink", "data/navlink.bejson", 4, "104"],
    ["tbl_config", "SiteConfig", "data/siteconfig.bejson", 6, "104"],
    ["tbl_social", "SocialLink", "data/sociallink.bejson", 3, "104"],
    ["tbl_video_meta", "PageVideoMetadata", "data/pagevideometadata.bejson", 1, "104"],
    ["tbl_doc_meta", "PageDocumentMetadata", "data/pagedocumentmetadata.bejson", 1, "104"]
  ]
}
```

### Full Relational Entity Schema Roster

The 12 relational entity tables enforce consistent column naming conventions:

1. **PageRecord (`data/pagerecord.bejson`)**:
   - `page_uuid` (string, PK): Unique UUIDv4 identifier.
   - `page_title` (string): Human-readable article title.
   - `page_slug` (string): URL-safe route slug.
   - `page_cat_name` (string): Foreign-key reference to `cat_name`.
   - `page_type` (string): Content type (`blog`, `article`, `video`, `document`, `page`).
   - `page_created_at` (string): ISO 8601 creation timestamp.
   - `page_external_url` (string): Optional external redirect URL.
   - `page_author_name` (string): Author attribution string.
   - `page_featured_img` (string): Filename of featured image in assets.
   - `page_template_key` (string): Layout template identifier (`default`, `full-width`).
   - `page_featured_video_url` (string): Optional YouTube video embed URL.

2. **Category (`data/category.bejson`)**:
   - `cat_name` (string, PK): Display name.
   - `cat_slug` (string): URL-safe category slug.

3. **AuthorProfile (`data/authorprofile.bejson`)**:
   - `author_id` (string, PK): Unique identifier.
   - `author_display_name` (string): Public display name.
   - `author_bio` (string): Author biography text.
   - `author_avatar_url` (string): Relative avatar image path.
   - `author_email` (string): Contact email address.
   - `author_website_url` (string): External website URL.
   - `author_social_links` (string): Serialized JSON array of social handles.

4. **MediaAsset (`data/mediaasset.bejson`)**:
   - `asset_filename` (string, PK): Unique physical filename on disk.
   - `asset_original_name` (string): Original client upload filename.
   - `asset_file_hash` (string): SHA-256 cryptographic digest.
   - `asset_file_size` (integer): Total file size in bytes.
   - `asset_mime_type` (string): Standard MIME type.
   - `asset_uploaded_at` (string): ISO 8601 upload timestamp.

5. **ExternalMedia (`data/externalmedia.bejson`)**:
   - `extmedia_uuid` (string, PK): Unique UUIDv4 identifier.
   - `extmedia_name` (string): Asset label.
   - `extmedia_type` (string): Type (`video`, `pdf`, `doc`, `audio`).
   - `extmedia_url` (string): Fully qualified external URL.
   - `extmedia_created_at` (string): ISO 8601 timestamp.

6. **AdUnit (`data/adunit.bejson`)**:
   - `ad_uuid` (string, PK): Unique UUIDv4 identifier.
   - `ad_name` (string): Internal campaign identifier.
   - `ad_zone` (string): Placement zone (`sidebar`, `header`, `footer`, `in-feed`).
   - `ad_image_filename` (string): Banner image filename.
   - `ad_target_url` (string): Destination URL on click.
   - `ad_alt_text` (string): Accessibility description.
   - `ad_enabled` (boolean): Active state toggle.

7. **StandaloneApp (`data/standaloneapp.bejson`)**:
   - `app_uuid` (string, PK): Unique UUIDv4 identifier.
   - `app_name` (string): Application display title.
   - `app_slug` (string): URL route slug.
   - `app_description` (string): Functional overview.
   - `app_entry_file` (string): Entry point path (e.g., `index.html`).
   - `app_featured_img` (string): Application icon or thumbnail.

8. **NavLink (`data/navlink.bejson`)**:
   - `nav_id` (string, PK): Unique identifier.
   - `nav_display_label` (string): Navigation text.
   - `nav_target_url` (string): Destination URL path.
   - `nav_sort_order` (integer): Position weight in navigation menus.

9. **SiteConfig (`data/siteconfig.bejson`)**:
   - `sys_key` (string, PK): Setting key name.
   - `sys_value` (string): Setting value.

10. **SocialLink (`data/sociallink.bejson`)**:
    - `social_platform_name` (string, PK): Platform identifier.
    - `social_target_url` (string): Profile URL.

11. **PageVideoMetadata (`data/pagevideometadata.bejson`)**:
    - `video_page_uuid` (string, PK): Associated page UUID.
    - `video_source_url` (string): Video source URL.
    - `video_duration` (string): Video duration string.
    - `video_resolution` (string): Native resolution.
    - `video_transcript` (string): Full text transcript.

12. **PageDocumentMetadata (`data/pagedocumentmetadata.bejson`)**:
    - `doc_page_uuid` (string, PK): Associated page UUID.
    - `doc_asset_filename` (string): Document filename in assets.
    - `doc_page_count` (integer): Page count.
    - `doc_file_size` (integer): File size in bytes.
    - `doc_download_rules` (string): Access restrictions.


![Figure: 08 BKS-1 Job Studio Playwright Capture](images/audit_captures/02_playwright_bks_jobs_studio.png)
*_Figure 8: Playwright Verification Capture of BKS-1 Blog Job Studio_*


---

## Page Storage Document Hierarchy (pages_db/)

While metadata for fast querying and filtering resides in `pagerecord.bejson`, full article content (HTML body, Markdown source, and embedded scripts) is persisted in individual BEJSON 104db files located at `storage/mfdb/pages_db/<page_uuid>.json`.

### Structure of a Page Storage File
```json
{
  "Format": "BEJSON",
  "Format_Version": "104db",
  "Format_Creator": "Elton Boehnen",
  "Parent_Hierarchy": "../site_master/104a.mfdb.bejson",
  "Records_Type": ["PageRecordPayload"],
  "Fields": [
    {"name": "Record_Type_Parent", "type": "string"},
    {"name": "payload_key", "type": "string"},
    {"name": "payload_content", "type": "string"}
  ],
  "Values": [
    ["PageMeta", "title", "Zero-SQL Architecture in Distributed Environments"],
    ["PageMeta", "slug", "zero-sql-distributed-environments"],
    ["PageMeta", "category", "Architecture"],
    ["PageMeta", "author", "Elton Boehnen"],
    ["PageMeta", "template", "default"],
    ["PageMeta", "featured_image", "zero_sql_hero.webp"],
    ["PageMeta", "featured_video", ""],
    ["Content", "html_body", "<h2>System Foundations</h2><p>Article body...</p>"],
    ["Content", "markdown_body", "## System Foundations\n\nArticle body..."],
    ["Content", "source_code", ""]
  ]
}
```

This decoupled design allows the CMS to read lightweight metadata lists without loading full article content into memory, keeping dashboard operations fast and responsive.


![Figure: 09 Page Editor V2 Full Playwright Capture](images/audit_captures/03_playwright_page_editor_v2.png)
*_Figure 9: Playwright Full-Page Verification Capture of Page Editor V2_*


---

## BKS-1 Job Engine & Structured Writing Architecture

The BKS-1 job engine (`src/lib/lib_bejson_CMS_bks_blog_jobs.py`) implements a structured writing workflow for complex technical content.

### BKS-1 Directory Architecture
```
storage/mfdb/bks_jobs/
├── book_types/                      # Predefined BookType schemas (104a)
├── templates/                       # Instantiated 4-part execution plans
├── jobs/                            # Execution state tracking records
├── books/                           # Individual part draft outputs
├── merged/                          # Merged Markdown and HTML outputs
├── registry.bejson                  # Central 104db job registry
└── cms_job_links.104a.bejson        # Relational mapping between jobs and CMS pages
```

### The 4-Part Structured Article Cycle
1. **Plan Formulation**: Generates a 4-task execution template specifying objectives, key technical points, and structural constraints for each part.
2. **Part-by-Part Drafting**: Executes tasks sequentially with context from previous parts passed forward to maintain cohesive narrative flow.
3. **Draft Merging**: Combines the four Markdown drafts into a unified document and converts it to semantic HTML using `lib_bejson_CMS_md2html.py`.
4. **Target Overwrite & Auto-Publish**: Updates the target page in `pages_db/<uuid>.json` and `pagerecord.bejson`, and automatically triggers a static site rebuild.


![Figure: 10 Page Editor AI Architect Tab Capture](images/audit_captures/04_playwright_editor_ai_architect_tab.png)
*_Figure 10: AI Architect and BKS-1 Tasking Tab in Page Editor V2_*


---

## REST API & HTTP Route Reference

BEJSON CMS exposes a clean REST API across its microservices:

### Content & Page Management API (Port 5001 / 5005)

| Endpoint | Method | Payload / Parameters | Response | Purpose |
| :--- | :---: | :--- | :--- | :--- |
| `/api/get/<uuid>` | `GET` | — | JSON Page Payload | Retrieve full page metadata, HTML body, and Markdown source. |
| `/api/save` | `POST` | JSON: `{uuid, title, slug, category, author, html_body, markdown_body, ...}` | `{"status": "ok"}` | Save page metadata and content atomically. |
| `/api/md2html` | `POST` | JSON: `{markdown: "## Source"}` | `{"html": "<h2>Source</h2>"}` | Convert Markdown text to semantic CMS HTML. |
| `/pages/delete/<uuid>` | `POST` | — | Redirect / Status | Delete page and remove its `pages_db` container. |
| `/pages/duplicate/<uuid>` | `POST` | — | Redirect | Clone existing page with a fresh UUID and `-copy` slug. |

### Media Management API (Port 5001)

| Endpoint | Method | Payload / Parameters | Response | Purpose |
| :--- | :---: | :--- | :--- | :--- |
| `/assets/list.json` | `GET` | — | JSON Array of Assets | List all registered media assets with hashes and sizes. |
| `/assets/upload` | `POST` | Multipart form data: `file` | `{"filename": "..."}` | Stream asset upload, compute hash, queue thumbnail. |
| `/assets/delete/<filename>`| `POST`| — | Redirect | Delete media asset and its corresponding thumbnail. |
| `/assets/replace/<filename>`| `POST`| Multipart form data: `file` | Redirect | Replace physical file while maintaining filename. |
| `/assets/rename/<filename>` | `POST`| Form data: `new_name` | Redirect | Rename asset record in database. |

### BKS-1 Job Studio API (Port 5001 / 5005)

| Endpoint | Method | Payload / Parameters | Response | Purpose |
| :--- | :---: | :--- | :--- | :--- |
| `/api/bks/bootstrap` | `GET` | — | JSON Registry State | Retrieve book types, existing jobs, and template lists. |
| `/api/bks/create_plan` | `POST` | JSON: `{topic, title, template, target_uuid}` | `{"job_slug": "..."}` | Generate 4-part job plan and register job. |
| `/api/bks/execute_part` | `POST` | JSON: `{job_slug, part_index}` | `{"status": "ok"}` | Execute a single part of the 4-part plan. |
| `/api/bks/execute_all` | `POST` | JSON: `{job_slug}` | `{"status": "ok"}` | Run all four parts sequentially. |
| `/api/bks/merge` | `POST` | JSON: `{job_slug}` | `{"markdown": "...", "html": "..."}` | Merge all four parts into unified document. |
| `/api/bks/approve` | `POST` | JSON: `{job_slug, target_uuid, publish}` | `{"status": "ok"}` | Approve merged post and overwrite target page. |

### Static Publisher API (Port 5002)

| Endpoint | Method | Payload / Parameters | Response | Purpose |
| :--- | :---: | :--- | :--- | :--- |
| `/publish/build` | `POST` | — | `{"status": "success", "files": 42}` | Trigger complete static site compilation. |
| `/publish/log` | `GET` | — | Plaintext log stream | Read real-time build log output. |
| `/publish/server/start` | `POST` | — | `{"status": "running", "port": 8080}` | Start local static preview server. |
| `/publish/server/stop` | `POST` | — | `{"status": "stopped"}` | Stop local preview server. |


![Figure: 11 Published Home Page Playwright Capture](images/audit_captures/05_playwright_published_home.png)
*_Figure 11: Playwright Audit Capture of Published Static Home Feed_*


---

## Command-Line Interface Reference (cms-manage.py)

The CLI toolkit `src/cms-manage.py` provides headless administration for automated environments:

```bash
python3 src/cms-manage.py <subcommand> [arguments]
```

### Complete Command Reference:

#### System Diagnostics & Backups
```bash
# Display manifest health, table paths, and record counts
python3 src/cms-manage.py status

# Create a full database and assets backup archive
python3 src/cms-manage.py backup --output ./storage/exports/site_backup.zip

# Restore system state from a backup archive
python3 src/cms-manage.py restore ./storage/exports/site_backup.zip

# Perform a complete factory reset to initial seed state
python3 src/cms-manage.py factory-reset
```

#### Page Management
```bash
# List all registered pages
python3 src/cms-manage.py page list

# Create a new article
python3 src/cms-manage.py page add   --title "System Architecture"   --category "Architecture"   --author "Elton Boehnen"   --body "<h2>Core Components</h2><p>Content...</p>"   --featured-video "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Update an existing page
python3 src/cms-manage.py page update <PAGE_UUID> --title "Updated Title"

# Delete a page
python3 src/cms-manage.py page delete <PAGE_UUID>

# Import Markdown file or batch-import directory
python3 src/cms-manage.py page md-import --category "Guides" --publish ./article.md
```

#### Categories, Authors & Links
```bash
# Category commands
python3 src/cms-manage.py category list
python3 src/cms-manage.py category add "Engineering"
python3 src/cms-manage.py category delete "engineering"

# Author commands
python3 src/cms-manage.py author list
python3 src/cms-manage.py author add "Jane Doe" --bio "Senior Engineer" --email "jane@example.com"
python3 src/cms-manage.py author delete <AUTHOR_ID>

# Navigation link commands
python3 src/cms-manage.py navlink list
python3 src/cms-manage.py navlink add "Documentation" "/docs/" 10
python3 src/cms-manage.py navlink delete <NAV_ID>
```

#### Media & Applications
```bash
# Add a media asset
python3 src/cms-manage.py asset add ./images/diagram.png

# Optimize PNG assets to WebP
python3 src/cms-manage.py asset optimize

# Register an external video or PDF
python3 src/cms-manage.py asset add-external "Reference Whitepaper" "pdf" "https://example.com/paper.pdf"

# Install a standalone web application
python3 src/cms-manage.py app add --name "Calculator" --slug "calculator" --zip ./calc.zip
```


![Figure: 12 Published Article Desktop Playwright Capture](images/audit_captures/06_playwright_published_article_desktop.png)
*_Figure 12: Playwright Desktop Viewport Audit Capture of Published Article_*


---

## TUI Supervisor Reference (advanced_launcher.py)

The TUI supervisor provides an operational control surface for multi-service environments:

```
┌─────────────────────────────────────────────────────────┐
│              BEJSON CMS TUI SUPERVISOR v2               │
├────┬───────┬───────┬──────┬─────────┬───────────────────┤
│ ID │ STATE │  PID  │ PORT │ UPTIME  │ SERVICE           │
├────┼───────┼───────┼──────┼─────────┼───────────────────┤
│ 1  │  RUN  │ 28140 │ 5001 │ 01h 14m │ Admin Suite       │
│ 2  │  RUN  │ 28145 │ 5002 │ 01h 14m │ Static Publisher  │
│ 3  │  OFF  │   -   │ 5003 │    -    │ Page Editor V1    │
│ 4  │  OFF  │   -   │ 5004 │    -    │ Profile Manager   │
│ 5  │  RUN  │ 28152 │ 5005 │ 01h 14m │ Page Editor V2    │
├────┴───────┴───────┴──────┴─────────┴───────────────────┤
│ COMMANDS: [1-5] Toggle | [S]tart All | [Z] Stop All     │
│ [r1-r5] Restart | [k1-k5] Kill | [l1-l5] Logs           │
│ [P]robe Ports | [C]onfig Ports | [Q]uit | [X] Exit All   │
└─────────────────────────────────────────────────────────┘
```

### Key Commands:
- **`1`–`5`**: Toggle individual services on or off.
- **`r1`–`r5`**: Restart a specific service cleanly.
- **`k1`–`k5`**: Send an immediate `SIGKILL` to clear hung sockets.
- **`l1`–`l5`**: View the last 30 lines of service logs.
- **`P`**: Probe all five ports with active TCP socket connections to verify responsiveness.
- **`C`**: Interactive port configuration editor.
- **`Q`**: Quit the supervisor interface while leaving background services running.
- **`X`**: Stop all running services and exit.


![Figure: 13 Published Article Mobile Playwright Capture](images/audit_captures/07_playwright_published_article_mobile.png)
*_Figure 13: Playwright Mobile Viewport Audit Capture (Zero Overflow Confirmed)_*


---

## Directory Architecture & Repository Map

```
BEJSON_CMS/
├── README.md                        # Master documentation and reference guide
├── CHANGELOG.md                     # Human-readable release version notes
├── LICENSE                          # PolyForm Noncommercial 1.0.0 license terms
├── SECURITY.md                      # Security model and vulnerability disclosure
├── CONTRIBUTING.md                  # Development guidelines and code standards
├── bejson_project.json              # Canonical project metadata and version tracker
├── config.json                      # Runtime configuration (BEJSON 104a)
├── advanced_launcher.py             # 57-column TUI multi-service supervisor
├── cms_launcher.sh                  # Single-service isolated shell launcher
├── pydroid_start.py                 # Mobile quick-start entry point
│
├── images/                          # Documentation screenshots and audit captures
│   ├── 01_admin_dashboard.png       # Resized 420p UI captures
│   ├── 02_pages_manager.png
│   ├── 03_media_library.png
│   ├── 04_page_editor_v2.png
│   ├── 05_profile_manager.png
│   ├── 06_static_publisher.png
│   └── audit_captures/              # High-DPI Playwright verification captures
│       ├── 01_playwright_admin_dashboard.png
│       ├── 02_playwright_bks_jobs_studio.png
│       ├── 03_playwright_page_editor_v2.png
│       ├── 04_playwright_editor_ai_architect_tab.png
│       ├── 05_playwright_published_home.png
│       ├── 06_playwright_published_article_desktop.png
│       └── 07_playwright_published_article_mobile.png
│
├── resources/                       # Static templates, styles, and seed assets
│   ├── default_brand_assets/        # Seed brand images for factory resets
│   ├── styles/                      # CSS themes (dark.css, light.css)
│   └── templates/                   # HTML skeleton templates for static export
│
├── src/                             # Core application source code
│   ├── cms-manage.py                # Headless CLI management tool
│   ├── lib/                         # Persistence, domain, and utility libraries
│   │   ├── lib_bejson_Core_bejson_core.py       # Positional matrix reader & atomic writer
│   │   ├── lib_bejson_Core_bejson_validator.py  # BEJSON 104/104a/104db structural validator
│   │   ├── lib_bejson_Core_bejson_path_guard.py # Safe path resolution & traversal guards
│   │   ├── lib_bejson_Core_mfdb_core.py         # Multi-File Database manifest orchestrator
│   │   ├── lib_bejson_Core_mfdb_validator.py    # Manifest and entity referential validator
│   │   ├── lib_bejson_CMS_cms_core.py           # High-level CMS entity operations wrapper
│   │   ├── lib_bejson_CMS_cms_mfdb.py           # CLI database abstraction layer
│   │   ├── lib_bejson_CMS_md2html.py            # CommonMark to semantic HTML converter
│   │   ├── lib_bejson_CMS_bks_blog_jobs.py      # BKS-1 4-part blog post job engine
│   │   ├── lib_bejson_CMS_cms_ports.py          # Port configuration resolver
│   │   └── lib_bejson_CMS_taxonomy.py           # Field prefix and entity taxonomies
│   │
│   └── web/                         # Flask microservice applications
│       ├── BEJSON_CMS_Admin.py                  # Main administrative suite entry point
│       ├── BEJSON_CMS_Content.py                # Content management blueprint
│       ├── BEJSON_CMS_Media.py                  # Media asset management blueprint
│       ├── BEJSON_CMS_Interface.py              # Navigation, social & ads blueprint
│       ├── BEJSON_CMS_System.py                 # System telemetry & backup blueprint
│       ├── BEJSON_CMS_Publisher.py              # Static site generator & preview host
│       ├── BEJSON_CMS_PageEditor.py             # Classic server-rendered code editor
│       ├── BEJSON_CMS_PageEditorV2.py           # API-driven editor & BKS-1 job studio
│       ├── BEJSON_CMS_ProfileManager.py         # Author profile and persona manager
│       ├── BEJSON_CMS_FileBrowser.py            # Media file browser modal provider
│       ├── BEJSON_CMS_Renderers.py              # Polymorphic static page renderers
│       └── BEJSON_CMS_Shared.py                 # Shared auth guards and asset middleware
│
├── storage/                         # Live runtime data and generated output
│   ├── builds/                      # Compiled static website output
│   ├── exports/                     # Database and asset backup archives
│   ├── logs/                        # Application and supervisor log files
│   ├── mfdb/                        # Active Multi-File Database
│   │   ├── site_master/             # Master manifest and 12 relational entity files
│   │   ├── pages_db/                # Individual 104db page content files
│   │   ├── assets/                  # Uploaded media assets and thumbnails
│   │   ├── bks_jobs/                # BKS-1 job plans, drafts, and templates
│   │   └── standalone_apps/         # Extracted containerized web applications
│   └── tmp/                         # Runtime state and temporary upload staging
│
├── tests/                           # Automated verification test suite
│   ├── test_lib_bejson_Core_bejson_path_guard.py
│   └── test_lib_bejson_Core_mfdb_validator.py
│
└── tools/                           # Maintenance and taxonomy migration scripts
```


![Figure: 14 Category Projects Viewport Capture](images/audit_captures/category_projects_desktop.png)
*_Figure 14: Published Category Feed Viewport Audit Capture_*


---

## Security, Concurrency & Data Integrity Architecture

### 1. Boundary-Checked Path Resolution (`bejson_safe_join`)
Path traversal attacks (`../../etc/passwd`) are blocked using strict boundary checks:
```python
def bejson_safe_join(base_directory: Path, untrusted_relative_path: str) -> Path:
    target_candidate = (base_directory / untrusted_relative_path).resolve()
    if not target_candidate.is_relative_to(base_directory.resolve()):
        raise PermissionError(f"Directory traversal detected: '{untrusted_relative_path}' escapes base root.")
    return target_candidate
```
This check is enforced across every file-serving route, asset upload handler, image thumbnail streamer, and ZIP extraction routine.

### 2. Atomic POSIX File Replacement
All data modifications use atomic write-and-replace patterns to prevent partial writes during unexpected process termination:
1. Data is written to a unique hidden temporary file in the target directory (`.bejson_<pid>_<random>.tmp`).
2. Data is explicitly flushed to disk via `flush()` and `os.fsync()`.
3. The temporary file replaces the target file atomically via `os.replace()`.
4. If an exception occurs, the temporary file is unlinked, leaving the original file intact.

### 3. Thread & Process Concurrency Serialization
Write operations across the Multi-File Database are synchronized using per-manifest reentrant locks (`threading.RLock`) inside `lib_bejson_Core_mfdb_core.py`. Multiple worker threads can read concurrently while write mutations are queued serially.

### 4. Zip-Bomb & Malicious Archive Defenses
Standalone web applications and ZIP backup archives are audited before decompression:
- **Uncompressed Size Limit**: Rejects archives expanding beyond 300MB.
- **Compression Ratio Check**: Detects recursive compression bombs.
- **Traversal Guard**: Inspects all archive member paths before extraction to ensure no files escape the target destination directory.

### 5. Centralized HTTP Basic Authentication
Authentication is enforced globally via `BEJSON_CMS_Shared.register_auth_guard(app)`:
- Every incoming HTTP request is checked before route handlers are invoked.
- Requests without valid HTTP Basic Authentication headers receive an immediate `401 Unauthorized` response with a `WWW-Authenticate` challenge.
- Static preview servers bound strictly to `127.0.0.1` run without external exposure.


![Figure: 15 Home Feed Desktop Capture](images/audit_captures/home_feed_desktop.png)
*_Figure 15: Clean 8-Lane Responsive Grid Layout of Published Home Feed_*


---

## Testing, Auditing & Verification Suite

BEJSON CMS includes automated test suites covering path security, schema validation, and responsive browser layout rendering:

```bash
# 1. Run the pytest test suite
pytest tests/ -v

# 2. Syntax-check all Python source files
python3 -m compileall -q src/ tools/ tests/

# 3. Audit README documentation compliance
python3 ~/.gemini/config/skills/readme-visual-enhancer/scripts/readme_auditor.py   --readme ./README.md

# 4. Run Playwright multi-viewport responsive layout audit
python3 storage/tmp/playwright_cms_verify.py
```

### Playwright Viewport Verification Targets:
- **Desktop (1280x800)**: Verifies full navigation layout, sidebar rendering, and horizontal overflow bounds (`scrollWidth == clientWidth`).
- **Tablet (768x1024)**: Validates responsive grid collapsing from multi-column to dual-column layouts.
- **Mobile (375x812)**: Confirms mobile menu drawer behavior, button wrapping, and zero horizontal overflow on small screens.


![Figure: 16 Mobile Hero Viewport Capture](images/audit_captures/post_105_mobile_hero.png)
*_Figure 16: Mobile Viewport Render of Hero Banner (Zero Horizontal Overflow)_*


---

## Troubleshooting & Diagnostic Handbook

### Common Issues & Solutions:

#### 1. Port Collision on Startup (`Address already in use`)
- **Cause**: A previous CMS service process did not release its socket cleanly.
- **Solution**:
  ```bash
  # Check active ports using the TUI launcher
  python3 advanced_launcher.py
  # Press 'P' to probe ports, or 'k1'-'k5' to force-kill hung services

  # Alternatively, clear ports via terminal command:
  fuser -k 5001/tcp 5002/tcp 5003/tcp 5004/tcp 5005/tcp
  ```

#### 2. Manifest Record Count Mismatch
- **Cause**: Manual editing of entity files on disk without updating `104a.mfdb.bejson`.
- **Solution**:
  ```bash
  python3 src/cms-manage.py status
  # The status command automatically detects and reconciles record count discrepancies
  ```

#### 3. Uploaded Image Thumbnail Missing
- **Cause**: The background thumbnail worker queue is processing a large file or Pillow encountered an unsupported color profile.
- **Solution**:
  ```bash
  # Check application logs
  cat storage/logs/launcher_admin.log | grep -i "thumb"

  # Re-run asset optimization to regenerate WebP variants
  python3 src/cms-manage.py asset optimize
  ```

#### 4. Static Site Build Fails
- **Cause**: Missing referenced asset or corrupted page JSON document.
- **Solution**:
  ```bash
  # Check build logs
  curl -u admin:changeme http://127.0.0.1:5002/publish/log

  # Verify all page storage documents validate cleanly
  python3 -c "
  from pathlib import Path
  import json
  for p in Path('storage/mfdb/pages_db').glob('*.json'):
      data = json.loads(p.read_text())
      assert data['Format'] == 'BEJSON'
  print('All page documents are valid.')
  "
  ```

---

## License & Project Metadata

**BEJSON CMS** is designed and maintained by **Elton Boehnen**.

- **Author**: Elton Boehnen
- **Email**: boehnenelton2024@gmail.com
- **Website**: [boehnenelton2024.pages.dev](https://boehnenelton2024.pages.dev)
- **Repository**: [github.com/boehnenelton/BEJSON_CMS](https://github.com/boehnenelton/BEJSON_CMS)
- **License**: PolyForm Noncommercial License 1.0.0 (See [LICENSE](LICENSE) for full terms)

---

*BEJSON CMS — High-Performance Zero-SQL Content Management for Independent Systems.*
