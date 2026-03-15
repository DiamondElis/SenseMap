"""
Map chunk, entity, and relationship hits to source metadata for provenance and UI trace.
Provides: document title, parent chunk ID, chunk ID, and source chunk IDs for relationships.
"""
from typing import Any, Optional

from shared.python.models.context import ContextBundle
from shared.python.models.retrieval import EntityHit, RelationshipHit, RetrievalHit


def chunk_citation_from_hit(hit: RetrievalHit) -> dict[str, Any]:
    """Extract citation fields from a chunk hit's metadata/provenance."""
    meta = hit.metadata or {}
    prov = hit.provenance or {}
    return {
        "chunk_id": hit.node_id,
        "parent_chunk_id": meta.get("parent_chunk_id") or prov.get("parent_chunk_id"),
        "document_id": meta.get("document_id") or prov.get("document_id"),
        "document_title": meta.get("document_title") or prov.get("document_title") or hit.node_id,
    }


def relationship_citation_from_hit(rel: RelationshipHit) -> dict[str, Any]:
    """Extract source chunk IDs for a relationship from metadata."""
    meta = rel.metadata or {}
    chunk_ids = meta.get("source_chunk_ids") or meta.get("source_chunk_id")
    if isinstance(chunk_ids, str):
        chunk_ids = [chunk_ids]
    return {
        "source_chunk_ids": list(chunk_ids) if chunk_ids else [],
        "source_id": rel.source_id,
        "target_id": rel.target_id,
        "rel_type": rel.rel_type,
    }


def build_citation_map(
    bundle: ContextBundle,
    *,
    chunk_meta_lookup: Optional[dict[str, dict[str, Any]]] = None,
    relationship_source_chunks: Optional[dict[tuple[str, str, str], list[str]]] = None,
) -> dict[str, Any]:
    """
    Build a citation map from the bundle and optional lookups.
    chunk_meta_lookup: node_id -> {document_title, parent_chunk_id, chunk_id, document_id}
    relationship_source_chunks: (source_id, target_id, rel_type) -> [chunk_id]
    Returns dict with chunk_citations (node_id -> citation) and relationship_citations (key -> citation).
    """
    chunk_meta_lookup = chunk_meta_lookup or {}
    relationship_source_chunks = relationship_source_chunks or {}

    chunk_citations: dict[str, dict[str, Any]] = {}
    for h in bundle.chunk_hits:
        c = chunk_citation_from_hit(h)
        override = chunk_meta_lookup.get(h.node_id)
        if override:
            c.update(override)
        chunk_citations[h.node_id] = c

    relationship_citations: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in bundle.relationship_hits:
        key = (r.source_id, r.target_id, r.rel_type)
        cit = relationship_citation_from_hit(r)
        if key in relationship_source_chunks:
            cit["source_chunk_ids"] = list(relationship_source_chunks[key])
        relationship_citations[key] = cit

    return {
        "chunk_citations": chunk_citations,
        "relationship_citations": relationship_citations,
    }
