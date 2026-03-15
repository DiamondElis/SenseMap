"""
Integration test: write a small lexical graph to Neo4j and verify nodes, edges, and idempotent reruns.
Requires a running Neo4j (e.g. NEO4J_URI=bolt://localhost:7687). Skips if Neo4j unavailable.
Verifies: one document, N parents, M children, NEXT_CHUNK chain length, all children attached to one parent,
child embeddings on Chunk nodes, NEXT_CHUNK reading order, idempotent rerun.
"""
import os
import pytest
from datetime import datetime, timezone

from shared.python.models.ingestion import NormalizedDocument, IngestionRun
from shared.python.models.chunks import ParentChunk, ChildChunk
from services.graph_builder.lexical_writer import write_lexical_graph
from neo4j import GraphDatabase


# Unique document id so we don't clash with other data; use env for test DB if needed
TEST_DOC_ID = "test_lexical_graph_write_doc_001"
TEST_RUN_ID = "test_run_001"


def _make_payload():
    """Sample document, 2 parents, 4 children (2 per parent), embeddings on children."""
    doc = NormalizedDocument(
        id=TEST_DOC_ID,
        source_id=TEST_DOC_ID,
        source_type="txt",
        title="Integration test document",
        text="Sample text for lexical graph write test.",
    )
    parents = [
        ParentChunk(id=f"{TEST_DOC_ID}_p0", document_id=TEST_DOC_ID, text="Parent 0", position=0, token_count=2),
        ParentChunk(id=f"{TEST_DOC_ID}_p1", document_id=TEST_DOC_ID, text="Parent 1", position=1, token_count=2),
    ]
    # Children: p0 -> c0, c1; p1 -> c2, c3. NEXT_CHUNK: c0->c1, c2->c3
    children = [
        ChildChunk(id=f"{TEST_DOC_ID}_c0", parent_id=f"{TEST_DOC_ID}_p0", document_id=TEST_DOC_ID, text="Child 0", position=0, token_count=1, embedding=[0.1] * 1536),
        ChildChunk(id=f"{TEST_DOC_ID}_c1", parent_id=f"{TEST_DOC_ID}_p0", document_id=TEST_DOC_ID, text="Child 1", position=1, token_count=1, embedding=[0.2] * 1536),
        ChildChunk(id=f"{TEST_DOC_ID}_c2", parent_id=f"{TEST_DOC_ID}_p1", document_id=TEST_DOC_ID, text="Child 2", position=0, token_count=1, embedding=[0.3] * 1536),
        ChildChunk(id=f"{TEST_DOC_ID}_c3", parent_id=f"{TEST_DOC_ID}_p1", document_id=TEST_DOC_ID, text="Child 3", position=1, token_count=1, embedding=[0.4] * 1536),
    ]
    run = IngestionRun(
        id=TEST_RUN_ID,
        source_type="txt",
        started_at=datetime.now(timezone.utc),
        status="running",
        version="0.1",
        input_path="/tmp/integration_test.txt",
    )
    return doc, parents, children, run


def _get_driver():
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USERNAME") or os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "password")
    return GraphDatabase.driver(uri, auth=(user, password))


