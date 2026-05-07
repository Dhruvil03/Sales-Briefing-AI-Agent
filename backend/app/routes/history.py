# backend/app/routes/history.py
"""
GET  /api/history             — paginated list of research sessions (most recent first)
GET  /api/history/search?q=  — semantic search across all sessions via stored embeddings
GET  /api/history/{id}        — full detail for one session (all children loaded)
DELETE /api/history/{id}      — delete a session and all its children (CASCADE)

Semantic search pipeline (Step 11):
  query string
    → embed with SentenceTransformer (same model used at index time)
    → cosine similarity against all stored chunk.embedding vectors
    → group by session, take max score per session
    → return top-k sessions with matched excerpt

The search route MUST be defined before /{id} so FastAPI doesn't try to
cast "search" as an integer.
"""
from __future__ import annotations

import asyncio

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session as get_db_session
from app.models import CallNotes, Chunk, ProspectResearch, ResearchSession, User
from app.services.auth import get_optional_user
from app.services.embeddings import embed_texts

router = APIRouter()

_VALID_OUTCOMES = {"booked", "follow-up", "not-interested", "no-show"}


# ── response schemas ──────────────────────────────────────────────────────────

class SessionListItem(BaseModel):
    id:             int
    company_name:   str | None
    prospect_name:  str | None
    company_url:    str | None
    created_at:     str
    call_outcome:   str | None
    # presence flags so the UI can show completion badges
    has_company:    bool
    has_prospect:   bool
    has_report:     bool
    # short previews for the list card
    company_preview:  str | None
    prospect_preview: str | None
    report_preview:   str | None

class SessionDetail(BaseModel):
    id:               int
    company_name:     str | None
    prospect_name:    str | None
    company_url:      str | None
    created_at:       str
    call_outcome:     str | None
    has_company:      bool
    has_prospect:     bool
    has_report:       bool
    # full text
    company_summary:      str | None
    prospect_insights:    str | None
    report_md:            str | None
    followup_email:       str | None
    call_notes_text:      str | None
    sources_searched:     list[str] | None
    aggregated_text_len:  int | None   # chars of raw scraped text


# ── helpers ───────────────────────────────────────────────────────────────────

def _preview(text: str | None, n: int = 280) -> str | None:
    if not text:
        return None
    return text[:n] + ("…" if len(text) > n else "")


def _to_list_item(s: ResearchSession) -> SessionListItem:
    cr = s.company_research
    pr = s.prospect_research
    rp = s.report
    return SessionListItem(
        id=s.id,
        company_name=s.company_name,
        prospect_name=s.prospect_name,
        company_url=s.company_url,
        created_at=s.created_at.isoformat() if s.created_at else "",
        call_outcome=s.call_outcome,
        has_company=cr is not None,
        has_prospect=pr is not None,
        has_report=rp is not None,
        company_preview=_preview(cr.summary if cr else None),
        prospect_preview=_preview(pr.insights if pr else None),
        report_preview=_preview(rp.report_md if rp else None),
    )


def _to_detail(s: ResearchSession) -> SessionDetail:
    cr = s.company_research
    pr = s.prospect_research
    rp = s.report
    fe = s.followup_email
    cn = s.call_notes
    return SessionDetail(
        id=s.id,
        company_name=s.company_name,
        prospect_name=s.prospect_name,
        company_url=s.company_url,
        created_at=s.created_at.isoformat() if s.created_at else "",
        call_outcome=s.call_outcome,
        has_company=cr is not None,
        has_prospect=pr is not None,
        has_report=rp is not None,
        company_summary=cr.summary if cr else None,
        prospect_insights=pr.insights if pr else None,
        report_md=rp.report_md if rp else None,
        followup_email=fe.email_md if fe else None,
        call_notes_text=cn.notes_text if cn else None,
        sources_searched=pr.sources_searched if pr else None,
        aggregated_text_len=len(pr.aggregated_text) if pr and pr.aggregated_text else None,
    )


