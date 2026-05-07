from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import Source, Chunk

async def create_source(db: AsyncSession, url: str, raw_text: str):
    s = Source(url=url, raw_text=raw_text)
    db.add(s)
    await db.flush()
    return s

async def create_chunks(db: AsyncSession, source_id: int, chunks: list[str]):
    for i, ch in enumerate(chunks):
        db.add(Chunk(source_id=source_id, chunk_index=i, chunk_text=ch))
    await db.flush()

async def get_source_by_url(db: AsyncSession, url: str):
    res = await db.execute(select(Source).where(Source.url == url).limit(1))
    row = res.first()
    return row[0] if row else None