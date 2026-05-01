from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.types import Uuid as UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class ClipStatus(str, enum.Enum):
    PENDING = "pending"
    RENDERING = "rendering"
    DUBBING = "dubbing"
    READY = "ready"
    FAILED = "failed"


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[uuid.UUID] = mapped_column(UUID(), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(), ForeignKey("videos.id", ondelete="CASCADE"), index=True
    )

    index: Mapped[int] = mapped_column(Integer, nullable=False)  # 0..N
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    hook: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)

    s3_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    thumbnail_s3_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Per-language renders: { "es": {"s3_key": "...", "audio_s3_key": "..."}, ... }
    dubs: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Per-platform metadata: { "youtube": {"title": "...", "description": "...", "tags": [...]}, ... }
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    status: Mapped[ClipStatus] = mapped_column(
        Enum(ClipStatus, native_enum=False, length=32), default=ClipStatus.PENDING, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    video = relationship("Video", back_populates="clips")
    scheduled_posts = relationship("ScheduledPost", back_populates="clip", cascade="all, delete-orphan")
