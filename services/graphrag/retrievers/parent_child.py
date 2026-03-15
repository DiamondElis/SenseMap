"""
Parent-child retriever: vector search on child chunks, traverse to parents, dedupe by max child score.
Uses the standard pattern: MATCH (node)<-[:HAS_CHILD]-(parent) WITH parent, max(score) AS score RETURN ...
"""
from typing import Optional

from shared.python.models.retrieval import RetrievalHit

from services.embeddings import get_embedder
from ._neo4j import get_driver, VECTOR_INDEX_NAME


def retrieve(
    query: str,
    k_children: int = 12,
    k_parents: int = 6,
    *,
    embedder=None,
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
) -> list[RetrievalHit]:
    """
    Run child chunk vector search, traverse to parents via HAS_CHILD, dedupe parents by max child score,
    return top k_parents.
    """
    if not query or not query.strip():
        return []
    embed = embedder or get_embedder()
    vectors = embed.embed_texts([query.strip()])
    if not vectors or not vectors[0]:
        return []
    query_embedding = vectors[0]

    driver = get_driver(uri=uri, user=user, password=password)
    hits: list[RetrievalHit] = []
    try:
        with driver.session() as session:
            r = session.run(
                """
                CALL db.index.vector.queryNodes($index, $vector_k, $embedding) YIELD node AS child, score
                MATCH (child)<-[:HAS_CHILD]-(parent)
                WITH parent, max(score) AS score
                RETURN parent.id AS id, parent.text AS text, score
                ORDER BY score DESC
                LIMIT $limit_k
                """,
                index=VECTOR_INDEX_NAME,
                vector_k=k_children,
                limit_k=k_parents,
                embedding=query_embedding,
            )
            for rec in r:
                nid = rec["id"]
                if nid is None:
                    continue
                hits.append(
                    RetrievalHit(
                        node_id=str(nid),
                        node_label="ParentChunk",
                        text=(rec["text"] or ""),
                        score=float(rec["score"]) if rec["score"] is not None else 0.0,
                        metadata={},
                        provenance={},
                    )
                )
    finally:
        driver.close()
    return hits
