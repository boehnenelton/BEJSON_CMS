"""
Library:        lib_bejson_AI_bejson_gemini_transcribe.py
Family:         AI
Description:    Audio/video transcription wrapper for Google Gemini's
                 multimodal `generate_content` endpoint (google-genai SDK).
                 Sibling module to lib_bejson_AI_bejson_gemini.py -- same
                 pattern already used for lib_bejson_AI_bejson_interactions.py
                 (a new file added alongside gemini.py rather than editing
                 it): gemini.py's GeminiAPI.generate() is text-in/text-out
                 and was never touched, so nothing that already imports it
                 is affected by this addition.

                 Ports the transcription mechanics of the standalone React
                 "Audio Transcriber" tool (App.tsx / server.ts, RELATIONAL_ID
                 05fc2518-bcbe-47ba-bd7f-2de1a7e5ea6d) into the BEJSON/MFDB
                 AI-family library ecosystem: media is base64-encoded and
                 sent as an inlineData Part alongside a text prompt to
                 ai.models.generate_content, with the same verbatim /
                 diarization / segment-marker prompt modes and the same
                 domain-terminology cleanup pass (BEJSON / BEHTML / MFDB /
                 104db / author name) run on the returned text.

                 Reuses gemini.py's own GeminiKeyRegistry, GeminiModelRegistry,
                 STD_KEY_PATH and STD_MODEL_PATH -- transcription and text
                 generation share the same API keys and the same Gemini
                 model lineup (Gemini 3.x/3.5+ Flash/Pro models are all
                 natively multimodal), so this module does not stand up a
                 second registry pair. No existing AI-family file was
                 modified to add this capability.
Version:        1.0.0
Date:           2026-09-03
Author:         Elton Boehnen
Contact:        boehnenelton2024@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  8f1c6a2d-4e7b-49f0-9a3c-2d6e8b1f5c94
Release_Version: 300

Changelog:
  1.0.0 (2026-09-03) -- Initial creation. New sibling file in the AI family;
        lib_bejson_AI_bejson_gemini.py, lib_bejson_AI_ai_registry_base.py,
        and lib_bejson_AI_bejson_errors.py were not modified beyond the
        additive E_AI_TRANSCRIBE_* error codes appended to bejson_errors.py
        1.3.0. Integrated into CLI_AI via
        lib_bejson_AI_ai_transcribe_dispatch.py and CLI/transcribe_cli/.
"""

import base64
import logging
import os
import re as _re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    from google import genai
    from google.genai import types
except ImportError:
    # Mirrors gemini.py: don't crash on import so registry management still
    # works without the SDK; GeminiTranscribeAPI itself will raise a typed
    # SDKNotInstalledError if actually used.
    genai = None

# --- Sibling Resolution ---
LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

CORE_DIR = os.path.join(os.path.dirname(LIB_DIR), "Core")
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

VERSION = "1.0.0"

try:
    from lib_bejson_AI_bejson_gemini import (
        GeminiKeyRegistry,
        GeminiModelRegistry,
        STD_KEY_PATH,
        STD_MODEL_PATH,
        _classify_generation_error,
    )
    from lib_bejson_AI_bejson_errors import (
        SDKNotInstalledError,
        NoAPIKeysError,
        TranscribeMediaNotFoundError,
        TranscribeUnsupportedMediaError,
        TranscribeMediaTooLargeError,
        TranscribeChunkingUnavailableError,
        TranscribeChunkingFailedError,
    )
    _CORE_IMPORT_ERROR = None
except ImportError as e:
    # Same graceful-degradation convention as every other AI-family module:
    # a caller doing `try: import lib_bejson_AI_bejson_gemini_transcribe /
    # except ImportError:` can catch this instead of the host process dying.
    _CORE_IMPORT_ERROR = e
    logging.error(f"[GeminiTranscribeLib] Missing AI-family dependencies: {e}")
    raise

