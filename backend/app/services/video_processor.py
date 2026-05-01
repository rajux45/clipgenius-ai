"""FFmpeg/OpenCV based video processing: cutting, vertical reframe with face tracking,
burned-in dynamic captions, thumbnail extraction, audio dubbing mux."""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import cv2

log = logging.getLogger(__name__)

# 9:16 vertical render size. On tiny dynos (Render free, 0.1 vCPU / 512 MB)
# encoding 1080x1920 takes 30-60x realtime; rendering at 720x1280 cuts that
# roughly 4x and is still well above what Reels/Shorts compress down to.
# Override via VIDEO_RENDER_HEIGHT env var (e.g. 1920 on real hardware).
VERTICAL_H = int(os.environ.get("VIDEO_RENDER_HEIGHT", "1280")) & ~1
VERTICAL_W = int(round(VERTICAL_H * 9 / 16)) & ~1  # libx264 needs even dims

# x264 preset; ultrafast is ~5x faster than veryfast at slightly lower quality.
FFMPEG_PRESET = os.environ.get("FFMPEG_PRESET", "ultrafast")
FFMPEG_THREADS = os.environ.get("FFMPEG_THREADS", "1")


def _run(cmd: list[str]) -> None:
    log.debug("Running: %s", " ".join(cmd))
    res = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd)}\nSTDERR: {res.stderr[-2000:]}")


def probe(path: str | Path) -> dict:
    res = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(res.stdout)


def get_duration(path: str | Path) -> float:
    info = probe(path)
    return float(info["format"]["duration"])


def cut_segment(input_path: str | Path, output_path: str | Path, start: float, end: float) -> str:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.1, end - start)
    _run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(input_path),
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            FFMPEG_PRESET,
            "-crf",
            "23",
            "-threads",
            FFMPEG_THREADS,
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    return str(output_path)


# --- Vertical reframe with face tracking ---


@dataclass
class FaceTrack:
    times: list[float]  # seconds
    centers_x: list[float]  # 0..1 fraction of frame width


def _detect_face_track(video_path: str | Path, sample_fps: float = 2.0) -> FaceTrack:
    if os.environ.get("DISABLE_FACE_TRACKING", "").strip() in {"1", "true", "yes"}:
        return FaceTrack([], [])
    sample_fps = float(os.environ.get("FACE_TRACK_SAMPLE_FPS", str(sample_fps)))
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return FaceTrack([], [])
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920)
    step = max(1, int(round(src_fps / sample_fps)))

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(cascade_path)

    times: list[float] = []
    xs: list[float] = []
    last_x = 0.5
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % step == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(80, 80))
            if len(faces) > 0:
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                cx = (x + w / 2) / width
                last_x = float(cx)
            times.append(frame_idx / src_fps)
            xs.append(last_x)
        frame_idx += 1
        if total and frame_idx >= total:
            break
    cap.release()
    if not times:
        return FaceTrack([], [])
    return FaceTrack(times=times, centers_x=_smooth(xs))


