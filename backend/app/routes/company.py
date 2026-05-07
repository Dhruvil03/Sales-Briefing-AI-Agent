# backend/app/routes/company.py
"""
POST /api/company/summary

Crawls a company website, extracts readable text, and streams an LLM-generated
summary as Server-Sent Events.

No RAG here — a single homepage is ~3-5k tokens, well within the 128k context
window. Sending the full text gives the LLM more signal than chunked retrieval.

SSE event sequence:
  status  "Fetching website..."
  status  "Analysing..."
  meta    {"session_id": N, "source_id": N}
  token   ... (LLM tokens)
  done
"""
from __future__ import annotations

import trafilatura
import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import create_session as crud_create_session, upsert_company_research
from app.db import get_session as get_db_session
from app.models import Source, User
from app.services.auth import get_optional_user
from app.services.cache import cache
from app.services.llm import stream_completion
from app.services.sse import sse_done, sse_error, sse_meta, sse_status, sse_token

router = APIRouter()

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


class Body(BaseModel):
    url:     HttpUrl
    bullets: int = 6


_PROMPT = """\
Summarize this company's website in {bullets} concise bullet points.

Cover: what they do, their ideal customer profile (ICP), key products or services, \
pricing signals (if any), tech stack signals, and any recent strategic notes.

Be specific — avoid generic statements like "they are a leading company."

COMPANY URL: {url}

WEBSITE CONTENT:
{context}
"""


async def _get_or_create_source(db: AsyncSession, url: str, raw_text: str) -> Source:
    res = await db.execute(select(Source).where(Source.url == url).limit(1))
    existing = res.scalar_one_or_none()
    if existing:
        return existing
    source = Source(url=url, raw_text=raw_text[:200_000])
    db.add(source)
    await db.flush()
    await db.commit()
    return source


@router.post("/company/summary")
async def company_summary(
    body: Body,
    db: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(get_optional_user),
):
    url = str(body.url)

    async def generate():
        # ── 1. Fetch (with Redis cache, 24 h TTL) ─────────────────────────────
        _cache_key = f"company_text:{url}"
        yield sse_status("Fetching company website...")

        text = await cache.get(_cache_key)
        if text:
            yield sse_status("Analysing company (cached)...")
        else:
            try:
                async with httpx.AsyncClient(
                    follow_redirects=True,
                    timeout=httpx.Timeout(30.0, connect=15.0),
                    headers=_HEADERS,
                ) as client:
                    r = await client.get(url)
                    r.raise_for_status()
                    html = r.text
            except httpx.ConnectError:
                yield sse_error(f"Could not reach {url}. Check the URL and try again.")
                return
            except httpx.ReadTimeout:
                yield sse_error("The page took too long to respond.")
                return
            except httpx.HTTPStatusError as exc:
                yield sse_error(f"HTTP {exc.response.status_code} while fetching the page.")
                return
            except Exception as exc:
                yield sse_error(f"Fetch failed: {repr(exc)}")
                return

            # ── 2. Extract readable text ──────────────────────────────────────
            text = trafilatura.extract(html, favor_recall=True) or ""
            if not text.strip():
                yield sse_error("Could not extract readable text from this page.")
                return

            await cache.set(_cache_key, text, ttl=86_400)  # 24 h

        yield sse_status("Analysing company...")

        # ── 3. Persist Source + Session (best-effort) ─────────────────────────
        session_id: int | None = None
        source_id:  int | None = None
        try:
            source  = await _get_or_create_source(db, url, text)
            session = await crud_create_session(db, company_url=url, user_id=user.id if user else None)
            session_id = session.id
            source_id  = source.id
        except Exception as exc:
            print(f"[company] Session/source persist warning: {repr(exc)}")

        # ── 4. Metadata event ─────────────────────────────────────────────────
        yield sse_meta({"session_id": session_id, "source_id": source_id})

        # ── 5. Build prompt ───────────────────────────────────────────────────
        prompt = _PROMPT.format(
            bullets=body.bullets,
            url=url,
            context=text[:12_000],
        )

        # ── 6. Stream LLM tokens ──────────────────────────────────────────────
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

        # ── 7. Persist generated summary (after stream) ───────────────────────
        if session_id and full_text:
            try:
                await upsert_company_research(
                    db,
                    session_id,
                    raw_text=text[:50_000],
                    summary="".join(full_text),
                    source_id=source_id,
                )
            except Exception as exc:
                print(f"[company] Summary persist warning: {repr(exc)}")

        yield sse_done()

    return StreamingResponse(generate(), media_type="text/event-stream")
