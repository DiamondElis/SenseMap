"""
Convert selected hits into prompt text and a structured debug object.
Sections: [Chunk Context], [Entity Context], [Relationship Context], [Evidence / Provenance].
Preserves ordering and keeps lexical and semantic evidence separate; provenance explicit for UI trace.
"""
from typing import Any, Optional

from shared.python.models.context import ContextBundle
from shared.python.models.retrieval import EntityHit, RelationshipHit, RetrievalHit

from .citations import build_citation_map


SECTION_CHUNK = "[Chunk Context]"
SECTION_ENTITY = "[Entity Context]"
SECTION_RELATIONSHIP = "[Relationship Context]"
SECTION_EVIDENCE = "[Evidence / Provenance]"


def _chunk_block(hit: RetrievalHit, index: int, citation: Optional[dict[str, Any]]) -> str:
    """Format one chunk for the prompt."""
    if citation:
        doc_title = citation.get("document_title") or citation.get("document_id") or "Unknown"
        parent_id = citation.get("parent_chunk_id") or hit.node_id
        header = f"{index}. Document: {doc_title}, ParentChunk: {parent_id}"
    else:
        header = f"{index}. Chunk: {hit.node_id}"
    text = (hit.text or "").strip()
    return f"{header}\n{text}"


def _entity_block(hit: EntityHit) -> str:
    """Format one entity line."""
    desc = (hit.metadata or {}).get("description") or ""
    return f"- {hit.canonical_name} ({hit.entity_type}): {desc}".strip()


def _relationship_block(rel: RelationshipHit) -> str:
    """Format one relationship line."""
    return f"- {rel.source_name} {rel.rel_type} {rel.target_name}"


def _evidence_lines(
    bundle: ContextBundle,
    citation_map: dict[str, Any],
) -> list[str]:
    """Build evidence/provenance bullet lines."""
    lines: list[str] = []
    chunk_cits = citation_map.get("chunk_citations") or {}
    rel_cits = citation_map.get("relationship_citations") or {}

    for hit in bundle.chunk_hits:
        c = chunk_cits.get(hit.node_id) or {}
        doc_title = c.get("document_title") or c.get("document_id") or "Unknown"
        parent_id = c.get("parent_chunk_id") or hit.node_id
        lines.append(f"- ParentChunk {parent_id} from Document {doc_title}")

    for rel in bundle.relationship_hits:
        key = (rel.source_id, rel.target_id, rel.rel_type)
        c = rel_cits.get(key) or {}
        chunk_ids = c.get("source_chunk_ids") or []
        if chunk_ids:
            for cid in chunk_ids[:5]:  # cap for readability
                lines.append(f"- Relationship derived from Chunk {cid}")
        else:
            lines.append(f"- Relationship {rel.source_name} {rel.rel_type} {rel.target_name} (no chunk source)")

    return lines


def _build_debug_context_object(
    bundle: ContextBundle,
    citation_map: dict[str, Any],
    chunk_texts: list[str],
    entity_texts: list[str],
    relationship_texts: list[str],
    evidence_lines_list: list[str],
) -> dict[str, Any]:
    """Structured object for debug and UI trace/highlighting."""
    chunk_entries = []
    for i, hit in enumerate(bundle.chunk_hits):
        c = (citation_map.get("chunk_citations") or {}).get(hit.node_id) or {}
        chunk_entries.append({
            "index": i + 1,
            "node_id": hit.node_id,
            "node_label": hit.node_label,
            "text": hit.text,
            "score": hit.score,
            "document_title": c.get("document_title"),
            "parent_chunk_id": c.get("parent_chunk_id"),
            "chunk_id": hit.node_id,
        })

    entity_entries = [
        {
            "canonical_name": h.canonical_name,
            "entity_type": h.entity_type,
            "entity_id": h.entity_id,
            "score": h.score,
            "description": (h.metadata or {}).get("description"),
        }
        for h in bundle.entity_hits
    ]

    relationship_entries = []
    rel_cits = citation_map.get("relationship_citations") or {}
    for r in bundle.relationship_hits:
        key = (r.source_id, r.target_id, r.rel_type)
        c = rel_cits.get(key) or {}
        relationship_entries.append({
            "source_id": r.source_id,
            "target_id": r.target_id,
            "source_name": r.source_name,
            "target_name": r.target_name,
            "rel_type": r.rel_type,
            "score": r.score,
            "source_chunk_ids": c.get("source_chunk_ids") or [],
        })

    return {
        "sections": {
            SECTION_CHUNK: {"entries": chunk_entries, "prompt_lines": chunk_texts},
            SECTION_ENTITY: {"entries": entity_entries, "prompt_lines": entity_texts},
            SECTION_RELATIONSHIP: {"entries": relationship_entries, "prompt_lines": relationship_texts},
            SECTION_EVIDENCE: {"lines": evidence_lines_list},
        },
        "citation_map": citation_map,
    }


def assemble(
    bundle: ContextBundle,
    citation_map: Optional[dict[str, Any]] = None,
    *,
    chunk_meta_lookup: Optional[dict[str, dict[str, Any]]] = None,
    relationship_source_chunks: Optional[dict[tuple[str, str, str], list[str]]] = None,
) -> tuple[str, dict[str, Any]]:
    """
    Convert the context bundle into prompt-ready text and a structured debug object.
    Order: chunks first, then entities, then relationships, then evidence/provenance.
    Returns (prompt_text, debug_context_object).
    """
    if citation_map is None:
        citation_map = build_citation_map(
            bundle,
            chunk_meta_lookup=chunk_meta_lookup,
            relationship_source_chunks=relationship_source_chunks,
        )

    chunk_cits = citation_map.get("chunk_citations") or {}

    # Chunk context
    chunk_blocks = [
        _chunk_block(h, i + 1, chunk_cits.get(h.node_id))
        for i, h in enumerate(bundle.chunk_hits)
    ]
    chunk_section = "\n\n".join(chunk_blocks) if chunk_blocks else "(none)"

    # Entity context
    entity_blocks = [_entity_block(h) for h in bundle.entity_hits]
    entity_section = "\n".join(entity_blocks) if entity_blocks else "(none)"

    # Relationship context
    rel_blocks = [_relationship_block(r) for r in bundle.relationship_hits]
    relationship_section = "\n".join(rel_blocks) if rel_blocks else "(none)"

    # Evidence / Provenance
    evidence_lines_list = _evidence_lines(bundle, citation_map)
    evidence_section = "\n".join(evidence_lines_list) if evidence_lines_list else "(none)"

    prompt_text = f"""{SECTION_CHUNK}
{chunk_section}

{SECTION_ENTITY}
{entity_section}

{SECTION_RELATIONSHIP}
{relationship_section}

{SECTION_EVIDENCE}
{evidence_section}
"""

    debug_context_object = _build_debug_context_object(
        bundle,
        citation_map,
        chunk_blocks,
        entity_blocks,
        rel_blocks,
        evidence_lines_list,
    )

    return prompt_text.strip(), debug_context_object
