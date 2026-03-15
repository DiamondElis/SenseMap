"""
Graph-serving endpoints: neighborhood, community, query-trace, lexical document graph.
Returns nodes and edges with labels and properties for 3D visualization.
Lexical graph: Document, ParentChunk, Chunk, IngestionRun and HAS_PARENT, HAS_CHILD, NEXT_CHUNK, INGESTED_IN.
"""
from typing import Any
import uuid

from neo4j import GraphDatabase

from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


def _driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def _node_payload(n: dict) -> dict[str, Any]:
    """Normalize a Neo4j node map to the shape expected by the graph UI."""
    nid = n.get("id")
    if nid is None:
        return {}
    label = n.get("label") or "Node"
    text = (
        (n.get("text") or "")[:500]
        or (n.get("title") or "")[:500]
        or (n.get("name") or "")[:500]
    )
    return {
        "id": str(nid),
        "label": label,
        "text": text,
        "communityId": n.get("communityId"),
        "pagerank": n.get("pagerank"),
        "type": n.get("type"),
    }


# In-memory store for query traces: query_id -> list of chunk/node ids from retrieval/answer
_query_traces: dict[str, list[str]] = {}


def store_query_trace(query_id: str, node_ids: list[str]) -> None:
    _query_traces[query_id] = list(node_ids)


def get_query_trace_ids(query_id: str) -> list[str]:
    return _query_traces.get(query_id, [])


def generate_query_id() -> str:
    return str(uuid.uuid4())


def list_lexical_documents() -> list[dict[str, Any]]:
    """Return list of Document nodes (id, title, source_type) for UI to choose from."""
    driver = _driver()
    with driver.session() as session:
        r = session.run(
            "MATCH (d:Document) RETURN d.id AS id, d.title AS title, d.source_type AS source_type ORDER BY d.id"
        )
        rows = list(r)
    driver.close()
    return [{"id": rec["id"], "title": rec.get("title") or rec["id"], "source_type": rec.get("source_type") or ""} for rec in rows]


def get_lexical_document(document_id: str) -> dict[str, Any]:
    """
    Return full lexical graph for one document: Document, ParentChunk, Chunk, IngestionRun
    and edges HAS_PARENT, HAS_CHILD, NEXT_CHUNK, INGESTED_IN. Shape matches graph UI expectations.
    """
    if not document_id or not document_id.strip():
        return {"nodes": [], "edges": []}
    driver = _driver()
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    with driver.session() as session:
        # Document and IngestionRun
        r = session.run(
            """
            MATCH (d:Document {id: $document_id})
            OPTIONAL MATCH (d)-[:INGESTED_IN]->(r:IngestionRun)
            RETURN d, r
            """,
            document_id=document_id.strip(),
        )
        row = r.single()
        if not row or not row.get("d"):
            driver.close()
            return {"nodes": [], "edges": []}
        doc_id = str(document_id.strip())
        d, r = row["d"], row.get("r")
        nodes.append(_node_payload({"id": d["id"], "label": "Document", "text": d.get("text") or d.get("title") or "", "title": d.get("title")}))
        if r:
            nodes.append(_node_payload({"id": r["id"], "label": "IngestionRun", "text": r.get("input_path") or r.get("status") or ""}))
            edges.append({"source": doc_id, "target": str(r["id"]), "type": "INGESTED_IN"})

        # ParentChunks and HAS_PARENT
        r = session.run(
            """
            MATCH (d:Document {id: $document_id})-[:HAS_PARENT]->(pc:ParentChunk)
            RETURN pc
            """,
            document_id=document_id.strip(),
        )
        for rec in r:
            pc = rec["pc"]
            pc_id = str(pc["id"])
            nodes.append(_node_payload({"id": pc_id, "label": "ParentChunk", "text": pc.get("text") or ""}))
            edges.append({"source": doc_id, "target": pc_id, "type": "HAS_PARENT"})

        # Chunks and HAS_CHILD
        r = session.run(
            """
            MATCH (d:Document {id: $document_id})-[:HAS_PARENT]->(pc:ParentChunk)-[:HAS_CHILD]->(ch:Chunk)
            RETURN pc.id AS parent_id, ch
            """,
            document_id=document_id.strip(),
        )
        for rec in r:
            ch = rec["ch"]
            ch_id = str(ch["id"])
            nodes.append(_node_payload({"id": ch_id, "label": "Chunk", "text": ch.get("text") or ""}))
            edges.append({"source": str(rec["parent_id"]), "target": ch_id, "type": "HAS_CHILD"})

        # NEXT_CHUNK between Chunks
        r = session.run(
            """
            MATCH (d:Document {id: $document_id})-[:HAS_PARENT]->(:ParentChunk)-[:HAS_CHILD]->(ch:Chunk)
            MATCH (ch)-[:NEXT_CHUNK]->(ch2:Chunk)
            RETURN ch.id AS source, ch2.id AS target
            """,
            document_id=document_id.strip(),
        )
        for rec in r:
            edges.append({"source": str(rec["source"]), "target": str(rec["target"]), "type": "NEXT_CHUNK"})
    driver.close()
    # Deduplicate nodes by id (keep first)
    seen: set[str] = set()
    unique_nodes: list[dict[str, Any]] = []
    for n in nodes:
        nid = n.get("id")
        if nid and nid not in seen:
            seen.add(nid)
            unique_nodes.append(n)
    return {"nodes": unique_nodes, "edges": edges}


