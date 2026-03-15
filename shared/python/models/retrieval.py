"""Typed retrieval result contracts for Step 4. Used by multiple retrievers and the answer pipeline."""

from typing import Any

from pydantic import BaseModel, Field


class RetrievalHit(BaseModel):
    """A single chunk or node hit from lexical/semantic retrieval."""

    node_id: str
    node_label: str
    text: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


class EntityHit(BaseModel):
    """A single entity hit from entity-level retrieval or expansion."""

    entity_id: str
    canonical_name: str
    entity_type: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class RelationshipHit(BaseModel):
    """A single relationship hit (entity–entity edge) from relationship retrieval."""

    source_id: str
    source_name: str
    target_id: str
    target_name: str
    rel_type: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)
