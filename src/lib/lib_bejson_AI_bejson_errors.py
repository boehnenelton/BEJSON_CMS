"""
Library:         lib_bejson_AI_bejson_errors.py
Family:          New
Module Purpose:  Error registry for the AI family. Created as part of the library-wide "each family owns its own error codes" pass. Add new E_AI_* constants here as they're introduced; do not define family error codes anywhere else.
Architecture:    BEJSON 104 Ecosystem Component maintaining strict schema integrity, field map caching, and standardized runtime contracts.
Version:         1.4.0
Release_Version: 300
Date:            2026-09-05
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   0d7f3b52-8e4a-4c19-b6d3-5a2f9c8e1b74
"""

VERSION = "1.4.0"

# ---------------------------------------------------------------------------
# AI (200-219) — Interactions API (lib_bejson_AI_bejson_interactions.py)
# ---------------------------------------------------------------------------
E_AI_NO_API_KEYS                     = 200
E_AI_INTERACTIONS_HTTP_ERROR         = 201
E_AI_INTERACTIONS_TIMEOUT            = 202
E_AI_INTERACTIONS_MAX_ROUNDS_EXCEEDED = 203
E_AI_INTERACTIONS_MISSING_TOOL_EXECUTOR = 204
E_AI_INTERACTIONS_INVALID_ATTACHMENT = 205

# ---------------------------------------------------------------------------
# AI (206-219) — Fatal/Recoverable exception hierarchy, applied first to
# lib_bejson_AI_bejson_gemini.py (2.4.0). Pattern taken directly from
# NewAgent's lib_bejson_newagent_errors.py: a fatal tier for conditions
# nothing can succeed against without fixing (no keys, SDK missing) vs a
# recoverable tier for single-call failures that may not recur (rate limit,
# network blip, bad key, provider-side error). Reuses E_AI_NO_API_KEYS above
# for NoAPIKeysError rather than allocating a second code for the same
# meaning.
# ---------------------------------------------------------------------------
E_AI_SDK_NOT_INSTALLED               = 211
E_AI_RATE_LIMITED                    = 212
E_AI_NETWORK_ERROR                   = 213
E_AI_AUTH_ERROR                      = 214
E_AI_PROVIDER_SERVER_ERROR           = 215
E_AI_GENERATION_FAILED               = 216

# ---------------------------------------------------------------------------
# AI (220-224) — Transcription (lib_bejson_AI_bejson_gemini_transcribe.py).
# media-not-found/unsupported-media are treated as fatal for the call chain
# (an input problem that retrying won't fix without the caller changing the
# path or extension); media-too-large and the chunking errors relate to the
# ffmpeg-based transcribe_long_media() path.
# ---------------------------------------------------------------------------
E_AI_TRANSCRIBE_MEDIA_NOT_FOUND       = 220
E_AI_TRANSCRIBE_UNSUPPORTED_MEDIA     = 221
E_AI_TRANSCRIBE_MEDIA_TOO_LARGE       = 222
E_AI_TRANSCRIBE_CHUNKING_UNAVAILABLE  = 223
E_AI_TRANSCRIBE_CHUNKING_FAILED       = 224

# ---------------------------------------------------------------------------
# AI (230-235) — Text-to-Speech (lib_bejson_AI_bejson_gemini_tts.py).
# Invalid-voice / multi-speaker-limit / unsupported-capability are input
# problems (fatal for that call -- fix the request and retry, same
# reasoning as the transcribe family's not-found/unsupported codes above).
# HTTP/timeout/no-audio-returned are transient provider-side conditions
# (retrying may succeed), same reasoning as the 211-216 recoverable tier.
# ---------------------------------------------------------------------------
E_AI_TTS_HTTP_ERROR                   = 230
E_AI_TTS_TIMEOUT                      = 231
E_AI_TTS_NO_AUDIO_RETURNED            = 232
E_AI_TTS_INVALID_VOICE                = 233
E_AI_TTS_MULTI_SPEAKER_LIMIT_EXCEEDED = 234
E_AI_TTS_UNSUPPORTED_CAPABILITY       = 235


class AIException(Exception):
    """Base for every AI-family structured error. error_code follows the
    numeric registry in this file -- do not allocate a family error code
    anywhere else."""
    error_code: int = 0

    def __init__(self, message: str, *, error_code: int = 0) -> None:
        super().__init__(message)
        self.error_code = error_code or self.error_code


class AIFatalError(AIException):
    """Unrecoverable for this call chain -- nothing can succeed without
    fixing the underlying condition (missing SDK, no keys configured).
    A caller looping over turns/retries should stop and surface this
    clearly rather than keep retrying."""


