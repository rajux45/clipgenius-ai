"""Scheduled posting + analytics refresh tasks."""
from __future__ import annotations

import logging
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from ..database import SessionLocal
from ..models import (
    Clip,
    OAuthAccount,
    Platform,
    PostStatus,
    ScheduledPost,
    Video,
)
from ..services import instagram as ig_service
from ..services import youtube as yt_service
from ..services.storage import storage as default_storage
from .celery_app import celery_app

log = logging.getLogger(__name__)


def _account_for(db, user_id: uuid.UUID, provider: str) -> OAuthAccount | None:
    return db.scalar(
        select(OAuthAccount).where(OAuthAccount.user_id == user_id, OAuthAccount.provider == provider)
    )


def _account_dict(acc: OAuthAccount) -> dict:
    return {
        "access_token": acc.access_token,
        "refresh_token": acc.refresh_token,
        "expires_at": acc.expires_at,
        "scope": acc.scope,
        "extra": acc.extra,
    }


@celery_app.task(name="app.tasks.posting_tasks.publish_due_posts")
def publish_due_posts() -> int:
    db = SessionLocal()
    count = 0
    try:
        now = datetime.now(UTC)
        due = (
            db.execute(
                select(ScheduledPost).where(
                    ScheduledPost.status == PostStatus.SCHEDULED,
                    ScheduledPost.scheduled_at <= now,
                )
            )
            .scalars()
            .all()
        )
        for post in due:
            try:
                publish_post.delay(str(post.id))
                count += 1
            except Exception as exc:  # noqa: BLE001
                log.exception("Failed to enqueue post %s: %s", post.id, exc)
        return count
    finally:
        db.close()


@celery_app.task(name="app.tasks.posting_tasks.publish_post", bind=True, max_retries=2)
def publish_post(self, post_id: str) -> dict:
    db = SessionLocal()
    try:
        post = db.get(ScheduledPost, uuid.UUID(post_id))
        if not post:
            raise RuntimeError("Post not found")
        if post.status not in {PostStatus.SCHEDULED, PostStatus.FAILED}:
            return {"status": post.status.value}
        post.status = PostStatus.PUBLISHING
        db.add(post)
        db.commit()

        clip = db.get(Clip, post.clip_id)
        if not clip or clip.s3_key is None:
            raise RuntimeError("Clip not ready")
        video = db.get(Video, clip.video_id)
        owner_id = video.owner_id

        # Pick the right key (dubbed if requested language)
        s3_key = clip.s3_key
        if post.language and post.language != "en" and clip.dubs and clip.dubs.get(post.language):
            s3_key = clip.dubs[post.language].get("s3_key") or s3_key

        title = post.title or clip.title
        caption = post.caption or clip.hook or clip.title
        hashtags = post.hashtags or []

        if post.platform == Platform.YOUTUBE:
            account = _account_for(db, owner_id, "youtube")
            if not account:
                raise RuntimeError("YouTube account not connected")
            with tempfile.TemporaryDirectory() as tmp:
                local = Path(tmp) / "clip.mp4"
                default_storage.download_file(s3_key, local)
                desc = caption + ("\n\n" + " ".join(f"#{h.lstrip('#')}" for h in hashtags) if hashtags else "")
                result = yt_service.upload_short(
                    _account_dict(account),
                    local,
                    title=title,
                    description=desc,
                    tags=[h.lstrip("#") for h in hashtags][:20],
                )
        elif post.platform == Platform.INSTAGRAM:
            account = _account_for(db, owner_id, "instagram")
            if not account:
                raise RuntimeError("Instagram account not connected")
            url = default_storage.public_url(s3_key)
            cap = caption + ("\n\n" + " ".join(f"#{h.lstrip('#')}" for h in hashtags) if hashtags else "")
            result = ig_service.publish_reel(_account_dict(account), video_url=url, caption=cap)
        else:
            raise RuntimeError(f"Unsupported platform: {post.platform}")

        post.external_id = result.get("id")
        post.external_url = result.get("url")
        post.status = PostStatus.PUBLISHED
        post.published_at = datetime.now(UTC)
        db.add(post)
        db.commit()
        return {"id": post.external_id, "url": post.external_url}
    except Exception as exc:  # noqa: BLE001
        log.exception("publish_post failed: %s", exc)
        post = db.get(ScheduledPost, uuid.UUID(post_id))
        if post:
            post.status = PostStatus.FAILED
            post.error_message = str(exc)[:1500]
            db.add(post)
            db.commit()
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.posting_tasks.refresh_analytics")
def refresh_analytics() -> int:
    db = SessionLocal()
    updated = 0
    try:
        cutoff = datetime.now(UTC) - timedelta(days=30)
        posts = (
            db.execute(
                select(ScheduledPost).where(
                    ScheduledPost.status == PostStatus.PUBLISHED,
                    ScheduledPost.external_id.is_not(None),
                    ScheduledPost.published_at >= cutoff,
                )
            )
            .scalars()
            .all()
        )
        for post in posts:
            try:
                clip = db.get(Clip, post.clip_id)
                video = db.get(Video, clip.video_id) if clip else None
                if not video:
                    continue
                if post.platform == Platform.YOUTUBE:
                    account = _account_for(db, video.owner_id, "youtube")
                    if not account:
                        continue
                    stats = yt_service.video_stats(_account_dict(account), post.external_id)
                else:
                    account = _account_for(db, video.owner_id, "instagram")
                    if not account:
                        continue
                    stats = ig_service.media_insights(_account_dict(account), post.external_id)
                if stats:
                    post.analytics = stats
                    post.analytics_updated_at = datetime.now(UTC)
                    db.add(post)
                    updated += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("Analytics refresh failed for %s: %s", post.id, exc)
        db.commit()
        return updated
    finally:
        db.close()
