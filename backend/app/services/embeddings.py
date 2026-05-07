# backend/app/services/embeddings.py
from sentence_transformers import SentenceTransformer
import numpy as np

_model = None

def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _model

def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_model()
    vecs = model.encode(texts, normalize_embeddings=True)  # cosine-ready
    if isinstance(vecs, np.ndarray):
        return vecs.astype(float).tolist()
    return [v.astype(float).tolist() for v in vecs]