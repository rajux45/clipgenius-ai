from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import decode_token, get_current_user
from ..auth.security import create_access_token
from ..config import settings
from ..database import get_db
from ..models import OAuthAccount, User
from ..services import instagram as ig_service
from ..services import youtube as yt_service

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/status")
def integrations_status(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    rows = db.execute(
        select(OAuthAccount).where(OAuthAccount.user_id == current.id)
    ).scalars().all()
    return {
        r.provider: {
            "connected": True,
            "scope": r.scope,
            "extra": {k: v for k, v in (r.extra or {}).items() if k != "user_token"},
        }
        for r in rows
    }


def _state_for(user: User) -> str:
    # short-lived signed token used to identify the user during the OAuth round-trip
    return create_access_token(str(user.id), extra={"oauth_nonce": secrets.token_urlsafe(8)})


def _user_from_state(state: str, db: Session) -> User:
    payload = decode_token(state)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    user = db.get(User, __import__("uuid").UUID(payload["sub"]))
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    return user


def _upsert_account(db: Session, user_id, provider: str, payload: dict) -> OAuthAccount:
    existing = db.scalar(
        select(OAuthAccount).where(OAuthAccount.user_id == user_id, OAuthAccount.provider == provider)
    )
    if existing:
        existing.access_token = payload["access_token"]
        existing.refresh_token = payload.get("refresh_token") or existing.refresh_token
        existing.expires_at = payload.get("expires_at")
        existing.scope = payload.get("scope")
        existing.extra = payload.get("extra") or existing.extra
        db.add(existing)
        db.commit()
        return existing
    acc = OAuthAccount(
        user_id=user_id,
        provider=provider,
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_at=payload.get("expires_at"),
        scope=payload.get("scope"),
        extra=payload.get("extra"),
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


# --- YouTube ---


@router.get("/youtube/connect")
def youtube_connect(current: User = Depends(get_current_user)) -> dict:
    return {"auth_url": yt_service.auth_url(_state_for(current))}


@router.get("/youtube/callback")
def youtube_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    user = _user_from_state(state, db)
    payload = yt_service.exchange_code(code)
    payload["extra"] = yt_service.channel_info(payload)
    _upsert_account(db, user.id, "youtube", payload)
    return RedirectResponse(f"{settings.frontend_url}/dashboard/settings?connected=youtube")


# --- Instagram (Meta) ---


@router.get("/instagram/connect")
def instagram_connect(current: User = Depends(get_current_user)) -> dict:
    return {"auth_url": ig_service.auth_url(_state_for(current))}


@router.get("/instagram/callback")
def instagram_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    user = _user_from_state(state, db)
    payload = ig_service.exchange_code(code)
    _upsert_account(db, user.id, "instagram", payload)
    return RedirectResponse(f"{settings.frontend_url}/dashboard/settings?connected=instagram")


@router.delete("/{provider}")
def disconnect(
    provider: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    acc = db.scalar(
        select(OAuthAccount).where(OAuthAccount.user_id == current.id, OAuthAccount.provider == provider)
    )
    if not acc:
        raise HTTPException(status_code=404, detail="Not connected")
    db.delete(acc)
    db.commit()
    return {"ok": True}
