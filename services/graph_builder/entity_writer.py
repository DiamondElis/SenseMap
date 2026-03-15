"""
Hybrid entity graph writer: Entity, EntityMention, Claim; MENTIONS, REFERS_TO, RELATES_TO, SUPPORTED_BY; optional HAS_ENTITY.
Writes canonical entities, chunk-local mentions, entity-entity semantic edges, and provenance. Marks chunks processed.
"""
import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

from .merge_utils import get_driver, run_write_query, run_batched_write


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_entity_id(canonical_name: str, entity_type: str) -> str:
    """Deterministic id for a new entity (create_new/review)."""
    key = f"{canonical_name}|{entity_type}".strip()
    return "entity_" + hashlib.sha256(key.encode()).hexdigest()[:16]


def _resolve_entity_ids(
    entities: list[dict],
    resolution_results: list[Any],
) -> list[tuple[str, str, str]]:
    """
    Return list of (entity_id, canonical_name, type) for each entity.
    Uses resolution_results[i].entity_id when set; else generates stable id from entity.
    """
    out = []
    for i, ent in enumerate(entities):
        if not isinstance(ent, dict):
            continue
        canonical = (ent.get("canonical_candidate") or ent.get("name") or "").strip()
        typ = (ent.get("type") or "").strip()
        if not canonical:
            continue
        res = resolution_results[i] if i < len(resolution_results) else None
        if res is not None and getattr(res, "entity_id", None):
            eid = str(res.entity_id)
        else:
            eid = _stable_entity_id(canonical, typ)
        out.append((eid, canonical, typ))
    return out


def _name_to_entity_id_map(entities: list[dict], resolution_results: list[Any]) -> dict[str, str]:
    """Map canonical_candidate and raw_text to resolved entity_id for relationship resolution."""
    id_list = _resolve_entity_ids(entities, resolution_results)
    name_to_id: dict[str, str] = {}
    for eid, canonical, _ in id_list:
        name_to_id[canonical.strip()] = eid
        name_to_id[canonical.strip().lower()] = eid
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        raw = (ent.get("raw_text") or "").strip()
        canonical = (ent.get("canonical_candidate") or ent.get("name") or "").strip()
        if not raw and not canonical:
            continue
        eid = name_to_id.get(canonical) or name_to_id.get(canonical.lower())
        if eid:
            if raw:
                name_to_id[raw] = eid
                name_to_id[raw.lower()] = eid
    return name_to_id


