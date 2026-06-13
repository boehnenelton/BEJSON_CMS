# BEJSON_CMS Development Roadmap

## Phase 2: Media & Advanced Integration

- [ ] **Image Media Management**
  - Implement bulk import utility for `/storage/emulated/0/Admin/dev/Python/BEJSON_CMS/storage/assets`.
  - Automated hashing (SHA-256) and registration in `MediaAsset` entity.
  - MIME-type detection and resolution.

- [ ] **Standalone App Importing**
  - Logic to register ZIP or folder-based HTML5 apps into the CMS.
  - Map `entry_file` and metadata to the `StandaloneApp` entity.

- [ ] **Page Media Linking**
  - Update CLI (`page set-image`) to link `MediaAsset` filenames to `Page` records via `featured_img`.
  - Implement cross-entity validation during creation.

- [ ] **Template Injection System**
  - Create a publisher module that replaces `{{key}}` placeholders with `SiteConfig` values.
  - Support for dynamic `NavLink` and `SocialLink` list injection into HTML skeletons.

## Phase 3: Intelligence & Security

- [ ] **Gemini AI Integration** (Mandate Sec 10)
  - Implement content optimizer using `google-genai` SDK.
  - Support for automated meta-description and tag generation.
  - Integrate mandated **API Key Rotation** (round-robin) across 20 slots.

- [ ] **Systemic Audit Logging** (Mandate Sec 17)
  - Create a dedicated `AuditEvent` entity in `global_master.mfdb`.
  - Automatically log all CLI and Web-based mutations (who, what, when).
  - Implement `related_entity_id_fk` for forensic traceability.

- [ ] **Search Indexer**
  - Build a lightweight full-text search index for MFDB `PageContent`.
  - CLI command `cms search <query>` for rapid content discovery.

- [ ] **Security Boundary Enforcement** (Mandate Sec 64)
  - Integrate `is_restricted` checks into the `MFDB_CMS_Manager`.
  - Prevent unauthorized modifications to sensitive entities via CLI.

- [ ] **Theme & UI Orchestration** (Mandate Sec 9)
  - Standardize CSS palette (#FFFFFF, #000000, #DE2626) in `dark.css`.
  - Implement a theme switcher that updates `SiteConfig` and triggers a publisher rebuild.

- [ ] **Automatic Sitemap & RSS Generation**
  - Publisher support for generating `sitemap.xml` and `feed.xml` based on `Category` feeds.

---
*Created: 2026-06-09 | Updated: 2026-06-09 | Author: Elton Boehnen*
