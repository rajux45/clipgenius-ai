"""Platform presets for clip generation.

Each preset controls the hard upper bound on clip duration (post-silence-cut),
the caption style (word-level karaoke vs classic block), and the ideal aspect
ratio. The segmenter and video processor both consult these so switching
platforms on the upload form actually changes the pipeline output.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    key: str
    name: str
    max_duration_seconds: int
    min_duration_seconds: int
    prefers_karaoke: bool
    ideal_aspect: str  # "9:16" | "1:1" | "16:9"


PRESETS: dict[str, Preset] = {
    "youtube": Preset(
        key="youtube",
        name="YouTube Shorts",
        max_duration_seconds=60,
        min_duration_seconds=15,
        prefers_karaoke=True,
        ideal_aspect="9:16",
    ),
    "instagram": Preset(
        key="instagram",
        name="Instagram Reels",
        max_duration_seconds=90,
        min_duration_seconds=15,
        prefers_karaoke=True,
        ideal_aspect="9:16",
    ),
    "tiktok": Preset(
        key="tiktok",
        name="TikTok",
        max_duration_seconds=60,
        min_duration_seconds=15,
        prefers_karaoke=True,
        ideal_aspect="9:16",
    ),
}

DEFAULT_PRESET: Preset = PRESETS["youtube"]


def resolve(platforms: list[str] | None) -> Preset:
    """Pick the strictest preset for the given list of platform keys.

    Strictest == smallest ``max_duration_seconds`` so clips don't exceed the
    limit of any target. Empty / unknown input falls back to YouTube.
    """
    if not platforms:
        return DEFAULT_PRESET
    candidates: list[Preset] = []
    for p in platforms:
        preset = PRESETS.get((p or "").strip().lower())
        if preset:
            candidates.append(preset)
    if not candidates:
        return DEFAULT_PRESET
    candidates.sort(key=lambda p: p.max_duration_seconds)
    return candidates[0]
