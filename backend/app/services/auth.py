# backend/app/services/auth.py
"""
JWT auth utilities.

Two dependency variants:
  get_current_user    — raises 401 if no valid token (protected routes)
  get_optional_user   — returns None if no token (research routes still work unauthenticated)
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import bcrypt as _bcrypt
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session as get_db_session
from app.models import User

SECRET_KEY  = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
ALGORITHM   = "HS256"
EXPIRE_DAYS = 30

_http = HTTPBearer(auto_error=False)


# ── password helpers ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


# ── token helpers ─────────────────────────────────────────────────────────────

def create_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=EXPIRE_DAYS)
    return jwt.encode({"sub": str(user_id), "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)

def _decode(token: str) -> int | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        return None


# ── FastAPI dependencies ──────────────────────────────────────────────────────

async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_http),
    db: AsyncSession = Depends(get_db_session),
) -> User:
    """Raises 401 if token is missing or invalid."""
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = _decode(creds.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_http),
    db: AsyncSession = Depends(get_db_session),
) -> User | None:
    """Returns None instead of raising — use on routes that work with or without auth."""
    if not creds:
        return None
    user_id = _decode(creds.credentials)
    if not user_id:
        return None
    res = await db.execute(select(User).where(User.id == user_id))
    return res.scalar_one_or_none()
