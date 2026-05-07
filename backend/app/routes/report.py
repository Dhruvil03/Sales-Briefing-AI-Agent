# backend/app/routes/report.py
"""
POST /api/report/precall        ← streaming SSE (primary)
POST /api/report/precall_rag    ← non-streaming, RAG-based (legacy, kept as-is)

The primary endpoint takes company summary text + prospect insights text,
builds a structured pre-call briefing, and streams it token by token.

Optionally accepts session_id to persist the report to the right session.

SSE event sequence:
  meta    {"session_id": N}   (only when session_id provided)
  token   ... (LLM tokens)
  done
"""
from __future__ import annotations

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import create_run, upsert_report
from app.db import get_session as get_db_session
from app.models import Chunk
from app.services.embeddings import embed_texts
from app.services.llm import stream_completion
from app.services.sse import sse_done, sse_error, sse_meta, sse_token
from app.services.vector_store import query_similar

router = APIRouter()


# ── prompt ────────────────────────────────────────────────────────────────────

_PROMPT = """\
You are an expert sales enablement writer.
Create a crisp, actionable pre-call briefing using the inputs below.

Rules:
- Use gender-neutral language for the prospect.
- Only use facts present in the provided context. If something is not in context,
  write "Not specified in sources."
- Be specific — avoid generic platitudes.

TONE: {tone}

SECTIONS (use clear headings and bullet points):
1) **Snapshot**
   - Who the company is, what they do, 2–3 recent or strategic notes
   - Prospect role and seniority, 2–3 interests or focus areas

2) **Talking Points** (5 bullets)

3) **Personalized Hooks** (3 bullets — specific, non-generic)

4) **Likely Objections & Short Answers** (3 bullets)

5) **CTA** (1–2 lines — clear next step)

---
[COMPANY]
{company}

[PROSPECT]
{prospect}
"""


# ── input models ──────────────────────────────────────────────────────────────

class PrecallBody(BaseModel):
    company:    str       = Field(min_length=10, description="Company summary or notes")
    prospect:   str       = Field(min_length=10, description="Prospect insights or notes")
    tone:       str | None = Field(default="concise, friendly, expert")
    session_id: int | None = None   # optional — saves report to existing session


class PrecallRagBody(BaseModel):
    company_source_id:  int
    prospect_source_id: int
    tone:  str | None = Field(default="concise, friendly, expert")
    top_k: int  = 5
    debug: bool = False


# ── primary streaming route ───────────────────────────────────────────────────

@router.post("/report/precall")
async def generate_precall(
    body: PrecallBody,
    db: AsyncSession = Depends(get_db_session),
):
    async def generate():
        # Optional metadata event if session context exists
        if body.session_id is not None:
            yield sse_meta({"session_id": body.session_id})

        prompt = _PROMPT.format(
            company=body.company[:20_000],
            prospect=body.prospect[:20_000],
            tone=body.tone or "concise, friendly, expert",
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

        # Persist after stream completes
        report_md = "".join(full_text)
        if report_md:
            try:
                if body.session_id:
                    await upsert_report(db, body.session_id, report_md=report_md, tone=body.tone)
                else:
                    # Legacy persist for backwards compatibility
                    await create_run(
                        db,
                        run_type="precall_report",
                        input_text=(body.company[:8_000] + "\n\n" + body.prospect[:8_000]),
                        output_text=report_md,
                        source=None,
                    )
            except Exception as exc:
                print(f"[report] Persist warning: {repr(exc)}")

        yield sse_done()

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── legacy RAG route (non-streaming, kept as-is) ──────────────────────────────

def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


async def _ensure_source_embeddings(db: AsyncSession, source_id: int) -> int:
    res = await db.execute(select(Chunk).where(Chunk.source_id == source_id))
    chunks = list(res.scalars().all())
    if not chunks:
        return 0
    missing = [c for c in chunks if not getattr(c, "embedding", None)]
    if not missing:
        return 0
    vecs = embed_texts([c.chunk_text for c in missing])
    for c, v in zip(missing, vecs):
        c.embedding = v
    await db.commit()
    return len(missing)


async def _local_retrieve(
    db: AsyncSession, query: str, source_id: int, top_k: int
) -> list[dict]:
    res = await db.execute(
        select(Chunk).where(
            Chunk.source_id == source_id,
            Chunk.embedding.isnot(None),
        )
    )
    chunks = list(res.scalars().all())
    if not chunks:
        return []
    qv = np.array(embed_texts([query])[0], dtype=float)
    scored = [(float(np.dot(qv, np.array(c.embedding, dtype=float))), c) for c in chunks]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {"score": s, "chunk_index": c.chunk_index, "chunk_text": c.chunk_text}
        for s, c in scored[:max(1, min(top_k, 20))]
    ]


