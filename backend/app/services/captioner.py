"""Per-platform caption / metadata generator."""
from __future__ import annotations

import logging

from . import metadata_heuristic, openai_client

log = logging.getLogger(__name__)


PLATFORM_HINTS = {
    "youtube": (
        "YouTube Shorts: title <= 80 chars with a strong hook; description <= 1500 chars with 2-3 sentence "
        "summary plus a call-to-action; 5-10 SEO hashtags; tags as plain words. The first 3 hashtags appear "
        "above the title in YouTube search results."
    ),
    "instagram": (
        "Instagram Reels: caption <= 2200 chars but keep the hook in the first 125 chars; punchy, "
        "conversational, emoji-friendly; 8-15 hashtags blended into a final block; no link in the body."
    ),
}


def generate_metadata(
    *,
    platforms: list[str],
    clip_transcript: str,
    clip_hook: str | None = None,
    clip_title: str | None = None,
    language: str = "en",
) -> dict:
    """Returns {platform: {"title": str, "description"|"caption": str, "tags"|"hashtags": [...]}}"""
    if not platforms:
        return {}
    system = (
        "You write social-media metadata for short vertical video clips. Output JSON only. "
        "Keys correspond exactly to the platforms requested. Each value must contain platform-appropriate "
        "fields. Use the target language code provided. Never add extra commentary."
    )
    hints = "\n".join(f"- {p}: {PLATFORM_HINTS.get(p, '')}" for p in platforms)
    schema = (
        "Return JSON like {"
        + ", ".join(
            (
                '"youtube": {"title": str, "description": str, "tags": [str], "hashtags": [str]}'
                if p == "youtube"
                else '"instagram": {"caption": str, "hashtags": [str]}'
            )
            for p in platforms
        )
        + "}."
    )
    user = (
        f"Language: {language}\n"
        f"Clip title (draft): {clip_title or ''}\n"
        f"Clip hook (draft): {clip_hook or ''}\n"
        f"Clip transcript:\n{clip_transcript[:3000]}\n\n"
        f"Platform rules:\n{hints}\n\n{schema}"
    )
    try:
        result = openai_client.chat_json(system, user)
    except Exception as exc:  # noqa: BLE001
        log.warning("LLM metadata failed (%s); using heuristic generator", exc)
        result = {}
    if not result:
        result = metadata_heuristic.generate_metadata(
            platforms=platforms,
            clip_transcript=clip_transcript,
            clip_hook=clip_hook,
            clip_title=clip_title,
            language=language,
        )
    return result
