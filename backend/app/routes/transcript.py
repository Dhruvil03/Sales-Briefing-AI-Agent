# backend/app/routes/transcript.py
"""
POST /api/sessions/{id}/transcript

Paste a meeting/call transcript → LLM extracts action items, next steps,
objections, sentiment, and drafts a personalized follow-up email.

Streams as SSE (same pattern as all other AI endpoints).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import get_session, upsert_followup_email
from app.db import get_session as get_db_session
from app.models import User
from app.services.auth import get_optional_user
from app.services.llm import stream_completion
from app.services.sse import sse_done, sse_error, sse_status, sse_token

router = APIRouter()

_PROMPT = """\
You are an expert sales analyst. Analyze this call/meeting transcript and produce a \
structured post-call summary for the sales rep.

PROSPECT: {name}
COMPANY: {company}

TRANSCRIPT:
{transcript}

---

Respond with the following sections (use these exact headings):

## Meeting Summary
2-3 sentence overview of what was discussed and the overall tone.

## Sentiment
Overall sentiment: [Positive / Neutral / Skeptical / Negative] — explain why in one sentence.

## Key Pain Points Uncovered
Bullet list of explicit problems or frustrations the prospect mentioned.

## Objections Raised
Bullet list of objections or concerns. Include any that were resolved during the call.

## Agreed Next Steps
Numbered list of specific next actions with owners (Rep / Prospect) and any deadlines mentioned.

## Follow-up Email Draft
A ready-to-send follow-up email referencing specific things said in the call. \
Professional tone, under 200 words. Include subject line.
"""


class TranscriptBody(BaseModel):
    transcript: str = Field(min_length=50)


@router.post("/sessions/{session_id}/transcript")
async def analyze_transcript(
    session_id: int,
    body: TranscriptBody,
    db:   AsyncSession = Depends(get_db_session),
    user: User | None  = Depends(get_optional_user),
):
    session = await get_session(db, session_id)
    if session is None:
        raise HTTPException(404, "Session not found")

    name    = session.prospect_name or "the prospect"
    company = session.company_name  or "their company"

    async def generate():
        yield sse_status("Analysing transcript…")

        prompt = _PROMPT.format(
            name=name,
            company=company,
            transcript=body.transcript[:8_000],
        )

        full: list[str] = []
        try:
            async for token in stream_completion(prompt):
                full.append(token)
                yield sse_token(token)
        except RuntimeError as exc:
            yield sse_error(str(exc))
            return
        except Exception as exc:
            yield sse_error(f"LLM error: {repr(exc)}")
            return

        # Persist the follow-up email section if we can extract it
        if full:
            text = "".join(full)
            if "## Follow-up Email Draft" in text:
                email_section = text.split("## Follow-up Email Draft", 1)[1].strip()
                try:
                    await upsert_followup_email(db, session_id, email_md=email_section)
                except Exception as exc:
                    print(f"[transcript] Persist follow-up failed: {repr(exc)}")

        yield sse_done()

    return StreamingResponse(generate(), media_type="text/event-stream")
