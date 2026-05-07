# backend/app/routes/followup.py
"""
POST /api/sessions/{session_id}/followup

Takes the rep's post-call notes and generates a personalized follow-up email
by combining those notes with the session's prospect insights and pre-call report.

Streams token-by-token as SSE. Saves the result to followup_emails table.

SSE event sequence:
  status  "Writing follow-up email..."
  token   ... (LLM tokens)
  done
  error   (on failure)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import upsert_followup_email, upsert_call_notes
from app.db import get_session as get_db_session
from app.models import ResearchSession
from app.services.llm import stream_completion
from app.services.sse import sse_done, sse_error, sse_status, sse_token

router = APIRouter()


# ── prompt ────────────────────────────────────────────────────────────────────

_PROMPT = """\
You are an expert B2B sales writer. Write a personalized follow-up email for \
the sales rep to send after a discovery call.

EMAIL TONE / TYPE: {tone}

Tone guidance:
- "warm follow-up after call" → reference specific conversation moments, assume positive rapport, clear next step
- "cold outreach" → no prior relationship assumed, hook with insight about their business, soft CTA
- "re-engagement" → acknowledge the gap, no guilt, lead with new value or timing angle
- For any tone: sound human, be specific, keep it short (subject + 4–6 sentences), no placeholders

Output format:
Subject: <subject line>

<email body>

---
PROSPECT: {prospect_name} at {company_name}

PROSPECT PROFILE:
{prospect_insights}

PRE-CALL REPORT:
{report_context}

CALL NOTES (what the rep observed during the call):
{call_notes}
"""


# ── request body ──────────────────────────────────────────────────────────────

_TONE_MAP = {
    "follow-up":     "warm follow-up after call",
    "cold":          "cold outreach",
    "re-engagement": "re-engagement after a long gap",
}

class FollowupBody(BaseModel):
    call_notes: str = Field(min_length=5, description="Rep's notes from the call")
    tone: str | None = Field(default="follow-up")


# ── route ─────────────────────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/followup")
async def generate_followup(
    session_id: int,
    body: FollowupBody,
    db: AsyncSession = Depends(get_db_session),
):
    # Load session with children
    res = await db.execute(
        select(ResearchSession)
        .options(
            selectinload(ResearchSession.prospect_research),
            selectinload(ResearchSession.report),
        )
        .where(ResearchSession.id == session_id)
    )
    session = res.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    prospect_insights = (
        session.prospect_research.insights
        if session.prospect_research else "Not available."
    )
    report_context = (
        session.report.report_md[:4_000]
        if session.report else "Not available."
    )

    async def generate():
        yield sse_status("Writing follow-up email...")

        # Save call notes (best-effort)
        try:
            await upsert_call_notes(db, session_id, notes_text=body.call_notes)
        except Exception as exc:
            print(f"[followup] Call notes save failed (non-fatal): {repr(exc)}")

        tone_label = _TONE_MAP.get(body.tone or "follow-up", "warm follow-up after call")
        prompt = _PROMPT.format(
            tone=tone_label,
            prospect_name=session.prospect_name or "the prospect",
            company_name=session.company_name or "their company",
            prospect_insights=prospect_insights[:6_000],
            report_context=report_context,
            call_notes=body.call_notes[:2_000],
        )

        full_text: list[str] = []
        try:
            async for token in stream_completion(prompt):
                full_text.append(token)
                yield sse_token(token)
        except RuntimeError as exc:
            yield sse_error(str(exc))
            return
        except Exception as exc:
            yield sse_error(f"LLM error: {repr(exc)}")
            return

        # Persist email
        email_md = "".join(full_text)
        if email_md:
            try:
                await upsert_followup_email(db, session_id, email_md=email_md)
            except Exception as exc:
                print(f"[followup] Persist failed (non-fatal): {repr(exc)}")

        yield sse_done()

    return StreamingResponse(generate(), media_type="text/event-stream")