class NoAPIKeysError(AIFatalError):
    error_code = E_AI_NO_API_KEYS


class SDKNotInstalledError(AIFatalError):
    error_code = E_AI_SDK_NOT_INSTALLED


class AIRecoverableError(AIException):
    """A single call failed but the condition may not recur -- transient
    network blip, a rate limit that will clear, a provider-side hiccup, or
    one bad key in a multi-key rotation. A caller can retry this turn or
    the next one; this is NOT a reason to stop the whole session. (If the
    same recoverable error keeps recurring, that's a job for a
    caller-side circuit breaker, same as NewAgent's agent.py loop -- this
    file only classifies the error, it doesn't count repetitions.)"""


class RateLimitedError(AIRecoverableError):
    error_code = E_AI_RATE_LIMITED


class NetworkError(AIRecoverableError):
    error_code = E_AI_NETWORK_ERROR


class AuthError(AIRecoverableError):
    """Bad/expired/revoked key. Recoverable, not fatal, because a
    multi-key rotation may have other working keys -- same reasoning
    NewAgent's loop uses (an auth error on one call doesn't mean every
    future call will also fail)."""
    error_code = E_AI_AUTH_ERROR


class ProviderServerError(AIRecoverableError):
    error_code = E_AI_PROVIDER_SERVER_ERROR


class GenerationError(AIRecoverableError):
    """Generic fallback when a generation failure doesn't match one of the
    more specific recoverable categories above."""
    error_code = E_AI_GENERATION_FAILED


class TranscribeMediaNotFoundError(AIFatalError):
    """The given media path doesn't exist or isn't a file. Fatal for this
    call chain -- retrying without the caller fixing the path won't help."""
    error_code = E_AI_TRANSCRIBE_MEDIA_NOT_FOUND


class TranscribeUnsupportedMediaError(AIFatalError):
    """The file extension isn't in the known audio/video mime-type tables.
    Fatal for this call chain -- same file will fail every retry until the
    caller supplies mime_type explicitly or converts the file."""
    error_code = E_AI_TRANSCRIBE_UNSUPPORTED_MEDIA


class TranscribeMediaTooLargeError(AIFatalError):
    """The file exceeds the single-request inline-data size limit. Fatal
    for GeminiTranscribeAPI.transcribe() -- use transcribe_long_media()
    (ffmpeg chunking) instead."""
    error_code = E_AI_TRANSCRIBE_MEDIA_TOO_LARGE


class TranscribeChunkingUnavailableError(AIFatalError):
    """ffmpeg isn't installed / not on PATH. Fatal until the environment is
    fixed (e.g. `pkg install ffmpeg` on Termux)."""
    error_code = E_AI_TRANSCRIBE_CHUNKING_UNAVAILABLE


class TranscribeChunkingFailedError(AIRecoverableError):
    """ffmpeg ran but exited non-zero or produced no chunks. Recoverable --
    a corrupt/truncated source file or a bad segment_time may not recur on
    a different file or setting."""
    error_code = E_AI_TRANSCRIBE_CHUNKING_FAILED


class TTSHTTPError(AIRecoverableError):
    """Interactions API returned a non-2xx status for a TTS request.
    Recoverable -- a provider-side hiccup on one call, same as
    ProviderServerError above."""
    error_code = E_AI_TTS_HTTP_ERROR


class TTSTimeoutError(AIRecoverableError):
    """TTS request exceeded its timeout. Recoverable -- retry the call."""
    error_code = E_AI_TTS_TIMEOUT


class TTSNoAudioReturnedError(AIRecoverableError):
    """The model returned text tokens instead of audio, or no output_audio
    field at all. Recoverable -- Google's own docs note this occurs
    randomly in a small percentage of TTS calls; retry logic is the
    documented mitigation, not a sign the request itself was wrong."""
    error_code = E_AI_TTS_NO_AUDIO_RETURNED


class TTSInvalidVoiceError(AIFatalError):
    """Requested voice name isn't in the documented voice catalog. Fatal
    for this call chain -- retrying without fixing the voice name won't
    help."""
    error_code = E_AI_TTS_INVALID_VOICE


class TTSMultiSpeakerLimitExceededError(AIFatalError):
    """More than 2 speaker_voice_config entries were supplied. Fatal --
    the API supports at most 2 speakers per multi-speaker request."""
    error_code = E_AI_TTS_MULTI_SPEAKER_LIMIT_EXCEEDED


class TTSUnsupportedCapabilityError(AIFatalError):
    """Requested a capability (streaming, multi-speaker) the target
    model_id's registry entry doesn't mark as supported. Fatal for this
    call chain until the caller picks a different model_id."""
    error_code = E_AI_TTS_UNSUPPORTED_CAPABILITY