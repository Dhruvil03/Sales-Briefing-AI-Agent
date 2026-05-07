# backend/app/routes/auth.py
"""
POST /api/auth/signup   — create account, return token
POST /api/auth/login    — verify credentials, return token
GET  /api/auth/me       — return current user profile
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session as get_db_session
from app.models import User
from app.services.auth import (
    create_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth")


# ── schemas ───────────────────────────────────────────────────────────────────

class SignupBody(BaseModel):
    email:     str  = Field(min_length=5)
    password:  str  = Field(min_length=6, description="Minimum 6 characters")
    full_name: str | None = None

class LoginBody(BaseModel):
    email:    str
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    user_id:      int
    email:        str
    full_name:    str | None

class UserOut(BaseModel):
    id:        int
    email:     str
    full_name: str | None


# ── routes ────────────────────────────────────────────────────────────────────

@router.post("/signup", response_model=TokenOut)
async def signup(body: SignupBody, db: AsyncSession = Depends(get_db_session)):
    # Check duplicate
    res = await db.execute(select(User).where(User.email == body.email.lower()))
    if res.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = User(
        email=body.email.lower().strip(),
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(user)
    await db.flush()
    await db.commit()
    await db.refresh(user)

    return TokenOut(
        access_token=create_token(user.id),
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
    )


@router.post("/login", response_model=TokenOut)
async def login(body: LoginBody, db: AsyncSession = Depends(get_db_session)):
    res = await db.execute(select(User).where(User.email == body.email.lower()))
    user = res.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    return TokenOut(
        access_token=create_token(user.id),
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
    )


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut(id=user.id, email=user.email, full_name=user.full_name)
