"""Smoke tests for caption generator path handling without calling OpenAI."""
from __future__ import annotations

from app.services import video_processor


def test_split_caption_lines_short_text():
    cues = video_processor._split_caption_lines("HELLO WORLD")
    assert cues == ["HELLO WORLD"]


def test_split_caption_lines_wraps_long_text():
    text = "this is a much longer string of caption text that must wrap into multiple lines"
    cues = video_processor._split_caption_lines(text.upper(), max_chars_per_line=18, max_lines=2)
    assert len(cues) >= 2
    for cue in cues:
        for line in cue.split("\\N"):
            assert len(line) <= 22  # small slack for word boundaries


def test_format_ass_time():
    assert video_processor._format_ass_time(0) == "0:00:00.00"
    assert video_processor._format_ass_time(125.5) == "0:02:05.50"