def _count_and_assert(driver):
    """Query Neo4j for our test document subgraph and return counts; assert structure."""
    with driver.session() as session:
        # Count nodes by label for our document
        r = session.run(
            "MATCH (d:Document {id: $doc_id}) OPTIONAL MATCH (d)-[:HAS_PARENT]->(pc:ParentChunk) "
            "OPTIONAL MATCH (pc)-[:HAS_CHILD]->(ch:Chunk) OPTIONAL MATCH (d)-[:INGESTED_IN]->(r:IngestionRun) "
            "RETURN d.id AS doc_id, count(DISTINCT pc) AS parent_count, count(DISTINCT ch) AS child_count, count(DISTINCT r) AS run_count",
            doc_id=TEST_DOC_ID,
        )
        row = r.single()
        if not row or row["doc_id"] is None:
            return None
        parent_count = row["parent_count"] or 0
        child_count = row["child_count"] or 0
        run_count = row["run_count"] or 0

        # NEXT_CHUNK count: should be M - N (one chain per parent: k children -> k-1 edges)
        r = session.run(
            "MATCH (d:Document {id: $doc_id})-[:HAS_PARENT]->(:ParentChunk)-[:HAS_CHILD]->(ch:Chunk) "
            "MATCH (ch)-[n:NEXT_CHUNK]->() RETURN count(n) AS next_count",
            doc_id=TEST_DOC_ID,
        )
        next_count = (r.single() or {}).get("next_count") or 0

        # Each Chunk should have exactly one incoming HAS_CHILD
        r = session.run(
            "MATCH (d:Document {id: $doc_id})-[:HAS_PARENT]->(:ParentChunk)-[r:HAS_CHILD]->(ch:Chunk) "
            "WITH ch, count(r) AS in_degree RETURN collect(in_degree) AS degrees",
            doc_id=TEST_DOC_ID,
        )
        degrees = (r.single() or {}).get("degrees") or []
        all_one_parent = all(d == 1 for d in degrees) and len(degrees) == child_count

        # Chunks with embedding property
        r = session.run(
            "MATCH (d:Document {id: $doc_id})-[:HAS_PARENT]->(:ParentChunk)-[:HAS_CHILD]->(ch:Chunk) "
            "WHERE ch.embedding IS NOT NULL RETURN count(ch) AS with_embedding",
            doc_id=TEST_DOC_ID,
        )
        with_embedding = (r.single() or {}).get("with_embedding") or 0

        # NEXT_CHUNK reading order: for p0 chain c0->c1, for p1 chain c2->c3
        r = session.run(
            "MATCH (a:Chunk)-[:NEXT_CHUNK]->(b:Chunk) WHERE a.id IN $ids AND b.id IN $ids "
            "RETURN a.id AS a, b.id AS b ORDER BY a.id, b.id",
            ids=[f"{TEST_DOC_ID}_c0", f"{TEST_DOC_ID}_c1", f"{TEST_DOC_ID}_c2", f"{TEST_DOC_ID}_c3"],
        )
        next_edges = [(rec["a"], rec["b"]) for rec in r]
        expected_next = [(f"{TEST_DOC_ID}_c0", f"{TEST_DOC_ID}_c1"), (f"{TEST_DOC_ID}_c2", f"{TEST_DOC_ID}_c3")]
        reading_order_ok = set(next_edges) == set(expected_next)

    return {
        "parent_count": parent_count,
        "child_count": child_count,
        "run_count": run_count,
        "next_count": next_count,
        "all_children_one_parent": all_one_parent,
        "chunks_with_embedding": with_embedding,
        "reading_order_ok": reading_order_ok,
    }


@pytest.fixture(scope="module")
def neo4j_driver():
    """Module-scoped Neo4j driver; skip if connection fails."""
    try:
        driver = _get_driver()
        driver.verify_connectivity()
        return driver
    except Exception:
        pytest.skip("Neo4j not available (set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)")


def test_lexical_graph_write_and_verify(neo4j_driver):
    """Write sample lexical graph, then query back and verify node counts and structure."""
    doc, parents, children, run = _make_payload()
    write_lexical_graph(doc, parents, children, run)

    counts = _count_and_assert(neo4j_driver)
    assert counts is not None, "Document not found in Neo4j after write"
    N, M = 2, 4
    assert counts["parent_count"] == N, "Expected N parents"
    assert counts["child_count"] == M, "Expected M children"
    assert counts["run_count"] == 1, "Expected one IngestionRun"
    # NEXT_CHUNK: 2 chains of 2 children each -> 1+1 = 2 edges (M - N)
    assert counts["next_count"] == M - N, "NEXT_CHUNK count should be M - N"
    assert counts["all_children_one_parent"], "Each child must be attached to exactly one parent"
    assert counts["chunks_with_embedding"] == M, "All M child chunks should have embedding on Chunk nodes"
    assert counts["reading_order_ok"], "NEXT_CHUNK should reflect reading order (c0->c1, c2->c3)"


def test_lexical_graph_write_idempotent_rerun(neo4j_driver):
    """Write same payload twice; second run must not create duplicate nodes or edges."""
    doc, parents, children, run = _make_payload()
    write_lexical_graph(doc, parents, children, run)
    counts1 = _count_and_assert(neo4j_driver)
    assert counts1 is not None

    write_lexical_graph(doc, parents, children, run)
    counts2 = _count_and_assert(neo4j_driver)

    assert counts2 is not None
    assert counts1["parent_count"] == counts2["parent_count"]
    assert counts1["child_count"] == counts2["child_count"]
    assert counts1["next_count"] == counts2["next_count"]
    assert counts1["chunks_with_embedding"] == counts2["chunks_with_embedding"]
