from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from ..models.schedule import Platform, PostStatus


class SchedulePostRequest(BaseModel):
    clip_id: uuid.UUID
    platform: Platform
    language: str = "en"
    scheduled_at: datetime
    title: str | None = None
    caption: str | None = None
    hashtags: list[str] | None = None


class ScheduledPostOut(BaseModel):
    id: uuid.UUID
    clip_id: uuid.UUID
    platform: Platform
    language: str
    title: str | None
    caption: str | None
    hashtags: list[str] | None
    scheduled_at: datetime
    published_at: datetime | None
    status: PostStatus
    external_id: str | None
    external_url: str | None
    error_message: str | None
    analytics: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}
