"""OpenAI integration: Whisper transcription, GPT for translation/captions, TTS for dubbing."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import settings

log = logging.getLogger(__name__)


def _client() -> OpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")
    return OpenAI(api_key=settings.openai_api_key)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20))
def transcribe(audio_path: str | Path) -> dict:
    """Transcribe an audio/video file with Whisper. Returns
    {"language": "...", "segments": [{"start": float, "end": float, "text": str}, ...], "text": "..."}
    """
    audio_path = Path(audio_path)
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


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15))
def chat_json(system: str, user: str) -> dict:
    """Call chat completions and require a JSON response."""
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


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15))
def chat_text(system: str, user: str) -> str:
    resp = _client().chat.completions.create(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.4,
    )
    return (resp.choices[0].message.content or "").strip()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20))
def tts(text: str, output_path: str | Path, voice: str | None = None) -> str:
    """Synthesise speech to an MP3 file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with _client().audio.speech.with_streaming_response.create(
        model=settings.openai_tts_model,
        voice=voice or settings.openai_tts_voice,
        input=text,
    ) as resp:
        resp.stream_to_file(str(output_path))
    return str(output_path)


def translate(text: str, target_language: str) -> str:
    """Translate text into the target language code (e.g. 'es', 'hi', 'fr')."""
    if not text.strip():
        return ""
    return chat_text(
        system=(
            "You are a professional translator. Translate the user's text into the target language "
            "specified. Preserve meaning, tone, and pacing. Output ONLY the translated text — no "
            "preamble, no notes."
        ),
        user=f"Target language code: {target_language}\n\nText:\n{text}",
    )
