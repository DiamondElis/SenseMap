"""
Run GDS enrichment: project 'kg' then PageRank, Leiden, FastRP, Node Similarity.
Only run when the hybrid graph (entities and relationships) is stable.
"""
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

from sensemap.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

# In Airflow container, GDS Cypher files are under plugins; we run inline to avoid path issues.
GDS_STEPS = [
    ("Drop existing graph", "CALL gds.graph.drop('kg', false) YIELD graphName RETURN graphName"),
    (
        "Project kg",
        "CALL gds.graph.project('kg', ['Document', 'Chunk', 'Entity'], "
        "['PART_OF', 'MENTIONS', 'RELATES_TO', 'NEXT_CHUNK']) "
        "YIELD graphName, nodeCount, relationshipCount RETURN graphName, nodeCount, relationshipCount",
    ),
    (
        "PageRank",
        "CALL gds.pageRank.write('kg', { writeProperty: 'pagerank' }) "
        "YIELD nodePropertiesWritten, ranIterations RETURN nodePropertiesWritten, ranIterations",
    ),
    (
        "Leiden",
        "CALL gds.leiden.write('kg', { writeProperty: 'communityId', randomSeed: 19 }) "
        "YIELD nodePropertiesWritten, communityCount RETURN nodePropertiesWritten, communityCount",
    ),
    (
        "FastRP",
        "CALL gds.fastRP.write('kg', { embeddingDimension: 128, writeProperty: 'graphEmbedding' }) "
        "YIELD nodePropertiesWritten RETURN nodePropertiesWritten",
    ),
    (
        "Node Similarity",
        "CALL gds.nodeSimilarity.write('kg', { writeRelationshipType: 'SIMILAR', writeProperty: 'score', topK: 10, similarityCutoff: 0.1 }) "
        "YIELD nodesCompared, relationshipsWritten RETURN nodesCompared, relationshipsWritten",
    ),
]


def run_gds_enrichment(
    uri: str = NEO4J_URI,
    user: str = NEO4J_USER,
    password: str = NEO4J_PASSWORD,
    skip_node_similarity: bool = False,
) -> list[dict[str, Any]]:
    """
    Run GDS steps in order. Returns list of step names and result summaries.
    skip_node_similarity: set True to run only PageRank, Leiden, FastRP.
    """
    driver = GraphDatabase.driver(uri, auth=(user, password))
    results: list[dict[str, Any]] = []
    steps = [s for s in GDS_STEPS if s[0] != "Node Similarity" or not skip_node_similarity]
    with driver.session() as session:
        for name, query in steps:
            try:
                r = session.run(query)
                rec = r.single()
                results.append({"step": name, "success": True, "record": dict(rec) if rec else None})
            except Exception as e:
                err = str(e).lower()
                if name == "Drop existing graph" and ("not find" in err or "does not exist" in err or "unknown" in err):
                    results.append({"step": name, "success": True, "record": None})
                    continue
                results.append({"step": name, "success": False, "error": str(e)})
                raise
    driver.close()
    return results
