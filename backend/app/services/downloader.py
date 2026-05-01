"""Download a video from a URL using yt-dlp.

YouTube has aggressive bot detection that blocks datacenter IPs. To bypass it
in production we accept cookies via:

* ``YT_DLP_COOKIES_FILE`` — absolute path to a Netscape cookies.txt file.
* ``YT_DLP_COOKIES_TXT``  — full cookies.txt content as a string (set as a
  Render / Vercel secret). We materialise it to a temp file at runtime.

We also rotate through several player clients (``tv``, ``ios``, ``web_safari``)
which are less aggressively bot-checked than the default ``web`` client.
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

import yt_dlp

log = logging.getLogger(__name__)

_COOKIE_FILE_CACHE: str | None = None


def _materialise_cookie_file() -> str | None:
    """Return a path to a cookies file if one is configured, else None."""
    global _COOKIE_FILE_CACHE
    if _COOKIE_FILE_CACHE and Path(_COOKIE_FILE_CACHE).exists():
        return _COOKIE_FILE_CACHE

    explicit = os.environ.get("YT_DLP_COOKIES_FILE", "").strip()
    if explicit and Path(explicit).exists():
        _COOKIE_FILE_CACHE = explicit
        return _COOKIE_FILE_CACHE

    inline = os.environ.get("YT_DLP_COOKIES_TXT", "").strip()
    if inline:
        # Render injects multi-line secrets verbatim.
        tmp_dir = Path(tempfile.gettempdir()) / "clipgenius"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        path = tmp_dir / "yt_cookies.txt"
        path.write_text(inline if inline.endswith("\n") else inline + "\n")
        _COOKIE_FILE_CACHE = str(path)
        return _COOKIE_FILE_CACHE
    return None


def download_video(url: str, output_dir: str | Path, *, max_height: int = 720) -> tuple[str, dict]:
    """Returns (local_path, info)."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(output_dir / "%(id)s.%(ext)s")
    ydl_opts: dict = {
        "outtmpl": outtmpl,
        "format": f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "concurrent_fragment_downloads": 4,
        "extractor_args": {
            # 'tv' and 'ios' clients see less bot challenge than the default web one.
            "youtube": {"player_client": ["tv", "ios", "web_safari"]},
        },
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
        ),
    }
    cookie_path = _materialise_cookie_file()
    if cookie_path:
        ydl_opts["cookiefile"] = cookie_path
        log.info("yt-dlp using cookies from %s", cookie_path)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)
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
