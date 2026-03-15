"""Post-retrieval context builders: deduplication, reranking, budgeting, citations, and assembly."""

from .dedupe import dedupe_bundle, dedupe_chunk_hits, dedupe_entity_hits, dedupe_relationship_hits
from .rerank import rerank_bundle, rerank_chunk_hits, rerank_entity_hits, rerank_relationship_hits
from .budget import (
    apply_budget,
    BudgetConfig,
    estimate_chunk_tokens,
    estimate_entity_tokens,
    estimate_relationship_tokens,
    DEFAULT_MAX_PARENTS,
    DEFAULT_MAX_ENTITY_EXPANSIONS,
    DEFAULT_MAX_RELATIONSHIP_LINES,
    DEFAULT_MAX_TOTAL_TOKENS,
)
from .citations import (
    build_citation_map,
    chunk_citation_from_hit,
    relationship_citation_from_hit,
)
from .assemble import assemble, SECTION_CHUNK, SECTION_ENTITY, SECTION_RELATIONSHIP, SECTION_EVIDENCE

__all__ = [
    "dedupe_bundle",
    "dedupe_chunk_hits",
    "dedupe_entity_hits",
    "dedupe_relationship_hits",
    "rerank_bundle",
    "rerank_chunk_hits",
    "rerank_entity_hits",
    "rerank_relationship_hits",
    "apply_budget",
    "BudgetConfig",
    "estimate_chunk_tokens",
    "estimate_entity_tokens",
    "estimate_relationship_tokens",
    "DEFAULT_MAX_PARENTS",
    "DEFAULT_MAX_ENTITY_EXPANSIONS",
    "DEFAULT_MAX_RELATIONSHIP_LINES",
    "DEFAULT_MAX_TOTAL_TOKENS",
    "build_citation_map",
    "chunk_citation_from_hit",
    "relationship_citation_from_hit",
    "assemble",
    "SECTION_CHUNK",
    "SECTION_ENTITY",
    "SECTION_RELATIONSHIP",
    "SECTION_EVIDENCE",
]
