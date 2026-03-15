"""Local cache for embeddings: key = sha256(text + backend + model)."""
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Optional

# Default cache DB in project data dir or cwd
_DEFAULT_CACHE_PATH = os.environ.get(
    "SENSEMAP_EMBEDDING_CACHE",
    str(Path(__file__).resolve().parents[2] / "data" / "processed" / "embedding_cache.db"),
)


def make_embedding_key(text: str, backend: str, model: str) -> str:
    """Deterministic cache key: sha256(text + backend + model)."""
    raw = f"{text}\0{backend}\0{model}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _get_connection(path: str = _DEFAULT_CACHE_PATH) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS embeddings (key TEXT PRIMARY KEY, embedding TEXT)"
    )
    return conn


def get_cached_embedding(key: str, cache_path: Optional[str] = None) -> Optional[list[float]]:
    """Return cached embedding for key, or None if missing."""
    path = cache_path or _DEFAULT_CACHE_PATH
    conn = _get_connection(path)
    try:
        row = conn.execute("SELECT embedding FROM embeddings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        return json.loads(row[0])
    finally:
        conn.close()


def set_cached_embedding(
    key: str,
    embedding: list[float],
    cache_path: Optional[str] = None,
) -> None:
    """Store embedding for key."""
    path = cache_path or _DEFAULT_CACHE_PATH
    conn = _get_connection(path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO embeddings (key, embedding) VALUES (?, ?)",
            (key, json.dumps(embedding)),
        )
        conn.commit()
    finally:
        conn.close()
