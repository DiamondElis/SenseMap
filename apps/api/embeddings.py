"""Query embedding for retrieval (1536 dims to match chunk_embedding index)."""
from openai import OpenAI


def embed_query(text: str, model: str = "text-embedding-3-small", api_key: str | None = None) -> list[float]:
    if not text.strip():
        return [0.0] * 1536
    key = api_key or __import__("os").environ.get("OPENAI_API_KEY")
    if not key:
        return [0.0] * 1536
    client = OpenAI(api_key=key)
    resp = client.embeddings.create(input=[text], model=model)
    return resp.data[0].embedding
