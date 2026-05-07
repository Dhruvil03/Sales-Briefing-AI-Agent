# backend/app/routes/search.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_session
from app.models import Chunk
from app.services.embeddings import embed_texts
from app.services.vector_store import query_similar

router = APIRouter()

class PineconeSearchBody(BaseModel):
    query: str
    source_id: int | None = None   # optional filter (company/prospect source)
    top_k: int = 5

@router.post("/search/pinecone")
async def search_pinecone(body: PineconeSearchBody, db: AsyncSession = Depends(get_session)):
    if not body.query.strip():
        raise HTTPException(400, "Query cannot be empty.")

    qv = embed_texts([body.query])[0]

    pinecone_filter = None
    if body.source_id is not None:
        pinecone_filter = {"source_id": {"$eq": body.source_id}}

    res = query_similar(
        query_vector=qv,
        top_k=max(1, min(body.top_k, 10)),
        filter=pinecone_filter,
    )

    matches = res.get("matches") if isinstance(res, dict) else getattr(res, "matches", None)
    if not matches:
        return {"matches": []}

    # Resolve chunk_text from DB using metadata.chunk_id
    out = []
    for m in matches:
        md = m.get("metadata") if isinstance(m, dict) else getattr(m, "metadata", {}) or {}
        score = m.get("score") if isinstance(m, dict) else getattr(m, "score", None)

        chunk_id = md.get("chunk_id")
        if chunk_id is None:
            # fallback: return metadata preview
            out.append({"score": score, "metadata": md})
            continue

        row = await db.execute(select(Chunk).where(Chunk.id == int(chunk_id)).limit(1))
        ch = row.scalar_one_or_none()
        if not ch:
            out.append({"score": score, "metadata": md})
            continue

        out.append({
            "score": float(score) if score is not None else None,
            "chunk_id": ch.id,
            "source_id": ch.source_id,
            "chunk_index": ch.chunk_index,
            "chunk_text": ch.chunk_text,
        })

    return {"matches": out}