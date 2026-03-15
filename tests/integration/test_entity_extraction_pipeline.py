"""
Integration test: entity extraction pipeline from a small lexical graph fixture.
Writes a minimal document with one or two chunks, runs extraction (with mocked LLM),
writes entity graph layer, and verifies entity count, mention count, relation count,
processed flag, and that uncertain entities produce review candidates (no unsafe merge).
Requires a running Neo4j. Skips if Neo4j unavailable.
"""
import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from neo4j import GraphDatabase
from shared.python.models.ingestion import NormalizedDocument, IngestionRun
from shared.python.models.chunks import ParentChunk, ChildChunk
from services.graph_builder.lexical_writer import write_lexical_graph
from services.extraction.pipeline import run_pipeline, fetch_unprocessed_chunks
from services.extraction.resolution.merge import resolve_entity


TEST_DOC_ID = "test_entity_extraction_doc_001"
TEST_RUN_ID = "test_entity_extraction_run_001"
CHUNK_1_ID = f"{TEST_DOC_ID}_c0"
CHUNK_2_ID = f"{TEST_DOC_ID}_c1"


def _get_driver():
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USERNAME") or os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "password")
    return GraphDatabase.driver(uri, auth=(user, password))


def _make_lexical_fixture():
    """Minimal document with 2 chunks with text for entity extraction."""
    doc = NormalizedDocument(
        id=TEST_DOC_ID,
        source_id=TEST_DOC_ID,
        source_type="txt",
        title="Entity extraction test doc",
        text="Acme Corp and Bob Smith signed a deal. The deal was announced by Acme.",
    )
    parents = [
        ParentChunk(id=f"{TEST_DOC_ID}_p0", document_id=TEST_DOC_ID, text="Parent", position=0, token_count=2),
    ]
    children = [
        ChildChunk(id=CHUNK_1_ID, parent_id=f"{TEST_DOC_ID}_p0", document_id=TEST_DOC_ID, text="Acme Corp and Bob Smith signed a deal.", position=0, token_count=8),
        ChildChunk(id=CHUNK_2_ID, parent_id=f"{TEST_DOC_ID}_p0", document_id=TEST_DOC_ID, text="The deal was announced by Acme.", position=1, token_count=6),
    ]
    run = IngestionRun(
        id=TEST_RUN_ID,
        source_type="txt",
        started_at=datetime.now(timezone.utc),
        status="running",
        version="0.1",
        input_path="/tmp/entity_extraction_test.txt",
    )
    return doc, parents, children, run


def _fixture_chunks():
    """Chunks to feed the pipeline (same ids as lexical fixture)."""
    return [
        {"id": CHUNK_1_ID, "text": "Acme Corp and Bob Smith signed a deal."},
        {"id": CHUNK_2_ID, "text": "The deal was announced by Acme."},
    ]


def _mock_extract_entities(text, glossary, schema):
    """Return fixed entities for our fixture texts."""
    if "Acme Corp and Bob Smith" in text:
        return {
            "entities": [
                {"raw_text": "Acme Corp", "canonical_candidate": "Acme Corp", "type": "Organization", "confidence": 0.95},
                {"raw_text": "Bob Smith", "canonical_candidate": "Bob Smith", "type": "Person", "confidence": 0.9},
            ],
        }
    if "deal was announced by Acme" in text:
        return {
            "entities": [
                {"raw_text": "Acme", "canonical_candidate": "Acme Corp", "type": "Organization", "confidence": 0.85},
            ],
        }
    return {"entities": []}


def _mock_extract_relationships(text, entities, schema):
    """Return fixed relationships for first chunk only."""
    if "Acme Corp and Bob Smith" in text and len(entities) >= 2:
        return {
            "relationships": [
                {"source_name": "Acme Corp", "target_name": "Bob Smith", "type": "RELATES_TO", "confidence": 0.8},
            ],
        }
    return {"relationships": []}


def _count_entity_layer(driver):
    """Return entity count, mention count, RELATES_TO count, and processed chunk ids for our fixture."""
    with driver.session() as session:
        r = session.run("MATCH (e:Entity) RETURN count(e) AS n")
        entity_count = (r.single() or {}).get("n") or 0

        r = session.run("MATCH (m:EntityMention) RETURN count(m) AS n")
        mention_count = (r.single() or {}).get("n") or 0

        r = session.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS n")
        rel_count = (r.single() or {}).get("n") or 0

        r = session.run(
            "MATCH (ch:Chunk) WHERE ch.id IN $ids RETURN ch.id AS id, ch.entity_processed_at AS at",
            ids=[CHUNK_1_ID, CHUNK_2_ID],
        )
        processed = {rec["id"]: rec["at"] for rec in r if rec.get("id")}

        r = session.run("MATCH (c:Claim) WHERE c.id IN $ids RETURN count(c) AS n", ids=[f"claim_{CHUNK_1_ID}", f"claim_{CHUNK_2_ID}"])
        claim_count = (r.single() or {}).get("n") or 0
    return {
        "entity_count": entity_count,
        "mention_count": mention_count,
        "relation_count": rel_count,
        "processed": processed,
        "claim_count": claim_count,
    }


@pytest.fixture(scope="module")
def neo4j_driver():
    try:
        driver = _get_driver()
        driver.verify_connectivity()
        return driver
    except Exception:
        pytest.skip("Neo4j not available (set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)")


def test_entity_extraction_pipeline_writes_entity_layer(neo4j_driver):
    """Run pipeline from lexical fixture; verify entity count > 0, mention count > 0, relation count > 0, processed set."""
    doc, parents, children, run = _make_lexical_fixture()
    write_lexical_graph(doc, parents, children, run)

    with patch("services.extraction.pipeline.fetch_unprocessed_chunks", return_value=_fixture_chunks()), \
         patch("services.extraction.pipeline.extract_entities", side_effect=_mock_extract_entities), \
         patch("services.extraction.pipeline.extract_relationships", side_effect=_mock_extract_relationships):
        summary = run_pipeline(limit=2, extractor_name="integration_test")

    assert summary["chunks_considered"] == 2
    assert summary["processed"] >= 1
    assert summary["errors"] == 0

    counts = _count_entity_layer(neo4j_driver)
    assert counts["entity_count"] > 0, "Expected at least one Entity node"
    assert counts["mention_count"] > 0, "Expected at least one EntityMention node"
    assert counts["relation_count"] > 0, "Expected at least one RELATES_TO edge"
    assert counts["claim_count"] >= 1, "Expected at least one Claim linked to chunk(s)"
    assert CHUNK_1_ID in counts["processed"] and counts["processed"][CHUNK_1_ID] is not None, "Chunk 1 should have entity_processed_at set"
    assert CHUNK_2_ID in counts["processed"] and counts["processed"][CHUNK_2_ID] is not None, "Chunk 2 should have entity_processed_at set"


def test_uncertain_entities_produce_review_candidates():
    """Verify uncertain entities (e.g. conflicting type, short ambiguous name) yield review action, not auto-merge."""
    existing = [{"id": "e1", "name": "Acme", "canonical_name": "Acme", "type": "Organization"}]
    candidate_same_name_different_type = {"canonical_candidate": "Acme", "type": "Person", "raw_text": "Acme"}
    result = resolve_entity(candidate_same_name_different_type, existing, {})
    assert result.action == "review"
    assert result.entity_id is None
    assert len(result.candidates) == 1
    assert result.candidates[0]["entity_id"] == "e1"
