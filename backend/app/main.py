from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine
from .routers import auth, clips, files, integrations, schedule, videos

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, debug=settings.debug, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https://.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    # In production we'd run alembic migrations; for MVP, ensure tables exist.
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not create tables on startup: %s", exc)


@app.get("/")
def root() -> dict:
    return {"app": settings.app_name, "version": "0.1.0", "ok": True}


@app.get("/health")
def health() -> dict:
    return {"ok": True}


app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(videos.router, prefix=settings.api_prefix)
app.include_router(clips.router, prefix=settings.api_prefix)
app.include_router(schedule.router, prefix=settings.api_prefix)
app.include_router(integrations.router, prefix=settings.api_prefix)
app.include_router(files.router, prefix=settings.api_prefix)
