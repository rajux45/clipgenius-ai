"""Unit tests for clip segmentation heuristics that don't need OpenAI."""
from __future__ import annotations

from app.services import segmenter


def test_build_windows_basic():
    segments = [
        {"start": 0.0, "end": 5.0, "text": "Hello world this is segment one"},
        {"start": 5.0, "end": 12.0, "text": "Now we have the second segment talking"},
        {"start": 12.0, "end": 25.0, "text": "And the third segment goes longer"},
        {"start": 25.0, "end": 40.0, "text": "Final segment for the test"},
    ]
    windows = segmenter._build_windows(segments, 15.0, 30.0)
    assert windows, "Should produce at least one viable window"
    for w in windows:
        assert 15.0 <= (w.end - w.start) <= 30.0


def test_score_keywords_detects_viral_words():
    score = segmenter._score_keywords("This is the secret hack that will make you rich")
    assert score > 0


def test_score_keywords_zero_for_neutral_text():
    score = segmenter._score_keywords("today the weather is mild and the sky is clear above us")
    assert score == 0.0
