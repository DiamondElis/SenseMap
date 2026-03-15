"""Unit tests for answer pipeline: provenance and debug route."""
from unittest.mock import patch, MagicMock

import pytest

from shared.python.models.context import ContextBundle
from shared.python.models.retrieval import EntityHit, RelationshipHit, RetrievalHit
from services.graphrag.orchestration.answer_pipeline import run_answer_pipeline


def test_empty_query_returns_no_context():
    """Empty query returns answer empty, context_used False, no route."""
    result = run_answer_pipeline("")
    assert result["answer"] == ""
    assert result["provenance"]["context_used"] is False
    assert result["provenance"].get("route") is None
    assert "error" in result["debug"]


@patch("services.graphrag.orchestration.answer_pipeline.hybrid_retrieve")
@patch("services.graphrag.orchestration.answer_pipeline.dedupe_bundle")
@patch("services.graphrag.orchestration.answer_pipeline.rerank_bundle")
@patch("services.graphrag.orchestration.answer_pipeline.apply_budget")
@patch("services.graphrag.orchestration.answer_pipeline.assemble")
def test_answer_pipeline_returns_provenance_and_debug_route(
    mock_assemble,
    mock_budget,
    mock_rerank,
    mock_dedupe,
    mock_retrieve,
):
    """Pipeline returns provenance (sources, route) and debug with route."""
    bundle = ContextBundle(
        chunk_hits=[
            RetrievalHit(node_id="p1", node_label="ParentChunk", text="Context text", score=0.9, metadata={}, provenance={}),
        ],
        entity_hits=[],
        relationship_hits=[],
        debug={"route": {"retriever_stack": "parent_child"}},
    )
    mock_retrieve.return_value = bundle
    mock_dedupe.return_value = bundle
    mock_rerank.return_value = bundle
    mock_budget.return_value = bundle
    mock_assemble.return_value = (
        "[Chunk Context]\n1. ...\n\n[Entity Context]\n(none)\n\n[Relationship Context]\n(none)\n\n[Evidence / Provenance]\n(none)",
        {"sections": {}, "citation_map": {}},
    )

    def fake_llm(ctx, q):
        return "The answer is X."

    result = run_answer_pipeline("What is ergonomics?", llm_fn=fake_llm)

    assert result["answer"] == "The answer is X."
    assert "provenance" in result
    assert result["provenance"]["context_used"] is True
    assert result["provenance"].get("route") in ("vector_only", "parent_child", "parent_child_expand", "community")
    assert "debug" in result
    assert "route" in result["debug"]
    assert "token_budget" in result["debug"] or "context_object" in result["debug"]
