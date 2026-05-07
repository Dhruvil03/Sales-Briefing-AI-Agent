from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import numpy as np

from app.db import get_session
from app.models import Chunk
from app.services.embeddings import embed_texts

router = APIRouter()

def cosine(a: np.ndarray, b: np.ndarray) -> float:
    # embeddings are normalized, so cosine is dot product
    return float(np.dot(a, b))

@router.get("/search")
async def search(q: str, top_k: int = 5, source_id: int | None = None, db: AsyncSession = Depends(get_session)):
    if not q.strip():
        raise HTTPException(400, "q is required")

    query_vec = np.array(embed_texts([q])[0], dtype=float)

    stmt = select(Chunk).where(Chunk.embedding.is_not(None))
    if source_id is not None:
        stmt = stmt.where(Chunk.source_id == source_id)

    res = await db.execute(stmt)
    chunks = res.scalars().all()
    if not chunks:
        raise HTTPException(400, "No embedded chunks found. Run /company/source/{id}/embed first.")

    scored = []
    for c in chunks:
        v = np.array(c.embedding, dtype=float)
        scored.append((cosine(query_vec, v), c))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[: max(1, min(top_k, 20))]

    return [
        {
            "score": round(score, 4),
            "source_id": c.source_id,
            "chunk_index": c.chunk_index,
            "chunk_text": c.chunk_text,
        }
        for score, c in top
    ]