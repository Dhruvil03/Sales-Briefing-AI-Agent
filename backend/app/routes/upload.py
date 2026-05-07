# backend/app/routes/upload.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from PyPDF2 import PdfReader
from io import BytesIO
import os, httpx, hashlib
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_session
from app.crud import create_run
from app.models import Source, Chunk
from app.services.embeddings import embed_texts

# Pinecone helper
from app.services.vector_store import query_similar_chunks

# embed core (ensures postgres embeddings + upsert logic)
from app.routes.embed import embed_source_chunks_core

router = APIRouter()
OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL = os.getenv("OLLAMA_MODEL", "llama3:8b")


def pdf_to_text(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 120) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunks.append(text[start:end])
        if end == n:
            break
        start = max(0, end - overlap)
    return chunks


async def get_or_create_source(db: AsyncSession, url: str, raw_text: str) -> Source:
    res = await db.execute(select(Source).where(Source.url == url).limit(1))
    existing = res.scalar_one_or_none()
    if existing:
        return existing
    s = Source(url=url, raw_text=(raw_text or "")[:200000])
    db.add(s)
    await db.flush()
    return s


async def get_chunks_for_source(db: AsyncSession, source_id: int) -> list[Chunk]:
    res = await db.execute(
        select(Chunk)
        .where(Chunk.source_id == source_id)
        .order_by(Chunk.chunk_index.asc())
    )
    return list(res.scalars().all())


