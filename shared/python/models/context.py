"""Context bundle contract for answer pipeline: aggregated retrieval hits and evidence."""

from typing import Any

from pydantic import BaseModel, Field

from .retrieval import EntityHit, RelationshipHit, RetrievalHit


class ContextBundle(BaseModel):
    """Aggregated context for RAG: chunk hits, entity/relationship hits, evidence, and prompt sections."""

    chunk_hits: list[RetrievalHit] = Field(default_factory=list)
    entity_hits: list[EntityHit] = Field(default_factory=list)
    relationship_hits: list[RelationshipHit] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    prompt_sections: dict[str, Any] = Field(default_factory=dict)
    debug: dict[str, Any] = Field(default_factory=dict)
