"""
Graph expansion: start from retrieved chunks or entities, traverse 1–2 hops to gather
related entities, mentions, relationships, and nearby chunks.
Traversals: Chunk -> EntityMention -> Entity; Entity -> RELATES_TO -> Entity; optional Chunk -> NEXT_CHUNK -> Chunk.
"""
from typing import Optional

from shared.python.models.retrieval import (
    EntityHit,
    RelationshipHit,
    RetrievalHit,
)

from ._neo4j import get_driver


def expand(
    chunk_hits: list[RetrievalHit],
    entity_hits: list[EntityHit] | None = None,
    max_hops: int = 2,
    max_entities: int = 10,
    max_relationships: int = 20,
    include_next_chunk: bool = True,
    *,
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
) -> tuple[list[EntityHit], list[RelationshipHit], list[RetrievalHit]]:
    """
    Expand from chunk_hits and optional entity_hits: traverse up to max_hops to collect
    related entities (Chunk->MENTIONS->EntityMention->REFERS_TO->Entity), entity-entity
    RELATES_TO, and optionally NEXT_CHUNK neighbor chunks. Returns deduplicated
    entity_hits, relationship_hits, and extra chunk hits (nearby chunks).
    """
    entity_hits = entity_hits or []
    chunk_ids = {h.node_id for h in chunk_hits}
    entity_ids = {h.entity_id for h in entity_hits}
    if not chunk_ids and not entity_ids:
        return [], [], []

    driver = get_driver(uri=uri, user=user, password=password)
    entities_out: list[EntityHit] = []
    relationships_out: list[RelationshipHit] = []
    chunks_out: list[RetrievalHit] = []

    try:
        with driver.session() as session:
            # 1) From chunks: Chunk -> MENTIONS -> EntityMention -> REFERS_TO -> Entity
            if chunk_ids:
                r = session.run(
                    """
                    MATCH (ch:Chunk)-[:MENTIONS]->(m:EntityMention)-[:REFERS_TO]->(e:Entity)
                    WHERE ch.id IN $chunk_ids
                    RETURN DISTINCT e.id AS entity_id, e.canonical_name AS canonical_name, e.type AS entity_type
                    LIMIT $max_entities
                    """,
                    chunk_ids=list(chunk_ids),
                    max_entities=max_entities,
                )
                seen_e: set[str] = set()
                for rec in r:
                    eid = rec.get("entity_id")
                    if eid and eid not in seen_e:
                        seen_e.add(eid)
                        entities_out.append(
                            EntityHit(
                                entity_id=str(eid),
                                canonical_name=(rec.get("canonical_name") or ""),
                                entity_type=(rec.get("entity_type") or ""),
                                score=1.0,
                                metadata={},
                            )
                        )

            # 2) From entities (seed or just discovered): Entity -> RELATES_TO -> Entity
            all_entity_ids = entity_ids | {e.entity_id for e in entities_out}
            if all_entity_ids:
                r = session.run(
                    """
                    MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
                    WHERE a.id IN $entity_ids OR b.id IN $entity_ids
                    RETURN a.id AS aid, a.canonical_name AS aname, b.id AS bid, b.canonical_name AS bname, type(r) AS rel_type
                    LIMIT $max_relationships
                    """,
                    entity_ids=list(all_entity_ids),
                    max_relationships=max_relationships,
                )
                seen_rel: set[tuple[str, str]] = set()
                for rec in r:
                    aid, bid = rec.get("aid"), rec.get("bid")
                    if not aid or not bid:
                        continue
                    key = (str(aid), str(bid))
                    if key in seen_rel:
                        continue
                    seen_rel.add(key)
                    relationships_out.append(
                        RelationshipHit(
                            source_id=str(aid),
                            source_name=(rec.get("aname") or ""),
                            target_id=str(bid),
                            target_name=(rec.get("bname") or ""),
                            rel_type=(rec.get("rel_type") or "RELATES_TO"),
                            score=1.0,
                            metadata={},
                        )
                    )
                    # Ensure both entities are in entity list if not already (up to max_entities)
                    for eid, ename in [(aid, rec.get("aname")), (bid, rec.get("bname"))]:
                        if len(entities_out) >= max_entities:
                            break
                        if eid and str(eid) not in {x.entity_id for x in entities_out}:
                            entities_out.append(
                                EntityHit(
                                    entity_id=str(eid),
                                    canonical_name=(ename or ""),
                                    entity_type="",
                                    score=0.0,
                                    metadata={},
                                )
                            )

            # 3) Optional: Chunk -> NEXT_CHUNK -> Chunk (nearby chunks)
            if include_next_chunk and chunk_ids and max_hops >= 1:
                current = set(chunk_ids)
                for _ in range(max_hops):
                    r = session.run(
                        """
                        MATCH (a:Chunk)-[:NEXT_CHUNK]->(b:Chunk)
                        WHERE a.id IN $ids
                        RETURN b.id AS id, b.text AS text
                        """,
                        ids=list(current),
                    )
                    next_ids: set[str] = set()
                    for rec in r:
                        nid = rec.get("id")
                        if nid and nid not in chunk_ids:
                            next_ids.add(str(nid))
                            chunks_out.append(
                                RetrievalHit(
                                    node_id=str(nid),
                                    node_label="Chunk",
                                    text=(rec.get("text") or ""),
                                    score=0.0,
                                    metadata={"expansion": "NEXT_CHUNK"},
                                    provenance={},
                                )
                            )
                    current = next_ids
                    if not current:
                        break
    finally:
        driver.close()

    return entities_out[:max_entities], relationships_out[:max_relationships], chunks_out
