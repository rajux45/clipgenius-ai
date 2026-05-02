"""End-to-end video processing pipeline as Celery tasks."""
from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Clip, ClipStatus, Video, VideoStatus
from ..services import (
    captioner,
    downloader,
    lipsync,
    openai_client,
    presets,
    segmenter,
    storage,
    video_processor,
)
from ..services.segmenter import VIRAL_KEYWORDS
from ..services.storage import storage as default_storage
from .celery_app import celery_app

log = logging.getLogger(__name__)


def _set_video_status(db: Session, video: Video, status: VideoStatus, error: str | None = None) -> None:
    video.status = status
    if error:
        video.error_message = error
    db.add(video)
    db.commit()


@celery_app.task(name="app.tasks.video_tasks.process_video", bind=True, max_retries=2)
def process_video(self, video_id: str) -> dict:  # noqa: PLR0915
    """Full pipeline: download/fetch -> transcribe -> segment -> render clips -> dub -> caption -> store."""
    db = SessionLocal()
    workdir = video_processor.workdir()
    try:
        video = db.get(Video, uuid.UUID(video_id))
        if not video:
            raise RuntimeError(f"Video {video_id} not found")

        # 1) Acquire local copy
        _set_video_status(db, video, VideoStatus.DOWNLOADING)
        local_input = workdir / "input.mp4"
        if video.source_type == "url" and video.source_url:
            log.info("Downloading %s", video.source_url)
            local_input_str, info = downloader.download_video(video.source_url, workdir)
            local_input = Path(local_input_str)
            if not video.title or video.title == "Untitled":
                video.title = info.get("title") or video.title
            video.duration_seconds = info.get("duration")
            video.width = info.get("width")
            video.height = info.get("height")
        elif video.source_type == "upload" and video.s3_key:
            default_storage.download_file(video.s3_key, local_input)
        else:
            raise RuntimeError("Video has no usable source (url or s3_key)")

        if not video.duration_seconds:
            try:
                video.duration_seconds = video_processor.get_duration(local_input)
            except Exception:  # noqa: BLE001
                pass

        # If we downloaded from URL, also persist the source file to storage so dubbing tasks can re-fetch
        if not video.s3_key:
            key = storage.StorageBackend.random_key("videos/source", suffix=".mp4")
            default_storage.upload_file(local_input, key, content_type="video/mp4")
            video.s3_key = key

        db.add(video)
        db.commit()

        # 2) Transcribe
        _set_video_status(db, video, VideoStatus.TRANSCRIBING)
        log.info("Transcribing %s", local_input)
        transcript = openai_client.transcribe(local_input)
        video.transcript = transcript
        db.add(video)
        db.commit()

        # 3) Segment / select viral moments
        _set_video_status(db, video, VideoStatus.SEGMENTING)
        target_languages = video.languages or ["en"]
        target_platforms = video.platforms or ["youtube"]
        preset = presets.resolve(target_platforms)
        log.info(
            "Using platform preset %s (max_duration=%ds, karaoke=%s)",
            preset.name,
            preset.max_duration_seconds,
            preset.prefers_karaoke,
        )
        moments = segmenter.select_viral_moments(
            transcript,
            audio_path=local_input,
            wanted=8,
            video_title=video.title,
            max_duration=preset.max_duration_seconds,
            min_duration=preset.min_duration_seconds,
        )
        if not moments:
            raise RuntimeError("No viable clip moments found in transcript")

        # 4) Render clips: cut -> silence-cut -> vertical reframe -> burn captions -> upload
        _set_video_status(db, video, VideoStatus.GENERATING_CLIPS)

        for idx, moment in enumerate(moments):
            clip_row = Clip(
                video_id=video.id,
                index=idx,
                title=moment["title"],
                hook=moment.get("hook"),
                start_seconds=moment["start"],
                end_seconds=moment["end"],
                duration_seconds=moment["end"] - moment["start"],
                score=moment.get("score", 0.0),
                transcript=moment.get("transcript"),
                status=ClipStatus.RENDERING,
            )
            db.add(clip_row)
            db.commit()
            db.refresh(clip_row)
            try:
                clip_dir = workdir / f"clip_{idx}"
                clip_dir.mkdir(exist_ok=True)
                cut_path = clip_dir / "cut.mp4"
                vert_path = clip_dir / "vertical.mp4"
                captioned_path = clip_dir / "captioned.mp4"
                final_path = clip_dir / "final.mp4"
                ass_path = clip_dir / "captions.ass"
                srt_path = clip_dir / "captions.srt"
                thumb_path = clip_dir / "thumb.jpg"

                video_processor.cut_segment(local_input, cut_path, moment["start"], moment["end"])
                # Reframe on the raw cut so the caption timestamps (which come
                # from the original transcript timeline) stay in sync. Silence
                # trimming happens AFTER captions are burned so the subtitle
                # pixels travel with their frames (fixes Devin Review BUG_0001:
                # captions were desynced when silences were removed first).
                video_processor.reframe_vertical(cut_path, vert_path)

                # Build clip-relative segments (with word timestamps when
                # available) for karaoke caption rendering. If a word's times
                # fall outside the clip window, drop it; otherwise shift by
                # the moment start.
                clip_segments: list[dict] = []
                for s in transcript.get("segments", []):
                    s_start = float(s["start"])
                    s_end = float(s["end"])
                    if s_end <= moment["start"] or s_start >= moment["end"]:
                        continue
                    local_words: list[dict] = []
                    for w in s.get("words") or []:
                        ws = float(w.get("start", s_start))
                        we = float(w.get("end", s_end))
                        if we <= moment["start"] or ws >= moment["end"]:
                            continue
                        local_words.append(
                            {
                                "start": max(0.0, ws - moment["start"]),
                                "end": max(0.1, we - moment["start"]),
                                "word": w.get("word", ""),
                            }
                        )
                    entry: dict = {
                        "start": max(0.0, s_start - moment["start"]),
                        "end": max(0.1, s_end - moment["start"]),
                        "text": s["text"],
                    }
                    if local_words:
                        entry["words"] = local_words
                    clip_segments.append(entry)

                if preset.prefers_karaoke and any(cs.get("words") for cs in clip_segments):
                    ass_text = video_processor.build_karaoke_ass(clip_segments)
                else:
                    ass_text = video_processor.build_caption_ass(
                        clip_segments,
                        highlight_words=VIRAL_KEYWORDS,
                    )
                ass_path.write_text(ass_text, encoding="utf-8")
                # Also emit a plain SRT alongside the clip so users can
                # re-use the transcript in Premiere / Davinci / etc.
                srt_path.write_text(
                    video_processor.segments_to_srt(clip_segments), encoding="utf-8"
                )
                # Burn captions onto the original-timeline reframed video
                # first, THEN run silence trimming. Because trim_silences cuts
                # both audio and video together, the burned subtitle pixels
                # travel with their frames and stay in sync with speech.
                video_processor.burn_captions(vert_path, captioned_path, ass_path)
                try:
                    video_processor.trim_silences(
                        captioned_path,
                        final_path,
                        min_silence_sec=0.7,
                        pad_sec=0.1,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning("silence-cut failed (%s); using captioned clip as-is", exc)
                    shutil.copy2(captioned_path, final_path)
                video_processor.extract_thumbnail(final_path, thumb_path, at=0.5)

                # Upload final + thumbnail + srt
                final_key = f"videos/{video.id}/clips/{clip_row.id}.mp4"
                thumb_key = f"videos/{video.id}/clips/{clip_row.id}.jpg"
                srt_key = f"videos/{video.id}/clips/{clip_row.id}.srt"
                default_storage.upload_file(final_path, final_key, content_type="video/mp4")
                default_storage.upload_file(thumb_path, thumb_key, content_type="image/jpeg")
                default_storage.upload_file(srt_path, srt_key, content_type="text/plain")

                # Per-platform metadata in primary language
                meta = captioner.generate_metadata(
                    platforms=target_platforms,
                    clip_transcript=clip_row.transcript or "",
                    clip_hook=clip_row.hook,
                    clip_title=clip_row.title,
                    language=target_languages[0],
                )

                # Dubs
                dubs: dict = {}
                for lang in target_languages:
                    if lang == "en":
                        dubs["en"] = {"s3_key": final_key}
                        continue
                    clip_row.status = ClipStatus.DUBBING
                    db.add(clip_row)
                    db.commit()
                    try:
                        translated = openai_client.translate(clip_row.transcript or "", lang)
                        dub_audio = clip_dir / f"dub_{lang}.mp3"
                        openai_client.tts(translated, dub_audio, language=lang)
                        dub_video = clip_dir / f"final_{lang}.mp4"
                        video_processor.replace_audio(
                            final_path, dub_audio, dub_video, keep_original_volume=0.05
                        )
                        # Optional lip-sync: only runs when USE_LIPSYNC=1 and a
                        # CUDA GPU is visible (e.g. HF Space upgraded to T4).
                        # On CPU-only free tier this short-circuits and we ship
                        # audio-only dubbing (which is production-standard).
                        dub_used_lipsync = False
                        if lipsync.is_enabled():
                            try:
                                lipsynced = clip_dir / f"final_{lang}_lipsync.mp4"
                                lipsync.apply_lipsync(dub_video, dub_audio, lipsynced)
                                dub_video = lipsynced
                                dub_used_lipsync = True
                                log.info("Lip-sync applied for clip=%s lang=%s", clip_row.id, lang)
                            except Exception as lip_exc:  # noqa: BLE001
                                log.warning(
                                    "Lip-sync failed for clip=%s lang=%s (%s); falling back to audio-only",
                                    clip_row.id,
                                    lang,
                                    lip_exc,
                                )
                        dub_key = f"videos/{video.id}/clips/{clip_row.id}_{lang}.mp4"
                        default_storage.upload_file(dub_video, dub_key, content_type="video/mp4")
                        dubs[lang] = {
                            "s3_key": dub_key,
                            "transcript": translated,
                            "lipsync": dub_used_lipsync,
                        }
                    except Exception as exc:  # noqa: BLE001
                        log.exception("Dub failed for %s lang=%s: %s", clip_row.id, lang, exc)
                        dubs[lang] = {"error": str(exc)}

                clip_row.s3_key = final_key
                clip_row.thumbnail_s3_key = thumb_key
                clip_row.dubs = dubs
                clip_row.metadata_json = meta
                clip_row.status = ClipStatus.READY
                db.add(clip_row)
                db.commit()
            except Exception as exc:  # noqa: BLE001
                log.exception("Clip %s failed: %s", clip_row.id, exc)
                clip_row.status = ClipStatus.FAILED
                clip_row.error_message = str(exc)[:1000]
                db.add(clip_row)
                db.commit()

        _set_video_status(db, video, VideoStatus.COMPLETED)
        return {"video_id": str(video.id), "clips": len(moments)}
    except Exception as exc:  # noqa: BLE001
        log.exception("process_video failed: %s", exc)
        try:
            video = db.get(Video, uuid.UUID(video_id))
            if video:
                _set_video_status(db, video, VideoStatus.FAILED, error=str(exc)[:1500])
        finally:
            pass
        raise
    finally:
        db.close()
        video_processor.cleanup_dir(workdir)
