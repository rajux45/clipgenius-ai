"""Identify viral moments in a video using transcript + audio energy heuristics + LLM ranking.

Inputs:  transcript dict from openai_client.transcribe(), local audio path.
Outputs: list of clip windows: [{start, end, score, transcript, hook, title}, ...]
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import settings
from . import openai_client

log = logging.getLogger(__name__)


@dataclass
class CandidateWindow:
    start: float
    end: float
    text: str
    energy_score: float = 0.0
    keyword_score: float = 0.0
    pause_score: float = 0.0


# Words that often correlate with engaging moments. Used as a heuristic boost only.
VIRAL_KEYWORDS = {
    "secret",
    "never",
    "always",
    "best",
    "worst",
    "trick",
    "hack",
    "warning",
    "shocking",
    "amazing",
    "incredible",
    "biggest",
    "fastest",
    "free",
    "money",
    "rich",
    "love",
    "hate",
    "stop",
    "start",
    "truth",
    "lie",
    "prove",
    "instantly",
    "guarantee",
    "viral",
    "famous",
    "poor",
    "win",
    "lose",
    "wow",
    "crazy",
    "wild",
    "must",
    "should",
    "will",
    "you",
    "your",
}


def _audio_rms(audio_path: str | Path, hop_seconds: float = 0.5) -> tuple[np.ndarray, float]:
    """Return per-hop RMS energy values and the hop size in seconds.

    Uses ffmpeg to extract mono PCM samples without requiring librosa.
    """
    import subprocess

    # 16 kHz mono PCM little-endian floats
    sr = 16000
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(audio_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sr),
        "-f",
        "f32le",
        "pipe:1",
    ]
    try:
        out = subprocess.run(cmd, check=True, capture_output=True).stdout
    except subprocess.CalledProcessError as exc:
        log.warning("ffmpeg RMS extraction failed: %s", exc)
        return np.zeros(1, dtype=np.float32), hop_seconds
    samples = np.frombuffer(out, dtype=np.float32)
    if samples.size == 0:
        return np.zeros(1, dtype=np.float32), hop_seconds
    hop = max(1, int(sr * hop_seconds))
    n_hops = math.ceil(samples.size / hop)
    pad = n_hops * hop - samples.size
    if pad:
        samples = np.concatenate([samples, np.zeros(pad, dtype=np.float32)])
    blocks = samples.reshape(n_hops, hop)
    rms = np.sqrt((blocks**2).mean(axis=1) + 1e-9)
    return rms.astype(np.float32), hop_seconds


def _normalise(arr: np.ndarray) -> np.ndarray:
    if arr.size == 0:
        return arr
    lo, hi = float(arr.min()), float(arr.max())
    if hi - lo < 1e-9:
        return np.zeros_like(arr)
    return (arr - lo) / (hi - lo)


def _build_windows(
    segments: list[dict],
    target_min: float,
    target_max: float,
) -> list[CandidateWindow]:
    """Greedy sliding window over transcript segments to build candidate clip ranges."""
    windows: list[CandidateWindow] = []
    n = len(segments)
    for i in range(n):
        start = float(segments[i]["start"])
        text_parts: list[str] = []
        for j in range(i, n):
            end = float(segments[j]["end"])
            text_parts.append(segments[j]["text"])
            duration = end - start
            if duration < target_min:
                continue
            if duration > target_max:
                break
            windows.append(CandidateWindow(start=start, end=end, text=" ".join(text_parts).strip()))
            break
    return windows


def _score_keywords(text: str) -> float:
    if not text:
        return 0.0
    words = [w.strip(".,!?;:'\"").lower() for w in text.split()]
    if not words:
        return 0.0
    hits = sum(1 for w in words if w in VIRAL_KEYWORDS)
    return min(1.0, hits / max(8, len(words) / 6))


def _score_energy(rms: np.ndarray, hop: float, start: float, end: float) -> float:
    if rms.size == 0:
        return 0.0
    a = max(0, int(start / hop))
    b = min(rms.size, int(end / hop))
    if b <= a:
        return 0.0
    window_mean = float(rms[a:b].mean())
    overall = float(rms.mean()) + 1e-6
    # Ratio above mean, clamped
    return float(min(1.0, max(0.0, (window_mean / overall - 0.5))))


def _score_pause(segments: list[dict], start: float, end: float) -> float:
    """Look for a meaningful pause just before the window — often signals a punchline / hook."""
    pauses = []
    last_end = 0.0
    for s in segments:
        if s["start"] > start:
            break
        gap = max(0.0, float(s["start"]) - last_end)
        pauses.append(gap)
        last_end = float(s["end"])
    if not pauses:
        return 0.0
    return float(min(1.0, max(pauses[-3:]) / 1.2))  # 1.2s pause -> max score


def _rank_with_llm(
    windows: list[CandidateWindow], wanted: int, video_title: str | None
) -> list[dict]:
    """Ask GPT to pick the most viral windows and write a hook/title for each."""
    if not windows:
        return []
    payload = [
        {
            "id": idx,
            "start": round(w.start, 2),
            "end": round(w.end, 2),
            "text": w.text[:1200],
            "scores": {
                "energy": round(w.energy_score, 3),
                "keywords": round(w.keyword_score, 3),
                "pause": round(w.pause_score, 3),
            },
        }
        for idx, w in enumerate(windows)
    ]
    system = (
        "You curate viral short-form video clips. Given candidate windows from a long-form video "
        "with timing, transcript snippets, and heuristic scores, pick the strongest clips for "
        "YouTube Shorts / Instagram Reels. For each pick, write a punchy hook (<=80 chars) that "
        "would make a viewer stop scrolling, and a short title (<=60 chars). "
        "Respond as JSON: {\"clips\": [{\"id\": int, \"title\": str, \"hook\": str, \"score\": float}]}."
    )
    user = json.dumps(
        {
            "video_title": video_title or "Untitled",
            "wanted_count": wanted,
            "candidates": payload,
        }
    )
    try:
        result = openai_client.chat_json(system, user)
    except Exception as exc:  # noqa: BLE001
        log.warning("LLM ranking failed, falling back to heuristic ranking: %s", exc)
        result = {}

    picks_raw = result.get("clips") or []
    selected: list[dict] = []
    seen_ids: set[int] = set()
    for entry in picks_raw:
        try:
            idx = int(entry["id"])
        except (KeyError, TypeError, ValueError):
            continue
        if idx in seen_ids or idx < 0 or idx >= len(windows):
            continue
        seen_ids.add(idx)
        w = windows[idx]
        selected.append(
            {
                "start": w.start,
                "end": w.end,
                "transcript": w.text,
                "title": (entry.get("title") or "Untitled clip")[:120],
                "hook": (entry.get("hook") or "")[:200],
                "score": float(entry.get("score") or (w.energy_score + w.keyword_score + w.pause_score)),
            }
        )

    if len(selected) < wanted:
        # Fill with top heuristic windows not already selected
        ranked = sorted(
            (
                (i, w.energy_score + w.keyword_score + w.pause_score, w)
                for i, w in enumerate(windows)
                if i not in seen_ids
            ),
            key=lambda t: t[1],
            reverse=True,
        )
        for _i, score, w in ranked:
            if len(selected) >= wanted:
                break
            selected.append(
                {
                    "start": w.start,
                    "end": w.end,
                    "transcript": w.text,
                    "title": (w.text.split(".")[0] or "Highlight")[:120],
                    "hook": "",
                    "score": float(score),
                }
            )
    return selected[:wanted]


def select_viral_moments(
    transcript: dict,
    audio_path: str | Path | None,
    *,
    wanted: int | None = None,
    video_title: str | None = None,
    min_duration: float | None = None,
    max_duration: float | None = None,
) -> list[dict]:
    wanted = wanted or settings.clips_per_video
    min_duration = float(min_duration or settings.clip_min_duration)
    max_duration = float(max_duration or settings.clip_max_duration)

    segments = transcript.get("segments") or []
    if not segments:
        return []

    windows = _build_windows(segments, min_duration, max_duration)
    if not windows:
        return []

    rms, hop = (np.zeros(1, dtype=np.float32), 0.5)
    if audio_path is not None:
        rms, hop = _audio_rms(audio_path)
        rms = _normalise(rms)

    for w in windows:
        w.energy_score = _score_energy(rms, hop, w.start, w.end) if rms.size else 0.0
        w.keyword_score = _score_keywords(w.text)
        w.pause_score = _score_pause(segments, w.start, w.end)

    # Take top-K candidates by heuristic before sending to LLM (cap context)
    windows.sort(key=lambda w: w.energy_score + w.keyword_score + w.pause_score, reverse=True)
    top_pool = windows[: max(wanted * 4, 12)]
    return _rank_with_llm(top_pool, wanted, video_title)
