"""Local BGE-compatible embedder (sentence-transformers). Scaffolded for milestone 1; optional dependency."""
import os
from typing import List, Optional

from .base import Embedder
from .cache import get_cached_embedding, set_cached_embedding, make_embedding_key

BACKEND_NAME = "local_bge"
DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


class LocalBGEEmbedder:
    """Embedder using sentence-transformers (BGE or similar). Uses cache; same interface as OpenAI."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        cache_path: Optional[str] = None,
        device: Optional[str] = None,
    ):
        self.model = model
        self._cache_path = cache_path
        self._device = device or os.environ.get("SENSEMAP_EMBEDDING_DEVICE", "cpu")
        self._model = None  # lazy load

    def _get_model(self):
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model, device=self._device)
            return self._model
        except ImportError as e:
            raise RuntimeError(
                "sentence-transformers is required for LocalBGEEmbedder; pip install sentence-transformers"
            ) from e

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed texts; use cache per text, run model only for uncached. Return order matches input."""
        if not texts:
            return []
        results: List[Optional[List[float]]] = [None] * len(texts)
        to_fetch: list[tuple[int, str]] = []
        for i, text in enumerate(texts):
            key = make_embedding_key(text, BACKEND_NAME, self.model)
            cached = get_cached_embedding(key, self._cache_path)
            if cached is not None:
                results[i] = cached
            else:
                to_fetch.append((i, text))

        if not to_fetch:
            assert all(r is not None for r in results)
            return [r for r in results if r is not None]

        batch_texts = [t[1] for t in to_fetch]
        vectors = self._get_model().encode(batch_texts, convert_to_numpy=True)
        for (idx, _), vec in zip(to_fetch, vectors, strict=True):
            embedding = vec.tolist()
            results[idx] = embedding
            key = make_embedding_key(texts[idx], BACKEND_NAME, self.model)
            set_cached_embedding(key, embedding, self._cache_path)

        assert all(r is not None for r in results)
        return [r for r in results if r is not None]
