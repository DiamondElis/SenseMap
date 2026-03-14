"""
Baseline GraphRAG retrieval: basic vector → parent-child → NEXT_CHUNK expansion.
Schema: Chunk (embedding on children), (child)-[:PART_OF]->(parent:Chunk), (Chunk)-[:NEXT_CHUNK]->(Chunk).
"""
from typing import Any

from neo4j import GraphDatabase

from config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER, VECTOR_INDEX_NAME


def _driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def basic_vector_retrieve(
    query_embedding: list[float],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Vector similarity search on Chunk.embedding; return chunks with text and score."""
    driver = _driver()
    results: list[dict[str, Any]] = []
    with driver.session() as session:
        # Procedure works across Neo4j 5.x; SEARCH clause is alternative in 5.15+
        r = session.run(
            "CALL db.index.vector.queryNodes($index, $k, $embedding) YIELD node, score "
            "RETURN node.id AS id, node.text AS text, score",
            index=VECTOR_INDEX_NAME,
            k=top_k,
            embedding=query_embedding,
        )
        for rec in r:
            results.append({
                "id": rec["id"],
                "text": rec["text"] or "",
                "score": float(rec["score"]) if rec["score"] is not None else 0.0,
                "metadata": {},
            })
    driver.close()
    return results


def parent_child_retrieve(
    query_embedding: list[float],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """
    Vector search on child chunks; for each, get parent Chunk via PART_OF.
    Returns parent.text and max score per parent (GraphRAG pattern: child embeddings, return parents).
    Schema: (child)-[:PART_OF]->(parent:Chunk); equivalent to (node)<-[:HAS_CHILD]-(parent).
    """
    driver = _driver()
    results: list[dict[str, Any]] = []
    with driver.session() as session:
        # Find child chunks by vector, then get parent Chunk (exclude PART_OF Document)
        r = session.run(
            """
            CALL db.index.vector.queryNodes($index, $vector_k, $embedding) YIELD node AS child, score
            MATCH (child)-[:PART_OF]->(parent:Chunk)
            WITH parent, max(score) AS score
            RETURN parent.id AS id, parent.text AS text, score
            ORDER BY score DESC
            LIMIT $limit_k
            """,
            index=VECTOR_INDEX_NAME,
            vector_k=top_k * 3,
            limit_k=top_k,
            embedding=query_embedding,
        )
        for rec in r:
            results.append({
                "id": rec["id"],
                "text": rec["text"] or "",
                "score": float(rec["score"]) if rec["score"] is not None else 0.0,
                "metadata": {},
            })
    driver.close()
    return results


def expand_adjacency(chunk_ids: list[str], depth: int = 1) -> list[dict[str, Any]]:
    """
    Expand from given chunk ids along NEXT_CHUNK (and reverse) to get adjacent chunks.
    Returns list of {id, text, metadata} for the seed and adjacent chunks.
    """
    if not chunk_ids:
        return []
    driver = _driver()
    seen: set[str] = set()
    with driver.session() as session:
        # Get seed chunks
        r = session.run(
            "MATCH (c:Chunk) WHERE c.id IN $ids RETURN c.id AS id, c.text AS text",
            ids=chunk_ids,
        )
        nodes: list[dict[str, Any]] = []
        for rec in r:
            nid = rec["id"]
            if nid not in seen:
                seen.add(nid)
                nodes.append({"id": nid, "text": rec["text"] or "", "metadata": {"seed": True}})
        # Expand along NEXT_CHUNK (outgoing and incoming) up to depth
        current = set(chunk_ids)
        for _ in range(depth):
            r = session.run(
                """
                MATCH (a:Chunk)-[:NEXT_CHUNK]-(b:Chunk)
                WHERE a.id IN $ids
                RETURN b.id AS id, b.text AS text
                """,
                ids=list(current),
            )
            next_ids: set[str] = set()
            for rec in r:
                nid = rec["id"]
                next_ids.add(nid)
                if nid not in seen:
                    seen.add(nid)
                    nodes.append({"id": nid, "text": rec["text"] or "", "metadata": {"seed": False}})
            current = next_ids
            if not current:
                break
    driver.close()
    return nodes


def get_subgraph(chunk_ids: list[str], expand_depth: int = 1) -> dict[str, Any]:
    """
    Return nodes and edges for visualization: seed chunks + NEXT_CHUNK and PART_OF neighborhood.
    """
    if not chunk_ids:
        return {"nodes": [], "edges": []}
    driver = _driver()
    with driver.session() as session:
        # Nodes: chunks in ids or adjacent via NEXT_CHUNK
        r = session.run(
            """
            MATCH (c:Chunk) WHERE c.id IN $ids
            OPTIONAL MATCH (c)-[:NEXT_CHUNK]-(n:Chunk)
            WITH collect(DISTINCT c) + collect(DISTINCT n) AS allNodes
            UNWIND allNodes AS n WHERE n IS NOT NULL
            WITH collect(DISTINCT n) AS nodes
            UNWIND nodes AS n
            RETURN n.id AS id, n.text AS text, labels(n)[0] AS label
            """,
            ids=chunk_ids,
        )
        nodes = [{"id": rec["id"], "text": (rec["text"] or "")[:200], "label": rec.get("label") or "Chunk"} for rec in r]
        ids_in_subgraph = {n["id"] for n in nodes}
        # Edges: NEXT_CHUNK and PART_OF among these nodes
        r = session.run(
            """
            MATCH (a:Chunk)-[r:PART_OF|NEXT_CHUNK]->(b)
            WHERE a.id IN $ids AND b.id IN $ids
            RETURN a.id AS source, b.id AS target, type(r) AS type
            """,
            ids=list(ids_in_subgraph),
        )
        edges = [{"source": rec["source"], "target": rec["target"], "type": rec["type"]} for rec in r]
    driver.close()
    return {"nodes": nodes, "edges": edges}
