from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import User, Video, VideoStatus
from ..schemas import VideoCreateRequest, VideoListItem, VideoOut
from ..services.storage import storage
from ..tasks.video_tasks import process_video

router = APIRouter(prefix="/videos", tags=["videos"])


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