def write_entity_graph(
    chunk_id: str,
    entities: list[dict],
    relationships: list[dict],
    resolution_results: list[Any],
    extractor_name: str,
    *,
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    add_has_entity: bool = True,
) -> None:
    """
    Write entity graph for one chunk: canonical Entity nodes, EntityMention per occurrence,
    Chunk->MENTIONS->EntityMention->REFERS_TO->Entity, Entity-RELATES_TO->Entity, Claim-SUPPORTED_BY->Chunk,
    optional Chunk-HAS_ENTITY->Entity. Mark Chunk as entity_processed_at.
    resolution_results[i] corresponds to entities[i]; use entity_id when set else create new.
    """
    if not chunk_id or not chunk_id.strip():
        return
    resolved = _resolve_entity_ids(entities, resolution_results)

    driver = get_driver(uri, user, password)
    now = _now_iso()
    try:
        with driver.session() as session:
            if not resolved:
                # No entities: still mark chunk processed and create Claim for provenance
                run_write_query(
                    session,
                    "MATCH (ch:Chunk {id: $chunk_id}) SET ch.entity_processed_at = $now",
                    {"chunk_id": chunk_id, "now": now},
                )
                run_write_query(
                    session,
                    """
                    MERGE (c:Claim {id: $claim_id})
                    SET c.status = $status, c.confidence = $confidence
                    WITH c
                    MATCH (ch:Chunk {id: $chunk_id})
                    MERGE (c)-[:SUPPORTED_BY]->(ch)
                    """,
                    {"claim_id": f"claim_{chunk_id}", "status": "extracted", "confidence": 1.0, "chunk_id": chunk_id},
                )
                return

            # 1. MERGE Entity nodes (unique by id)
            entity_rows = []
            seen_eid: set[str] = set()
            for eid, canonical_name, typ in resolved:
                if eid in seen_eid:
                    continue
                seen_eid.add(eid)
                desc = ""
                for e in entities:
                    if not isinstance(e, dict):
                        continue
                    c = (e.get("canonical_candidate") or e.get("name") or "").strip()
                    if c == canonical_name or (e.get("raw_text") or "").strip() == canonical_name:
                        desc = (e.get("description") or "")[:500] if isinstance(e.get("description"), str) else ""
                        break
                entity_rows.append({
                    "id": eid,
                    "canonical_name": canonical_name,
                    "type": typ,
                    "description": desc,
                    "created_at": now,
                })
            if entity_rows:
                run_batched_write(
                    session,
                    """
                    UNWIND $rows AS row
                    MERGE (e:Entity {id: row.id})
                    SET e.canonical_name = row.canonical_name, e.type = row.type,
                        e.description = row.description, e.created_at = row.created_at
                    """,
                    entity_rows,
                )

            # 2. EntityMention and Chunk->MENTIONS->EntityMention->REFERS_TO->Entity
            mention_rows = []
            for i, (eid, canonical_name, _) in enumerate(resolved):
                ent = entities[i] if i < len(entities) and isinstance(entities[i], dict) else {}
                raw_text = (ent.get("raw_text") or canonical_name or "").strip()[:500]
                conf = ent.get("confidence")
                if conf is not None and not isinstance(conf, (int, float)):
                    try:
                        conf = float(conf)
                    except (TypeError, ValueError):
                        conf = 0.0
                if conf is None or not (0 <= conf <= 1):
                    conf = 0.0
                mention_id = f"{chunk_id}_m_{i}"
                mention_rows.append({
                    "mention_id": mention_id,
                    "chunk_id": chunk_id,
                    "entity_id": eid,
                    "raw_text": raw_text,
                    "confidence": conf,
                    "extractor": extractor_name,
                })
            if mention_rows:
                run_batched_write(
                    session,
                    """
                    UNWIND $rows AS row
                    MERGE (ch:Chunk {id: row.chunk_id})
                    MERGE (m:EntityMention {id: row.mention_id})
                    SET m.raw_text = row.raw_text, m.confidence = row.confidence, m.extractor = row.extractor
                    MERGE (e:Entity {id: row.entity_id})
                    MERGE (ch)-[:MENTIONS]->(m)
                    MERGE (m)-[:REFERS_TO]->(e)
                    """,
                    mention_rows,
                )

            # 3. Entity-[:RELATES_TO {type, confidence, source_chunk_id}]->Entity
            name_to_id = _name_to_entity_id_map(entities, resolution_results)
            rel_rows = []
            for r in relationships:
                if not isinstance(r, dict):
                    continue
                src_name = (r.get("source_name") or "").strip()
                tgt_name = (r.get("target_name") or "").strip()
                rel_type = (r.get("type") or "RELATES_TO").strip()
                conf = r.get("confidence")
                if conf is not None and not isinstance(conf, (int, float)):
                    try:
                        conf = float(conf)
                    except (TypeError, ValueError):
                        conf = 0.0
                if conf is None or not (0 <= conf <= 1):
                    conf = 0.0
                src_id = name_to_id.get(src_name) or name_to_id.get(src_name.lower())
                tgt_id = name_to_id.get(tgt_name) or name_to_id.get(tgt_name.lower())
                if not src_id or not tgt_id or src_id == tgt_id:
                    continue
                rel_rows.append({
                    "source_id": src_id,
                    "target_id": tgt_id,
                    "type": rel_type,
                    "confidence": conf,
                    "source_chunk_id": chunk_id,
                })
            if rel_rows:
                run_batched_write(
                    session,
                    """
                    UNWIND $rows AS row
                    MATCH (a:Entity {id: row.source_id}), (b:Entity {id: row.target_id})
                    MERGE (a)-[r:RELATES_TO]->(b)
                    SET r.type = row.type, r.confidence = row.confidence, r.source_chunk_id = row.source_chunk_id
                    """,
                    rel_rows,
                )

            # 4. Claim and Claim-[:SUPPORTED_BY]->Chunk
            claim_id = f"claim_{chunk_id}"
            run_write_query(
                session,
                """
                MERGE (c:Claim {id: $claim_id})
                SET c.status = $status, c.confidence = $confidence
                WITH c
                MATCH (ch:Chunk {id: $chunk_id})
                MERGE (c)-[:SUPPORTED_BY]->(ch)
                """,
                {"claim_id": claim_id, "status": "extracted", "confidence": 1.0, "chunk_id": chunk_id},
            )

            # 5. Mark chunk processed
            run_write_query(
                session,
                "MATCH (ch:Chunk {id: $chunk_id}) SET ch.entity_processed_at = $now",
                {"chunk_id": chunk_id, "now": now},
            )

            # 6. Optional Chunk-[:HAS_ENTITY]->Entity
            if add_has_entity:
                has_entity_rows = [{"chunk_id": chunk_id, "entity_id": eid} for eid, _, _ in resolved]
                run_batched_write(
                    session,
                    """
                    UNWIND $rows AS row
                    MATCH (ch:Chunk {id: row.chunk_id}), (e:Entity {id: row.entity_id})
                    MERGE (ch)-[:HAS_ENTITY]->(e)
                    """,
                    has_entity_rows,
                )
    finally:
        driver.close()