logger = logging.getLogger("lib_bejson_AI_bejson_gemini_transcribe")

# --- Media type tables -------------------------------------------------
# Mirrors the extension lists used by the mediatrim CLI tool and the React
# Audio Transcriber, kept in one place here so both CLI-side detection and
# the Gemini `mimeType` field agree on the same file.

AUDIO_MIME_MAP: Dict[str, str] = {
    "mp3": "audio/mpeg", "m4a": "audio/mp4", "wav": "audio/wav",
    "aac": "audio/aac", "flac": "audio/flac", "ogg": "audio/ogg",
    "opus": "audio/opus", "wma": "audio/x-ms-wma", "mka": "audio/x-matroska",
    "aiff": "audio/aiff", "alac": "audio/mp4",
}

VIDEO_MIME_MAP: Dict[str, str] = {
    "mp4": "video/mp4", "mkv": "video/x-matroska", "mov": "video/quicktime",
    "avi": "video/x-msvideo", "webm": "video/webm", "flv": "video/x-flv",
    "wmv": "video/x-ms-wmv", "m4v": "video/x-m4v", "ts": "video/mp2t",
    "3gp": "video/3gpp", "ogv": "video/ogg",
}

# Gemini inline-data requests are limited to ~20MB total request payload;
# base64 inflates size by ~4/3, so cap the raw file well under that.
MAX_INLINE_BYTES = 15 * 1024 * 1024  # 15MB raw -> ~20MB base64

# --- Domain terminology cleanup -----------------------------------------
# Ported verbatim (regex-for-regex) from cleanDomainTerminology() in
# App.tsx / server.ts (RELATIONAL_ID 05fc2518-bcbe-47ba-bd7f-2de1a7e5ea6d)
# so a transcript produced here reads identically to one produced by the
# React tool.

_DOMAIN_CLEANUP_PATTERNS = [
    (r"\bElton\s+Bon[ie]n\b", "Elton Boehnen"),
    (r"\bMDFB\b", "MFDB"),
    (r"\b(?:BJAON|B\s+JAON|B-JAON|Bachain|Bason|Bazon|BJSON|B\s+JSON|beJSON|be-json|be\s+json)\b", "BEJSON"),
    (r"\b(?:BHTML|B\s+HTML|B-HTML|beHTML|be-html|be\s+html)\b", "BEHTML"),
    (r"\bBEJSON\s+plus\s+(?:BHTML|B\s+HTML|be\s+html|BEHTML)\b", "BEJSON plus BEHTML"),
    (r"\b(?:BJAON|B\s+JAON)\s+plus\s+(?:BHTML|B\s+HTML|BEHTML)\b", "BEJSON plus BEHTML"),
    (r"\b140B\b", "104db"),
    (r"\b104-DB\b", "104db"),
    (r"\bMDFB\s+132\b", "MFDB 1.32"),
    (r"\b(?:eltonboehnen|eltonbon[ie]n|boehnenelton)\s*(?:at|@)\s*gmail\.com\b", "boehnenelton2024@gmail.com"),
]
_DOMAIN_CLEANUP_COMPILED = [(_re.compile(p, _re.IGNORECASE), r) for p, r in _DOMAIN_CLEANUP_PATTERNS]


def clean_domain_terminology(text: str) -> str:
    """Corrects known mis-transcriptions of BEJSON/BEHTML/MFDB/104db and the
    author's name. Pure text function -- ported from the React Audio
    Transcriber's cleanDomainTerminology() so output matches byte-for-byte
    in behavior."""
    if not text:
        return text
    cleaned = text
    for pattern, repl in _DOMAIN_CLEANUP_COMPILED:
        cleaned = pattern.sub(repl, cleaned)
    return cleaned


