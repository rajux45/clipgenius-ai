from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

from ..models.video import VideoStatus


class VideoCreateRequest(BaseModel):
    title: str | None = None
    source_url: HttpUrl | None = None
    languages: list[str] = Field(default_factory=lambda: ["en"])
    platforms: list[Literal["youtube", "instagram"]] = Field(default_factory=lambda: ["youtube"])
    clips_count: int = Field(default=8, ge=1, le=20)


class VideoListItem(BaseModel):
    id: uuid.UUID
    title: str
    status: VideoStatus
    source_type: str
    duration_seconds: float | None
    languages: list[str] | None = None
    platforms: list[str] | None = None
    created_at: datetime
    clips_count: int = 0

    model_config = {"from_attributes": True}


class VideoOut(BaseModel):
    id: uuid.UUID
    title: str
    status: VideoStatus
    source_type: str
    source_url: str | None
    s3_key: str | None
    duration_seconds: float | None
    languages: list[str] | None
    platforms: list[str] | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
