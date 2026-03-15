"""Unit tests for claim extraction: only factual assertions and corrections generate claims."""
import pytest

from shared.python.models.conversation import MessageRecord
from services.conversation_memory.extract_claims import (
    classify_message,
    extract_claims_from_conversation,
    extract_claims_from_message,
    extract_relations_from_claim,
)


def _msg(conv_id: str, position: int, text: str, role: str = "user") -> MessageRecord:
    return MessageRecord(
        id=f"{conv_id}_msg_{position}",
        conversation_id=conv_id,
        role=role,
        text=text,
        position=position,
    )


def test_only_factual_assertion_generates_claims():
    """Factual assertion message produces one candidate claim."""
    msg = _msg("c1", 0, "Neo4j is the graph backend for SenseMap.")
    claims = extract_claims_from_message(msg)
    assert len(claims) == 1
    assert claims[0].claim_type == "factual_assertion"
    assert claims[0].message_id == msg.id
    assert "Neo4j" in claims[0].text


def test_only_correction_generates_claims():
    """Correction message produces one candidate claim."""
    msg = _msg("c1", 0, "Actually, the backend is Neo4j.")
    claims = extract_claims_from_message(msg)
    assert len(claims) == 1
    assert claims[0].claim_type == "correction"


def test_question_generates_no_claims():
    """Question messages do not produce claims by default."""
    msg = _msg("c1", 0, "What is the graph backend?")
    claims = extract_claims_from_message(msg)
    assert len(claims) == 0


def test_instruction_generates_no_claims():
    """Instruction messages do not produce claims."""
    msg = _msg("c1", 0, "Please tell me about SenseMap.")
    claims = extract_claims_from_message(msg)
    assert len(claims) == 0


def test_speculation_generates_no_claims():
    """Speculation messages do not produce claims by default."""
    msg = _msg("c1", 0, "I think maybe it uses Neo4j.")
    claims = extract_claims_from_message(msg)
    assert len(claims) == 0


def test_classify_message_categories():
    """Classification returns expected category for each intent."""
    assert classify_message("What is X?", "user") == "question"
    assert classify_message("Please show me Y.", "user") == "instruction"
    assert classify_message("Maybe it is Z.", "user") == "speculation"
    assert classify_message("Actually, it is Z.", "user") == "correction"
    assert classify_message("SenseMap uses Neo4j.", "user") == "factual_assertion"


def test_extract_claims_from_conversation_mixed():
    """Only factual and correction messages contribute claims in a mixed transcript."""
    messages = [
        _msg("c1", 0, "What is the backend?"),
        _msg("c1", 1, "Neo4j is the graph backend."),
        _msg("c1", 2, "Please confirm."),
        _msg("c1", 3, "Actually, we also use Redis."),
    ]
    claims, relations = extract_claims_from_conversation(messages)
    assert len(claims) == 2  # positions 1 and 3
    assert all(c.claim_type in ("factual_assertion", "correction") for c in claims)
    assert claims[0].message_id == "c1_msg_1"
    assert claims[1].message_id == "c1_msg_3"


def test_extract_relations_use_approved_ontology_only():
    """Extracted relations use only approved relation types (e.g. USES, RELATES_TO)."""
    from shared.python.models.conversation import CandidateClaimRecord

    claim = CandidateClaimRecord(
        id="c1_msg_0_claim_0",
        message_id="c1_msg_0",
        text="SenseMap uses Neo4j for the graph.",
        claim_type="factual_assertion",
        confidence=0.85,
    )
    relations = extract_relations_from_claim(claim)
    assert len(relations) >= 1
    from services.extraction.entities.schema import is_valid_relationship_type
    for rel in relations:
        assert is_valid_relationship_type(rel.relation_type), rel.relation_type
    assert all(r.claim_id == claim.id for r in relations)


def test_every_claim_linked_to_message():
    """Every candidate claim has message_id set."""
    messages = [
        _msg("c1", 0, "Neo4j is the backend."),
        _msg("c1", 1, "Actually, we use both Neo4j and Redis."),
    ]
    claims, _ = extract_claims_from_conversation(messages)
    for c in claims:
        assert c.message_id.startswith("c1_msg_")
