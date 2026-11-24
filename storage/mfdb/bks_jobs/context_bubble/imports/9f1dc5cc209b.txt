# AI_Core urgent-instructions progress (2026-11-17) — PARTIAL

DONE
- Lib_PY/AI renamed to Lib_PY/AI_Core; all modules now lib_bejson_AI_Core_<module>.py (errors: lib_bejson_AI_Core_errors.py). 49/49 existing tests pass.
- Core dependency = BEJSON read/write only, via lib_bejson_AI_Core_core_bridge.py (config, key-rotator state, 105 envelopes now go through Core).
- Validator: lib_bejson_AI_Core_validator.py (naming, headers, VERSION sync, no print, no abs paths, no key in URL, stdlib-only, Core only via bridge, logger present) + SHA-256 freeze manifest (not frozen yet). AI_Core: 0 violations.
- Plugin registry + schema: plugin_schema / plugin_base / plugin_registry (pre, post, render; gated by new plugins_enabled setting; hooked into dispatcher). Error codes 236-244 (AI now owns 200-249).
- Lib_PY/AI_Extensions: 3 sample plugins with SHA-pinned extension.105a.bejson manifests + manifest tool.
- 105 profiles: lib_bejson_AI_Core_profiles.py (create/validate/update, 104->105 converter, never overwrites source). Ported runtime to AI_Extensions/lib_bejson_AI_Extensions_profile_runtime.py.

DONE (Continued)
- AI_Extensions profile_compiler and profile_abstraction ported and verified.
- AI_Core and AI_Extensions test suites (103 total tests: 82 AI_Core + 21 AI_Extensions) passing 100%.
- BEJSON/ self-tracking MFDB ledger synchronized: families.bejson (AI_Core + AI_Extensions), metadata.bejson (5.9.11), library_changes.bejson, and 104a.mfdb.bejson validated clean.
- AI_Core and AI_Extensions README.md documentation refreshed.
- Both families verified with 0 violations via lib_bejson_AI_Core_validator.py.

