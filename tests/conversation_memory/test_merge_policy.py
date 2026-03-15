"""Unit tests for merge policy: contradictions -> needs-review/rejected, merged status."""
import pytest

from shared.python.models.conversation import (
    CandidateClaimRecord,
    CandidateRelationRecord,
    ValidationTaskRecord,
)
from services.conversation_memory.merge import (
    AcceptedRelation,
    MergeResult,
    merge_decision,
    _check_contradiction_relation,
)


def _claim(
    claim_id: str = "c1_msg_0_claim_0",
    message_id: str = "c1_msg_0",
    text: str = "SenseMap uses Neo4j.",
    claim_type: str = "factual_assertion",
    confidence: float = 0.9,
) -> CandidateClaimRecord:
    return CandidateClaimRecord(
        id=claim_id,
        message_id=message_id,
        text=text,
        claim_type=claim_type,
        confidence=confidence,
        status="pending",
    )


def _rel(
    claim_id: str = "c1_msg_0_claim_0",
    source: str = "SenseMap",
    target: str = "Neo4j",
    relation_type: str = "USES",
    confidence: float = 0.85,
) -> CandidateRelationRecord:
    return CandidateRelationRecord(
        id=f"{claim_id}_rel_0",
        claim_id=claim_id,
        source_entity_name=source,
        target_entity_name=target,
        relation_type=relation_type,
        confidence=confidence,
    )


def _vt(claim_id: str, status: str = "auto-approved", reason: str | None = None) -> ValidationTaskRecord:
    return ValidationTaskRecord(id=f"vt_{claim_id}", claim_id=claim_id, status=status, reason=reason)


def test_contradiction_same_source_type_different_target_produces_review_or_rejected():
    """When (source, relation_type, target) conflicts with accepted (same source+type, different target) -> needs-review or rejected."""
    claim = _claim()
    rel = _rel(source="SenseMap", target="Neo4j", relation_type="USES")
    vt = _vt(claim.id, status="auto-approved")
    existing = [
        {"id": "e1", "name": "SenseMap", "canonical_name": "SenseMap", "type": "Technology"},
        {"id": "e2", "name": "Neo4j", "canonical_name": "Neo4j", "type": "Technology"},
    ]
    # Accepted already has SenseMap USES Redis (different target)
    accepted = [
        AcceptedRelation(source_id="e1", relation_type="USES", target_id="e_redis"),
    ]
    mr = merge_decision(claim, [rel], vt, existing, accepted, glossary={})
    # Contradiction: we're proposing SenseMap USES Neo4j but accepted has SenseMap USES Redis
    assert mr.decision in ("needs_review", "rejected")
    assert mr.reason is not None


def test_no_contradiction_same_triple_allows_auto_merge():
    """When (source, type, target) already in accepted (same triple), no contradiction."""
    contradicted, reason = _check_contradiction_relation("e1", "USES", "e2", [
        AcceptedRelation(source_id="e1", relation_type="USES", target_id="e2"),
    ])
    assert contradicted is False
    assert reason is None


def test_contradiction_different_target_detected():
    """Same source+relation_type but different target returns contradiction."""
    contradicted, reason = _check_contradiction_relation("e1", "USES", "e3", [
        AcceptedRelation(source_id="e1", relation_type="USES", target_id="e2"),
    ])
    assert contradicted is True
    assert reason == "incompatible_target"


def test_rejected_validation_does_not_auto_merge():
    """If validation status is rejected, merge_decision returns rejected."""
    claim = _claim()
    rel = _rel(relation_type="USES")
    vt = _vt(claim.id, status="rejected", reason="ontology_violation")
    existing = [
        {"id": "e1", "name": "SenseMap", "canonical_name": "SenseMap", "type": "Technology"},
        {"id": "e2", "name": "Neo4j", "canonical_name": "Neo4j", "type": "Technology"},
    ]
    mr = merge_decision(claim, [rel], vt, existing, [], glossary={})
    assert mr.decision == "rejected"
    assert mr.claim_id == claim.id


def test_auto_merge_decision_when_safe():
    """When validation auto-approved, no contradiction, valid ontology -> decision is auto_merge."""
    claim = _claim()
    rel = _rel(relation_type="USES")
    vt = _vt(claim.id, status="auto-approved")
    existing = [
        {"id": "e1", "name": "SenseMap", "canonical_name": "SenseMap", "type": "Technology"},
        {"id": "e2", "name": "Neo4j", "canonical_name": "Neo4j", "type": "Technology"},
    ]
    accepted: list[AcceptedRelation] = []
    mr = merge_decision(claim, [rel], vt, existing, accepted, glossary={})
    assert mr.decision == "auto_merge"
    assert mr.claim_id == claim.id


def test_merge_result_auto_merge_implies_safe_to_merge():
    """When merge_decision is auto_merge, claim is safe to merge (status update tested in integration)."""
    claim = _claim()
    rel = _rel()
    vt = _vt(claim.id, status="auto-approved")
    existing = [
        {"id": "e1", "name": "SenseMap", "canonical_name": "SenseMap", "type": "Technology"},
        {"id": "e2", "name": "Neo4j", "canonical_name": "Neo4j", "type": "Technology"},
    ]
    mr = merge_decision(claim, [rel], vt, existing, [], glossary={})
    assert mr.decision == "auto_merge"
    assert mr.claim_id == claim.id
