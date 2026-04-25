"""Local file serving for development (when S3 isn't configured)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..services.storage import storage

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{key:path}")
def get_file(key: str) -> FileResponse:
    if storage.use_s3:
        # In S3 mode, presigned URLs are returned directly; this route is local-only.
        raise HTTPException(status_code=404, detail="Not available in S3 mode")
    path: Path = storage.local_path_for(key)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(path))
