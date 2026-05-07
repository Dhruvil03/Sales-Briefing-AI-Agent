# backend/app/routes/prospect.py
"""
POST /api/research/prospect

Streams progress + LLM output as Server-Sent Events.

SSE event sequence:
  status  "Searching public sources for <name>..."
  status  "Found N sources, processing..."
  status  "Generating profile..."
  meta    {"session_id": N, "source_id": N, "sources": [...], "used_rag": bool}
  token   ... (LLM tokens)
  done

Architecture note — embeddings are intentionally NOT computed in the request path.
PyTorch holds the Python GIL during CPU inference, which freezes the asyncio event
loop and makes the entire server unresponsive.  Instead, BackgroundTasks computes
and stores embeddings AFTER the streaming response is complete.  This is the
correct production pattern:

  request path  →  fast  (web search + LLM stream, ~20-40 s)
  background    →  slow  (embed 10-20 chunks via SentenceTransformer, ~5-30 s)

The stored embeddings are used by the History semantic-search endpoint (Step 9),
not by this request.  So the user never waits for them.
"""
from __future__ import annotations

import asyncio

import numpy as np
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.models import User
from app.services.auth import get_optional_user
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import (
    create_session as crud_create_session,
    get_session as crud_get_session,
    update_session_meta,
    upsert_prospect_research,
)
from app.db import AsyncSessionLocal, get_session as get_db_session
from app.models import Chunk, Source
from app.services.cache import cache
from app.services.embeddings import embed_texts
from app.services.llm import stream_completion
from app.services.prospect_search import search_and_scrape
from app.services.sse import sse_done, sse_error, sse_meta, sse_status, sse_token

router = APIRouter()


# ── prompt ────────────────────────────────────────────────────────────────────

_PROMPT = """\
You are a sales intelligence analyst preparing a B2B sales rep for a discovery call.

Based only on the public web content provided below, build a concise, actionable \
prospect profile. Do not invent facts. If something is not in the sources, write \
"Not found in public sources."

Structure your response with these exact headings:

**Role & Seniority**
Title, scope, and level of influence (decision-maker, influencer, end-user?).

**Background**
Career path, tenure at current company, notable past roles or companies.

**Focus & Interests**
What they publicly speak, write, or post about. Recurring themes.

**Likely Pain Points**
Inferred from their role, company stage, and public signals. Be specific.

**Personalization Hooks**
2–3 specific, non-generic angles to open the conversation. Reference real things.

**Avoid**
One or two topics or approaches that would likely fall flat with this person.

---
PROSPECT: {name} at {company_name}

CONTEXT:
{context}
"""


# ── input model ───────────────────────────────────────────────────────────────

class ProspectBody(BaseModel):
    name:          str = Field(min_length=2)
    company_name:  str = Field(min_length=2)
    session_id:    int | None = None
    extra_context: str | None = None
    linkedin_url:  str | None = None


# ── helpers ───────────────────────────────────────────────────────────────────

def _chunk_text(text: str, chunk_size: int = 900, overlap: int = 120) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks, start, n = [], 0, len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunks.append(text[start:end])
        if end == n:
            break
        start = max(0, end - overlap)
    return chunks


# ── background embedding task ─────────────────────────────────────────────────

async def _embed_source_in_background(source_id: int, raw_text: str) -> None:
    """
    Runs AFTER the streaming response is complete.
    Opens its own DB session — the request's session is already closed.

    Chunks the text, embeds each chunk via SentenceTransformer, and stores
    the vectors in the chunks table for history semantic search (Step 9).

    PyTorch is allowed to hold the GIL here because this function runs in
    a background task — the HTTP response is already sent to the client.
    """
    loop = asyncio.get_event_loop()
    try:
        async with AsyncSessionLocal() as db:
            # Idempotent — skip if chunks already exist for this source
            res = await db.execute(
                select(Chunk).where(Chunk.source_id == source_id).limit(1)
            )
            if res.scalar_one_or_none() is not None:
                return

            pieces = _chunk_text(raw_text)
            if not pieces:
                return

            # Persist chunks first (without embeddings)
            chunks: list[Chunk] = []
            for i, ch in enumerate(pieces):
                c = Chunk(source_id=source_id, chunk_index=i, chunk_text=ch[:5_000])
                db.add(c)
                chunks.append(c)
            await db.flush()

            # Compute embeddings — this is the slow PyTorch step.
            # Runs in a thread executor so it doesn't block the event loop,
            # but it WILL hold the GIL.  That's acceptable here because the
            # HTTP response is already sent — no client is waiting.
            try:
                texts   = [c.chunk_text for c in chunks]
                vectors: list[list[float]] = await asyncio.wait_for(
                    loop.run_in_executor(None, embed_texts, texts),
                    timeout=60,
                )
                for chunk, vec in zip(chunks, vectors):
                    chunk.embedding = vec
                print(f"[prospect] Embedded {len(chunks)} chunks for source {source_id}")

                # ── Optional: upsert to Pinecone if configured ────────────────
                try:
                    from app.services.vector_store import upsert_chunk_embeddings
                    pinecone_items = [
                        {
                            "id": f"chunk-{source_id}-{c.chunk_index}",
                            "values": vec,
                            "metadata": {
                                "source_id": source_id,
                                "chunk_index": c.chunk_index,
                                "chunk_text": c.chunk_text[:500],
                            },
                        }
                        for c, vec in zip(chunks, vectors)
                    ]
                    await loop.run_in_executor(
                        None, upsert_chunk_embeddings, pinecone_items
                    )
                    print(f"[prospect] Upserted {len(chunks)} chunks to Pinecone for source {source_id}")
                except RuntimeError:
                    pass  # Pinecone not configured — skip silently
                except Exception as exc:
                    print(f"[prospect] Pinecone upsert failed (non-fatal): {repr(exc)}")

            except (asyncio.TimeoutError, Exception) as exc:
                print(f"[prospect] Embedding failed (chunks saved without vectors): {repr(exc)}")

            await db.commit()
    except Exception as exc:
        print(f"[prospect] Background embed task failed: {repr(exc)}")