async def _pinecone_retrieve(
    db: AsyncSession, query: str, source_id: int, top_k: int
) -> tuple[list[dict], str | None]:
    try:
        qv = embed_texts([query])[0]
        res = query_similar(
            query_vector=qv,
            top_k=max(1, min(top_k, 10)),
            filter={"source_id": {"$eq": source_id}},
        )
        matches = res.get("matches") if isinstance(res, dict) else getattr(res, "matches", None)
        if not matches:
            return [], None
        hits = []
        for m in matches:
            md    = m.get("metadata") if isinstance(m, dict) else getattr(m, "metadata", {}) or {}
            score = m.get("score")    if isinstance(m, dict) else getattr(m, "score", None)
            chunk_id = md.get("chunk_id")
            if chunk_id is None:
                hits.append({"score": float(score or 0), "chunk_index": None, "chunk_text": md.get("chunk_text", "")})
                continue
            row = await db.execute(select(Chunk).where(Chunk.id == int(chunk_id)).limit(1))
            ch  = row.scalar_one_or_none()
            hits.append({
                "score":       float(score or 0),
                "chunk_index": ch.chunk_index if ch else md.get("chunk_index"),
                "chunk_text":  ch.chunk_text  if ch else md.get("chunk_text", ""),
            })
        return hits, None
    except Exception as exc:
        return [], repr(exc)


@router.post("/report/precall_rag")
async def generate_precall_rag(
    body: PrecallRagBody,
    db: AsyncSession = Depends(get_db_session),
):
    top_k = max(1, min(body.top_k, 10))

    try:
        await _ensure_source_embeddings(db, body.company_source_id)
        await _ensure_source_embeddings(db, body.prospect_source_id)
    except Exception as exc:
        raise HTTPException(500, f"Embedding step failed: {repr(exc)}")

    company_q  = "What the organization does, key services, who they serve, strategic notes."
    prospect_q = "Current title, seniority, skills, goals, and 2 personalization hooks."

    company_hits,  company_err  = await _pinecone_retrieve(db, company_q,  body.company_source_id,  top_k)
    prospect_hits, prospect_err = await _pinecone_retrieve(db, prospect_q, body.prospect_source_id, top_k)

    used = {"company": "pinecone", "prospect": "pinecone"}

    if not company_hits:
        company_hits  = await _local_retrieve(db, company_q,  body.company_source_id,  top_k)
        used["company"] = "local_db"
    if not prospect_hits:
        prospect_hits = await _local_retrieve(db, prospect_q, body.prospect_source_id, top_k)
        used["prospect"] = "local_db"

    if not company_hits:
        raise HTTPException(400, "No company chunks found. Ingest and embed the company source first.")
    if not prospect_hits:
        raise HTTPException(400, "No prospect chunks found. Upload and embed the prospect PDF first.")

    company_ctx  = "\n\n---\n\n".join(h["chunk_text"] for h in company_hits)[:12_000]
    prospect_ctx = "\n\n---\n\n".join(h["chunk_text"] for h in prospect_hits)[:12_000]

    prompt = _PROMPT.format(
        company=company_ctx,
        prospect=prospect_ctx,
        tone=body.tone or "concise, friendly, expert",
    )

    from app.services.llm import complete
    try:
        report_md = await complete(prompt)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"LLM error: {repr(exc)}")

    if not report_md:
        raise HTTPException(502, "LLM returned an empty response.")

    try:
        await create_run(
            db,
            run_type="precall_report_rag",
            input_text=(company_ctx[:9_000] + "\n\n" + prospect_ctx[:9_000]),
            output_text=report_md,
            source=f"company:{body.company_source_id}|prospect:{body.prospect_source_id}",
        )
    except Exception as exc:
        print(f"[report_rag] Persist warning: {repr(exc)}")

    resp: dict = {"report_md": report_md}
    if body.debug:
        resp["rag"] = {
            "retrieval_used":           used,
            "company_top":              [{"score": round(h["score"], 4), "chunk_index": h["chunk_index"]} for h in company_hits],
            "prospect_top":             [{"score": round(h["score"], 4), "chunk_index": h["chunk_index"]} for h in prospect_hits],
            "company_context_preview":  company_ctx[:600],
            "prospect_context_preview": prospect_ctx[:600],
            "pinecone_error_company":   company_err,
            "pinecone_error_prospect":  prospect_err,
        }
    return resp
