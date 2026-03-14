"""
Write Entity nodes, (Chunk)-[:MENTIONS]->(Entity), (Entity)-[:RELATES_TO]->(Entity).
Apply resolution: merge duplicate entities and re-point MENTIONS/RELATES_TO to canonical.
"""
from typing import Any

from sensemap.neo4j_writer import _driver
from sensemap.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


def load_chunks_for_extraction(
    uri: str = NEO4J_URI,
    user: str = NEO4J_USER,
    password: str = NEO4J_PASSWORD,
    limit: int = 0,
) -> list[tuple[str, str]]:
    """Return list of (chunk_id, text) for chunks that have text. limit=0 means no limit."""
    driver = _driver(uri, user, password)
    out: list[tuple[str, str]] = []
    with driver.session() as session:
        q = "MATCH (c:Chunk) WHERE c.text IS NOT NULL AND size(c.text) > 0 RETURN c.id AS id, c.text AS text"
        if limit > 0:
            q += f" LIMIT {limit}"
        r = session.run(q)
        for rec in r:
            out.append((rec["id"], rec["text"] or ""))
    driver.close()
    return out


def load_entities_for_resolution(
    uri: str = NEO4J_URI,
    user: str = NEO4J_USER,
    password: str = NEO4J_PASSWORD,
) -> list[dict[str, Any]]:
    """Return all Entity nodes as [{id, name, type}, ...] for resolution."""
    driver = _driver(uri, user, password)
    out: list[dict[str, Any]] = []
    with driver.session() as session:
        r = session.run("MATCH (e:Entity) RETURN e.id AS id, e.name AS name, e.type AS type")
        for rec in r:
            out.append({"id": rec["id"], "name": rec["name"] or "", "type": rec["type"] or "OTHER"})
    driver.close()
    return out


def write_entities_and_mentions(
    chunk_entities: list[tuple[str, list[dict[str, Any]]]],
    uri: str = NEO4J_URI,
    user: str = NEO4J_USER,
    password: str = NEO4J_PASSWORD,
) -> None:
    """
    chunk_entities: list of (chunk_id, [entity dicts with id, name, type]).
    Creates Entity nodes and (Chunk)-[:MENTIONS]->(Entity).
    """
    driver = _driver(uri, user, password)
    with driver.session() as session:
        for chunk_id, entities in chunk_entities:
            for e in entities:
                session.run(
                    """
                    MERGE (e:Entity {id: $id})
                    SET e.name = $name, e.type = $type
                    WITH e
                    MATCH (c:Chunk {id: $chunk_id})
                    MERGE (c)-[:MENTIONS]->(e)
                    """,
                    id=e["id"],
                    name=e.get("name", ""),
                    type=e.get("type", "OTHER"),
                    chunk_id=chunk_id,
                )
    driver.close()


def write_relations(
    relations: list[tuple[str, str, str]],
    uri: str = NEO4J_URI,
    user: str = NEO4J_USER,
    password: str = NEO4J_PASSWORD,
) -> None:
    """relations: (entity_a_id, entity_b_id, relation_type). Creates (Entity)-[:RELATES_TO {type: ...}]->(Entity)."""
    if not relations:
        return
    driver = _driver(uri, user, password)
    with driver.session() as session:
        for a_id, b_id, rel_type in relations:
            if a_id == b_id:
                continue
            session.run(
                """
                MATCH (a:Entity {id: $a_id}), (b:Entity {id: $b_id})
                MERGE (a)-[r:RELATES_TO]->(b)
                SET r.type = $type
                """,
                a_id=a_id,
                b_id=b_id,
                type=rel_type[:64] if rel_type else "RELATED_TO",
            )
    driver.close()


def apply_resolution(
    id_to_canonical: dict[str, str],
    uri: str = NEO4J_URI,
    user: str = NEO4J_USER,
    password: str = NEO4J_PASSWORD,
) -> None:
    """
    Merge duplicate entities: for each non-canonical entity, point MENTIONS and RELATES_TO to canonical,
    then delete the duplicate entity (or leave and merge in a second step). Simple approach:
    - For (Chunk)-[:MENTIONS]->(Entity e): if e.id maps to canonical c, create (Chunk)-[:MENTIONS]->(c), delete old relationship.
    - For (Entity)-[r:RELATES_TO]-(Entity): re-point to canonicals and collapse duplicates.
    """
    if not id_to_canonical:
        return
    driver = _driver(uri, user, password)
    with driver.session() as session:
        for eid, can in id_to_canonical.items():
            if eid == can:
                continue
            # Re-point MENTIONS from Chunk->eid to Chunk->can
            session.run(
                """
                MATCH (c:Chunk)-[m:MENTIONS]->(e:Entity {id: $eid})
                MATCH (canon:Entity {id: $can})
                MERGE (c)-[:MENTIONS]->(canon)
                DELETE m
                """,
                eid=eid,
                can=can,
            )
            # Re-point RELATES_TO: (eid)-[r]->(other) => (can)-[r]->(canonical(other)); (other)-[r]->(eid) => (canonical(other))->(can)
            session.run(
                """
                MATCH (e:Entity {id: $eid})-[r:RELATES_TO]->(other:Entity)
                MATCH (canon:Entity {id: $can})
                WITH canon, other, r
                MERGE (canon)-[r2:RELATES_TO]->(other)
                SET r2.type = r.type
                DELETE r
                """,
                eid=eid,
                can=can,
            )
            session.run(
                """
                MATCH (other:Entity)-[r:RELATES_TO]->(e:Entity {id: $eid})
                MATCH (canon:Entity {id: $can})
                WITH canon, other, r
                MERGE (other)-[r2:RELATES_TO]->(canon)
                SET r2.type = r.type
                DELETE r
                """,
                eid=eid,
                can=can,
            )
            # Outgoing RELATES_TO from canonical to duplicate: remove (canon)-[r]->(eid), avoid self-loop
            session.run(
                "MATCH (canon:Entity {id: $can})-[r:RELATES_TO]->(e:Entity {id: $eid}) DELETE r",
                eid=eid,
                can=can,
            )
        # Delete orphan Entity nodes that were merged away
        for eid, can in id_to_canonical.items():
            if eid == can:
                continue
            session.run(
                "MATCH (e:Entity {id: $eid}) WHERE NOT (e)<-[:MENTIONS]-() AND NOT (e)-[:RELATES_TO]-() DETACH DELETE e",
                eid=eid,
            )
    driver.close()
