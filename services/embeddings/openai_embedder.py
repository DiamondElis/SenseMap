"""OpenAI embeddings with cache and batching."""
import os
from typing import Optional

from .base import Embedder
from .cache import get_cached_embedding, set_cached_embedding, make_embedding_key

BACKEND_NAME = "openai"
DEFAULT_MODEL = "text-embedding-3-small"
MAX_BATCH_SIZE = 2048  # OpenAI limit; we batch by token count roughly via chunk count


class OpenAIEmbedder:
    """Embedder using OpenAI API with local cache and batching."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: Optional[str] = None,
        cache_path: Optional[str] = None,
    ):
        self.model = model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._cache_path = cache_path

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed texts; use cache for each, batch only uncached through API. Return order matches input."""
        if not texts:
            return []
        results: list[list[float] | None] = [None] * len(texts)
        to_fetch: list[tuple[int, str]] = []  # (index, text)
        for i, text in enumerate(texts):
            key = make_embedding_key(text, BACKEND_NAME, self.model)
            cached = get_cached_embedding(key, self._cache_path or "")
            if cached is not None:
                results[i] = cached
            else:
                to_fetch.append((i, text))

        if not to_fetch:
            return results

        # Batch fetch in chunks of MAX_BATCH_SIZE
        for start in range(0, len(to_fetch), MAX_BATCH_SIZE):
            batch = to_fetch[start : start + MAX_BATCH_SIZE]
            indices = [t[0] for t in batch]
            batch_texts = [t[1] for t in batch]
            vectors = self._call_api(batch_texts)
            for idx, vec in zip(indices, vectors, strict=True):
                results[idx] = vec
                key = make_embedding_key(texts[idx], BACKEND_NAME, self.model)
                set_cached_embedding(key, vec, self._cache_path)

        assert all(r is not None for r in results), "all indices should be filled"
        return [r for r in results if r is not None]

    def _call_api(self, texts: list[str]) -> list[list[float]]:
        if not self._api_key:
            dim = 1536 if "3-small" in self.model else 1536
            return [[0.0] * dim for _ in texts]
        from openai import OpenAI

        client = OpenAI(api_key=self._api_key)
        resp = client.embeddings.create(input=texts, model=self.model)
        by_idx = {e.index: e.embedding for e in resp.data}
        return [by_idx[i] for i in range(len(texts))]