_DOMAIN_CONTEXT_INSTRUCTIONS = (
    "CRITICAL MANDATORY DOMAIN DICTIONARY & TERMINOLOGY INSTRUCTIONS:\n"
    "- 'BEHTML' must ALWAYS be spelled 'BEHTML' (Boehnen Elton HTML). NEVER "
    "spell it as 'BHTML', 'B HTML', 'be HTML', 'beHTML', or 'bhtml'.\n"
    "- 'BEJSON' must ALWAYS be spelled 'BEJSON' (Boehnen Elton JSON). NEVER "
    "spell it as 'BJAON', 'B JAON', 'Bason', 'B-JAON', 'BJSON', 'B JSON', "
    "'beJSON', or 'be json'.\n"
    "- 'MFDB' must ALWAYS be spelled 'MFDB' (Multi-File Data Base). NEVER "
    "spell it as 'MDFB'.\n"
    "- Author Name: 'Elton Boehnen'. NEVER spell it as 'Elton Bonin' or "
    "'Elton Bonen'.\n"
    "- Standard Formats: '104', '104a', '104db' (NEVER '140B' or '104-DB').\n"
    "Transcribe these terms with absolute precision as specified above."
)


def _build_system_prompt(mode: str, segment: bool, domain_context: bool, extra_instructions: Optional[str]) -> str:
    """Mirrors server.ts's /api/transcribe prompt assembly (verbatim vs
    diarization, plus the optional segment-marker addendum)."""
    context = f"\n\n{_DOMAIN_CONTEXT_INSTRUCTIONS}" if domain_context else ""

    if mode == "diarization":
        prompt = (
            "Please transcribe this audio clip. Perform voice recognition to "
            "distinguish between different speakers (e.g., Speaker A, Speaker B). "
            "Identify transitions, tag the speakers accurately, and locate the "
            "timeline/timestamps (e.g., [00:12 - 00:25] Speaker A: ...) when each "
            "speaker talks. Return a clean, readable verbatim transcript formatted "
            "with speaker tags and timestamps. Do not add any preamble or "
            f"conversational introduction, just output the transcript text.{context}"
        )
    else:
        prompt = (
            "Please transcribe this audio clip accurately and verbatim. Return "
            f"only the transcription text.{context}"
        )

    if segment:
        prompt += (
            "\n\nADDITIONAL INSTRUCTION: Attempt to identify logical segments, "
            "chapters, or major topic transitions within the audio. Format the "
            "output with clear segment headers like '--- Segment X: [Topic Name] "
            "---' or similar structural markers. Ensure the transcription remains "
            "accurate and verbatim within each segment."
        )

    if extra_instructions:
        prompt += f"\n\n{extra_instructions}"

    return prompt


def detect_media_mime_type(file_path: Union[str, Path]) -> str:
    """
    Resolves a Gemini-compatible mimeType from a file extension using the
    AUDIO_MIME_MAP / VIDEO_MIME_MAP tables above. Raises
    TranscribeUnsupportedMediaError for an unrecognized extension rather than
    guessing -- Section 5.2's "do not fill ambiguous gaps" applies here: a
    wrong mimeType silently sent to Gemini fails opaquely on the provider
    side instead of with a clear local error.
    """
    ext = Path(file_path).suffix.lower().lstrip(".")
    if ext in AUDIO_MIME_MAP:
        return AUDIO_MIME_MAP[ext]
    if ext in VIDEO_MIME_MAP:
        return VIDEO_MIME_MAP[ext]
    raise TranscribeUnsupportedMediaError(
        f"Unsupported media extension '.{ext}' for {file_path}. "
        f"Supported audio: {sorted(AUDIO_MIME_MAP)}; video: {sorted(VIDEO_MIME_MAP)}."
    )


def _read_media_b64(file_path: Path) -> str:
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


# --- Main API interface --------------------------------------------------

