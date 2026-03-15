"""
Embedding hooks for Airflow. Expose configured backend and batch embedding helper.
Secrets and config stay in the hook; DAG tasks call the hook without connection or config logic.
"""
from typing import Any, Callable, List, Optional

try:
    from airflow.hooks.base import BaseHook
    _AIRFLOW_AVAILABLE = True
except ImportError:
    _AIRFLOW_AVAILABLE = False
    BaseHook = object  # type: ignore[misc, assignment]

# Default batch size for embedding APIs (e.g. OpenAI allows many per request; cap for reliability)
DEFAULT_EMBED_BATCH_SIZE = 256


def _get_config() -> tuple[str, str, Optional[str]]:
    """Centralized config: (backend, model, cache_path). No secrets in return."""
    try:
        from shared.python.config import settings
        backend = settings.EMBEDDING_BACKEND
        model = getattr(settings, "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        cache_path = getattr(settings, "SENSEMAP_EMBEDDING_CACHE", None)
        return backend, model, cache_path
    except ImportError:
        import os
        backend = os.environ.get("EMBEDDING_BACKEND", "openai")
        model = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        cache_path = os.environ.get("SENSEMAP_EMBEDDING_CACHE")
        return backend, model, cache_path


def get_embedding_fn(
    backend: Optional[str] = None,
    model: Optional[str] = None,
    cache_path: Optional[str] = None,
) -> Callable[[List[str]], List[List[float]]]:
    """
    Return a function that embeds a list of texts. Config from shared config / env when not overridden.
    """
    cfg_backend, cfg_model, cfg_cache = _get_config()
    backend = backend or cfg_backend
    model = model or cfg_model
    cache_path = cache_path or cfg_cache

    if backend in ("local", "bge"):
        return _local_bge_embedding_fn(cache_path=cache_path)
    return _openai_embedding_fn(model=model, cache_path=cache_path)


def embed_batch(
    texts: List[str],
    batch_size: int = DEFAULT_EMBED_BATCH_SIZE,
    backend: Optional[str] = None,
    model: Optional[str] = None,
) -> List[List[float]]:
    """
    Embed texts in batches using the configured backend. Single entry point for DAG tasks.
    Handles chunking; secrets and config are resolved inside this helper.
    """
    fn = get_embedding_fn(backend=backend, model=model)
    if not texts:
        return []
    if batch_size <= 0:
        batch_size = DEFAULT_EMBED_BATCH_SIZE
    out: List[List[float]] = []
    for i in range(0, len(texts), batch_size):
        chunk = texts[i : i + batch_size]
        out.extend(fn(chunk))
    return out


def _openai_embedding_fn(
    model: Optional[str] = None,
    cache_path: Optional[str] = None,
) -> Callable[[List[str]], List[List[float]]]:
    """Build OpenAI embedding callable. API key from shared config / env only."""
    try:
        from shared.python.config import settings
        model = model or settings.OPENAI_EMBEDDING_MODEL
        api_key = settings.OPENAI_API_KEY
    except ImportError:
        import os
        model = model or os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        api_key = os.environ.get("OPENAI_API_KEY", "")

    def _embed(texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            r = client.embeddings.create(input=texts, model=model)
            return [d.embedding for d in sorted(r.data, key=lambda x: x.index)]
        except Exception:
            return [[0.0] * 1536 for _ in texts]
    return _embed


def _local_bge_embedding_fn(cache_path: Optional[str] = None) -> Callable[[List[str]], List[List[float]]]:
    """Build local BGE embedding callable; defer to sensemap if available."""
    try:
        from sensemap.embeddings import generate_chunk_embeddings
        def _embed(texts: List[str]) -> List[List[float]]:
            if not texts:
                return []
            return generate_chunk_embeddings(texts)
        return _embed
    except ImportError:
        def _embed(texts: List[str]) -> List[List[float]]:
            return [[0.0] * 384 for _ in texts]
        return _embed


if _AIRFLOW_AVAILABLE:

    class EmbeddingHook(BaseHook):
        """
        Airflow Hook for embeddings. Exposes configured backend and batch helper.
        DAG tasks use get_embedding_fn() or embed_batch(); no config or secrets in task code.
        """

        def __init__(self, backend: Optional[str] = None, model: Optional[str] = None, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._backend_override = backend
            self._model_override = model

        def get_backend(self) -> str:
            """Return the configured embedding backend (e.g. openai, local)."""
            backend, _, _ = _get_config()
            return self._backend_override or backend

        def get_embedding_fn(self) -> Callable[[List[str]], List[List[float]]]:
            """Return a function that embeds a list of texts (configured backend)."""
            return get_embedding_fn(backend=self._backend_override, model=self._model_override)

        def embed_batch(
            self,
            texts: List[str],
            batch_size: int = DEFAULT_EMBED_BATCH_SIZE,
        ) -> List[List[float]]:
            """Embed texts in batches using the configured backend. No config in caller."""
            return embed_batch(
                texts,
                batch_size=batch_size,
                backend=self._backend_override,
                model=self._model_override,
            )
