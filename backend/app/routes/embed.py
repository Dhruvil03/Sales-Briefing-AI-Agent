from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_session
from app.models import Chunk
from app.services.embeddings import embed_texts

router = APIRouter()


async def embed_source_chunks_core(
    db: AsyncSession,
    source_id: int,
    force: bool = False,
) -> dict:
    """
    SMART-FORCE behavior:
    - Always ensure Postgres has embeddings (compute only missing).
    - force=False: upsert ONLY chunks that were embedded in this request.
    - force=True: upsert ALL chunks that already have embeddings (no recompute).
      (Safe: Pinecone upsert overwrites by vector id, no duplicates.)
    """
    res = await db.execute(
        select(Chunk)
        .where(Chunk.source_id == source_id)
        .order_by(Chunk.chunk_index.asc())
    )
    chunks = list(res.scalars().all())
    if not chunks:
        raise HTTPException(404, "No chunks found for this source_id")

    # 1) Compute embeddings only for missing ones
    missing = [c for c in chunks if not getattr(c, "embedding", None)]
    newly_embedded: list[Chunk] = []

    if missing:
        texts = [c.chunk_text for c in missing]
        vectors = embed_texts(texts)

        for c, v in zip(missing, vectors):
            c.embedding = v
            newly_embedded.append(c)

        await db.commit()

    embedded_now = len(newly_embedded)

    # 2) Decide what to upsert to Pinecone
    if force:
        # upsert everything that has an embedding in Postgres
        to_upsert = [c for c in chunks if getattr(c, "embedding", None)]
    else:
        # only the ones we just computed now
        to_upsert = newly_embedded

    pinecone_upserted = 0
    pinecone_error = None

    if to_upsert:
        try:
            from app.services.vector_store import upsert_chunk_embeddings

            items = []
            for c in to_upsert:
                items.append(
                    {
                        "id": f"chunk:{c.id}",  # stable ID => no duplicates
                        "values": c.embedding,
                        "metadata": {
                            "chunk_id": c.id,
                            "source_id": c.source_id,
                            "chunk_index": c.chunk_index,
                            "chunk_text": (c.chunk_text or "")[:1000],
                        },
                    }
                )

            upsert_chunk_embeddings(items)
            pinecone_upserted = len(items)

        except Exception as e:
            pinecone_error = repr(e)
            print("Warning: Pinecone upsert failed:", pinecone_error)

    return {
        "status": "ok",
        "source_id": source_id,
        "embedded_now": embedded_now,
        "total_chunks": len(chunks),
        "pinecone_upserted": pinecone_upserted,
        "force": force,
        "pinecone_error": pinecone_error,
    }


@router.post("/company/source/{source_id}/embed")
async def embed_source_chunks(
    source_id: int,
    force: bool = Query(False),
    db: AsyncSession = Depends(get_session),
):
    return await embed_source_chunks_core(db, source_id, force=force)

# from fastapi import APIRouter, Depends, HTTPException
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy import select

# from app.db import get_session
# from app.models import Chunk
# from app.services.embeddings import embed_texts

# router = APIRouter()


# @router.post("/company/source/{source_id}/embed")
# async def embed_source_chunks(source_id: int, db: AsyncSession = Depends(get_session)):
#     res = await db.execute(
#         select(Chunk)
#         .where(Chunk.source_id == source_id)
#         .order_by(Chunk.chunk_index.asc())
#     )
#     chunks = list(res.scalars().all())
#     if not chunks:
#         raise HTTPException(404, "No chunks found for this source_id")

#     # Only embed missing ones (fast)
#     to_embed = [c for c in chunks if not getattr(c, "embedding", None)]
#     if not to_embed:
#         return {
#             "status": "ok",
#             "source_id": source_id,
#             "embedded_now": 0,
#             "total_chunks": len(chunks),
#             "pinecone_upserted": 0,
#         }

#     texts = [c.chunk_text for c in to_embed]
#     vectors = embed_texts(texts)

#     # 1) Save embeddings to Postgres
#     for c, v in zip(to_embed, vectors):
#         c.embedding = v

#     await db.commit()

#     # 2) Upsert to Pinecone (best-effort)
#     pinecone_upserted = 0
#     try:
#         from app.services.vector_store import upsert_chunk_embeddings

#         items = []
#         for c, v in zip(to_embed, vectors):
#             items.append(
#                 {
#                     "id": f"chunk:{c.id}",
#                     "values": v,
#                     "metadata": {
#                         "chunk_id": c.id,
#                         "source_id": c.source_id,
#                         "chunk_index": c.chunk_index,
#                         "chunk_text": c.chunk_text[:1000],
#                     },
#                 }
#             )

#         upsert_chunk_embeddings(items)
#         pinecone_upserted = len(items)

#     except Exception as e:
#         print("Warning: Pinecone upsert failed:", repr(e))

#     return {
#         "status": "ok",
#         "source_id": source_id,
#         "embedded_now": len(to_embed),
#         "total_chunks": len(chunks),
#         "pinecone_upserted": pinecone_upserted,
#     }