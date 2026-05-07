from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, HttpUrl
import httpx, trafilatura

from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_session
from app.crud_ingest import create_source, create_chunks, get_source_by_url

router = APIRouter()

class IngestBody(BaseModel):
    url: HttpUrl
    force: bool = False          # if true, re-ingest even if exists
    chunk_size: int = 900        # approx characters (simple + works)
    overlap: int = 120

def chunk_text(text: str, chunk_size: int = 900, overlap: int = 120) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunks.append(text[start:end])
        if end == n:
            break
        start = max(0, end - overlap)
    return chunks

@router.post("/company/ingest")
async def ingest_company(body: IngestBody, db: AsyncSession = Depends(get_session)):
    url = str(body.url)

    # If already ingested and not forcing, return existing info
    existing = await get_source_by_url(db, url)
    if existing and not body.force:
        return {
            "status": "exists",
            "source_id": existing.id,
            "url": existing.url,
            "raw_text_len": len(existing.raw_text or ""),
            "message": "Already ingested. Use force=true to re-ingest.",
        }

    # Fetch HTML
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as c:
            r = await c.get(url)
            r.raise_for_status()
            html = r.text
    except httpx.ConnectError:
        raise HTTPException(503, "Could not reach target URL.")
    except httpx.ReadTimeout:
        raise HTTPException(504, "Timed out while fetching the page.")
    except httpx.HTTPStatusError as e:
        raise HTTPException(400, f"Error fetching page: {e.response.status_code}")

    # Extract text
    text = trafilatura.extract(html, favor_recall=True) or ""
    if not text.strip():
        raise HTTPException(400, "Could not extract readable text from page")

    # Chunk
    chunks = chunk_text(text, chunk_size=body.chunk_size, overlap=body.overlap)
    if not chunks:
        raise HTTPException(400, "Chunking produced no text chunks.")

    # Store: source + chunks in one transaction
    try:
        source = await create_source(db, url=url, raw_text=text[:200000])  # cap raw_text
        await create_chunks(db, source_id=source.id, chunks=[c[:5000] for c in chunks])  # cap each chunk
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(500, f"DB error while ingesting: {repr(e)}")

    return {
        "status": "ingested",
        "source_id": source.id,
        "url": url,
        "raw_text_len": len(text),
        "chunks_count": len(chunks),
    }