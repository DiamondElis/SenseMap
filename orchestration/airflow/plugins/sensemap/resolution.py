"""
Entity resolution: fuzzy matching + optional embedding similarity to cluster duplicates.
Produces a mapping from duplicate entity ids to a canonical id; caller merges in Neo4j.
"""
from __future__ import annotations

from typing import Any

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None  # type: ignore[assignment]


def _normalize(name: str) -> str:
    return " ".join(name.lower().strip().split())


def resolve_entities_fuzzy(
    entities: list[dict[str, Any]],
    score_threshold: int = 85,
) -> dict[str, str]:
    """
    Cluster entities by name similarity (same type). Returns map: entity_id -> canonical_entity_id.
    canonical = first in cluster (by id string order).
    """
    if not entities:
        return {}
    if fuzz is None:
        return {e["id"]: e["id"] for e in entities}
    by_type: dict[str, list[dict[str, Any]]] = {}
    for e in entities:
        t = e.get("type") or "OTHER"
        by_type.setdefault(t, []).append(e)
    id_to_canonical: dict[str, str] = {}
    for type_, group in by_type.items():
        sorted_group = sorted(group, key=lambda x: x["id"])
        for i, e in enumerate(sorted_group):
            eid = e["id"]
            name = _normalize(e.get("name") or "")
            if not name:
                id_to_canonical[eid] = eid
                continue
            canonical = eid
            for j, other in enumerate(sorted_group):
                if i == j:
                    continue
                oid = other["id"]
                oname = _normalize(other.get("name") or "")
                if not oname:
                    continue
                score = fuzz.ratio(name, oname)
                if score >= score_threshold:
                    canonical = id_to_canonical.get(oid, oid)
                    break
            id_to_canonical[eid] = canonical
    # Propagate: if A->B and B->C, set A->C
    changed = True
    while changed:
        changed = False
        for eid, can in list(id_to_canonical.items()):
            next_can = id_to_canonical.get(can, can)
            if next_can != can:
                id_to_canonical[eid] = next_can
                changed = True
    return id_to_canonical


def resolve_entities_embedding(
    entities: list[dict[str, Any]],
    embeddings: dict[str, list[float]],
    similarity_threshold: float = 0.92,
) -> dict[str, str]:
    """
    Cluster by embedding cosine similarity (same type). embeddings: entity_id -> vector.
    Returns map: entity_id -> canonical_entity_id.
    """
    if not embeddings or not entities:
        return resolve_entities_fuzzy(entities)
    by_type: dict[str, list[dict[str, Any]]] = {}
    for e in entities:
        t = e.get("type") or "OTHER"
        by_type.setdefault(t, []).append(e)
    id_to_canonical: dict[str, str] = {}
    for type_, group in by_type.items():
        sorted_group = sorted(group, key=lambda x: x["id"])
        for i, e in enumerate(sorted_group):
            eid = e["id"]
            vec = embeddings.get(eid)
            if not vec:
                id_to_canonical[eid] = eid
                continue
            canonical = eid
            for j, other in enumerate(sorted_group):
                if i == j:
                    continue
                oid = other["id"]
                ovec = embeddings.get(oid)
                if not ovec or len(ovec) != len(vec):
                    continue
                dot = sum(a * b for a, b in zip(vec, ovec, strict=True))
                na = sum(x * x for x in vec) ** 0.5
                nb = sum(x * x for x in ovec) ** 0.5
                if na * nb <= 0:
                    continue
                sim = dot / (na * nb)
                if sim >= similarity_threshold:
                    canonical = id_to_canonical.get(oid, oid)
                    break
            id_to_canonical[eid] = canonical
    changed = True
    while changed:
        changed = False
        for eid, can in list(id_to_canonical.items()):
            next_can = id_to_canonical.get(can, can)
            if next_can != can:
                id_to_canonical[eid] = next_can
                changed = True
    return id_to_canonical


def _follow(m: dict[str, str], k: str) -> str:
    while m.get(k, k) != k:
        k = m.get(k, k)
    return k


def resolve_entities(
    entities: list[dict[str, Any]],
    embeddings: dict[str, list[float]] | None = None,
    fuzzy_threshold: int = 85,
    embedding_threshold: float = 0.92,
) -> dict[str, str]:
    """Fuzzy matching first; if embeddings provided, also merge by embedding similarity within type."""
    if not entities:
        return {}
    id_to_canonical = resolve_entities_fuzzy(entities, score_threshold=fuzzy_threshold)
    if embeddings:
        embed_map = resolve_entities_embedding(entities, embeddings, similarity_threshold=embedding_threshold)
        for eid, can in embed_map.items():
            if can != eid:
                id_to_canonical[eid] = _follow(id_to_canonical, can)
    return id_to_canonical