def _smooth(values: list[float], window: int = 5) -> list[float]:
    if not values:
        return values
    out = []
    for i in range(len(values)):
        lo = max(0, i - window // 2)
        hi = min(len(values), i + window // 2 + 1)
        out.append(sum(values[lo:hi]) / (hi - lo))
    return out


def reframe_vertical(input_path: str | Path, output_path: str | Path) -> str:
    """Convert a horizontal video to 9:16 (1080x1920) using face-aware center cropping.

    Strategy: detect dominant face center per ~0.5s, build a per-second crop expression
    using a stepwise function in ffmpeg. Falls back to center crop if no faces found.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    info = probe(input_path)
    vstream = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    if not vstream:
        raise RuntimeError("No video stream found")
    src_w = int(vstream["width"])
    src_h = int(vstream["height"])

    # Target: scale so height = 1920 maintaining aspect, then crop horizontally to 1080
    scaled_w = int(round(src_w * (VERTICAL_H / src_h)))
    crop_w = VERTICAL_W

    track = _detect_face_track(input_path)

    if track.times and scaled_w > crop_w:
        # Build per-time x-offset expression. ffmpeg supports `if(lt(t,T),A,B)` ladders.
        # To keep the ladder small, downsample track to ~1 sample per second.
        keyed: list[tuple[float, float]] = []
        last_t = -1.0
        for t, fx in zip(track.times, track.centers_x, strict=False):
            if t - last_t >= 1.0:
                keyed.append((t, fx))
                last_t = t
        if not keyed:
            keyed = [(0.0, track.centers_x[0])]
        # Target center x in scaled frame = fx * scaled_w; offset = clamp(center - crop_w/2, 0, scaled_w-crop_w)
        max_off = scaled_w - crop_w
        offsets = [(t, max(0, min(max_off, int(fx * scaled_w - crop_w / 2)))) for t, fx in keyed]
        # Build ladder: if(lt(t,t1),o0, if(lt(t,t2),o1, ...))
        # Each offset is active until the NEXT keyframe's time, so pair offset
        # at index i with the timestamp at i+1 as the lt() threshold.
        expr = str(offsets[-1][1])
        for i in range(len(offsets) - 2, -1, -1):
            t_next = offsets[i + 1][0]
            off = offsets[i][1]
            expr = f"if(lt(t,{t_next:.2f}),{off},{expr})"
        crop_expr = expr
    else:
        crop_expr = str(max(0, (scaled_w - crop_w) // 2))

    # Commas inside the crop x-expression must be escaped or ffmpeg will treat
    # them as filter-chain separators. Using \\, escapes them in argv form.
    safe_expr = crop_expr.replace(",", "\\,")
    vf = (
        f"scale=-2:{VERTICAL_H},"
        f"crop={VERTICAL_W}:{VERTICAL_H}:{safe_expr}:0,"
        "setsar=1"
    )
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            FFMPEG_PRESET,
            "-crf",
            "23",
            "-threads",
            FFMPEG_THREADS,
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    return str(output_path)


# --- Captions ---


def _format_ass_time(t: float) -> str:
    if t < 0:
        t = 0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _split_caption_lines(text: str, max_chars_per_line: int = 18, max_lines: int = 2) -> list[str]:
    """Split text into ~max_chars_per_line chunks of `max_lines` lines per cue."""
    words = text.split()
    cues: list[str] = []
    current_lines: list[str] = []
    current_line = ""
    for w in words:
        candidate = (current_line + " " + w).strip()
        if len(candidate) <= max_chars_per_line:
            current_line = candidate
        else:
            current_lines.append(current_line)
            current_line = w
            if len(current_lines) >= max_lines:
                cues.append("\\N".join(current_lines))
                current_lines = []
        if len(current_lines) == max_lines and current_line == "":
            cues.append("\\N".join(current_lines))
            current_lines = []
    if current_line:
        current_lines.append(current_line)
    if current_lines:
        cues.append("\\N".join(current_lines))
    return [c for c in cues if c]


def build_caption_ass(
    segments: Iterable[dict],
    *,
    width: int = VERTICAL_W,
    height: int = VERTICAL_H,
    highlight_words: set[str] | None = None,
) -> str:
    """Generate an .ass subtitle string with bold uppercase captions and yellow highlight on keywords."""
    style = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Inter,72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,4,2,2,40,40,200,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    highlight_words = {w.lower() for w in (highlight_words or set())}
    lines: list[str] = []
    for seg in segments:
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start + 1.5))
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        cues = _split_caption_lines(text.upper(), max_chars_per_line=18, max_lines=2)
        if not cues:
            continue
        per_cue = max(0.4, (end - start) / len(cues))
        for i, cue in enumerate(cues):
            cs = start + i * per_cue
            ce = min(end, cs + per_cue)
            # Highlight viral keywords with yellow inline tag
            words_out = []
            for word in cue.split():
                clean = word.strip(".,!?;:'\"\\N").lower()
                if clean in highlight_words:
                    words_out.append("{\\c&H00F2FF&}" + word + "{\\c&HFFFFFF&}")
                else:
                    words_out.append(word)
            text_out = " ".join(words_out)
            lines.append(
                f"Dialogue: 0,{_format_ass_time(cs)},{_format_ass_time(ce)},Default,,0,0,0,,{text_out}"
            )
    return style + "\n".join(lines) + "\n"


def burn_captions(input_path: str | Path, output_path: str | Path, ass_path: str | Path) -> str:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # ffmpeg subtitles filter requires escaped path on some systems
    ass_path_str = str(ass_path).replace(":", "\\:").replace(",", "\\,")
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-vf",
            f"subtitles='{ass_path_str}'",
            "-c:v",
            "libx264",
            "-preset",
            FFMPEG_PRESET,
            "-crf",
            "23",
            "-threads",
            FFMPEG_THREADS,
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    return str(output_path)


def extract_thumbnail(input_path: str | Path, output_path: str | Path, at: float = 1.0) -> str:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{at:.2f}",
            "-i",
            str(input_path),
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(output_path),
        ]
    )
    return str(output_path)


def replace_audio(
    video_path: str | Path,
    audio_path: str | Path,
    output_path: str | Path,
    *,
    keep_original_volume: float = 0.0,
    dub_volume: float = 1.0,
) -> str:
    """Replace (or mix) the video's audio track with a new dubbed audio track.

    keep_original_volume in [0,1] keeps a fraction of the original audio (e.g. 0.1 for ambient bg).
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if keep_original_volume <= 0:
        _run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(audio_path),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-shortest",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )
    else:
        filter_graph = (
            f"[0:a]volume={keep_original_volume}[a0];"
            f"[1:a]volume={dub_volume}[a1];"
            "[a0][a1]amix=inputs=2:duration=longest:dropout_transition=0[aout]"
        )
        _run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(audio_path),
                "-filter_complex",
                filter_graph,
                "-map",
                "0:v:0",
                "-map",
                "[aout]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )
    return str(output_path)


def workdir() -> Path:
    d = Path(tempfile.mkdtemp(prefix="clipgenius_"))
    return d


def cleanup_dir(path: str | Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
