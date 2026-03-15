"""
Deduplication of retrieval results: parent chunks by node_id, entities by canonical id,
relationships by (source, rel_type, target). Remove redundant chunk contexts when same parent already selected.
"""
from typing import Optional

from shared.python.models.context import ContextBundle
from shared.python.models.retrieval import EntityHit, RelationshipHit, RetrievalHit


def dedupe_chunk_hits(
    hits: list[RetrievalHit],
    *,
    keep_max_score: bool = True,
) -> list[RetrievalHit]:
    """Dedupe chunk/parent hits by node_id. Keeps first occurrence or max score per node_id."""
    if not hits:
        return []
    by_id: dict[str, RetrievalHit] = {}
    for h in hits:
        nid = h.node_id
        if nid not in by_id:
            by_id[nid] = h
        elif keep_max_score and h.score > by_id[nid].score:
            by_id[nid] = h
    return list(by_id.values())


def dedupe_entity_hits(
    hits: list[EntityHit],
    *,
    keep_max_score: bool = True,
) -> list[EntityHit]:
    """Dedupe entities by entity_id (canonical id). Keeps first or max score per entity."""
    if not hits:
        return []
    by_id: dict[str, EntityHit] = {}
    for h in hits:
        eid = h.entity_id
        if eid not in by_id:
            by_id[eid] = h
        elif keep_max_score and h.score > by_id[eid].score:
            by_id[eid] = h
    return list(by_id.values())


def dedupe_relationship_hits(
    hits: list[RelationshipHit],
    *,
    keep_max_score: bool = True,
) -> list[RelationshipHit]:
    """Dedupe relationships by (source_id, rel_type, target_id). Keeps first or max score."""
    if not hits:
        return []
    key = lambda r: (r.source_id, r.rel_type, r.target_id)
    by_key: dict[tuple[str, str, str], RelationshipHit] = {}
    for h in hits:
        k = key(h)
        if k not in by_key:
            by_key[k] = h
        elif keep_max_score and h.score > by_key[k].score:
            by_key[k] = h
    return list(by_key.values())


def remove_chunks_redundant_with_parents(
    chunk_hits: list[RetrievalHit],
    parent_node_ids: set[str],
    chunk_to_parent: dict[str, str],
) -> list[RetrievalHit]:
    """
    Remove chunk hits that are children of an already-selected parent (redundant context).
    chunk_to_parent: mapping chunk node_id -> parent node_id. If a chunk's parent is in parent_node_ids, drop it.
    """
    if not parent_node_ids or not chunk_to_parent:
        return chunk_hits
    return [
        h for h in chunk_hits
        if chunk_to_parent.get(h.node_id) not in parent_node_ids
    ]


def dedupe_bundle(
    bundle: ContextBundle,
    *,
    keep_max_score: bool = True,
    chunk_to_parent: Optional[dict[str, str]] = None,
) -> ContextBundle:
    """
    Dedupe all list fields in the bundle: chunk_hits by node_id, entity_hits by entity_id,
    relationship_hits by (source_id, rel_type, target_id). Optionally remove chunk hits that
    are redundant with already-selected parents (pass chunk_to_parent: chunk_id -> parent_id).
    """
    chunk_hits = dedupe_chunk_hits(bundle.chunk_hits, keep_max_score=keep_max_score)
    entity_hits = dedupe_entity_hits(bundle.entity_hits, keep_max_score=keep_max_score)
    relationship_hits = dedupe_relationship_hits(
        bundle.relationship_hits, keep_max_score=keep_max_score
    )

    parent_ids = {h.node_id for h in chunk_hits if h.node_label == "ParentChunk"}
    if parent_ids and chunk_to_parent:
        chunk_hits = remove_chunks_redundant_with_parents(
            chunk_hits, parent_ids, chunk_to_parent
        )
        # Again dedupe by node_id after removal (no-op if we only removed)
        chunk_hits = dedupe_chunk_hits(chunk_hits, keep_max_score=keep_max_score)

    return ContextBundle(
        chunk_hits=chunk_hits,
        entity_hits=entity_hits,
        relationship_hits=relationship_hits,
        evidence=bundle.evidence,
        prompt_sections=bundle.prompt_sections,
        debug={**bundle.debug, "deduped": True},
    )
