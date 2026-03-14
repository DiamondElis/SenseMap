"""
Orchestrate entity extraction → relation extraction → resolution → hybrid graph.
Run after lexical graph is populated (ingest_pdf_pipeline).
"""
from __future__ import annotations

from typing import Any

from sensemap.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, OPENAI_API_KEY
from sensemap.entity_extraction import extract_entities
from sensemap.relation_extraction import extract_relations
from sensemap.resolution import resolve_entities
from sensemap.neo4j_entity_writer import (
    load_chunks_for_extraction,
    load_entities_for_resolution,
    write_entities_and_mentions,
    write_relations,
    apply_resolution,
)


def run_entity_relation_pipeline(
    run_id: str,
    chunk_limit: int = 0,
    use_llm: bool = True,
    fuzzy_threshold: int = 85,
) -> None:
    """
    Load chunks from Neo4j -> extract entities -> write Entity + MENTIONS
    -> extract relations between co-occurring entities -> write RELATES_TO
    -> load entities -> resolve (fuzzy) -> apply resolution in Neo4j.
    chunk_limit: 0 = all chunks.
    """
    chunks = load_chunks_for_extraction(
        NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, limit=chunk_limit
    )
    if not chunks:
        return
    chunk_entities: list[tuple[str, list[dict[str, Any]]]] = []
    for chunk_id, text in chunks:
        entities = extract_entities(text, use_llm=use_llm, api_key=OPENAI_API_KEY or None)
        if entities:
            chunk_entities.append((chunk_id, entities))
    write_entities_and_mentions(chunk_entities, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    relations: list[tuple[str, str, str]] = []
    for chunk_id, entities in chunk_entities:
        if len(entities) < 2:
            continue
        text = next((t for cid, t in chunks if cid == chunk_id), "")
        pairs: list[tuple[str, str, str, str]] = []
        for i, a in enumerate(entities):
            for b in entities[i + 1 :]:
                pairs.append((a["id"], a["name"], b["id"], b["name"]))
        rels = extract_relations(
            text, pairs, use_llm=use_llm, api_key=OPENAI_API_KEY or None
        )
        relations.extend(rels)
    write_relations(relations, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    all_entities = load_entities_for_resolution(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    id_to_canonical = resolve_entities(all_entities, fuzzy_threshold=fuzzy_threshold)
    apply_resolution(id_to_canonical, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
