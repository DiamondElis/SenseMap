"""
Merge policy and contradiction checks for Step 5 conversation memory.
Decides: auto_merge, needs_review, or rejected. When auto-approved, execute_merge writes
canonical relations with provenance and updates candidate status to merged.
Safe claims can auto-merge; ambiguous or conflicting claims become review tasks; rejected stay in candidate memory.
"""
from datetime import datetime, timezone
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, Field

from shared.python.models.conversation import (
    CandidateClaimRecord,
    CandidateRelationRecord,
    ValidationTaskRecord,
)
from services.extraction.entities.schema import is_valid_relationship_type
from services.graph_builder.merge_utils import get_driver, run_batched_write, run_write_query

from services.conversation_memory.provenance import MergeProvenance
from services.conversation_memory.validate import (
    MIN_CLAIM_CONFIDENCE,
    MIN_RELATION_CONFIDENCE,
    STRONG_RESOLUTION_ACTIONS,
    _resolve_entity_name,
)


MergeDecision = Literal["auto_merge", "needs_review", "rejected"]

# Claim types that are allowed to be considered for merge (factual or correction only)
ALLOWED_CLAIM_TYPES_FOR_MERGE = frozenset({"factual_assertion", "correction"})

# Message class that marks speculative source; do not auto-merge
SPECULATIVE_MESSAGE_CLASS = "speculation"


class AcceptedRelation(BaseModel):
    """One accepted relation in the canonical graph (for contradiction checks)."""

    source_id: str
    relation_type: str
    target_id: str


class AcceptedProperty(BaseModel):
    """One accepted entity property (for contradiction checks)."""

    entity_id: str
    property_key: str
    value: Any


class MergeResult(BaseModel):
    """Result of merge policy: decision and reason; no graph write."""

    decision: MergeDecision
    reason: str | None = None
    claim_id: str
    validation_task_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


def _normalize_triple(source_id: str, relation_type: str, target_id: str) -> tuple[str, str, str]:
    """Normalize for set membership."""
    return (str(source_id).strip(), str(relation_type).strip(), str(target_id).strip())


def _check_contradiction_relation(
    source_id: str | None,
    relation_type: str,
    target_id: str | None,
    accepted_relations: list[AcceptedRelation],
) -> tuple[bool, str | None]:
    """
    Check if (source_id, relation_type, target_id) contradicts accepted facts.
    Returns (has_contradiction, reason).
    - Same (source, relation_type) but different target -> incompatible target.
    - Same triple -> no conflict (duplicate).
    """
    if source_id is None or target_id is None:
        return False, None
    key = (source_id, relation_type, target_id)
    accepted_tuples = {_normalize_triple(r.source_id, r.relation_type, r.target_id) for r in accepted_relations}
    if key in accepted_tuples:
        return False, None
    # Same source + relation_type, different target
    for r in accepted_relations:
        if (r.source_id, r.relation_type) == (source_id, relation_type) and r.target_id != target_id:
            return True, "incompatible_target"
    return False, None


def _check_contradiction_property(
    entity_id: str | None,
    property_key: str | None,
    value: Any,
    accepted_properties: list[AcceptedProperty],
) -> bool:
    """Same entity + property key but different value -> contradiction."""
    if not entity_id or not property_key:
        return False
    for p in accepted_properties:
        if p.entity_id == entity_id and p.property_key == property_key:
            if p.value != value:
                return True
    return False


