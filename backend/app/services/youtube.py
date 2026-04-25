"""YouTube Data API v3 OAuth + Shorts upload."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from ..config import settings

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def _redirect_uri() -> str:
    return f"{settings.backend_url.rstrip('/')}{settings.api_prefix}/integrations/youtube/callback"


def _client_config() -> dict:
    if not (settings.youtube_client_id and settings.youtube_client_secret):
        raise RuntimeError("YouTube OAuth credentials not configured")
    return {
        "web": {
            "client_id": settings.youtube_client_id,
            "client_secret": settings.youtube_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [_redirect_uri()],
        }
    }


def auth_url(state: str) -> str:
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, redirect_uri=_redirect_uri())
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    return url


def exchange_code(code: str) -> dict:
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, redirect_uri=_redirect_uri())
    flow.fetch_token(code=code)
    creds = flow.credentials
    return {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "expires_at": creds.expiry.replace(tzinfo=UTC) if creds.expiry else None,
        "scope": " ".join(creds.scopes or SCOPES),
    }


def _credentials(account: dict[str, Any]) -> Credentials:
    creds = Credentials(
        token=account["access_token"],
        refresh_token=account.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.youtube_client_id,
        client_secret=settings.youtube_client_secret,
        scopes=SCOPES,
    )
    if account.get("refresh_token") and not creds.valid:
        creds.refresh(Request())
    return creds


def channel_info(account: dict[str, Any]) -> dict:
    creds = _credentials(account)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    resp = yt.channels().list(part="snippet,statistics", mine=True).execute()
    items = resp.get("items", [])
    if not items:
        return {}
    item = items[0]
    return {
        "channel_id": item["id"],
        "title": item["snippet"]["title"],
        "thumbnail": item["snippet"]["thumbnails"]["default"]["url"],
        "subscribers": item["statistics"].get("subscriberCount"),
    }


def upload_short(
    account: dict[str, Any],
    video_path: str | Path,
    *,
    title: str,
    description: str,
    tags: list[str] | None = None,
    privacy: str = "public",
    publish_at: datetime | None = None,
) -> dict:
    creds = _credentials(account)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": (tags or [])[:20],
            "categoryId": "22",  # People & Blogs (broadly safe default)
        },
        "status": {
            "privacyStatus": "private" if publish_at else privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    if publish_at:
        body["status"]["publishAt"] = publish_at.astimezone(UTC).isoformat()
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True, chunksize=1024 * 1024 * 8)
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log.info("YT upload progress: %d%%", int(status.progress() * 100))
    return {
        "id": response["id"],
        "url": f"https://www.youtube.com/shorts/{response['id']}",
    }


def video_stats(account: dict[str, Any], video_id: str) -> dict:
    creds = _credentials(account)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    resp = yt.videos().list(part="statistics", id=video_id).execute()
    items = resp.get("items", [])
    if not items:
        return {}
    s = items[0]["statistics"]
    return {
        "views": int(s.get("viewCount", 0)),
        "likes": int(s.get("likeCount", 0)),
        "comments": int(s.get("commentCount", 0)),
    }
