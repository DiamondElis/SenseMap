"""Generate embeddings for chunk text (1536 dims, cosine index)."""
from typing import Any

EMBEDDING_DIMS = 1536


def embed_texts(
    texts: list[str],
    model: str = "text-embedding-3-small",
    api_key: str | None = None,
) -> list[list[float]]:
    """Return list of embedding vectors (1536 dims) for each text. Uses OpenAI if key set."""
    if not texts:
        return []
    key = api_key or __import__("os").environ.get("OPENAI_API_KEY")
    if not key:
        # Placeholder: zero vectors so pipeline runs without OpenAI for testing
        return [[0.0] * EMBEDDING_DIMS for _ in texts]
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        resp = client.embeddings.create(input=texts, model=model)
        return [e.embedding for e in resp.data]
    except Exception:
        return [[0.0] * EMBEDDING_DIMS for _ in texts]


def generate_chunk_embeddings(
    child_chunks: list[dict[str, Any]],
    model: str = "text-embedding-3-small",
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """Attach embedding list to each child chunk (key 'embedding')."""
    texts = [c["text"] for c in child_chunks]
    vectors = embed_texts(texts, model=model, api_key=api_key)
    out = []
    for c, vec in zip(child_chunks, vectors, strict=True):
        out.append({**c, "embedding": vec})
    return out
