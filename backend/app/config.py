"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # Core
    app_name: str = "ClipGenius AI"
    environment: str = Field(default="development")
    debug: bool = False
    api_prefix: str = "/api/v1"
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"

    # Auth
    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Database
    database_url: str = "postgresql+psycopg2://clipgenius:clipgenius@localhost:5432/clipgenius"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    # AWS S3
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_region: str = "us-east-1"
    aws_s3_bucket: str | None = None
    s3_public_base_url: str | None = None  # e.g. https://cdn.example.com

    # OpenAI
    openai_api_key: str | None = None
    openai_whisper_model: str = "whisper-1"
    openai_chat_model: str = "gpt-4o-mini"
    openai_tts_model: str = "tts-1"
    openai_tts_voice: str = "alloy"

    # YouTube
    youtube_client_id: str | None = None
    youtube_client_secret: str | None = None

    # Meta / Instagram
    meta_app_id: str | None = None
    meta_app_secret: str | None = None

    # Limits
    max_upload_mb: int = 1024
    clip_min_duration: int = 15
    clip_max_duration: int = 60
    clips_per_video: int = 8

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    @property
    def cors_origins(self) -> list[str]:
        origins = {self.frontend_url, "http://localhost:3000", "http://127.0.0.1:3000"}
        return [o for o in origins if o]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
