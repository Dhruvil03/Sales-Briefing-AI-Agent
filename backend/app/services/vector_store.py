# backend/app/services/vector_store.py
import os
from typing import Any, Dict, List, Optional

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "sales-copilot")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "dev")

_client = None
_index = None


def _get_index():
    """
    Lazy init Pinecone client + index.
    Works with newer pinecone SDKs.
    """
    global _client, _index

    if _index is not None:
        return _index

    if not PINECONE_API_KEY:
        raise RuntimeError("PINECONE_API_KEY is missing in env")

    # Newer SDK
    try:
        from pinecone import Pinecone  # type: ignore
        _client = Pinecone(api_key=PINECONE_API_KEY)
        _index = _client.Index(PINECONE_INDEX)
        return _index
    except Exception:
        pass

    # Older SDK fallback
    try:
        import pinecone  # type: ignore
        pinecone.init(api_key=PINECONE_API_KEY)
        _index = pinecone.Index(PINECONE_INDEX)
        return _index
    except Exception as e:
        raise RuntimeError(f"Could not initialize Pinecone client: {repr(e)}")


def upsert_chunk_embeddings(
    items: List[Dict[str, Any]],
    namespace: Optional[str] = None,
):
    """
    items: [{id: str, values: List[float], metadata: dict}]
    """
    idx = _get_index()
    ns = namespace or PINECONE_NAMESPACE

    # Keep metadata small (Pinecone has limits)
    vectors = []
    for it in items:
        md = it.get("metadata") or {}
        if "chunk_text" in md and isinstance(md["chunk_text"], str):
            md["chunk_text"] = md["chunk_text"][:1000]
        vectors.append({"id": it["id"], "values": it["values"], "metadata": md})

    # Newer SDK uses `upsert(vectors=..., namespace=...)`
    try:
        return idx.upsert(vectors=vectors, namespace=ns)
    except TypeError:
        # Older SDK signature
        return idx.upsert(vectors=vectors, namespace=ns)


def query_similar(
    query_vector: List[float],
    top_k: int = 5,
    namespace: Optional[str] = None,
    filter: Optional[Dict[str, Any]] = None,
):
    idx = _get_index()
    ns = namespace or PINECONE_NAMESPACE

    # Newer SDK
    try:
        return idx.query(
            vector=query_vector,
            top_k=top_k,
            include_metadata=True,
            namespace=ns,
            filter=filter,
        )
    except TypeError:
        # Older SDK
        return idx.query(
            vector=query_vector,
            top_k=top_k,
            include_metadata=True,
            namespace=ns,
            filter=filter,
        )
    
# app/services/vector_store.py

def query_similar_chunks(query_vector: list[float], top_k: int = 5, source_id: int | None = None):
    pinecone_filter = None
    if source_id is not None:
        # match what you used in search.py
        pinecone_filter = {"source_id": {"$eq": source_id}}

    res = query_similar(
        query_vector=query_vector,
        top_k=max(1, min(top_k, 10)),
        filter=pinecone_filter,
    )

    matches = res.get("matches") if isinstance(res, dict) else getattr(res, "matches", None)
    return matches or []