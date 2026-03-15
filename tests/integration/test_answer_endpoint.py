"""
Integration test for POST /answer: small fixture or mocked pipeline, verify response shape.
Checks: answer exists, provenance exists, graph_trace not empty when context used, route is correct.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app


def _mock_pipeline_result():
    """Minimal pipeline result matching _build_answer_response expectations."""
    return {
        "answer": "Ergonomics influences industrial design by linking user-centered design to product usability.",
        "provenance": {
            "context_used": True,
            "sources": [{"node_id": "p1", "node_label": "ParentChunk", "score": 0.9, "text_preview": "Ergonomics links..."}],
            "route": "parent_child_expand",
            "chunk_count": 1,
            "entity_count": 1,
            "relationship_count": 1,
        },
        "debug": {
            "analysis": {"query_type": "multi_hop_entity", "routing_hints": {}},
            "route": {"retriever_stack": "parent_child_expand", "query_type": "multi_hop_entity"},
            "token_budget": {
                "total_tokens": 1200,
                "max_total_tokens": 3500,
                "final_chunk_count": 1,
                "final_entity_count": 1,
                "final_relationship_count": 1,
            },
            "context_object": {
                "sections": {
                    "[Chunk Context]": {
                        "entries": [
                            {
                                "node_id": "p1",
                                "node_label": "ParentChunk",
                                "text": "Ergonomics links user-centered design to product usability.",
                                "score": 0.9,
                                "document_title": "Industrial Design",
                                "parent_chunk_id": "p_12",
                                "chunk_id": "p1",
                            }
                        ],
                        "prompt_lines": ["1. Document: Industrial Design, ParentChunk: p_12\nErgonomics links..."],
                    },
                    "[Entity Context]": {
                        "entries": [
                            {"entity_id": "e1", "canonical_name": "Ergonomics", "entity_type": "Concept", "score": 0.9}
                        ],
                        "prompt_lines": ["- Ergonomics (Concept): Human-centered design principle."],
                    },
                    "[Relationship Context]": {
                        "entries": [
                            {
                                "source_id": "e1",
                                "target_id": "e2",
                                "source_name": "Ergonomics",
                                "target_name": "Industrial Design",
                                "rel_type": "INFLUENCES",
                                "score": 0.8,
                                "source_chunk_ids": ["c_12_4"],
                            }
                        ],
                        "prompt_lines": ["- Ergonomics INFLUENCES Industrial Design"],
                    },
                    "[Evidence / Provenance]": {"lines": ["- ParentChunk p_12 from Document Industrial Design"]},
                },
                "citation_map": {"chunk_citations": {}, "relationship_citations": {}},
            },
        },
    }


@patch("apps.api.main.run_answer_pipeline")
def test_post_answer_returns_answer_and_provenance(mock_run_pipeline):
    """POST /answer returns answer, provenance, graph_trace; when debug=true includes debug."""
    mock_run_pipeline.return_value = _mock_pipeline_result()
    client = TestClient(app)
    resp = client.post(
        "/answer",
        json={"question": "How does ergonomics influence industrial design?", "max_context_tokens": 3500, "debug": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert len(data["answer"]) > 0
    assert "provenance" in data
    assert data["provenance"]["documents"] is not None
    assert data["provenance"]["parent_chunks"] is not None
    assert data["provenance"]["chunks"] is not None
    assert data["provenance"]["entities"] is not None
    assert data["provenance"]["relationships"] is not None


@patch("apps.api.main.run_answer_pipeline")
def test_post_answer_graph_trace_not_empty_when_context_used(mock_run_pipeline):
    """When pipeline returns context, graph_trace has nodes and edges."""
    mock_run_pipeline.return_value = _mock_pipeline_result()
    client = TestClient(app)
    resp = client.post("/answer", json={"question": "Test?", "debug": True})
    assert resp.status_code == 200
    data = resp.json()
    assert "graph_trace" in data
    assert "nodes" in data["graph_trace"]
    assert "edges" in data["graph_trace"]
    assert len(data["graph_trace"]["nodes"]) >= 1
    assert len(data["graph_trace"]["edges"]) >= 1


@patch("apps.api.main.run_answer_pipeline")
def test_post_answer_debug_includes_route(mock_run_pipeline):
    """When debug=true, response includes debug.route (external name)."""
    mock_run_pipeline.return_value = _mock_pipeline_result()
    client = TestClient(app)
    resp = client.post("/answer", json={"question": "Test?", "debug": True})
    assert resp.status_code == 200
    data = resp.json()
    assert "debug" in data
    assert data["debug"]["route"] == "parent_child_plus_graph_expand"
    assert "token_budget" in data["debug"]


@patch("apps.api.main.run_answer_pipeline")
def test_post_answer_debug_false_omits_debug(mock_run_pipeline):
    """When debug=false, response may omit or minimize debug."""
    mock_run_pipeline.return_value = _mock_pipeline_result()
    client = TestClient(app)
    resp = client.post("/answer", json={"question": "Test?", "debug": False})
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "provenance" in data
    assert "graph_trace" in data
    # debug might still be present but minimal; route is the key external contract
    if "debug" in data:
        assert "route" in data["debug"]
