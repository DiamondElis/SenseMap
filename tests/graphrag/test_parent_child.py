"""Unit tests for parent-child retriever: dedupes parents by max child score."""
from unittest.mock import MagicMock, patch

import pytest

from shared.python.models.retrieval import RetrievalHit
from services.graphrag.retrievers.parent_child import retrieve


def test_empty_query_returns_empty_list():
    """Empty query returns []."""
    with patch("services.graphrag.retrievers.parent_child.get_driver"):
        assert retrieve("") == []
        assert retrieve("   ") == []


@patch("services.graphrag.retrievers.parent_child.get_driver")
def test_parent_child_retriever_dedupes_parents_correctly(mock_get_driver):
    """Parent-child returns ParentChunk hits ordered by score (one per parent, max child score)."""
    mock_session = MagicMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=None)
    mock_get_driver.return_value = mock_driver

    # Simulate: multiple children map to same parent; Cypher returns parent once with max(score)
    mock_session.run.return_value = [
        {"id": "p1", "text": "Parent one", "score": 0.92},
        {"id": "p2", "text": "Parent two", "score": 0.85},
        {"id": "p3", "text": "Parent three", "score": 0.78},
    ]

    mock_embedder = MagicMock()
    mock_embedder.embed_texts.return_value = [[0.1] * 64]

    result = retrieve("test", k_children=12, k_parents=6, embedder=mock_embedder)

    assert len(result) == 3
    assert all(h.node_label == "ParentChunk" for h in result)
    assert result[0].node_id == "p1" and result[0].score == 0.92
    assert result[1].node_id == "p2" and result[1].score == 0.85
    assert result[2].node_id == "p3" and result[2].score == 0.78
    mock_driver.close.assert_called_once()


@patch("services.graphrag.retrievers.parent_child.get_driver")
def test_parent_child_respects_k_parents_and_vector_k(mock_get_driver):
    """Session run receives limit_k and vector_k."""
    mock_session = MagicMock()
    mock_session.run.return_value = []
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=None)
    mock_get_driver.return_value = mock_driver
    mock_embedder = MagicMock()
    mock_embedder.embed_texts.return_value = [[0.1] * 64]

    retrieve("q", k_children=20, k_parents=4, embedder=mock_embedder)

    call_args = mock_session.run.call_args
    params = call_args[0][1]
    assert params["vector_k"] == 20
    assert params["limit_k"] == 4
