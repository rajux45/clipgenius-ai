"""Heuristic per-platform metadata generator that doesn't need an LLM.

Used as a fallback when no GPT key is available so the pipeline still produces
sensible captions, hashtags, and titles.
"""
from __future__ import annotations

import re

# Reasonable evergreen hashtags per platform — ensures content is at least
# discoverable. Per-clip keywords are appended on top.
PLATFORM_BASE_TAGS = {
    "youtube": ["shorts", "viral", "trending", "explained", "shortvideo"],
    "instagram": ["reels", "viral", "trending", "explore", "reelsinstagram"],
}


_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "to", "of",
    "in", "on", "at", "for", "with", "and", "or", "but", "if", "then", "so",
    "this", "that", "these", "those", "it", "its", "as", "you", "your",
    "i", "we", "our", "us", "they", "them", "their", "he", "she", "his",
    "her", "him", "do", "does", "did", "have", "has", "had", "not", "no",
    "yes", "very", "just", "really", "more", "most", "some", "any", "all",
    "about", "up", "down", "out", "into", "than", "from", "by", "will",
    "would", "could", "should", "can", "may",
}


def _keywords(text: str, *, limit: int = 5) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z'-]{2,}", text.lower())
    counts: dict[str, int] = {}
    for w in words:
        if w in _STOPWORDS:
            continue
        counts[w] = counts.get(w, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return [w for w, _ in ranked[:limit]]


def _slugify_tag(word: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]", "", word.lower())
    return cleaned


def _truncate(text: str, max_len: int) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def generate_metadata(
    *,
    platforms: list[str],
    clip_transcript: str,
    clip_hook: str | None = None,
    clip_title: str | None = None,
    language: str = "en",  # noqa: ARG001 — kept for API parity
) -> dict:
    """Return per-platform metadata derived purely from the transcript text."""
    transcript = (clip_transcript or "").strip()
    hook = (clip_hook or "").strip() or _first_sentence(transcript)
    title = (clip_title or "").strip() or hook or "Highlight"
    keywords = _keywords(transcript or hook or title)
    out: dict[str, dict] = {}

    for p in platforms:
        base_tags = PLATFORM_BASE_TAGS.get(p, [])
        per_clip_tags = [_slugify_tag(w) for w in keywords if _slugify_tag(w)]
        all_tags = list(dict.fromkeys(per_clip_tags + base_tags))  # dedupe, preserve order
        hashtag_block = " ".join(f"#{t}" for t in all_tags[:12] if t)

        if p == "youtube":
            yt_title = _truncate(title or hook or "Watch this short", 80)
            description_parts = []
            if hook:
                description_parts.append(hook)
            if transcript and transcript != hook:
                description_parts.append(transcript)
            description_parts.append(hashtag_block)
            description = "\n\n".join(part for part in description_parts if part)
            out["youtube"] = {
                "title": yt_title,
                "description": _truncate(description, 4500),
                "tags": all_tags[:15],
                "hashtags": [f"#{t}" for t in all_tags[:5] if t],
            }
        elif p == "instagram":
            caption_parts = []
            if hook:
                caption_parts.append(hook)
            if transcript and transcript != hook:
                caption_parts.append(_truncate(transcript, 1800))
            caption_parts.append(hashtag_block)
            caption = "\n\n".join(part for part in caption_parts if part)
            out["instagram"] = {
                "caption": _truncate(caption, 2200),
                "hashtags": [f"#{t}" for t in all_tags[:15] if t],
            }
        else:
            out[p] = {
                "title": _truncate(title, 80),
                "description": _truncate(transcript, 1500),
                "hashtags": [f"#{t}" for t in all_tags[:10] if t],
            }
    return out


def _first_sentence(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    match = re.search(r"[.!?]\s", text)
    if match:
        return text[: match.start() + 1].strip()
    return text[:120]
