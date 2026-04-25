"""Download a video from a URL using yt-dlp."""
from __future__ import annotations

import logging
from pathlib import Path

import yt_dlp

log = logging.getLogger(__name__)


def download_video(url: str, output_dir: str | Path, *, max_height: int = 1080) -> tuple[str, dict]:
    """Returns (local_path, info)."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(output_dir / "%(id)s.%(ext)s")
    ydl_opts = {
        "outtmpl": outtmpl,
        "format": f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "concurrent_fragment_downloads": 4,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)
        # If merge_output_format kicked in, the actual file has .mp4 extension
        p = Path(path)
        if not p.exists():
            mp4 = p.with_suffix(".mp4")
            if mp4.exists():
                p = mp4
        return str(p), {
            "title": info.get("title"),
            "duration": info.get("duration"),
            "width": info.get("width"),
            "height": info.get("height"),
            "uploader": info.get("uploader"),
            "id": info.get("id"),
        }
