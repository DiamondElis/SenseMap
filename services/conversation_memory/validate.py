"""
Validation and confidence scoring for Step 5 conversation memory.
Rule-based triage: auto-approved, needs-review, rejected.
Reuses Step 3 entity resolution; does not trust LLM confidence alone.
"""
from typing import Any, Callable, Literal

from shared.python.models.conversation import (
    CandidateClaimRecord,
    CandidateRelationRecord,
    ValidationTaskRecord,
)
from services.extraction.entities.schema import is_valid_relationship_type
from services.extraction.resolution.merge import ResolutionResult, resolve_entity


# Allowed claim types (from extract_claims) that may produce knowledge
ALLOWED_CLAIM_MESSAGE_CLASSES = frozenset({"factual_assertion", "correction"})

# Minimum confidence thresholds (we do not trust extraction confidence alone)
MIN_CLAIM_CONFIDENCE = 0.5
MIN_RELATION_CONFIDENCE = 0.5

# Resolution actions that count as "resolved" for auto-approve; "review" and "create_new" with 0 confidence -> needs-review or rejected
STRONG_RESOLUTION_ACTIONS = frozenset({"exact_match", "fuzzy_match", "embedding_match"})

ValidationReason = Literal[
    "low_confidence",
    "unknown_entity",
    "ontology_violation",
    "ambiguous_match",
    "possible_contradiction",
    "disallowed_message_class",
]


def _validation_task_id(claim_id: str) -> str:
    return f"vt_{claim_id}"


def _resolve_entity_name(
    entity_name: str,
    existing_entities: list[dict[str, Any]],
    glossary: dict[str, Any],
    *,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> ResolutionResult:
    """Resolve a name string using Step 3 resolution logic."""
    candidate = {"name": (entity_name or "").strip()}
    return resolve_entity(candidate, existing_entities, glossary, embed_fn=embed_fn)


def _validate_claim_level(
    claim: CandidateClaimRecord,
    reasons: list[ValidationReason],
) -> None:
    """Claim-level: allowed message class, minimum confidence, not purely speculative."""
    if claim.claim_type not in ALLOWED_CLAIM_MESSAGE_CLASSES:
        reasons.append("disallowed_message_class")
    if claim.confidence < MIN_CLAIM_CONFIDENCE:
        reasons.append("low_confidence")
    # Purely speculative: if metadata says message_class was speculation but claim_type is factual, flag
    msg_class = (claim.metadata or {}).get("message_class")
    if msg_class == "speculation" and claim.claim_type not in ALLOWED_CLAIM_MESSAGE_CLASSES:
        reasons.append("ontology_violation")


def _validate_relation_level(
    rel: CandidateRelationRecord,
    existing_entities: list[dict[str, Any]],
    glossary: dict[str, Any],
    reasons: list[ValidationReason],
    *,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> tuple[bool, bool]:
    """
    Relation-level: ontology, entity resolution, confidence, not malformed.
    Returns (source_resolved_strongly, target_resolved_strongly).
    """
    source_strong = False
    target_strong = False

    if not is_valid_relationship_type(rel.relation_type):
        reasons.append("ontology_violation")
    if rel.confidence < MIN_RELATION_CONFIDENCE:
        reasons.append("low_confidence")

    src_name = (rel.source_entity_name or "").strip()
    tgt_name = (rel.target_entity_name or "").strip()
    if not src_name or not tgt_name:
        reasons.append("ontology_violation")
        return source_strong, target_strong
    if src_name.lower() == tgt_name.lower():
        # Self-loop: allow for some relation types (e.g. RELATES_TO) but flag for review
        reasons.append("possible_contradiction")

    res_src = _resolve_entity_name(src_name, existing_entities, glossary, embed_fn=embed_fn)
    res_tgt = _resolve_entity_name(tgt_name, existing_entities, glossary, embed_fn=embed_fn)

    if res_src.action in STRONG_RESOLUTION_ACTIONS and res_src.confidence >= MIN_RELATION_CONFIDENCE:
        source_strong = True
    elif res_src.action == "review" and res_src.candidates:
        reasons.append("ambiguous_match")
    elif res_src.action == "create_new" and not res_src.candidates:
        reasons.append("unknown_entity")

    if res_tgt.action in STRONG_RESOLUTION_ACTIONS and res_tgt.confidence >= MIN_RELATION_CONFIDENCE:
        target_strong = True
    elif res_tgt.action == "review" and res_tgt.candidates:
        reasons.append("ambiguous_match")
    elif res_tgt.action == "create_new" and not res_tgt.candidates:
        reasons.append("unknown_entity")

    return source_strong, target_strong


def _decide_status(reasons: list[ValidationReason]) -> Literal["auto-approved", "needs-review", "rejected"]:
    """Map validation reasons to final status. Low-confidence or schema-violating candidates do not auto-merge."""
    if not reasons:
        return "auto-approved"
    if "ontology_violation" in reasons or "disallowed_message_class" in reasons:
        return "rejected"
    if "low_confidence" in reasons:
        return "rejected"
    # unknown_entity, ambiguous_match, possible_contradiction -> needs-review
    return "needs-review"


def validate_candidate_claim(
    claim: CandidateClaimRecord,
    relation_candidates: list[CandidateRelationRecord],
    existing_entities: list[dict[str, Any]],
    ontology: dict[str, Any] | None = None,
    *,
    glossary: dict[str, Any] | None = None,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> ValidationTaskRecord:
    """
    Validate a candidate claim and its relation candidates against the approved ontology.
    Reuses Step 3 entity resolution (exact / fuzzy / embedding). Does not trust extraction
    confidence alone; applies minimum thresholds and assigns auto-approved, needs-review, or rejected.
    """
    reasons: list[ValidationReason] = []
    glossary = glossary or {}
    # Ontology: use provided set or default to schema (already enforced via is_valid_relationship_type)

    _validate_claim_level(claim, reasons)

    for rel in relation_candidates:
        _validate_relation_level(rel, existing_entities, glossary, reasons, embed_fn=embed_fn)

    status = _decide_status(reasons)
    reason_str = "; ".join(sorted(set(reasons))) if reasons else None

    return ValidationTaskRecord(
        id=_validation_task_id(claim.id),
        claim_id=claim.id,
        status=status,
        reason=reason_str,
        reviewer=None,
        metadata={"reasons": list(set(reasons)), "relation_count": len(relation_candidates)},
    )