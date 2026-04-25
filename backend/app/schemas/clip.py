from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from ..models.clip import ClipStatus


class ClipOut(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    index: int
    title: str
    hook: str | None
    start_seconds: float
    end_seconds: float
    duration_seconds: float | None
    score: float
    transcript: str | None
    s3_key: str | None
    thumbnail_s3_key: str | None
    dubs: dict | None
    metadata_json: dict | None
    status: ClipStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class ClipUpdateRequest(BaseModel):
    title: str | None = None
    hook: str | None = None
    metadata_json: dict | None = None
