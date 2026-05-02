"""Free, no-API-key alternatives for transcription, translation, and TTS.

These are used as fallbacks when OpenAI is unavailable (no key / quota
exhausted) or when ``USE_FREE_STACK=1`` is set in the environment.

* Transcription: ``faster-whisper`` (CTranslate2) — small CPU-friendly model.
* Translation:  ``deep-translator`` (free Google Translate endpoint).
* TTS:          ``edge-tts`` (Microsoft Edge text-to-speech).
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Whisper (faster-whisper)
# ---------------------------------------------------------------------------

_WHISPER_MODEL: Any | None = None


def _load_whisper() -> Any:
    """Lazy-load faster-whisper. Free tier RAM is tight, so only load on demand."""
    global _WHISPER_MODEL
    if _WHISPER_MODEL is not None:
        return _WHISPER_MODEL
    from faster_whisper import WhisperModel  # noqa: WPS433 (deferred import)

    model_size = os.environ.get("WHISPER_LOCAL_MODEL", "tiny")
    compute_type = os.environ.get("WHISPER_LOCAL_COMPUTE_TYPE", "int8")
    log.info("Loading faster-whisper model=%s compute=%s", model_size, compute_type)
    _WHISPER_MODEL = WhisperModel(model_size, device="cpu", compute_type=compute_type)
    return _WHISPER_MODEL


def transcribe(audio_path: str | Path) -> dict:
    """Transcribe audio using faster-whisper. Returns the same shape as the
    OpenAI Whisper wrapper so callers don't care which backend ran.

    When ``WHISPER_WORD_TIMESTAMPS`` is enabled (default), each segment also
    gets a ``words`` list with per-word ``(start, end, word)`` used by the
    karaoke-caption renderer.
    """
    model = _load_whisper()
    want_words = os.environ.get("WHISPER_WORD_TIMESTAMPS", "1").strip() in {"1", "true", "yes"}
    segments_iter, info = model.transcribe(
        str(audio_path),
        beam_size=1,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        word_timestamps=want_words,
    )
    segments: list[dict] = []
    text_parts: list[str] = []
    for seg in segments_iter:
        text = (seg.text or "").strip()
        if not text:
            continue
        words: list[dict] = []
        for w in getattr(seg, "words", None) or []:
            w_text = (getattr(w, "word", "") or "").strip()
            if not w_text:
                continue
            words.append(
                {
                    "start": float(getattr(w, "start", seg.start) or seg.start),
                    "end": float(getattr(w, "end", seg.end) or seg.end),
                    "word": w_text,
                }
            )
        entry = {"start": float(seg.start), "end": float(seg.end), "text": text}
        if words:
            entry["words"] = words
        segments.append(entry)
        text_parts.append(text)
    return {
        "language": info.language or "en",
        "text": " ".join(text_parts),
        "segments": segments,
    }


# ---------------------------------------------------------------------------
# Translation (deep-translator)
# ---------------------------------------------------------------------------


def translate(text: str, target_language: str, source_language: str = "auto") -> str:
    if not text.strip():
        return ""
    target = target_language.split("-")[0].lower()
    source = source_language.split("-")[0].lower() if source_language else "auto"
    if source != "auto" and source == target:
        return text
    from deep_translator import GoogleTranslator  # noqa: WPS433 (deferred import)

    try:
        # The free endpoint chokes on >5k chars, so chunk by sentence boundary.
        chunks = _split_into_chunks(text, max_chars=4500)
        out = []
        for chunk in chunks:
            out.append(GoogleTranslator(source=source, target=target).translate(chunk))
        return " ".join(p for p in out if p)
    except Exception as exc:  # noqa: BLE001
        log.warning("deep-translator failed (%s); returning original text", exc)
        return text


def _split_into_chunks(text: str, *, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    out: list[str] = []
    cursor = 0
    while cursor < len(text):
        end = min(cursor + max_chars, len(text))
        if end < len(text):
            # try to break on sentence boundary
            boundary = max(
                text.rfind(". ", cursor, end),
                text.rfind("! ", cursor, end),
                text.rfind("? ", cursor, end),
                text.rfind("\n", cursor, end),
            )
            if boundary > cursor + 200:
                end = boundary + 1
        out.append(text[cursor:end].strip())
        cursor = end
    return out


# ---------------------------------------------------------------------------
# TTS (edge-tts)
# ---------------------------------------------------------------------------


# A minimal, well-tested voice per language. Edge has hundreds, this is just
# the default — power users can override via ``EDGE_TTS_VOICE_<LANG>`` env vars.
EDGE_VOICES = {
    "en": "en-US-AriaNeural",
    "es": "es-ES-ElviraNeural",
    "hi": "hi-IN-SwaraNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "pt": "pt-BR-FranciscaNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "ar": "ar-SA-ZariyahNeural",
    "id": "id-ID-GadisNeural",
    "it": "it-IT-ElsaNeural",
    "nl": "nl-NL-ColetteNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "tr": "tr-TR-EmelNeural",
    "vi": "vi-VN-HoaiMyNeural",
    "th": "th-TH-PremwadeeNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
}


def _voice_for(language: str) -> str:
    code = language.split("-")[0].lower()
    override = os.environ.get(f"EDGE_TTS_VOICE_{code.upper()}")
    if override:
        return override
    return EDGE_VOICES.get(code, EDGE_VOICES["en"])


async def _edge_save(text: str, output_path: str, voice: str) -> None:
    import edge_tts  # noqa: WPS433 (deferred import)

    communicate = edge_tts.Communicate(text=text, voice=voice)
    await communicate.save(output_path)


def tts(text: str, output_path: str | Path, voice: str | None = None, language: str = "en") -> str:
    """Synthesise speech to an MP3 file using free Microsoft Edge TTS."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    chosen_voice = voice or _voice_for(language)
    log.info("edge-tts synthesising (%s, voice=%s, %d chars)", language, chosen_voice, len(text))
    _run_async(_edge_save(text, str(output_path), chosen_voice))
    return str(output_path)


def _run_async(coro: Any) -> None:
    """Run an async coroutine to completion from sync code, even if a loop is
    already running on the current thread (e.g. inside an async FastAPI route
    that calls into the OpenAI facade and falls back to the free stack)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None or not loop.is_running():
        asyncio.run(coro)
        return
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(asyncio.run, coro).result()
