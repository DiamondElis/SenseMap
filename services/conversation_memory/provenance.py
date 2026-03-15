"""
Provenance for merged conversation knowledge. Enables jumping from graph facts back to supporting text.
Preserve: conversation_id, message_id, claim_id, merge_timestamp, merge_reason, validation_decision.
"""
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class MergeProvenance(BaseModel):
    """
    Provenance for a relation merged from conversation memory into the canonical graph.
    Stored on the Entity-RELATES_TO->Entity relationship so we can trace back to Conversation, Message, and Claim.
    """

    conversation_id: str
    message_id: str
    claim_id: str
    merge_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    merge_reason: str | None = None
    validation_decision: str = "auto-approved"

    def to_neo4j_props(self) -> dict[str, str | float | None]:
        """
        Flat dict for Neo4j relationship properties. Use these keys when writing RELATES_TO from conversation.
        Enables querying: which conversation/message/claim supports this edge?
        """
        return {
            "source_conversation_id": self.conversation_id,
            "source_message_id": self.message_id,
            "source_claim_id": self.claim_id,
            "merged_at": self.merge_timestamp.isoformat(),
            "merge_reason": self.merge_reason,
            "validation_decision": self.validation_decision,
            "source_layer": "conversation",
        }
