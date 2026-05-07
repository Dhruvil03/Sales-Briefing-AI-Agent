# backend/app/crud.py
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    ResearchRun,
    ResearchSession,
    CompanyResearch,
    ProspectResearch,
    PreCallReport,
    CallNotes,
    FollowUpEmail,
)


# ---------------------------------------------------------------------------
# ResearchSession
# ---------------------------------------------------------------------------

async def create_session(
    db: AsyncSession,
    *,
    company_url: str | None = None,
    company_name: str | None = None,
    prospect_name: str | None = None,
    user_id: int | None = None,
) -> ResearchSession:
    session = ResearchSession(
        user_id=user_id,
        company_url=company_url,
        company_name=company_name,
        prospect_name=prospect_name,
    )
    db.add(session)
    await db.flush()
    await db.commit()
    await db.refresh(session)
    return session


async def get_session(
    db: AsyncSession, session_id: int, user_id: int | None = None
) -> ResearchSession | None:
    q = select(ResearchSession).where(ResearchSession.id == session_id)
    if user_id is not None:
        q = q.where(ResearchSession.user_id == user_id)
    res = await db.execute(q)
    return res.scalar_one_or_none()


async def list_sessions(
    db: AsyncSession, user_id: int | None = None, limit: int = 50
) -> list[ResearchSession]:
    q = select(ResearchSession).order_by(desc(ResearchSession.created_at)).limit(limit)
    if user_id is not None:
        q = q.where(ResearchSession.user_id == user_id)
    res = await db.execute(q)
    return [r for (r,) in res.all()]


async def update_session_meta(
    db: AsyncSession,
    session_id: int,
    *,
    company_name: str | None = None,
    prospect_name: str | None = None,
    call_outcome: str | None = None,
    call_date: datetime | None = None,
) -> ResearchSession | None:
    row = await get_session(db, session_id)
    if not row:
        return None
    if company_name  is not None: row.company_name  = company_name
    if prospect_name is not None: row.prospect_name = prospect_name
    if call_outcome  is not None: row.call_outcome  = call_outcome
    if call_date     is not None: row.call_date     = call_date
    await db.commit()
    await db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# CompanyResearch  (one per session — upsert pattern)
# ---------------------------------------------------------------------------

async def upsert_company_research(
    db: AsyncSession,
    session_id: int,
    *,
    raw_text: str | None = None,
    summary: str | None = None,
    signals: list[dict[str, Any]] | None = None,
    source_id: int | None = None,
) -> CompanyResearch:
    res = await db.execute(
        select(CompanyResearch).where(CompanyResearch.session_id == session_id)
    )
    row = res.scalar_one_or_none()
    if row is None:
        row = CompanyResearch(session_id=session_id)
        db.add(row)

    if raw_text   is not None: row.raw_text  = raw_text
    if summary    is not None: row.summary   = summary
    if signals    is not None: row.signals   = signals
    if source_id  is not None: row.source_id = source_id

    await db.commit()
    await db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# ProspectResearch  (one per session — upsert pattern)
# ---------------------------------------------------------------------------

async def upsert_prospect_research(
    db: AsyncSession,
    session_id: int,
    *,
    sources_searched: list[str] | None = None,
    aggregated_text: str | None = None,
    insights: str | None = None,
    source_id: int | None = None,
) -> ProspectResearch:
    res = await db.execute(
        select(ProspectResearch).where(ProspectResearch.session_id == session_id)
    )
    row = res.scalar_one_or_none()
    if row is None:
        row = ProspectResearch(session_id=session_id)
        db.add(row)

    if sources_searched is not None: row.sources_searched = sources_searched
    if aggregated_text  is not None: row.aggregated_text  = aggregated_text
    if insights         is not None: row.insights         = insights
    if source_id        is not None: row.source_id        = source_id

    await db.commit()
    await db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# PreCallReport  (one per session — upsert pattern)
# ---------------------------------------------------------------------------

async def upsert_report(
    db: AsyncSession,
    session_id: int,
    *,
    report_md: str | None = None,
    tone: str | None = None,
) -> PreCallReport:
    res = await db.execute(
        select(PreCallReport).where(PreCallReport.session_id == session_id)
    )
    row = res.scalar_one_or_none()
    if row is None:
        row = PreCallReport(session_id=session_id)
        db.add(row)

    if report_md is not None: row.report_md = report_md
    if tone      is not None: row.tone      = tone

    await db.commit()
    await db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# CallNotes  (one per session — upsert pattern)
# ---------------------------------------------------------------------------

async def upsert_call_notes(
    db: AsyncSession,
    session_id: int,
    *,
    notes_text: str,
) -> CallNotes:
    res = await db.execute(
        select(CallNotes).where(CallNotes.session_id == session_id)
    )
    row = res.scalar_one_or_none()
    if row is None:
        row = CallNotes(session_id=session_id)
        db.add(row)

    row.notes_text = notes_text

    await db.commit()
    await db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# FollowUpEmail  (one per session — upsert pattern)
# ---------------------------------------------------------------------------

async def upsert_followup_email(
    db: AsyncSession,
    session_id: int,
    *,
    email_md: str,
) -> FollowUpEmail:
    res = await db.execute(
        select(FollowUpEmail).where(FollowUpEmail.session_id == session_id)
    )
    row = res.scalar_one_or_none()
    if row is None:
        row = FollowUpEmail(session_id=session_id)
        db.add(row)

    row.email_md = email_md

    await db.commit()
    await db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Full session detail (eager loads all child rows)
# ---------------------------------------------------------------------------

async def get_session_full(
    db: AsyncSession, session_id: int, user_id: int | None = None
) -> ResearchSession | None:
    """
    Returns the session with all child relationships loaded.
    Uses selectinload-style approach via separate queries to stay async-safe.
    """
    from sqlalchemy.orm import selectinload

    q = (
        select(ResearchSession)
        .options(
            selectinload(ResearchSession.company_research),
            selectinload(ResearchSession.prospect_research),
            selectinload(ResearchSession.report),
            selectinload(ResearchSession.call_notes),
            selectinload(ResearchSession.followup_email),
        )
        .where(ResearchSession.id == session_id)
    )
    if user_id is not None:
        q = q.where(ResearchSession.user_id == user_id)

    res = await db.execute(q)
    return res.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Legacy — used by old routes until they are updated in later steps.
# ---------------------------------------------------------------------------

async def create_run(
    db: AsyncSession,
    run_type: str,
    input_text: str | None,
    output_text: str | None,
    source: str | None = None,
    input_meta: str | None = None,
) -> ResearchRun:
    new = ResearchRun(
        run_type=run_type,
        input_text=input_text,
        output_text=output_text,
        source=source,
        input_meta=input_meta,
    )
    db.add(new)
    await db.flush()
    await db.commit()
    await db.refresh(new)
    return new


async def list_runs(db: AsyncSession, limit: int = 50) -> list[ResearchRun]:
    q = select(ResearchRun).order_by(desc(ResearchRun.created_at)).limit(limit)
    res = await db.execute(q)
    return [r for (r,) in res.all()]
