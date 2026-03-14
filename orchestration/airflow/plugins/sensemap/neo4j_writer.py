"""Write documents, chunks, and structural edges to Neo4j lexical graph."""
from typing import Any

try:
    from neo4j import GraphDatabase
except ImportError:
    GraphDatabase = None  # type: ignore[misc, assignment]


def _driver(uri: str, user: str, password: str):
    if GraphDatabase is None:
        raise RuntimeError("neo4j driver required; pip install neo4j")
    return GraphDatabase.driver(uri, auth=(user, password))


def write_documents(
    parsed_docs: list[dict[str, Any]],
    run_id: str,
    uri: str,
    user: str,
    password: str,
) -> None:
    """Create Document nodes with id, source, run_id."""
    if not parsed_docs:
        return
    driver = _driver(uri, user, password)
    with driver.session() as session:
        for doc in parsed_docs:
            session.run(
                """
                MERGE (d:Document {id: $id})
                SET d.source = $source, d.run_id = $run_id
                """,
                id=doc["id"],
                source=doc.get("source", ""),
                run_id=run_id,
            )
    driver.close()


def write_parent_chunks(
    parent_chunks: list[dict[str, Any]],
    run_id: str,
    uri: str,
    user: str,
    password: str,
) -> None:
    """Create Chunk nodes for parents (no embedding). Link PART_OF Document."""
    if not parent_chunks:
        return
    driver = _driver(uri, user, password)
    with driver.session() as session:
        for p in parent_chunks:
            session.run(
                """
                MERGE (c:Chunk {id: $id})
                SET c.text = $text, c.position = $position, c.run_id = $run_id
                WITH c
                MATCH (d:Document {id: $document_id})
                MERGE (c)-[:PART_OF]->(d)
                """,
                id=p["id"],
                text=p.get("text", ""),
                position=p.get("position", 0),
                run_id=run_id,
                document_id=p["document_id"],
            )
    driver.close()


def write_child_chunks(
    child_chunks: list[dict[str, Any]],
    run_id: str,
    uri: str,
    user: str,
    password: str,
) -> None:
    """Create Chunk nodes for children with embedding. Link PART_OF Document and PART_OF parent Chunk."""
    if not child_chunks:
        return
    driver = _driver(uri, user, password)
    with driver.session() as session:
        for c in child_chunks:
            session.run(
                """
                MERGE (c:Chunk {id: $id})
                SET c.text = $text, c.position = $position, c.run_id = $run_id, c.embedding = $embedding
                WITH c
                MATCH (d:Document {id: $document_id})
                MERGE (c)-[:PART_OF]->(d)
                WITH c
                MATCH (parent:Chunk {id: $parent_id})
                MERGE (c)-[:PART_OF]->(parent)
                """,
                id=c["id"],
                text=c.get("text", ""),
                position=c.get("position", 0),
                run_id=run_id,
                embedding=c.get("embedding", []),
                document_id=c["document_id"],
                parent_id=c["parent_id"],
            )
    driver.close()


def create_part_of_and_next_chunk_edges(
    parent_chunks: list[dict[str, Any]],
    child_chunks: list[dict[str, Any]],
    uri: str,
    user: str,
    password: str,
) -> None:
    """Create NEXT_CHUNK edges between consecutive siblings (parents and children)."""
    driver = _driver(uri, user, password)
    with driver.session() as session:
        # Next edges between parent chunks of same document
        by_doc: dict[str, list[dict[str, Any]]] = {}
        for p in parent_chunks:
            doc_id = p["document_id"]
            by_doc.setdefault(doc_id, []).append(p)
        for doc_id, parents in by_doc.items():
            parents_sorted = sorted(parents, key=lambda x: x["position"])
            for i in range(len(parents_sorted) - 1):
                a, b = parents_sorted[i]["id"], parents_sorted[i + 1]["id"]
                session.run(
                    "MATCH (a:Chunk {id: $a}), (b:Chunk {id: $b}) MERGE (a)-[:NEXT_CHUNK]->(b)",
                    a=a, b=b,
                )
        # Next edges between child chunks of same parent
        by_parent: dict[str, list[dict[str, Any]]] = {}
        for c in child_chunks:
            pid = c["parent_id"]
            by_parent.setdefault(pid, []).append(c)
        for pid, children in by_parent.items():
            children_sorted = sorted(children, key=lambda x: x["position"])
            for i in range(len(children_sorted) - 1):
                a, b = children_sorted[i]["id"], children_sorted[i + 1]["id"]
                session.run(
                    "MATCH (a:Chunk {id: $a}), (b:Chunk {id: $b}) MERGE (a)-[:NEXT_CHUNK]->(b)",
                    a=a, b=b,
                )
    driver.close()


def validate_ingestion_run(
    run_id: str,
    expected_docs: int,
    expected_parent_chunks: int,
    expected_child_chunks: int,
    uri: str,
    user: str,
    password: str,
) -> None:
    """Verify Document and Chunk counts for this run_id; raise if mismatch."""
    driver = _driver(uri, user, password)
    with driver.session() as session:
        r = session.run(
            "MATCH (d:Document) WHERE d.run_id = $run_id RETURN count(d) AS n",
            run_id=run_id,
        )
        doc_count = r.single()["n"]
        r = session.run(
            "MATCH (c:Chunk) WHERE c.run_id = $run_id RETURN count(c) AS n",
            run_id=run_id,
        )
        chunk_count = r.single()["n"]
    driver.close()
    if doc_count != expected_docs:
        raise ValueError(f"Document count mismatch: got {doc_count}, expected {expected_docs}")
    if chunk_count != expected_parent_chunks + expected_child_chunks:
        raise ValueError(
            f"Chunk count mismatch: got {chunk_count}, expected {expected_parent_chunks + expected_child_chunks}"
        )
