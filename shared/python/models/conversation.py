"""
Candidate conversation memory models for Step 5. Isolated from the canonical Entity graph.
Statuses are explicit and reusable by validation and merge logic.
"""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# Explicit statuses for claims and validation tasks
ClaimStatus = Literal["pending", "auto-approved", "needs-review", "rejected", "merged"]
VALID_CLAIM_STATUSES: tuple[str, ...] = ("pending", "auto-approved", "needs-review", "rejected", "merged")

ValidationTaskStatus = Literal["pending", "auto-approved", "needs-review", "rejected", "merged"]
VALID_VALIDATION_STATUSES: tuple[str, ...] = ("pending", "auto-approved", "needs-review", "rejected", "merged")


class ConversationRecord(BaseModel):
    """One conversation session (e.g. chat thread)."""

    id: str
    source: str
    started_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageRecord(BaseModel):
    """One message in a conversation."""

    id: str
    conversation_id: str
    role: str
    text: str
    position: int
    timestamp: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CandidateClaimRecord(BaseModel):
    """Candidate claim extracted from a message; not yet merged into canonical graph."""

    id: str
    message_id: str
    text: str
    claim_type: str
    confidence: float
    status: ClaimStatus = "pending"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CandidateRelationRecord(BaseModel):
    """Candidate relation (entity–entity) tied to a claim; not yet in canonical graph."""

    id: str
    claim_id: str
    source_entity_name: str
    target_entity_name: str
    relation_type: str
    confidence: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationTaskRecord(BaseModel):
    """Validation task for a candidate claim (review, approve, reject, merge)."""

    id: str
    claim_id: str
    status: ValidationTaskStatus = "pending"
    reason: str | None = None
    reviewer: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
