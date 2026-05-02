"""Regression tests for SRT formatting and karaoke caption building."""
from __future__ import annotations

import re

from app.services.video_processor import build_karaoke_ass, segments_to_srt

SRT_TIMESTAMP = re.compile(r"^(\d{2}):(\d{2}):(\d{2}),(\d{3})$")


def _assert_valid_srt_timestamps(srt: str) -> None:
    for line in srt.splitlines():
        if "-->" not in line:
            continue
        start, end = [p.strip() for p in line.split("-->")]
        for stamp in (start, end):
            match = SRT_TIMESTAMP.match(stamp)
            assert match, f"malformed SRT timestamp: {stamp!r}"
            hh, mm, ss, ms = (int(g) for g in match.groups())
            assert hh < 100
            assert mm < 60, f"minutes >= 60 in {stamp!r}"
            assert ss < 60, f"seconds >= 60 in {stamp!r}"
            assert ms < 1000, f"ms >= 1000 in {stamp!r}"


def test_srt_edge_rounding_does_not_produce_sixty_seconds() -> None:
    # 59.9996 used to render as "00:00:60,000" because the old formatter
    # incremented seconds without carrying into minutes. Check both a clean
    # minute boundary and an hour boundary.
    segments = [
        {"start": 0.0, "end": 59.9996, "text": "edge case near minute"},
        {"start": 59.9999, "end": 3599.9999, "text": "edge case near hour"},
    ]
    srt = segments_to_srt(segments)
    _assert_valid_srt_timestamps(srt)
    # The 59.9996 case should carry to "00:01:00,000"
    assert "00:01:00,000" in srt
    # The 3599.9999 case should carry to "01:00:00,000"
    assert "01:00:00,000" in srt


def test_srt_negative_start_is_clamped_to_zero() -> None:
    srt = segments_to_srt([{"start": -0.01, "end": 1.5, "text": "hi"}])
    assert "00:00:00,000 --> 00:00:01,500" in srt


def test_karaoke_ass_emits_per_word_dialogues() -> None:
    segments = [
        {
            "start": 0.0,
            "end": 2.0,
            "text": "Hello world now",
            "words": [
                {"start": 0.0, "end": 0.5, "word": "Hello"},
                {"start": 0.6, "end": 1.2, "word": "world"},
                {"start": 1.3, "end": 2.0, "word": "now"},
            ],
        }
    ]
    ass = build_karaoke_ass(segments, max_words_per_cue=3)
    dialogues = [ln for ln in ass.splitlines() if ln.startswith("Dialogue:")]
    # One dialogue line per word because each word gets its own active window.
    assert len(dialogues) == 3
    # Each dialogue line should contain the highlight color tag exactly once.
    for line in dialogues:
        assert line.count("{\\c&H00F2FF&}") == 1


def test_karaoke_ass_falls_back_to_block_when_no_words() -> None:
    segments = [{"start": 0.0, "end": 2.0, "text": "no word timing here"}]
    ass = build_karaoke_ass(segments)
    # Falls through to block renderer — still produces at least one Dialogue line.
    assert "Dialogue:" in ass
