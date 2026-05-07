from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_session
from app.models import Source, Chunk

router = APIRouter()

@router.get("/company/source/{source_id}")
async def get_source(source_id: int, db: AsyncSession = Depends(get_session)):
    res = await db.execute(select(Source).where(Source.id == source_id))
    s = res.scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Source not found")
    return {"id": s.id, "url": s.url, "raw_text": s.raw_text, "created_at": s.created_at}

@router.get("/company/source/{source_id}/chunks")
async def get_chunks(source_id: int, db: AsyncSession = Depends(get_session)):
    res = await db.execute(
        select(Chunk).where(Chunk.source_id == source_id).order_by(Chunk.chunk_index.asc())
    )
    rows = res.scalars().all()
    return [{"chunk_index": c.chunk_index, "chunk_text": c.chunk_text} for c in rows]