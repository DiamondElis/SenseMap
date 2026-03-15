from typing import Optional

from shared.python.config import settings

from .base import Embedder
from .cache import get_cached_embedding, set_cached_embedding, make_embedding_key
from .openai_embedder import OpenAIEmbedder
from .local_bge_embedder import LocalBGEEmbedder

DEFAULT_BACKEND = settings.EMBEDDING_BACKEND


def get_embedder(
    backend: Optional[str] = None,
    model: Optional[str] = None,
    cache_path: Optional[str] = None,
    **kwargs: object,
) -> Embedder:
    """Return an Embedder by config. backend from EMBEDDING_BACKEND env or argument."""
    backend = backend or DEFAULT_BACKEND
    if backend == "openai":
        return OpenAIEmbedder(
            model=model or settings.OPENAI_EMBEDDING_MODEL,
            cache_path=cache_path,
            **kwargs,
        )
    if backend == "local_bge":
        return LocalBGEEmbedder(
            model=model or settings.LOCAL_BGE_MODEL,
            cache_path=cache_path,
            **kwargs,
        )
    raise ValueError(f"Unknown embedding backend: {backend}. Use 'openai' or 'local_bge'.")


__all__ = [
    "Embedder",
    "get_cached_embedding",
    "set_cached_embedding",
    "make_embedding_key",
    "OpenAIEmbedder",
    "LocalBGEEmbedder",
    "get_embedder",
]
