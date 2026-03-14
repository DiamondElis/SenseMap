"""
Single pipeline run: PDF source -> load -> parse -> parent/child chunks -> embeddings -> Neo4j.
Matches Neo4j KG builder flow: data loader, text splitter, chunk embeddings, lexical graph.
"""
from pathlib import Path
from typing import Any

from sensemap.config import (
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    OPENAI_API_KEY,
    CHILD_CHUNK_OVERLAP,
    CHILD_CHUNK_SIZE,
    EMBEDDING_MODEL,
    PARENT_CHUNK_OVERLAP,
    PARENT_CHUNK_SIZE,
)
from sensemap.load_documents import load_documents
from sensemap.parse_documents import parse_documents
from sensemap.chunking import create_parent_child_chunks
from sensemap.embeddings import generate_chunk_embeddings
from sensemap.neo4j_writer import (
    write_documents,
    write_parent_chunks,
    write_child_chunks,
    create_part_of_and_next_chunk_edges,
    validate_ingestion_run,
)


def ingest_pdf_run(source_path: str, run_id: str) -> None:
    """
    Run the full PDF ingestion pipeline:
    load -> parse -> parent/child chunks -> child embeddings -> Neo4j writes -> validate.
    """
    paths = load_documents(source_path)
    parsed_docs = parse_documents(paths)

    parent_chunks: list[dict[str, Any]] = []
    child_chunks: list[dict[str, Any]] = []

    for doc in parsed_docs:
        p_chunks, c_chunks = create_parent_child_chunks(
            [doc],
            parent_chunk_size=PARENT_CHUNK_SIZE,
            parent_chunk_overlap=PARENT_CHUNK_OVERLAP,
            child_chunk_size=CHILD_CHUNK_SIZE,
            child_chunk_overlap=CHILD_CHUNK_OVERLAP,
        )
        parent_chunks.extend(p_chunks)
        child_chunks.extend(c_chunks)

    child_chunks = generate_chunk_embeddings(
        child_chunks,
        model=EMBEDDING_MODEL,
        api_key=OPENAI_API_KEY or None,
    )

    write_documents(parsed_docs, run_id, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    write_parent_chunks(parent_chunks, run_id, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    write_child_chunks(child_chunks, run_id, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    create_part_of_and_next_chunk_edges(
        parent_chunks, child_chunks, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
    )
    validate_ingestion_run(
        run_id,
        expected_docs=len(parsed_docs),
        expected_parent_chunks=len(parent_chunks),
        expected_child_chunks=len(child_chunks),
        uri=NEO4J_URI,
        user=NEO4J_USER,
        password=NEO4J_PASSWORD,
    )