class GeminiTranscribeAPI:
    """
    Sends a single audio/video file to Gemini's multimodal generate_content
    endpoint as an inlineData Part and returns the transcript text, with the
    same verbatim/diarization/segment prompt modes and domain-terminology
    cleanup as the React Audio Transcriber tool.

    For files too large for a single inline request, see
    transcribe_long_media() below, which chunks via ffmpeg first.
    """

    def __init__(self, key_registry: GeminiKeyRegistry, model_registry: GeminiModelRegistry):
        self.keys = key_registry
        self.models = model_registry
        if genai is None:
            logging.error("[GeminiTranscribeLib] google-genai SDK not installed. Run 'pip install google-genai'.")

    def transcribe(
        self,
        file_path: Union[str, Path],
        *,
        model_id: Optional[str] = None,
        mode: str = "verbatim",
        segment: bool = False,
        domain_context: bool = True,
        clean_domain_terms: bool = True,
        mime_type: Optional[str] = None,
        extra_instructions: Optional[str] = None,
    ) -> str:
        """
        Transcribes one audio/video file.

        file_path            -- Path to the media file.
        model_id              -- Model override; falls back to the active
                                  Gemini model (self.models.active_model_id).
        mode                  -- "verbatim" (default) or "diarization"
                                  (speaker tags + timestamps).
        segment               -- If True, asks Gemini to mark logical
                                  segments/chapters in the output.
        domain_context        -- If True (default), includes the BEJSON/
                                  BEHTML/MFDB terminology dictionary in the
                                  system prompt so those terms transcribe
                                  correctly the first time.
        clean_domain_terms    -- If True (default), runs
                                  clean_domain_terminology() on the response
                                  text as a second-pass correction.
        mime_type             -- Override the auto-detected mimeType.
        extra_instructions    -- Extra free-text appended to the prompt.

        Raises TranscribeMediaNotFoundError, TranscribeUnsupportedMediaError,
        TranscribeMediaTooLargeError, SDKNotInstalledError, NoAPIKeysError
        (fatal -- fix the input/environment and retry), or one of gemini.py's
        AIRecoverableError subclasses via _classify_generation_error()
        (transient -- may succeed on retry).
        """
        # Input validation first (file path, extension, size) -- these are
        # the most actionable errors and don't need the SDK or any key, so
        # a caller with no keys configured yet still gets a clear "file not
        # found" / "unsupported extension" instead of that being masked by
        # a NoAPIKeysError that has nothing to do with what they typed.
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise TranscribeMediaNotFoundError(f"Media file not found: {path}")

        resolved_mime = mime_type or detect_media_mime_type(path)

        file_size = path.stat().st_size
        if file_size > MAX_INLINE_BYTES:
            raise TranscribeMediaTooLargeError(
                f"{path.name} is {file_size / 1024 / 1024:.1f}MB, over the "
                f"{MAX_INLINE_BYTES / 1024 / 1024:.0f}MB single-request inline limit. "
                f"Use transcribe_long_media() to chunk it first."
            )

        if genai is None:
            raise SDKNotInstalledError("google-genai SDK not installed. Run 'pip install google-genai'.")
        if not self.keys.keys:
            raise NoAPIKeysError("No Gemini API keys found.")

        prompt = _build_system_prompt(mode, segment, domain_context, extra_instructions)
        key = self.keys.get_next_key() if hasattr(self.keys, "get_next_key") else None
        if key is None:
            import random
            key = random.choice(self.keys.keys)

        mid = model_id or self.models.active_model_id
        client = genai.Client(api_key=key)
        media_b64 = _read_media_b64(path)

        try:
            response = client.models.generate_content(
                model=mid,
                contents=[
                    types.Part.from_bytes(data=base64.b64decode(media_b64), mime_type=resolved_mime),
                    prompt,
                ],
            )
            text = response.text or ""
        except Exception as e:
            logger.error(f"[GeminiTranscribeLib] Transcription failed for {path.name}: {e}")
            raise _classify_generation_error(e)

        return clean_domain_terminology(text) if clean_domain_terms else text

    def transcribe_long_media(
        self,
        file_path: Union[str, Path],
        *,
        chunk_seconds: int = 600,
        keep_chunks: bool = False,
        **transcribe_kwargs: Any,
    ) -> str:
        """
        For media over MAX_INLINE_BYTES: splits the file into
        `chunk_seconds`-long, 16kHz mono WAV segments via ffmpeg (same
        downsample target the React tool's audioChunker.ts uses), transcribes
        each chunk with transcribe(), and joins the results with
        '--- Segment N of M ---' headers -- consistent with the segment-name
        pattern (`{base}_part{N}_of_{M}`) the React tool's
        parseSegmentInfo()/sortSegmentFiles() already recognize, so chunk
        output from this function is interchangeable with that tool's own
        segmenter if ever moved between them.

        Requires `ffmpeg` on PATH. Raises TranscribeChunkingUnavailableError
        if it isn't found, or TranscribeChunkingFailedError if ffmpeg exits
        non-zero. All other **transcribe_kwargs are passed through to
        transcribe() for every chunk.
        """
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            raise TranscribeChunkingUnavailableError(
                "ffmpeg not found on PATH. In Termux: pkg install ffmpeg."
            )

        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise TranscribeMediaNotFoundError(f"Media file not found: {path}")

        with tempfile.TemporaryDirectory(prefix="gemini_transcribe_chunks_") as tmp_str:
            tmp_dir = Path(tmp_str)
            pattern = tmp_dir / "chunk_%04d.wav"
            cmd = [
                ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "warning",
                "-i", str(path),
                "-ar", "16000", "-ac", "1",
                "-f", "segment", "-segment_time", str(chunk_seconds),
                str(pattern),
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0:
                raise TranscribeChunkingFailedError(f"ffmpeg chunking failed: {result.stderr}")

            chunk_files = sorted(tmp_dir.glob("chunk_*.wav"))
            if not chunk_files:
                raise TranscribeChunkingFailedError("ffmpeg produced no chunk files.")

            total = len(chunk_files)
            transcripts: List[str] = []
            persisted_paths: List[Path] = []

            for i, chunk_path in enumerate(chunk_files, start=1):
                if keep_chunks:
                    dest = path.parent / f"{path.stem}_part{i}_of_{total}.wav"
                    shutil.copy2(chunk_path, dest)
                    persisted_paths.append(dest)
                text = self.transcribe(chunk_path, mime_type="audio/wav", **transcribe_kwargs)
                transcripts.append(f"--- Segment {i} of {total} ---\n{text}")

            logger.info(
                f"[GeminiTranscribeLib] Transcribed {path.name} in {total} chunk(s) "
                f"of ~{chunk_seconds}s each."
                + (f" Chunks kept at: {[str(p) for p in persisted_paths]}" if keep_chunks else "")
            )
            return "\n\n".join(transcripts)


# --- Global Standard Access (mirrors gemini.py's get_standard_api()) -----
# Deliberately reuses gemini.py's own STD_KEY_PATH / STD_MODEL_PATH files --
# text generation and transcription share the same key pool and model
# lineup, so there is exactly one gemini_keys.104a.bejson and one
# gemini_model_registry.104a.bejson on disk, not two.

_std_transcribe_api_singleton: Optional["GeminiTranscribeAPI"] = None


def get_standard_transcribe_api() -> "GeminiTranscribeAPI":
    """Zero-config GeminiTranscribeAPI, built from gemini.py's standard key/
    model registry paths. Cached after first call."""
    global _std_transcribe_api_singleton
    if _std_transcribe_api_singleton is None:
        key_reg = GeminiKeyRegistry(STD_KEY_PATH)
        model_reg = GeminiModelRegistry(STD_MODEL_PATH)
        _std_transcribe_api_singleton = GeminiTranscribeAPI(key_reg, model_reg)
    return _std_transcribe_api_singleton