@router.post("/prospect/upload")
async def prospect_upload(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Please upload a PDF file.")

    data = await file.read()
    text = pdf_to_text(data)
    if len(text) < 120:
        raise HTTPException(400, "Could not extract enough text from PDF.")

    # stable key so re-uploads don't duplicate
    digest = hashlib.sha1(data).hexdigest()[:12]
    source_key = f"pdf:{file.filename}:{digest}"

    source = None
    context = text[:12000]

    try:
        # 1) Store source + chunks
        source = await get_or_create_source(db, url=source_key, raw_text=text)

        chunks = await get_chunks_for_source(db, source.id)
        if not chunks:
            pieces = chunk_text(text, chunk_size=900, overlap=120)
            for i, ch in enumerate(pieces):
                db.add(Chunk(source_id=source.id, chunk_index=i, chunk_text=ch[:5000]))
            await db.commit()
            chunks = await get_chunks_for_source(db, source.id)

        # 2) Ensure embeddings + upsert to Pinecone (smart core)
        try:
            await embed_source_chunks_core(db, source.id, force=False)
        except Exception as e:
            # non-fatal: we still continue with best-effort retrieval
            print("Warning: embed_core failed for prospect upload:", repr(e))

        # 3) Retrieve relevant prospect context via Pinecone
        retrieval_query = (
            "Extract prospect insights: role & seniority, responsibilities, interests, current focus, "
            "possible pains, and 1–2 personalized hooks."
        )

        try:
            qv = embed_texts([retrieval_query])[0]
            matches = query_similar_chunks(query_vector=qv, top_k=5, source_id=source.id)
            # matches are pinecone-style objects; metadata.chunk_text used when available
            top_chunks = [m.get("metadata", {}).get("chunk_text", "") for m in matches]
            if top_chunks and any(top_chunks):
                context = "\n\n---\n\n".join(top_chunks)[:12000]
            else:
                # fallback to local chunks text
                context = text[:12000]
        except Exception as e:
            print("Warning: Pinecone query failed for prospect upload:", repr(e))
            context = text[:12000]

    except Exception as e:
        print("Warning: PDF RAG prep failed, falling back to raw text:", repr(e))
        context = text[:12000]

    # 4) Ask Ollama to produce clean bullets from retrieved context
    prompt = (
        "Extract prospect insights in concise bullets: role & seniority, interests, current focus, "
        "possible pains, and 1–2 personalized hooks. Return 5–7 bullets.\n\n"
        f"CONTEXT:\n{context}"
    )

    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(
            f"{OLLAMA_BASE}/api/generate",
            json={"model": MODEL, "prompt": prompt, "stream": False},
        )
        if r.status_code == 404:
            r = await c.post(
                f"{OLLAMA_BASE}/api/chat",
                json={"model": MODEL, "messages": [{"role": "user", "content": prompt}], "stream": False},
            )
        r.raise_for_status()
        out = r.json()

    summary = (out.get("response") or out.get("message", {}).get("content") or "").strip()

    # 5) Persist run (best-effort)
    try:
        await create_run(
            db,
            run_type="prospect_upload_rag",
            input_text=context[:20000],
            output_text=summary,
            source=source_key,
        )
    except Exception as e:
        print("Warning: persist failed (prospect_upload_rag):", repr(e))

    return {
        "summary": summary,
        "prospect_source_id": (source.id if source else None),
        "source_key": source_key,
    }

# from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
# from PyPDF2 import PdfReader
# from io import BytesIO
# import os, httpx, hashlib
# import numpy as np
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy import select

# from app.db import get_session
# from app.crud import create_run
# from app.models import Source, Chunk
# from app.services.embeddings import embed_texts

# from app.services.vector_store import upsert_chunk_embeddings

# router = APIRouter()
# OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
# MODEL = os.getenv("OLLAMA_MODEL", "llama3:8b")


# def pdf_to_text(content: bytes) -> str:
#     reader = PdfReader(BytesIO(content))
#     return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


# def cosine(a: np.ndarray, b: np.ndarray) -> float:
#     return float(np.dot(a, b))  # normalized vectors => cosine == dot


# def chunk_text(text: str, chunk_size: int = 900, overlap: int = 120) -> list[str]:
#     text = (text or "").strip()
#     if not text:
#         return []
#     chunks: list[str] = []
#     start = 0
#     n = len(text)
#     while start < n:
#         end = min(start + chunk_size, n)
#         chunks.append(text[start:end])
#         if end == n:
#             break
#         start = max(0, end - overlap)
#     return chunks


# async def get_or_create_source(db: AsyncSession, url: str, raw_text: str) -> Source:
#     res = await db.execute(select(Source).where(Source.url == url).limit(1))
#     existing = res.scalar_one_or_none()
#     if existing:
#         return existing
#     s = Source(url=url, raw_text=(raw_text or "")[:200000])
#     db.add(s)
#     await db.flush()  # populate id
#     return s


# async def get_chunks_for_source(db: AsyncSession, source_id: int) -> list[Chunk]:
#     res = await db.execute(
#         select(Chunk)
#         .where(Chunk.source_id == source_id)
#         .order_by(Chunk.chunk_index.asc())
#     )
#     return list(res.scalars().all())


# # async def ensure_embeddings(db: AsyncSession, chunks: list[Chunk]) -> int:
# #     missing = [c for c in chunks if not getattr(c, "embedding", None)]
# #     if not missing:
# #         return 0
# #     vecs = embed_texts([c.chunk_text for c in missing])

    
# #     #pincone upsert
# #     items = []
# #     for c, v in zip(missing, vecs):
# #         c.embedding = v
# #         items.append({
# #             "id": f"chunk:{c.id}",          # pinecone vector id
# #             "values": v,
# #             "metadata": {
# #                 "chunk_id": c.id,
# #                 "source_id": c.source_id,
# #                 "chunk_index": c.chunk_index,
# #                 "chunk_text": c.chunk_text[:1000],
# #             }
# #         })
# #     await db.commit()
# #     upsert_chunk_embeddings(items)

# #     for c, v in zip(missing, vecs):
# #         c.embedding = v
# #     await db.commit()
# #     return len(missing)

# async def ensure_embeddings(db: AsyncSession, chunks: list[Chunk]) -> int:
#     missing = [c for c in chunks if not getattr(c, "embedding", None)]
#     if not missing:
#         return 0

#     vecs = embed_texts([c.chunk_text for c in missing])

#     # 1) Save embeddings to Postgres
#     for c, v in zip(missing, vecs):
#         c.embedding = v

#     await db.commit()  # commit once

#     # 2) Upsert to Pinecone (best-effort; don't fail request if Pinecone is down)
#     try:
#         from app.services.vector_store import upsert_chunk_embeddings

#         items = []
#         for c, v in zip(missing, vecs):
#             items.append(
#                 {
#                     "id": f"chunk:{c.id}",  # pinecone vector id
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

#     except Exception as e:
#         print("Warning: Pinecone upsert failed:", repr(e))

#     return len(missing)


# async def retrieve_top_chunks(db: AsyncSession, query: str, source_id: int, top_k: int = 5) -> list[str]:
#     res = await db.execute(
#         select(Chunk).where(
#             Chunk.source_id == source_id,
#             Chunk.embedding.is_not(None),
#         )
#     )
#     chunks = list(res.scalars().all())
#     if not chunks:
#         return []

#     qv = np.array(embed_texts([query])[0], dtype=float)

#     scored: list[tuple[float, Chunk]] = []
#     for c in chunks:
#         v = np.array(c.embedding, dtype=float)
#         scored.append((cosine(qv, v), c))

#     scored.sort(key=lambda x: x[0], reverse=True)
#     top = scored[: max(1, min(top_k, 20))]
#     return [c.chunk_text for score, c in top]


# @router.post("/prospect/upload")
# async def prospect_upload(
#     file: UploadFile = File(...),
#     db: AsyncSession = Depends(get_session),
# ):
#     if not file.filename.lower().endswith(".pdf"):
#         raise HTTPException(400, "Please upload a PDF file.")

#     data = await file.read()
#     text = pdf_to_text(data)
#     if len(text) < 120:
#         raise HTTPException(400, "Could not extract enough text from PDF.")

#     # Make a stable "url" key so re-uploading same PDF doesn't duplicate
#     digest = hashlib.sha1(data).hexdigest()[:12]
#     source_key = f"pdf:{file.filename}:{digest}"

#     # 1) Store source + chunks
#     try:
#         source = await get_or_create_source(db, url=source_key, raw_text=text)

#         chunks = await get_chunks_for_source(db, source.id)
#         if not chunks:
#             pieces = chunk_text(text, chunk_size=900, overlap=120)
#             for i, ch in enumerate(pieces):
#                 db.add(Chunk(source_id=source.id, chunk_index=i, chunk_text=ch[:5000]))
#             await db.commit()
#             chunks = await get_chunks_for_source(db, source.id)

#         # 2) Embed if needed
#         await ensure_embeddings(db, chunks)

#         # 3) Retrieve relevant prospect context (RAG)
#         retrieval_query = (
#             "Extract prospect insights: role & seniority, responsibilities, interests, current focus, "
#             "possible pains, and 1–2 personalized hooks."
#         )
#         top_chunks = await retrieve_top_chunks(db, retrieval_query, source_id=source.id, top_k=5)
#         context = "\n\n---\n\n".join(top_chunks)[:12000]
#     except Exception as e:
#         # fallback to raw
#         print("Warning: PDF RAG prep failed, falling back to raw text:", repr(e))
#         source = None
#         context = text[:12000]

#     # 4) Ask Ollama to produce clean bullets from retrieved context
#     prompt = (
#         "Extract prospect insights in concise bullets: role & seniority, interests, current focus, "
#         "possible pains, and 1–2 personalized hooks. Return 5–7 bullets.\n\n"
#         f"CONTEXT:\n{context}"
#     )

#     async with httpx.AsyncClient(timeout=120) as c:
#         r = await c.post(
#             f"{OLLAMA_BASE}/api/generate",
#             json={"model": MODEL, "prompt": prompt, "stream": False},
#         )
#         if r.status_code == 404:
#             r = await c.post(
#                 f"{OLLAMA_BASE}/api/chat",
#                 json={"model": MODEL, "messages": [{"role": "user", "content": prompt}], "stream": False},
#             )
#         r.raise_for_status()
#         out = r.json()

#     summary = (out.get("response") or out.get("message", {}).get("content") or "").strip()

#     # 5) Persist run (don’t fail request if DB write fails)
#     try:
#         await create_run(
#             db,
#             run_type="prospect_upload_rag",
#             input_text=context[:20000],
#             output_text=summary,
#             source=source_key,
#         )
#     except Exception as e:
#         print("Warning: persist failed (prospect_upload_rag):", e)

#     return {
#         "summary": summary,
#         "prospect_source_id": (source.id if source else None),
#         "source_key": source_key,
#     }