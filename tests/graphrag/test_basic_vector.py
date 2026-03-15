"""Unit tests for basic vector retriever: ordered hits by score."""
from unittest.mock import MagicMock, patch

import pytest

from shared.python.models.retrieval import RetrievalHit
from services.graphrag.retrievers.basic_vector import retrieve


def test_empty_query_returns_empty_list():
    """Empty or whitespace query returns []."""
    with patch("services.graphrag.retrievers.basic_vector.get_driver"):
        assert retrieve("") == []
        assert retrieve("   ") == []


@patch("services.graphrag.retrievers.basic_vector.get_driver")
def test_vector_retriever_returns_ordered_hits(mock_get_driver):
    """Retriever returns hits in the order returned by Neo4j (vector search order by score)."""
    mock_session = MagicMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=None)
    mock_get_driver.return_value = mock_driver

    mock_session.run.return_value = [
        {"id": "c1", "text": "First chunk", "score": 0.95},
        {"id": "c2", "text": "Second chunk", "score": 0.88},
        {"id": "c3", "text": "Third chunk", "score": 0.72},
    ]

    mock_embedder = MagicMock()
    mock_embedder.embed_texts.return_value = [[0.1] * 64]

    result = retrieve("test query", k=5, embedder=mock_embedder)

    assert len(result) == 3
    assert all(isinstance(h, RetrievalHit) for h in result)
    assert result[0].node_id == "c1" and result[0].score == 0.95
    assert result[1].node_id == "c2" and result[1].score == 0.88
    assert result[2].node_id == "c3" and result[2].score == 0.72
    assert result[0].node_label == "Chunk"
    mock_driver.close.assert_called_once()


@patch("services.graphrag.retrievers.basic_vector.get_driver")
def test_vector_retriever_respects_k(mock_get_driver):
    """Session is called with k parameter."""
    mock_session = MagicMock()
    mock_session.run.return_value = []
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=None)
    mock_get_driver.return_value = mock_driver
    mock_embedder = MagicMock()
    mock_embedder.embed_texts.return_value = [[0.1] * 64]

    retrieve("q", k=3, embedder=mock_embedder)

    call_args = mock_session.run.call_args
    assert call_args[0][1]["k"] == 3
