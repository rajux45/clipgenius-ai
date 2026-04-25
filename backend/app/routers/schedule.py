from __future__ import annotations

import uuid
from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Clip, PostStatus, ScheduledPost, User, Video
from ..schemas import ScheduledPostOut, SchedulePostRequest

router = APIRouter(prefix="/posts", tags=["posts"])


@router.post("", response_model=ScheduledPostOut, status_code=status.HTTP_201_CREATED)
def schedule_post(
    req: SchedulePostRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> ScheduledPost:
    clip = db.get(Clip, req.clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    video = db.get(Video, clip.video_id)
    if not video or video.owner_id != current.id:
        raise HTTPException(status_code=404, detail="Clip not found")

    sched_at = req.scheduled_at
    if sched_at.tzinfo is None:
        sched_at = sched_at.replace(tzinfo=UTC)

    post = ScheduledPost(
        clip_id=clip.id,
        platform=req.platform,
        language=req.language,
        title=req.title or clip.title,
        caption=req.caption or clip.hook,
        hashtags=req.hashtags or [],
        scheduled_at=sched_at,
        status=PostStatus.SCHEDULED,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


@router.get("", response_model=list[ScheduledPostOut])
def list_posts(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[ScheduledPost]:
    rows = (
        db.execute(
            select(ScheduledPost)
            .join(Clip, Clip.id == ScheduledPost.clip_id)
            .join(Video, Video.id == Clip.video_id)
            .where(Video.owner_id == current.id)
            .order_by(ScheduledPost.scheduled_at.desc())
        )
        .scalars()
        .all()
    )
    return rows


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_post(
    post_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> None:
    post = db.get(ScheduledPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    clip = db.get(Clip, post.clip_id)
    video = db.get(Video, clip.video_id) if clip else None
    if not video or video.owner_id != current.id:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.status not in {PostStatus.SCHEDULED, PostStatus.FAILED}:
        raise HTTPException(status_code=400, detail="Cannot cancel a published post")
    post.status = PostStatus.CANCELED
    db.add(post)
    db.commit()