def get_lexical_preview(document_id: str) -> dict[str, Any]:
    """Same as get_lexical_document: full lexical graph for one document (preview entrypoint)."""
    return get_lexical_document(document_id)


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
                   text: coalesce(toString(x.text), toString(x.title), toString(x.name), '')[:500],
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


def get_graph_entities(chunk_id: str) -> dict[str, Any]:
    """
    Return entities and mentions for one chunk: Chunk, EntityMention, Entity
    and edges MENTIONS, REFERS_TO, HAS_ENTITY.
    """
    if not chunk_id or not chunk_id.strip():
        return {"nodes": [], "edges": []}
    chunk_id_s = chunk_id.strip()
    driver = _driver()
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    try:
        with driver.session() as session:
            r = session.run(
                """
                MATCH (ch:Chunk {id: $chunk_id})
                OPTIONAL MATCH (ch)-[:MENTIONS]->(m:EntityMention)-[:REFERS_TO]->(e:Entity)
                RETURN ch, m, e
                """,
                chunk_id=chunk_id_s,
            )
            chunk_added = False
            for rec in r:
                ch, m, e = rec.get("ch"), rec.get("m"), rec.get("e")
                if ch and not chunk_added:
                    nodes.append(_node_payload({"id": ch["id"], "label": "Chunk", "text": ch.get("text") or ""}))
                    chunk_added = True
                if m and m.get("id"):
                    nodes.append(_node_payload({
                        "id": m["id"],
                        "label": "EntityMention",
                        "text": m.get("raw_text") or "",
                        "type": None,
                    }))
                    edges.append({"source": chunk_id_s, "target": str(m["id"]), "type": "MENTIONS"})
                if e and e.get("id"):
                    nodes.append(_node_payload({
                        "id": e["id"],
                        "label": "Entity",
                        "text": e.get("canonical_name") or e.get("description") or "",
                        "type": e.get("type"),
                    }))
                    if m and m.get("id"):
                        edges.append({"source": str(m["id"]), "target": str(e["id"]), "type": "REFERS_TO"})
            r = session.run(
                "MATCH (ch:Chunk {id: $chunk_id})-[:HAS_ENTITY]->(e:Entity) RETURN e.id AS eid",
                chunk_id=chunk_id_s,
            )
            for rec in r:
                edges.append({"source": chunk_id_s, "target": str(rec["eid"]), "type": "HAS_ENTITY"})
    finally:
        driver.close()
    seen: set[str] = set()
    unique_nodes = []
    for n in nodes:
        nid = n.get("id")
        if nid and nid not in seen:
            seen.add(nid)
            unique_nodes.append(n)
    seen_edges: set[tuple[str, str, str]] = set()
    unique_edges = []
    for e in edges:
        key = (e["source"], e["target"], e.get("type") or "")
        if key not in seen_edges:
            seen_edges.add(key)
            unique_edges.append(e)
    return {"nodes": unique_nodes, "edges": unique_edges}