# ── route ─────────────────────────────────────────────────────────────────────

@router.post("/research/prospect")
async def research_prospect(
    body: ProspectBody,
    db: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(get_optional_user),
):
    async def generate():
        # ── 1. Open stream immediately — no blocking work before first yield ──
        yield sse_status(f"Searching public sources for {body.name}...")

        # ── 2. Web search + scrape (Redis cache, 12 h TTL) ───────────────────
        _prospect_cache_key = (
            f"prospect_search:{body.name.lower().strip()}:"
            f"{body.company_name.lower().strip()}"
        )
        _cached_text = await cache.get(_prospect_cache_key)

        try:
            prospect_data = await search_and_scrape(
                name=body.name,
                company_name=body.company_name,
                extra_context=body.extra_context,
                cached_text=_cached_text,
                linkedin_url=body.linkedin_url,
            )
        except Exception as exc:
            yield sse_error(f"Prospect search failed: {repr(exc)}")
            return

        # Cache aggregated text for next request
        if not _cached_text and prospect_data.aggregated_text:
            await cache.set(_prospect_cache_key, prospect_data.aggregated_text, ttl=43_200)

        if prospect_data.is_empty:
            yield sse_error(
                f"No public information found for '{body.name}' at "
                f"'{body.company_name}'. Add context in the optional field."
            )
            return

        n_sources = len(prospect_data.sources_searched)
        yield sse_status(
            f"Found {n_sources} source{'s' if n_sources != 1 else ''}, processing..."
        )

        # ── 3. Session — best-effort, after first yield ───────────────────────
        session = None
        try:
            if body.session_id:
                session = await crud_get_session(db, body.session_id)
            else:
                session = await crud_create_session(
                    db,
                    company_name=body.company_name,
                    prospect_name=body.name,
                    user_id=user.id if user else None,
                )
        except Exception as exc:
            print(f"[prospect] Session create failed (non-fatal): {repr(exc)}")

        # ── 4. Store Source row (text only, no vectors yet) ───────────────────
        #
        # Embeddings are computed by _embed_source_in_background() AFTER the
        # stream ends.  The stored vectors enable history semantic search (Step 9).
        source_key = (
            f"prospect:{body.name}:{body.company_name}"
            .lower()
            .replace(" ", "-")
        )
        source = None
        try:
            res = await db.execute(
                select(Source).where(Source.url == source_key).limit(1)
            )
            source = res.scalar_one_or_none()
            if source is None:
                source = Source(
                    url=source_key,
                    raw_text=prospect_data.aggregated_text[:200_000],
                )
                db.add(source)
                await db.flush()
                await db.commit()
        except Exception as exc:
            print(f"[prospect] Store source failed (non-fatal): {repr(exc)}")

        # ── 5. Context for LLM (full text, no RAG needed — fits in 128k ctx) ──
        aggregated = prospect_data.aggregated_text
        context    = aggregated[:12_000]

        # ── 6. Metadata event ─────────────────────────────────────────────────
        yield sse_meta({
            "session_id":       session.id if session else None,
            "source_id":        source.id if source else None,
            "sources_searched": prospect_data.sources_searched,
            "used_rag":         False,
            "total_chars":      prospect_data.total_chars,
        })

        # ── 7. Stream LLM tokens ──────────────────────────────────────────────
        yield sse_status("Generating profile...")

        prompt = _PROMPT.format(
            name=body.name,
            company_name=body.company_name,
            context=context,
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

        # ── 8. Persist insights ───────────────────────────────────────────────
        if session is not None:
            try:
                await upsert_prospect_research(
                    db,
                    session.id,
                    sources_searched=prospect_data.sources_searched,
                    aggregated_text=aggregated[:50_000],
                    insights="".join(full_text),
                    source_id=source.id if source else None,
                )
                await update_session_meta(db, session.id, prospect_name=body.name)
            except Exception as exc:
                print(f"[prospect] Persist failed (non-fatal): {repr(exc)}")

        # ── 9. Schedule background embedding ─────────────────────────────────
        #
        # asyncio.create_task() is used here instead of BackgroundTasks because
        # tasks added to BackgroundTasks inside a StreamingResponse generator are
        # never executed — FastAPI checks for tasks before the generator runs.
        #
        # create_task() schedules the coroutine on the running event loop
        # immediately, so it starts after the current yield completes.
        if source is not None:
            asyncio.create_task(
                _embed_source_in_background(
                    source.id,
                    prospect_data.aggregated_text,
                )
            )

        yield sse_done()

    return StreamingResponse(generate(), media_type="text/event-stream")
