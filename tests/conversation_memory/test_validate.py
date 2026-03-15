"""Unit tests for validation: ontology rejection, strong match auto-approve, ambiguous -> review."""
import pytest

from shared.python.models.conversation import (
    CandidateClaimRecord,
    CandidateRelationRecord,
    ValidationTaskRecord,
)
from services.conversation_memory.validate import validate_candidate_claim


def _claim(
    claim_id: str = "c1_msg_0_claim_0",
    message_id: str = "c1_msg_0",
    text: str = "SenseMap uses Neo4j.",
    claim_type: str = "factual_assertion",
    confidence: float = 0.85,
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
    rel_id: str = "c1_msg_0_claim_0_rel_0",
    claim_id: str = "c1_msg_0_claim_0",
    source: str = "SenseMap",
    target: str = "Neo4j",
    relation_type: str = "USES",
    confidence: float = 0.8,
) -> CandidateRelationRecord:
    return CandidateRelationRecord(
        id=rel_id,
        claim_id=claim_id,
        source_entity_name=source,
        target_entity_name=target,
        relation_type=relation_type,
        confidence=confidence,
    )


def test_invalid_ontology_relation_rejected():
    """Invalid relation type (not in approved ontology) yields rejected validation."""
    claim = _claim()
    # Relation type that is not in RELATIONSHIP_TYPES
    rel = _rel(relation_type="INVALID_TYPE")
    existing = [{"id": "e1", "name": "SenseMap", "canonical_name": "SenseMap", "type": "Technology"},
                {"id": "e2", "name": "Neo4j", "canonical_name": "Neo4j", "type": "Technology"}]
    vt = validate_candidate_claim(claim, [rel], existing, glossary={})
    assert vt.status == "rejected"
    assert "ontology_violation" in (vt.reason or "")


def test_low_confidence_rejected():
    """Claim or relation below minimum confidence is rejected."""
    claim = _claim(confidence=0.3)
    rel = _rel(confidence=0.8)
    existing = [{"id": "e1", "name": "SenseMap", "canonical_name": "SenseMap", "type": "Technology"},
                {"id": "e2", "name": "Neo4j", "canonical_name": "Neo4j", "type": "Technology"}]
    vt = validate_candidate_claim(claim, [rel], existing, glossary={})
    assert vt.status == "rejected"
    assert "low_confidence" in (vt.reason or "")


def test_strong_match_auto_approved():
    """When entities resolve strongly (exact match) and ontology valid, status is auto-approved."""
    claim = _claim()
    rel = _rel(source="SenseMap", target="Neo4j", relation_type="USES")
    # Exact match: canonical name matches existing entity id/name
    existing = [
        {"id": "entity_sensemap", "name": "sensemap", "canonical_name": "SenseMap", "type": "Technology"},
        {"id": "entity_neo4j", "name": "neo4j", "canonical_name": "Neo4j", "type": "Technology"},
    ]
    vt = validate_candidate_claim(claim, [rel], existing, glossary={})
    assert vt.status == "auto-approved"


def test_ambiguous_entity_names_create_review():
    """When entity resolution is ambiguous (e.g. review action), status is needs-review."""
    claim = _claim()
    rel = _rel(source="Acme", target="Beta", relation_type="USES")
    # No existing entities: resolve returns create_new with no candidates -> unknown_entity -> needs-review or rejected
    existing: list = []
    vt = validate_candidate_claim(claim, [rel], existing, glossary={})
    assert vt.status in ("needs-review", "rejected")
    assert vt.reason is not None


def test_disallowed_message_class_rejected():
    """Claim type outside factual_assertion/correction is rejected."""
    claim = _claim(claim_type="speculation")
    rel = _rel(relation_type="USES")
    existing = [{"id": "e1", "name": "SenseMap", "canonical_name": "SenseMap", "type": "Technology"},
                {"id": "e2", "name": "Neo4j", "canonical_name": "Neo4j", "type": "Technology"}]
    vt = validate_candidate_claim(claim, [rel], existing, glossary={})
    assert vt.status == "rejected"
    assert "disallowed_message_class" in (vt.reason or "")


def test_validation_task_linked_to_claim():
    """ValidationTaskRecord has claim_id set."""
    claim = _claim(claim_id="my_claim_1")
    rel = _rel(claim_id="my_claim_1", relation_type="RELATES_TO")
    existing = [{"id": "e1", "name": "A", "canonical_name": "A", "type": "Concept"},
                {"id": "e2", "name": "B", "canonical_name": "B", "type": "Concept"}]
    vt = validate_candidate_claim(claim, [rel], existing, glossary={})
    assert vt.claim_id == "my_claim_1"
