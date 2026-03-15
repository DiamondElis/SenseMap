"""Data contracts for ingestion and graph writes. No Neo4j or DB logic."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class NormalizedDocument(BaseModel):
    """Document as produced by ingestion; anchors chunks and provenance. IDs are stable and set upstream."""

    id: str
    source_id: str
    source_type: str
    title: str
    author: Optional[str] = None
    uri: Optional[str] = None
    created_at: Optional[datetime] = None
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestionRun(BaseModel):
    """Single run of an ingestion pipeline; linked from Document via INGESTED_IN."""

    id: str
    source_type: str
    started_at: datetime
    status: str
    version: str
    input_path: str
