"""
Rerank retrieval results by combining similarity score, structural relevance, and support.
Boost: parents with multiple supporting child hits, entities connected to multiple chunks,
relationships supported by retrieved chunks. Optionally penalize overly generic entities.
Formula: final_score = semantic_score * 0.55 + structural_score * 0.25 + support_score * 0.20
Deterministic and simple.
"""
from typing import Optional

from shared.python.models.context import ContextBundle
from shared.python.models.retrieval import EntityHit, RelationshipHit, RetrievalHit


SEMANTIC_WEIGHT = 0.55
STRUCTURAL_WEIGHT = 0.25
SUPPORT_WEIGHT = 0.20

GENERIC_ENTITY_TYPES = frozenset({"DocumentTopic", "Concept"})


def _normalize_score(s: float) -> float:
    """Clamp score to [0, 1] for formula."""
    if s is None:
        return 0.0
    return max(0.0, min(1.0, float(s)))


def rerank_chunk_hits(
    hits: list[RetrievalHit],
    *,
    parent_child_count: Optional[dict[str, int]] = None,
) -> list[RetrievalHit]:
    """
    Rerank chunk/parent hits: combine semantic (existing score), structural (ParentChunk vs Chunk),
    and support (number of child hits per parent when provided). Sorted by final score descending.
    """
    if not hits:
        return []
    max_support = max(parent_child_count.values(), default=1) if parent_child_count else 1

    scored: list[tuple[float, float, float, float, RetrievalHit]] = []
    for h in hits:
        semantic = _normalize_score(h.score)
        structural = 1.0 if h.node_label == "ParentChunk" else 0.5
        support = (parent_child_count.get(h.node_id, 1) / max_support) if parent_child_count else 0.5
        support = min(1.0, support)
        final = SEMANTIC_WEIGHT * semantic + STRUCTURAL_WEIGHT * structural + SUPPORT_WEIGHT * support
        scored.append((final, semantic, structural, support, h))

    scored.sort(key=lambda x: -x[0])
    return [
        RetrievalHit(
            node_id=h.node_id,
            node_label=h.node_label,
            text=h.text,
            score=round(final, 4),
            metadata={**h.metadata, "rerank_semantic": semantic, "rerank_structural": structural, "rerank_support": support},
            provenance=h.provenance,
        )
        for final, semantic, structural, support, h in scored
    ]


def rerank_entity_hits(
    hits: list[EntityHit],
    *,
    entity_chunk_count: Optional[dict[str, int]] = None,
    entity_in_relationship: Optional[set[str]] = None,
    penalize_generic: bool = True,
) -> list[EntityHit]:
    """
    Rerank entity hits: semantic + structural (connected to a relationship) + support (mentioned by many chunks).
    Optionally penalize overly generic entity types (DocumentTopic, Concept).
    """
    if not hits:
        return []
    entity_in_relationship = entity_in_relationship or set()
    max_support = max(entity_chunk_count.values(), default=1) if entity_chunk_count else 1

    scored: list[tuple[float, float, float, float, EntityHit]] = []
    for h in hits:
        semantic = _normalize_score(h.score)
        structural = 1.0 if h.entity_id in entity_in_relationship else 0.5
        support = (entity_chunk_count.get(h.entity_id, 1) / max_support) if entity_chunk_count else 0.5
        support = min(1.0, support)
        final = SEMANTIC_WEIGHT * semantic + STRUCTURAL_WEIGHT * structural + SUPPORT_WEIGHT * support
        if penalize_generic and (h.entity_type or "").strip() in GENERIC_ENTITY_TYPES:
            final *= 0.9
        scored.append((final, semantic, structural, support, h))

    scored.sort(key=lambda x: -x[0])
    return [
        EntityHit(
            entity_id=h.entity_id,
            canonical_name=h.canonical_name,
            entity_type=h.entity_type,
            score=round(final, 4),
            metadata={**h.metadata, "rerank_semantic": semantic, "rerank_structural": structural, "rerank_support": support},
        )
        for final, semantic, structural, support, h in scored
    ]


def rerank_relationship_hits(
    hits: list[RelationshipHit],
    *,
    relationship_chunk_count: Optional[dict[tuple[str, str, str], int]] = None,
    entity_ids: Optional[set[str]] = None,
) -> list[RelationshipHit]:
    """
    Rerank relationship hits: semantic + structural (both endpoints in entity set) + support (supported by many chunks).
    """
    if not hits:
        return []
    entity_ids = entity_ids or set()
    rel_key = lambda r: (r.source_id, r.rel_type, r.target_id)
    max_support = 1
    if relationship_chunk_count:
        max_support = max(relationship_chunk_count.values(), default=1)

    scored: list[tuple[float, float, float, float, RelationshipHit]] = []
    for h in hits:
        semantic = _normalize_score(h.score)
        structural = 1.0 if (h.source_id in entity_ids and h.target_id in entity_ids) else 0.5
        key = rel_key(h)
        support = (relationship_chunk_count.get(key, 1) / max_support) if relationship_chunk_count else 0.5
        support = min(1.0, support)
        final = SEMANTIC_WEIGHT * semantic + STRUCTURAL_WEIGHT * structural + SUPPORT_WEIGHT * support
        scored.append((final, semantic, structural, support, h))

    scored.sort(key=lambda x: -x[0])
    return [
        RelationshipHit(
            source_id=h.source_id,
            source_name=h.source_name,
            target_id=h.target_id,
            target_name=h.target_name,
            rel_type=h.rel_type,
            score=round(final, 4),
            metadata={**h.metadata, "rerank_semantic": semantic, "rerank_structural": structural, "rerank_support": support},
        )
        for final, semantic, structural, support, h in scored
    ]


def rerank_bundle(
    bundle: ContextBundle,
    *,
    parent_child_count: Optional[dict[str, int]] = None,
    entity_chunk_count: Optional[dict[str, int]] = None,
    relationship_chunk_count: Optional[dict[tuple[str, str, str], int]] = None,
    penalize_generic_entities: bool = True,
) -> ContextBundle:
    """
    Rerank all list fields in the bundle. Builds entity_in_relationship and entity_ids from
    relationship_hits. Optionally pass support counts when available from retrieval/expansion.
    """
    entity_ids = {e.entity_id for e in bundle.entity_hits}
    entity_in_relationship = set()
    for r in bundle.relationship_hits:
        entity_in_relationship.add(r.source_id)
        entity_in_relationship.add(r.target_id)

    chunk_hits = rerank_chunk_hits(
        bundle.chunk_hits,
        parent_child_count=parent_child_count,
    )
    entity_hits = rerank_entity_hits(
        bundle.entity_hits,
        entity_chunk_count=entity_chunk_count,
        entity_in_relationship=entity_in_relationship,
        penalize_generic=penalize_generic_entities,
    )
    relationship_hits = rerank_relationship_hits(
        bundle.relationship_hits,
        relationship_chunk_count=relationship_chunk_count,
        entity_ids=entity_ids,
    )

    return ContextBundle(
        chunk_hits=chunk_hits,
        entity_hits=entity_hits,
        relationship_hits=relationship_hits,
        evidence=bundle.evidence,
        prompt_sections=bundle.prompt_sections,
        debug={**bundle.debug, "reranked": True},
    )