def _resolve_relation_entities(
    rel: CandidateRelationRecord,
    existing_entities: list[dict[str, Any]],
    glossary: dict[str, Any],
    *,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> tuple[str | None, str | None, bool, bool]:
    """
    Resolve source and target names to entity IDs using Step 3 resolution.
    Returns (source_entity_id, target_entity_id, source_strong, target_strong).
    """
    res_src = _resolve_entity_name(
        (rel.source_entity_name or "").strip(),
        existing_entities,
        glossary,
        embed_fn=embed_fn,
    )
    res_tgt = _resolve_entity_name(
        (rel.target_entity_name or "").strip(),
        existing_entities,
        glossary,
        embed_fn=embed_fn,
    )
    src_id = res_src.entity_id if res_src.action in STRONG_RESOLUTION_ACTIONS else None
    tgt_id = res_tgt.entity_id if res_tgt.action in STRONG_RESOLUTION_ACTIONS else None
    src_strong = res_src.action in STRONG_RESOLUTION_ACTIONS and res_src.confidence >= MIN_RELATION_CONFIDENCE
    tgt_strong = res_tgt.action in STRONG_RESOLUTION_ACTIONS and res_tgt.confidence >= MIN_RELATION_CONFIDENCE
    return src_id, tgt_id, src_strong, tgt_strong


def merge_decision(
    claim: CandidateClaimRecord,
    relation_candidates: list[CandidateRelationRecord],
    validation_task: ValidationTaskRecord,
    existing_entities: list[dict[str, Any]],
    accepted_relations: list[AcceptedRelation],
    *,
    accepted_properties: list[AcceptedProperty] | None = None,
    glossary: dict[str, Any] | None = None,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> MergeResult:
    """
    Apply merge policy and contradiction checks. Does not write to the canonical graph.
    - Auto-merge only when: strong entity match, valid relation type, confidence above threshold,
      no contradiction, source not marked speculative.
    - Otherwise create a review task (needs_review) or reject (rejected).
    Rejected claims remain in candidate memory for auditability.
    """
    glossary = glossary or {}
    accepted_properties = accepted_properties or []
    reasons: list[str] = []

    # Reject if validation already rejected
    if validation_task.status == "rejected":
        return MergeResult(
            decision="rejected",
            reason=validation_task.reason or "validation_rejected",
            claim_id=claim.id,
            validation_task_id=validation_task.id,
            metadata={"source": "validation"},
        )

    # Ontology and malformed checks (merge-level)
    if claim.claim_type not in ALLOWED_CLAIM_TYPES_FOR_MERGE:
        return MergeResult(
            decision="rejected",
            reason="disallowed_claim_type",
            claim_id=claim.id,
            validation_task_id=validation_task.id,
            metadata={"claim_type": claim.claim_type},
        )
    if claim.confidence < MIN_CLAIM_CONFIDENCE:
        return MergeResult(
            decision="rejected",
            reason="low_confidence",
            claim_id=claim.id,
            validation_task_id=validation_task.id,
        )

    msg_class = (claim.metadata or {}).get("message_class")
    if msg_class == SPECULATIVE_MESSAGE_CLASS:
        reasons.append("speculative_source")

    # Relation-level: ontology, confidence, malformed, entity type (if we had types)
    for rel in relation_candidates:
        if not is_valid_relationship_type(rel.relation_type):
            return MergeResult(
                decision="rejected",
                reason="ontology_violation",
                claim_id=claim.id,
                validation_task_id=validation_task.id,
                metadata={"relation_type": rel.relation_type},
            )
        if rel.confidence < MIN_RELATION_CONFIDENCE:
            reasons.append("low_relation_confidence")
        src_name = (rel.source_entity_name or "").strip()
        tgt_name = (rel.target_entity_name or "").strip()
        if not src_name or not tgt_name:
            return MergeResult(
                decision="rejected",
                reason="malformed_extraction",
                claim_id=claim.id,
                validation_task_id=validation_task.id,
            )
        if src_name.lower() == tgt_name.lower():
            reasons.append("self_loop_requires_review")

    # Contradiction detection against accepted graph
    for rel in relation_candidates:
        src_id, tgt_id, src_strong, tgt_strong = _resolve_relation_entities(
            rel, existing_entities, glossary, embed_fn=embed_fn
        )
        contradicted, reason = _check_contradiction_relation(src_id, rel.relation_type, tgt_id, accepted_relations)
        if contradicted:
            reasons.append(reason or "contradiction")

    # Needs-review: validation said so, or ambiguous / weakly grounded / correction vs stored
    if validation_task.status == "needs-review":
        reasons.append("validation_needs_review")
    if claim.claim_type == "correction":
        # Correction that contradicts stored claim already added above as contradiction
        if any(r in reasons for r in ("contradiction", "incompatible_target")):
            reasons.append("correction_contradicts_stored")

    # Final decision
    if reasons:
        unique = sorted(set(reasons))
        if "ontology_violation" in unique or "malformed_extraction" in unique or "disallowed_claim_type" in unique:
            return MergeResult(
                decision="rejected",
                reason="; ".join(unique),
                claim_id=claim.id,
                validation_task_id=validation_task.id,
                metadata={"reasons": unique},
            )
        return MergeResult(
            decision="needs_review",
            reason="; ".join(unique),
            claim_id=claim.id,
            validation_task_id=validation_task.id,
            metadata={"reasons": unique},
        )

    # Auto-merge only if validation was auto-approved and no contradictions
    if validation_task.status != "auto-approved":
        return MergeResult(
            decision="needs_review",
            reason=validation_task.reason or "validation_not_auto_approved",
            claim_id=claim.id,
            validation_task_id=validation_task.id,
        )

    # All checks passed: strong match, valid type, confidence OK, no contradiction, not speculative
    return MergeResult(
        decision="auto_merge",
        reason=None,
        claim_id=claim.id,
        validation_task_id=validation_task.id,
        metadata={"relation_count": len(relation_candidates)},
    )


class ExecuteMergeResult(BaseModel):
    """Result of executing a merge: relations written and candidate status updated."""

    claim_id: str
    relations_written: int = 0
    candidate_status_updated: bool = False
    provenance: MergeProvenance | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def execute_merge(
    claim: CandidateClaimRecord,
    relation_candidates: list[CandidateRelationRecord],
    validation_task: ValidationTaskRecord,
    merge_result: MergeResult,
    existing_entities: list[dict[str, Any]],
    conversation_id: str,
    *,
    glossary: dict[str, Any] | None = None,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
) -> ExecuteMergeResult:
    """
    When merge_result.decision == "auto_merge": write accepted relations into the canonical graph
    with provenance (conversation_id, message_id, claim_id, merge_timestamp, merge_reason, validation_decision),
    then set candidate claim status to merged. Idempotent: MERGE and SET so re-runs do not duplicate.
    Rejected and needs-review claims are not written; candidate layer remains queryable for audit.
    """
    glossary = glossary or {}
    out = ExecuteMergeResult(claim_id=claim.id)

    if merge_result.decision != "auto_merge":
        return out

    provenance = MergeProvenance(
        conversation_id=conversation_id,
        message_id=claim.message_id,
        claim_id=claim.id,
        merge_timestamp=datetime.now(timezone.utc),
        merge_reason=merge_result.reason,
        validation_decision=validation_task.status or "auto-approved",
    )
    out.provenance = provenance
    neo4j_props = provenance.to_neo4j_props()

    rel_rows: list[dict[str, Any]] = []
    for rel in relation_candidates:
        src_id, tgt_id, src_strong, tgt_strong = _resolve_relation_entities(
            rel, existing_entities, glossary, embed_fn=embed_fn
        )
        if not src_strong or not tgt_strong or not src_id or not tgt_id or src_id == tgt_id:
            continue
        conf = rel.confidence if isinstance(rel.confidence, (int, float)) else 0.0
        if not (0 <= conf <= 1):
            conf = 0.0
        rel_rows.append({
            "source_id": src_id,
            "target_id": tgt_id,
            "type": (rel.relation_type or "RELATES_TO").strip(),
            "confidence": conf,
            **neo4j_props,
        })

    if not rel_rows:
        return out

    driver = get_driver(uri=uri, user=user, password=password)
    try:
        with driver.session() as session:
            run_batched_write(
                session,
                """
                UNWIND $rows AS row
                MATCH (a:Entity {id: row.source_id}), (b:Entity {id: row.target_id})
                MERGE (a)-[r:RELATES_TO]->(b)
                SET r.type = row.type, r.confidence = row.confidence,
                    r.source_conversation_id = row.source_conversation_id,
                    r.source_message_id = row.source_message_id,
                    r.source_claim_id = row.source_claim_id,
                    r.merged_at = row.merged_at,
                    r.merge_reason = row.merge_reason,
                    r.validation_decision = row.validation_decision,
                    r.source_layer = row.source_layer
                """,
                rel_rows,
            )
            out.relations_written = len(rel_rows)

            run_write_query(
                session,
                """
                MERGE (cc:CandidateClaim {id: $claim_id})
                SET cc.message_id = $message_id, cc.text = $text, cc.claim_type = $claim_type,
                    cc.confidence = $confidence, cc.status = $status
                WITH cc
                MATCH (m:Message {id: $message_id})
                MERGE (cc)-[:FROM_MESSAGE]->(m)
                """,
                {
                    "claim_id": claim.id,
                    "message_id": claim.message_id,
                    "text": claim.text,
                    "claim_type": claim.claim_type,
                    "confidence": claim.confidence,
                    "status": "merged",
                },
            )
            out.candidate_status_updated = True
    finally:
        driver.close()

    out.metadata["relation_count"] = len(rel_rows)
    return out
