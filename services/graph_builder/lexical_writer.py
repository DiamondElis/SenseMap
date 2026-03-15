"""
Lexical graph writer: Document, ParentChunk, Chunk, IngestionRun and structural edges.
Uses MERGE for idempotent writes; embeddings only on child Chunk nodes; NEXT_CHUNK in reading order.
"""
from typing import Any, Optional

from shared.python.models.ingestion import NormalizedDocument, IngestionRun
from shared.python.models.chunks import ParentChunk, ChildChunk

from .merge_utils import get_driver, run_write_query, run_batched_write
from .provenance import (
    document_properties,
    parent_chunk_properties,
    child_chunk_properties,
    ingestion_run_properties,
)
from .validators import validate_lexical_payload, ValidationError


def write_ingestion_run(session: Any, run: IngestionRun) -> None:
    """Create or merge the IngestionRun node."""
    run_write_query(
        session,
        """
        MERGE (r:IngestionRun {id: $id})
        SET r.source_type = $source_type, r.started_at = $started_at, r.status = $status,
            r.version = $version, r.input_path = $input_path
        """,
        ingestion_run_properties(run),
    )


def write_document(session: Any, document: NormalizedDocument) -> None:
    """MERGE Document node by document id."""
    run_write_query(
        session,
        """
        MERGE (d:Document {id: $id})
        SET d.source_id = $source_id, d.source_type = $source_type, d.title = $title,
            d.author = $author, d.uri = $uri, d.created_at = $created_at, d.text = $text,
            d.metadata = $metadata
        """,
        document_properties(document),
    )


def link_document_to_ingestion_run(
    session: Any, document_id: str, run_id: str
) -> None:
    """MERGE (Document)-[:INGESTED_IN]->(IngestionRun)."""
    run_write_query(
        session,
        """
        MATCH (d:Document {id: $document_id}), (r:IngestionRun {id: $run_id})
        MERGE (d)-[:INGESTED_IN]->(r)
        """,
        {"document_id": document_id, "run_id": run_id},
    )


def write_parent_chunks(session: Any, parent_chunks: list[ParentChunk]) -> None:
    """MERGE ParentChunk nodes by chunk id. No embeddings (parent chunks do not need them)."""
    if not parent_chunks:
        return
    rows = [parent_chunk_properties(p) for p in parent_chunks]
    run_batched_write(
        session,
        """
        UNWIND $rows AS row
        MERGE (pc:ParentChunk {id: row.id})
        SET pc.document_id = row.document_id, pc.text = row.text, pc.position = row.position,
            pc.token_count = row.token_count, pc.metadata = row.metadata
        """,
        rows,
    )


def link_document_to_parents(
    session: Any, document_id: str, parent_ids: list[str]
) -> None:
    """MERGE (Document)-[:HAS_PARENT]->(ParentChunk) for each parent id."""
    if not parent_ids:
        return
    rows = [{"document_id": document_id, "parent_id": pid} for pid in parent_ids]
    run_batched_write(
        session,
        """
        UNWIND $rows AS row
        MATCH (d:Document {id: row.document_id}), (pc:ParentChunk {id: row.parent_id})
        MERGE (d)-[:HAS_PARENT]->(pc)
        """,
        rows,
    )


def write_child_chunks(session: Any, child_chunks: list[ChildChunk]) -> None:
    """MERGE Chunk nodes by id; write embeddings only to child Chunk nodes."""
    if not child_chunks:
        return
    rows = [child_chunk_properties(c) for c in child_chunks]
    run_batched_write(
        session,
        """
        UNWIND $rows AS row
        MERGE (ch:Chunk {id: row.id})
        SET ch.parent_id = row.parent_id, ch.document_id = row.document_id, ch.text = row.text,
            ch.position = row.position, ch.token_count = row.token_count, ch.metadata = row.metadata
        """,
        rows,
    )
    embedding_rows = [
        {"id": c.id, "embedding": c.embedding}
        for c in child_chunks
        if c.embedding is not None
    ]
    if embedding_rows:
        run_batched_write(
            session,
            "UNWIND $rows AS row MATCH (ch:Chunk {id: row.id}) SET ch.embedding = row.embedding",
            embedding_rows,
        )


def link_parents_to_children(
    session: Any, parent_child_pairs: list[tuple[str, str]]
) -> None:
    """MERGE (ParentChunk)-[:HAS_CHILD]->(Chunk) for each (parent_id, child_id) pair."""
    if not parent_child_pairs:
        return
    rows = [
        {"parent_id": pid, "child_id": cid}
        for pid, cid in parent_child_pairs
    ]
    run_batched_write(
        session,
        """
        UNWIND $rows AS row
        MATCH (pc:ParentChunk {id: row.parent_id}), (ch:Chunk {id: row.child_id})
        MERGE (pc)-[:HAS_CHILD]->(ch)
        """,
        rows,
    )


def link_chunk_sequence(session: Any, child_chunks: list[ChildChunk]) -> None:
    """MERGE (Chunk)-[:NEXT_CHUNK]->(Chunk) in reading order (by position per parent)."""
    by_parent: dict[str, list[ChildChunk]] = {}
    for c in child_chunks:
        by_parent.setdefault(c.parent_id, []).append(c)
    next_chunk_rows: list[dict[str, str]] = []
    for children in by_parent.values():
        sorted_children = sorted(children, key=lambda x: x.position)
        for i in range(len(sorted_children) - 1):
            next_chunk_rows.append({
                "a": sorted_children[i].id,
                "b": sorted_children[i + 1].id,
            })
    if not next_chunk_rows:
        return
    run_batched_write(
        session,
        """
        UNWIND $rows AS row
        MATCH (a:Chunk {id: row.a}), (b:Chunk {id: row.b})
        MERGE (a)-[:NEXT_CHUNK]->(b)
        """,
        next_chunk_rows,
    )


def write_lexical_graph(
    document: NormalizedDocument,
    parent_chunks: list[ParentChunk],
    child_chunks: list[ChildChunk],
    ingestion_run: IngestionRun,
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
) -> None:
    """
    Persist document, parent/child chunks, and ingestion run into Neo4j.
    Uses MERGE throughout so rerunning with the same payload does not create duplicates.
    Relationships: Document -[:HAS_PARENT]-> ParentChunk -[:HAS_CHILD]-> Chunk,
    Chunk -[:NEXT_CHUNK]-> Chunk (reading order), Document -[:INGESTED_IN]-> IngestionRun.
    Embeddings are written only to child Chunk nodes.
    """
    validate_lexical_payload(document, parent_chunks, child_chunks, ingestion_run)

    driver = get_driver(uri, user, password)
    try:
        with driver.session() as session:
            write_ingestion_run(session, ingestion_run)
            write_document(session, document)
            link_document_to_ingestion_run(session, document.id, ingestion_run.id)

            write_parent_chunks(session, parent_chunks)
            link_document_to_parents(
                session, document.id, [p.id for p in parent_chunks]
            )

            write_child_chunks(session, child_chunks)
            link_parents_to_children(
                session,
                [(c.parent_id, c.id) for c in child_chunks],
            )
            link_chunk_sequence(session, child_chunks)
    finally:
        driver.close()
