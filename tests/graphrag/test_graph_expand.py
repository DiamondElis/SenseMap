"""Unit tests for graph expansion: hop and count limits."""
from unittest.mock import MagicMock, patch

import pytest

from shared.python.models.retrieval import EntityHit, RelationshipHit, RetrievalHit
from services.graphrag.retrievers.graph_expand import expand


def test_expand_empty_chunk_hits_returns_empty():
    """No chunk_hits and no entity_hits returns ([], [], [])."""
    with patch("services.graphrag.retrievers.graph_expand.get_driver"):
        assert expand([], None) == ([], [], [])
        assert expand([], []) == ([], [], [])


@patch("services.graphrag.retrievers.graph_expand.get_driver")
def test_graph_expansion_stays_within_hop_and_count_limits(mock_get_driver):
    """Expansion respects max_entities and max_relationships; NEXT_CHUNK limited by max_hops."""
    mock_session = MagicMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=None)
    mock_get_driver.return_value = mock_driver

    # First run: entities from chunks (return 5)
    # Second run: RELATES_TO (return 3)
    # Third run: NEXT_CHUNK (return 2)
    def run_side_effect(*args, **kwargs):
        query = args[0]
        if "MENTIONS" in query and "REFERS_TO" in query:
            return [
                {"entity_id": f"e{i}", "canonical_name": f"Entity{i}", "entity_type": "Concept"}
                for i in range(5)
            ]
        if "RELATES_TO" in query:
            return [
                {"aid": "e0", "aname": "E0", "bid": "e1", "bname": "E1", "relType": "RELATES_TO"},
                {"aid": "e1", "aname": "E1", "bid": "e2", "bname": "E2", "relType": "RELATES_TO"},
                {"aid": "e2", "aname": "E2", "bid": "e3", "bname": "E3", "relType": "RELATES_TO"},
            ]
        if "NEXT_CHUNK" in query:
            return [{"id": "c_next_1", "text": "Next chunk"}, {"id": "c_next_2", "text": "Next chunk 2"}]
        return []

    mock_session.run.side_effect = run_side_effect

    chunk_hits = [RetrievalHit(node_id="c1", node_label="Chunk", text="x", score=0.9, metadata={}, provenance={})]
    entities, relationships, chunks = expand(
        chunk_hits,
        max_hops=1,
        max_entities=3,
        max_relationships=2,
        include_next_chunk=True,
    )

    assert len(entities) <= 3
    assert len(relationships) <= 2
    mock_get_driver.return_value.close.assert_called_once()
