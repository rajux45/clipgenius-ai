from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Clip, User, Video
from ..schemas import ClipOut, ClipUpdateRequest
from ..services.storage import storage

router = APIRouter(prefix="/clips", tags=["clips"])


def _attach_urls(clip: Clip) -> ClipOut:
    out = ClipOut.model_validate(clip)
    # Build presigned/public URLs
    if clip.s3_key:
        out.s3_key = storage.public_url(clip.s3_key)
    if clip.thumbnail_s3_key:
        out.thumbnail_s3_key = storage.public_url(clip.thumbnail_s3_key)
    if clip.dubs:
        dubs_with_urls = {}
        for lang, info in clip.dubs.items():
            if isinstance(info, dict) and info.get("s3_key"):
                dubs_with_urls[lang] = {**info, "url": storage.public_url(info["s3_key"])}
            else:
                dubs_with_urls[lang] = info
        out.dubs = dubs_with_urls
    return out


@router.get("/by-video/{video_id}", response_model=list[ClipOut])
def list_clips_for_video(
    video_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[ClipOut]:
    video = db.get(Video, video_id)
    if not video or video.owner_id != current.id:
        raise HTTPException(status_code=404, detail="Video not found")
    clips = (
        db.execute(select(Clip).where(Clip.video_id == video_id).order_by(Clip.index.asc()))
        .scalars()
        .all()
    )
    return [_attach_urls(c) for c in clips]


@router.get("/{clip_id}", response_model=ClipOut)
def get_clip(
    clip_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> ClipOut:
    clip = db.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    video = db.get(Video, clip.video_id)
    if not video or video.owner_id != current.id:
        raise HTTPException(status_code=404, detail="Clip not found")
    return _attach_urls(clip)


@router.patch("/{clip_id}", response_model=ClipOut)
def update_clip(
    clip_id: uuid.UUID,
    req: ClipUpdateRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> ClipOut:
    clip = db.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    video = db.get(Video, clip.video_id)
    if not video or video.owner_id != current.id:
        raise HTTPException(status_code=404, detail="Clip not found")
    if req.title is not None:
        clip.title = req.title
    if req.hook is not None:
        clip.hook = req.hook
    if req.metadata_json is not None:
        clip.metadata_json = req.metadata_json
    db.add(clip)
    db.commit()
    db.refresh(clip)
    return _attach_urls(clip)
