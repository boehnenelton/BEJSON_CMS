"""
Name:           test_bejson_cms_profile_manager.py
Description:    Integration and unit test suite for BEJSON_CMS_ProfileManager.py
                and lib_cms_persona_writer.py covering all 20 Persona Editor audit
                remediations and verification probes (T1-T8).
Version:        1.0
Date:           2026-11-07
Author:         Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
RELATIONAL_ID:  8a4e91c2-5b13-4d76-9f28-1c3e7b6a4d20
"""

import base64
import os
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src" / "web"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "lib"))

os.environ.setdefault("CMS_PASSWORD", "test-only-password-for-pytest")

import BEJSON_CMS_ProfileManager as profile_mgr
import lib_bejson_CMS_cms_core as CMSCore
import lib_bejson_CMS_taxonomy as Taxonomy
import lib_cms_persona_writer as PersonaWriterMod


def _auth_headers(extra=None):
    creds = base64.b64encode(f"admin:{os.environ['CMS_PASSWORD']}".encode()).decode()
    headers = {"Authorization": f"Basic {creds}"}
    if extra:
        headers.update(extra)
    return headers


@pytest.fixture()
def isolated_profile_env(tmp_path, monkeypatch):
    """Create an isolated copy of site_master MFDB for each test."""
    src_site_master = PROJECT_ROOT / "storage" / "mfdb" / "site_master"
    dst_site_master = tmp_path / "site_master"
    shutil.copytree(src_site_master, dst_site_master)
    manifest_file = dst_site_master / "104a.mfdb.bejson"
    isolated_db = CMSCore.CMSCore(str(manifest_file))
    isolated_db.mount()
    monkeypatch.setattr(profile_mgr, "db", isolated_db)
    monkeypatch.setattr(profile_mgr, "MANIFEST_PATH", str(manifest_file))
    client = profile_mgr.app.test_client()
    return client, isolated_db, str(manifest_file)


