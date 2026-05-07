from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import numpy as np
from app.models import Chunk
from app.services.embeddings import embed_texts

def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))  # vectors are normalized

async def retrieve_chunks(db: AsyncSession, query: str, source_id: int | None = None, top_k: int = 5):
    qv = np.array(embed_texts([query])[0], dtype=float)

    stmt = select(Chunk).where(Chunk.embedding.is_not(None))
    if source_id is not None:
        stmt = stmt.where(Chunk.source_id == source_id)

    res = await db.execute(stmt)
    chunks = res.scalars().all()

    scored = []
    for c in chunks:
        v = np.array(c.embedding, dtype=float)
        scored.append((cosine(qv, v), c))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[: max(1, min(top_k, 20))]

    return [{"score": s, "chunk_text": c.chunk_text, "chunk_index": c.chunk_index, "source_id": c.source_id} for s, c in top]