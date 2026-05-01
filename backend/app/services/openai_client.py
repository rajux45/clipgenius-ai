"""AI integration facade.

Tries OpenAI first when an API key is configured, automatically falls back to
the free, no-key stack (faster-whisper / deep-translator / edge-tts /
heuristic metadata) on any failure — including quota errors. This means the
pipeline keeps working end-to-end with zero paid services.

Set ``USE_FREE_STACK=1`` to skip OpenAI entirely.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import settings
from . import free_stack

log = logging.getLogger(__name__)


def _force_free() -> bool:
    if os.environ.get("USE_FREE_STACK", "").strip() in {"1", "true", "yes"}:
        return True
    return not bool(settings.openai_api_key)


def _client():
    from openai import OpenAI  # noqa: WPS433 (deferred import, only when needed)

    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")
    return OpenAI(api_key=settings.openai_api_key)


def _is_quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "insufficient_quota" in msg
        or "exceeded your current quota" in msg
        or "rate_limit" in msg
        or "rate limit" in msg
    )


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------


def transcribe(audio_path: str | Path) -> dict:
    """Transcribe with OpenAI Whisper if available, else faster-whisper."""
    audio_path = Path(audio_path)
    if _force_free():
        log.info("Transcribing with faster-whisper (free stack)")
        return free_stack.transcribe(audio_path)
    try:
        return _openai_transcribe(audio_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("OpenAI transcribe failed (%s); falling back to faster-whisper", exc)
        return free_stack.transcribe(audio_path)


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=10))
def _openai_transcribe(audio_path: Path) -> dict:
    with open(audio_path, "rb") as f:
        resp = _client().audio.transcriptions.create(
            model=settings.openai_whisper_model,
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )
    data = resp.model_dump() if hasattr(resp, "model_dump") else resp
    segments = []
    for seg in data.get("segments", []) or []:
        segments.append(
            {
                "start": float(seg.get("start", 0.0)),
                "end": float(seg.get("end", 0.0)),
                "text": (seg.get("text") or "").strip(),
            }
        )
    return {
        "language": data.get("language", "en"),
        "text": data.get("text", ""),
        "segments": segments,
    }


# ---------------------------------------------------------------------------
# Chat (used for clip ranking + metadata polishing). Always optional — the
# segmenter and captioner already have heuristic fallbacks if {} is returned.
# ---------------------------------------------------------------------------


def chat_json(system: str, user: str) -> dict:
    if _force_free():
        return {}
    try:
        return _openai_chat_json(system, user)
    except Exception as exc:  # noqa: BLE001
        log.warning("OpenAI chat_json failed (%s); skipping LLM polish", exc)
        return {}


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=10))
def _openai_chat_json(system: str, user: str) -> dict:
    resp = _client().chat.completions.create(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.4,
    )
    content = resp.choices[0].message.content or "{}"
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        log.warning("Non-JSON response from chat: %s", content[:200])
        return {}


def chat_text(system: str, user: str) -> str:
    if _force_free():
        return ""
    try:
        return _openai_chat_text(system, user)
    except Exception as exc:  # noqa: BLE001
        log.warning("OpenAI chat_text failed (%s)", exc)
        return ""


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=10))
def _openai_chat_text(system: str, user: str) -> str:
    resp = _client().chat.completions.create(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.4,
    )
    return (resp.choices[0].message.content or "").strip()


# ---------------------------------------------------------------------------
# Translation (for dubbing)
# ---------------------------------------------------------------------------


def translate(text: str, target_language: str) -> str:
    """Translate text into the target language code (e.g. 'es', 'hi', 'fr')."""
    if not text.strip():
        return ""
    if _force_free():
        return free_stack.translate(text, target_language)
    try:
        out = _openai_chat_text(
            system=(
                "You are a professional translator. Translate the user's text into the target language "
                "specified. Preserve meaning, tone, and pacing. Output ONLY the translated text — no "
                "preamble, no notes."
            ),
            user=f"Target language code: {target_language}\n\nText:\n{text}",
        )
        if out.strip():
            return out
        raise RuntimeError("empty translation from OpenAI")
    except Exception as exc:  # noqa: BLE001
        log.warning("OpenAI translate failed (%s); falling back to deep-translator", exc)
        return free_stack.translate(text, target_language)


# ---------------------------------------------------------------------------
# TTS (for dubbing)
# ---------------------------------------------------------------------------


def tts(text: str, output_path: str | Path, voice: str | None = None, language: str = "en") -> str:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if _force_free():
        return free_stack.tts(text, output_path, language=language)
    try:
        return _openai_tts(text, output_path, voice=voice)
    except Exception as exc:  # noqa: BLE001
        log.warning("OpenAI tts failed (%s); falling back to edge-tts", exc)
        return free_stack.tts(text, output_path, language=language)


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=10))
def _openai_tts(text: str, output_path: Path, voice: str | None = None) -> str:
    with _client().audio.speech.with_streaming_response.create(
        model=settings.openai_tts_model,
        voice=voice or settings.openai_tts_voice,
        input=text,
    ) as resp:
        resp.stream_to_file(str(output_path))
    return str(output_path)