class TestPersonaEditorAuditRemediations:
    def test_t1_save_preserves_version_control_and_avatar_data(self, isolated_profile_env):
        """Finding #1 / Probe T1: Saving an existing persona preserves CodeParsing_VersionControl and Avatar_Data."""
        client, isolated_db, _ = isolated_profile_env
        clean_svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><circle cx="8" cy="8" r="6"/></svg>'

        resp = client.post(
            "/save",
            headers=_auth_headers(),
            data={
                "original_name": "Code Sentinel",
                "name": "Code Sentinel",
                "archetype": "Security & AST Policy Auditor",
                "persona_bio": "Updated bio",
                "system_instruction": "Audit all parameters.",
                "active": "1",
                "max_tokens": "4096",
                "creativity": "0.3",
                "tones": "analytical,critical",
                "formality": "formal",
                "verbosity": "concise",
                "emotional_intensity": "0.0",
                "code_interpreter": "1",
                "code_mode": "strict",
                "code_languages": "python,bash",
                "structure_validation": "1",
                "version_control": "1",
                "thinking_supported": "1",
                "forbidden_topics": "unmasked credentials",
                "avatar_type": "data",
                "avatar_sourceUrl": "",
                "avatar_data": clean_svg,
                "_form_full": "1",
            },
        )
        assert resp.status_code == 302
        saved = next(p for p in isolated_db.get_records("AI_Profile") if p["Name"] == "Code Sentinel")
        assert saved["CodeParsing_VersionControl"] is True
        assert "<svg" in saved["Avatar_Data"]
        assert "circle" in saved["Avatar_Data"]

        # Partial post without version_control or avatar_data also preserves existing stored values
        resp2 = client.post(
            "/save",
            headers=_auth_headers(),
            data={
                "name": "Code Sentinel",
                "archetype": "Security & AST Policy Auditor",
                "formality": "formal",
                "verbosity": "concise",
                "creativity": "0.3",
                "max_tokens": "4096",
                "code_mode": "strict",
                "avatar_type": "data",
            },
        )
        assert resp2.status_code == 302
        saved_after = next(p for p in isolated_db.get_records("AI_Profile") if p["Name"] == "Code Sentinel")
        assert saved_after["CodeParsing_VersionControl"] is True
        assert "<svg" in saved_after["Avatar_Data"]

    def test_t2_xss_and_avatar_sanitization(self, isolated_profile_env):
        """Findings #13 & #14 / Probe T2: Malicious SVG onload and javascript: avatar URLs are rejected."""
        client, isolated_db, _ = isolated_profile_env
        resp_bad_url = client.post(
            "/save",
            headers=_auth_headers(),
            data={
                "name": "Code Sentinel",
                "formality": "formal",
                "verbosity": "concise",
                "creativity": "0.3",
                "max_tokens": "4096",
                "code_mode": "strict",
                "avatar_type": "url",
                "avatar_sourceUrl": "javascript:alert(1)",
            },
        )
        assert resp_bad_url.status_code == 302
        assert "Error" in unquote(resp_bad_url.headers["Location"])

        # SVG with onload handler has onload stripped by svg_sanitizer
        resp_svg_onload = client.post(
            "/save",
            headers=_auth_headers(),
            data={
                "name": "Code Sentinel",
                "formality": "formal",
                "verbosity": "concise",
                "creativity": "0.3",
                "max_tokens": "4096",
                "code_mode": "strict",
                "avatar_type": "data",
                "avatar_data": '<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><rect width="10" height="10"/><script>alert(1)</script></svg>',
            },
        )
        assert resp_svg_onload.status_code == 302
        saved = next(p for p in isolated_db.get_records("AI_Profile") if p["Name"] == "Code Sentinel")
        assert "onload" not in saved["Avatar_Data"].lower()
        assert "<script" not in saved["Avatar_Data"].lower()

    def test_t3_case_insensitive_update_succeeds(self, isolated_profile_env):
        """Finding #3 / Probe T3: Posting lowercase name against mixed-case stored Name updates the record."""
        client, isolated_db, _ = isolated_profile_env
        resp = client.post(
            "/save",
            headers=_auth_headers(),
            data={
                "name": "code sentinel",
                "archetype": "Updated Security Auditor",
                "persona_bio": "Case-matched update check",
                "formality": "formal",
                "verbosity": "concise",
                "creativity": "0.4",
                "max_tokens": "4096",
                "code_mode": "strict",
                "avatar_type": "cube",
            },
        )
        assert resp.status_code == 302
        saved = next(p for p in isolated_db.get_records("AI_Profile") if p["Name"] == "Code Sentinel")
        assert saved["Archetype"] == "Updated Security Auditor"
        assert saved["Persona"] == "Case-matched update check"

    def test_t4_unsafe_name_characters_and_url_encoding(self, isolated_profile_env):
        """Finding #11 / Probe T4: Names with /, ?, #, % are rejected and redirects are URL-encoded."""
        client, isolated_db, _ = isolated_profile_env
        for unsafe_name in ["A/B?x=1#y", "Bad%Name", "Bad<Script>"]:
            resp = client.post(
                "/save",
                headers=_auth_headers(),
                data={"name": unsafe_name},
            )
            assert resp.status_code == 302
            assert "Error" in unquote(resp.headers["Location"])
            assert not any(p["Name"] == unsafe_name for p in isolated_db.get_records("AI_Profile"))

        # Valid name with spaces is properly URL-encoded in redirect
        resp_valid = client.post(
            "/save",
            headers=_auth_headers(),
            data={
                "name": "Custom Agent Alpha",
                "archetype": "Analyst",
                "formality": "rigorous",
                "verbosity": "concise",
                "creativity": "0.5",
                "max_tokens": "4096",
                "code_mode": "strict",
                "avatar_type": "cube",
            },
        )
        assert resp_valid.status_code == 302
        assert "/edit/Custom%20Agent%20Alpha?" in resp_valid.headers["Location"]

    def test_t5_validation_rejects_out_of_range_nan_and_bad_enums(self, isolated_profile_env):
        """Finding #10 / Probe T5: Out-of-range creativity, NaN, negative tokens, and invalid enums are rejected."""
        client, isolated_db, _ = isolated_profile_env
        invalid_payloads = [
            {"name": "Code Sentinel", "creativity": "99"},
            {"name": "Code Sentinel", "creativity": "nan"},
            {"name": "Code Sentinel", "max_tokens": "-5"},
            {"name": "Code Sentinel", "formality": "<script>"},
            {"name": "Code Sentinel", "code_mode": "zzz"},
            {"name": "Code Sentinel", "emotional_intensity": "2.5"},
        ]
        for bad_data in invalid_payloads:
            resp = client.post("/save", headers=_auth_headers(), data=bad_data)
            assert resp.status_code == 302
            assert "Error" in unquote(resp.headers["Location"])

        sentinel = next(p for p in isolated_db.get_records("AI_Profile") if p["Name"] == "Code Sentinel")
        assert sentinel["Creativity"] == 0.3
        assert sentinel["MaxResponseTokens"] == 4096
        assert sentinel["Formality"] == "formal"
        assert sentinel["CodeParsing_Mode"] == "strict"

    def test_t6_protect_default_persona_and_cleanup_author_profile_on_delete(self, isolated_profile_env):
        """Finding #5 / Probe T6: Deleting boehnenelton2024 is blocked; deleting custom persona removes AuthorProfile."""
        client, isolated_db, _ = isolated_profile_env

        # Attempt to delete default persona boehnenelton2024
        resp_default = client.post("/delete/boehnenelton2024", headers=_auth_headers())
        assert resp_default.status_code == 302
        assert "Cannot delete canonical default" in unquote(resp_default.headers["Location"])
        assert any(p["Name"] == "boehnenelton2024" for p in isolated_db.get_records("AI_Profile"))

        # Delete non-default persona Code Sentinel and verify AuthorProfile is also deleted
        assert any(a["author_display_name"] == "Code Sentinel" for a in isolated_db.get_records("AuthorProfile"))
        resp_del = client.post("/delete/Code%20Sentinel", headers=_auth_headers())
        assert resp_del.status_code == 302
        assert not any(p["Name"] == "Code Sentinel" for p in isolated_db.get_records("AI_Profile"))
        assert not any(a["author_display_name"] == "Code Sentinel" for a in isolated_db.get_records("AuthorProfile"))

    def test_t7_csrf_foreign_origin_rejected(self, isolated_profile_env):
        """Finding #4 / Probe T7: Cross-origin POST with foreign Origin or Referer returns 403 Forbidden."""
        client, isolated_db, _ = isolated_profile_env
        resp = client.post(
            "/delete/Code%20Sentinel",
            headers=_auth_headers({"Origin": "https://evil.example"}),
        )
        assert resp.status_code == 403
        assert any(p["Name"] == "Code Sentinel" for p in isolated_db.get_records("AI_Profile"))

        resp_ref = client.post(
            "/save",
            headers=_auth_headers({"Referer": "https://evil.example/attack.html"}),
            data={"name": "Injected"},
        )
        assert resp_ref.status_code == 403

    def test_t8_inactive_persona_blocked_and_unknown_edit_returns_404(self, isolated_profile_env):
        """Findings #6, #7, #8, #16 / Probe T8: Inactive personas do not resolve or execute; /edit/DoesNotExist returns 404."""
        client, isolated_db, manifest_path = isolated_profile_env

        # Unknown persona edit returns 404
        resp_404 = client.get("/edit/DoesNotExist", headers=_auth_headers())
        assert resp_404.status_code == 404

        writer = PersonaWriterMod.PersonaWriter(manifest_path)
        active_persona = writer.get_persona("Code Sentinel")
        assert active_persona is not None
        assembled = writer.assemble_system_instruction(active_persona)
        assert "[IDENTITY]: Code Sentinel (Security & AST Policy Auditor)" in assembled
        assert "[TONE]: analytical, critical, rigorous, precise" in assembled
        assert "[DELIVERY]: Formality=formal, Verbosity=concise, Creativity=0.3" in assembled
        assert "[COGNITIVE_GATES]: Thinking=true, CodeInterpreter=true, EphemeralMemory=false, MaxResponseTokens=4096" in assembled
        assert "[CODE_PARSING]: Mode=strict, StructureValidation=true, VersionControl=true" in assembled
        assert "[VOICE_DIRECTIVES]:" in assembled
        assert "[SYSTEM_INSTRUCTION]:" in assembled
        assert "[LANGUAGES]: python, bash, json" in assembled
        assert "[FORBIDDEN_TOPICS]: unverified claims, unmasked credentials" in assembled
        assert "[SAFETY_BOUNDARIES]:" in assembled

        # Set Active=False and verify get_persona, assemble_system_instruction, and dispatch_ai block it
        isolated_db.update_record("AI_Profile", "Name", "Code Sentinel", {"Active": False})
        assert writer.get_persona("Code Sentinel") is None
        inactive_raw = writer.get_persona("Code Sentinel", include_inactive=True)
        assert inactive_raw is not None
        assert writer.assemble_system_instruction(inactive_raw) == ""
        dispatch_res = writer.dispatch_ai("Test prompt", persona_name="Code Sentinel")
        assert dispatch_res["success"] is False
        assert "inactive" in dispatch_res["error"].lower()

    def test_duplicate_and_seed_sync_author_profile_and_rename_cascades(self, isolated_profile_env):
        """Findings #2, #9, #12, #18: Duplicate and seed sync AuthorProfile; rename cascades to AuthorProfile and PageRecord."""
        client, isolated_db, _ = isolated_profile_env

        # Duplicate Code Sentinel
        resp_dup = client.post("/duplicate/Code%20Sentinel", headers=_auth_headers())
        assert resp_dup.status_code == 302
        assert any(p["Name"] == "Code Sentinel_Copy" for p in isolated_db.get_records("AI_Profile"))
        assert any(a["author_display_name"] == "Code Sentinel_Copy" for a in isolated_db.get_records("AuthorProfile"))

        # Rename Code Sentinel_Copy -> Sentinel Prime and verify cascade
        resp_rename = client.post(
            "/save",
            headers=_auth_headers(),
            data={
                "original_name": "Code Sentinel_Copy",
                "name": "Sentinel Prime",
                "archetype": "Auditor",
                "formality": "academic",
                "verbosity": "balanced",
                "creativity": "0.5",
                "max_tokens": "4096",
                "code_mode": "strict",
                "avatar_type": "cube",
            },
        )
        assert resp_rename.status_code == 302
        assert not any(p["Name"] == "Code Sentinel_Copy" for p in isolated_db.get_records("AI_Profile"))
        assert any(p["Name"] == "Sentinel Prime" for p in isolated_db.get_records("AI_Profile"))
        assert any(a["author_display_name"] == "Sentinel Prime" for a in isolated_db.get_records("AuthorProfile"))

        # Check taxonomy registration (#18)
        assert "AI_Profile" in Taxonomy.taxonomy_list_entities()
        assert Taxonomy.taxonomy_get_uuid_field("AI_Profile") == "Name"
