"""Embedding cache tests: repeated text returns same value."""
import tempfile
import pytest

from services.embeddings.cache import (
    make_embedding_key,
    get_cached_embedding,
    set_cached_embedding,
)


@pytest.fixture
def temp_cache_path(tmp_path):
    return str(tmp_path / "embedding_cache.db")


def test_make_embedding_key_deterministic():
    """Same text + backend + model produce same key."""
    k1 = make_embedding_key("hello", "openai", "text-embedding-3-small")
    k2 = make_embedding_key("hello", "openai", "text-embedding-3-small")
    assert k1 == k2
    k3 = make_embedding_key("hello", "local_bge", "BAAI/bge-small")
    assert k1 != k3


def test_cache_returns_same_values_for_repeated_text(temp_cache_path):
    """Store embedding for text; repeated get returns same list."""
    key = make_embedding_key("repeated text", "openai", "model")
    embedding = [0.1, 0.2, 0.3]
    set_cached_embedding(key, embedding, cache_path=temp_cache_path)
    first = get_cached_embedding(key, cache_path=temp_cache_path)
    second = get_cached_embedding(key, cache_path=temp_cache_path)
    assert first is not None
    assert first == embedding
    assert second == first


def test_cache_missing_returns_none(temp_cache_path):
    """Unknown key returns None."""
    key = make_embedding_key("never stored", "openai", "model")
    assert get_cached_embedding(key, cache_path=temp_cache_path) is None


def test_cache_overwrite(temp_cache_path):
    """Setting same key again overwrites; get returns new value."""
    key = make_embedding_key("overwrite", "openai", "model")
    set_cached_embedding(key, [1.0], cache_path=temp_cache_path)
    set_cached_embedding(key, [2.0, 3.0], cache_path=temp_cache_path)
    got = get_cached_embedding(key, cache_path=temp_cache_path)
    assert got == [2.0, 3.0]
