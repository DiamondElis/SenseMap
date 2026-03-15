"""Unit tests for lexical_writer: internal write functions and validation gate."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from shared.python.models.ingestion import NormalizedDocument, IngestionRun
from shared.python.models.chunks import ParentChunk, ChildChunk
from services.graph_builder.lexical_writer import (
    write_ingestion_run,
    write_document,
    link_document_to_ingestion_run,
    write_parent_chunks,
    link_document_to_parents,
    write_child_chunks,
    link_parents_to_children,
    link_chunk_sequence,
    write_lexical_graph,
)
from services.graph_builder.validators import ValidationError


def _doc() -> NormalizedDocument:
    return NormalizedDocument(
        id="doc1",
        source_id="doc1",
        source_type="txt",
        title="Test",
        text="Some text.",
    )


def _run() -> IngestionRun:
    return IngestionRun(
        id="run1",
        source_type="txt",
        started_at=datetime.now(timezone.utc),
        status="running",
        version="0.1",
        input_path="/tmp/test.txt",
    )


def _parents() -> list[ParentChunk]:
    return [
        ParentChunk(id="p1", document_id="doc1", text="parent", position=0, token_count=1),
    ]


def _children() -> list[ChildChunk]:
    return [
        ChildChunk(id="c1", parent_id="p1", document_id="doc1", text="child", position=0, token_count=1),
    ]


def test_write_ingestion_run_calls_session():
    """write_ingestion_run runs MERGE query with run properties."""
    session = MagicMock()
    run = _run()
    write_ingestion_run(session, run)
    session.run.assert_called_once()
    call = session.run.call_args
    assert "MERGE" in call[0][0] and "IngestionRun" in call[0][0]
    assert call[0][1].get("id") == run.id


def test_write_document_calls_session():
    """write_document runs MERGE Document query."""
    session = MagicMock()
    doc = _doc()
    write_document(session, doc)
    session.run.assert_called_once()
    call = session.run.call_args
    assert "Document" in call[0][0] and call[0][1].get("id") == doc.id


def test_link_document_to_ingestion_run_calls_session():
    """link_document_to_ingestion_run runs MATCH/MERGE for INGESTED_IN."""
    session = MagicMock()
    link_document_to_ingestion_run(session, "doc1", "run1")
    session.run.assert_called_once()
    call = session.run.call_args
    assert "INGESTED_IN" in call[0][0] or "IngestionRun" in call[0][0]
    assert call[0][1].get("document_id") == "doc1" and call[0][1].get("run_id") == "run1"


def test_write_parent_chunks_empty_no_op():
    """write_parent_chunks with empty list does not run query."""
    session = MagicMock()
    write_parent_chunks(session, [])
    session.run.assert_not_called()


def test_write_parent_chunks_calls_batched_write():
    """write_parent_chunks runs UNWIND MERGE for ParentChunk."""
    session = MagicMock()
    write_parent_chunks(session, _parents())
    session.run.assert_called()
    call = session.run.call_args
    assert "ParentChunk" in call[0][0] and "UNWIND" in call[0][0]


def test_link_document_to_parents_empty_no_op():
    """link_document_to_parents with empty parent_ids does not run."""
    session = MagicMock()
    link_document_to_parents(session, "doc1", [])
    session.run.assert_not_called()


def test_write_child_chunks_includes_embedding_when_present():
    """write_child_chunks runs second batch for embeddings when children have embedding."""
    session = MagicMock()
    children = [
        ChildChunk(id="c1", parent_id="p1", document_id="doc1", text="x", position=0, token_count=1, embedding=[0.1, 0.2]),
    ]
    write_child_chunks(session, children)
    assert session.run.call_count >= 2  # MERGE Chunk + SET embedding
    calls = [c[0][0] for c in session.run.call_args_list]
    assert any("embedding" in q for q in calls)


def test_link_chunk_sequence_builds_reading_order_pairs():
    """link_chunk_sequence produces NEXT_CHUNK pairs by position per parent."""
    session = MagicMock()
    children = [
        ChildChunk(id="c0", parent_id="p1", document_id="doc1", text="a", position=0, token_count=1),
        ChildChunk(id="c1", parent_id="p1", document_id="doc1", text="b", position=1, token_count=1),
    ]
    link_chunk_sequence(session, children)
    session.run.assert_called_once()
    rows = session.run.call_args[0][1]["rows"]
    assert rows == [{"a": "c0", "b": "c1"}]


def test_write_lexical_graph_raises_on_invalid_payload():
    """write_lexical_graph calls validator and raises before writing when payload invalid."""
    doc = _doc()
    parents = _parents()
    children = [ChildChunk(id="c1", parent_id="nonexistent", document_id="doc1", text="x", position=0, token_count=1)]
    run = _run()
    with pytest.raises(ValidationError) as exc:
        write_lexical_graph(doc, parents, children, run)
    assert "parent_id" in str(exc.value).lower() or "orphan" in str(exc.value).lower()
