"""
Candidate claim and relation extraction from conversation messages (Step 5).
Classify messages; only factual assertions and corrections produce candidate claims.
Use approved ontology from Step 3 (RELATIONSHIP_TYPES). All output is candidate-memory only.
"""
import re
from typing import Literal

from shared.python.models.conversation import (
    CandidateClaimRecord,
    CandidateRelationRecord,
    MessageRecord,
)
from services.extraction.entities.schema import RELATIONSHIP_TYPES, is_valid_relationship_type


MessageClass = Literal["factual_assertion", "question", "instruction", "speculation", "correction"]

# Heuristics: phrases that suggest each class (lowercased)
QUESTION_STARTS = ("what", "which", "who", "when", "where", "why", "how", "is ", "are ", "do ", "does ", "can ", "could ", "?")
INSTRUCTION_STARTS = ("please", "can you", "could you", "would you", "tell me", "show me", "let's", "we should")
SPECULATION_PHRASES = ("i think", "maybe", "perhaps", "might", "could be", "not sure", "not certain", "brainstorm", "idea:")
CORRECTION_PHRASES = ("actually", "no,", "correction", "i meant", "i meant to say", "sorry,", "that's wrong", "instead,")


def classify_message(text: str, role: str) -> MessageClass:
    """
    Classify a message into factual assertion, question, instruction, speculation, or correction.
    Rule-based; does not treat all text as a claim.
    """
    t = (text or "").strip()
    if not t:
        return "factual_assertion"  # empty -> treat as neutral
    lower = t.lower()
    if any(lower.startswith(p) for p in CORRECTION_PHRASES) or lower.startswith("no, "):
        return "correction"
    if t.endswith("?") or any(lower.startswith(p) for p in QUESTION_STARTS):
        return "question"
    if any(p in lower for p in INSTRUCTION_STARTS):
        return "instruction"
    if any(p in lower for p in SPECULATION_PHRASES):
        return "speculation"
    return "factual_assertion"


def _claim_id(message_id: str, index: int) -> str:
    return f"{message_id}_claim_{index}"


def _relation_id(claim_id: str, index: int) -> str:
    return f"{claim_id}_rel_{index}"


def _default_confidence_for_class(msg_class: MessageClass) -> float:
    if msg_class == "correction":
        return 0.75
    return 0.85


def _extract_relation_candidates_from_text(text: str) -> list[tuple[str, str, str, float]]:
    """
    Heuristic: look for "X relation_type Y" or "X VERB Y" patterns.
    Returns list of (source_entity_name, target_entity_name, relation_type, confidence).
    Only relation_type in RELATIONSHIP_TYPES is allowed; default RELATES_TO if unknown.
    """
    results: list[tuple[str, str, str, float]] = []
    # Normalize: use only approved types
    allowed = set(RELATIONSHIP_TYPES)
    # Simple pattern: "X is Y" -> RELATES_TO; "X uses Y" -> USES; "X part of Y" -> PART_OF
    lower = (text or "").lower()
    # "X uses Y", "X use Y"
    for m in re.finditer(r"(\w+(?:\s+\w+)*)\s+uses?\s+(\w+(?:\s+\w+)*)", lower, re.IGNORECASE):
        src, tgt = m.group(1).strip().title(), m.group(2).strip().title()
        if src and tgt and "USES" in allowed:
            results.append((src, tgt, "USES", 0.8))
    for m in re.finditer(r"(\w+(?:\s+\w+)*)\s+is\s+(?:the\s+)?(?:graph\s+)?(\w+(?:\s+\w+)*)", lower, re.IGNORECASE):
        src, tgt = m.group(1).strip().title(), m.group(2).strip().title()
        if src and tgt and len(src) > 1 and len(tgt) > 1:
            results.append((src, tgt, "RELATES_TO", 0.7))
    for m in re.finditer(r"(\w+(?:\s+\w+)*)\s+(?:influences?|influence)\s+(\w+(?:\s+\w+)*)", lower, re.IGNORECASE):
        src, tgt = m.group(1).strip().title(), m.group(2).strip().title()
        if src and tgt and "INFLUENCES" in allowed:
            results.append((src, tgt, "INFLUENCES", 0.8))
    for m in re.finditer(r"(\w+(?:\s+\w+)*)\s+part\s+of\s+(\w+(?:\s+\w+)*)", lower, re.IGNORECASE):
        src, tgt = m.group(1).strip().title(), m.group(2).strip().title()
        if src and tgt and "PART_OF" in allowed:
            results.append((src, tgt, "PART_OF", 0.75))
    return results


def extract_claims_from_message(
    message: MessageRecord,
    *,
    produce_claims_for: tuple[MessageClass, ...] = ("factual_assertion", "correction"),
) -> list[CandidateClaimRecord]:
    """
    Extract candidate claims from a single message. Only messages classified as
    factual_assertion or correction (by default) produce claims. Each claim is linked to message.id.
    """
    msg_class = classify_message(message.text, message.role)
    if msg_class not in produce_claims_for:
        return []
    claims: list[CandidateClaimRecord] = []
    # One claim per message for now: the full message text as the claim text
    claim_type = "factual_assertion" if msg_class == "factual_assertion" else "correction"
    confidence = _default_confidence_for_class(msg_class)
    claim_id = _claim_id(message.id, 0)
    claims.append(
        CandidateClaimRecord(
            id=claim_id,
            message_id=message.id,
            text=message.text.strip(),
            claim_type=claim_type,
            confidence=confidence,
            status="pending",
            metadata={"message_class": msg_class},
        )
    )
    return claims


def extract_relations_from_claim(
    claim: CandidateClaimRecord,
) -> list[CandidateRelationRecord]:
    """
    Extract candidate relations from a claim's text. Only approved relation types
    (Step 3 RELATIONSHIP_TYPES) are used; invalid types are not emitted.
    Each relation is linked to claim.id.
    """
    relations: list[CandidateRelationRecord] = []
    candidates = _extract_relation_candidates_from_text(claim.text)
    for i, (src, tgt, rel_type, conf) in enumerate(candidates):
        if not is_valid_relationship_type(rel_type):
            rel_type = "RELATES_TO"
        rel_id = _relation_id(claim.id, i)
        relations.append(
            CandidateRelationRecord(
                id=rel_id,
                claim_id=claim.id,
                source_entity_name=src,
                target_entity_name=tgt,
                relation_type=rel_type,
                confidence=conf,
                metadata={},
            )
        )
    return relations


def extract_claims_from_conversation(
    messages: list[MessageRecord],
    *,
    produce_claims_for: tuple[MessageClass, ...] = ("factual_assertion", "correction"),
) -> tuple[list[CandidateClaimRecord], list[CandidateRelationRecord]]:
    """
    Classify each message, extract candidate claims only from factual assertions and corrections,
    then extract candidate relations from each claim using the approved ontology.
    Returns (claims, relations); every claim has message_id set.
    """
    claims: list[CandidateClaimRecord] = []
    relations: list[CandidateRelationRecord] = []
    for msg in messages:
        msg_claims = extract_claims_from_message(msg, produce_claims_for=produce_claims_for)
        for c in msg_claims:
            claims.append(c)
            relations.extend(extract_relations_from_claim(c))
    return claims, relations
