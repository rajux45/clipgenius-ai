from __future__ import annotations

import io
import re
import tempfile
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Clip, User, Video, VideoStatus
from ..schemas import VideoCreateRequest, VideoListItem, VideoOut
from ..services.storage import storage
from ..tasks.video_tasks import process_video

router = APIRouter(prefix="/videos", tags=["videos"])


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str, ext: str) -> str:
    stem = _SAFE_NAME.sub("_", (name or "clip").strip())[:60] or "clip"
    if not ext.startswith("."):
        ext = "." + ext
    return f"{stem}{ext}"


@router.post("", response_model=VideoOut, status_code=status.HTTP_201_CREATED)
def create_video_from_url(
    req: VideoCreateRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> Video:
    if not req.source_url:
        raise HTTPException(status_code=400, detail="source_url required (or use /videos/upload)")
    video = Video(
        owner_id=current.id,
        title=req.title or "Untitled",
        source_type="url",
        source_url=str(req.source_url),
        languages=req.languages,
        platforms=req.platforms,
        status=VideoStatus.PENDING,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    process_video.delay(str(video.id))
    return video


@router.post("/upload", response_model=VideoOut, status_code=status.HTTP_201_CREATED)
def upload_video(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    languages: str = Form("en"),
    platforms: str = Form("youtube"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> Video:
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="File must be a video")
    key = storage.random_key(f"videos/uploads/{current.id}", suffix=".mp4")
    storage.upload_fileobj(file.file, key, content_type=file.content_type)

    video = Video(
        owner_id=current.id,
        title=title or file.filename or "Upload",
        source_type="upload",
        s3_key=key,
        languages=[s.strip() for s in languages.split(",") if s.strip()],
        platforms=[s.strip() for s in platforms.split(",") if s.strip()],
        status=VideoStatus.PENDING,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    process_video.delay(str(video.id))
    return video


@router.get("", response_model=list[VideoListItem])
def list_videos(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[VideoListItem]:
    rows = (
        db.execute(
            select(Video).where(Video.owner_id == current.id).order_by(Video.created_at.desc())
        )
        .scalars()
        .all()
    )
    out: list[VideoListItem] = []
    for v in rows:
        out.append(
            VideoListItem(
                id=v.id,
                title=v.title,
                status=v.status,
                source_type=v.source_type,
                duration_seconds=v.duration_seconds,
                languages=v.languages,
                platforms=v.platforms,
                created_at=v.created_at,
                clips_count=len(v.clips),
            )
        )
    return out


@router.get("/{video_id}", response_model=VideoOut)
def get_video(
    video_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> Video:
    video = db.get(Video, video_id)
    if not video or video.owner_id != current.id:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(
    video_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> None:
    video = db.get(Video, video_id)
    if not video or video.owner_id != current.id:
        raise HTTPException(status_code=404, detail="Video not found")
    db.delete(video)
    db.commit()


@router.get("/{video_id}/export.zip")
def export_video_zip(
    video_id: uuid.UUID,
    language: str | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> StreamingResponse:
    """Bundle all clips of a video (plus their SRT subtitles) into a zip.

    By default every language in ``clip.dubs`` is included (English + dubs).
    Pass ``?language=hi`` to only include a specific language.
    """
    video = db.get(Video, video_id)
    if not video or video.owner_id != current.id:
        raise HTTPException(status_code=404, detail="Video not found")
    clips: list[Clip] = (
        db.execute(select(Clip).where(Clip.video_id == video.id).order_by(Clip.index))
        .scalars()
        .all()
    )
    if not clips:
        raise HTTPException(status_code=404, detail="No clips to export yet")

    buffer = io.BytesIO()
    with tempfile.TemporaryDirectory() as tmpdir, zipfile.ZipFile(
        buffer, "w", compression=zipfile.ZIP_DEFLATED
    ) as zf:
        tmp = Path(tmpdir)
        for clip in clips:
            if not clip.s3_key:
                continue
            base_title = f"{clip.index + 1:02d}_{clip.title or 'clip'}"
            langs_to_include: list[tuple[str, str]] = []
            # Primary English clip is the clip.s3_key itself
            if not language or language == "en":
                langs_to_include.append(("en", clip.s3_key))
            for lang_code, dub_info in (clip.dubs or {}).items():
                if lang_code == "en":
                    continue
                if language and lang_code != language:
                    continue
                key = (dub_info or {}).get("s3_key")
                if key:
                    langs_to_include.append((lang_code, key))

            for lang_code, key in langs_to_include:
                mp4_dest = tmp / f"{clip.id}_{lang_code}.mp4"
                try:
                    storage.download_file(key, mp4_dest)
                except Exception:  # noqa: BLE001
                    continue
                zf.write(
                    mp4_dest,
                    arcname=_safe_filename(f"{base_title}_{lang_code}", ".mp4"),
                )

            # SRT — only one, since subtitles come from the source transcript
            srt_key = f"videos/{video.id}/clips/{clip.id}.srt"
            srt_dest = tmp / f"{clip.id}.srt"
            try:
                storage.download_file(srt_key, srt_dest)
                zf.write(srt_dest, arcname=_safe_filename(base_title, ".srt"))
            except Exception:  # noqa: BLE001
                # SRT is best-effort; older clips may not have one.
                pass

    buffer.seek(0)
    filename = _safe_filename(video.title or str(video.id), ".zip")
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
