"""
Graph-serving endpoints: neighborhood, community, query-trace.
Returns nodes and edges with labels and properties for 3D visualization.
"""
from typing import Any
import uuid

from neo4j import GraphDatabase

from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


def _driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# In-memory store for query traces: query_id -> list of chunk/node ids from retrieval/answer
_query_traces: dict[str, list[str]] = {}


def store_query_trace(query_id: str, node_ids: list[str]) -> None:
    _query_traces[query_id] = list(node_ids)


def get_query_trace_ids(query_id: str) -> list[str]:
    return _query_traces.get(query_id, [])


def generate_query_id() -> str:
    return str(uuid.uuid4())


def get_neighborhood(entity_id: str, hops: int = 2) -> dict[str, Any]:
    """
    Expand from a node (any label) by N hops; return nodes and edges with labels and key props.
    Uses variable-length path; no GDS required.
    """
    if not entity_id or hops < 0:
        return {"nodes": [], "edges": []}
    driver = _driver()
    depth = min(int(hops), 5)
    with driver.session() as session:
        r = session.run(
            """
            MATCH (start) WHERE start.id = $id
            MATCH path = (start)-[*1..%d]-(other)
            WHERE other.id IS NOT NULL
            WITH collect(DISTINCT start) + collect(DISTINCT other) AS nodeList
            UNWIND nodeList AS n WHERE n IS NOT NULL
            WITH collect(DISTINCT n) AS nodes
            UNWIND nodes AS n
            WITH nodes,
                 [x IN nodes | {
                   id: x.id,
                   label: labels(x)[0],
                   text: coalesce(toString(x.text), toString(x.name), '')[:500],
                   communityId: x.communityId,
                   pagerank: x.pagerank,
                   type: x.type
                 }] AS nodeData
            WITH nodes, nodeData
            UNWIND nodes AS n1
            MATCH (n1)-[r]->(n2) WHERE n2 IN nodes
            WITH nodeData AS nodes, collect(DISTINCT { source: n1.id, target: n2.id, type: type(r) }) AS edgeList
            RETURN nodes, [e IN edgeList WHERE e.source IS NOT NULL AND e.target IS NOT NULL] AS edges
            """ % depth,
            id=entity_id,
        )
        row = r.single()
    driver.close()
    if not row:
        return {"nodes": [], "edges": []}
    nodes = row.get("nodes") or []
    edges = [{"source": e["source"], "target": e["target"], "type": e.get("type", "RELATED")} for e in (row.get("edges") or []) if e.get("source") and e.get("target")]
    return {"nodes": nodes, "edges": edges}


def get_community(community_id: str) -> dict[str, Any]:
    """All nodes with communityId = community_id and edges between them."""
    if not community_id:
        return {"nodes": [], "edges": []}
    driver = _driver()
    with driver.session() as session:
        r = session.run(
            """
            MATCH (n) WHERE n.communityId = $cid
            WITH collect(n) AS nodeList
            UNWIND nodeList AS n
            WITH nodeList,
                 [x IN nodeList | {
                   id: x.id,
                   label: labels(x)[0],
                   text: coalesce(toString(x.text), toString(x.name), '')[:500],
                   communityId: x.communityId,
                   pagerank: x.pagerank,
                   type: x.type
                 }] AS nodes
            UNWIND nodeList AS n1
            MATCH (n1)-[r]->(n2) WHERE n2 IN nodeList
            WITH nodes, collect(DISTINCT { source: n1.id, target: n2.id, type: type(r) }) AS edgeList
            RETURN nodes, [e IN edgeList WHERE e.source IS NOT NULL AND e.target IS NOT NULL] AS edges
            """,
            cid=community_id,
        )
        row = r.single()
    driver.close()
    if not row:
        return {"nodes": [], "edges": []}
    nodes = row.get("nodes") or []
    edges = [{"source": e["source"], "target": e["target"], "type": e.get("type", "RELATED")} for e in (row.get("edges") or []) if e.get("source") and e.get("target")]
    return {"nodes": nodes, "edges": edges}