def get_entity_neighborhood(entity_id: str, hops: int = 2) -> dict[str, Any]:
    """Expand from an Entity (or any node) by N hops; return nodes and edges. Reuses generic neighborhood."""
    return get_neighborhood(entity_id, hops=hops)


def get_hybrid_document(document_id: str) -> dict[str, Any]:
    """
    Return combined lexical + entity graph for one document: Document, ParentChunk, Chunk, IngestionRun,
    Entity, EntityMention, and all lexical edges plus MENTIONS, REFERS_TO, HAS_ENTITY, RELATES_TO.
    """
    if not document_id or not document_id.strip():
        return {"nodes": [], "edges": []}
    lexical = get_lexical_document(document_id.strip())
    doc_id = document_id.strip()
    driver = _driver()
    # Chunks that belong to this document (via HAS_PARENT from Document)
    chunk_ids: list[str] = []
    with driver.session() as session:
        r = session.run(
            "MATCH (d:Document {id: $doc_id})-[:HAS_PARENT]->(:ParentChunk)-[:HAS_CHILD]->(ch:Chunk) RETURN ch.id AS id",
            doc_id=doc_id,
        )
        chunk_ids = [str(rec["id"]) for rec in r if rec.get("id")]
    if not chunk_ids:
        driver.close()
        return lexical
    entity_ids: set[str] = set()
    with driver.session() as session:
        r = session.run(
            """
            MATCH (ch:Chunk)-[:MENTIONS]->(m:EntityMention)-[:REFERS_TO]->(e:Entity)
            WHERE ch.id IN $chunk_ids
            RETURN ch.id AS chunk_id, m, e
            """,
            chunk_ids=chunk_ids,
        )
        for rec in r:
            m, e = rec.get("m"), rec.get("e")
            if m and m.get("id"):
                lexical["nodes"].append(_node_payload({
                    "id": m["id"],
                    "label": "EntityMention",
                    "text": m.get("raw_text") or "",
                    "type": None,
                }))
                lexical["edges"].append({"source": str(rec["chunk_id"]), "target": str(m["id"]), "type": "MENTIONS"})
            if e and e.get("id"):
                eid = str(e["id"])
                entity_ids.add(eid)
                lexical["nodes"].append(_node_payload({
                    "id": e["id"],
                    "label": "Entity",
                    "text": e.get("canonical_name") or e.get("description") or "",
                    "type": e.get("type"),
                }))
                if m and m.get("id"):
                    lexical["edges"].append({"source": str(m["id"]), "target": eid, "type": "REFERS_TO"})
        r = session.run(
            """
            MATCH (ch:Chunk)-[:HAS_ENTITY]->(e:Entity) WHERE ch.id IN $chunk_ids
            RETURN ch.id AS chunk_id, e.id AS entity_id
            """,
            chunk_ids=chunk_ids,
        )
        for rec in r:
            eid = str(rec["entity_id"])
            entity_ids.add(eid)
            lexical["edges"].append({"source": str(rec["chunk_id"]), "target": eid, "type": "HAS_ENTITY"})
        # RELATES_TO: include when both endpoints are in this document's entity set
        if entity_ids:
            r = session.run(
                """
                MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
                WHERE a.id IN $entity_ids AND b.id IN $entity_ids
                RETURN a.id AS aid, b.id AS bid, type(r) AS relType
                """,
                entity_ids=list(entity_ids),
            )
            for rec in r:
                lexical["edges"].append({"source": str(rec["aid"]), "target": str(rec["bid"]), "type": rec.get("relType") or "RELATES_TO"})
    driver.close()
    # Deduplicate nodes by id
    seen = set()
    unique = []
    for n in lexical["nodes"]:
        nid = n.get("id")
        if nid and nid not in seen:
            seen.add(nid)
            unique.append(n)
    lexical["nodes"] = unique
    return lexical


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
