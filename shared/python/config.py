"""
Central config from environment. Use these settings across services and apps.
Env var names match the documented list; aliases (e.g. NEO4J_USER) supported for backward compatibility.
"""
import os
from pathlib import Path


class Settings:
    """Simple settings from os.environ with defaults."""

    # Neo4j
    NEO4J_URI: str = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USERNAME: str = os.environ.get("NEO4J_USERNAME") or os.environ.get("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.environ.get("NEO4J_PASSWORD", "password")

    # OpenAI
    OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")

    # Embedding backend and models
    EMBEDDING_BACKEND: str = (
        os.environ.get("EMBEDDING_BACKEND")
        or os.environ.get("SENSEMAP_EMBEDDING_BACKEND", "openai")
    )
    OPENAI_EMBEDDING_MODEL: str = os.environ.get(
        "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
    )
    LOCAL_BGE_MODEL: str = os.environ.get("LOCAL_BGE_MODEL") or os.environ.get(
        "SENSEMAP_BGE_MODEL", "BAAI/bge-small-en-v1.5"
    )

    # Optional: embedding cache path
    SENSEMAP_EMBEDDING_CACHE: str = os.environ.get(
        "SENSEMAP_EMBEDDING_CACHE",
        str(Path(__file__).resolve().parents[2] / "data" / "processed" / "embedding_cache.db"),
    )

    # Backward compatibility: many callers use NEO4J_USER
    @property
    def NEO4J_USER(self) -> str:
        return self.NEO4J_USERNAME


# Singleton instance; import and use settings.XXX
settings = Settings()
