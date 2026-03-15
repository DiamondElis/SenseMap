"""
Basic vector retriever: embed query, search Chunk.embedding, return top-k child chunk hits.
"""
from typing import Optional

from shared.python.models.retrieval import RetrievalHit

from services.embeddings import get_embedder
from ._neo4j import get_driver, VECTOR_INDEX_NAME


def retrieve(
    query: str,
    k: int = 8,
    *,
    embedder=None,
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
) -> list[RetrievalHit]:
    """
    Embed the query, run vector similarity search on Chunk.embedding, return top-k hits.
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
                "CALL db.index.vector.queryNodes($index, $k, $embedding) YIELD node, score "
                "RETURN node.id AS id, node.text AS text, score",
                index=VECTOR_INDEX_NAME,
                k=k,
                embedding=query_embedding,
            )
            for rec in r:
                hits.append(
                    RetrievalHit(
                        node_id=rec["id"] or "",
                        node_label="Chunk",
                        text=(rec["text"] or ""),
                        score=float(rec["score"]) if rec["score"] is not None else 0.0,
                        metadata={},
                        provenance={},
                    )
                )
    finally:
        driver.close()
    return hits