def _eager_query():
    return (
        select(ResearchSession)
        .options(
            selectinload(ResearchSession.company_research),
            selectinload(ResearchSession.prospect_research),
            selectinload(ResearchSession.report),
            selectinload(ResearchSession.followup_email),
            selectinload(ResearchSession.call_notes),
        )
        .order_by(desc(ResearchSession.created_at))
    )


# ── search schema ────────────────────────────────────────────────────────────

class SearchResult(BaseModel):
    session_id:    int
    company_name:  str | None
    prospect_name: str | None
    created_at:    str
    score:         float        # cosine similarity 0–1
    excerpt:       str          # best-matching chunk text (preview)


# ── routes ────────────────────────────────────────────────────────────────────

@router.get("/history", response_model=list[SessionListItem])
async def list_history(
    limit: int = 50,
    db: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(get_optional_user),
):
    q = _eager_query().limit(limit)
    if user:
        q = q.where(ResearchSession.user_id == user.id)
    res = await db.execute(q)
    sessions = res.scalars().all()
    return [_to_list_item(s) for s in sessions]


@router.get("/history/search", response_model=list[SearchResult])
async def search_history(
    q: str,
    limit: int = 8,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Semantic search across all research sessions.

    Pipeline:
      1. Embed the query (one short text — fast, GIL hold < 100ms)
      2. Load all stored chunk embeddings from DB
      3. Cosine similarity (embeddings are L2-normalised at write time → dot = cosine)
      4. Group by session, keep best score + best excerpt per session
      5. Return top-k sessions sorted by relevance

    Returns [] with a 200 if no embeddings exist yet (not an error — just
    means prospect research hasn't run yet, or background task is still pending).
    """
    if not q.strip():
        raise HTTPException(status_code=422, detail="Query cannot be empty")

    loop = asyncio.get_event_loop()

    # ── 1. Embed query ────────────────────────────────────────────────────────
    try:
        qvecs: list[list[float]] = await asyncio.wait_for(
            loop.run_in_executor(None, embed_texts, [q.strip()]),
            timeout=15,
        )
        qvec = np.array(qvecs[0], dtype=float)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="Embedding timed out. Try again.")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Embedding failed: {repr(exc)}")

    # ── 2. Try Pinecone first; fall back to local PostgreSQL embeddings ───────
    best: dict[int, tuple[float, str]] = {}

    _pinecone_used = False
    try:
        from app.services.vector_store import query_similar
        pinecone_res = await loop.run_in_executor(
            None, query_similar, qvec.tolist(), limit * 3
        )
        matches = (
            pinecone_res.get("matches")
            if isinstance(pinecone_res, dict)
            else getattr(pinecone_res, "matches", None)
        ) or []

        # Map source_id → session_id
        pr_res = await db.execute(
            select(ProspectResearch.source_id, ProspectResearch.session_id)
            .where(ProspectResearch.source_id.isnot(None))
        )
        source_to_session: dict[int, int] = {
            row.source_id: row.session_id for row in pr_res.fetchall()
        }

        for m in matches:
            meta       = m.get("metadata", {}) if isinstance(m, dict) else getattr(m, "metadata", {}) or {}
            score      = m.get("score", 0.0)   if isinstance(m, dict) else getattr(m, "score", 0.0)
            source_id  = meta.get("source_id")
            chunk_text = meta.get("chunk_text", "")
            if source_id is None:
                continue
            session_id = source_to_session.get(int(source_id))
            if session_id is None:
                continue
            if session_id not in best or score > best[session_id][0]:
                best[session_id] = (float(score), chunk_text)

        if matches:
            _pinecone_used = True

    except RuntimeError:
        pass  # Pinecone not configured — use local
    except Exception as exc:
        print(f"[history/search] Pinecone query failed, using local: {repr(exc)}")

    # ── Local PostgreSQL fallback (or primary when Pinecone not configured) ──
    if not _pinecone_used:
        chunk_res = await db.execute(
            select(Chunk.id, Chunk.source_id, Chunk.chunk_text, Chunk.embedding)
            .where(Chunk.embedding.isnot(None))
        )
        chunk_rows = chunk_res.fetchall()

        if not chunk_rows:
            return []

        pr_res = await db.execute(
            select(ProspectResearch.source_id, ProspectResearch.session_id)
            .where(ProspectResearch.source_id.isnot(None))
        )
        source_to_session = {
            row.source_id: row.session_id for row in pr_res.fetchall()
        }

        for row in chunk_rows:
            session_id = source_to_session.get(row.source_id)
            if session_id is None:
                continue
            vec   = np.array(row.embedding, dtype=float)
            score = float(np.dot(qvec, vec))
            if session_id not in best or score > best[session_id][0]:
                best[session_id] = (score, row.chunk_text)

    if not best:
        return []

    # ── 4. Sort and load session metadata ─────────────────────────────────────
    top_ids = sorted(best, key=lambda sid: best[sid][0], reverse=True)[:limit]

    sess_res = await db.execute(
        select(ResearchSession).where(ResearchSession.id.in_(top_ids))
    )
    sessions = {s.id: s for s in sess_res.scalars().all()}

    # ── 5. Build response ─────────────────────────────────────────────────────
    results: list[SearchResult] = []
    for sid in top_ids:
        s = sessions.get(sid)
        if not s:
            continue
        score, excerpt = best[sid]
        results.append(SearchResult(
            session_id=s.id,
            company_name=s.company_name,
            prospect_name=s.prospect_name,
            created_at=s.created_at.isoformat() if s.created_at else "",
            score=round(score, 4),
            excerpt=excerpt[:280] + ("…" if len(excerpt) > 280 else ""),
        ))

    return results


@router.get("/history/{session_id}", response_model=SessionDetail)
async def get_history_item(
    session_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    res = await db.execute(
        _eager_query().where(ResearchSession.id == session_id)
    )
    session = res.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _to_detail(session)


@router.delete("/history/{session_id}", status_code=204)
async def delete_history_item(
    session_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    res = await db.execute(
        select(ResearchSession).where(ResearchSession.id == session_id)
    )
    session = res.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.delete(session)
    await db.commit()


class NotesBody(BaseModel):
    notes_text: str  # empty string clears the notes


@router.patch("/history/{session_id}/notes", response_model=SessionDetail)
async def update_notes(
    session_id: int,
    body: NotesBody,
    db: AsyncSession = Depends(get_db_session),
):
    res = await db.execute(
        _eager_query().where(ResearchSession.id == session_id)
    )
    session = res.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.call_notes:
        session.call_notes.notes_text = body.notes_text
    else:
        cn = CallNotes(session_id=session_id, notes_text=body.notes_text)
        db.add(cn)
        await db.flush()
        # Reload to get the relationship populated
        await db.refresh(session, ["call_notes"])

    await db.commit()
    # Re-fetch with eager loads for the response
    res2 = await db.execute(
        _eager_query().where(ResearchSession.id == session_id)
    )
    session = res2.scalar_one_or_none()
    return _to_detail(session)


class OutcomeBody(BaseModel):
    outcome: str | None  # null clears the outcome


@router.patch("/history/{session_id}/outcome", response_model=SessionListItem)
async def set_outcome(
    session_id: int,
    body: OutcomeBody,
    db: AsyncSession = Depends(get_db_session),
):
    if body.outcome is not None and body.outcome not in _VALID_OUTCOMES:
        raise HTTPException(
            status_code=422,
            detail=f"outcome must be one of: {sorted(_VALID_OUTCOMES)} or null",
        )
    res = await db.execute(
        _eager_query().where(ResearchSession.id == session_id)
    )
    session = res.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.call_outcome = body.outcome
    await db.commit()
    await db.refresh(session)
    return _to_list_item(session)
