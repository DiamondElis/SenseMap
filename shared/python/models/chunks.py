"""Data contracts for parent/child chunks consumed by the graph builder. No Neo4j logic."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class ParentChunk(BaseModel):
    """Parent chunk; id and document_id are stable and set upstream."""

    id: str
    document_id: str
    text: str
    position: int
    token_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChildChunk(BaseModel):
    """Child chunk; id, parent_id, document_id are stable and set upstream. Embedding optional."""

    id: str
    parent_id: str
    document_id: str
    text: str
    position: int
    token_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: Optional[list[float]] = None
