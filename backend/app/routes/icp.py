# backend/app/routes/icp.py
"""
ICP (Ideal Customer Profile) management + fit scoring.

GET  /api/icp                     — get user's ICP profile
POST /api/icp                     — create/update ICP profile
POST /api/sessions/{id}/icp-score — score a prospect against the ICP
GET  /api/sessions/{id}/icp-score — get existing ICP score
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import get_session_full
from app.db import get_session as get_db_session
from app.models import ICPProfile, ICPScore, User
from app.services.auth import get_current_user
from app.services.llm import complete

router = APIRouter()

_SCORE_PROMPT = """\
You are a sales qualification expert. Score how well this prospect fits the \
Ideal Customer Profile (ICP) below.

IDEAL CUSTOMER PROFILE:
- Industry: {industry}
- Company size: {company_size}
- Target roles: {roles}
- Key pain points we solve: {pain_points}
- Positive buying signals: {signals}

PROSPECT PROFILE:
{prospect_summary}

Return ONLY a valid JSON object (no explanation, no markdown) with this exact shape:
{{
  "score": <integer 1-10>,
  "breakdown": {{
    "industry_fit": <integer 1-10>,
    "role_fit": <integer 1-10>,
    "pain_match": <integer 1-10>,
    "signals_match": <integer 1-10>
  }},
  "reasoning": "<2-3 sentences explaining the score>"
}}
"""


# ── Pydantic models ───────────────────────────────────────────────────────────

class ICPProfileIn(BaseModel):
    industry:     str | None = None
    company_size: str | None = None
    roles:        str | None = None
    pain_points:  str | None = None
    signals:      str | None = None


class ICPProfileOut(BaseModel):
    industry:     str | None
    company_size: str | None
    roles:        str | None
    pain_points:  str | None
    signals:      str | None

    class Config:
        from_attributes = True


class ICPScoreOut(BaseModel):
    score:     int
    breakdown: dict | None
    reasoning: str | None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/icp", response_model=ICPProfileOut | None)
async def get_icp(
    db:   AsyncSession = Depends(get_db_session),
    user: User         = Depends(get_current_user),
):
    res = await db.execute(select(ICPProfile).where(ICPProfile.user_id == user.id))
    return res.scalar_one_or_none()


@router.post("/icp", response_model=ICPProfileOut)
async def upsert_icp(
    body: ICPProfileIn,
    db:   AsyncSession = Depends(get_db_session),
    user: User         = Depends(get_current_user),
):
    res = await db.execute(select(ICPProfile).where(ICPProfile.user_id == user.id))
    profile = res.scalar_one_or_none()

    if profile is None:
        profile = ICPProfile(user_id=user.id)
        db.add(profile)

    if body.industry     is not None: profile.industry     = body.industry
    if body.company_size is not None: profile.company_size = body.company_size
    if body.roles        is not None: profile.roles        = body.roles
    if body.pain_points  is not None: profile.pain_points  = body.pain_points
    if body.signals      is not None: profile.signals      = body.signals

    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/sessions/{session_id}/icp-score", response_model=ICPScoreOut | None)
async def get_score(
    session_id: int,
    db:   AsyncSession = Depends(get_db_session),
    user: User         = Depends(get_current_user),
):
    res = await db.execute(
        select(ICPScore).where(ICPScore.session_id == session_id)
    )
    row = res.scalar_one_or_none()
    if row is None:
        return None
    return ICPScoreOut(score=row.score, breakdown=row.breakdown, reasoning=row.reasoning)


@router.post("/sessions/{session_id}/icp-score", response_model=ICPScoreOut)
async def score_prospect(
    session_id: int,
    db:   AsyncSession = Depends(get_db_session),
    user: User         = Depends(get_current_user),
):
    """
    Scores the prospect in session_id against the user's ICP.
    Returns the score immediately (non-streaming).
    """
    # Load ICP
    icp_res = await db.execute(select(ICPProfile).where(ICPProfile.user_id == user.id))
    icp = icp_res.scalar_one_or_none()
    if icp is None:
        raise HTTPException(400, "No ICP profile found. Create one at /api/icp first.")

    # Load session
    session = await get_session_full(db, session_id, user_id=user.id)
    if session is None:
        raise HTTPException(404, "Session not found")

    prospect_summary = ""
    if session.prospect_research and session.prospect_research.insights:
        prospect_summary = session.prospect_research.insights[:4_000]
    elif session.company_research and session.company_research.summary:
        prospect_summary = session.company_research.summary[:4_000]
    else:
        raise HTTPException(400, "No prospect or company research found to score.")

    # Call LLM
    prompt = _SCORE_PROMPT.format(
        industry=icp.industry or "Any",
        company_size=icp.company_size or "Any",
        roles=icp.roles or "Any",
        pain_points=icp.pain_points or "Not specified",
        signals=icp.signals or "Not specified",
        prospect_summary=prospect_summary,
    )

    raw = await complete(prompt)

    # Parse JSON response (LLM may wrap it in markdown fences)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(500, f"LLM returned invalid JSON: {raw[:200]}")

    score_val  = int(data.get("score", 5))
    breakdown  = data.get("breakdown")
    reasoning  = str(data.get("reasoning", ""))

    # Upsert ICPScore
    score_res = await db.execute(
        select(ICPScore).where(ICPScore.session_id == session_id)
    )
    score_row = score_res.scalar_one_or_none()
    if score_row is None:
        score_row = ICPScore(session_id=session_id)
        db.add(score_row)

    score_row.score     = score_val
    score_row.breakdown = breakdown
    score_row.reasoning = reasoning
    await db.commit()
    await db.refresh(score_row)

    return ICPScoreOut(score=score_val, breakdown=breakdown, reasoning=reasoning)
