from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.types import Uuid as UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class VideoStatus(str, enum.Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    SEGMENTING = "segmenting"
    GENERATING_CLIPS = "generating_clips"
    COMPLETED = "completed"
    FAILED = "failed"


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # "url" | "upload"
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    s3_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[VideoStatus] = mapped_column(
        Enum(VideoStatus, native_enum=False, length=32), default=VideoStatus.PENDING, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    transcript: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {segments: [...], language: "..."}
    languages: Mapped[list | None] = mapped_column(JSON, nullable=True)  # target dub langs e.g. ["es", "hi"]
    platforms: Mapped[list | None] = mapped_column(JSON, nullable=True)  # ["youtube", "instagram"]

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner = relationship("User", back_populates="videos")
    clips = relationship("Clip", back_populates="video", cascade="all, delete-orphan")
