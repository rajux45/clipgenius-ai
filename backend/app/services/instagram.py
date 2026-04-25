"""Meta Graph API integration for Instagram Reels.

Flow:
  1. User logs in with Facebook (Meta OAuth) granting `instagram_basic`,
     `instagram_content_publish`, `pages_show_list`, `business_management`.
  2. We list their Pages and find the linked IG Business / Creator Account.
  3. To publish a Reel we POST a "media container" with the public video URL
     (must be accessible to Meta's servers, hence S3) and then publish it.

Production note: Reel publishing requires a Meta App reviewed for
`instagram_content_publish`. Until review, only test users added to the app can post.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from ..config import settings

log = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com/v21.0"

SCOPES = [
    "instagram_basic",
    "instagram_content_publish",
    "pages_show_list",
    "pages_read_engagement",
    "business_management",
]


def _redirect_uri() -> str:
    return f"{settings.backend_url.rstrip('/')}{settings.api_prefix}/integrations/instagram/callback"


def auth_url(state: str) -> str:
    if not settings.meta_app_id:
        raise RuntimeError("META_APP_ID not configured")
    qs = httpx.QueryParams(
        {
            "client_id": settings.meta_app_id,
            "redirect_uri": _redirect_uri(),
            "scope": ",".join(SCOPES),
            "response_type": "code",
            "state": state,
        }
    )
    return f"https://www.facebook.com/v21.0/dialog/oauth?{qs}"


def exchange_code(code: str) -> dict:
    if not (settings.meta_app_id and settings.meta_app_secret):
        raise RuntimeError("Meta app credentials missing")
    short = httpx.get(
        f"{GRAPH}/oauth/access_token",
        params={
            "client_id": settings.meta_app_id,
            "client_secret": settings.meta_app_secret,
            "redirect_uri": _redirect_uri(),
            "code": code,
        },
        timeout=30,
    )
    short.raise_for_status()
    short_token = short.json()["access_token"]

    # Exchange for long-lived (~60 days) user token
    longp = httpx.get(
        f"{GRAPH}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": settings.meta_app_id,
            "client_secret": settings.meta_app_secret,
            "fb_exchange_token": short_token,
        },
        timeout=30,
    )
    longp.raise_for_status()
    longp_data = longp.json()
    user_token = longp_data["access_token"]

    # Find a Page + linked IG account
    pages = httpx.get(
        f"{GRAPH}/me/accounts",
        params={"access_token": user_token, "fields": "id,name,access_token,instagram_business_account"},
        timeout=30,
    ).json()
    page_id = ig_id = page_token = page_name = None
    for p in pages.get("data", []):
        if p.get("instagram_business_account"):
            page_id = p["id"]
            page_name = p.get("name")
            page_token = p["access_token"]  # page tokens for Pages don't expire if from long-lived user token
            ig_id = p["instagram_business_account"]["id"]
            break

    return {
        "access_token": page_token or user_token,
        "refresh_token": None,
        "expires_at": None,
        "scope": ",".join(SCOPES),
        "extra": {
            "user_token": user_token,
            "page_id": page_id,
            "page_name": page_name,
            "ig_user_id": ig_id,
        },
    }


def publish_reel(
    account: dict[str, Any],
    *,
    video_url: str,
    caption: str,
    share_to_feed: bool = True,
) -> dict:
    """Publish a Reel via the public video URL (S3 presigned)."""
    extra = account.get("extra") or {}
    ig_id = extra.get("ig_user_id")
    page_token = account["access_token"]
    if not ig_id:
        raise RuntimeError("No Instagram Business account linked to this Facebook Page")

    # 1) create container
    create = httpx.post(
        f"{GRAPH}/{ig_id}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption[:2200],
            "share_to_feed": "true" if share_to_feed else "false",
            "access_token": page_token,
        },
        timeout=60,
    )
    create.raise_for_status()
    container_id = create.json()["id"]

    # 2) wait for container to finish processing
    deadline = time.time() + 300
    while time.time() < deadline:
        status = httpx.get(
            f"{GRAPH}/{container_id}",
            params={"fields": "status_code", "access_token": page_token},
            timeout=30,
        ).json()
        code = status.get("status_code")
        if code == "FINISHED":
            break
        if code == "ERROR":
            raise RuntimeError(f"Instagram container error: {status}")
        time.sleep(5)
    else:
        raise TimeoutError("Instagram container did not finish processing in time")

    # 3) publish
    pub = httpx.post(
        f"{GRAPH}/{ig_id}/media_publish",
        data={"creation_id": container_id, "access_token": page_token},
        timeout=60,
    )
    pub.raise_for_status()
    media_id = pub.json()["id"]

    # 4) fetch permalink
    info = httpx.get(
        f"{GRAPH}/{media_id}",
        params={"fields": "permalink", "access_token": page_token},
        timeout=30,
    ).json()
    return {"id": media_id, "url": info.get("permalink")}


def media_insights(account: dict[str, Any], media_id: str) -> dict:
    page_token = account["access_token"]
    metrics = "plays,reach,likes,comments,saved,shares"
    resp = httpx.get(
        f"{GRAPH}/{media_id}/insights",
        params={"metric": metrics, "access_token": page_token},
        timeout=30,
    )
    if resp.status_code != 200:
        return {}
    out: dict[str, int] = {}
    for entry in resp.json().get("data", []):
        name = entry.get("name")
        values = entry.get("values") or []
        if not values:
            continue
        out[name] = int(values[0].get("value", 0) or 0)
    return out
