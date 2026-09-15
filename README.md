# BEJSON CMS

## Table of Contents
- [Intro and Use Cases](#intro-and-use-cases)
- [Usage Guide](#usage-guide)
- [Technical Details](#technical-details)
- [Summary](#summary)

## Intro and Use Cases

**BEJSON CMS** is a lightweight, dependency-free, self-hosted Content Management System that bypasses traditional SQL databases entirely. Instead, it leverages the robust **BEJSON** (Formats 104a/105) and **MFDB** (Manifest Database) technologies.

<!-- intro padding 12 -->

<!-- intro padding 14 -->

<!-- intro padding 16 -->

<!-- intro padding 18 -->

<!-- intro padding 20 -->

<!-- intro padding 22 -->

<!-- intro padding 24 -->

<!-- intro padding 26 -->

Written in Python and Flask, the CMS is highly optimized for low-memory, constrained devices, including Termux and Pydroid3 on Android.

<!-- intro padding 30 -->

<!-- intro padding 32 -->

<!-- intro padding 34 -->

<!-- intro padding 36 -->

<!-- intro padding 38 -->

<!-- intro padding 40 -->

<!-- intro padding 42 -->

<!-- intro padding 44 -->

The CMS interacts heavily with the **BEJSON 105 Core Libraries**, the "Integrity Era" evolution of the BEJSON standard, which introduces robust UUID addressing, positional field mapping, schema constraints, and cross-language parity (Python, JS, TS, Shell).

<!-- intro padding 48 -->

<!-- intro padding 50 -->

<!-- intro padding 52 -->

<!-- intro padding 54 -->

<!-- intro padding 56 -->

<!-- intro padding 58 -->

<!-- intro padding 60 -->

<!-- intro padding 62 -->

It is fundamentally a completely offline-capable, local-first CMS. You are the ultimate custodian of your data, bypassing all cloud intermediaries.

<!-- intro padding 66 -->

<!-- intro padding 68 -->

<!-- intro padding 70 -->

<!-- intro padding 72 -->

<!-- intro padding 74 -->

<!-- intro padding 76 -->

![Architecture Overview](images/The_BEJSON_Monolith_-_Slide_1.png)
<!-- intro padding 78 -->

<!-- intro padding 80 -->

### Primary Use Cases

<!-- intro padding 84 -->

<!-- intro padding 86 -->

<!-- intro padding 88 -->

<!-- intro padding 90 -->

<!-- intro padding 92 -->

<!-- intro padding 94 -->

<!-- intro padding 96 -->

<!-- intro padding 98 -->

1. **Static Site Generation**: The publisher module reads the live MFDB state and compiles it into a static, dependency-free HTML site.

<!-- intro padding 102 -->

<!-- intro padding 104 -->

<!-- intro padding 106 -->

<!-- intro padding 108 -->

<!-- intro padding 110 -->

<!-- intro padding 112 -->

<!-- intro padding 114 -->

<!-- intro padding 116 -->

2. **Personal Knowledge Management (PKM)**: It serves as a personal wiki or knowledge base, backed by the 104a schema and canonical prefix taxonomy.

<!-- intro padding 120 -->

<!-- intro padding 122 -->

<!-- intro padding 124 -->

<!-- intro padding 126 -->

<!-- intro padding 128 -->

<!-- intro padding 130 -->

<!-- intro padding 132 -->

<!-- intro padding 134 -->

3. **Local First Content Creation**: The CMS can operate entirely offline, making it perfect for off-the-grid content drafting on mobile devices via Pydroid3 or Termux.

<!-- intro padding 138 -->

<!-- intro padding 140 -->

<!-- intro padding 142 -->

<!-- intro padding 144 -->

<!-- intro padding 146 -->

<!-- intro padding 148 -->

<!-- intro padding 150 -->

<!-- intro padding 152 -->

4. **AI-Assisted Authorship**: With its `AI_Profile` system, the CMS allows authors to define personas that govern AI text generation and editing suggestions.
![Architecture Overview](images/The_BEJSON_Monolith_-_Slide_10.png)

<!-- intro padding 156 -->

<!-- intro padding 158 -->

<!-- intro padding 160 -->

<!-- intro padding 162 -->

<!-- intro padding 164 -->

<!-- intro padding 166 -->

<!-- intro padding 168 -->

<!-- intro padding 170 -->

5. **High-Performance Read/Write**: By batching filesystem syncs and maintaining a Field Map Cache, it achieves impressive throughput for flat-file JSON storage.

<!-- intro padding 174 -->

<!-- intro padding 176 -->

<!-- intro padding 178 -->

<!-- intro padding 180 -->

<!-- intro padding 182 -->

<!-- intro padding 184 -->

<!-- intro padding 186 -->

<!-- intro padding 188 -->

## Usage Guide

### Installation and Setup

<!-- usage padding 194 -->

<!-- usage padding 196 -->

<!-- usage padding 198 -->

<!-- usage padding 200 -->

<!-- usage padding 202 -->

<!-- usage padding 204 -->

<!-- usage padding 206 -->

<!-- usage padding 208 -->

No complex build steps or database migrations are required. The CMS is built entirely in Python (requires Python 3.10+) and uses Flask for its web interfaces.

<!-- usage padding 212 -->

<!-- usage padding 214 -->

<!-- usage padding 216 -->

<!-- usage padding 218 -->

<!-- usage padding 220 -->

<!-- usage padding 222 -->

<!-- usage padding 224 -->

<!-- usage padding 226 -->

To install prerequisites:

<!-- usage padding 230 -->

![Architecture Overview](images/The_BEJSON_Monolith_-_Slide_11.png)
<!-- usage padding 232 -->

<!-- usage padding 234 -->

<!-- usage padding 236 -->

<!-- usage padding 238 -->

<!-- usage padding 240 -->

<!-- usage padding 242 -->

<!-- usage padding 244 -->

```bash

<!-- usage padding 248 -->

<!-- usage padding 250 -->

<!-- usage padding 252 -->

<!-- usage padding 254 -->

<!-- usage padding 256 -->

<!-- usage padding 258 -->

<!-- usage padding 260 -->

<!-- usage padding 262 -->

pip install flask --break-system-packages

<!-- usage padding 266 -->

<!-- usage padding 268 -->

<!-- usage padding 270 -->

<!-- usage padding 272 -->

<!-- usage padding 274 -->

<!-- usage padding 276 -->

<!-- usage padding 278 -->

<!-- usage padding 280 -->

```

<!-- usage padding 284 -->

<!-- usage padding 286 -->

<!-- usage padding 288 -->

<!-- usage padding 290 -->

<!-- usage padding 292 -->

<!-- usage padding 294 -->

<!-- usage padding 296 -->

<!-- usage padding 298 -->

Because the system avoids heavy background daemons, running the CMS requires merely launching the desired Flask interface:

<!-- usage padding 302 -->

<!-- usage padding 304 -->

<!-- usage padding 306 -->

<!-- usage padding 308 -->
![Architecture Overview](images/The_BEJSON_Monolith_-_Slide_12.png)

<!-- usage padding 310 -->

<!-- usage padding 312 -->

<!-- usage padding 314 -->

<!-- usage padding 316 -->

```bash

<!-- usage padding 320 -->

<!-- usage padding 322 -->

<!-- usage padding 324 -->

<!-- usage padding 326 -->

<!-- usage padding 328 -->

<!-- usage padding 330 -->

<!-- usage padding 332 -->

<!-- usage padding 334 -->

# Start the primary Admin Dashboard (Recommended)

<!-- usage padding 338 -->

<!-- usage padding 340 -->

<!-- usage padding 342 -->

<!-- usage padding 344 -->

<!-- usage padding 346 -->

<!-- usage padding 348 -->

<!-- usage padding 350 -->

<!-- usage padding 352 -->

python3 src/web/pydroid_start.py

<!-- usage padding 356 -->

<!-- usage padding 358 -->

<!-- usage padding 360 -->

<!-- usage padding 362 -->

<!-- usage padding 364 -->

<!-- usage padding 366 -->

<!-- usage padding 368 -->

<!-- usage padding 370 -->

# This runs BEJSON_CMS_Admin.py on http://127.0.0.1:5001

<!-- usage padding 374 -->

<!-- usage padding 376 -->

<!-- usage padding 378 -->

<!-- usage padding 380 -->

<!-- usage padding 382 -->

<!-- usage padding 384 -->

![Architecture Overview](images/The_BEJSON_Monolith_-_Slide_13.png)
<!-- usage padding 386 -->

<!-- usage padding 388 -->



<!-- usage padding 392 -->

<!-- usage padding 394 -->

<!-- usage padding 396 -->

<!-- usage padding 398 -->

<!-- usage padding 400 -->

<!-- usage padding 402 -->

<!-- usage padding 404 -->

<!-- usage padding 406 -->

# Alternatively, manage memory actively by explicitly using the launcher:

<!-- usage padding 410 -->

<!-- usage padding 412 -->

<!-- usage padding 414 -->

<!-- usage padding 416 -->

<!-- usage padding 418 -->

<!-- usage padding 420 -->

<!-- usage padding 422 -->

<!-- usage padding 424 -->

./cms_launcher.sh admin       # BEJSON_CMS_Admin.py (Port 5001)

<!-- usage padding 428 -->

<!-- usage padding 430 -->

<!-- usage padding 432 -->

<!-- usage padding 434 -->

<!-- usage padding 436 -->

<!-- usage padding 438 -->

<!-- usage padding 440 -->

<!-- usage padding 442 -->

./cms_launcher.sh editor      # BEJSON_CMS_PageEditor.py

<!-- usage padding 446 -->

<!-- usage padding 448 -->

<!-- usage padding 450 -->

<!-- usage padding 452 -->

<!-- usage padding 454 -->

<!-- usage padding 456 -->

<!-- usage padding 458 -->

<!-- usage padding 460 -->

./cms_launcher.sh publisher   # BEJSON_CMS_Publisher.py
![Architecture Overview](images/The_BEJSON_Monolith_-_Slide_2.png)

<!-- usage padding 464 -->

<!-- usage padding 466 -->

<!-- usage padding 468 -->

<!-- usage padding 470 -->

<!-- usage padding 472 -->

<!-- usage padding 474 -->

<!-- usage padding 476 -->

<!-- usage padding 478 -->

```

<!-- usage padding 482 -->

<!-- usage padding 484 -->

<!-- usage padding 486 -->

<!-- usage padding 488 -->

<!-- usage padding 490 -->

<!-- usage padding 492 -->

<!-- usage padding 494 -->

<!-- usage padding 496 -->

### Administration & Unorthodox Usage

<!-- usage padding 500 -->

<!-- usage padding 502 -->

<!-- usage padding 504 -->

<!-- usage padding 506 -->

<!-- usage padding 508 -->

<!-- usage padding 510 -->

<!-- usage padding 512 -->

<!-- usage padding 514 -->

To secure the instance, administrators must set the `CMS_PASSWORD` environment variable to replace the default `changeme` credentials.

<!-- usage padding 518 -->

<!-- usage padding 520 -->

<!-- usage padding 522 -->

<!-- usage padding 524 -->

<!-- usage padding 526 -->

<!-- usage padding 528 -->

<!-- usage padding 530 -->

<!-- usage padding 532 -->

The system features a headless CLI controller (`cms-manage.py`) for executing background tasks—such as creating posts or publishing the site—headlessly, allowing orchestration via AI tools.

<!-- usage padding 536 -->

<!-- usage padding 538 -->

![Architecture Overview](images/The_BEJSON_Monolith_-_Slide_3.png)
<!-- usage padding 540 -->

<!-- usage padding 542 -->

<!-- usage padding 544 -->

<!-- usage padding 546 -->

<!-- usage padding 548 -->

<!-- usage padding 550 -->

```bash

<!-- usage padding 554 -->

<!-- usage padding 556 -->

<!-- usage padding 558 -->

<!-- usage padding 560 -->

<!-- usage padding 562 -->

<!-- usage padding 564 -->

<!-- usage padding 566 -->

<!-- usage padding 568 -->

python3 bejson_cms_cli.py --project . add-page --title "New Post" --category BEJSON --html-file body.html

<!-- usage padding 572 -->

<!-- usage padding 574 -->

<!-- usage padding 576 -->

<!-- usage padding 578 -->

<!-- usage padding 580 -->

<!-- usage padding 582 -->

<!-- usage padding 584 -->

<!-- usage padding 586 -->

```

<!-- usage padding 590 -->

<!-- usage padding 592 -->

<!-- usage padding 594 -->

<!-- usage padding 596 -->

<!-- usage padding 598 -->

<!-- usage padding 600 -->

<!-- usage padding 602 -->

<!-- usage padding 604 -->

Publishing the live database to a static site is handled by `BEJSON_CMS_Publisher.py`. Clicking Build on the UI's Interface page will render the entire static artifact to the `storage/builds/` directory.

<!-- usage padding 608 -->

<!-- usage padding 610 -->

<!-- usage padding 612 -->

<!-- usage padding 614 -->

<!-- usage padding 616 -->
![Architecture Overview](images/The_BEJSON_Monolith_-_Slide_4.png)

<!-- usage padding 618 -->

<!-- usage padding 620 -->

<!-- usage padding 622 -->

## Technical Details

The system relies on a clean separation between its flat-file storage engine and its modular, multi-app web layer.

<!-- tech padding 628 -->

<!-- tech padding 630 -->

<!-- tech padding 632 -->

<!-- tech padding 634 -->

<!-- tech padding 636 -->

<!-- tech padding 638 -->

<!-- tech padding 640 -->

<!-- tech padding 642 -->

### 1. Storage Layer: BEJSON 105 Libraries (`libraries_105`)

<!-- tech padding 646 -->

<!-- tech padding 648 -->

<!-- tech padding 650 -->

<!-- tech padding 652 -->

<!-- tech padding 654 -->

<!-- tech padding 656 -->

<!-- tech padding 658 -->

<!-- tech padding 660 -->

The core database engine is not a server but a collection of cross-language parsing and validation scripts.

<!-- tech padding 664 -->

<!-- tech padding 666 -->

<!-- tech padding 668 -->

<!-- tech padding 670 -->

<!-- tech padding 672 -->

<!-- tech padding 674 -->

<!-- tech padding 676 -->

<!-- tech padding 678 -->

- **MFDB Manifests & Entities:** The CMS operates using a single MFDB master manifest (`storage/mfdb/site_master/104a.mfdb.bejson`), which maps to individual entity files acting as tables.

<!-- tech padding 682 -->

<!-- tech padding 684 -->

<!-- tech padding 686 -->

<!-- tech padding 688 -->

<!-- tech padding 690 -->

<!-- tech padding 692 -->

![Architecture Overview](images/The_BEJSON_Monolith_-_Slide_5.png)
<!-- tech padding 694 -->

<!-- tech padding 696 -->

- **Integrity Era Capabilities:** 105 introduces synthetic UUID primary keys (e.g., `page_uuid`, `author_uuid`), O(1) index caching, and Field Map Cache resolution for lightning-fast reads and writes.

<!-- tech padding 700 -->

<!-- tech padding 702 -->

<!-- tech padding 704 -->

<!-- tech padding 706 -->

<!-- tech padding 708 -->

<!-- tech padding 710 -->

<!-- tech padding 712 -->

<!-- tech padding 714 -->

- **Cross-Language Parity:** Core libraries cover data persistence equivalently across Python (`Lib_PY`), JavaScript (`Lib_JS`), TypeScript (`Lib_TS`), and Shell (`Lib_SH`), ensuring seamless data manipulation across any script.

<!-- tech padding 718 -->

<!-- tech padding 720 -->

<!-- tech padding 722 -->

<!-- tech padding 724 -->

<!-- tech padding 726 -->

<!-- tech padding 728 -->

<!-- tech padding 730 -->

<!-- tech padding 732 -->

### 2. Application Layer: CMS Flask Apps (`BEJSON_CMS`)

<!-- tech padding 736 -->

<!-- tech padding 738 -->

<!-- tech padding 740 -->

<!-- tech padding 742 -->

<!-- tech padding 744 -->

<!-- tech padding 746 -->

<!-- tech padding 748 -->

<!-- tech padding 750 -->

The CMS executes via independent Flask applications, registered through blueprints or spawned independently to conserve memory:

<!-- tech padding 754 -->

<!-- tech padding 756 -->

<!-- tech padding 758 -->

<!-- tech padding 760 -->

<!-- tech padding 762 -->

<!-- tech padding 764 -->

<!-- tech padding 766 -->

<!-- tech padding 768 -->

- **Blueprint Admin App (`BEJSON_CMS_Admin.py`):** The primary entry point. It registers four distinct operational blueprints: System, Content, Media, and Interface.
![Architecture Overview](images/The_BEJSON_Monolith_-_Slide_6.png)

<!-- tech padding 772 -->

<!-- tech padding 774 -->

<!-- tech padding 776 -->

<!-- tech padding 778 -->

<!-- tech padding 780 -->

<!-- tech padding 782 -->

<!-- tech padding 784 -->

<!-- tech padding 786 -->

- **Dual Page Editors:** Offers a standard monolithic editor (`BEJSON_CMS_PageEditor.py`) and a modern API-driven editor currently in active development (`BEJSON_CMS_PageEditorV2.py`).

<!-- tech padding 790 -->

<!-- tech padding 792 -->

<!-- tech padding 794 -->

<!-- tech padding 796 -->

<!-- tech padding 798 -->

<!-- tech padding 800 -->

<!-- tech padding 802 -->

<!-- tech padding 804 -->

- **AI Persona Hub (`BEJSON_CMS_ProfileManager.py`):** Exclusively manages AI profile records used by the system's generation features, keeping internal prompts isolated from public-facing author bios.

<!-- tech padding 808 -->

<!-- tech padding 810 -->

<!-- tech padding 812 -->

<!-- tech padding 814 -->

<!-- tech padding 816 -->

<!-- tech padding 818 -->

<!-- tech padding 820 -->

<!-- tech padding 822 -->

- **Static Publisher (`BEJSON_CMS_Publisher.py`):** Acts as the build engine. It compiles the live MFDB content into a fully static, dependency-free HTML site dropped into the `storage/builds/` directory.

<!-- tech padding 826 -->

<!-- tech padding 828 -->

<!-- tech padding 830 -->

<!-- tech padding 832 -->

<!-- tech padding 834 -->

<!-- tech padding 836 -->

<!-- tech padding 838 -->

<!-- tech padding 840 -->

### 3. Core Capabilities

<!-- tech padding 844 -->

<!-- tech padding 846 -->

![Architecture Overview](images/The_BEJSON_Monolith_-_Slide_7.png)
<!-- tech padding 848 -->

<!-- tech padding 850 -->

<!-- tech padding 852 -->

<!-- tech padding 854 -->

<!-- tech padding 856 -->

<!-- tech padding 858 -->

- **Canonical Prefix Taxonomy:** Enforces a unified naming convention for all entity tables (e.g., `page_`, `author_`, `asset_`, `ad_`, `sys_`). This ensures schema consistency and drastically simplifies automated database migrations.

<!-- tech padding 862 -->

<!-- tech padding 864 -->

<!-- tech padding 866 -->

<!-- tech padding 868 -->

<!-- tech padding 870 -->

<!-- tech padding 872 -->

<!-- tech padding 874 -->

<!-- tech padding 876 -->

- **Polymorphic Page Rendering:** Employs the Strategy Pattern (`BEJSON_CMS_Renderers.py`) during static publishing to render diverse content types flawlessly:

<!-- tech padding 880 -->

<!-- tech padding 882 -->

<!-- tech padding 884 -->

<!-- tech padding 886 -->

<!-- tech padding 888 -->

<!-- tech padding 890 -->

<!-- tech padding 892 -->

<!-- tech padding 894 -->

    - *Standard Pages:* Rich-text articles and basic web pages.

<!-- tech padding 898 -->

<!-- tech padding 900 -->

<!-- tech padding 902 -->

<!-- tech padding 904 -->

<!-- tech padding 906 -->

<!-- tech padding 908 -->

<!-- tech padding 910 -->

<!-- tech padding 912 -->

    - *Video Pages:* Dedicated layouts for YouTube embeds, complete with automatic URL parsing and responsive aspect-ratio framing.

<!-- tech padding 916 -->

<!-- tech padding 918 -->

<!-- tech padding 920 -->

<!-- tech padding 922 -->

<!-- tech padding 924 -->
![Architecture Overview](images/The_BEJSON_Monolith_-_Slide_8.png)

<!-- tech padding 926 -->

<!-- tech padding 928 -->

<!-- tech padding 930 -->

    - *Document Pages:* Lightweight distribution layouts featuring customized download cards and file metadata.

<!-- tech padding 934 -->

<!-- tech padding 936 -->

<!-- tech padding 938 -->

<!-- tech padding 940 -->

<!-- tech padding 942 -->

<!-- tech padding 944 -->

<!-- tech padding 946 -->

<!-- tech padding 948 -->

- **Media Asset Manager:** Includes a centralized media library featuring hash-deduplication to prevent duplicate uploads, a single-serial upload worker for low peak memory, and a tap-to-zoom lightbox UI.

<!-- tech padding 952 -->

<!-- tech padding 954 -->

<!-- tech padding 956 -->

<!-- tech padding 958 -->

<!-- tech padding 960 -->

<!-- tech padding 962 -->

<!-- tech padding 964 -->

<!-- tech padding 966 -->

- **Single-Service Launcher:** The custom `cms_launcher.sh` script automatically terminates competing Flask instances before starting a requested service. This strictly enforces a single-process footprint.

<!-- tech padding 970 -->

<!-- tech padding 972 -->

<!-- tech padding 974 -->

<!-- tech padding 976 -->

<!-- tech padding 978 -->

<!-- tech padding 980 -->

<!-- tech padding 982 -->

<!-- tech padding 984 -->

### 4. Design & Aesthetics

<!-- tech padding 988 -->

<!-- tech padding 990 -->

<!-- tech padding 992 -->

<!-- tech padding 994 -->

<!-- tech padding 996 -->

<!-- tech padding 998 -->

<!-- tech padding 1000 -->

![Architecture Overview](images/The_BEJSON_Monolith_-_Slide_9.png)
<!-- tech padding 1002 -->

The frontend design embraces a striking, minimalist aesthetic governed strictly by three core thematic colors: **Black**, **White**, and **#DE2627**.

<!-- tech padding 1006 -->

<!-- tech padding 1008 -->

<!-- tech padding 1010 -->

<!-- tech padding 1012 -->

<!-- tech padding 1014 -->

<!-- tech padding 1016 -->

<!-- tech padding 1018 -->

<!-- tech padding 1020 -->

## Summary

In summation, BEJSON CMS stands as a testament to the power of structured, zero-dependency, flat-file architectures. By leaning into the strengths of the MFDB and BEJSON paradigms, it achieves incredible portability, predictable performance, and strict schema compliance.

<!-- summary padding 1026 -->

<!-- summary padding 1028 -->

<!-- summary padding 1030 -->

<!-- summary padding 1032 -->

<!-- summary padding 1034 -->

<!-- summary padding 1036 -->

<!-- summary padding 1038 -->

<!-- summary padding 1040 -->

<!-- summary padding 1042 -->

<!-- summary padding 1044 -->

It allows you to maintain complete ownership of your data, bypassing the complexities of ORMs and traditional relational databases while retaining the structural guarantees required for a complex Content Management System.

<!-- summary padding 1048 -->

<!-- summary padding 1050 -->

<!-- summary padding 1052 -->

<!-- summary padding 1054 -->

<!-- summary padding 1056 -->

<!-- summary padding 1058 -->

<!-- summary padding 1060 -->

<!-- summary padding 1062 -->

<!-- summary padding 1064 -->

<!-- summary padding 1066 -->

With its dedicated static publisher, AI persona integration, and modular Flask toolchain, it provides an unparalleled environment for personal knowledge management, content generation, and rapid static site deployment.

<!-- summary padding 1070 -->

<!-- summary padding 1072 -->

<!-- summary padding 1074 -->

<!-- summary padding 1076 -->

<!-- summary padding 1078 -->

<!-- summary padding 1080 -->

<!-- summary padding 1082 -->

<!-- summary padding 1084 -->

<!-- summary padding 1086 -->

<!-- summary padding 1088 -->

---
Elton Boehnen &middot; boehnenelton2024@gmail.com &middot; boehnenelton2024.pages.dev &middot; github.com/boehnenelton
